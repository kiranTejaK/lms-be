from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.models.user import User
from app.services.auth_service import AuthService


@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def auth_service(mock_db):
    return AuthService(mock_db)

def test_login_success(auth_service, mock_db):
    # Setup
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.password_hash = "hashed_pw"
    mock_user.is_active = True

    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user

    form_data = MagicMock()
    form_data.username = "test@example.com"
    form_data.password = "password123"

    with patch("app.services.auth_service.verify_password", return_value=True), \
         patch("app.services.auth_service.create_access_token", return_value="access"), \
         patch("app.services.auth_service.create_refresh_token", return_value="refresh"):

        # Execute
        result = auth_service.login(form_data)

        # Assert
        assert result["access_token"] == "access"
        assert result["refresh_token"] == "refresh"
        assert result["token_type"] == "bearer"

def test_login_invalid_credentials(auth_service, mock_db):
    # Setup
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    form_data = MagicMock()
    form_data.username = "wrong@example.com"
    form_data.password = "wrong"

    # Execute & Assert
    with pytest.raises(UnauthorizedException):
        auth_service.login(form_data)

def test_login_inactive_user(auth_service, mock_db):
    # Setup
    mock_user = MagicMock(spec=User)
    mock_user.is_active = False
    mock_user.password_hash = "hashed_pw"

    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user

    form_data = MagicMock()
    form_data.username = "test@example.com"
    form_data.password = "password123"

    with patch("app.services.auth_service.verify_password", return_value=True):
        # Execute & Assert
        with pytest.raises(ForbiddenException):
            auth_service.login(form_data)

def test_refresh_token_success(auth_service, mock_db):
    # Setup
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.is_active = True

    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user

    with patch("app.services.auth_service.verify_token", return_value={"sub": "1"}), \
         patch("app.services.auth_service.create_access_token", return_value="new_access"), \
         patch("app.services.auth_service.create_refresh_token", return_value="new_refresh"):

        # Execute
        result = auth_service.refresh_token("old_refresh")

        # Assert
        assert result["access_token"] == "new_access"
        assert result["refresh_token"] == "new_refresh"
