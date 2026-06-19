"""
User service handling user CRUD, profile management, and avatar uploads.

All operations are synchronous. Avatar uploads use the S3 service; cache
invalidation is performed after mutations.
"""

from datetime import datetime, timezone

import structlog
from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.redis import clear_cache, entity_key_generator, query_key_generator, redis_cache
from app.core.security import get_password_hash
from app.core.tasks import BackgroundTaskManager
from app.crud.crud_user import crud_user
from app.models.user import User, UserProfile
from app.schemas.user import UserCreate, UserProfileUpdate
from app.services.email_service import EmailService
from app.services.s3_service import S3Service

logger = structlog.get_logger(__name__)


class UserService:
    def __init__(self, db: Session):
        self.db = db
    #completed
    def create_user(self, user_in: UserCreate, background_tasks: BackgroundTasks = None) -> User:
        """Register a new user with hashed password."""
        logger.info("creating_user", email=user_in.email)

        existing = crud_user.get_by_email(self.db, email=user_in.email)
        if existing:
            raise ConflictException("Email already registered")

        # Also check username uniqueness
        existing_username = crud_user.get_by_username(self.db, username=user_in.username)
        if existing_username:
            raise ConflictException("Username already taken")

        user = User(
            email=user_in.email,
            username=user_in.username,
            password_hash=get_password_hash(user_in.password),
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        clear_cache("*:users:*")
        logger.info("user_created", user_id=user.id)

        # Send welcome email as a background task with retry
        task_manager = BackgroundTaskManager(self.db)
        if background_tasks:
            background_tasks.add_task(task_manager.execute_with_retry, self._send_welcome_email, user.email, user.username)
        else:
            task_manager.execute_with_retry(
                self._send_welcome_email, user.email, user.username
            )

        return user
    #completed
    @redis_cache(key_generator_func=query_key_generator, module="users", resource="get_users", expire_seconds=3600)
    def get_users(self, skip: int = 0, limit: int = 100) -> dict:
        """Return a paginated list of users with total count."""
        total = self.db.scalar(select(func.count(User.id)))
        users = (
            self.db.execute(
                select(User)
                .options(selectinload(User.roles))
                .offset(skip)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return {"users": users, "total": total}

    @redis_cache(key_generator_func=entity_key_generator, module="users", resource="profile", expire_seconds=3600,)
    def get_user_profile(self, user_id: int) -> UserProfile:
        """Fetch the user's profile, creating a default one if absent."""
        profile = self.db.execute(
            select(UserProfile).filter(UserProfile.user_id == user_id)
        ).scalar_one_or_none()
        if not profile:
            profile = UserProfile(user_id=user_id, full_name="New User")
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)
        return profile

    def update_user_profile(self, user_id: int, profile_in: UserProfileUpdate) -> UserProfile:
        """Update an existing user profile. Creates one if it doesn't exist yet."""
        profile = self.db.execute(
            select(UserProfile).filter(UserProfile.user_id == user_id)
        ).scalar_one_or_none()

        if not profile:
            profile = UserProfile(user_id=user_id, full_name=profile_in.full_name or "New User")
            self.db.add(profile)

        update_data = profile_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(profile, field, value)

        self.db.commit()
        self.db.refresh(profile)

        clear_cache(entity_key_generator("users", "profile", str(user_id)))
        logger.info("profile_updated", user_id=user_id)
        return profile

    def upload_avatar(self, user_id: int, file: UploadFile, current_user: User, background_tasks: BackgroundTasks = None) -> UserProfile:
        """
        Upload an avatar image to S3 and update the user's profile.

        This is fully synchronous — S3 upload is a blocking call.
        """
        if current_user.id != user_id:
            raise ForbiddenException("Cannot update another user's avatar")

        profile = self.db.execute(
            select(UserProfile).filter(UserProfile.user_id == user_id)
        ).scalar_one_or_none()
        if not profile:
            profile = UserProfile(user_id=user_id, full_name=current_user.username)
            self.db.add(profile)

        s3_svc = S3Service()
        file_path = f"avatars/{user_id}/{file.filename}"
        url = s3_svc.upload_file(file.file, file_path, file.content_type)

        if url:
            profile.avatar_url = url
            self.db.commit()
            self.db.refresh(profile)

            clear_cache(entity_key_generator("users", "profile", str(user_id)))

            # Run sync background task with retries
            task_manager = BackgroundTaskManager(self.db)
            if background_tasks:
                background_tasks.add_task(task_manager.execute_with_retry, self._sync_task_profile_updated, user_id)
            else:
                task_manager.execute_with_retry(self._sync_task_profile_updated, user_id)

        return profile

    def deactivate_user(self, user_id: int) -> User:
        """Soft-delete a user by setting is_active to False."""
        user = self.db.execute(
            select(User).filter(User.id == user_id)
        ).scalar_one_or_none()
        if not user:
            raise NotFoundException("User", user_id)

        user.is_active = False
        self.db.commit()
        self.db.refresh(user)

        clear_cache("*:users:*")
        logger.info("user_deactivated", user_id=user_id)
        return user

    def _sync_task_profile_updated(self, user_id: int):
        """Synchronous background task triggered after profile changes."""
        user = self.db.execute(
            select(User).filter(User.id == user_id)
        ).scalar_one_or_none()
        if user:
            EmailService.send_email(
                to_email=user.email,
                subject="Profile Updated",
                template_path=f"{settings.EMAIL_TEMPLATE_DIR}/profile_updated.html",
                context={"email": user.email, "year": datetime.now(timezone.utc).year},
            )
        logger.info("profile_sync_task_executed", user_id=user_id)

    @staticmethod
    def _send_welcome_email(email: str, username: str):
        """Background task: send welcome email to newly registered user."""
        EmailService.send_email(
            to_email=email,
            subject="Welcome to Learning Platform!",
            template_path=f"{settings.EMAIL_TEMPLATE_DIR}/welcome.html",
            context={"full_name": username, "year": datetime.now(timezone.utc).year},
        )
