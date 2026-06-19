# Structured Logging (Structlog): Strategy & Implementation

## 1. Concept Overview

**What it is:**
Structured logging is the practice of outputting logs as structured data (usually JSON) rather than plain-text strings. **Structlog** is a library that forces developers to log events as key-value pairs (e.g., `logger.info("user_login", user_id=123)`). 

**Why it is used:**
In a modern backend, searching through plain text logs using Regex is slow and brittle. By outputting JSON, tools like Datadog, ELK (Elasticsearch), or CloudWatch can easily parse, index, and query logs. Furthermore, Structlog allows us to "bind" contextual variables (like a `correlation_id`) to a request, ensuring *every* log emitted during that request automatically includes that ID, making debugging asynchronous microservices effortless.

---

## 2. Project Setup (Configuration)

The logging initialization lives in `app/core/logging.py`. The project hijacks the standard library `logging` module and pipes it through Structlog's processor chain.

### Structlog Configuration & Processors
The processors determine *how* the log is formatted before it is rendered to the console or file.

```python
# app/core/logging.py
import logging
from logging.handlers import RotatingFileHandler
import structlog
from app.core.config import settings

def setup_logging() -> None:
    # 1. Clear existing handlers to prevent duplicate logs
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.propagate = False

    # 2. Define the structlog processor chain
    processors = [
        structlog.contextvars.merge_contextvars, # Injects variables like correlation_id
        structlog.stdlib.add_log_level,          # Adds "level": "info"
        structlog.stdlib.add_logger_name,        # Adds "logger": "app.services.auth"
        structlog.processors.TimeStamper(fmt="iso"), # Adds ISO 8601 timestamp
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,    # Properly formats exceptions
    ]

    # 3. Dynamic Renderer: JSON for Prod, human-readable for Dev
    renderer = structlog.processors.JSONRenderer() if settings.LOG_JSON else structlog.dev.ConsoleRenderer()
    
    # 4. Bind structlog to stdlib
    formatter = structlog.stdlib.ProcessorFormatter(processor=renderer, foreign_pre_chain=processors)
    structlog.configure(
        processors=processors + [renderer],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # 5. Add File Handler
    if settings.ENABLE_FILE_LOGGING:
        log_path = os.path.join(settings.LOG_DIR, "app.log")
        file_handler = RotatingFileHandler(log_path, maxBytes=settings.LOG_MAX_BYTES, backupCount=settings.LOG_BACKUP_COUNT)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
```

### Module Initialization
To ensure logging is configured before any other modules emit logs, it is imported as a side-effect at the top of `app/main.py`.

```python
# app/main.py
from app.core import logging  # noqa: F401  — initialises structlog
```

---

## 3. Key Code Walkthrough

### Contextual Request Middleware
The `RequestLoggingMiddleware` is critical. It intercepts every incoming HTTP request, generates a `correlation_id`, and binds it using `contextvars`. This guarantees that *any* log emitted downstream (even deep in a database service) will include this ID.

```python
# app/middleware/RequestLoggingMiddleware.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import structlog
import uuid

logger = structlog.get_logger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate or extract Trace ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        
        # BIND to structlog context
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        
        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
        )

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            
            logger.info(
                "request_finished",
                method=request.method,
                status_code=response.status_code,
            )
            return response
        finally:
            # CRITICAL: Prevent context leakage to other async workers
            structlog.contextvars.clear_contextvars()
```

### Real Usage: Service Layer
Because the middleware handles the context, the service layer simply imports `structlog` and logs events as key-value dictionaries.

```python
# app/services/auth_service.py
import structlog
logger = structlog.get_logger(__name__)

class AuthService:
    def login(self, form_data):
        logger.info("login_attempt", username=form_data.username)
        
        # ... logic ...
        
        if not user:
            logger.warning("login_failed", username=form_data.username, reason="user_not_found")
            raise UnauthorizedException()
            
        logger.info("login_success", user_id=user.id)
```
*Output in JSON mode:*
`{"event": "login_success", "user_id": 42, "correlation_id": "abc-123", "level": "info", "timestamp": "2026-..."}`

