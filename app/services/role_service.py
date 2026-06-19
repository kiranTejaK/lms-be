"""Role management service."""

from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
import structlog

from app.models.user import Role, User
from app.core.exceptions import NotFoundException, ConflictException
from app.crud.crud_role import crud_role
from app.crud.crud_user import crud_user

logger = structlog.get_logger(__name__)


class RoleService:
    def __init__(self, db: Session):
        self.db = db

    def get_roles(self) -> List[Role]:
        """Return all roles."""
        return list(self.db.execute(select(Role)).scalars().all())

    def create_role(self, name: str) -> Role:
        """Create a new role with a unique name."""
        existing = crud_role.get_by_name(self.db, name=name)
        if existing:
            raise ConflictException("Role already exists")

        role = Role(name=name)
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)

        logger.info("role_created", role_id=role.id, name=name)
        return role

    def assign_role_to_user(self, user_id: int, role_id: int) -> dict:
        """Assign a role to a user. Idempotent — silently skips if already assigned."""
        user = crud_user.get(self.db, user_id)
        if not user:
            raise NotFoundException("User", user_id)

        role = crud_role.get(self.db, role_id)
        if not role:
            raise NotFoundException("Role", role_id)

        if role not in user.roles:
            user.roles.append(role)
            self.db.commit()
            logger.info("role_assigned", user_id=user_id, role_id=role_id)

        return {"detail": f"Role '{role.name}' assigned to user {user_id}"}
