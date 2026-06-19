# Backend Developer Interview Preparation (3 YOE)
*Tailored for FastAPI, SQLAlchemy 2.0, Pydantic, and Docker Stack*

This document contains 50 deep-level technical interview questions and comprehensive answers divided across 5 core topics, designed to evaluate a candidate with ~3 Years of Experience (YOE) building production-grade backend systems.

---

## Topic 1: FastAPI & Pydantic V2

**1. Synchronous vs. Asynchronous Endpoints**
*Question:* Explain the architectural difference between `def` and `async def` endpoints in FastAPI. Under what circumstances would defining a purely I/O bound endpoint as synchronous (`def`) cause performance degradation?
*Answer:* `async def` endpoints run directly on the main asynchronous event loop. `def` endpoints are executed in a separate background threadpool (managed by Starlette) to prevent blocking the event loop. If you define a purely I/O bound endpoint (like a slow API call) as `async def` but use a *synchronous* library (like `requests`), it will block the entire main event loop, causing the server to freeze and drop all other concurrent requests.

**2. Dependency Injection Lifecycle**
*Question:* How does FastAPI's Dependency Injection system manage the lifecycle of resources (like database connections)? Can you write a dependency that ensures a database session is always closed, even if an exception occurs?
*Answer:* FastAPI dependencies can use the `yield` keyword. Code executed before the `yield` runs before the route handler, and code in a `finally` block after the `yield` runs after the response is delivered, ensuring guaranteed resource cleanup.
*Example:*
```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() # Always executes
```

**3. Pydantic V2 Architecture**
*Question:* Pydantic V2 introduced a new core written in Rust (`pydantic-core`). How does this affect validation performance, and what are the main differences between `BaseModel` in V1 vs V2?
*Answer:* The Rust core drastically increases validation speed (often 5x-50x faster). Method names were unified and prefixed with `model_` to prevent namespace collisions with user data. For instance, `parse_obj` became `model_validate`, and `dict()` became `model_dump()`.

**4. Complex Validation & Field Types**
*Question:* How do you validate a complex, nested JSON payload where certain fields are conditionally required based on the value of another field?
*Answer:* Use the `@model_validator(mode='after')` decorator. It runs after all individual fields are validated and provides access to the fully populated model instance, allowing you to enforce cross-field logic.
*Example:*
```python
from pydantic import BaseModel, model_validator

class PaymentPayload(BaseModel):
    method: str
    card_number: str | None = None

    @model_validator(mode='after')
    def check_card_number(self):
        if self.method == 'credit_card' and not self.card_number:
            raise ValueError('Card number required for credit card')
        return self
```

**5. Global Exception Handling**
*Question:* If a Pydantic validation error occurs, FastAPI automatically returns a 422 response. How would you override this globally to return a custom error structure?
*Answer:* You define an exception handler using `@app.exception_handler(RequestValidationError)`. Inside it, you intercept the exception, extract the error details (`exc.errors()`), format them into your company's standardized JSON API error format, and return a custom `JSONResponse`.

**6. Background Tasks vs. Task Queues**
*Question:* FastAPI provides `BackgroundTasks`. What are the limitations of using this over a dedicated task queue like Celery or RQ?
*Answer:* FastAPI's `BackgroundTasks` run in the same memory space as the web server after the HTTP response is returned. They do not persist across server restarts, lack automatic retries, and can consume valuable web worker memory. A dedicated task queue (Celery) runs in separate worker processes, offering persistence, retries, rate limiting, and horizontal scaling.

**7. Serialization and Lazy Loading**
*Question:* When returning SQLAlchemy models from a FastAPI endpoint, how do you prevent Pydantic from triggering N+1 queries due to lazy-loaded relationships during serialization?
*Answer:* Pydantic touches relationship attributes when converting the ORM model to a dictionary (`model_validate`). If those relationships aren't loaded, SQLAlchemy fires lazy queries synchronously. To prevent this, eagerly load the relationships directly in your SQLAlchemy query using `options(selectinload(Model.relation))`.

**8. Advanced Dependency Overrides**
*Question:* During testing, how do you completely mock or override a deeply nested dependency (like an external API client) that is injected into your endpoint?
*Answer:* You use the application's `dependency_overrides` dictionary. In your test setup: `app.dependency_overrides[get_real_client] = get_mock_client`. This replaces the dependency tree globally for the test client.

