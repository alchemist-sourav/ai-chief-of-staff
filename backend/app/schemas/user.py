from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class UserCreate(UserBase):
    password: Optional[str] = None


class UserRead(UserBase):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
