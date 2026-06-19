"""
User management endpoints: profile, avatar upload, listing, and deactivation.
"""

from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import structlog

from app.api import deps
from app.models.user import User
from app.schemas.user import UserProfileResponse, UserProfileUpdate, UserResponse, UserListResponse
from app.services.user_service import UserService

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/", response_model=UserListResponse)
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    """List all users with pagination. Returns users and total count."""
    svc = UserService(db)
    return svc.get_users(skip=skip, limit=limit)


@router.get("/{user_id}/profile", response_model=UserProfileResponse)
def get_user_profile(user_id: int, db: Session = Depends(deps.get_db)):
    """Get a user's profile (creates a default if none exists)."""
    svc = UserService(db)
    return svc.get_user_profile(user_id=user_id)


@router.put("/{user_id}/profile", response_model=UserProfileResponse)
def update_user_profile(
    user_id: int,
    profile_in: UserProfileUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Update the authenticated user's profile."""
    if current_user.id != user_id:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException("Cannot update another user's profile")
    svc = UserService(db)
    return svc.update_user_profile(user_id, profile_in)


@router.put("/{user_id}/profile/avatar", response_model=UserProfileResponse)
def upload_avatar(
    user_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Upload an avatar image to S3 for the authenticated user."""
    svc = UserService(db)
    return svc.upload_avatar(user_id, file, current_user, background_tasks)


@router.put("/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
    user_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """Deactivate a user account (admin only)."""
    svc = UserService(db)
    return svc.deactivate_user(user_id)
