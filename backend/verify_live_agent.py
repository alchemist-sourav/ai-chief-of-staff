import asyncio
from app.core.database import init_db, async_session_factory
from app.models.user import User
from app.models.task import Task
from app.models.approval import ApprovalRequest
from app.schemas.agent import AgentChatRequest
from app.services.agent_service import agent_orchestrator
from app.services.task_service import TaskService


async def verify_live_agent_loop():
    print("=" * 65)
    print("AI Chief of Staff - Live Groq Agent Orchestrator Verification")
    print("=" * 65)

    await init_db()

    async with async_session_factory() as session:
        # 1. Setup verified live user
        user_id = "live-demo-executive-user-001"
        user = await session.get(User, user_id)
        if not user:
            user = User(
                id=user_id,
                email="live_exec@homingo.ai",
                full_name="Live Executive",
                is_active=True,
            )
            session.add(user)
            await session.commit()

        # Step 1: Natural Language Task Creation (Safe Tool)
        print("\n[Step 1] Sending prompt: 'Please create a high-priority task titled Audit Q3 Cloud Invoices' ...")
        req1 = AgentChatRequest(message="Please create a high-priority task titled 'Audit Q3 Cloud Invoices'.")
        res1 = await agent_orchestrator.run(session=session, user_id=user_id, request=req1)

        print(f"Conversation ID: {res1.conversation_id}")
        print(f"Tool(s) Executed: {[t.tool_name for t in res1.tool_calls_executed]}")
        print(f"Reply:\n  -> {res1.reply}")
        assert len(res1.tool_calls_executed) >= 1
        assert res1.tool_calls_executed[0].tool_name == "create_task"
        created_task_id = res1.tool_calls_executed[0].result["task_id"]
        print(f"Task verified in database with ID: {created_task_id}")

        # Step 2: Multi-turn Task Query (Safe Tool)
        print("\n[Step 2] Sending prompt in same thread: 'List my tasks' ...")
        req2 = AgentChatRequest(
            conversation_id=res1.conversation_id,
            message="List my tasks to verify it's there.",
        )
        res2 = await agent_orchestrator.run(session=session, user_id=user_id, request=req2)
        print(f"Tool(s) Executed: {[t.tool_name for t in res2.tool_calls_executed]}")
        print(f"Reply:\n  -> {res2.reply}")
        assert any(t.tool_name == "list_tasks" for t in res2.tool_calls_executed)

        # Step 3: Guarded Action (Delete Task -> Pending Approval)
        print(f"\n[Step 3] Sending guarded prompt: 'Delete task {created_task_id}' ...")
        req3 = AgentChatRequest(
            conversation_id=res1.conversation_id,
            message=f"Please delete task {created_task_id}",
        )
        res3 = await agent_orchestrator.run(session=session, user_id=user_id, request=req3)
        print(f"Tool(s) Executed: {[t.tool_name for t in res3.tool_calls_executed]}")
        print(f"Pending Approval ID: {res3.pending_approval_id}")
        print(f"Reply:\n  -> {res3.reply}")
        assert res3.pending_approval_id is not None
        assert res3.tool_calls_executed[0].requires_approval is True

        # Verify task is still alive in DB
        task_in_db = await TaskService.get_task_by_id(session, user_id, created_task_id)
        assert task_in_db is not None, "Task must NOT be deleted yet!"
        print("✓ Verified: Task is NOT deleted from DB (guarded gatekeeper held)")

        # Verify approval record
        approval = await session.get(ApprovalRequest, res3.pending_approval_id)
        assert approval is not None
        assert approval.status == "PENDING"
        print(f"✓ Verified: Approval Request #{approval.id} is PENDING authorization")

    print("\n" + "=" * 65)
    print("ALL LIVE AGENT ORCHESTRATION VERIFICATIONS PASSED!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(verify_live_agent_loop())
