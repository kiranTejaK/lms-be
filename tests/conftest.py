"""
Pytest configuration and fixtures for the test suite.

Uses SQLite for isolated testing.

Mocking strategy:
  - SMTP:    MailHog (local SMTP server on port 1025, UI on 8025)
  - S3:      Moto (in-process mock of AWS services)
  - Redis:   Real Redis server (localhost:6379) — NOT mocked
  - JWT:     Real tokens — NOT mocked
  - Logging: Real structlog — NOT mocked

Provides reusable fixtures for DB sessions, authenticated clients,
and test data (users, courses, categories).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.api.deps import get_db
from app.db.base import BaseModel
from app.core.security import create_access_token, get_password_hash

# ── Test Database (SQLite In-Memory) ──────────────────────────────────────

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Database Lifecycle Fixtures ───────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    """Create all tables at session start, drop at session end."""
    BaseModel.metadata.create_all(bind=engine)
    yield
    BaseModel.metadata.drop_all(bind=engine)


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


# ── NOTE: No Redis mock ──────────────────────────────────────────────────
# Redis uses the real server on localhost:6379.
# JWT tokens use real creation and verification.
# Logging uses real structlog.
# This ensures integration tests exercise the full stack.


# ── Helper Fixtures ───────────────────────────────────────────────────────

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


@pytest.fixture
def test_category(db_session):
    """Create and return a test category."""
    from app.models.course import Category
    import uuid

    cat = Category(name=f"TestCategory_{str(uuid.uuid4())[:8]}")
    db_session.add(cat)
    db_session.commit()
    db_session.refresh(cat)
    return cat


@pytest.fixture
def test_course(db_session, test_category):
    """Create and return a test course with a category."""
    from app.models.course import Course

    course = Course(
        title="Test Course",
        description="A test course",
        category_id=test_category.id,
        max_students=50,
    )
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)
    return course


@pytest.fixture
def test_lesson(db_session, test_course):
    """Create and return a test lesson."""
    from app.models.course import Lesson

    lesson = Lesson(
        title="Test Lesson",
        content="Test content",
        lesson_order=1,
        course_id=test_course.id,
    )
    db_session.add(lesson)
    db_session.commit()
    db_session.refresh(lesson)
    return lesson


@pytest.fixture
def admin_user(db_session):
    """Create an admin user with 'admin' role."""
    from app.models.user import User, Role
    import uuid

    unique = str(uuid.uuid4())[:8]

    # Create admin role if it doesn't exist
    from sqlalchemy import select
    role = db_session.execute(select(Role).filter(Role.name == "admin")).scalar_one_or_none()
    if not role:
        role = Role(name="admin")
        db_session.add(role)
        db_session.flush()

    user = User(
        email=f"admin_{unique}@example.com",
        username=f"admin_{unique}",
        password_hash=get_password_hash("adminpassword123"),
        is_active=True,
    )
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    """Return authorization headers for the admin user."""
    token = create_access_token(data={"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def two_users(db_session):
    """Create two test users for bulk enrollment tests."""
    from app.models.user import User

    users = []
    for i in range(2):
        unique = str(uuid.uuid4())[:8]
        user = User(
            email=f"bulkuser_{i}_{unique}@example.com",
            username=f"bulkuser_{i}_{unique}",
            password_hash=get_password_hash("testpass123"),
            is_active=True,
        )
        db_session.add(user)
        users.append(user)
    db_session.commit()
    for u in users:
        db_session.refresh(u)
    return users


@pytest.fixture
def test_instructor(db_session, test_user):
    """Create an instructor linked to the test user."""
    from app.models.user import Instructor

    instructor = Instructor(
        bio="Expert in Python",
        specialization="Backend Development",
        rating=4.5,
        user_id=test_user.id,
    )
    db_session.add(instructor)
    db_session.commit()
    db_session.refresh(instructor)
    return instructor


@pytest.fixture
def instructor_with_course(db_session, test_instructor, test_category):
    """Create a course assigned to the test instructor."""
    from app.models.course import Course

    course = Course(
        title="Advanced Python",
        description="Deep dive into Python",
        category_id=test_category.id,
        instructor_id=test_instructor.id,
        max_students=100,
    )
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)
    return course


# ── Integration Service Fixtures ──────────────────────────────────────────

@pytest.fixture(scope="session")
def mailhog_client():
    """
    Providing a helper to interact with MailHog's API.
    Used to verify that emails were actually 'sent' to the local SMTP server.
    """
    import httpx

    class MailHogClient:
        BASE_URL = "http://localhost:8025/api/v2"

        def get_messages(self):
            resp = httpx.get(f"{self.BASE_URL}/messages")
            resp.raise_for_status()
            return resp.json()

        def delete_all_messages(self):
            httpx.delete(f"{self.BASE_URL}/messages")

    client = MailHogClient()
    try:
        client.delete_all_messages()  # Start clean
    except Exception:
        pass  # MailHog might not be running
    return client


@pytest.fixture(scope="session")
def s3_integration_client():
    """
    Providing a real boto3 client pointing to our Moto service in Docker.
    """
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
        endpoint_url="http://localhost:5000",
        config=Config(signature_version="s3v4"),
    )

    # Ensure the test bucket exists
    bucket_name = "test-bucket"
    try:
        client.create_bucket(Bucket=bucket_name)
    except Exception:
        pass  # Already exists or other error

    return client
