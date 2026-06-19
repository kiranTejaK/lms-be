# Backend Coding & Scaffold Interview Questions
*(Based on FastAPI, Redis, Structlog, and SQLAlchemy)*

## 1. Project Architecture Highlights

### Logging & Observability (`structlog`)
This project implements a robust, structured logging architecture using `structlog` backed by Python's standard `logging` library.
- **Structured Output**: In production, it emits JSON logs. This is critical for observability tools (like Datadog, ELK, or CloudWatch) which natively index JSON keys (e.g., `user_id`, `request_id`). This allows developers to instantly query logs and trace errors across distributed systems.
- **Middleware Integration**: A custom `RequestLoggingMiddleware` automatically intercepts every incoming HTTP request. It logs a `request_started` event, followed by a `request_finished` event detailing the HTTP method, URL, status code, and precise `process_time`.
- **File Rotation**: It utilizes a `RotatingFileHandler` to safely write logs to disk (e.g., `logs/app.log`), automatically rolling them over to prevent log files from indefinitely consuming server disk space (max 5MB per file, keeping 5 backups).
- **Context Injection**: Uses processor chains to automatically inject ISO-8601 timestamps, the logger module name, exception tracebacks, and severity levels into every log event seamlessly.

### Caching Layer (`Redis`)
The project utilizes Redis as a fast, intermediate caching layer sitting between the FastAPI service layer and the PostgreSQL database to reduce database load for read-heavy operations.
- **Graceful Degradation**: Core cache operations (`cache_get` and `cache_set`) are wrapped in `try/except redis.RedisError` blocks. If the Redis server crashes or experiences a network timeout, the application explicitly catches the error, logs a warning, and degrades gracefully by fetching the data directly from PostgreSQL. This ensures high availability.
- **Decorator-based Caching**: A custom `@redis_cache` Python decorator is applied directly to service methods. It dynamically generates a unique Redis key (either hashed for paginated queries, or deterministic for single entities). On a cache miss, it executes the underlying SQL query, serializes the result, stores it in Redis with a TTL (Time To Live), and returns it.
- **Cache Invalidation**: On data mutation (create/update/delete), the services explicitly call a `clear_cache()` utility that uses glob pattern matching (e.g., `clear_cache("*:courses:*")`) to immediately evict stale data from the cache, ensuring data consistency.

---

## 2. Expected Coding & Scaffold Questions

Based on the architectural patterns above, interviewers will likely ask you to write the code that powers these exact systems. Here are 5 practical scaffold coding questions you should be prepared to answer on a whiteboard or during a live coding session.

### Question 1: Implement a Request Logging Middleware
**Prompt:** Write a custom ASGI Middleware class for FastAPI that intercepts a request, measures the exact time it takes to process, and logs both the incoming request path and the final execution time.

**Expected Scaffold Answer:**
```python
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Record start time before passing request to the application
        start_time = time.perf_counter()
        logger.info(f"Started {request.method} {request.url.path}")
        
        try:
            # 2. Await the actual endpoint execution
            response = await call_next(request)
            
            # 3. Calculate process time and log success
            process_time = time.perf_counter() - start_time
            logger.info(f"Finished {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.4f}s")
            return response
            
        except Exception as e:
            # 4. Ensure we still log the execution time even if the endpoint crashes
            process_time = time.perf_counter() - start_time
            logger.error(f"Failed {request.method} {request.url.path} - Time: {process_time:.4f}s - Error: {str(e)}")
            raise
```

### Question 2: Implement Graceful Cache Degradation
**Prompt:** Write a Python function `get_user_profile(user_id)` that attempts to fetch a user profile from a Redis cache. If Redis is completely unreachable (e.g., connection timeout), the code MUST NOT crash. Instead, it should query a `db_get_user()` function, attempt to cache the result, and return the data.

**Expected Scaffold Answer:**
```python
import redis
import json

# Setup client with a strict socket timeout so it fails fast
redis_client = redis.Redis(host='localhost', port=6379, socket_timeout=2)

def db_get_user(user_id):
    # Simulates an expensive database call
    return {"id": user_id, "name": "John Doe"}

def get_user_profile(user_id: int):
    cache_key = f"user:profile:{user_id}"
    
    # 1. Attempt to fetch from cache gracefully
    try:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except redis.RedisError as e:
        print(f"Cache read failed, falling back to DB: {e}")
        
    # 2. Cache miss or Redis failure: fetch from DB
    db_data = db_get_user(user_id)
    
    # 3. Attempt to write to cache gracefully
    try:
        # setex sets the key with a 3600-second TTL
        redis_client.setex(cache_key, 3600, json.dumps(db_data))
    except redis.RedisError as e:
        print(f"Cache write failed: {e}")
        
    return db_data
```

### Question 3: Write a Python Caching Decorator
**Prompt:** Write a Python decorator `@simple_cache(ttl=60)` that can be applied to any synchronous function. It should use a global dictionary as an in-memory cache, dynamically generating a cache key based on the function's arguments.

**Expected Scaffold Answer:**
```python
import time
from functools import wraps

# Global in-memory dictionary
_CACHE = {}

def simple_cache(ttl: int = 60):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a deterministic key based on function name and passed arguments
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Check if key exists and hasn't expired
            if key in _CACHE:
                cached_time, cached_value = _CACHE[key]
                if time.time() - cached_time < ttl:
                    return cached_value
                
            # Execute function, cache result, and return
            result = func(*args, **kwargs)
            _CACHE[key] = (time.time(), result)
            return result
        return wrapper
    return decorator

@simple_cache(ttl=120)
def compute_heavy_math(x, y):
    time.sleep(2) # Simulating heavy work
    return x * y
```

### Question 4: Fix an N+1 Query in SQLAlchemy
**Prompt:** You are given two SQLAlchemy models: `Author` and `Book` (One-to-Many). Write a SQLAlchemy 2.0 query that fetches the first 10 authors and all their associated books without triggering the N+1 query problem.

**Expected Scaffold Answer:**
```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

def get_authors_with_books(session):
    # The selectinload option eagerly loads the 'books' relationship in a second 
    # query using an IN clause, emitting exactly 2 queries instead of 11.
    stmt = (
        select(Author)
        .options(selectinload(Author.books))
        .limit(10)
    )
    result = session.execute(stmt)
    return result.scalars().all()
```

### Question 5: Pydantic Cross-Field Validation
**Prompt:** Create a Pydantic V2 model `UserRegistration` with fields `username`, `password`, and `confirm_password`. Write a custom validator that ensures `password` and `confirm_password` match exactly.

**Expected Scaffold Answer:**
```python
from pydantic import BaseModel, model_validator

class UserRegistration(BaseModel):
    username: str
    password: str
    confirm_password: str

    # mode='after' allows us to inspect the fully instantiated model
    @model_validator(mode='after')
    def verify_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match!")
        return self
```