**9. Middleware vs. Dependencies**
*Question:* Explain the difference between applying logic via a FastAPI Middleware vs. a global Dependency. Why might you choose a Dependency for request correlation IDs, or conversely, a Middleware?
*Answer:* Middleware wraps *every* single HTTP request and response at the ASGI level (great for CORS, timing, or correlation IDs). Dependencies are explicitly declared in the route signature. For correlation IDs, middleware is better as it applies universally without developer intervention. Dependencies are better for database sessions or current user auth, which aren't needed on every single route.

**10. Context Variables (`contextvars`)**
*Question:* In high-concurrency async applications, how do you safely pass request-specific data (like a correlation ID) deep into service layers without explicitly passing it through every function argument?
*Answer:* Use Python's built-in `contextvars.ContextVar`. Unlike global variables, which leak across concurrent requests in an async environment, `ContextVar` maintains isolated state per async task, ensuring the correlation ID stays strictly mapped to the current HTTP request.

---

## Topic 2: SQLAlchemy 2.0 & Database Design

**1. The N+1 Query Problem**
*Question:* What is the N+1 query problem? Demonstrate how to resolve it in SQLAlchemy 2.0.
*Answer:* The N+1 problem happens when you query a list of N parent objects, and then loop through them, accessing a child relationship that triggers a new database query for each iteration (1 initial + N child queries). Resolve it using eager loading.
*Example:*
```python
from sqlalchemy.orm import selectinload
# selectinload emits exactly 2 queries regardless of N
stmt = select(User).options(selectinload(User.items))
users = db.execute(stmt).scalars().all()
```

**2. 2.0 Style Syntax vs 1.4**
*Question:* SQLAlchemy 2.0 forces a new declarative querying style. What are the key differences between `session.query(Model)` and `session.execute(select(Model))`?
*Answer:* The 2.0 style strictly separates the query construction (`select()`) from execution (`session.execute()`). This aligns perfectly with Python static typing (mypy) and allows the exact same `select()` statement to be executed both synchronously and asynchronously, unlike the legacy `session.query()` which is deprecated.

**3. Pessimistic Locking / Concurrency**
*Question:* How do you prevent race conditions when two concurrent requests try to update the same user balance in PostgreSQL using SQLAlchemy?
*Answer:* You apply a pessimistic row-level lock using `.with_for_update()`. This translates to `SELECT ... FOR UPDATE`, forcing the database to lock the row. Concurrent transactions attempting to read/write that row will wait until the first transaction commits or rolls back.

**4. Migrations and Alembic**
*Question:* You have an Alembic migration that adds a non-nullable column to a table with 10 million rows. How do you write this without causing application downtime?
*Answer:* You cannot add a non-nullable column directly without locking the table heavily. You must do it in phases: 1) Add the column as `nullable=True`. 2) Deploy code that writes to the new column. 3) Run a script to backfill existing rows in small batches. 4) Run a final migration to alter the column to `nullable=False`.

**5. Soft Deletes**
*Question:* Explain how to implement a soft-delete architecture in SQLAlchemy.
*Answer:* Add a `deleted_at` timestamp column to your base model. Instead of `session.delete()`, you update `deleted_at = func.now()`. Because SQLAlchemy lacks a native global scoping mechanism, you must explicitly append `.where(Model.deleted_at.is_(None))` to your select queries, or build custom query classes to handle it automatically.

**6. PostgreSQL Isolation Levels**
*Question:* What is the default transaction isolation level in PostgreSQL? Explain a scenario where you would need `SERIALIZABLE`.
*Answer:* The default is `Read Committed`. You would elevate to `Serializable` for highly sensitive operations (like complex financial transfers or double-booking prevention) where you need mathematical certainty that concurrent transactions will behave exactly as if they were executed one after the other, preventing serialization anomalies.

**7. Database Indexing Strategies**
*Question:* Besides standard B-Tree indexes, when would you use a Partial Index in PostgreSQL?
*Answer:* A Partial Index only indexes rows that meet a `WHERE` condition (e.g., `WHERE is_active = true`). It is highly useful when you frequently query a small active subset of a massive table, saving disk space and speeding up index traversal.

**8. Connection Pooling**
*Question:* In a FastAPI application under high load, you encounter "QueuePool limit overflow" errors. What causes this?
*Answer:* SQLAlchemy maintains a `QueuePool` (e.g., size 5, max overflow 10). If 15 requests are actively holding DB connections, the 16th request will wait in line. If it waits past the `pool_timeout`, it throws an overflow error. It's caused by holding sessions open too long (e.g., doing slow HTTP calls while a DB session is open) or traffic spikes. Fix by increasing pool sizes or using PgBouncer.

