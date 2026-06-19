"""Admin service for failed task management and dashboard statistics."""

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import List
import structlog

from app.models.failed_task import FailedTask
from app.models.user import User
from app.models.course import Course, Enrollment, Category, Lesson
from app.core.exceptions import NotFoundException

logger = structlog.get_logger(__name__)


class AdminService:
    def __init__(self, db: Session):
        self.db = db

    def get_failed_tasks(self, skip: int = 0, limit: int = 50) -> List[FailedTask]:
        """Return failed background tasks for admin review."""
        return list(
            self.db.execute(
                select(FailedTask).order_by(FailedTask.failed_at.desc()).offset(skip).limit(limit)
            )
            .scalars()
            .all()
        )

    def retry_failed_task(self, task_id: int) -> dict:
        """
        Mark a failed task as acknowledged / retried.

        In a real system this would re-queue the task — here we simply
        delete the record to clear the failure log.
        """
        task = self.db.execute(
            select(FailedTask).filter(FailedTask.id == task_id)
        ).scalar_one_or_none()
        if not task:
            raise NotFoundException("Failed task", task_id)

        self.db.delete(task)
        self.db.commit()

        logger.info("failed_task_retried", task_id=task_id, task_name=task.task_name)
        return {"detail": f"Failed task {task_id} cleared"}

    def get_dashboard_stats(self) -> dict:
        """Return aggregate counts for the admin dashboard."""
        return {
            "total_users": self.db.scalar(select(func.count(User.id))) or 0,
            "total_courses": self.db.scalar(select(func.count(Course.id))) or 0,
            "total_enrollments": self.db.scalar(select(func.count(Enrollment.id))) or 0,
            "total_categories": self.db.scalar(select(func.count(Category.id))) or 0,
            "total_lessons": self.db.scalar(select(func.count(Lesson.id))) or 0,
        }
