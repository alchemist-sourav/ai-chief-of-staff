import pytest
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.task import Task
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.services.approval_service import (
    ApprovalService,
    ApprovalError,
    ApprovalNotFoundError,
    InvalidStateTransitionError,
    PayloadTamperedError,
)
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_create_request(db_session: AsyncSession, test_user: User):
    """1. Test approval request creation with canonical payload hashing."""
    payload = {"task_id": "test_task_1", "action": "delete"}
    request = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="Delete task 1",
        proposed_payload=payload,
    )

    assert request.id is not None
    assert request.user_id == test_user.id
    assert request.status == ApprovalStatus.PENDING.value
    assert len(request.payload_hash) == 64
    assert request.action_type == "DELETE_TASK"


@pytest.mark.asyncio
async def test_successful_deletion_after_approval(db_session: AsyncSession, test_user: User):
    """2. Test full lifecycle: PENDING -> APPROVED -> EXECUTING -> EXECUTED with task deletion."""
    # Create task
    task = Task(user_id=test_user.id, title="Task to be deleted after approval")
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    # Create approval request
    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary=f"Delete task: {task.title}",
        proposed_payload={"task_id": task.id, "title": task.title},
    )

    # Approve request
    approved_req = await ApprovalService.approve_request(
        session=db_session,
        user_id=test_user.id,
        request_id=req.id,
        comment="Authorized by executive user",
    )
    assert approved_req.status == ApprovalStatus.APPROVED.value
    assert approved_req.user_comment == "Authorized by executive user"
    assert approved_req.resolved_at is not None

    # Execute approved action
    exec_result = await ApprovalService.execute_approved_action(
        session=db_session,
        user_id=test_user.id,
        request_id=req.id,
    )
    assert exec_result.status == ApprovalStatus.EXECUTED
    assert exec_result.result_data["deleted_task_id"] == task.id

    # Verify task was actually deleted from database
    task_check = await TaskService.get_task_by_id(session=db_session, user_id=test_user.id, task_id=task.id)
    assert task_check is None, "Task must be deleted after approval execution"


@pytest.mark.asyncio
async def test_rejection_without_execution(db_session: AsyncSession, test_user: User):
    """3. Test rejection lifecycle and ensure task remains untouched."""
    task = Task(user_id=test_user.id, title="Do not delete this task")
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary=f"Delete task: {task.title}",
        proposed_payload={"task_id": task.id},
    )

    # Reject request
    rejected = await ApprovalService.reject_request(
        session=db_session,
        user_id=test_user.id,
        request_id=req.id,
        comment="Rejected: task is still active.",
    )
    assert rejected.status == ApprovalStatus.REJECTED.value
    assert rejected.user_comment == "Rejected: task is still active."

    # Verify task still exists in DB
    task_in_db = await TaskService.get_task_by_id(session=db_session, user_id=test_user.id, task_id=task.id)
    assert task_in_db is not None, "Task must NOT be deleted when rejected"

    # Verify execution fails on rejected request
    with pytest.raises(InvalidStateTransitionError):
        await ApprovalService.execute_approved_action(
            session=db_session,
            user_id=test_user.id,
            request_id=req.id,
        )


@pytest.mark.asyncio
async def test_payload_tampering_detection(db_session: AsyncSession, test_user: User):
    """4. Test cryptographic verification catches and blocks tampered payloads."""
    task_real = Task(user_id=test_user.id, title="Legitimate Task")
    task_victim = Task(user_id=test_user.id, title="Victim Task")
    db_session.add_all([task_real, task_victim])
    await db_session.commit()

    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="Delete legitimate task",
        proposed_payload={"task_id": task_real.id},
    )

    # Approve request legitimately
    await ApprovalService.approve_request(session=db_session, user_id=test_user.id, request_id=req.id)

    # Malicious actor or bug mutates proposed_payload in DB without updating payload_hash
    req.proposed_payload = {"task_id": task_victim.id}
    await db_session.commit()

    # Execution must detect hash mismatch, reject execution, and mark FAILED
    with pytest.raises(PayloadTamperedError):
        await ApprovalService.execute_approved_action(
            session=db_session,
            user_id=test_user.id,
            request_id=req.id,
        )

    # Refresh approval from DB
    await db_session.refresh(req)
    assert req.status == ApprovalStatus.FAILED.value
    assert "tamper" in req.error_message.lower()

    # Verify victim task was NOT deleted
    victim_check = await TaskService.get_task_by_id(session=db_session, user_id=test_user.id, task_id=task_victim.id)
    assert victim_check is not None, "Tampered execution must NOT delete victim task"


@pytest.mark.asyncio
async def test_cross_user_approval_denial(db_session: AsyncSession, test_user: User):
    """5. Test tenant isolation: User B cannot view, approve, reject, or execute User A's requests."""
    user_b = User(id="user-b-uuid-88888", email="user_b_isolation@homingo.ai", full_name="User B")
    db_session.add(user_b)
    await db_session.commit()

    # User A creates request
    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="User A private task",
        proposed_payload={"task_id": "abc"},
    )

    # User B attempts to access User A's request
    assert await ApprovalService.get_request(db_session, user_id=user_b.id, request_id=req.id) is None

    with pytest.raises(ApprovalNotFoundError):
        await ApprovalService.approve_request(db_session, user_id=user_b.id, request_id=req.id)

    with pytest.raises(ApprovalNotFoundError):
        await ApprovalService.reject_request(db_session, user_id=user_b.id, request_id=req.id)

    with pytest.raises(ApprovalNotFoundError):
        await ApprovalService.execute_approved_action(db_session, user_id=user_b.id, request_id=req.id)