**9. Polymorphic Relationships**
*Question:* How do you model polymorphic associations in SQLAlchemy?
*Answer:* The cleanest way is using SQLAlchemy's Native Inheritance (Joined Table Inheritance). You create a base table (e.g., `Entity` with a `type` discriminator column) and subclass models (`UserEntity`, `ProductEntity`). SQLAlchemy automatically joins the base and child tables based on the discriminator.

**10. SQLAlchemy Events**
*Question:* How can you use SQLAlchemy lifecycle events (like `before_insert`) to automatically compute a column value?
*Answer:* You register an event listener using `event.listen`. 
*Example:*
```python
from sqlalchemy import event
def generate_slug(mapper, connection, target):
    target.slug = target.title.lower().replace(" ", "-")

event.listen(Article, 'before_insert', generate_slug)
```

---

## Topic 3: Authentication, Authorization & Security

**1. JWT Anatomy and Storage**
*Question:* Describe the three parts of a JSON Web Token. If the payload is merely base64 encoded, how does the backend trust the token?
*Answer:* A JWT consists of a Header, Payload, and Signature. The backend trusts the payload because the Signature is a cryptographic hash of the Header + Payload generated using a secret key only the server knows. If a user modifies the base64 payload, the signature will be invalidated.

**2. OAuth2 Password Bearer Flow**
*Question:* Explain the OAuth2 Password Bearer flow in FastAPI.
*Answer:* The frontend sends an HTTP POST to a login endpoint containing `username` and `password` as standard `application/x-www-form-urlencoded` form data. FastAPI parses this via `OAuth2PasswordRequestForm`. The backend verifies the credentials and issues an `access_token`. Subsequent requests include `Authorization: Bearer <token>` in the headers.

**3. Role-Based Access Control (RBAC)**
*Question:* Implement a dependency that restricts an endpoint to users with an "admin" role.
*Answer:* First, resolve the current user. Then verify roles.
```python
def require_admin(user: User = Depends(get_current_user)):
    roles = [role.name for role in user.roles]
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Not admin")
    return user
```

**4. Password Hashing**
*Question:* Why is `bcrypt` preferred over SHA-256 for passwords? What role does a "salt" play?
*Answer:* `bcrypt` is designed to be computationally slow, which thwarts brute-force hardware attacks. A salt is random data appended to the password before hashing. This ensures two users with the password "password123" have completely different hashes, completely neutralizing pre-computed Rainbow Table attacks.

**5. Cross-Origin Resource Sharing (CORS)**
*Question:* Explain the CORS preflight (`OPTIONS`) mechanism and how to configure FastAPI to allow it.
*Answer:* Browsers block cross-origin AJAX requests by default. Before sending a complex POST request, the browser sends an `OPTIONS` request to ask the server if the origin is allowed. You resolve this by adding FastAPI's `CORSMiddleware` and explicitly defining `allow_origins`, allowing the server to reply with the correct `Access-Control-Allow-Origin` headers.

**6. Secure Token Refresh Mechanisms**
*Question:* How do you implement a secure Refresh Token flow? Should refresh tokens be stored in the database?
*Answer:* Issue a short-lived Access Token (e.g., 15 min) and a long-lived Refresh Token (e.g., 7 days). Store the hashed Refresh Token in the database or Redis. When the Access Token expires, the client calls a `/refresh` endpoint. The server validates the Refresh Token against the DB, invalidates it (token rotation), and issues a new pair.

**7. Rate Limiting Strategies**
*Question:* How would you implement IP-based rate limiting in FastAPI using Redis?
*Answer:* You can use a Sliding Window or Token Bucket algorithm. Using Redis, you track the user's IP as a key. When a request hits, you increment the value. If the value exceeds the limit (e.g., 100 requests) within the TTL (e.g., 60 seconds), you raise a `429 Too Many Requests` exception. Libraries like `slowapi` abstract this cleanly.

**8. SQL Injection & ORMs**
*Question:* Does using SQLAlchemy completely protect you from SQL injection?
*Answer:* ORMs inherently protect against SQL injection because they use parameterized queries (separating the SQL structure from the user data). However, you can still be vulnerable if you manually concatenate strings into raw SQL execution, e.g., `db.execute(text(f"SELECT * FROM users WHERE name = '{user_input}'"))`.

**9. Secure Secrets Management**
*Question:* How does `pydantic-settings` help in managing environment variables? Where should secrets live in production?
*Answer:* `pydantic-settings` automatically reads `.env` files or system environment variables, validates them, and casts them to Python types. Secrets should *never* be hardcoded or checked into git. In production, they should be securely injected at runtime by an orchestrator like Kubernetes Secrets or AWS Parameter Store.

