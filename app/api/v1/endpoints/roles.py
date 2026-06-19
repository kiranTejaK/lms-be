"""Role management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.api import deps
from app.schemas.user import RoleResponse, RoleCreate, RoleAssign
from app.services.role_service import RoleService

router = APIRouter()


@router.get("/", response_model=List[RoleResponse])
def list_roles(db: Session = Depends(deps.get_db)):
    """List all available roles."""
    svc = RoleService(db)
    return svc.get_roles()


@router.post("/", response_model=RoleResponse)
def create_role(role_in: RoleCreate, db: Session = Depends(deps.get_db)):
    """Create a new role."""
    svc = RoleService(db)
    return svc.create_role(role_in.name)


@router.post("/assign")
def assign_role(body: RoleAssign, db: Session = Depends(deps.get_db)):
    """Assign a role to a user."""
    svc = RoleService(db)
    return svc.assign_role_to_user(body.user_id, body.role_id)
