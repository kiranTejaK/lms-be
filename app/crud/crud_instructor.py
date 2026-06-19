"""Instructor CRUD operations extending the generic CRUDBase."""

from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.crud.base import CRUDBase
from app.models.user import Instructor
from app.schemas.user import InstructorCreate, InstructorUpdate


class CRUDInstructor(CRUDBase[Instructor, InstructorCreate, InstructorUpdate]):
    """CRUD for the Instructor model."""

    def get_by_user_id(self, db: Session, *, user_id: int) -> Optional[Instructor]:
        """Fetch an instructor record by their associated user ID."""
        result = db.execute(
            select(Instructor).filter(Instructor.user_id == user_id)
        )
        return result.scalar_one_or_none()


# Singleton instance
crud_instructor = CRUDInstructor(Instructor)
