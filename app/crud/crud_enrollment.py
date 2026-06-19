"""Enrollment CRUD operations extending the generic CRUDBase."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.course import Enrollment
from app.schemas.course import EnrollmentCreate, EnrollmentUpdate


class CRUDEnrollment(CRUDBase[Enrollment, EnrollmentCreate, EnrollmentUpdate]):
    """CRUD for the Enrollment model."""

    def get_by_user(self, db: Session, *, user_id: int) -> List[Enrollment]:
        """Fetch all enrollments for a specific user."""
        result = db.execute(
            select(Enrollment).filter(Enrollment.user_id == user_id)
        )
        return list(result.scalars().all())

    def get_by_course(self, db: Session, *, course_id: int) -> List[Enrollment]:
        """Fetch all enrollments for a specific course."""
        result = db.execute(
            select(Enrollment).filter(Enrollment.course_id == course_id)
        )
        return list(result.scalars().all())

    def get_by_user_and_course(self, db: Session, *, user_id: int, course_id: int) -> Optional[Enrollment]:
        """Check if a user is already enrolled in a course."""
        result = db.execute(
            select(Enrollment).filter(
                Enrollment.user_id == user_id,
                Enrollment.course_id == course_id,
            )
        )
        return result.scalar_one_or_none()


# Singleton instance
crud_enrollment = CRUDEnrollment(Enrollment)
