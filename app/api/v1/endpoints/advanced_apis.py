"""
Advanced API endpoints demonstrating production database patterns.

Patterns:
  - Transaction + row-level locking (concurrent enrollment)
  - N+1 query prevention (instructor dashboard)
  - Bulk insert with atomic rollback (bulk course creation)
  - Aggregation / subquery optimization (course analytics)
  - Pessimistic locking with deadlock avoidance (enrollment transfer)
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.api import deps
from app.schemas.advanced import (
    BulkEnrollRequest,
    BulkEnrollResponse,
    BulkCourseCreateRequest,
    BulkCourseCreateResponse,
    TransferEnrollmentRequest,
    TransferEnrollmentResponse,
    CourseAnalyticsResponse,
    InstructorDashboardResponse,
)
from app.services.advanced_service import AdvancedService

router = APIRouter()


@router.post("/concurrent-enroll", response_model=BulkEnrollResponse)
def concurrent_enroll(
    req: BulkEnrollRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(deps.get_db),
):
    """
    Enroll multiple users in a single course atomically.

    Uses row-level locking (`SELECT … FOR UPDATE`) on the course row
    to prevent race conditions when concurrent requests compete for
    the remaining seats.
    """
    svc = AdvancedService(db)
    return svc.concurrent_enroll(req, background_tasks)


@router.get(
    "/instructor-dashboard/{instructor_id}",
    response_model=InstructorDashboardResponse,
)
def instructor_dashboard(
    instructor_id: int,
    db: Session = Depends(deps.get_db),
):
    """
    Fetch a rich instructor overview with courses, lessons, and enrollment
    counts — all in 3–4 queries instead of N+1.

    Uses `selectinload` for collections and `joinedload` for single-row
    relations.
    """
    svc = AdvancedService(db)
    return svc.get_instructor_dashboard(instructor_id)


@router.post("/bulk-create-courses", response_model=BulkCourseCreateResponse)
def bulk_create_courses(
    req: BulkCourseCreateRequest,
    db: Session = Depends(deps.get_db),
):
    """
    Batch-create multiple courses in a single atomic transaction.

    If any single insert fails (e.g. FK constraint violation), the
    entire batch is rolled back — no partial state.
    """
    svc = AdvancedService(db)
    return svc.bulk_create_courses(req)


@router.get("/course-analytics", response_model=CourseAnalyticsResponse)
def course_analytics(
    db: Session = Depends(deps.get_db),
):
    """
    Compute per-course enrollment statistics using database-level
    aggregation (COUNT, AVG, CASE) instead of loading all rows.
    """
    svc = AdvancedService(db)
    return svc.get_course_analytics()


@router.post("/transfer-enrollment", response_model=TransferEnrollmentResponse)
def transfer_enrollment(
    req: TransferEnrollmentRequest,
    db: Session = Depends(deps.get_db),
):
    """
    Transfer a student from one course to another atomically.

    Acquires row-level locks on both course rows in ascending ID order
    to prevent deadlocks under concurrent transfers.
    """
    svc = AdvancedService(db)
    return svc.transfer_enrollment(req)
