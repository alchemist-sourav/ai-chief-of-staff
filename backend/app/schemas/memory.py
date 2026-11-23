from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class UserMemoryBase(BaseModel):
    category: str = Field(default="PREFERENCE", pattern="^(PREFERENCE|FACT|WORK_STYLE|CONTACT)$")
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1)
    metadata_json: Optional[Dict[str, Any]] = None
    is_active: bool = True


class UserMemoryCreate(UserMemoryBase):
    pass


class UserMemoryUpdate(BaseModel):
    category: Optional[str] = Field(None, pattern="^(PREFERENCE|FACT|WORK_STYLE|CONTACT)$")
    key: Optional[str] = Field(None, min_length=1, max_length=100)
    value: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class UserMemoryRead(UserMemoryBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
