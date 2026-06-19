# Interview Questions & Answers

This file contains interview questions related to **this project's architecture** and **general backend engineering topics** covered by the technologies used.

---

## Part 1 — Project-Based Questions

### Q1: Why was the service layer pattern used?

**A:** The service layer separates business logic from the API routing layer.  This brings three key benefits:
1. **Testability** — services can be unit tested without spinning up an HTTP server
2. **Reusability** — the same service method can be called from different endpoints, background tasks, or admin scripts
3. **Maintainability** — API endpoints stay thin (validate → delegate → respond), while complex logic lives in one place

Without a service layer, endpoints become fat controllers that mix HTTP concerns with business rules, making them hard to test and prone to code duplication.

---

### Q2: Why use Redis caching in this project?

**A:** Redis is used as a read-through cache to reduce database load for frequently-accessed data like course listings.  The key design decisions are:
- **Decorator-based caching** — `@redis_cache` makes caching transparent; no cache logic in the service methods
- **Two key strategies** — `query_key_generator` for paginated results (hash-based), `entity_key_generator` for single lookups (deterministic)
- **Graceful degradation** — if Redis goes down, the app falls back to PostgreSQL without errors
- **Active invalidation** — after mutations (create/update/delete), relevant cache keys are cleared with `clear_cache()`

The tradeoff is eventual consistency: for a brief window after a write, some reads may return stale data.  This is acceptable for a learning platform where course data changes infrequently.

---

### Q3: Why SQLAlchemy ORM instead of raw SQL?

**A:** SQLAlchemy 2.0 provides:
- **Data integrity** — models enforce types, constraints, and relationships at the Python level
- **Query composition** — `select()`, `filter()`, `join()` are composable and database-agnostic
- **Eager loading** — `selectinload()` and `joinedload()` prevent N+1 query problems declaratively
- **Migration support** — Alembic auto-generates migration scripts from model changes
- **Security** — parameterised queries prevent SQL injection by default

Raw SQL would be faster for highly optimised queries, but for 95% of this project's operations, the ORM's expressiveness and safety outweigh the minor performance overhead.

---

### Q4: How are race conditions handled during enrollment?

**A:** `CourseService.enroll_in_course()` uses **row-level locking** (`SELECT ... FOR UPDATE`):

```python
stmt = select(Course).filter(Course.id == course_id).with_for_update()
course = self.db.execute(stmt).scalar_one_or_none()
```

This locks the course row for the duration of the transaction.  If two users try to enroll simultaneously:
1. Request A locks the row → checks count → enrolls → commits → releases lock
2. Request B blocks at `FOR UPDATE` → acquires lock → re-checks count → enrolls or rejects if full

Without `FOR UPDATE`, both requests could read `count = 49` (with `max_students = 50`), both enroll, and the course would have 51 students.

---

### Q5: How are transactions managed?

**A:** SQLAlchemy's `Session` is the unit of work:
- The session is created per-request via `get_db()` (dependency injection)
- All operations within a request share the same session
- `db.commit()` persists changes; `db.rollback()` reverts on error
- The session is closed automatically after the request via the `finally` block in `get_db()`

For enrollment, explicit try/except/rollback is used because the `FOR UPDATE` lock must be released even on business-rule failures (e.g. "course is full").

---

### Q6: How does JWT authentication work in this project?

**A:** Three-step flow:
1. **Login** → server verifies password hash → issues access token (30 min) + refresh token (7 days)
2. **Authenticated requests** → client sends `Authorization: Bearer <access_token>` → server decodes JWT without any DB lookup (stateless)
3. **Token refresh** → when access token expires, client sends refresh token → server issues new pair

Design decisions:
- **`type` claim** — access and refresh tokens have `"type": "access"` / `"type": "refresh"` to prevent cross-use
- **bcrypt** — passwords are hashed with a slow algorithm resistant to brute-force
- **No blacklist** — logout is client-side (discard tokens); server-side blacklisting can be added with Redis

---

### Q7: Why were `selectinload` and `joinedload` used?

**A:** Both are SQLAlchemy **eager loading strategies** to prevent the N+1 query problem:

- **`joinedload(Course.instructor)`** — adds a JOIN in the same query.  Best for single-row relationships (1-to-1, many-to-1) because it doesn't duplicate the parent row
- **`selectinload(Course.lessons)`** — fires a second `SELECT ... WHERE course_id IN (...)` query.  Best for collections (1-to-many) because it avoids cartesian explosion

Without eager loading, accessing `course.lessons` would fire a separate query **per course** (N+1 problem), turning a 2-query operation into potentially 101 queries for a 100-course list.

---

### Q8: How does the centralized exception handling work?

**A:** Custom exceptions inherit from `AppException`:
```python
class NotFoundException(AppException):
    def __init__(self, resource="Resource"):
        super().__init__(detail=f"{resource} not found", status_code=404)
```

Global handlers in `main.py` convert these to JSON responses:
- `AppException` → structured `{"detail": "..."}` with the correct status code
- Unhandled `Exception` → generic `500 Internal server error` (prevents stack traces from leaking to clients)

