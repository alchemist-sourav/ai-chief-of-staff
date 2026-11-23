from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class MessageRead(BaseModel):
    id: str
    conversation_id: str
    sender_role: str
    content: str
    model: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    title: Optional[str] = "Executive Session"


class ConversationRead(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: Optional[List[MessageRead]] = None

    model_config = ConfigDict(from_attributes=True)
