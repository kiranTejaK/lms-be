# Backend Coding: Advanced Deep Dives & Scaffolds
*(Part 2: Tracing, Concurrency, Pagination, and Testing)*

---

## 1. Deep Dive: Logging Middleware vs. Configuration

One of the most confusing parts of enterprise logging is understanding **where** context is gathered vs. **how** it is formatted. Let's break down the implementation of **Correlation IDs (Request IDs)**.

### The Goal
When a user calls `POST /checkout`, that request might hit the Router, then the Auth Service, then the Payment Service, and finally the DB Layer. You want **every single log** emitted across these layers to automatically contain `"request_id": "abc-123"`. 

### A. What goes in the Middleware? (The "Capture")
The middleware's job is purely to **capture and store** dynamic request data in an isolated, thread-safe way using Python's `contextvars`.

```python
import structlog
from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 1. Generate or extract the ID from incoming headers
        req_id = request.headers.get("X-Correlation-ID", str(uuid4()))
        
        # 2. Bind the ID to the current async task context
        # This stores it in memory, specific ONLY to this HTTP request lifecycle
        structlog.contextvars.bind_contextvars(request_id=req_id)
        
        # 3. Process the request
        try:
            return await call_next(request)
        finally:
            # 4. Clean up the context so memory doesn't leak
            structlog.contextvars.clear_contextvars()
```

### B. What goes in the Setup/Config? (The "Injection")
The configuration (`app/core/logging.py`) defines the global **Processor Chain**. Think of processors as an assembly line that modifies the log dictionary before it gets printed to the console or file.

```python
import structlog

def setup_logging():
    structlog.configure(
        processors=[
            # This processor is the bridge! 
            # It looks at the current async task, grabs the 'request_id' 
            # we saved in the middleware, and injects it into the log dictionary.
            structlog.contextvars.merge_contextvars,
            
            # Other standard processors
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
```

### Why do we need both?
- **If you only have Middleware:** You save the `request_id` in memory, but when you call `logger.info("foo")`, `structlog` doesn't know it should look for it. The ID never prints to the file.
- **If you only have Setup:** The `merge_contextvars` processor runs on every log, but it finds an empty context because no middleware ever intercepted the HTTP request to bind the `request_id`.

---

## 2. Advanced Scaffold Coding Questions

### Question 6: Handling Race Conditions (Pessimistic Locking)
**Prompt:** You are building a digital wallet. Write a SQLAlchemy function that withdraws money from a `Wallet` model. If a user maliciously clicks the "Withdraw" button 5 times at the exact same millisecond, how do you guarantee their balance doesn't drop below zero due to a race condition?

**Deep Level Understanding:** If 5 threads read the balance as $100 simultaneously, they might all subtract $20 and write back $80, meaning the user successfully withdrew $100 but the DB only tracked $20. 

**Expected Scaffold Answer:**
```python
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Wallet

def withdraw_funds(session: Session, wallet_id: int, amount: float):
    # 1. .with_for_update() tells PostgreSQL to lock this specific row.
    # Concurrent requests will pause here and wait in line for the lock to release.
    stmt = select(Wallet).where(Wallet.id == wallet_id).with_for_update()
    
    # Executing the statement acquires the lock
    wallet = session.execute(stmt).scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    # 2. Safely perform business logic (we are guaranteed to have the most recent data)
    if wallet.balance < amount:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    # 3. Mutate and commit
    wallet.balance -= amount
    
    # 4. Committing the transaction saves the data AND releases the row lock,
    # allowing the next concurrent request in line to proceed.
    session.commit()
    return wallet
```

### Question 7: Cursor-based Pagination
**Prompt:** The standard `offset(50000).limit(20)` pagination is causing severe database performance degradation because the DB has to scan and discard 50,000 rows. Write a SQLAlchemy query that implements Cursor-Based Pagination (Keyset Pagination) to fetch the next 20 users.

**Deep Level Understanding:** Cursor pagination remembers the `id` of the last item on the previous page and uses an index to jump directly to the next page. It is lightning fast regardless of table size, but prevents users from jumping directly to "Page 45".

**Expected Scaffold Answer:**
```python
from sqlalchemy import select
from typing import List, Optional

def get_users_cursor(session, limit: int = 20, cursor_id: Optional[int] = None):
    stmt = select(User)
    
    # If a cursor is provided, ONLY look at rows created after that ID
    if cursor_id is not None:
        stmt = stmt.where(User.id > cursor_id)
        
    # Crucial: Must order by the cursor column ascending to ensure predictable results
    stmt = stmt.order_by(User.id.asc()).limit(limit)
    
    users = session.execute(stmt).scalars().all()
    
    # Calculate the next cursor to pass back to the frontend
    next_cursor = users[-1].id if users else None
    
    return {
        "data": users,
        "next_cursor": next_cursor
    }
```

