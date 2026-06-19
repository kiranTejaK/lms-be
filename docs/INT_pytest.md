# Pytest: Testing Strategy & Implementation

## 1. Concept Overview

**What it is:**
Pytest is a mature, full-featured Python testing framework that makes it easy to write small, readable tests, and can scale to support complex functional testing for applications and libraries.

**Why it is used:**
In this project, Pytest is used to ensure code quality and prevent regressions across the FastAPI backend. It provides a robust architecture for dependency injection through "fixtures", enabling the seamless mocking of services (like the database and third-party APIs) and the creation of isolated test environments. The project categorizes tests into **Unit Tests** (isolated component logic) and **Integration Tests** (end-to-end API flows with a real, localized database).

---

## 2. Project Setup (Configuration & Fixtures)

The test configuration is located in `pyproject.toml` and `tests/conftest.py`. The project uses an in-memory SQLite database to make integration tests incredibly fast and isolated.

### `pyproject.toml` Configuration
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
markers = [
    "integration: marks tests as integration tests (requires Docker services)",
]
```

### `tests/conftest.py` Database Isolation
FastAPI's `get_db` dependency is overridden to inject an isolated, per-test database session using an in-memory SQLite database. Each test runs in a transaction that is rolled back afterward.

```python
# conftest.py
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """Provide a clean, transaction-rolled-back session for each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden DB dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

### `tests/conftest.py` Data Factory Fixtures
To avoid boilerplate, fixtures are used to pre-populate required entities like users, authentication headers, and domain models.

```python
@pytest.fixture
def test_user(db_session):
    """Create and return a test user in the database."""
    from app.models.user import User
    import uuid

    unique = str(uuid.uuid4())[:8]
    user = User(
        email=f"testuser_{unique}@example.com",
        username=f"testuser_{unique}",
        password_hash=get_password_hash("testpassword123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def auth_headers(test_user):
    """Return authorization headers for the test user."""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}
```

---

## 3. Key Code Walkthrough

### Unit Testing: Service Layer Isolation
In `tests/unit/test_user_service.py`, dependencies like the database and underlying CRUD functions are aggressively mocked. This verifies the business logic (e.g., conflict handling, password hashing) without any I/O overhead.

```python
# tests/unit/test_user_service.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.user_service import UserService
from app.schemas.user import UserCreate
from app.core.exceptions import ConflictException

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def user_service(mock_db):
    return UserService(mock_db)

def test_create_user_conflict(user_service, mock_db):
    # Setup
    user_in = UserCreate(
        email="test@example.com",
        username="testuser",
        password="password123"
    )
    
    # Mocking the CRUD layer to simulate an existing user
    with patch("app.services.user_service.crud_user") as mock_crud:
        mock_crud.get_by_email.return_value = MagicMock()
        
        # Execute & Assert
        with pytest.raises(ConflictException):
            user_service.create_user(user_in)
```

### Integration Testing: End-to-End API Workflows
In `tests/integration/test_auth.py`, no internal mocks are used. The application uses the real database (SQLite mock), actual JWT creation, and realistic HTTP traffic via the `TestClient`.

```python
# tests/integration/test_auth.py
def test_full_auth_flow(client):
    """INTEGRATION: Register → login → get current user → change password → re-login."""
    unique = str(uuid.uuid4())[:8]
    email = f"authflow_{unique}@example.com"
    password = "securepass123"

    # Register
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": f"authflow_{unique}", "password": password},
    )
    assert resp.status_code == 200

    # Login
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200
    tokens = resp.json()

    # Access Protected Route
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
```

---

## 4. End-to-End Flow

1. **Test Discovery:** Pytest scans the `tests/` directory for files matching `test_*.py` as configured in `pyproject.toml`.
2. **Session Initialization:** Pytest triggers the `@pytest.fixture(scope="session", autouse=True)` in `conftest.py` which builds the SQLite database tables. 
3. **Per-Test Setup:** Before a test executes, the `db_session` fixture creates a new transaction. If the test needs the API client, `client` overrides `get_db` on the FastAPI app. If the test requests `test_user`, the user is created in the DB.
4. **Execution:** The test function runs. Assertions validate the expected responses, exception types, or database states.
5. **Teardown:** Once complete, the `db_session` fixture yields back control, rolls back the transaction (discarding any state changes), and closes connections.

---

## 5. Design Decisions

1. **Transaction-Level Rollbacks for Isolation:**
   Instead of dropping and creating tables for every test (which is incredibly slow), a single connection and transaction are spun up per test, then simply rolled back. This makes hundreds of DB-dependent tests execute in seconds.
2. **Strict Separation of Unit and Integration Tests:**
   The project structure explicitly separates `tests/unit` and `tests/integration`. Unit tests validate complex logic via mocks, while Integration tests use the database to validate correct system wiring.
3. **Docker Mocks for External Infrastructure:**
   Using tools like `MailHog` (for SMTP) and `Moto` (for S3), integration tests can interact with external dependencies over HTTP without needing real external credentials. Redis and structlog are explicitly left unmocked to validate true behavior.

---

## 6. Alternatives & Trade-offs

* **PostgreSQL in Docker vs. In-Memory SQLite:**
  * *Alternative:* Spinning up a real Postgres Testcontainer via Docker for every run.
  * *Trade-off:* While using SQLite locally is lightning fast, it limits testing of Postgres-specific features (like JSONB fields or full-text search) and can occasionally create "works in test, fails in prod" bugs due to dialect differences.
* **`unittest` Standard Library vs. Pytest:**
  * *Alternative:* Using Python's built-in `unittest` class-based structures.
  * *Trade-off:* `pytest` requires less boilerplate, allows functional composition via fixtures, and features rich output tracebacks. `unittest` avoids a 3rd party dependency but is heavier to write.
* **End-to-End browser testing:**
  * *Alternative:* Using Playwright/Selenium for E2E tests.
  * *Trade-off:* Slower and flaky. We currently rely exclusively on the `TestClient` API tests.

---

## 7. Interview Questions & Answers

**Q1: How do you ensure test isolation when multiple tests share the same database?**
*Answer:* We use a `db_session` fixture scoped to the function level. This fixture opens a database connection, begins a transaction, and yields the session to the test. After the test runs, the transaction is unconditionally rolled back. This ensures any records created during the test never persist to affect subsequent tests.

**Q2: How do you handle mocking external services like S3 or Emails in your tests?**
*Answer:* We use mock servers spun up locally (often via Docker-Compose for integration tests). For example, `MailHog` catches all SMTP requests locally, and we use a `mailhog_client` fixture to assert emails were sent. For S3, we use a tool like `Moto` as a standalone server, allowing standard `boto3` API calls to hit our local mock instead of AWS.

**Q3: Explain FastAPI's `dependency_overrides` and why it's critical for your tests.**
*Answer:* FastAPI injects dependencies (like a database session or external client) into route handlers. During testing, we want to inject a specialized testing version of that dependency—like our transaction-wrapped SQLite session. Using `app.dependency_overrides[get_db] = override_get_db`, we swap out the real dependency for our test fixture temporarily.

**Q4: When would you write a Unit test using `patch/MagicMock` versus an Integration test using `TestClient`?**
*Answer:* I use Unit tests when testing complex, isolated business logic (e.g. state machines, data transformations, conflict handling). Mocks are perfect here because they eliminate I/O overhead. I use Integration tests with `TestClient` to test the "wiring" of the application: ensuring the routing works, middlewares execute, database constraints trigger properly, and that Pydantic properly serializes the response.

---

## 8. Bonus: Common Mistakes & Insights

* **Leaking State between Tests:** A common mistake is failing to close a transaction or accidentally committing the overarching test transaction in your app code (e.g. `session.commit()` inside the app, which might break the outer transaction wrapper). Modern SQLAlchemy approaches or savepoints (`session.begin_nested()`) are used to manage this.
* **Over-Mocking:** Mocking everything in unit tests can lead to brittle tests that pass even when the system is fundamentally broken. E.g., changing a model column but the mock returns a dictionary containing the old column.
* **Slow Test Suites:** Not utilizing `--tb=short` or `-n auto` (pytest-xdist) for parallelization. SQLite transaction-based tests are inherently fast and usually solve DB bottleneck problems organically.
