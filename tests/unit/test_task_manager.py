# ==============================================================================
# INTEGRATION TESTS — BackgroundTaskManager with real DB session
#
# Mocking: None — uses real SQLite DB session and real function calls.
# Tests the retry mechanism with exponential backoff and the failed-task
# database logging when all retries are exhausted.
# ==============================================================================

"""BackgroundTaskManager tests — fully synchronous, real DB."""

from unittest.mock import MagicMock

from sqlalchemy import select

from app.core.tasks import BackgroundTaskManager
from app.models.failed_task import FailedTask


def test_run_with_retry_success(db_session):
    """INTEGRATION: Successful task execution on first attempt."""
    task_manager = BackgroundTaskManager(db_session)

    mock_func = MagicMock()
    mock_func.__name__ = "mock_func"

    task_manager.execute_with_retry(mock_func)
    assert mock_func.call_count == 1


def test_run_with_retry_eventual_success(db_session):
    """INTEGRATION: Task fails once then succeeds on retry."""
    task_manager = BackgroundTaskManager(db_session)

    call_count = 0

    def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("transient failure")

    flaky_func.__name__ = "flaky_func"

    task_manager.execute_with_retry(flaky_func, max_retries=3, base_delay=0.01)
    assert call_count == 2  # Failed once, succeeded on retry


def test_run_with_retry_exhaustion_logs_to_db(db_session):
    """INTEGRATION: After all retries, the failed task is recorded in the database."""
    task_manager = BackgroundTaskManager(db_session)

    def always_fails():
        raise ValueError("permanent failure")

    always_fails.__name__ = "always_fails"

    task_manager.execute_with_retry(always_fails, max_retries=2, base_delay=0.01)

    # Verify the failed task was saved to DB
    stmt = select(FailedTask).where(FailedTask.task_name == "always_fails")
    failed_task = db_session.execute(stmt).scalar_one_or_none()

    assert failed_task is not None
    assert "permanent failure" in failed_task.last_error
