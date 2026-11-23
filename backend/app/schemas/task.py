from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    status: str = Field(default="TODO", pattern="^(TODO|IN_PROGRESS|DONE|ARCHIVED)$")
    due_date: Optional[datetime] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    status: Optional[str] = Field(None, pattern="^(TODO|IN_PROGRESS|DONE|ARCHIVED)$")
    due_date: Optional[datetime] = None


class TaskRead(TaskBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
