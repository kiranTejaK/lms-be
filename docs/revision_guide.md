# Project Revision Guide: Realistic ETR (Quick Learner)

This guide provides a balanced revision plan for the **15 core endpoints**, tailored for a quick learner who understands the concepts but needs to verify the implementation details.

## 🚀 Part 1: Core Endpoints (Realistic ETR for Quick Learner)

### 🔴 Phase 3: Advanced Optimization & Concurrency (40m each)
*Focus: Tracing edge cases, row-locking scope, and transaction boundaries.*

| Endpoint | Location (API File) | Topic | ETR | Key Focus Area |
| :--- | :--- | :--- | :--- | :--- |
| `POST /transfer` | `advanced_apis.py` | **Deadlock Avoidance** | **40m** | Order of row locking to prevent deadlocks. |
| `POST /concurrent-enroll`| `advanced_apis.py` | **Row Locking** | **40m** | `FOR UPDATE` concurrency safety. |
| `GET /instructor-dash` | `advanced_apis.py` | **Eager Loading** | **40m** | Deep collection loading (N+1 prevention). |
| `GET /analytics` | `advanced_apis.py` | **SQL Aggregation** | **40m** | `func` and `case` for system metrics. |
| `POST /bulk-create` | `advanced_apis.py` | **Atomic Transactions**| **40m** | Batch insert with all-or-nothing rollback. |

### 🟡 Phase 2: Integration & Asynchronous logic (25m each)
*Focus: Understanding the "wiring" of external services (S3, SMTP, Redis).*

| Endpoint | Location (API File) | Topic | ETR | Key Focus Area |
| :--- | :--- | :--- | :--- | :--- |
| `PUT /profile/avatar` | `users.py` | **AWS S3 & Async** | **25m** | `S3Service` + `BackgroundTasks`. |
| `POST /courses/{id}/enroll`| `courses.py` | **Trans. & M:N Rel** | **25m** | M:N mapping and transaction boundaries. |
| `POST /auth/password` | `auth.py` | **Security & Async** | **25m** | Password hashing + Background emails. |
| `DELETE /courses/{id}` | `courses.py` | **Cascade & Cache Clear**| **25m** | Cascade rules and Redis wildcard purge. |
| `GET /users/{id}/profile` | `users.py` | **Redis Caching** | **20m** | Cache decorators and key generation. |

### 🟢 Phase 1: Fundamentals & Basic Relationship (15m each)
*Focus: Standardizing service patterns and DTO structures.*

| Endpoint | Location (API File) | Topic | ETR | Key Focus Area |
| :--- | :--- | :--- | :--- | :--- |
| `POST /auth/register` | `auth.py` | **CRUD & Service** | **15m** | Service-layer pattern basics. |
| `GET /courses/` | `courses.py` | **Pagination** | **15m** | Limit/Offset and DTO responses. |
| `POST /bulk-update` | `courses.py` | **Bulk SQL Update** | **15m** | App-level vs DB-level updates. |
| `GET /courses/{id}/detailed`| `courses.py` | **Load Strategies** | **15m** | `selectinload` vs `joinedload` rules. |
| `POST /auth/login` | `auth.py` | **JWT & Validation** | **10m** | Token structure and Pydantic rules. |

---

## 🧪 Part 2: Pytest Revision Points (Speed Run: 60m)

| Topic | Focus Area | Revise File |
| :--- | :--- | :--- |
| **Fixtures** | `db` (Session), `client` (TestClient), `current_user` (Auto-auth). | `tests/conftest.py` |
| **Mocking I/O** | Using `unittest.mock` to bypass S3 and SMTP calls. | `tests/test_services.py` |
| **Validation** | Testing 400/401/403/404 errors (Negative Testing). | `tests/test_auth.py` |
| **Parametrization**| Using `@pytest.mark.parametrize` for data-driven tests. | `tests/test_users.py` |
| **Lifecycle** | `BackgroundTasks` handling - testing that sync logic completes correctly. | `tests/test_task_manager.py` |
| **Integration** | Running functional flows against a real SQLite database. | `tests/test_courses.py` |

### Key Questions to Ask Yourself During Revision:
- **Why use `with_for_update()`?** (To prevent race conditions on shared resources like course seats).
- **Why `BackgroundTasks` instead of `async def`?** (To offload I/O-bound tasks to a thread pool without complicating the DB driver/session management).
- **How to invalidate Redis selectively?** (Using the custom `clear_cache` helper with specific entity keys or wildcards).
- **How are migrations handled?** (Check `alembic/versions/` for schema evolution details).

---

## 🎤 Part 3: Technical Interview Preparation (100 Questions Context)

These are the "high-impact" questions an interviewer might ask about this specific architecture.

### 1. Concurrency & Database Operations
- **"How does the system handle race conditions during enrollment?"**
  - *Answer:* Using `with_for_update()` to apply a row-level pessimistic lock on the course row before checking seat availability and committing.
- **"Explain your deadlock avoidance strategy in enrollment transfers."**
  - *Answer:* Always acquiring locks on course rows in **ascending order of their IDs** to ensure a consistent locking sequence across concurrent threads.
