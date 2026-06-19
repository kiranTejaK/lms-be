from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class FailedTaskBase(BaseModel):
    task_name: str
    task_args: Optional[Dict[str, Any]] = None
    last_error: str
    attempts: int = 1
    failed_at: Optional[datetime] = None

class FailedTaskCreate(FailedTaskBase):
    pass

class FailedTaskResponse(FailedTaskBase):
    id: int
    failed_at: datetime
    model_config = ConfigDict(from_attributes=True)
