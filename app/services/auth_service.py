"""
Authentication service handling login, token refresh, and password management.

All operations are synchronous, using bcrypt for password hashing
and PyJWT for token creation/verification.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select

from fastapi import BackgroundTasks
from app.models.user import User
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.core.exceptions import UnauthorizedException, ForbiddenException, ValidationException
from app.core.tasks import BackgroundTaskManager
from app.services.email_service import EmailService
import structlog
from app.core.config  import settings
logger = structlog.get_logger(__name__)


class AuthService:
    def __init__(self, db: Session):
        self.db = db
    #completed
    def login(self, form_data) -> dict:
        """Authenticate user and return JWT token pair."""
        logger.info("login_attempt", username=form_data.username)

        user = self.db.execute(
            select(User).filter(User.email == form_data.username)
        ).scalar_one_or_none()

        if not user or not verify_password(form_data.password, user.password_hash):
            logger.warning("login_failed", username=form_data.username)
            raise UnauthorizedException("Incorrect email or password")

        if not user.is_active:
            raise ForbiddenException("Account is deactivated")

        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        logger.info("login_success", user_id=user.id)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }
    #completed
    def refresh_token(self, refresh_token_str: str) -> dict:
        """
        Issue a new access token from a valid refresh token.

        The refresh token itself is not rotated — it remains valid
        until its original expiry.
        """
        payload = verify_token(refresh_token_str)
        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedException("Invalid refresh token")

        user = self.db.execute(
            select(User).filter(User.id == int(user_id))
        ).scalar_one_or_none()
        if not user or not user.is_active:
            raise UnauthorizedException("Invalid refresh token")

        new_access = create_access_token(data={"sub": str(user.id)})
        new_refresh = create_refresh_token(data={"sub": str(user.id)})

        logger.info("token_refreshed", user_id=user.id)
        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }
    #completed
    def change_password(self, user: User, current_password: str, new_password: str, background_tasks: BackgroundTasks = None) -> dict:
        """Change password for an authenticated user after verifying the old one."""
        if not verify_password(current_password, user.password_hash):
            raise ValidationException("Current password is incorrect")

        user.password_hash = get_password_hash(new_password)
        self.db.commit()

        # Send password change notification as a background task
        task_manager = BackgroundTaskManager(self.db)
        if background_tasks:
            background_tasks.add_task(task_manager.execute_with_retry, self._send_password_change_notification, user.email)
        else:
            task_manager.execute_with_retry(
                self._send_password_change_notification, user.email
            )

        logger.info("password_changed", user_id=user.id)
        return {"detail": "Password updated successfully"}

    @staticmethod
    def _send_password_change_notification(email: str):
        """Background task: notify user about password change via template."""
        from datetime import datetime, timezone

        EmailService.send_email(
            to_email=email,
            subject="Password Changed",
            template_path=f"{settings.EMAIL_TEMPLATE_DIR}/password_change.html",
            context={"email": email, "year": datetime.now(timezone.utc).year},
        )