- **"When do you choose `selectinload` over `joinedload`?"**
  - *Answer:* `joinedload` is for 1:1 or N:1 (scalar) relations (adds a JOIN), while `selectinload` is better for 1:M or M:N (collections) to avoid duplicate rows and the cartesian product problem.

### 2. Performance & Caching
- **"Describe your Redis caching and invalidation strategy."**
  - *Answer:* Using a decentralized approach with custom decorators. Invalidation is triggered after mutations (PUT/POST/DELETE) using prefix-based wildcard clearing (`*:courses:*`) to ensure cache consistency.
- **"How do you measure and prevent N+1 query problems in your dashboard?"**
  - *Answer:* By using SQLAlchemy's eager loading options to fetch related instructor and student data in exactly 3–4 optimized queries instead of N+1 (one per row).

### 3. Architecture & Infrastructure
- **"Why did you use FastAPI's `BackgroundTasks` instead of a dedicated worker like Celery?"**
  - *Answer:* For this scale, `BackgroundTasks` provides a lightweight, non-blocking way to offload I/O (S3, SMTP) without the overhead of a message broker (RabbitMQ/Redis) and separate worker processes.
- **"How is the system resilient to email or S3 delivery failures?"**
  - *Answer:* The `BackgroundTaskManager` implements a synchronous retry loop with **exponential backoff**. If all retries fail, the details are persisted in the `FailedTask` table for manual intervention.

### 4. Authentication & Security
- **"Explain the JWT token rotation and security in this project."**
  - *Answer:* The system uses dual tokens (Access + Refresh). Password hashing is done via `bcrypt`, and the `get_current_user` dependency ensures that all sensitive routes are protected by a valid JWT payload.

### 5. API Design & Testing
- **"How do you mock external services like AWS S3 or SMTP in your test suite?"**
  - *Answer:* Using `unittest.mock.patch` to intercept the service calls during tests, allowing us to verify "emails sent" or "files uploaded" counts without actually hitting the network.
- **"Explain the Service Layer pattern in your codebase."**
  - *Answer:* Business logic, database commits, and cache management are isolated in dedicated `Service` classes. This keeps API endpoints thin and makes the core logic easily testable without a full HTTP request.

---

## 🏗️ Part 4: Technical Deep-Dive (Advanced Concept Questions)

These questions cover the underlying infrastructure and framework-specific patterns.

### 6. SQLAlchemy: Sessions & Lifecycle
- **"What is the lifecycle of a `Session` in this project?"**
  - *Answer:* The session is created per request via the `get_db` dependency. It is injected into services, then automatically closed after the request is finished by FastAPI's dependency system.
- **"Why do we use Connection Pooling (SQLAlchemy)?"**
  - *Answer:* It maintains a set of database connections (usually 5–20) that are reused across requests, significantly reducing the overhead of establishing a new TCP connection for every API call.
- **"Explain the role of `Alembic` in your development workflow."**
  - *Answer:* Alembic tracks schema changes via version scripts (migrations). It allows us to evolve the database schema (adding tables/columns) in a version-controlled, repeatable way across different environments.

### 7. FastAPI: DI, Pydantic & Middleware
- **"What's the benefit of using `Depends()` for database and auth?"**
  - *Answer:* It promotes **loose coupling** and **testability**. We can easily swap the real database for a mock/SQLite-in-memory during testing by overriding the dependency.
- **"Why use Pydantic `BaseModel` and `model_dump()` instead of raw dictionaries?"**
  - *Answer:* Pydantic provides runtime data validation, automatic serialization/deserialization, and generates the OpenAPI (Swagger) schema automatically.
- **"Where would you implement a custom Middleware in this stack?"**
  - *Answer:* For cross-cutting concerns like adding a `X-Process-Time` header, global error handling to JSON, or tracking request/response sizes for monitoring.

### 8. Redis, JWT & Logging
- **"How does the custom Redis `query_key_generator` work?"**
  - *Answer:* It hashes the function name and argument values into a unique string to ensure that the same query parameters always return the same cached result.
- **"Why choose `json-structlog` for application logs?"**
  - *Answer:* It outputs logs in a structured JSON format, making them easily searchable and indexable by log aggregators (like ELK or CloudWatch) compared to flat-text logs.
- **"What happens if a JWT is leaked? How does the Refresh/Access token split help?"**
  - *Answer:* Access tokens have a short TTL (e.g., 30m) to minimize the damage window. Refresh tokens are long-lived and can be revoked on the server (via a blacklist/Redis) to stop further access.

### 9. Advanced ORM & Optimization
- **"How do you handle 'Too many connections' errors in production?"**
  - *Answer:* By tuning SQLAlchemy's `pool_size` and `max_overflow`, and ensuring every session is properly closed via a `try...finally` block (or `contextlib`).
- **"Explain 'Atomic Operations' in the context of your `concurrent_enroll`."**
  - *Answer:* All database changes (decrementing seats + creating enrollment row) happen within one transaction. If any part fails, the database remains in the original state—no partial enrollments.

---

> [!IMPORTANT]
> **Revision Checklist**: Reviewing these 20+ questions alongside the **15 core endpoints** covers ~95% of typical Senior Backend Interview technical topics.