---

## 4. End-to-End Flow

1. **Application Startup:** `app/main.py` runs `setup_logging()`. The JSON renderer and processors are attached to the root logger.
2. **Request Incoming:** An HTTP GET hits the API.
3. **Middleware Interception:** `RequestLoggingMiddleware` generates a `uuid4` correlation ID and calls `bind_contextvars()`. It logs `"request_started"`.
4. **Service Execution:** The router routes the request to a service. The service calls `logger.info("db_query", table="users")`. Structlog automatically injects the bound `correlation_id` into the JSON payload.
5. **Response Sent:** The middleware logs `"request_finished"` including the status code and duration.
6. **Cleanup:** `clear_contextvars()` is executed in the `finally` block to ensure the worker thread's memory is cleared for the next incoming request.

---

## 5. Design Decisions

1. **`contextvars` over `threading.local`:** 
   FastAPI uses asynchronous `async/await` workers. Traditional thread-locals (used by older logging tools) fail here because multiple requests can share the same thread. `structlog.contextvars` natively supports asyncio, ensuring variables don't leak between concurrent requests.
2. **Hijacking the Stdlib Logger:** 
   By routing `logging.getLogger()` through Structlog, even third-party libraries (like SQLAlchemy, Uvicorn, or Boto3) that use standard Python logging will automatically be formatted as JSON and include our correlation IDs.
3. **JSON vs Console Renderer:** 
   JSON is impossible to read quickly in a terminal during development. The `settings.LOG_JSON` toggle switches to `structlog.dev.ConsoleRenderer()` locally (which uses nice colors and aligned columns), while preserving machine-readable JSON in production.

---

## 6. Alternatives & Trade-offs

* **Standard Python `logging` + `jsonlogger`:**
  * *Alternative:* Using the built-in logging module combined with a library like `python-json-logger`.
  * *Trade-off:* While it achieves JSON output, the standard library doesn't easily support bound contextual variables across async boundaries. Developers often end up manually passing `correlation_id` to every single function, cluttering the business logic.
* **Loguru:**
  * *Alternative:* Using `loguru`, another popular Python logging library.
  * *Trade-off:* Loguru is easier to set up out of the box, but Structlog's processor pipeline is more explicitly configurable and industry-standard for complex enterprise environments.

---

## 7. Interview Questions & Answers

**Q1: What is a Correlation ID (or Trace ID), and why is it necessary?**
*Answer:* A correlation ID is a unique identifier attached to an incoming request. In concurrent environments or microservices, logs from hundreds of simultaneous requests are interleaved. By attaching the correlation ID to every log entry, you can filter your logging platform (like Datadog) by that ID to see the exact sequential path of a single request.

**Q2: Why do you need `clear_contextvars()` in the `finally` block of your middleware?**
*Answer:* FastAPI uses an ASGI server (Uvicorn) with persistent worker processes that handle multiple async requests over time. If we don't clear the context variables at the end of the request, the `correlation_id` from Request A might leak and be attached to the logs of Request B handled by the same worker later.

**Q3: How do you ensure logs from third-party libraries (like SQLAlchemy) conform to your JSON format?**
*Answer:* We configured `structlog` to integrate with the standard library `logging` module. We cleared the root logger's default handlers and attached our own `ProcessorFormatter`. Because third-party libraries use `logging.getLogger()`, their logs flow through our Structlog pipeline and are output as JSON.

---

## 8. Bonus: Common Mistakes & Performance Insights

* **Logging PII (Personally Identifiable Information):** A major risk with structured logging is inadvertently logging sensitive data by dumping entire request dicts (e.g., `logger.info("payload", data=request.body)`). Always explicitly define keys, like `logger.info("user_updated", user_id=user.id)`.
* **String formatting inside the log call:** Using f-strings (`logger.info(f"User {user_id} logged in")`) defeats the purpose of structured logging. You lose the ability to query by the discrete `user_id` field in your log aggregator. Always pass variables as kwargs: `logger.info("user_logged_in", user_id=user_id)`.
