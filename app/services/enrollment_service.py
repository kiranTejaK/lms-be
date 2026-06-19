"""Enrollment management service."""

from typing import List

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.redis import clear_cache, query_key_generator, redis_cache
from app.crud.crud_enrollment import crud_enrollment
from app.models.course import Enrollment
from app.schemas.course import EnrollmentUpdate

logger = structlog.get_logger(__name__)


class EnrollmentService:
    def __init__(self, db: Session):
        self.db = db

    @redis_cache(key_generator_func=query_key_generator, module="enrollments", resource="get_user_enrollments", expire_seconds=3600)
    def get_user_enrollments(self, user_id: int) -> List[Enrollment]:
        """Return all enrollments for a specific user."""
        return crud_enrollment.get_by_user(self.db, user_id=user_id)

    @redis_cache(key_generator_func=query_key_generator, module="enrollments", resource="get_course_enrollments", expire_seconds=3600)
    def get_course_enrollments(self, course_id: int) -> List[Enrollment]:
        """Return all enrollments for a specific course."""
        return crud_enrollment.get_by_course(self.db, course_id=course_id)

    def update_enrollment(self, enrollment_id: int, enroll_in: EnrollmentUpdate) -> Enrollment:
        """Update enrollment progress / completion status."""
        enrollment = self.db.execute(
            select(Enrollment).filter(Enrollment.id == enrollment_id)
        ).scalar_one_or_none()
        if not enrollment:
            raise NotFoundException("Enrollment", enrollment_id)

        update_data = enroll_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(enrollment, field, value)
        self.db.commit()
        self.db.refresh(enrollment)

        clear_cache("*:enrollments:*")
        logger.info("enrollment_updated", enrollment_id=enrollment_id)
        return enrollment

    def unenroll(self, enrollment_id: int, user_id: int) -> dict:
        """Remove a user's enrollment. Only the enrolled user can unenroll."""
        enrollment = self.db.execute(
            select(Enrollment).filter(Enrollment.id == enrollment_id)
        ).scalar_one_or_none()
        if not enrollment:
            raise NotFoundException("Enrollment", enrollment_id)
        if enrollment.user_id != user_id:
            raise ForbiddenException("Cannot unenroll another user")

        self.db.delete(enrollment)
        self.db.commit()

        clear_cache("*:courses:*")
        clear_cache("*:enrollments:*")
        logger.info("user_unenrolled", enrollment_id=enrollment_id, user_id=user_id)
        return {"detail": "Successfully unenrolled"}
