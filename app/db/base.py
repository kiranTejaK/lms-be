from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Define standard naming conventions for constraints and indexes
# This avoids naming conflicts and ensures deterministic names during Alembic migrations
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

class BaseModel(DeclarativeBase):
    """
    Base class for all SQLAlchemy 2.0 mapped models.
    Inherits from DeclarativeBase which is the modern approach 
    over declarative_base().
    """
    metadata = MetaData(naming_convention=convention)
    __abstract__ = True
