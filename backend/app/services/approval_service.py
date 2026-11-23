import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalRequest, ApprovalStatus, compute_canonical_payload_hash
from app.models.task import Task
from app.schemas.approval import ApprovalExecutionResult
from app.services.task_service import TaskService

logger = logging.getLogger("ai_chief_of_staff.approval_service")

# Explicit whitelist of permitted action types
ALLOWED_ACTION_TYPES: Set[str] = {
    "DELETE_TASK",
    "PROPOSE_EXTERNAL_ACTION",
    "SEND_EMAIL",
    "SCHEDULE_EVENT",
    "EXTERNAL_API_CALL",
}


class ApprovalError(Exception):
    """Base exception for approval operations."""
    pass


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval request is not found or does not belong to the user."""
    pass


class InvalidStateTransitionError(ApprovalError):
    """Raised when an invalid state transition is attempted."""
    pass


class PayloadTamperedError(ApprovalError):
    """Raised when the stored payload does not match its cryptographic hash."""
    pass


class ApprovalService:
    """Service managing the secure lifecycle and execution of human-in-the-loop approvals."""

    @staticmethod
    async def create_request(
        session: AsyncSession,
        user_id: str,
        action_type: str,
        summary: str,
        proposed_payload: Dict[str, Any],
    ) -> ApprovalRequest:
        """Create a new PENDING approval request with canonical payload hashing."""
        action_type_clean = action_type.strip().upper()
        if action_type_clean not in ALLOWED_ACTION_TYPES:
            raise ApprovalError(f"Action type '{action_type_clean}' is not in the approved whitelist.")

        payload_hash = compute_canonical_payload_hash(proposed_payload)

        approval = ApprovalRequest(
            user_id=user_id,
            action_type=action_type_clean,
            summary=summary.strip(),
            proposed_payload=proposed_payload,
            payload_hash=payload_hash,
            status=ApprovalStatus.PENDING.value,
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)

        logger.info(f"Created approval request {approval.id} ({action_type_clean}) for user {user_id}")
        return approval

    @staticmethod
    async def get_request(
        session: AsyncSession,
        user_id: str,
        request_id: str,
    ) -> Optional[ApprovalRequest]:
        """Fetch approval request strictly isolated by user_id."""
        query = select(ApprovalRequest).where(
            and_(ApprovalRequest.id == request_id, ApprovalRequest.user_id == user_id)
        )
        result = await session.execute(query)
        return result.scalars().first()

    @staticmethod
    async def list_requests(
        session: AsyncSession,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ApprovalRequest]:
        """List approval requests for a user, optionally filtered by status."""
        filters = [ApprovalRequest.user_id == user_id]
        if status:
            filters.append(ApprovalRequest.status == status.upper())

        query = (
            select(ApprovalRequest)
            .where(and_(*filters))
            .order_by(ApprovalRequest.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def approve_request(
        session: AsyncSession,
        user_id: str,
        request_id: str,
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        """Transition request: PENDING -> APPROVED.
        
        Rejects invalid transitions and raises safe not-found if unauthorized.
        """
        approval = await ApprovalService.get_request(session, user_id, request_id)
        if not approval:
            raise ApprovalNotFoundError(f"Approval request '{request_id}' not found.")

        if approval.status != ApprovalStatus.PENDING.value:
            raise InvalidStateTransitionError(
                f"Cannot approve request '{request_id}' in '{approval.status}' status. Must be 'PENDING'."
            )

        approval.status = ApprovalStatus.APPROVED.value
        approval.resolved_at = datetime.now(timezone.utc)
        if comment:
            approval.user_comment = comment

        await session.commit()
        await session.refresh(approval)
        logger.info(f"Approval request {request_id} transitioned to APPROVED by user {user_id}")
        return approval

    @staticmethod
    async def reject_request(
        session: AsyncSession,
        user_id: str,
        request_id: str,
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        """Transition request: PENDING -> REJECTED."""
        approval = await ApprovalService.get_request(session, user_id, request_id)
        if not approval:
            raise ApprovalNotFoundError(f"Approval request '{request_id}' not found.")

        if approval.status != ApprovalStatus.PENDING.value:
            raise InvalidStateTransitionError(
                f"Cannot reject request '{request_id}' in '{approval.status}' status. Must be 'PENDING'."
            )

        approval.status = ApprovalStatus.REJECTED.value
        approval.resolved_at = datetime.now(timezone.utc)
        if comment:
            approval.user_comment = comment

        await session.commit()
        await session.refresh(approval)
        logger.info(f"Approval request {request_id} transitioned to REJECTED by user {user_id}")
        return approval

    @staticmethod
    async def execute_approved_action(
        session: AsyncSession,
        user_id: str,
        request_id: str,
    ) -> ApprovalExecutionResult:
        """Execute an approved action through the state machine: APPROVED -> EXECUTING -> EXECUTED (or FAILED).
        
        Guarantees:
        1. User ownership is enforced.
        2. Status must be APPROVED.
        3. Canonical payload hash is verified against stored hash before executing.
        4. State is locked to EXECUTING during execution to prevent race conditions.
        5. Handlers are strictly mapped from an explicit allowlist (no arbitrary code execution).
        6. If operation fails, state transitions to FAILED (never marked EXECUTED).
        """
        approval = await ApprovalService.get_request(session, user_id, request_id)
        if not approval:
            raise ApprovalNotFoundError(f"Approval request '{request_id}' not found.")

        # State transition validation
        if approval.status == ApprovalStatus.EXECUTED.value:
            raise InvalidStateTransitionError(f"Approval request '{request_id}' has already been executed.")
        elif approval.status == ApprovalStatus.REJECTED.value:
            raise InvalidStateTransitionError(f"Cannot execute rejected approval request '{request_id}'.")
        elif approval.status == ApprovalStatus.FAILED.value:
            raise InvalidStateTransitionError(f"Cannot execute failed approval request '{request_id}'.")
        elif approval.status == ApprovalStatus.EXECUTING.value:
            raise InvalidStateTransitionError(f"Approval request '{request_id}' is already executing.")
        elif approval.status != ApprovalStatus.APPROVED.value:
            raise InvalidStateTransitionError(
                f"Approval request '{request_id}' must be in 'APPROVED' status to execute (current: '{approval.status}')."
            )

        # 1. Cryptographic payload tamper verification
        computed_hash = compute_canonical_payload_hash(approval.proposed_payload)
        if computed_hash != approval.payload_hash:
            logger.critical(
                f"TAMPER DETECTED on approval {request_id}! "
                f"Expected hash {approval.payload_hash}, computed {computed_hash}"
            )
            approval.status = ApprovalStatus.FAILED.value
            approval.error_message = "Cryptographic tamper detected: proposed payload does not match original signature."
            approval.executed_at = datetime.now(timezone.utc)
            await session.commit()
            raise PayloadTamperedError(approval.error_message)

        # 2. Transition state: APPROVED -> EXECUTING
        approval.status = ApprovalStatus.EXECUTING.value
        await session.commit()
        await session.refresh(approval)

        # 3. Dispatch to explicit action handler
        try:
            if approval.action_type == "DELETE_TASK":
                result = await ApprovalService._handle_delete_task(session, user_id, approval)
            elif approval.action_type in ["PROPOSE_EXTERNAL_ACTION", "SEND_EMAIL", "SCHEDULE_EVENT", "EXTERNAL_API_CALL"]:
                result = await ApprovalService._handle_external_action(session, user_id, approval)
            else:
                raise ApprovalError(f"Unsupported action type: {approval.action_type}")

            # 4. Success transition: EXECUTING -> EXECUTED
            approval.status = ApprovalStatus.EXECUTED.value
            approval.executed_at = datetime.now(timezone.utc)
            approval.execution_result = result
            approval.error_message = None
            await session.commit()
            await session.refresh(approval)

            logger.info(f"Approval request {request_id} executed successfully.")
            return ApprovalExecutionResult(
                request_id=approval.id,
                action_type=approval.action_type,
                status=ApprovalStatus.EXECUTED,
                executed_at=approval.executed_at,
                result_data=result,
            )

        except Exception as e:
            # 5. Failure transition: EXECUTING -> FAILED
            logger.error(f"Execution failed for approval request {request_id}: {e}")
            approval.status = ApprovalStatus.FAILED.value
            approval.executed_at = datetime.now(timezone.utc)
            approval.error_message = str(e)
            approval.execution_result = {"error": str(e)}
            await session.commit()
            await session.refresh(approval)

            return ApprovalExecutionResult(
                request_id=approval.id,
                action_type=approval.action_type,
                status=ApprovalStatus.FAILED,
                executed_at=approval.executed_at,
                error_message=str(e),
            )

    @staticmethod
    async def _handle_delete_task(
        session: AsyncSession,
        user_id: str,
        approval: ApprovalRequest,
    ) -> Dict[str, Any]:
        """Guarded handler for DELETE_TASK."""
        task_id = approval.proposed_payload.get("task_id")
        if not task_id:
            raise ValueError("Approval payload missing required 'task_id'.")

        task = await TaskService.get_task_by_id(session, user_id, task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found or does not belong to you.")

        task_title = task.title
        deleted = await TaskService.delete_task(session, user_id, task_id)
        if not deleted:
            raise RuntimeError(f"Failed to delete task '{task_id}'.")

        return {
            "deleted_task_id": task_id,
            "title": task_title,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    async def _handle_external_action(
        session: AsyncSession,
        user_id: str,
        approval: ApprovalRequest,
    ) -> Dict[str, Any]:
        """Guarded handler for external action proposals.
        
        Records authorization without performing live external network side-effects.
        """
        return {
            "authorized": True,
            "action_type": approval.action_type,
            "summary": approval.summary,
            "external_integration": "deferred_milestone_3",
            "message": "Action proposal approved and authorized. Live external integration is deferred to Milestone 3.",
            "authorized_at": datetime.now(timezone.utc).isoformat(),
        }
