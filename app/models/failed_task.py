from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base import BaseModel
from app.db.mixins import IDMixin, TimeStampMixin


class FailedTask(BaseModel, IDMixin, TimeStampMixin):
    __tablename__ = 'failed_tasks'
    task_name = Column(String(255), index=True, nullable=False)
    task_args = Column(JSON, nullable=True)
    last_error = Column(Text, nullable=False)
    attempts = Column(Integer, default=1, nullable=False)
    failed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
