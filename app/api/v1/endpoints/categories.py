"""Category CRUD endpoints."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.schemas.course import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services.category_service import CategoryService

router = APIRouter()


@router.get("/", response_model=List[CategoryResponse])
def list_categories(skip: int = 0, limit: int = 100, db: Session = Depends(deps.get_db)):
    """List all categories."""
    svc = CategoryService(db)
    return svc.get_categories(skip=skip, limit=limit)


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, db: Session = Depends(deps.get_db)):
    """Get a single category by ID."""
    svc = CategoryService(db)
    return svc.get_category(category_id)


@router.post("/", response_model=CategoryResponse)
def create_category(cat_in: CategoryCreate, db: Session = Depends(deps.get_db)):
    """Create a new category."""
    svc = CategoryService(db)
    return svc.create_category(cat_in)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, cat_in: CategoryUpdate, db: Session = Depends(deps.get_db)):
    """Update a category."""
    svc = CategoryService(db)
    return svc.update_category(category_id, cat_in)


@router.delete("/{category_id}")
def delete_category(category_id: int, db: Session = Depends(deps.get_db)):
    """Delete a category."""
    svc = CategoryService(db)
    return svc.delete_category(category_id)
