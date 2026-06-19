"""Lesson CRUD service scoped to courses."""

from typing import List

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.core.redis import clear_cache, entity_key_generator, query_key_generator, redis_cache
from app.crud.crud_course import crud_course, crud_lesson
from app.models.course import Lesson
from app.schemas.course import LessonCreate, LessonUpdate

logger = structlog.get_logger(__name__)


class LessonService:
    def __init__(self, db: Session):
        self.db = db

    @redis_cache(key_generator_func=query_key_generator, module="lessons", resource="get_lessons_by_course", expire_seconds=3600)
    def get_lessons_by_course(self, course_id: int) -> List[Lesson]:
        """Return all lessons for a course, ordered by lesson_order."""
        return list(
            self.db.execute(
                select(Lesson)
                .filter(Lesson.course_id == course_id)
                .order_by(Lesson.lesson_order)
            )
            .scalars()
            .all()
        )

    @redis_cache(key_generator_func=entity_key_generator, module="lessons", resource="single")
    def get_lesson(self, lesson_id: int) -> Lesson:
        """Get a single lesson by ID."""
        lesson = crud_lesson.get(self.db, lesson_id)
        if not lesson:
            raise NotFoundException("Lesson", lesson_id)
        return lesson

    def create_lesson(self, lesson_in: LessonCreate) -> Lesson:
        """Create a lesson — validates the parent course exists."""
        course = crud_course.get(self.db, lesson_in.course_id)
        if not course:
            raise NotFoundException("Course", lesson_in.course_id)

        lesson = Lesson(**lesson_in.model_dump())
        self.db.add(lesson)
        self.db.commit()
        self.db.refresh(lesson)

        clear_cache("*:courses:*")
        logger.info("lesson_created", lesson_id=lesson.id, course_id=lesson_in.course_id)
        return lesson

    def update_lesson(self, lesson_id: int, lesson_in: LessonUpdate) -> Lesson:
        """Partially update a lesson."""
        lesson = self.get_lesson(lesson_id)
        update_data = lesson_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(lesson, field, value)
        self.db.commit()
        self.db.refresh(lesson)

        clear_cache("*:courses:*")
        logger.info("lesson_updated", lesson_id=lesson_id)
        return lesson

    def delete_lesson(self, lesson_id: int) -> dict:
        """Delete a lesson."""
        lesson = self.get_lesson(lesson_id)
        self.db.delete(lesson)
        self.db.commit()

        clear_cache("*:courses:*")
        logger.info("lesson_deleted", lesson_id=lesson_id)
        return {"detail": f"Lesson {lesson_id} deleted"}
