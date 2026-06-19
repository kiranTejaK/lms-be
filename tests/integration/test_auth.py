# ==============================================================================
# INTEGRATION TESTS — Auth-specific endpoint tests via FastAPI TestClient
#
# Mocking: Real DB (SQLite), real JWT tokens (PyJWT), real structlog.
# No external mocks — tests exercise full auth flow end-to-end.
# ==============================================================================

"""Auth-specific tests: token creation, refresh, and edge cases."""

import uuid

from app.core.config import settings

PREFIX = f"/{settings.APP_PREFIX}/v1"


def test_full_auth_flow(client):
    """INTEGRATION: Register → login → get current user → change password → re-login."""
    unique = str(uuid.uuid4())[:8]
    email = f"authflow_{unique}@example.com"
    password = "securepass123"

    # Register
    resp = client.post(
        f"{PREFIX}/auth/register",
        json={"email": email, "username": f"authflow_{unique}", "password": password},
    )
    assert resp.status_code == 200
    user_id = resp.json()["id"]

    # Login
    resp = client.post(
        f"{PREFIX}/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    # Access /me
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = client.get(f"{PREFIX}/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == user_id

    # Change password
    resp = client.post(
        f"{PREFIX}/auth/change-password",
        json={"current_password": password, "new_password": "newpassword456"},
        headers=headers,
    )
    assert resp.status_code == 200

    # Re-login with new password
    resp = client.post(
        f"{PREFIX}/auth/login",
        data={"username": email, "password": "newpassword456"},
    )
    assert resp.status_code == 200


def test_login_with_invalid_credentials(client):
    """INTEGRATION: Login with non-existent user returns 401."""
    resp = client.post(
        f"{PREFIX}/auth/login",
        data={"username": "nonexistent@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


def test_me_without_token(client):
    """INTEGRATION: Accessing /me without a token returns 401."""
    resp = client.get(f"{PREFIX}/auth/me")
    assert resp.status_code == 401


def test_me_with_invalid_token(client):
    """INTEGRATION: Accessing /me with a garbage token returns 401."""
    resp = client.get(
        f"{PREFIX}/auth/me",
        headers={"Authorization": "Bearer invalidtoken123"},
    )
    assert resp.status_code == 401


def test_refresh_with_invalid_token(client):
    """INTEGRATION: Refresh with invalid token returns 401."""
    resp = client.post(
        f"{PREFIX}/auth/refresh",
        json={"refresh_token": "invalid_refresh_token"},
    )
    assert resp.status_code == 401
