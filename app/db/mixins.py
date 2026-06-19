from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, declarative_mixin
from sqlalchemy.sql import func
from datetime import datetime

@declarative_mixin
class IDMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

@declarative_mixin
class TimeStampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
