from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.approval import ApprovalStatus, compute_canonical_payload_hash


class ApprovalRequestCreate(BaseModel):
    """Schema for proposing an action requiring human approval."""
    action_type: str = Field(..., min_length=1, max_length=50)
    summary: str = Field(..., min_length=1, max_length=255)
    proposed_payload: Dict[str, Any] = Field(..., description="Action parameters dictionary")


class ApprovalDecisionRequest(BaseModel):
    """Schema for submitting an approval decision (approve or reject)."""
    comment: Optional[str] = Field(None, max_length=1000, description="Optional user review notes")


class ApprovalRequestRead(BaseModel):
    """Schema for reading an approval request with its audit trail."""
    id: str
    user_id: str
    action_type: str
    summary: str
    proposed_payload: Dict[str, Any]
    payload_hash: str
    status: ApprovalStatus
    user_comment: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    resolved_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalExecutionResult(BaseModel):
    """Result returned after an approved action is executed by the backend."""
    request_id: str
    action_type: str
    status: ApprovalStatus
    executed_at: Optional[datetime] = None
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
