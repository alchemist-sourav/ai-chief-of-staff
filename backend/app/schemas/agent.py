from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ToolCallInfo(BaseModel):
    """Details of a tool call emitted by the LLM or executed by the agent."""
    tool_name: str
    arguments: Dict[str, Any]
    tool_call_id: Optional[str] = None
    requires_approval: bool = False
    result: Optional[Any] = None


class AgentStepLog(BaseModel):
    """Step-by-step diagnostic log of the agent's thought-action loop."""
    step: int
    action_type: str
    detail: str


class AgentChatRequest(BaseModel):
    """User request to the autonomous AI Chief of Staff agent."""
    message: str = Field(..., min_length=1, description="Command or inquiry for the agent")
    conversation_id: Optional[str] = Field(None, description="Optional thread ID to continue")
    include_memory: bool = Field(True, description="Whether to inject personal memory context")
    model: Optional[str] = Field(None, description="Optional model override")


class AgentChatResponse(BaseModel):
    """Response returned by the agent orchestration engine."""
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    model: str
    reply: str
    tool_calls_executed: List[ToolCallInfo] = Field(default_factory=list)
    pending_approval_id: Optional[str] = None
    execution_steps: List[AgentStepLog] = Field(default_factory=list)
    usage: Optional[Dict[str, Any]] = None
