"""
Database engine and session factory configuration.

Uses synchronous SQLAlchemy engine with connection pooling.
The `SessionLocal` factory creates scoped sessions for request handling.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URI,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
