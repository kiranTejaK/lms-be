"""Enrollment management endpoints."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.schemas.course import EnrollmentResponse, EnrollmentUpdate
from app.services.enrollment_service import EnrollmentService

router = APIRouter()


@router.get("/user/{user_id}", response_model=List[EnrollmentResponse])
def get_user_enrollments(user_id: int, db: Session = Depends(deps.get_db)):
    """List all enrollments for a user."""
    svc = EnrollmentService(db)
    return svc.get_user_enrollments(user_id)


@router.get("/course/{course_id}", response_model=List[EnrollmentResponse])
def get_course_enrollments(course_id: int, db: Session = Depends(deps.get_db)):
    """List all enrollments for a course."""
    svc = EnrollmentService(db)
    return svc.get_course_enrollments(course_id)


@router.put("/{enrollment_id}", response_model=EnrollmentResponse)
def update_enrollment(
    enrollment_id: int,
    enroll_in: EnrollmentUpdate,
    db: Session = Depends(deps.get_db),
):
    """Update an enrollment's progress or completion status."""
    svc = EnrollmentService(db)
    return svc.update_enrollment(enrollment_id, enroll_in)


@router.delete("/{enrollment_id}")
def unenroll(
    enrollment_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Unenroll from a course (only the enrolled user can unenroll)."""
    svc = EnrollmentService(db)
    return svc.unenroll(enrollment_id, current_user.id)
