from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.approval import (
    ApprovalRequestRead,
    ApprovalDecisionRequest,
    ApprovalExecutionResult,
)
from app.services.approval_service import (
    ApprovalService,
    ApprovalNotFoundError,
    InvalidStateTransitionError,
    PayloadTamperedError,
)

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.get(
    "",
    response_model=List[ApprovalRequestRead],
    summary="List Approval Requests",
    description="Retrieve all approval requests for the authenticated user, optionally filtered by status.",
)
async def list_approvals(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status, e.g. PENDING, APPROVED, EXECUTED"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List approval requests for current user with tenant isolation."""
    return await ApprovalService.list_requests(
        session=session,
        user_id=current_user.id,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/{approval_id}",
    response_model=ApprovalRequestRead,
    summary="Get Approval Request",
    description="Retrieve details of a specific approval request.",
    responses={
        404: {"description": "Approval request not found or unauthorized."},
    },
)
async def get_approval(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get single approval request enforcing user ownership."""
    approval = await ApprovalService.get_request(
        session=session,
        user_id=current_user.id,
        request_id=approval_id,
    )
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        )
    return approval


@router.post(
    "/{approval_id}/approve",
    response_model=ApprovalExecutionResult,
    summary="Approve and Execute Action",
    description="Authorize and execute a pending approval request. Enforces cryptographic hash verification and atomic state transition.",
    responses={
        200: {"description": "Action authorized and executed successfully."},
        400: {"description": "Invalid state transition or execution failed."},
        404: {"description": "Approval request not found."},
        409: {"description": "Payload tamper detected."},
    },
)
async def approve_and_execute_approval(
    approval_id: str,
    decision: Optional[ApprovalDecisionRequest] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Authorize and execute a pending approval request."""
    comment = decision.comment if decision else None
    try:
        # 1. State transition: PENDING -> APPROVED
        await ApprovalService.approve_request(
            session=session,
            user_id=current_user.id,
            request_id=approval_id,
            comment=comment,
        )
        # 2. State transition & Execution: APPROVED -> EXECUTING -> EXECUTED
        result = await ApprovalService.execute_approved_action(
            session=session,
            user_id=current_user.id,
            request_id=approval_id,
        )
        if result.status.value == "FAILED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Action execution failed: {result.error_message}",
            )
        return result

    except ApprovalNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except PayloadTamperedError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while approving the action.",
        )


@router.post(
    "/{approval_id}/reject",
    response_model=ApprovalRequestRead,
    summary="Reject Approval Request",
    description="Reject a pending approval request without executing the proposed action.",
    responses={
        200: {"description": "Approval request rejected."},
        400: {"description": "Invalid state transition."},
        404: {"description": "Approval request not found."},
    },
)
async def reject_approval(
    approval_id: str,
    decision: Optional[ApprovalDecisionRequest] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Reject a pending approval request."""
    comment = decision.comment if decision else None
    try:
        return await ApprovalService.reject_request(
            session=session,
            user_id=current_user.id,
            request_id=approval_id,
            comment=comment,
        )
    except ApprovalNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while rejecting the action.",
        )
