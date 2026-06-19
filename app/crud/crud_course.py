"""Course-related CRUD operations extending the generic CRUDBase."""

from typing import List

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.crud.base import CRUDBase
from app.models.course import Course, Category, Lesson
from app.schemas.course import (
    CourseCreate, CourseUpdate,
    CategoryCreate, CategoryUpdate,
    LessonCreate, LessonUpdate,
)


class CRUDCourse(CRUDBase[Course, CourseCreate, CourseUpdate]):
    """CRUD for the Course model."""

    def get_by_category(self, db: Session, *, category_id: int, skip: int = 0, limit: int = 100) -> List[Course]:
        """Fetch courses filtered by category."""
        result = db.execute(
            select(Course).filter(Course.category_id == category_id).offset(skip).limit(limit)
        )
        return list(result.scalars().all())


class CRUDCategory(CRUDBase[Category, CategoryCreate, CategoryUpdate]):
    """CRUD for the Category model."""

    def get_by_name(self, db: Session, *, name: str):
        """Fetch a category by its unique name."""
        result = db.execute(select(Category).filter(Category.name == name))
        return result.scalar_one_or_none()


class CRUDLesson(CRUDBase[Lesson, LessonCreate, LessonUpdate]):
    """CRUD for the Lesson model."""

    def get_by_course(self, db: Session, *, course_id: int) -> List[Lesson]:
        """Fetch all lessons for a given course, ordered by lesson_order."""
        result = db.execute(
            select(Lesson)
            .filter(Lesson.course_id == course_id)
            .order_by(Lesson.lesson_order)
        )
        return list(result.scalars().all())


# Singleton instances
crud_course = CRUDCourse(Course)
crud_category = CRUDCategory(Category)
crud_lesson = CRUDLesson(Lesson)
