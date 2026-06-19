"""
Synchronous background task manager with retry logic.

Provides a retry mechanism with exponential backoff for tasks that may
fail transiently. Failed tasks are logged to the database for manual
intervention after all retries are exhausted.
"""

import time
import traceback
from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.models.failed_task import FailedTask

logger = structlog.get_logger(__name__)


class BackgroundTaskManager:
    """
    Manages synchronous task execution with configurable retry logic.

    Usage:
        manager = BackgroundTaskManager(db)
        manager.execute_with_retry(some_function, arg1, arg2, max_retries=3)
    """

    def __init__(self, db: Session):
        self.db = db

    def execute_with_retry(self, func, *args, max_retries: int = 3, base_delay: float = 2.0, **kwargs):
        """
        Execute a function with exponential backoff on failure.

        Args:
            func: The callable to execute.
            *args: Positional arguments passed to `func`.
            max_retries: Maximum number of retry attempts (default: 3).
            base_delay: Base delay in seconds for exponential backoff.
            **kwargs: Keyword arguments passed to `func`.
        """
        task_name = func.__name__
        logger.info("background_task_started", task_name=task_name)

        attempt = 1
        while attempt <= max_retries:
            try:
                func(*args, **kwargs)
                logger.info("background_task_success", task_name=task_name, attempt=attempt)
                return
            except Exception as e:
                logger.error(
                    "background_task_failed",
                    task_name=task_name,
                    attempt=attempt,
                    error=str(e),
                    traceback=traceback.format_exc(),
                )
                if attempt == max_retries:
                    self._log_failed_task(task_name, str(e), args, kwargs)
                    return
                time.sleep(base_delay ** attempt)
                attempt += 1

    def _log_failed_task(self, task_name: str, error: str, args: tuple, kwargs: dict):
        """
        Record a permanently failed task to the database for manual review.

        This is called only after all retry attempts are exhausted.
        """
        try:
            failed_record = FailedTask(
                task_name=task_name,
                task_args={
                    "args": [str(a) for a in args],
                    "kwargs": {k: str(v) for k, v in kwargs.items()},
                },
                last_error=error,
                attempts=3,
                failed_at=datetime.now(timezone.utc),
            )
            self.db.add(failed_record)
            self.db.commit()
            logger.info("failed_task_recorded_to_db", task_name=task_name)
        except Exception as db_err:
            logger.critical("failed_task_recording_error", error=str(db_err))
