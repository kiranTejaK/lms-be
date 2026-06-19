"""
Course endpoints: CRUD, detailed view, enrollment, and bulk operations.
"""

from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.schemas.course import CourseCreate, CourseDetailedResponse, CourseResponse, CourseUpdate
from app.services.course_service import CourseService

router = APIRouter()


@router.get("/", response_model=List[CourseResponse])
def get_courses(skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    """List all courses with eager-loaded category and instructor."""
    svc = CourseService(db)
    return svc.get_courses(skip=skip, limit=limit)


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(course_id: int, db: Session = Depends(deps.get_db)):
    """Get a single course with its lessons."""
    svc = CourseService(db)
    return svc.get_course(course_id=course_id)


@router.get("/{course_id}/detailed", response_model=CourseDetailedResponse)
def get_course_detailed(course_id: int, db: Session = Depends(deps.get_db)):
    """Get a course with all related data: category, instructor, lessons."""
    svc = CourseService(db)
    return svc.get_course_detailed(course_id)


@router.post("/", response_model=CourseResponse)
def create_course(course_in: CourseCreate, db: Session = Depends(deps.get_db)):
    """Create a new course."""
    svc = CourseService(db)
    return svc.create_course(course_in)


@router.put("/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: int,
    course_in: CourseUpdate,
    db: Session = Depends(deps.get_db),
):
    """Partially update a course."""
    svc = CourseService(db)
    return svc.update_course(course_id, course_in)


@router.delete("/{course_id}")
def delete_course(course_id: int, db: Session = Depends(deps.get_db)):
    """Delete a course and cascade to lessons/enrollments."""
    svc = CourseService(db)
    return svc.delete_course(course_id)


@router.post("/{course_id}/enroll")
def enroll_in_course(
    course_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Enroll the authenticated user in a course (with row-level locking)."""
    svc = CourseService(db)
    return svc.enroll_in_course(course_id, current_user, background_tasks)


@router.post("/bulk-update-category", response_model=Dict[str, int])
def bulk_update_course_categories(
    old_category_id: int,
    new_category_id: int,
    db: Session = Depends(deps.get_db),
):
    """Bulk-reassign courses from one category to another."""
    svc = CourseService(db)
    return svc.bulk_update_course_categories(old_category_id, new_category_id)