**10. API Key Rotation**
*Question:* Design a system for issuing and rotating API keys.
*Answer:* Generate a cryptographically secure random string. Hash it using bcrypt/SHA-256 and store *only* the hash in the database. Show the raw key to the user exactly once. When they pass the key in a header, hash it and compare it to the DB. To rotate, generate a new key, store the new hash, and delete/expire the old hash.

---

## Topic 4: System Architecture, Caching & Observability

**1. Advanced Redis Use Cases**
*Question:* Aside from standard string caching, describe a use case where you would utilize Redis Hashes or Sorted Sets.
*Answer:* Redis Hashes (`HSET`) are excellent for storing user sessions or partial object data without constantly serializing/deserializing JSON. Sorted Sets (`ZADD`) natively rank data by a score, making them perfect for real-time leaderboards or time-series rate-limiting windows.

**2. Response Caching**
*Question:* How do you implement an HTTP response cache for a specific FastAPI endpoint?
*Answer:* Compute a unique cache key based on the request URL and query parameters. Before doing DB work, check Redis. If a value exists, return it immediately. If not, fetch the data, store it in Redis with an expiration (`SETEX`), and return it. Also return HTTP `Cache-Control` headers so clients cache it locally.

**3. Structured Logging**
*Question:* Your project uses `structlog`. Why is structured logging superior to unstructured text logging in production?
*Answer:* Unstructured logs (`"User 123 logged in"`) require complex regex parsing to extract data. Structured logging outputs pure JSON (`{"event": "login", "user_id": 123, "level": "info"}`). Aggregators like Datadog or ELK natively index JSON keys, allowing developers to instantly query, filter, and alert on specific fields like `user_id`.

**4. Distributed Tracing**
*Question:* How do you trace the complete lifecycle of a single request across multiple independent microservices?
*Answer:* The API Gateway generates a unique `X-Correlation-ID`. Every service logs this ID in its structured logs and injects it into the HTTP headers of any downstream requests it makes. Distributed tracing tools (like Jaeger or OpenTelemetry) use these IDs to reconstruct the exact path and latency of the request across the network.

**5. Message Brokers & Event-Driven Architecture**
*Question:* How does decoupling logic with a Message Broker (RabbitMQ/Kafka) improve resilience?
*Answer:* Instead of synchronously waiting for an Email API to respond, the backend publishes an "UserCreated" event to the broker and immediately responds to the user. A separate worker consumes the event and sends the email. If the email service crashes, the event remains safely in the queue until the worker restarts, preventing data loss.

**6. Idempotency**
*Question:* What does it mean for an API endpoint to be idempotent?
*Answer:* An idempotent API yields the identical system state no matter how many times it is called. For `POST` requests (like payments), clients send an `Idempotency-Key` header. The server caches the result against this key. If the client experiences a network timeout and retries, the server returns the cached success response instead of processing a duplicate payment.

