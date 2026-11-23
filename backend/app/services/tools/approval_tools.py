import logging
from typing import Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalRequest, ApprovalStatus, compute_canonical_payload_hash
from app.services.tools.base import BaseTool, ToolResult, ToolSecurityLevel

logger = logging.getLogger("ai_chief_of_staff.tools.approval")


class ProposeExternalActionArgs(BaseModel):
    action_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Action type, e.g. SEND_EMAIL, SCHEDULE_EVENT, EXTERNAL_API_CALL",
    )
    summary: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Clear executive summary of the proposed action",
    )
    payload: Dict[str, Any] = Field(
        ...,
        description="Structured payload containing all arguments required to execute the action",
    )


class ProposeExternalActionTool(BaseTool):
    name = "propose_external_action"
    description = (
        "Propose an external or sensitive action (e.g. drafting an email to send, proposing a calendar invite, "
        "or triggering a third-party service). Does not execute immediately; creates a PENDING approval request "
        "for user authorization."
    )
    security_level = ToolSecurityLevel.GUARDED
    args_schema = ProposeExternalActionArgs

    async def execute(self, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
        action_type = kwargs["action_type"].upper().strip()
        summary = kwargs["summary"].strip()
        payload = kwargs["payload"]

        # Canonicalize proposed action payload
        canonical_payload = {
            "action_type": action_type,
            "summary": summary,
            "parameters": payload,
        }
        payload_hash = compute_canonical_payload_hash(canonical_payload)

        # Store PENDING ApprovalRequest (No external side effect executed)
        approval = ApprovalRequest(
            user_id=user_id,
            action_type=action_type,
            summary=summary,
            proposed_payload=canonical_payload,
            payload_hash=payload_hash,
            status=ApprovalStatus.PENDING.value,
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)

        logger.info(f"Created pending external action proposal {approval.id} ({action_type}) for user {user_id}")

        return ToolResult(
            success=True,
            message=f"Action proposal created: '{summary}'. Approval Request #{approval.id} is pending your authorization.",
            requires_approval=True,
            approval_id=approval.id,
            data={
                "approval_id": approval.id,
                "action_type": action_type,
                "summary": summary,
                "status": "PENDING",
            },
        )
