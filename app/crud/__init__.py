"""Re-export all CRUD instances for convenient imports."""

from .crud_course import crud_category, crud_course, crud_lesson
from .crud_enrollment import crud_enrollment
from .crud_instructor import crud_instructor
from .crud_role import crud_role
from .crud_user import crud_user

__all__ = [
    "crud_category",
    "crud_course",
    "crud_lesson",
    "crud_enrollment",
    "crud_instructor",
    "crud_role",
    "crud_user",
]