### Question 8: Pytest Mocking and Caching Logic Verification
**Prompt:** Write a Pytest function to test a service method `get_course_details(course_id)` that utilizes Redis. Verify that when the cache is empty (Cache Miss), the function queries the DB and then explicitly attempts to write the result to Redis exactly once.

**Deep Level Understanding:** The interviewer wants to see if you can isolate side effects using `unittest.mock.patch` and verify interactions rather than just asserting the final output.

**Expected Scaffold Answer:**
```python
import pytest
from unittest.mock import patch, MagicMock
from app.services.course_service import get_course_details

# We patch the exact location where redis_client is imported/used in the service
@patch("app.services.course_service.redis_client")
def test_get_course_details_cache_miss_writes_to_cache(mock_redis, db_session):
    # 1. Setup the mock behavior
    # When the service tries to get() from Redis, simulate a Cache Miss (return None)
    mock_redis.get.return_value = None
    
    # 2. Execute the function
    course_id = 42
    result = get_course_details(db_session, course_id)
    
    # 3. Assertions
    # Verify the mock get was called correctly
    mock_redis.get.assert_called_once_with(f"course:details:{course_id}")
    
    # Verify that because it was a miss, it wrote the fetched data back to Redis
    # We use assert_called_once to ensure we aren't spamming the cache unnecessarily
    assert mock_redis.setex.call_count == 1
    
    # Ensure the returned data is valid (assumes the DB fixture has course 42)
    assert result.id == 42
```

### Question 9: Redis Distributed Lock Strategy
**Prompt:** You have a cron job running on 3 different Docker containers that processes pending payments every 5 minutes. How do you ensure that only one container actually processes the payments? Write a context manager using Redis that acquires a lock, processes the payments, and safely releases the lock.

**Deep Level Understanding:** A standard SQLAlchemy row lock (`.with_for_update()`) only works if you are targeting specific rows. If you are protecting a broad system process across completely different servers, you need a distributed lock. The critical components of a Redis lock are:
1.  **NX (Not Exists):** Ensure only the first caller gets the lock.
2.  **EX/PX (Expiration):** Ensure the lock auto-expires if the worker crashes (preventing deadlocks).
3.  **Unique Identifier:** The worker must write its unique ID to the lock. When releasing, it must verify the ID matches so it doesn't accidentally delete another worker's active lock if its own process ran longer than the timeout.

**Expected Scaffold Answer:**
```python
import redis
import time
from uuid import uuid4
from contextlib import contextmanager

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

@contextmanager
def acquire_redis_lock(lock_name: str, lock_timeout_sec: int = 10):
    lock_key = f"lock:{lock_name}"
    # Generate a unique ID for this specific execution
    worker_id = str(uuid4())
    
    # 1. Acquire Lock: 
    # nx=True (Only set if it doesn't exist)
    # ex=lock_timeout_sec (Auto-expire to prevent deadlocks if we crash)
    acquired = redis_client.set(lock_key, worker_id, nx=True, ex=lock_timeout_sec)
    
    if not acquired:
        # We didn't get the lock. Yield False so the caller knows to skip execution.
        yield False
        return
        
    try:
        # We got the lock! Yield True.
        yield True
    finally:
        # 2. Release Lock Safely:
        # We must ONLY delete the lock if the current value matches our worker_id.
        # Otherwise, if our task took 12s, our lock expired at 10s, and Worker B got it,
        # we don't want to accidentally delete Worker B's active lock!
        
        # This requires a Lua script to execute the check-and-delete atomically.
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        redis_client.eval(lua_script, 1, lock_key, worker_id)

# --- Usage Example ---
def process_pending_payments():
    # Attempt to acquire a lock for "payments" that lasts max 30 seconds
    with acquire_redis_lock("process_payments", lock_timeout_sec=30) as locked:
        if not locked:
            print("Another worker is processing payments. Skipping.")
            return
            
        print("Lock acquired! Processing payments...")
        time.sleep(5)  # Simulate work
        print("Payments processed. Lock releasing automatically.")
```

### Question 10: Preventing a "Cache Stampede" (Thundering Herd)
**Prompt:** A highly popular API endpoint (e.g., getting the homepage dashboard) is cached in Redis. When the cache TTL expires, 500 concurrent users hit the endpoint simultaneously. They all get a "Cache Miss" and immediately query the database, overloading and crashing the DB. Use a Redis lock to implement a strategy where only *one* request queries the DB, while the others wait and read the newly cached data.

