# Backend Interview Revision: Cache, JWT, and Logger

This guide provides a comprehensive overview of the full flows, common interview questions, and **Python/FastAPI code implementations** for Caching, JSON Web Tokens (JWT), and Logging.

---

## 1. Caching (e.g., Redis)

Caching is the process of storing copies of frequently accessed data in a temporary, fast-access storage layer (usually RAM) to reduce database load and improve application response times.

### The Full Flow (Cache-Aside Pattern)
1. **Client Request**: The client requests data (e.g., `GET /users/123`).
2. **Check Cache**: The backend checks the Cache (e.g., Redis) using a specific key (e.g., `user:123`).
3. **Cache Hit**: If data is found, return it immediately. The DB is not touched.
4. **Cache Miss**: If data is *not* found, query the Database. Write the result to the Cache (usually with a TTL), then return it to the client.
5. **Data Update**: When data is updated, update the Database and then **invalidate** (delete) the corresponding cache key.

### Code Example: FastAPI + Redis (Cache-Aside)
```python
import json
from fastapi import FastAPI
import redis.asyncio as redis

app = FastAPI()
# Initialize Redis connection
redis_client = redis.from_url("redis://localhost", decode_responses=True)

async def fetch_user_from_db(user_id: int):
    # Simulate an expensive DB query
    return {"id": user_id, "name": "John Doe", "email": "john@example.com"}

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    cache_key = f"user:{user_id}"
    
    # 1. Check Cache
    cached_user = await redis_client.get(cache_key)
    if cached_user:
        return {"source": "cache", "data": json.loads(cached_user)}
    
    # 2. Cache Miss -> Query Database
    user_data = await fetch_user_from_db(user_id)
    
    # 3. Write to Cache with a TTL (e.g., 60 seconds)
    await redis_client.setex(cache_key, 60, json.dumps(user_data))
    
    return {"source": "database", "data": user_data}
```

### Interview Questions & Answers
**Q1: What is the difference between Cache-Aside, Write-Through, and Write-Behind caching?**
*   **Cache-Aside**: App checks cache, if miss, queries DB and populates cache (shown above).
*   **Write-Through**: App writes to cache, cache synchronously writes to DB. Data is always consistent.
*   **Write-Behind (Write-Back)**: App writes to cache, cache asynchronously writes to DB later. Extremely fast, but risk of data loss.

**Q2: How do you handle Cache Invalidation?**
*   **TTL (Time-To-Live)**: Absolute expiration time.
*   **Event-Driven/Active**: Actively delete (`await redis_client.delete(cache_key)`) when a write operation occurs on an entity.

**Q3: What is the "Thundering Herd" (or Cache Stampede) problem?**
*   **Problem**: A popular cache key expires. Thousands of concurrent requests miss the cache simultaneously and hit the DB, crashing it.
*   **Solution**: Locking/Mutex (only the first thread queries DB while others wait) or Stale-While-Revalidate (return stale data while background thread updates cache).

---

## 2. JWT (JSON Web Tokens)

JWT is an open standard for securely transmitting information. It is stateless, meaning the server doesn't need to store session data.

### The Full Flow (Authentication & Authorization)
1. **Login**: Client sends username/password.
2. **Verification**: Backend verifies credentials against DB.
3. **Token Generation**: Backend generates a JWT (`Header.Payload.Signature`) signed with a Secret Key.
4. **Token Delivery**: Server sends the JWT to the client.
5. **Subsequent Requests**: Client includes JWT in the `Authorization: Bearer <token>` header.
6. **Token Validation**: Middleware intercepts the request, verifies the signature using the Secret Key. If it matches, the user is authenticated.

### Code Example: FastAPI + PyJWT
```python
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

app = FastAPI()

SECRET_KEY = "your-super-secret-signing-key"
ALGORITHM = "HS256"
# Extracts the token from the "Authorization: Bearer ..." header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- 1. Token Generation ---
def create_access_token(data: dict, expires_delta: timedelta = timedelta(minutes=15)):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    # Create the Header.Payload.Signature token
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- 2. Token Validation Dependency ---
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # This decode function validates the signature AND the expiration (exp) automatically
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise credentials_exception
        
    return {"user_id": user_id}

# --- 3. Protected Route ---
@app.get("/protected-route")
async def read_protected_data(current_user: dict = Depends(get_current_user)):
    return {"message": "You are authenticated!", "user_id": current_user["user_id"]}
```

### Interview Questions & Answers
**Q1: What are the pros and cons of JWTs vs Session Cookies?**
*   **Pros**: Stateless (easy to scale), cross-domain friendly (CORS), mobile-app friendly.
*   **Cons**: Cannot be easily revoked before expiration, larger payload size.

