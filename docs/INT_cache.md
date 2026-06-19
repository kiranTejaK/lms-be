# Redis Cache: Strategy & Implementation

## 1. Concept Overview

**What it is:**
Caching is the process of storing frequently accessed data in memory so that future requests for that data can be served much faster. In this project, **Redis** is used as the high-performance, in-memory data store.

**Why it is used:**
By intercepting database queries and serving responses directly from Redis, we drastically reduce database load (especially for expensive JOINs) and improve API response times. The project implements a **Graceful Degradation** pattern: if Redis goes down, the cache layer silently catches the errors, skips caching, and falls back to fetching data from the primary database, ensuring 100% uptime.

---

## 2. Project Setup (Configuration & Core Implementation)

The caching configuration lives in `app/core/config.py`, and the client initialization is located in `app/core/redis.py`.

### Configuration
```python
# app/core/config.py
class Settings(BaseSettings):
    # ...
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_NAME: str = "0"
```

### Redis Client Initialization
The client is initialized with timeouts to prevent hanging the application if the Redis server is unreachable.

```python
# app/core/redis.py
import redis
from app.core.config import settings

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=int(settings.REDIS_NAME) if settings.REDIS_NAME else 0,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)
```

### Key Generation Strategies
To ensure keys are predictable and avoid collisions, two key generators are provided:

```python
def query_key_generator(module: str, func_name: str, *args, **kwargs) -> str:
    """Build a deterministic hash key for paginated / filtered queries."""
    key_dict = {"args": args, "kwargs": kwargs}
    dict_str = json.dumps(key_dict, sort_keys=True, default=str)
    hash_str = hashlib.md5(dict_str.encode()).hexdigest()
    return f"{settings.APP_PREFIX}:{settings.CACHE_VERSION}:{module}:{func_name}:query:{hash_str}"

def entity_key_generator(module: str, entity_name: str, entity_id: str) -> str:
    """Build a predictable cache key for a single entity by ID."""
    return f"{settings.APP_PREFIX}:{settings.CACHE_VERSION}:{module}:{entity_name}:{entity_id}"
```

---

## 3. Key Code Walkthrough

### The `@redis_cache` Decorator
The heart of the caching system is a custom Python decorator. It intercepts function calls, checks Redis for a cached response, and either returns the cached data or executes the function and caches the new result.

```python
# app/core/redis.py
def redis_cache(key_generator_func, expire_seconds: int = 3600, **generator_kwargs):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 1. Build the cache key
            key = build_cache_key(key_generator_func, func, args, kwargs, generator_kwargs)

            # 2. Try cache read
            cached = cache_get(key)
            if cached is not None:
                return json.loads(cached)

            # 3. Cache Miss: Execute function
            result = func(*args, **kwargs)

            # 4. Serialize & cache write
            serialized = serialize_result(result)
            cache_set(key, serialized, expire_seconds)

            return result
        return wrapper
    return decorator
```
*(Note: `cache_get` and `cache_set` contain `try/except redis.RedisError` blocks to ensure graceful degradation).*

### Real Usage: Service Layer Caching
The decorator is applied to service methods. Note how it specifies which key generator to use.

```python
# app/services/course_service.py
from app.core.redis import clear_cache, redis_cache, query_key_generator, entity_key_generator

class CourseService:
    # Caching a paginated query (uses MD5 hash)
    @redis_cache(key_generator_func=query_key_generator, module="courses", expire_seconds=3600)
    def get_courses(self, skip: int = 0, limit: int = 100) -> List[Course]:
        stmt = select(Course).options(selectinload(Course.category), joinedload(Course.instructor)).offset(skip).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    # Caching a single entity (uses deterministic ID-based key)
    @redis_cache(key_generator_func=entity_key_generator, module="courses", entity_name="single")
    def get_course(self, course_id: int) -> Course:
        stmt = select(Course).options(selectinload(Course.lessons)).filter(Course.id == course_id)
        course = self.db.execute(stmt).scalar_one_or_none()
        return course

    # Cache Invalidation on Mutations
    def update_course(self, course_id: int, course_in: CourseUpdate) -> Course:
        # ... logic to update course in DB ...
        self.db.commit()
        
        # Invalidate all course caches
        clear_cache("*:courses:*") 
        return course
```

