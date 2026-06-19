"""User CRUD operations extending the generic CRUDBase."""

from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    """
    CRUD operations for the User model.

    Adds lookup by email and username on top of the standard
    get / get_multi / create / update / remove provided by CRUDBase.
    """

    def get_by_email(self, db: Session, *, email: str) -> Optional[User]:
        """Fetch a user by email address."""
        result = db.execute(select(User).filter(User.email == email))
        return result.scalar_one_or_none()

    def get_by_username(self, db: Session, *, username: str) -> Optional[User]:
        """Fetch a user by username."""
        result = db.execute(select(User).filter(User.username == username))
        return result.scalar_one_or_none()


# Singleton instance — import this instead of the class
crud_user = CRUDUser(User)
