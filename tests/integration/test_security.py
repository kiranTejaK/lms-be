# ==============================================================================
# UNIT TESTS — Pure function tests, no database or external dependencies
#
# Mocking: None (tests pure functions directly)
# These test the core security module: password hashing (bcrypt) and
# JWT token creation / verification (PyJWT).
# ==============================================================================

import pytest
from datetime import timedelta
from app.core import security


def test_password_hashing():
    """UNIT: bcrypt hash is non-reversible and verifiable."""
    password = "testpassword"
    hashed = security.get_password_hash(password)
    assert hashed != password
    assert security.verify_password(password, hashed)
    assert not security.verify_password("wrongpassword", hashed)


def test_jwt_tokens():
    """UNIT: access and refresh tokens encode the subject claim correctly."""
    user_id = "1"
    access_token = security.create_access_token(data={"sub": user_id})
    refresh_token = security.create_refresh_token(data={"sub": user_id})

    # Decode and verify
    access_payload = security.verify_token(access_token)
    assert access_payload["sub"] == user_id

    refresh_payload = security.verify_token(refresh_token)
    assert refresh_payload["sub"] == user_id


def test_invalid_token():
    """UNIT: malformed tokens return an empty dict."""
    assert security.verify_token("invalid_token") == {}


def test_token_expiration():
    """UNIT: expired tokens are rejected and return an empty dict."""
    user_id = "1"
    token = security.create_access_token(data={"sub": user_id}, expires_delta=timedelta(minutes=-1))
    assert security.verify_token(token) == {}
