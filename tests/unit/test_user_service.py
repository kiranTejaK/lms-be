from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.schemas.user import UserCreate
from app.services.user_service import UserService


@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def user_service(mock_db):
    return UserService(mock_db)

def test_create_user_success(user_service, mock_db):
    # Setup
    user_in = UserCreate(
        email="test@example.com",
        username="testuser",
        password="password123"
    )

    with patch("app.services.user_service.crud_user") as mock_crud, \
         patch("app.services.user_service.get_password_hash", return_value="hashed"), \
         patch("app.services.user_service.clear_cache"), \
         patch("app.services.user_service.BackgroundTaskManager"):

        mock_crud.get_by_email.return_value = None
        mock_crud.get_by_username.return_value = None

        # Execut
        user = user_service.create_user(user_in)

        # Assert
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.password_hash == "hashed"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

def test_create_user_conflict(user_service, mock_db):
    # Setup
    user_in = UserCreate(
        email="test@example.com",
        username="testuser",
        password="password123"
    )

    with patch("app.services.user_service.crud_user") as mock_crud:
        mock_crud.get_by_email.return_value = MagicMock()

        # Execute & Assert
        with pytest.raises(ConflictException):
            user_service.create_user(user_in)

def test_get_user_profile_new(user_service, mock_db):
    # Setup
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    # Execute
    profile = user_service.get_user_profile(user_id=1)

    # Assert
    assert profile.user_id == 1
    assert profile.full_name == "New User"
    mock_db.add.assert_called_once()

def test_deactivate_user_not_found(user_service, mock_db):
    # Setup
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    # Execute & Assert
    with pytest.raises(NotFoundException):
        user_service.deactivate_user(user_id=999)