**Deep Level Understanding:** This specific pattern solves the "Cache Stampede" (or Thundering Herd) problem. We use a concept called **Double-Checked Locking**. When a cache miss happens, a thread tries to acquire a lock. If it succeeds, it fetches from the DB and writes to the cache. If it fails to get the lock, it knows *another thread is already rebuilding the cache*, so it simply sleeps for a few milliseconds and then tries to read from the cache again.

**Expected Scaffold Answer:**
```python
import redis
import time
import json

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

def db_get_popular_data():
    # Simulates an expensive 2-second database query
    time.sleep(2)
    return {"data": "Super important dashboard metrics"}

def get_popular_dashboard(max_retries=10):
    cache_key = "dashboard:metrics"
    lock_key = f"lock:{cache_key}"
    
    # 1. Standard Cache Check
    cached_data = redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    # 2. Cache Miss: Attempt to acquire the rebuilding lock
    for attempt in range(max_retries):
        # NX=True ensures only ONE concurrent request successfully gets this lock
        # EX=5 ensures the lock drops if the DB query crashes
        lock_acquired = redis_client.set(lock_key, "locked", nx=True, ex=5)
        
        if lock_acquired:
            try:
                # 3. Double-checked locking: Just in case the cache was 
                # populated in the millisecond between step 1 and step 2
                cached_data = redis_client.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
                
                # 4. We are the chosen thread! Query the database.
                db_data = db_get_popular_data()
                
                # 5. Populate the cache for everyone else
                redis_client.setex(cache_key, 3600, json.dumps(db_data))
                return db_data
            finally:
                # Release the lock so future rebuilds can happen when TTL expires
                redis_client.delete(lock_key)
                
        else:
            # 6. We didn't get the lock. This means another thread is currently 
            # querying the database. We should wait and then check the cache again.
            time.sleep(0.5) # Sleep for 500ms
            
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
            
            # If still not in cache, loop continues and we wait again
            
    # Fallback if the database is completely hung and we exhausted our retries
    raise Exception("Timeout waiting for cache to rebuild")
```

### Question 11: Generic Cache Stampede Decorator
**Prompt:** Hardcoding the double-checked locking logic into every service function is a violation of DRY (Don't Repeat Yourself). Write a generic Python decorator called `@anti_stampede_cache(ttl=3600)` that can be wrapped around any synchronous database function. It should automatically handle key generation, cache hits, distributed locking for cache misses, and waiting for other threads.

**Deep Level Understanding:** By moving the complex lock-and-wait mechanism into a decorator, your business logic remains incredibly clean. Any function wrapped with this decorator instantly becomes immune to thundering herd attacks. It dynamically creates unique lock keys based on the function's arguments, ensuring that a stampede on `get_user(1)` doesn't accidentally block requests for `get_user(2)`.

**Expected Scaffold Answer:**
```python
import redis
import json
import time
from functools import wraps

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

def anti_stampede_cache(ttl: int = 3600, max_retries: int = 10, sleep_time: float = 0.5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 1. Generate a deterministic cache key based on the function name and arguments
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            lock_key = f"lock:{cache_key}"
            
            # 2. Standard fast-path cache check
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
                
            # 3. Cache Miss: Enter the Anti-Stampede loop
            for _ in range(max_retries):
                # Attempt to get the lock for this specific cache key
                lock_acquired = redis_client.set(lock_key, "locked", nx=True, ex=10)
                
                if lock_acquired:
                    try:
                        # Double-checked locking
                        cached_data = redis_client.get(cache_key)
                        if cached_data:
                            return json.loads(cached_data)
                            
                        # We have the lock! Execute the actual underlying DB function
                        db_result = func(*args, **kwargs)
                        
                        # Save the result to cache and return
                        redis_client.setex(cache_key, ttl, json.dumps(db_result))
                        return db_result
                    finally:
                        # Always release the lock so the key can be rebuilt when TTL expires
                        redis_client.delete(lock_key)
                else:
                    # Someone else has the lock. Sleep and retry reading the cache.
                    time.sleep(sleep_time)
                    cached_data = redis_client.get(cache_key)
                    if cached_data:
                        return json.loads(cached_data)
                        
            raise Exception(f"Timeout waiting for cache rebuild on {func.__name__}")
            
        return wrapper
    return decorator

# --- Usage Example ---
# Now, simply applying this decorator protects ANY database call from a stampede!
@anti_stampede_cache(ttl=600)
def fetch_heavy_analytics(user_id: int):
    # Simulates an expensive 3-second database query
    time.sleep(3)
    return {"user_id": user_id, "report": "generated"}
```
