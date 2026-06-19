# Application & Request Lifecycle: Strategy & Implementation

## 1. Concept Overview

**What it is:**
The lifecycle defines exactly what happens from the moment the application server boots up, to the microsecond an HTTP request enters the system, all the way to the response being returned to the client and the memory being cleaned up.

**Why it is used:**
Understanding the lifecycle is critical for managing state, preventing memory leaks, and tracking down bugs. By strictly defining how middlewares intercept traffic, how database sessions are scoped to requests, and how global exceptions are caught, the FastAPI backend ensures robust, stateless, and observable request handling.

---

## 2. Project Setup (App Initialization & Middleware Wiring)

When `uvicorn` boots the application, it loads `app.main:app`. At this stage, static configurations are evaluated, the structlog logging engine initializes, and the middleware pipeline is assembled.

### Application Factory & Middleware Stack
Middlewares run in the reverse order they are added (the outermost wrapper is added first). `RequestLoggingMiddleware` is added first so it wraps the entire request execution.

```python
# app/main.py
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.middleware.RequestLoggingMiddleware import RequestLoggingMiddleware
from app.core.exceptions import register_exception_handlers
from app.core import logging  # noqa: F401  — initialises structlog immediately on import

app = FastAPI(
    title="Learning Platform API",
    version="1.0.0",
)

# ── Middleware (outermost first) ─────────────────────────────────────────
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes & Exception Handlers ──────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")
register_exception_handlers(app)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
```

---

## 3. Key Code Walkthrough

### The Request Shell (Middleware)
Every incoming HTTP request passes through the `RequestLoggingMiddleware` before hitting routing logic. It generates a correlation ID, logs the start time, `await call_next(request)` hands control to the router, and the `finally` block ensures context is safely cleared.

```python
# app/middleware/RequestLoggingMiddleware.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import time
import structlog
import uuid

logger = structlog.get_logger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        
        # Bind the correlation ID so all downstream logs include it
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        
        start_time = time.time()
        logger.info("request_started", method=request.method, path=request.url.path)

        try:
            # Yield control to the rest of the application
            response = await call_next(request)
            
            process_time = time.time() - start_time
            response.headers["X-Correlation-ID"] = correlation_id

            logger.info("request_finished", status_code=response.status_code, duration=round(process_time, 4))
            return response
        finally:
            # Always clear context vars to prevent leaking to other requests in async workers
            structlog.contextvars.clear_contextvars()
```

### The Database Session Scope
FastAPI uses Python Generator functions (`yield`) as a dependency to map the lifecycle of a database connection perfectly to the lifecycle of the HTTP request.

```python
# app/api/deps.py
from typing import Generator
from app.db.session import SessionLocal

def get_db() -> Generator:
    """
    Yield a database session per request, ensuring cleanup on exit.
    """
    db = SessionLocal()
    try:
        # Hand the session to the route handler
        yield db
    finally:
        # Guarantee the connection is returned to the pool after the response is built
        db.close()
```

### The Exception Catch-All
If business logic fails (e.g., a `ConflictException` is raised), it bubbles up out of the route. Before it crashes the server, the global exception handler catches it, logs it, and safely translates it to an HTTP response.

```python
# app/core/exceptions.py
from fastapi import Request
from fastapi.responses import JSONResponse

class AppException(Exception):
    def __init__(self, detail: str, status_code: int = 500):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)

def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Convert AppException subclasses into structured JSON responses."""
    logger.warning("app_exception", status_code=exc.status_code, detail=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
```

---

## 4. End-to-End Request Lifecycle

1. **Client Sends Request:** An HTTP GET request arrives at `uvicorn` (ASGI Server).
2. **Middleware Entry:** The request hits `RequestLoggingMiddleware`. A trace ID is generated, the context is bound, and the timer starts.
3. **CORS Check:** The `CORSMiddleware` validates the origin.
4. **Routing & Dependency Resolution:** FastAPI matches the URL to a route. It sees the `db: Session = Depends(get_db)` parameter.
5. **Session Creation:** The `get_db` generator fires, creating a new `SessionLocal()` object, pulling a connection from the SQLAlchemy pool. The generator `yields` execution to the route handler.
6. **Execution:** The route handler (and related services) run their business logic using the injected `db` session.
7. **Response Creation:** The handler returns a Pydantic model, which FastAPI serializes to JSON.
8. **Dependency Teardown:** The `get_db` generator resumes execution after the `yield`, running the `finally` block to call `db.close()` (returning the connection to the pool).
9. **Middleware Exit:** Execution bubbles back to the `RequestLoggingMiddleware`. The process duration is calculated, `request_finished` is logged, and `clear_contextvars()` runs.
10. **Client Receives Response:** The HTTP response leaves the server.

