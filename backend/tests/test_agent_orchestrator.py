import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from groq import RateLimitError

from app.models.user import User
from app.models.task import Task
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.schemas.agent import AgentChatRequest
from app.services.agent_service import AgentOrchestrator
from app.services.memory_service import MemoryService
from app.services.conversation_service import ConversationService
from app.services.task_service import TaskService


def create_mock_groq_response(content=None, tool_calls=None, prompt_tokens=20, completion_tokens=10):
    """Helper to generate a mock Groq ChatCompletion structure."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_choice.message.tool_calls = tool_calls

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage.prompt_tokens = prompt_tokens
    mock_completion.usage.completion_tokens = completion_tokens
    mock_completion.usage.total_tokens = prompt_tokens + completion_tokens
    return mock_completion


def create_mock_tool_call(call_id, function_name, arguments_dict):
    """Helper to generate a mock ToolCall structure."""
    mock_tc = MagicMock()
    mock_tc.id = call_id
    mock_tc.type = "function"
    mock_tc.function.name = function_name
    mock_tc.function.arguments = json.dumps(arguments_dict)
    return mock_tc


@pytest.mark.asyncio
async def test_normal_conversational_response_without_tools(db_session: AsyncSession, test_user: User):
    """1. Test standard conversational turn without tool calls."""
    orchestrator = AgentOrchestrator()
    mock_resp = create_mock_groq_response(content="Good morning! How may I assist you today?")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="Good morning, Chief.")
        response = await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        assert response.reply == "Good morning! How may I assist you today?"
        assert len(response.tool_calls_executed) == 0
        assert response.pending_approval_id is None
        assert response.conversation_id is not None

        # Verify messages persisted in DB
        messages = await ConversationService.get_conversation_history(db_session, response.conversation_id)
        assert len(messages) == 2
        assert messages[0].sender_role == "user"
        assert messages[1].sender_role == "assistant"


@pytest.mark.asyncio
async def test_successful_create_task_tool_call(db_session: AsyncSession, test_user: User):
    """2. Test single-step tool execution: model calls create_task, then generates reply."""
    orchestrator = AgentOrchestrator()

    # Step 1: Model invokes create_task
    tc = create_mock_tool_call(
        call_id="call_create_1",
        function_name="create_task",
        arguments_dict={"title": "Finish Investor Pitch", "priority": "HIGH"},
    )
    step1_resp = create_mock_groq_response(content="", tool_calls=[tc])

    # Step 2: Model synthesizes final response based on tool result
    step2_resp = create_mock_groq_response(content="I have created the task 'Finish Investor Pitch' for you with HIGH priority.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [step1_resp, step2_resp]
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="Add an urgent task to finish the investor pitch.")
        response = await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        assert "Finish Investor Pitch" in response.reply
        assert len(response.tool_calls_executed) == 1
        assert response.tool_calls_executed[0].tool_name == "create_task"
        task_id = response.tool_calls_executed[0].result["task_id"]

        # Verify task is in DB
        db_task = await TaskService.get_task_by_id(db_session, test_user.id, task_id)
        assert db_task is not None
        assert db_task.title == "Finish Investor Pitch"
        assert db_task.priority == "HIGH"


@pytest.mark.asyncio
async def test_list_tasks_tool_call(db_session: AsyncSession, test_user: User):
    """3. Test list_tasks tool call."""
    # Seed 2 tasks
    t1 = Task(user_id=test_user.id, title="Review Marketing Plan", priority="MEDIUM")
    t2 = Task(user_id=test_user.id, title="Audit Cloud Bills", priority="HIGH")
    db_session.add_all([t1, t2])
    await db_session.commit()

    orchestrator = AgentOrchestrator()
    tc = create_mock_tool_call(
        call_id="call_list_1",
        function_name="list_tasks",
        arguments_dict={"priority": "HIGH"},
    )
    step1_resp = create_mock_groq_response(content="", tool_calls=[tc])
    step2_resp = create_mock_groq_response(content="You have 1 HIGH priority task: Audit Cloud Bills.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [step1_resp, step2_resp]
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="What high priority tasks do I have?")
        response = await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        assert len(response.tool_calls_executed) == 1
        assert response.tool_calls_executed[0].tool_name == "list_tasks"
        assert response.tool_calls_executed[0].result["count"] == 1


@pytest.mark.asyncio
async def test_memory_retrieval_and_context_injection(db_session: AsyncSession, test_user: User):
    """4. Test that personal memories are injected into the Groq system prompt."""
    await MemoryService.create_or_update_memory(
        session=db_session,
        user_id=test_user.id,
        category="PREFERENCE",
        key="diet",
        value="Strictly vegetarian, allergic to peanuts",
    )

    orchestrator = AgentOrchestrator()
    mock_resp = create_mock_groq_response(content="I've noted that for lunch reservations.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="Where should I book lunch for tomorrow?", include_memory=True)
        await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        # Inspect system prompt passed to Groq
        calls = mock_client.chat.completions.create.call_args_list
        initial_messages = calls[0][1]["messages"]
        system_msg = initial_messages[0]["content"]
        assert "Strictly vegetarian" in system_msg
        assert "allergic to peanuts" in system_msg


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_one_turn(db_session: AsyncSession, test_user: User):
    """5. Test model emitting multiple tool calls in a single turn."""
    orchestrator = AgentOrchestrator()

    tc1 = create_mock_tool_call(
        call_id="call_multi_1",
        function_name="create_task",
        arguments_dict={"title": "Task One", "priority": "LOW"},
    )
    tc2 = create_mock_tool_call(
        call_id="call_multi_2",
        function_name="save_memory",
        arguments_dict={"category": "FACT", "key": "office_code", "value": "4502"},
    )
    step1_resp = create_mock_groq_response(content="", tool_calls=[tc1, tc2])
    step2_resp = create_mock_groq_response(content="Created Task One and remembered your office code.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [step1_resp, step2_resp]
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="Add task 'Task One' and remember my office code is 4502.")
        response = await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        assert len(response.tool_calls_executed) == 2
        tool_names = [t.tool_name for t in response.tool_calls_executed]
        assert "create_task" in tool_names
        assert "save_memory" in tool_names


@pytest.mark.asyncio
async def test_multi_step_tool_execution_loop(db_session: AsyncSession, test_user: User):
    """6. Test iterative multi-step chain: turn 1 calls tool A -> turn 2 calls tool B -> turn 3 final response."""
    orchestrator = AgentOrchestrator()

    # Turn 1: create task
    tc1 = create_mock_tool_call("call_step_1", "create_task", {"title": "Send Quarterly Report"})
    resp_turn1 = create_mock_groq_response(tool_calls=[tc1])

    # Turn 2: save memory
    tc2 = create_mock_tool_call("call_step_2", "save_memory", {"key": "reporting_cycle", "value": "Quarterly"})
    resp_turn2 = create_mock_groq_response(tool_calls=[tc2])

    # Turn 3: final text
    resp_turn3 = create_mock_groq_response(content="Quarterly report task scheduled and reporting cycle remembered.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [resp_turn1, resp_turn2, resp_turn3]
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="Schedule quarterly report and save the preference.")
        response = await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        assert len(response.tool_calls_executed) == 2
        assert len(response.execution_steps) == 3
        assert "Quarterly report task scheduled" in response.reply


@pytest.mark.asyncio
async def test_guarded_delete_creates_pending_approval(db_session: AsyncSession, test_user: User):
    """7. Test guarded delete_task creates a PENDING approval and DOES NOT delete the task."""
    task = Task(user_id=test_user.id, title="Protected Task", priority="URGENT")
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    orchestrator = AgentOrchestrator()

    tc = create_mock_tool_call("call_del_1", "delete_task", {"task_id": task.id, "reason": "Redundant"})
    step1_resp = create_mock_groq_response(tool_calls=[tc])
    step2_resp = create_mock_groq_response(content=f"I have created a pending approval request to delete '{task.title}'.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [step1_resp, step2_resp]
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message=f"Delete task {task.id}")
        response = await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        assert response.pending_approval_id is not None
        assert response.tool_calls_executed[0].requires_approval is True

        # Verify task is STILL in the database (not deleted)
        task_in_db = await TaskService.get_task_by_id(db_session, test_user.id, task.id)
        assert task_in_db is not None, "Guarded task must NOT be deleted without explicit approval"

        # Verify ApprovalRequest is in PENDING state
        approval = await db_session.get(ApprovalRequest, response.pending_approval_id)
        assert approval is not None
        assert approval.status == ApprovalStatus.PENDING.value
        assert approval.action_type == "DELETE_TASK"


@pytest.mark.asyncio
async def test_unknown_tool_handling(db_session: AsyncSession, test_user: User):
    """8. Test graceful handling when model calls an unregistered tool."""
    orchestrator = AgentOrchestrator()

    tc = create_mock_tool_call("call_bad_1", "drop_all_tables", {"confirm": True})
    step1_resp = create_mock_groq_response(tool_calls=[tc])
    step2_resp = create_mock_groq_response(content="I cannot perform that unrecognized action.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [step1_resp, step2_resp]
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="Run drop_all_tables")
        response = await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        assert len(response.tool_calls_executed) == 1
        assert response.tool_calls_executed[0].tool_name == "drop_all_tables"
        # Tool result sent to model indicates error without crashing
        assert "I cannot perform that" in response.reply


@pytest.mark.asyncio
async def test_invalid_tool_arguments(db_session: AsyncSession, test_user: User):
    """9. Test graceful handling when model emits malformed or missing arguments."""
    orchestrator = AgentOrchestrator()

    # Missing required 'title'
    tc = create_mock_tool_call("call_invalid_1", "create_task", {"description": "No title here"})
    step1_resp = create_mock_groq_response(tool_calls=[tc])
    step2_resp = create_mock_groq_response(content="Please provide a title for the task.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [step1_resp, step2_resp]
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="Create a task without a title")
        response = await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        assert len(response.tool_calls_executed) == 1
        assert "Please provide a title" in response.reply


@pytest.mark.asyncio
async def test_maximum_step_enforcement(db_session: AsyncSession, test_user: User):
    """10. Test that loop terminates and synthesizes response when MAX_ORCHESTRATION_STEPS is reached."""
    orchestrator = AgentOrchestrator()

    # Mock an endless loop: always emit list_tasks
    infinite_tc = create_mock_tool_call("call_loop", "list_tasks", {})
    loop_resp = create_mock_groq_response(tool_calls=[infinite_tc])

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        # Always returns tool calls
        mock_client.chat.completions.create.return_value = loop_resp
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="List tasks in a loop")
        response = await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        # Loop must cap at 5 steps
        assert len(response.tool_calls_executed) == 5
        assert any(step.action_type == "MAX_STEPS_REACHED" for step in response.execution_steps)
        assert "maximum execution limit of 5 steps" in response.reply


@pytest.mark.asyncio
async def test_groq_api_failure_handling(db_session: AsyncSession, test_user: User):
    """11. Test clean exception mapping when Groq API fails."""
    orchestrator = AgentOrchestrator()

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        # Simulate 429 RateLimitError
        mock_client.chat.completions.create.side_effect = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body={"error": "Rate limit exceeded"}
        )
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message="Hello")
        with pytest.raises(HTTPException) as exc_info:
            await orchestrator.run(session=db_session, user_id=test_user.id, request=req)

        assert exc_info.value.status_code == 429
        assert "rate limit" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_conversation_history_persistence(db_session: AsyncSession, test_user: User):
    """12. Test multi-turn conversational persistence across independent orchestrator calls."""
    orchestrator = AgentOrchestrator()

    resp1 = create_mock_groq_response(content="Hello! How can I help?")
    resp2 = create_mock_groq_response(content="I remember our discussion about Q4.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [resp1, resp2]
        mock_get_client.return_value = mock_client

        # Turn 1
        req1 = AgentChatRequest(message="Hello, my name is Alex.")
        res1 = await orchestrator.run(session=db_session, user_id=test_user.id, request=req1)
        conv_id = res1.conversation_id

        # Turn 2 in the same thread
        req2 = AgentChatRequest(conversation_id=conv_id, message="What did we just discuss?")
        res2 = await orchestrator.run(session=db_session, user_id=test_user.id, request=req2)

        # Inspect database history
        messages = await ConversationService.get_conversation_history(db_session, conv_id)
        assert len(messages) == 4
        assert messages[0].content == "Hello, my name is Alex."
        assert messages[1].content == "Hello! How can I help?"
        assert messages[2].content == "What did we just discuss?"
        assert messages[3].content == "I remember our discussion about Q4."


@pytest.mark.asyncio
async def test_user_identity_isolation(db_session: AsyncSession, test_user: User):
    """13. Test tenant isolation: agent execution strictly confines access to the authenticated user's records."""
    # User A creates a task
    task_a = Task(user_id=test_user.id, title="User A Confidential Roadmap")
    db_session.add(task_a)

    # User B
    user_b = User(id="user-b-uuid-77777", email="user_b_agent@homingo.ai", full_name="User B")
    db_session.add(user_b)
    await db_session.commit()

    orchestrator = AgentOrchestrator()

    # User B attempts to delete User A's task via the agent
    tc = create_mock_tool_call("call_del_cross", "delete_task", {"task_id": task_a.id})
    step1_resp = create_mock_groq_response(tool_calls=[tc])
    step2_resp = create_mock_groq_response(content="I could not find that task in your account.")

    with patch.object(orchestrator, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [step1_resp, step2_resp]
        mock_get_client.return_value = mock_client

        req = AgentChatRequest(message=f"Delete task {task_a.id}")
        response = await orchestrator.run(session=db_session, user_id=user_b.id, request=req)

        # Tool result must reflect failure
        assert response.pending_approval_id is None
        assert response.tool_calls_executed[0].requires_approval is False

        # Task A remains untouched
        await db_session.refresh(task_a)
        assert task_a.title == "User A Confidential Roadmap"