**7. Monolith vs Microservices**
*Question:* When would you choose a modular monolith over a microservices architecture?
*Answer:* A modular monolith is preferred to avoid distributed system complexity (network failures, distributed transactions, complex CI/CD). Microservices should only be introduced when there is a strict organizational need (teams are stepping on each other's toes) or a technical need (one specific feature requires massive independent horizontal scaling).

**8. WebSockets & Real-time Communication**
*Question:* If you scale your FastAPI WebSocket application to 5 Docker containers, how do you broadcast a message to all connected clients?
*Answer:* WebSocket connections are stateful and pinned to a single container. To broadcast globally, you must use a pub/sub backplane (like Redis Pub/Sub). When container A wants to broadcast, it publishes a message to Redis. Containers B, C, D, and E subscribe to Redis, receive the message, and push it to their local WebSocket clients.

**9. Database Read Replicas**
*Question:* How do you configure SQLAlchemy to utilize a PostgreSQL Read Replica?
*Answer:* You create two SQLAlchemy engines (Primary and Replica). You then implement a custom `Session` class or routing logic that intercepts the SQL statement. If the statement is purely a `select()`, it routes the execution to the Replica engine. If it involves an `insert`, `update`, or `delete`, it routes to the Primary engine.

**10. Circuit Breaker Pattern**
*Question:* Your API relies on a 3rd-party service that occasionally hangs. How do you implement a Circuit Breaker?
*Answer:* A Circuit Breaker monitors external API failures. If failures exceed a threshold (e.g., 5 timeouts in a row), the circuit "opens." Subsequent requests fail fast immediately without actually hitting the external API, preventing your own server's threads from hanging. After a cooldown, it "half-opens" to test if the service has recovered.

---

## Topic 5: Testing (Pytest) & Deployment (Docker)

**1. Mocking External Dependencies**
*Question:* How do you use `unittest.mock` to verify an email function was called without sending real emails during testing?
*Answer:* Use the `patch` decorator to intercept the import path of the email function.
*Example:*
```python
from unittest.mock import patch
def test_user_registration(client):
    with patch("app.services.email.send_email") as mock_send:
        client.post("/register", json={"email": "test@test.com"})
        mock_send.assert_called_once()
```

**2. Pytest Fixtures and Database Rollbacks**
*Question:* How do you configure a Pytest fixture to ensure database test isolation without dropping and recreating tables every time?
*Answer:* Create a session fixture that starts a nested transaction (`SAVEPOINT`). After the test executes (using `yield`), explicitly call `session.rollback()`. This discards all database mutations made during the test instantaneously, keeping the database perfectly clean for the next test.

**3. Integration Testing vs Unit Testing**
*Question:* What strictly defines the boundary between a unit test and an integration test?
*Answer:* A Unit Test tests business logic in pure isolation; it *must never* talk to a real database, Redis, or external network (everything is mocked). An Integration Test validates that your code interacts correctly with real infrastructure, meaning it connects to a test database and real Redis container.

**4. Async Testing in Pytest**
*Question:* How do you test `async def` FastAPI endpoints?
*Answer:* Install `pytest-asyncio` and decorate tests with `@pytest.mark.asyncio`. Instead of the synchronous `TestClient`, use `httpx.AsyncClient` pointing to your FastAPI `app` object to execute requests asynchronously within the test event loop.

**5. Multi-stage Docker Builds**
*Question:* What is a multi-stage Docker build, and why is it useful for Python backends?
*Answer:* A multi-stage Dockerfile uses multiple `FROM` statements. Stage 1 (Builder) installs heavy OS dependencies (like `gcc`) and compiles Python packages into `.whl` files. Stage 2 (Runtime) uses a minimal Python image, copies only the compiled wheels, and runs the app. This drastically reduces the final image size and minimizes security vulnerabilities.

**6. Docker Compose for Local Development**
*Question:* How do you use Docker Compose to create a local development environment with live-reloading?
*Answer:* In `docker-compose.yml`, mount your local source code into the container using `volumes: [".:/app"]`. Override the command to run `uvicorn main:app --reload`. Define backing services (db, redis) in the same compose file so they share an internal Docker network, allowing the app to connect using hostnames like `redis:6379`.

**7. Environment Variable Management in Containers**
*Question:* Why is it an anti-pattern to bake environment variables (like DB passwords) directly into a Docker image at build time?
*Answer:* Baking secrets into the image makes them visible to anyone who has access to the Docker registry (a massive security risk). Furthermore, an image should be environment-agnostic; the exact same image hash should be deployed to Staging and Production, with the environment variables injected at *runtime* via the orchestrator.

**8. Container Healthchecks**
*Question:* How do you configure a Docker `HEALTHCHECK`, and why is it critical for orchestrators like Kubernetes?
*Answer:* Define an HTTP endpoint (e.g., `/health`) that returns 200 OK. In Docker, use `HEALTHCHECK CMD curl -f http://localhost/health || exit 1`. Orchestrators use this to determine if the app is ready to receive traffic. If the healthcheck fails, the orchestrator stops sending traffic and automatically restarts the container.

**9. Zero-Downtime Deployments**
*Question:* Explain how to deploy a database migration without downtime.
*Answer:* Migrations must be completely backward-compatible because the old V1 application and the new V2 application run simultaneously during the deployment window. For example, instead of renaming a column outright, you must: create a new column, deploy code that writes to both, run a backfill, deploy code that reads from the new column, and finally drop the old column.

**10. CI/CD Pipelines**
*Question:* Describe the sequence of a CI/CD pipeline for a Python backend.
*Answer:* Upon pushing code: 1) Run static analysis and linters (`ruff`, `mypy`). 2) Run Unit Tests (fast, isolated). 3) Run Integration Tests (spin up ephemeral DB/Redis containers). 4) Build the Docker image. 5) Push the image to a container registry. Upon a release tag, the orchestrator is triggered to pull the new image and perform a rolling deployment.
