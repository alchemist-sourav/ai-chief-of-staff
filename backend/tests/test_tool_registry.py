import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.task import Task
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.memory import UserMemory
from app.services.tools import (
    default_registry,
    ToolRegistry,
    ToolSecurityLevel,
    CreateTaskTool,
)


def test_tool_registration_and_lookup():
    """Verify tool registration, lookup, security classification, and schema export."""
    expected_tools = {
        "create_task": ToolSecurityLevel.SAFE,
        "list_tasks": ToolSecurityLevel.SAFE,
        "update_task": ToolSecurityLevel.SAFE,
        "save_memory": ToolSecurityLevel.SAFE,
        "retrieve_memory": ToolSecurityLevel.SAFE,
        "delete_task": ToolSecurityLevel.GUARDED,
        "propose_external_action": ToolSecurityLevel.GUARDED,
    }

    registered_names = set(default_registry.get_tool_names())
    assert set(expected_tools.keys()).issubset(registered_names)

    for name, expected_level in expected_tools.items():
        tool = default_registry.get(name)
        assert tool is not None, f"Tool '{name}' must be registered"
        assert tool.security_level == expected_level, f"Tool '{name}' security level mismatch"

    # Verify OpenAI / Groq function calling schema generation
    schemas = default_registry.get_openai_schemas()
    assert len(schemas) >= 7
    for s in schemas:
        assert s["type"] == "function"
        assert "name" in s["function"]
        assert "description" in s["function"]
        assert "parameters" in s["function"]
        assert s["function"]["parameters"]["type"] == "object"


@pytest.mark.asyncio
async def test_safe_task_tools_execution(db_session: AsyncSession, test_user: User):
    """Verify create_task, list_tasks, and update_task safe execution."""
    # 1. create_task
    create_res = await default_registry.dispatch(
        session=db_session,
        user_id=test_user.id,
        tool_name="create_task",
        arguments={"title": "Prepare Financial Model", "priority": "HIGH", "description": "Q3 Revenue projections"},
    )
    assert create_res.success is True
    assert create_res.requires_approval is False
    task_id = create_res.data["task_id"]
    assert create_res.data["title"] == "Prepare Financial Model"

    # Verify task exists in DB
    db_task = await db_session.get(Task, task_id)
    assert db_task is not None
    assert db_task.user_id == test_user.id
    assert db_task.priority == "HIGH"

    # 2. list_tasks
    list_res = await default_registry.dispatch(
        session=db_session,
        user_id=test_user.id,
        tool_name="list_tasks",
        arguments={"priority": "HIGH"},
    )
    assert list_res.success is True
    assert list_res.data["count"] >= 1
    assert any(t["id"] == task_id for t in list_res.data["tasks"])

    # 3. update_task
    update_res = await default_registry.dispatch(
        session=db_session,
        user_id=test_user.id,
        tool_name="update_task",
        arguments={"task_id": task_id, "status": "IN_PROGRESS", "priority": "URGENT"},
    )
    assert update_res.success is True
    assert update_res.data["status"] == "IN_PROGRESS"
    assert update_res.data["priority"] == "URGENT"

    await db_session.refresh(db_task)
    assert db_task.status == "IN_PROGRESS"
    assert db_task.priority == "URGENT"


@pytest.mark.asyncio
async def test_safe_memory_tools_execution(db_session: AsyncSession, test_user: User):
    """Verify save_memory and retrieve_memory safe execution."""
    # 1. save_memory
    save_res = await default_registry.dispatch(
        session=db_session,
        user_id=test_user.id,
        tool_name="save_memory",
        arguments={
            "category": "WORK_STYLE",
            "key": "meeting_cadence",
            "value": "Weekly 1-on-1s on Tuesdays at 10 AM",
        },
    )
    assert save_res.success is True
    assert save_res.requires_approval is False
    assert save_res.data["key"] == "meeting_cadence"

    # 2. retrieve_memory
    retrieve_res = await default_registry.dispatch(
        session=db_session,
        user_id=test_user.id,
        tool_name="retrieve_memory",
        arguments={"query": "When are my 1-on-1 meetings?"},
    )
    assert retrieve_res.success is True
    assert retrieve_res.data["count"] >= 1
    found = any(m["key"] == "meeting_cadence" for m in retrieve_res.data["memories"])
    assert found is True


