from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message to the Chief of Staff")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID to append to, or creates a new one if None")
    include_memory: bool = Field(True, description="Whether to inject relevant user memories into the agent context")
    model: Optional[str] = Field(None, description="Optional Groq model override")


class AIChatResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    model: str
    reply: str
    memories_used: List[str] = Field(default_factory=list)
    usage: Optional[Dict[str, Any]] = None


# Kept for backward compatibility with /api/ai/test
class AITestRequest(BaseModel):
    message: str = Field(
        default="Introduce yourself concisely as my AI Chief of Staff.",
        min_length=1,
    )
    model: Optional[str] = None
    system_prompt: Optional[str] = "You are an elite, proactive AI Chief of Staff. Answer concisely and professionally."
    max_tokens: Optional[int] = 250


class AITestResponse(BaseModel):
    status: str
    model: str
    prompt: str
    response: str
    usage: Optional[Dict[str, Any]] = None
