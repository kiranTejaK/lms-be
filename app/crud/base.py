"""
Generic CRUD base class providing standard database operations.

Uses SQLAlchemy 2.0 style queries with the `select()` construct.
All operations are synchronous, consistent with the project's architecture.
"""

from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=PydanticBaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=PydanticBaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Generic CRUD object with default methods to Create, Read, Update, Delete.

    Subclass this with concrete model and schema types for type-safe operations:
        class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
            ...
    """

    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        """Fetch a single record by primary key."""
        result = db.execute(select(self.model).filter(self.model.id == id))
        return result.scalar_one_or_none()

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Fetch multiple records with pagination."""
        result = db.execute(select(self.model).offset(skip).limit(limit))
        return list(result.scalars().all())

    def create(self, db: Session, *, obj_in: CreateSchemaType) -> ModelType:
        """Create a new record from a Pydantic schema."""
        obj_in_data = obj_in.model_dump()
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, *, db_obj: ModelType, obj_in: Union[UpdateSchemaType, Dict[str, Any]]) -> ModelType:
        """Update an existing record with partial data."""
        obj_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        for field in obj_data:
            setattr(db_obj, field, obj_data[field])
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: int) -> Optional[ModelType]:
        """Delete a record by primary key. Returns the deleted object or None."""
        obj = self.get(db, id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj
