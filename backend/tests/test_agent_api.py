import json
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.task import Task
from app.models.approval import ApprovalRequest
from app.core.security import create_access_token
from app.services.agent_service import agent_orchestrator


def create_mock_groq_response(content=None, tool_calls=None):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_choice.message.tool_calls = tool_calls

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage.prompt_tokens = 30
    mock_completion.usage.completion_tokens = 15
    mock_completion.usage.total_tokens = 45
    return mock_completion


def create_mock_tool_call(call_id, function_name, arguments_dict):
    mock_tc = MagicMock()
    mock_tc.id = call_id
    mock_tc.type = "function"
    mock_tc.function.name = function_name
    mock_tc.function.arguments = json.dumps(arguments_dict)
    return mock_tc


@pytest.mark.asyncio
async def test_authenticated_agent_chat(client: AsyncClient):
    """1. Test successful authenticated agent chat."""
    mock_resp = create_mock_groq_response(content="I am ready to help organize your week.")

    with patch.object(agent_orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        res = await client.post("/api/v1/agent/chat", json={"message": "Good morning!"})
        assert res.status_code == 200
        data = res.json()
        assert data["reply"] == "I am ready to help organize your week."
        assert data["conversation_id"] is not None


@pytest.mark.asyncio
async def test_unauthenticated_agent_chat_denial(unauth_client: AsyncClient):
    """2. Test unauthenticated request is denied with 401."""
    res = await unauth_client.post("/api/v1/agent/chat", json={"message": "Hello"})
    assert res.status_code == 401
    assert "Not authenticated" in res.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_token_denial(client: AsyncClient):
    """3. Test invalid Bearer token is rejected with 401."""
    res = await client.post(
        "/api/v1/agent/chat",
        json={"message": "Hello"},
        headers={"Authorization": "Bearer invalid.jwt.signature"},
    )
    assert res.status_code == 401
    assert "Invalid authentication token" in res.json()["detail"]


@pytest.mark.asyncio
async def test_conversation_continuity_api(client: AsyncClient):
    """4. Test multi-turn chat continuity across the HTTP API."""
    mock_resp1 = create_mock_groq_response(content="First reply.")
    mock_resp2 = create_mock_groq_response(content="Second reply with context.")

    with patch.object(agent_orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [mock_resp1, mock_resp2]
        mock_get_client.return_value = mock_client

        # Turn 1
        res1 = await client.post("/api/v1/agent/chat", json={"message": "Message 1"})
        assert res1.status_code == 200
        conv_id = res1.json()["conversation_id"]

        # Turn 2
        res2 = await client.post("/api/v1/agent/chat", json={"conversation_id": conv_id, "message": "Message 2"})
        assert res2.status_code == 200
        assert res2.json()["conversation_id"] == conv_id
        assert res2.json()["reply"] == "Second reply with context."


@pytest.mark.asyncio
async def test_tool_execution_through_http_api(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """5. Test tool execution (create_task) triggered through HTTP API."""
    tc = create_mock_tool_call(
        call_id="call_api_create",
        function_name="create_task",
        arguments_dict={"title": "Board Meeting Preparation", "priority": "HIGH"},
    )
    step1_resp = create_mock_groq_response(tool_calls=[tc])
    step2_resp = create_mock_groq_response(content="Board meeting prep task created.")

    with patch.object(agent_orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [step1_resp, step2_resp]
        mock_get_client.return_value = mock_client

        res = await client.post("/api/v1/agent/chat", json={"message": "Create task for board meeting"})
        assert res.status_code == 200
        data = res.json()
        assert len(data["tool_calls_executed"]) == 1
        assert data["tool_calls_executed"][0]["tool_name"] == "create_task"

        # Verify task created in database for test_user
        created_task_id = data["tool_calls_executed"][0]["result"]["task_id"]
        task = await db_session.get(Task, created_task_id)
        assert task is not None
        assert task.user_id == test_user.id
        assert task.title == "Board Meeting Preparation"


@pytest.mark.asyncio
async def test_guarded_action_creates_pending_approval_via_api(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """6. Test guarded tool execution creates pending approval and leaves task intact."""
    task = Task(user_id=test_user.id, title="Protected Task To Delete")
    db_session.add(task)
    await db_session.commit()

    tc = create_mock_tool_call(
        call_id="call_api_delete",
        function_name="delete_task",
        arguments_dict={"task_id": task.id},
    )
    step1_resp = create_mock_groq_response(tool_calls=[tc])
    step2_resp = create_mock_groq_response(content="I have prepared deletion approval.")

    with patch.object(agent_orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [step1_resp, step2_resp]
        mock_get_client.return_value = mock_client

        res = await client.post("/api/v1/agent/chat", json={"message": f"Delete task {task.id}"})
        assert res.status_code == 200
        data = res.json()
        assert data["pending_approval_id"] is not None

        # Verify approval is PENDING in DB
        approval = await db_session.get(ApprovalRequest, data["pending_approval_id"])
        assert approval is not None
        assert approval.status == "PENDING"
        assert approval.user_id == test_user.id

        # Verify task is NOT deleted from DB
        task_in_db = await db_session.get(Task, task.id)
        assert task_in_db is not None
