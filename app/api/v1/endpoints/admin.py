"""Admin endpoints: failed tasks management and dashboard stats."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.schemas.course import DashboardStats
from app.schemas.failed_task import FailedTaskResponse
from app.services.admin_service import AdminService

router = APIRouter()


@router.get("/failed-tasks", response_model=List[FailedTaskResponse])
def list_failed_tasks(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """List all failed background tasks (admin only)."""
    svc = AdminService(db)
    return svc.get_failed_tasks(skip=skip, limit=limit)


@router.delete("/failed-tasks/{task_id}")
def retry_failed_task(
    task_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """Acknowledge/retry a failed task — removes it from the failure log (admin only)."""
    svc = AdminService(db)
    return svc.retry_failed_task(task_id)


@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_admin),
):
    """Return aggregate statistics for the admin dashboard (admin only)."""
    svc = AdminService(db)
    return svc.get_dashboard_stats()
