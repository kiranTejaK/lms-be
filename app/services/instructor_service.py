"""Instructor CRUD service."""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from typing import List
import structlog

from app.models.user import Instructor, User
from app.schemas.user import InstructorCreate, InstructorUpdate
from app.core.exceptions import NotFoundException, ConflictException
from app.crud.crud_instructor import crud_instructor
from app.crud.crud_user import crud_user
from app.core.redis import clear_cache, redis_cache, query_key_generator, entity_key_generator

logger = structlog.get_logger(__name__)


class InstructorService:
    def __init__(self, db: Session):
        self.db = db

    @redis_cache(key_generator_func=query_key_generator, module="instructors", resource="get_instructors", expire_seconds=3600)
    def get_instructors(self, skip: int = 0, limit: int = 100) -> List[Instructor]:
        """Return all instructors with their associated user details."""
        return list(
            self.db.execute(
                select(Instructor)
                .options(joinedload(Instructor.user))
                .offset(skip)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    @redis_cache(key_generator_func=entity_key_generator, module="instructors", resource="single")
    def get_instructor(self, instructor_id: int) -> Instructor:
        """Get a single instructor by ID."""
        inst = self.db.execute(
            select(Instructor)
            .options(joinedload(Instructor.user))
            .filter(Instructor.id == instructor_id)
        ).scalar_one_or_none()
        if not inst:
            raise NotFoundException("Instructor", instructor_id)
        return inst

    def create_instructor(self, inst_in: InstructorCreate) -> Instructor:
        """Create an instructor record, validating the user exists and isn't already an instructor."""
        user = crud_user.get(self.db, inst_in.user_id)
        if not user:
            raise NotFoundException("User", inst_in.user_id)

        existing = crud_instructor.get_by_user_id(self.db, user_id=inst_in.user_id)
        if existing:
            raise ConflictException("User is already an instructor")

        instructor = Instructor(**inst_in.model_dump())
        self.db.add(instructor)
        self.db.commit()
        self.db.refresh(instructor)

        clear_cache("*:instructors:*")
        logger.info("instructor_created", instructor_id=instructor.id, user_id=inst_in.user_id)
        return instructor

    def update_instructor(self, instructor_id: int, inst_in: InstructorUpdate) -> Instructor:
        """Partially update an instructor's details."""
        inst = self.get_instructor(instructor_id)
        update_data = inst_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(inst, field, value)
        self.db.commit()
        self.db.refresh(inst)

        clear_cache("*:instructors:*")
        logger.info("instructor_updated", instructor_id=instructor_id)
        return inst
