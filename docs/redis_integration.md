# Redis Integration

## Purpose

Redis serves as the **caching layer** for this application, sitting between the API/service layer and the database.  It reduces database load for frequently-accessed, read-heavy data (course listings, user profiles) and enables fast cache invalidation after mutations.

---

## Architecture Overview

```
Client → FastAPI Endpoint → Service Layer → [Redis Cache Check]
                                               ├─ HIT  → Return cached JSON
                                               └─ MISS → Query PostgreSQL
                                                           → Serialise result
                                                           → Store in Redis (with TTL)
                                                           → Return result
```

All caching logic lives in **`app/core/redis.py`**, exposed through:

| Component | Description |
|---|---|
| `redis_client` | Singleton `redis.Redis` instance with connection pooling |
| `redis_cache` decorator | Transparently caches any service method's return value |
| `query_key_generator` | Produces hash-based keys for list/query results |
| `entity_key_generator` | Produces deterministic keys for single-entity lookups |
| `cache_get` / `cache_set` | Low-level wrappers with error handling |
| `clear_cache` | Pattern-based bulk invalidation |

---

## Implementation Details

### Connection

```python
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=int(settings.REDIS_NAME),
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
)
```

Key production features:
- **Socket timeouts** — prevent application hangs if Redis becomes unresponsive
- **`retry_on_timeout=True`** — automatic retry on transient network failures
- **`decode_responses=True`** — returns strings instead of bytes

### Graceful Degradation

All cache operations go through `cache_get()` and `cache_set()` wrappers that catch `redis.RedisError`.  If Redis goes down, the application continues serving from PostgreSQL without any user-facing errors — only a logged warning.

```python
def cache_get(key: str) -> Optional[str]:
    try:
        return redis_client.get(key)
    except redis.RedisError as exc:
        logger.warning("redis_get_failed", key=key, error=str(exc))
        return None
```

### Key Strategy

Two key generators handle different caching scenarios:

**Query keys** (for paginated lists):
```
lms_be:v1:courses:get_courses:query:a1b2c3d4...
```
The hash is derived from the function arguments, ensuring different pagination/filter combos get different cache entries.

**Entity keys** (for single lookups):
```
lms_be:v1:users:profile:42
```
Deterministic and predictable, making targeted invalidation trivial.

### Cache Invalidation

After any mutation (create, update, delete), the relevant service calls `clear_cache()` with a glob pattern:

```python
# After creating a course:
clear_cache("*:courses:get_courses:*")

# After updating a user profile:
clear_cache(entity_key_generator("users", "profile", str(user_id)))
```

---

## Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_NAME` | `0` | Redis database index |
| `APP_PREFIX` | `app` | Key namespace prefix |
| `CACHE_VERSION` | `v1` | Key version segment (bump to invalidate all caches) |

---

## Interaction with Other Systems

- **Service Layer** — services use the `@redis_cache` decorator or call `clear_cache()` directly
- **Database** — Redis reduces repeated SQL queries; writethrough happens on cache misses
- **Testing** — Redis is globally mocked in `conftest.py` (`cache_get` always returns `None`)

---

## Error Handling Strategy

1. **Connection failures** → logged as warning, function returns `None` / skips write
2. **Serialisation failures** → raised (indicates a bug in the calling code)
3. **Key pattern failures** → logged and silently skipped

---

## Production Considerations

- **Memory limits** — set `maxmemory` and `maxmemory-policy allkeys-lru` in `redis.conf`
- **Sentinel / Cluster** — for HA, replace the single `Redis()` client with `Sentinel()` or `RedisCluster()`
- **`KEYS` vs `SCAN`** — `clear_cache` currently uses `KEYS` which blocks Redis; for very high-traffic systems replace with incremental `SCAN`
- **TTL tuning** — default is 3600s (1 hour); adjust per-entity based on change frequency

---

## Example Flow

1. Client sends `GET /lms_be/v1/courses/`
2. `CourseService.get_courses()` is decorated with `@redis_cache`
3. Decorator calls `query_key_generator` → `lms_be:v1:courses:get_courses:query:abc123`
4. `cache_get("lms_be:v1:courses:get_courses:query:abc123")` → `None` (miss)
5. Function executes, queries PostgreSQL, returns `[Course, ...]`
6. Decorator serialises result → `cache_set(key, json_str, 3600)`
7. Next identical request hits the cache → returns JSON directly, skipping the database