**Q2: Since JWTs are stateless, how do you revoke them?**
*   **Short Expiry + Refresh Tokens**: Give access token a short life (15 mins). Revoke the Refresh Token in the DB.
*   **Blocklist/Denylist**: Store revoked JWT signatures in Redis. Middleware checks Redis on every request.

**Q3: Explain Symmetric vs. Asymmetric Signing in JWT.**
*   **Symmetric (HS256)**: Single secret key used to both sign and verify.
*   **Asymmetric (RS256)**: Private Key used to sign, Public Key used to verify. Ideal for microservices (Auth service signs, other services verify).

---

## 3. Logger (Application Logging with `structlog`)

Logging records events and system states. It is crucial for debugging and monitoring distributed systems. Your application uses **`structlog`**, a modern Python logging library designed specifically for **structured logging** (JSON outputs) and context binding.

### Code Breakdown: `structlog` & Correlation ID Setup

**1. The `structlog` Configuration (`app/core/logging.py`)**
```python
import structlog

processors = [
    structlog.contextvars.merge_contextvars, # <--- The Magic Key for Correlation IDs!
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]
# Switch output format based on environment
renderer = structlog.processors.JSONRenderer() if settings.LOG_JSON else structlog.dev.ConsoleRenderer()

structlog.configure(
    processors=processors + [renderer],
    # ... other stdlib bridge configs
)
```
*   **Processors Pipeline**: In `structlog`, a log event is passed through a chain of functions called processors before being written. First, it merges context variables, then adds the log level (`INFO`), then adds an ISO timestamp, etc.
*   **Renderer**: If `settings.LOG_JSON` is True (Production), it uses `JSONRenderer()`, turning logs into machine-readable JSON strings for Elasticsearch. If False (Development), it uses `ConsoleRenderer()`, which color-codes output for developers to read in the terminal.
*   **`merge_contextvars`**: This is the most critical processor for tracing. It looks into Python's `contextvars` (which are safe to use in async/await concurrent environments) and automatically pulls variables (like `correlation_id`) into every log event.

**2. The Middleware Dispatch Method (`app/middleware/RequestLoggingMiddleware.py`)**
```python
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Extract or generate ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        
        # 2. Bind to structlog context
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        
        start_time = time.time()
        logger.info("request_started", method=request.method, path=request.url.path)

        try:
            # 3. Route request
            response = await call_next(request)
            
            process_time = time.time() - start_time
            response.headers["X-Correlation-ID"] = correlation_id
            
            logger.info("request_finished", status_code=response.status_code, duration=round(process_time, 4))
            return response
        finally:
            # 4. Cleanup!
            structlog.contextvars.clear_contextvars()
```
*   **`bind_contextvars`**: This is where we inject the `correlation_id` we grabbed from the header (or generated via UUID). Once we bind it here, *every single log statement* executed anywhere else in the code during this specific request's lifecycle will automatically have `{"correlation_id": "..."}` attached to it. You don't need to manually pass the ID down to your services or database layers!
*   **The `try/finally` block**: This is incredibly important. In an asynchronous server like FastAPI, thread/worker loops are reused. If you don't call `clear_contextvars()` in a `finally` block, the `correlation_id` from Request A might "leak" and accidentally get printed in the logs of Request B!
*   **Returning the ID**: `response.headers["X-Correlation-ID"] = correlation_id` attaches the ID to the *outgoing response headers*. If a user encounters a 500 error, their browser's network tab will show this `X-Correlation-ID`. They can give this ID to customer support, and you can search Kibana/Datadog to instantly find the exact stack trace for their failed request.

### Interview Questions & Answers
**Q1: What are the standard Log Levels?**
*   **DEBUG**: Developer details.
*   **INFO**: Standard operational events.
*   **WARNING**: Recoverable, unexpected issues.
*   **ERROR**: Operation failed, but system running.
*   **CRITICAL**: System-level failure requiring immediate attention.

**Q2: What is Structured Logging and why does this codebase use `structlog`?**
*   Structured logging means outputting logs as key-value pairs (like JSON) instead of flat text strings.
*   `structlog` is used because it separates the *formatting* of logs (JSON vs Console) from the *data collection*. It makes it trivial to bind context (like a `correlation_id`) at the start of a request and have it automatically apply to all downstream logs.

**Q3: What is a Correlation ID / Trace ID?**
*   A unique UUID generated at the API edge and passed down. It allows developers to trace a single request's path across multiple microservices or deep within a monolith by searching for that single ID.

**Q4: What should you absolutely NEVER log?**
*   **PII (Personally Identifiable Information)**: Unmasked SSNs, passwords, JWTs, API keys. Use log masking libraries to filter these out.
