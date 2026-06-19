"""Role CRUD operations extending the generic CRUDBase."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.user import Role
from app.schemas.user import RoleBase, RoleCreate


class CRUDRole(CRUDBase[Role, RoleCreate, RoleBase]):
    """CRUD for the Role model."""

    def get_by_name(self, db: Session, *, name: str) -> Optional[Role]:
        """Fetch a role by its unique name."""
        result = db.execute(select(Role).filter(Role.name == name))
        return result.scalar_one_or_none()


# Singleton instance
crud_role = CRUDRole(Role)
