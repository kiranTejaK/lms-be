"""
Course service handling CRUD, enrollment with race-condition safety,
and bulk operations.

Uses `selectinload` / `joinedload` to prevent N+1 queries.
Enrollment uses `with_for_update()` row locking for concurrency safety.
"""

from typing import List

import structlog
from fastapi import BackgroundTasks
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.exceptions import AppException, ConflictException, NotFoundException, ValidationException
from app.core.redis import clear_cache, entity_key_generator, query_key_generator, redis_cache
from app.core.tasks import BackgroundTaskManager
from app.models.course import Course, Enrollment
from app.models.user import User
from app.schemas.course import CourseCreate, CourseUpdate
from app.services.email_service import EmailService

logger = structlog.get_logger(__name__)


class CourseService:
    def __init__(self, db: Session):
        self.db = db

    @redis_cache(key_generator_func=query_key_generator, module="courses", resource="course", expire_seconds=3600)
    def get_courses(self, skip: int = 0, limit: int = 100) -> List[Course]:
        """Fetch courses with eager-loaded category and instructor."""
        logger.info("fetching_courses", skip=skip, limit=limit)
        stmt = (
            select(Course)
            .options(selectinload(Course.category), joinedload(Course.instructor))
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    @redis_cache(key_generator_func=entity_key_generator, module="courses", resource="course")
    def get_course(self, course_id: int) -> Course:
        """Fetch a single course with its lessons eager-loaded."""
        logger.info("fetching_single_course", course_id=course_id)
        stmt = (
            select(Course)
            .options(selectinload(Course.lessons))
            .filter(Course.id == course_id)
        )
        course = self.db.execute(stmt).scalar_one_or_none()
        if not course:
            raise NotFoundException("Course", course_id)
        return course

    def get_course_detailed(self, course_id: int) -> Course:
        """
        Fetch a course with all relations: category, instructor → user, lessons.

        Uses `joinedload` for single-row relations and `selectinload` for
        collections to balance query count vs result-set size.
        """
        stmt = (
            select(Course)
            .options(
                joinedload(Course.category),
                joinedload(Course.instructor),
                selectinload(Course.lessons),
            )
            .filter(Course.id == course_id)
        )
        course = self.db.execute(stmt).unique().scalar_one_or_none()
        if not course:
            raise NotFoundException("Course", course_id)
        return course

    def create_course(self, course_in: CourseCreate) -> Course:
        """Create a new course and invalidate list caches."""
        course = Course(**course_in.model_dump())
        self.db.add(course)
        self.db.commit()
        self.db.refresh(course)

        logger.info("course_created", course_id=course.id)
        clear_cache("*:courses:get_courses:*")
        return course

    def update_course(self, course_id: int, course_in: CourseUpdate) -> Course:
        """Partially update a course's fields."""
        course = self.db.execute(
            select(Course).filter(Course.id == course_id)
        ).scalar_one_or_none()
        if not course:
            raise NotFoundException("Course", course_id)

        update_data = course_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(course, field, value)

        self.db.commit()
        self.db.refresh(course)

        clear_cache("*:courses:*")
        logger.info("course_updated", course_id=course_id)
        return course

    def delete_course(self, course_id: int) -> dict:
        """Delete a course and cascade to lessons/enrollments."""
        course = self.db.execute(
            select(Course).filter(Course.id == course_id)
        ).scalar_one_or_none()
        if not course:
            raise NotFoundException("Course", course_id)

        self.db.delete(course)
        self.db.commit()

        clear_cache("*:courses:*")
        logger.info("course_deleted", course_id=course_id)
        return {"detail": f"Course {course_id} deleted"}

    def enroll_in_course(self, course_id: int, current_user: User, background_tasks: BackgroundTasks = None) -> dict:
        """
        Enroll a user in a course with row-level locking to prevent
        race conditions on the max_students cap.
        """
        try:
            # Lock the course row to prevent concurrent over-enrollment
            stmt = select(Course).filter(Course.id == course_id).with_for_update()
            course = self.db.execute(stmt).scalar_one_or_none()

            if not course:
                raise NotFoundException("Course", course_id)

            existing = self.db.execute(
                select(Enrollment).filter(
                    Enrollment.user_id == current_user.id,
                    Enrollment.course_id == course_id,
                )
            ).scalar_one_or_none()
            if existing:
                raise ConflictException("Already enrolled in this course")

            count_stmt = select(func.count(Enrollment.id)).filter(
                Enrollment.course_id == course_id
            )
            current_count = self.db.scalar(count_stmt)

            if current_count >= course.max_students:
                raise ValidationException("Course is full")

            enrollment = Enrollment(user_id=current_user.id, course_id=course_id)
            self.db.add(enrollment)
            self.db.commit()
            self.db.refresh(enrollment)

            clear_cache(entity_key_generator("courses", "single", str(course_id)))
            clear_cache("*:enrollments:*")

            # Send enrollment confirmation email as a background task
            task_manager = BackgroundTaskManager(self.db)
            if background_tasks:
                background_tasks.add_task(task_manager.execute_with_retry, self._send_enrollment_email, current_user.email, course.title)
            else:
                task_manager.execute_with_retry(
                    self._send_enrollment_email, current_user.email, course.title
                )

            return {"status": "success", "enrollment_id": enrollment.id}

        except (NotFoundException, ConflictException, ValidationException):
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            logger.error("enrollment_transaction_failed", error=str(e))
            raise AppException("Enrollment transaction failed")

    def _send_enrollment_email(self, user_email: str, course_title: str):
        """Background task: send enrollment confirmation email."""
        EmailService.send_email(
            to_email=user_email,
            subject=f"Enrolled in {course_title}",
            template_path=f"{settings.EMAIL_TEMPLATE_DIR}/enrollment_confirmation.html",
            context={"course_title": course_title, "email": user_email},
        )

    def bulk_update_course_categories(self, old_category_id: int, new_category_id: int) -> dict:
        """Bulk-reassign courses from one category to another."""
        stmt = (
            update(Course)
            .where(Course.category_id == old_category_id)
            .values(category_id=new_category_id)
        )
        result = self.db.execute(stmt)
        self.db.commit()

        logger.info(
            "bulk_update_completed",
            old_category_id=old_category_id,
            new_category_id=new_category_id,
            rowcount=result.rowcount,
        )
        clear_cache("*:courses:*")
        return {"updated_count": result.rowcount}
