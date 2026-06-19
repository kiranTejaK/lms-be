# Comprehensive Backend Interview Guide
*(FastAPI, SQLAlchemy, Pydantic, Caching, and SQL)*

This document compiles the most critical interview questions, theoretical answers, and concrete code scaffold examples drawn directly from the project architecture.

---

## 1. FastAPI & Application Architecture

### Question 1: Implement a Request Logging Middleware
**Prompt:** Write a custom ASGI Middleware class for FastAPI that intercepts a request, measures the exact time it takes to process, and logs both the incoming request path and the final execution time.

**Answer & Scaffold:**
Using `structlog` or standard `logging`, a middleware is perfect for universal observability (e.g. for Datadog or ELK).

```python
import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Record start time
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
            # 4. Log failure and re-raise
            process_time = time.perf_counter() - start_time
            logger.error(f"Failed {request.method} {request.url.path} - Time: {process_time:.4f}s - Error: {str(e)}")
            raise
```

### Question 2: Synchronous vs. Asynchronous Endpoints
**Question:** Explain the architectural difference between `def` and `async def` endpoints in FastAPI. Under what circumstances would defining a purely I/O bound endpoint as synchronous (`def`) cause performance degradation?
**Answer:** `async def` endpoints run directly on the main asynchronous event loop. `def` endpoints are executed in a separate background threadpool (managed by Starlette) to prevent blocking the event loop. If you define a purely I/O bound endpoint as `async def` but use a *synchronous* library (like `requests`), it will block the entire main event loop, causing the server to freeze and drop all other concurrent requests.

---

## 2. Pydantic V2 & Data Validation

### Question 3: Cross-Field Validation
**Prompt:** Create a Pydantic V2 model `UserRegistration` with fields `username`, `password`, and `confirm_password`. Write a custom validator that ensures `password` and `confirm_password` match exactly.

**Answer & Scaffold:**
Use `@model_validator(mode='after')`. Running in "after" mode means the validator receives the fully instantiated model, allowing cross-field comparisons.

```python
from pydantic import BaseModel, model_validator

class UserRegistration(BaseModel):
    username: str
    password: str
    confirm_password: str

    @model_validator(mode='after')
    def verify_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match!")
        return self
```

### Question 4: Pydantic V2 Architecture Changes
**Question:** Pydantic V2 introduced a new core written in Rust. How does this affect performance, and what are the API differences?
**Answer:** The Rust core drastically increases validation speed (often 5x-50x faster). Method names were unified and prefixed with `model_` to prevent namespace collisions. For instance, `parse_obj` became `model_validate`, and `dict()` became `model_dump()`.

---

## 3. SQLAlchemy 2.0 & Pure SQL / Stored Procedures

### Question 5: Resolving the N+1 Query Problem
**Prompt:** You are given two SQLAlchemy models: `Author` and `Book` (One-to-Many). Write a SQLAlchemy 2.0 query that fetches the first 10 authors and all their associated books without triggering the N+1 query problem.

**Answer & Scaffold:**
The N+1 problem occurs when you query N parent records, and then emit an additional query for each parent when accessing their children. We solve this by eagerly loading the relationship.

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

def get_authors_with_books(session):
    # selectinload eagerly loads 'books' in a second query using an IN clause
    # emitting exactly 2 queries regardless of how many authors exist.
    stmt = (
        select(Author)
        .options(selectinload(Author.books))
        .limit(10)
    )
    result = session.execute(stmt)
    return result.scalars().all()
```

### Question 6: Stored Procedure Design Pattern
**Question:** Describe a standardized way to return API responses directly from a MySQL stored procedure.
**Answer:** You can design a stored procedure that builds standard response variables (`status_flag`, `status_code`, `secure_data`, `data`). The procedure executes business logic, sets the status code, and finally formats a JSON object representing the exact payload the backend API should return to the client.

**Scaffold Example:**
```sql
DELIMITER $$
CREATE DEFINER=`root`@`localhost` PROCEDURE `xp_user_create`(
    IN p_username VARCHAR(255),
    IN p_i18n VARCHAR(10)
)
BEGIN
    DECLARE v_api_response_status_flag VARCHAR(1);
    DECLARE v_api_response_status_code VARCHAR(25);
    DECLARE v_api_response_data_open JSON DEFAULT NULL;
    
    -- Core Business Logic
    -- e.g. INSERT INTO users (username) VALUES (p_username);
    
    SET v_api_response_status_code := 'SUCCESS_CODE';
    SET v_api_response_status_flag := 'S';
    SET v_api_response_data_open := JSON_OBJECT('username', p_username);
    
    -- Final Output
    SELECT 
        v_api_response_status_flag AS status,
        v_api_response_status_code AS status_code,
        JSON_UNQUOTE(v_api_response_data_open) AS data;
END$$
DELIMITER ;
```

---

## 4. Caching & Resilience

### Question 7: Implement Graceful Cache Degradation
**Prompt:** Write a function `get_user_profile(user_id)` that fetches data from Redis. If Redis is unreachable, the code MUST NOT crash, but rather fall back to the database.

**Answer & Scaffold:**
Wrap cache reads and writes in `try/except redis.RedisError` blocks to ensure high availability.

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

### Question 8: Write an In-Memory Caching Decorator
**Prompt:** Write a Python decorator `@simple_cache(ttl=60)` that can be applied to any synchronous function.

**Answer & Scaffold:**
```python
import time
from functools import wraps

_CACHE = {}

def simple_cache(ttl: int = 60):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            if key in _CACHE:
                cached_time, cached_value = _CACHE[key]
                if time.time() - cached_time < ttl:
                    return cached_value
                
            result = func(*args, **kwargs)
            _CACHE[key] = (time.time(), result)
            return result
        return wrapper
    return decorator
```