### Mental Model: How Arguments Map to the Cache Key

To make it stick, let's break down how the decorator transforms function calls into a Redis key for both caching strategies.

#### Example 1: Paginated Query (`get_courses`)
When `course_service.get_courses(skip=0, limit=10)` is called:
- **`key_generator_func`**: `query_key_generator` (passed to `@redis_cache`)
- **`generator_kwargs`**: `{"module": "courses", "expire_seconds": 3600}` (passed to `@redis_cache`)
- **`func`**: The `get_courses` method.
- **`args`**: `(self,)` (the class instance)
- **`kwargs`**: `{"skip": 0, "limit": 10}` (passed to `get_courses`)

#### Example 2: Single Entity (`get_course`)
When `course_service.get_course(course_id=5)` is called:
- **`key_generator_func`**: `entity_key_generator` (passed to `@redis_cache`)
- **`generator_kwargs`**: `{"module": "courses", "entity_name": "single"}` (passed to `@redis_cache`)
- **`func`**: The `get_course` method.
- **`args`**: `(self,)` (the class instance)
- **`kwargs`**: `{"course_id": 5}` (passed to `get_course`)

#### Inside `build_cache_key`

The decorator passes these components into `build_cache_key`, which determines how to construct the final key depending on the strategy used:

```python
def build_cache_key(key_generator_func, func, args, kwargs, generator_kwargs):
    # 1. Extract module (e.g., "courses") from the decorator arguments
    module = generator_kwargs.get("module", "default")

    # 2. Query Strategy: Passes the function name and all query arguments to be hashed
    if key_generator_func == query_key_generator:
        # Example 1: returns query_key_generator("courses", "get_courses", self, skip=0, limit=10)
        return key_generator_func(module, func.__name__, *args, **kwargs)

    # 3. Entity Strategy: Inspect function signature to find the ID robustly
    entity_id = None
    try:
        # Binds *args and **kwargs to actual parameter names (e.g. self, course_id)
        bound_args = inspect.signature(func).bind(*args, **kwargs)
        bound_args.apply_defaults()
        
        # Look for explicit id_param first, then auto-detect names like `id` or `course_id`
        id_param = generator_kwargs.get("id_param")
        if id_param and id_param in bound_args.arguments:
            entity_id = bound_args.arguments[id_param]
        else:
            for name, value in bound_args.arguments.items():
                if name in ("id", "entity_id") or name.endswith("_id"):
                    entity_id = value
                    break
    except Exception:
        pass

    if entity_id is None:
        entity_id = "all"
    
    # Example 2: returns entity_key_generator("courses", "single", "5")
    return key_generator_func(module, generator_kwargs.get("entity_name", "entity"), str(entity_id))
```

This layer of abstraction lets the decorator remain agnostic to *how* keys are generated. It simply delegates the variables to `build_cache_key`. For our `get_course(course_id=5)` example, it falls through to the entity strategy, extracts the entity ID, and outputs a predictable key like `prefix:v1:courses:single:5`.

---

## 4. End-to-End Flow

1. **Request Received:** The user requests `GET /courses?skip=0&limit=10`.
2. **Decorator Interception:** The router calls `course_service.get_courses(skip=0, limit=10)`. The `@redis_cache` decorator intercepts this call.
3. **Key Generation:** The decorator uses `query_key_generator` to create an MD5 hash of `{"skip": 0, "limit": 10}`. 
4. **Cache Lookup:** It calls `redis_client.get(key)`. 
   * **Hit:** If data exists, it deserializes the JSON and returns it immediately. The database is never touched.
   * **Miss/Error:** If no data exists (or Redis is down), it proceeds to step 5.