@pytest.mark.asyncio
async def test_duplicate_approval_prevention(db_session: AsyncSession, test_user: User):
    """6. Test that approving an already approved request raises InvalidStateTransitionError."""
    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="PROPOSE_EXTERNAL_ACTION",
        summary="Propose action",
        proposed_payload={"test": 1},
    )

    # First approval succeeds
    await ApprovalService.approve_request(db_session, user_id=test_user.id, request_id=req.id)

    # Second approval attempt must raise error
    with pytest.raises(InvalidStateTransitionError):
        await ApprovalService.approve_request(db_session, user_id=test_user.id, request_id=req.id)


@pytest.mark.asyncio
async def test_double_execution_prevention(db_session: AsyncSession, test_user: User):
    """7. Test that executing an already executed request is rejected."""
    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="PROPOSE_EXTERNAL_ACTION",
        summary="Action proposal",
        proposed_payload={"action": "test"},
    )
    await ApprovalService.approve_request(db_session, user_id=test_user.id, request_id=req.id)
    await ApprovalService.execute_approved_action(db_session, user_id=test_user.id, request_id=req.id)

    # Double execution must be blocked
    with pytest.raises(InvalidStateTransitionError):
        await ApprovalService.execute_approved_action(db_session, user_id=test_user.id, request_id=req.id)


@pytest.mark.asyncio
async def test_invalid_state_transition_rejection(db_session: AsyncSession, test_user: User):
    """8. Test rejection of illegal transitions (e.g. executing PENDING, approving REJECTED)."""
    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="PROPOSE_EXTERNAL_ACTION",
        summary="Test action",
        proposed_payload={"test": 123},
    )

    # Cannot execute while PENDING
    with pytest.raises(InvalidStateTransitionError):
        await ApprovalService.execute_approved_action(db_session, user_id=test_user.id, request_id=req.id)

    # Reject request
    await ApprovalService.reject_request(db_session, user_id=test_user.id, request_id=req.id)

    # Cannot approve once REJECTED
    with pytest.raises(InvalidStateTransitionError):
        await ApprovalService.approve_request(db_session, user_id=test_user.id, request_id=req.id)


@pytest.mark.asyncio
async def test_missing_task_handling(db_session: AsyncSession, test_user: User):
    """9. Test handling when target task is deleted out-of-band before approval execution."""
    task = Task(user_id=test_user.id, title="Temporary Task")
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary=f"Delete {task.title}",
        proposed_payload={"task_id": task.id},
    )

    # Approve request
    await ApprovalService.approve_request(db_session, user_id=test_user.id, request_id=req.id)

    # Task is deleted out-of-band directly
    await db_session.delete(task)
    await db_session.commit()

    # Execution should fail gracefully and mark status FAILED (never EXECUTED)
    res = await ApprovalService.execute_approved_action(db_session, user_id=test_user.id, request_id=req.id)
    assert res.status == ApprovalStatus.FAILED
    assert "not found" in res.error_message.lower()

    await db_session.refresh(req)
    assert req.status == ApprovalStatus.FAILED.value


@pytest.mark.asyncio
async def test_external_action_remains_unexecuted(db_session: AsyncSession, test_user: User):
    """10. Test external action records authorization without executing external integrations."""
    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="PROPOSE_EXTERNAL_ACTION",
        summary="Send executive summary email to investors",
        proposed_payload={"to": "investors@vc.com", "subject": "Q4 Summary"},
    )
    await ApprovalService.approve_request(db_session, user_id=test_user.id, request_id=req.id)

    exec_result = await ApprovalService.execute_approved_action(db_session, user_id=test_user.id, request_id=req.id)
    assert exec_result.status == ApprovalStatus.EXECUTED
    assert exec_result.result_data["external_integration"] == "deferred_milestone_3"
    assert "deferred to Milestone 3" in exec_result.result_data["message"]


@pytest.mark.asyncio
async def test_execution_failure_handling(db_session: AsyncSession, test_user: User):
    """11. Test that unexpected handler exceptions transition state to FAILED."""
    task = Task(user_id=test_user.id, title="Failing Task")
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    req = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="Delete with simulated failure",
        proposed_payload={"task_id": task.id},
    )
    await ApprovalService.approve_request(db_session, user_id=test_user.id, request_id=req.id)

    # Mock TaskService.delete_task to raise an unexpected database exception
    with patch.object(TaskService, "delete_task", side_effect=RuntimeError("Database lock timeout")):
        result = await ApprovalService.execute_approved_action(db_session, user_id=test_user.id, request_id=req.id)
        assert result.status == ApprovalStatus.FAILED
        assert "Database lock timeout" in result.error_message

    await db_session.refresh(req)
    assert req.status == ApprovalStatus.FAILED.value
    assert req.error_message == "Database lock timeout"
