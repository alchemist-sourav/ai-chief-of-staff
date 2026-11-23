import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import ValidationError

from app.models.user import User
from app.models.approval import ApprovalRequest, ApprovalStatus, compute_canonical_payload_hash
from app.schemas.approval import (
    ApprovalRequestCreate,
    ApprovalRequestRead,
    ApprovalDecisionRequest,
)
from app.schemas.agent import (
    ToolCallInfo,
    AgentChatRequest,
    AgentChatResponse,
)


def test_approval_status_definitions():
    """Verify all 6 required lifecycle states are defined in ApprovalStatus."""
    expected_statuses = {"PENDING", "APPROVED", "EXECUTING", "EXECUTED", "REJECTED", "FAILED"}
    actual_statuses = {status.value for status in ApprovalStatus}
    assert actual_statuses == expected_statuses, f"Expected {expected_statuses}, got {actual_statuses}"


def test_canonical_payload_hashing_consistency():
    """Verify that payload hashing is deterministic and key-order independent."""
    payload_a = {"title": "Delete Roadmap Task", "task_id": "task_123", "force": True}
    payload_b = {"force": True, "task_id": "task_123", "title": "Delete Roadmap Task"}

    hash_a = compute_canonical_payload_hash(payload_a)
    hash_b = compute_canonical_payload_hash(payload_b)

    assert len(hash_a) == 64, "SHA-256 hash must be 64 hexadecimal characters"
    assert hash_a == hash_b, "Hashes must be identical regardless of dictionary key order"

    # Test nested dictionary key order independence
    nested_a = {"action": "SEND_EMAIL", "details": {"to": "alice@corp.com", "subject": "Hello"}}
    nested_b = {"details": {"subject": "Hello", "to": "alice@corp.com"}, "action": "SEND_EMAIL"}
    assert compute_canonical_payload_hash(nested_a) == compute_canonical_payload_hash(nested_b)

    # Different payload must produce a different hash
    different_payload = {"title": "Delete Different Task", "task_id": "task_999"}
    assert compute_canonical_payload_hash(different_payload) != hash_a


@pytest.mark.asyncio
async def test_approval_request_model_and_relationships(db_session: AsyncSession, test_user: User):
    """Test ApprovalRequest creation, default status, foreign key, and cascade deletion."""
    payload = {"task_id": "task_xyz", "action": "DELETE_TASK"}
    payload_hash = compute_canonical_payload_hash(payload)

    approval = ApprovalRequest(
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="Delete task: Finish pitch deck",
        proposed_payload=payload,
        payload_hash=payload_hash,
        status=ApprovalStatus.PENDING.value,
    )
    db_session.add(approval)
    await db_session.commit()
    await db_session.refresh(approval)

    assert approval.id is not None
    assert approval.user_id == test_user.id
    assert approval.status == ApprovalStatus.PENDING.value
    assert approval.payload_hash == payload_hash
    assert approval.created_at is not None

    # Test querying approval by user_id
    query = select(ApprovalRequest).where(ApprovalRequest.user_id == test_user.id)
    result = await db_session.execute(query)
    user_approvals = list(result.scalars().all())
    assert len(user_approvals) == 1
    assert user_approvals[0].id == approval.id

    # Test status transitions
    approval.status = ApprovalStatus.APPROVED.value
    approval.resolved_at = datetime.now(timezone.utc)
    approval.user_comment = "Confirmed by user in UI"
    await db_session.commit()
    await db_session.refresh(approval)
    assert approval.status == "APPROVED"
    assert approval.user_comment == "Confirmed by user in UI"

    # Test cascade deletion when user is deleted
    await db_session.delete(test_user)
    await db_session.commit()

    check_query = select(ApprovalRequest).where(ApprovalRequest.id == approval.id)
    check_res = await db_session.execute(check_query)
    assert check_res.scalars().first() is None, "ApprovalRequest must be cascade deleted with User"


def test_approval_schema_validation():
    """Test Pydantic validation on approval schemas."""
    # Valid creation schema
    create_schema = ApprovalRequestCreate(
        action_type="SCHEDULE_EVENT",
        summary="Schedule meeting with investor",
        proposed_payload={"time": "2026-11-23T10:00:00Z", "attendees": ["test@example.com"]},
    )
    assert create_schema.action_type == "SCHEDULE_EVENT"

    # Read schema validation from model-like dictionary
    read_dict = {
        "id": "appr_123",
        "user_id": "usr_456",
        "action_type": "DELETE_TASK",
        "summary": "Delete old task",
        "proposed_payload": {"task_id": "123"},
        "payload_hash": "a" * 64,
        "status": "PENDING",
        "user_comment": None,
        "execution_result": None,
        "error_message": None,
        "resolved_at": None,
        "executed_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    read_schema = ApprovalRequestRead.model_validate(read_dict)
    assert read_schema.status == ApprovalStatus.PENDING

    # Invalid status should raise ValidationError
    invalid_dict = read_dict.copy()
    invalid_dict["status"] = "INVALID_STATUS_VALUE"
    with pytest.raises(ValidationError):
        ApprovalRequestRead.model_validate(invalid_dict)


def test_agent_schema_validation():
    """Test agent-related Pydantic schema validation."""
    tool_info = ToolCallInfo(
        tool_name="delete_task",
        arguments={"task_id": "task_abc"},
        requires_approval=True,
    )
    assert tool_info.requires_approval is True

    agent_resp = AgentChatResponse(
        conversation_id="conv_123",
        user_message_id="msg_1",
        assistant_message_id="msg_2",
        model="openai/gpt-oss-120b",
        reply="I have prepared this deletion for your approval.",
        tool_calls_executed=[tool_info],
        pending_approval_id="appr_999",
    )
    assert agent_resp.pending_approval_id == "appr_999"
    assert len(agent_resp.tool_calls_executed) == 1
