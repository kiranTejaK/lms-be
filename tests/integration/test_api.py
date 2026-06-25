# ==============================================================================
# INTEGRATION TESTS — Full HTTP endpoint tests via FastAPI TestClient
#
# Mocking: Real DB (SQLite), real Redis, real JWT tokens, real structlog.
# SMTP is configured for MailHog (localhost:1025) in test environments.
# These tests exercise the complete request → service → DB → response flow.
# ==============================================================================

"""
Comprehensive API endpoint tests covering the full authentication flow,
course management, and health check.
"""

import uuid

from app.core.config import settings

PREFIX = f"/{settings.APP_PREFIX}/v1"


# ── Health Check ──────────────────────────────────────────────────────────

def test_health_check(client):
    """INTEGRATION: Health endpoint returns 200 with status and environment."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "environment" in data


# ── Auth Flow ─────────────────────────────────────────────────────────────

def test_register_and_login_flow(client):
    """INTEGRATION: Full registration → login → me flow."""
    unique = str(uuid.uuid4())[:8]
    email = f"flow_{unique}@example.com"
    username = f"flowuser_{unique}"

    # Register
    resp = client.post(
        f"{PREFIX}/auth/register",
        json={"email": email, "username": username, "password": "strongpass123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == email
    assert "id" in data

    # Login
    resp = client.post(
        f"{PREFIX}/auth/login",
        data={"username": email, "password": "strongpass123"},
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"

    # Get current user
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = client.get(f"{PREFIX}/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == email


def test_register_duplicate_email(client, test_user):
    """INTEGRATION: Registration with existing email should fail with 409."""
    resp = client.post(
        f"{PREFIX}/auth/register",
        json={
            "email": test_user.email,
            "username": "newuniquename",
            "password": "pass123",
        },
    )
    assert resp.status_code == 409


def test_login_wrong_password(client, test_user):
    """INTEGRATION: Login with wrong password returns 401."""
    resp = client.post(
        f"{PREFIX}/auth/login",
        data={"username": test_user.email, "password": "wrongpassword"},
    )
    assert resp.status_code == 401


def test_refresh_token_flow(client):
    """INTEGRATION: Token refresh endpoint issues a new access token."""
    unique = str(uuid.uuid4())[:8]
    email = f"refresh_{unique}@example.com"

    # Register + login to get tokens
    client.post(
        f"{PREFIX}/auth/register",
        json={"email": email, "username": f"refresh_{unique}", "password": "pass123"},
    )
    resp = client.post(
        f"{PREFIX}/auth/login",
        data={"username": email, "password": "pass123"},
    )
    tokens = resp.json()

    # Refresh
    resp = client.post(
        f"{PREFIX}/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert "access_token" in new_tokens


def test_change_password(client, auth_headers):
    """INTEGRATION: Authenticated user can change their password."""
    resp = client.post(
        f"{PREFIX}/auth/change-password",
        json={"current_password": "testpassword123", "new_password": "newpassword456"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


def test_change_password_wrong_current(client, auth_headers):
    """INTEGRATION: Change password with wrong current password fails with 422."""
    resp = client.post(
        f"{PREFIX}/auth/change-password",
        json={"current_password": "wrongpassword", "new_password": "newpassword456"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_logout(client):
    """INTEGRATION: Logout always returns success."""
    resp = client.post(f"{PREFIX}/auth/logout")
    assert resp.status_code == 200


# ── Course CRUD ───────────────────────────────────────────────────────────

def test_create_course(client):
    """INTEGRATION: Create a course via POST endpoint."""
    resp = client.post(
        f"{PREFIX}/courses/",
        json={"title": "FastAPI Masterclass", "description": "Learn FastAPI", "max_students": 50},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "FastAPI Masterclass"


def test_get_courses_list(client):
    """INTEGRATION: GET /courses/ returns a list."""
    resp = client.get(f"{PREFIX}/courses/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_single_course(client, test_course):
    """INTEGRATION: GET /courses/{id} returns the correct course."""
    resp = client.get(f"{PREFIX}/courses/{test_course.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == test_course.id


def test_get_course_not_found(client):
    """INTEGRATION: GET /courses/99999 returns 404 for non-existent course."""
    resp = client.get(f"{PREFIX}/courses/99999")
    assert resp.status_code == 404


def test_update_course(client, test_course):
    """INTEGRATION: PUT /courses/{id} updates course fields."""
    resp = client.put(
        f"{PREFIX}/courses/{test_course.id}",
        json={"title": "Updated Title"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


def test_delete_course(client, test_course):
    """INTEGRATION: DELETE /courses/{id} removes the course."""
    resp = client.delete(f"{PREFIX}/courses/{test_course.id}")
    assert resp.status_code == 200


def test_get_course_detailed(client, test_course):
    """INTEGRATION: Detailed view returns category, instructor, and lessons."""
    resp = client.get(f"{PREFIX}/courses/{test_course.id}/detailed")
    assert resp.status_code == 200
    data = resp.json()
    assert "lessons" in data
    assert "category" in data


def test_enroll_in_course(client, test_course, auth_headers):
    """INTEGRATION: Authenticated user can enroll in a course."""
    resp = client.post(
        f"{PREFIX}/courses/{test_course.id}/enroll",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


# ── User Endpoints ────────────────────────────────────────────────────────

def test_list_users(client):
    """INTEGRATION: GET /users/ returns paginated user list."""
    resp = client.get(f"{PREFIX}/users/")
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert "total" in data


def test_get_user_profile(client, test_user):
    """INTEGRATION: GET /users/{id}/profile returns or creates profile."""
    resp = client.get(f"{PREFIX}/users/{test_user.id}/profile")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == test_user.id


def test_update_user_profile(client, test_user, auth_headers):
    """INTEGRATION: PUT /users/{id}/profile updates the user's profile."""
    resp = client.put(
        f"{PREFIX}/users/{test_user.id}/profile",
        json={"full_name": "Updated Name", "bio": "Hello!"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"
