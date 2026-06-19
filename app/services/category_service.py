"""Category CRUD service."""

from typing import List

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.core.redis import clear_cache, entity_key_generator, query_key_generator, redis_cache
from app.crud.crud_course import crud_category
from app.models.course import Category
from app.schemas.course import CategoryCreate, CategoryUpdate

logger = structlog.get_logger(__name__)


class CategoryService:
    def __init__(self, db: Session):
        self.db = db

    @redis_cache(key_generator_func=query_key_generator, module="categories", resource="get_categories", expire_seconds=3600)
    def get_categories(self, skip: int = 0, limit: int = 100) -> List[Category]:
        """Return all categories with pagination."""
        return list(
            self.db.execute(select(Category).offset(skip).limit(limit)).scalars().all()
        )

    @redis_cache(key_generator_func=entity_key_generator, module="categories", resource="single")
    def get_category(self, category_id: int) -> Category:
        """Get a single category by ID."""
        cat = crud_category.get(self.db, category_id)
        if not cat:
            raise NotFoundException("Category", category_id)
        return cat

    def create_category(self, cat_in: CategoryCreate) -> Category:
        """Create a new category, enforcing name uniqueness."""
        existing = crud_category.get_by_name(self.db, name=cat_in.name)
        if existing:
            raise ConflictException("Category already exists")

        cat = Category(**cat_in.model_dump())
        self.db.add(cat)
        self.db.commit()
        self.db.refresh(cat)

        logger.info("category_created", category_id=cat.id)
        return cat

    def update_category(self, category_id: int, cat_in: CategoryUpdate) -> Category:
        """Update a category's fields."""
        cat = self.get_category(category_id)
        update_data = cat_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(cat, field, value)
        self.db.commit()
        self.db.refresh(cat)

        clear_cache("*:courses:*")
        logger.info("category_updated", category_id=category_id)
        return cat

    def delete_category(self, category_id: int) -> dict:
        """Delete a category. Courses referencing it will have category_id set to NULL."""
        cat = self.get_category(category_id)
        self.db.delete(cat)
        self.db.commit()

        clear_cache("*:courses:*")
        logger.info("category_deleted", category_id=category_id)
        return {"detail": f"Category {category_id} deleted"}