@pytest.mark.asyncio
async def test_guarded_delete_task_tool(db_session: AsyncSession, test_user: User):
    """Verify delete_task creates PENDING approval and DOES NOT delete the task."""
    # Create task first
    task = Task(user_id=test_user.id, title="Critical Milestone Task", priority="URGENT")
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    # Call guarded delete_task tool
    del_res = await default_registry.dispatch(
        session=db_session,
        user_id=test_user.id,
        tool_name="delete_task",
        arguments={"task_id": task.id, "reason": "No longer needed for sprint"},
    )

    # 1. Must flag approval requirement
    assert del_res.success is True
    assert del_res.requires_approval is True
    assert del_res.approval_id is not None
    approval_id = del_res.approval_id

    # 2. Verify ApprovalRequest was created in DB with PENDING status
    approval = await db_session.get(ApprovalRequest, approval_id)
    assert approval is not None
    assert approval.user_id == test_user.id
    assert approval.action_type == "DELETE_TASK"
    assert approval.status == ApprovalStatus.PENDING.value
    assert approval.proposed_payload["task_id"] == task.id

    # 3. CRITICAL: Verify task was NOT deleted
    task_in_db = await db_session.get(Task, task.id)
    assert task_in_db is not None, "Task must remain in database until approval is granted"
    assert task_in_db.id == task.id


@pytest.mark.asyncio
async def test_guarded_propose_external_action_tool(db_session: AsyncSession, test_user: User):
    """Verify propose_external_action creates PENDING approval record without side effects."""
    action_args = {
        "action_type": "SEND_EMAIL",
        "summary": "Send monthly investor update to syndicate",
        "payload": {
            "to": "investors@syndicate.vc",
            "subject": "November 2026 Monthly Update",
            "body": "Revenue up 25% MoM.",
        },
    }

    prop_res = await default_registry.dispatch(
        session=db_session,
        user_id=test_user.id,
        tool_name="propose_external_action",
        arguments=action_args,
    )

    assert prop_res.success is True
    assert prop_res.requires_approval is True
    assert prop_res.approval_id is not None

    approval = await db_session.get(ApprovalRequest, prop_res.approval_id)
    assert approval is not None
    assert approval.user_id == test_user.id
    assert approval.action_type == "SEND_EMAIL"
    assert approval.status == ApprovalStatus.PENDING.value
    assert approval.proposed_payload["summary"] == "Send monthly investor update to syndicate"


@pytest.mark.asyncio
async def test_invalid_arguments_rejection(db_session: AsyncSession, test_user: User):
    """Verify registry catches and rejects invalid or malformed arguments via Pydantic."""
    # Missing required field 'title'
    res1 = await default_registry.dispatch(
        session=db_session,
        user_id=test_user.id,
        tool_name="create_task",
        arguments={"description": "Missing title"},
    )
    assert res1.success is False
    assert res1.error == "INVALID_ARGUMENTS"

    # Invalid enum value for priority
    res2 = await default_registry.dispatch(
        session=db_session,
        user_id=test_user.id,
        tool_name="create_task",
        arguments={"title": "Test", "priority": "NOT_A_VALID_PRIORITY"},
    )
    assert res2.success is False
    assert res2.error == "INVALID_ARGUMENTS"


@pytest.mark.asyncio
async def test_unknown_tool_rejection(db_session: AsyncSession, test_user: User):
    """Verify registry rejects unregistered or malicious tool calls."""
    malicious_tools = ["exec_command", "eval_python", "drop_tables", "read_env"]
    for bad_tool in malicious_tools:
        res = await default_registry.dispatch(
            session=db_session,
            user_id=test_user.id,
            tool_name=bad_tool,
            arguments={"cmd": "whoami"},
        )
        assert res.success is False
        assert res.error == "UNKNOWN_TOOL"
        assert "not recognized" in res.message


@pytest.mark.asyncio
async def test_user_ownership_isolation(db_session: AsyncSession, test_user: User):
    """Verify tools enforce user data isolation and prevent cross-tenant access."""
    # Create another user (User B)
    other_user = User(
        id="user-b-uuid-99999",
        email="user_b@homingo.ai",
        full_name="Bob User",
        is_active=True,
    )
    db_session.add(other_user)

    # Create task belonging to User A (test_user)
    task_a = Task(user_id=test_user.id, title="User A Confidential Strategy")
    db_session.add(task_a)
    await db_session.commit()

    # User B attempts to update User A's task -> must fail with TASK_NOT_FOUND
    upd_res = await default_registry.dispatch(
        session=db_session,
        user_id=other_user.id,
        tool_name="update_task",
        arguments={"task_id": task_a.id, "title": "Compromised by User B"},
    )
    assert upd_res.success is False
    assert upd_res.error == "TASK_NOT_FOUND"

    # User B attempts to delete User A's task -> must fail with TASK_NOT_FOUND
    del_res = await default_registry.dispatch(
        session=db_session,
        user_id=other_user.id,
        tool_name="delete_task",
        arguments={"task_id": task_a.id},
    )
    assert del_res.success is False
    assert del_res.error == "TASK_NOT_FOUND"

    # Verify no approval request was created
    appr_query = select(ApprovalRequest).where(ApprovalRequest.user_id == other_user.id)
    appr_res = await db_session.execute(appr_query)
    assert len(list(appr_res.scalars().all())) == 0

    # Verify User A's task was untouched
    await db_session.refresh(task_a)
    assert task_a.title == "User A Confidential Strategy"