5. **DB Execution:** The underlying SQLAlchemy query executes.
6. **Cache Write:** The resulting SQLAlchemy models are serialized to JSON. `redis_client.setex(key, 3600, json_data)` is called.
7. **Invalidation:** If an admin later updates a course, `clear_cache("*:courses:*")` is triggered, purging the old data from Redis using wildcard matching.

---

## 5. Design Decisions

1. **Graceful Degradation:** All Redis operations (`cache_get`, `cache_set`, `clear_cache`) are wrapped in `try/except redis.RedisError`. This means Redis is treated as an optional optimization layer; if it crashes, the application survives.
2. **Decorator Pattern:** Using a `@redis_cache` decorator keeps caching logic completely separate from business logic. Services remain clean and solely focused on database operations.
3. **JSON Serialization over Pickle:** Python's `pickle` is vulnerable to arbitrary code execution if the cache is compromised. We use `json.dumps()` explicitly converting Pydantic/SQLAlchemy models.
4. **Two Key Strategies:** 
   * A single entity lookup like `get_course(5)` needs a predictable key (`prefix:v1:courses:single:5`) so we can invalidate it specifically.
   * A query like `get_courses(skip=10, limit=20)` has too many permutations. We MD5 hash the arguments to ensure uniqueness and prevent excessively long Redis keys.

---

## 6. Alternatives & Trade-offs

* **In-Memory Caching (e.g., Python `functools.lru_cache`):**
  * *Alternative:* Caching directly in the Python process memory.
  * *Trade-off:* It avoids the network overhead of Redis. However, in a multi-worker setup (like Gunicorn/Uvicorn), each worker has its own cache. If an admin updates a course, you can't easily invalidate the memory of all other workers. Redis provides a centralized state.
* **FastAPI Response Caching Middleware:**
  * *Alternative:* Caching the final HTTP response at the router/middleware level (like `fastapi-cache`).
  * *Trade-off:* Router caching is simpler, but Service-level caching (what we chose) is more versatile. Service-level caching allows internal background tasks or other services to also benefit from the cached data.
* **SCAN vs KEYS for Cache Clearing:**
  * *Alternative:* Currently, `clear_cache` uses `redis.keys(pattern)`.
  * *Trade-off:* `KEYS` is an O(N) operation that blocks Redis. For a very large dataset, this should be swapped to `SCAN` to prevent blocking the single-threaded Redis event loop.

---

## 7. Interview Questions & Answers

**Q1: How does your application handle a Redis outage?**
*Answer:* We implemented Graceful Degradation. When initializing the Redis client, we set a `socket_connect_timeout=5`. Inside our wrapper functions (`cache_get`, `cache_set`), we catch `redis.RedisError`. If Redis is down, `cache_get` simply returns `None` (acting as a cache miss), and `cache_set` silently skips writing. The application continues to serve traffic directly from the database without throwing 500 errors.

**Q2: How do you handle cache invalidation for paginated queries?**
*Answer:* When an entity is updated or deleted, we use wildcard cache clearing. For example, updating a course triggers `clear_cache("*:courses:*")`, which deletes all specific course caches AND all paginated query caches associated with the "courses" module. This ensures stale lists are never served.

**Q3: Why do you hash the arguments for query caching instead of just concatenating them?**
*Answer:* Concatenating complex arguments (like dictionaries or long strings) can result in incredibly long, unwieldy Redis keys, which wastes memory. By JSON-dumping the arguments (with sorted keys to ensure consistency) and hashing them with MD5, we guarantee a fixed-length, deterministic key regardless of how complex the query parameters are.

---

## 8. Bonus: Common Mistakes & Performance Insights

* **The Thundering Herd Problem:** If a highly trafficked cache key expires, thousands of concurrent requests might simultaneously hit the database before the first one repopulates the cache. A common fix is implementing "cache locking" (allowing only one thread to regenerate the cache while others wait) or adding "jitter" to expiration times.
* **Serialization Nightmares:** Trying to serialize SQLAlchemy objects with detached lazy-loaded relationships. We mitigate this by strictly using eager loading (`selectinload`, `joinedload`) for cached service methods, ensuring the data is fully populated before serialization.
