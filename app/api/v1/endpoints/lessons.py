"""Lesson CRUD endpoints, scoped to courses."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.api import deps
from app.schemas.course import LessonResponse, LessonCreate, LessonUpdate
from app.services.lesson_service import LessonService

router = APIRouter()


@router.get("/by-course/{course_id}", response_model=List[LessonResponse])
def list_lessons_by_course(course_id: int, db: Session = Depends(deps.get_db)):
    """List all lessons for a course, ordered by lesson_order."""
    svc = LessonService(db)
    return svc.get_lessons_by_course(course_id)


@router.get("/{lesson_id}", response_model=LessonResponse)
def get_lesson(lesson_id: int, db: Session = Depends(deps.get_db)):
    """Get a single lesson."""
    svc = LessonService(db)
    return svc.get_lesson(lesson_id)


@router.post("/", response_model=LessonResponse)
def create_lesson(lesson_in: LessonCreate, db: Session = Depends(deps.get_db)):
    """Create a new lesson in a course."""
    svc = LessonService(db)
    return svc.create_lesson(lesson_in)


@router.put("/{lesson_id}", response_model=LessonResponse)
def update_lesson(lesson_id: int, lesson_in: LessonUpdate, db: Session = Depends(deps.get_db)):
    """Update a lesson."""
    svc = LessonService(db)
    return svc.update_lesson(lesson_id, lesson_in)


@router.delete("/{lesson_id}")
def delete_lesson(lesson_id: int, db: Session = Depends(deps.get_db)):
    """Delete a lesson."""
    svc = LessonService(db)
    return svc.delete_lesson(lesson_id)