This means services raise domain exceptions (`raise NotFoundException("Course")`), and the framework handles HTTP translation.

---

### Q9: Why was the project kept synchronous?

**A:** The synchronous architecture was a deliberate choice to:
1. **Reduce complexity** — no need to handle event loops, async context managers, or async-compatible libraries
2. **Simplify debugging** — synchronous stack traces are straightforward; async exceptions are notoriously hard to trace
3. **Leverage caching** — Redis handles the performance concern; database queries are fast with connection pooling
4. **Team familiarity** — sync code is more accessible to developers who aren't experienced with async Python

FastAPI supports sync endpoints natively — they run in a thread pool, so they don't block the event loop.

---

## Part 2 — Backend Technical Questions

### FastAPI

**Q: How does FastAPI handle synchronous endpoints?**
A: FastAPI runs sync endpoints in a thread pool (via `anyio`/`run_in_threadpool`).  Each sync request gets its own OS thread, so blocking I/O (database, Redis) doesn't block other requests.  This is why sync FastAPI can still handle concurrent requests efficiently.

**Q: What is dependency injection in FastAPI?**
A: `Depends()` declares that a parameter should be resolved by calling a function.  FastAPI resolves the dependency graph before calling the endpoint.  This project uses it for `get_db` (database session) and `get_current_user` (auth).

---

### SQLAlchemy

**Q: What changed between SQLAlchemy 1.x and 2.0?**
A: SQLAlchemy 2.0 introduced:
- `select()` instead of `session.query()` — more explicit, composable
- `session.execute(select(...))` returns rows, not model instances — use `.scalars()` to extract objects
- Type annotations via `Mapped[int]` instead of `Column(Integer)`
- Stricter session semantics — explicit `begin()` / `commit()` encouraged

**Q: What is the N+1 problem?**
A: When loading a parent + children (e.g. courses + lessons), lazy loading fires 1 query for the parents and then 1 query **per parent** to load children.  For 100 courses, that's 101 queries.  Eager loading (`selectinload`, `joinedload`) reduces this to 1-2 queries.

---

### Redis

**Q: What caching strategies exist?**
A: Common strategies:
- **Cache-aside** (this project) — app checks cache, falls back to DB, writes to cache on miss
- **Write-through** — every DB write also writes to cache
- **Write-behind** — writes go to cache first, DB is updated asynchronously
- **Read-through** — cache sits in front of DB; cache-layer fetches on miss

Cache-aside is the simplest and most appropriate when data freshness is not critical (seconds-level staleness is acceptable).

**Q: How do you handle cache invalidation?**
A: This project uses **active invalidation** — after any mutation, `clear_cache("*:courses:*")` deletes matching keys.  Combined with TTL (1 hour), this ensures:
- Immediate consistency for writes by the same user
- Eventual consistency for other users (within TTL)

---

### JWT Authentication

**Q: What are the pros and cons of JWT vs session-based auth?**
A:
| | JWT | Sessions |
|---|---|---|
| **Stateless** | ✅ No server-side storage | ❌ Requires session store |
| **Scalable** | ✅ Any server can validate | ❌ Need sticky sessions or shared store |
| **Revocation** | ❌ Hard (need blacklist) | ✅ Delete from store |
| **Size** | ❌ Larger tokens (~500 bytes) | ✅ Small session ID |

JWT is ideal for API-first backends (like this project) where statelessness simplifies horizontal scaling.

---

### Transactions & Race Conditions

**Q: What is `SELECT ... FOR UPDATE`?**
A: It's a PostgreSQL row-level lock.  When a transaction selects a row with `FOR UPDATE`, other transactions that try to select the same row with `FOR UPDATE` will **block** until the first transaction commits or rolls back.  This prevents concurrent modifications to the same data.

**Q: What is optimistic vs pessimistic locking?**
A:
- **Pessimistic** (this project) — lock the row before reading (`FOR UPDATE`).  Guarantees no conflicts but reduces concurrency.
- **Optimistic** — read without locking, check a version column before writing.  Better concurrency but requires retry logic on conflicts.

---

### Docker

**Q: Why use multi-stage Docker builds?**
A: Multi-stage builds separate the build environment from the runtime environment:
- **Builder stage** — installs gcc, compiles C extensions (bcrypt, psycopg), installs Python packages
- **Runtime stage** — copies only the installed packages, not the compiler.  Results in a smaller, more secure image.

**Q: What is a Docker health check?**
A: A `HEALTHCHECK` instruction tells Docker how to test if the container is working.  Orchestrators (Kubernetes, ECS) use this to restart unhealthy containers.  This project checks `GET /health` every 30 seconds.

---

### CI/CD

**Q: What does the CI pipeline in this project do?**
A: Three stages:
1. **Lint** — `ruff check` catches style issues and common bugs
2. **Test** — `pytest` runs 58 tests with coverage reporting
3. **Docker Build** — builds the production image (only on `main` branch)

The pipeline runs on every push and PR, ensuring code quality gates are enforced before merge.
