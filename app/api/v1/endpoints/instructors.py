"""Instructor CRUD endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.api import deps
from app.schemas.user import InstructorResponse, InstructorCreate, InstructorUpdate
from app.services.instructor_service import InstructorService

router = APIRouter()


@router.get("/", response_model=List[InstructorResponse])
def list_instructors(skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    """List all instructors."""
    svc = InstructorService(db)
    return svc.get_instructors(skip=skip, limit=limit)


@router.get("/{instructor_id}", response_model=InstructorResponse)
def get_instructor(instructor_id: int, db: Session = Depends(deps.get_db)):
    """Get a single instructor."""
    svc = InstructorService(db)
    return svc.get_instructor(instructor_id)


@router.post("/", response_model=InstructorResponse)
def create_instructor(inst_in: InstructorCreate, db: Session = Depends(deps.get_db)):
    """Create an instructor profile for an existing user."""
    svc = InstructorService(db)
    return svc.create_instructor(inst_in)


@router.put("/{instructor_id}", response_model=InstructorResponse)
def update_instructor(
    instructor_id: int,
    inst_in: InstructorUpdate,
    db: Session = Depends(deps.get_db),
):
    """Update an instructor's details."""
    svc = InstructorService(db)
    return svc.update_instructor(instructor_id, inst_in)
