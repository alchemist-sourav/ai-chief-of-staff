from typing import Optional, Any
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    database_connected: bool
    groq_configured: bool
    default_model: str


class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