---

## 5. Design Decisions

1. **Generator Dependencies (`yield`):**
   Using `yield` in the dependency injection container guarantees that teardown logic (`db.close()`) runs even if the route handler throws an unhandled exception. This absolutely prevents database connection leaks.
2. **Centralized Exception Handling:**
   Instead of cluttering service logic with `try/except` and returning raw `fastapi.HTTPException`, services raise clean Python domain exceptions (like `ConflictException`). The global handlers at the ASGI level map these domain errors to JSON responses cleanly.
3. **Context Vars in Middleware:**
   Because FastAPI relies on `asyncio` (where a single OS thread multiplexes hundreds of concurrent requests), traditional Thread-Local storage fails. ContextVars guarantee that the trace ID injected at the start of the lifecycle doesn't leak into another concurrent request's lifecycle.

---

## 6. Alternatives & Trade-offs

* **Middleware vs. Dependencies for DB Sessions:**
  * *Alternative:* Injecting the database session via a global Middleware (`request.state.db = SessionLocal()`) instead of FastAPI Dependencies (`Depends(get_db)`).
  * *Trade-off:* Middleware runs on *every single* request, even endpoints that don't need a database (like `/health`). This wastes connections. The `Depends` approach ensures a connection is only pulled from the pool if the specific route actually requires it.
* **Lifespan Events vs Side Effects:**
  * *Alternative:* Currently, logging is initialized via a module-level side effect (`from app.core import logging`). Alternatively, we could use FastAPI's `@asynccontextmanager` `lifespan` event.
  * *Trade-off:* Lifespan events are elegant for starting background tasks or ML models, but logging needs to be ready *before* ASGI routing even starts, making side-effect initialization often the safest path for base infrastructure.

---

## 7. Interview Questions & Answers

**Q1: What happens to the database connection if a route throws a massive unhandled exception?**
*Answer:* Because the `get_db` dependency uses a `try...finally` block around its `yield` statement, FastAPI's dependency injection system guarantees that the `finally` block will execute as the stack unwinds. The `db.close()` method runs securely, rolling back any uncommitted transaction and returning the connection to the pool, preventing connection leaks.

**Q2: Why do we clear context variables (`clear_contextvars()`) at the end of the RequestLoggingMiddleware?**
*Answer:* Uvicorn/FastAPI uses an asynchronous event loop, meaning a single worker thread handles many requests over its lifetime. If we don't clear the context variables, the `correlation_id` set during Request A might persist in memory and accidentally get attached to Request B if the event loop reuses the same context space.

**Q3: Why raise custom `AppException` objects instead of returning HTTP Responses directly from your Service layer?**
*Answer:* The Service layer should be framework-agnostic. It shouldn't know about HTTP status codes, headers, or FastAPI JSONResponses. By raising custom Python exceptions (like `NotFoundException`), the service logic remains clean. The API layer (via global exception handlers configured in `main.py`) acts as the translator, catching those exceptions and formatting them into HTTP 404 responses.

---

## 8. Bonus: Common Mistakes & Performance Insights

* **Async `call_next` Blocking:** In middleware, the `await call_next(request)` line executes the entire remainder of the application logic. If you put heavy synchronous CPU-bound logic inside an async middleware before or after `call_next`, you will freeze the entire event loop for all other concurrent requests.
* **Returning Data from `get_db`:** A common mistake is returning `db.commit()` inside the `finally` block of the `get_db` dependency. The `get_db` lifecycle manager should *only* manage connections (`db.close()`). Explicit commits should be handled by the business logic, otherwise, you might accidentally commit partial state if an error happened during serialization.
