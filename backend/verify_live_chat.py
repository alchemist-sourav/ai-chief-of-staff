import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db

async def verify_live_chat_and_persistence():
    print("=" * 65)
    print("AI Chief of Staff - Live Chat & Persistence Verification")
    print("=" * 65)

    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health check
        print("\n[Step 1] Checking /api/v1/health ...")
        res = await client.get("/api/v1/health")
        print("Health status:", res.status_code, res.json())
        assert res.status_code == 200

        # 2. Add Personal Memory
        print("\n[Step 2] Storing user preference in /api/v1/memory ...")
        memory_payload = {
            "category": "PREFERENCE",
            "key": "beverage_order",
            "value": "Iced Oat Milk Matcha Latte, half sweet",
        }
        mem_res = await client.post("/api/v1/memory", json=memory_payload)
        print("Memory saved:", mem_res.status_code, mem_res.json()["key"])
        assert mem_res.status_code == 200

        # 3. Test Live Chat with Groq using Memory Injection
        print("\n[Step 3] Sending prompt to /api/v1/ai/chat with memory injection ...")
        chat_payload = {
            "message": "I'm stopping by a cafe. What is my exact customary drink order?",
            "include_memory": True,
        }
        chat_res = await client.post("/api/v1/ai/chat", json=chat_payload)
        print("Chat status:", chat_res.status_code)
        chat_data = chat_res.json()
        print(f"Conversation ID: {chat_data['conversation_id']}")
        print(f"Model: {chat_data['model']}")
        print(f"Memories used: {chat_data['memories_used']}")
        print(f"Assistant Reply:\n  -> {chat_data['reply']}")
        assert chat_res.status_code == 200
        assert "Matcha" in chat_data["reply"] or "Oat" in chat_data["reply"]

        # 4. Multi-turn chat persistence in the same conversation
        print("\n[Step 4] Sending follow-up message to the same conversation thread ...")
        conv_id = chat_data["conversation_id"]
        follow_up_payload = {
            "conversation_id": conv_id,
            "message": "Thanks. Also remind me what kind of assistant you are.",
            "include_memory": False,
        }
        chat2_res = await client.post("/api/v1/ai/chat", json=follow_up_payload)
        print("Follow-up status:", chat2_res.status_code)
        print(f"Follow-up Reply:\n  -> {chat2_res.json()['reply']}")
        assert chat2_res.status_code == 200

        # 5. Fetch Conversation Messages from DB
        print(f"\n[Step 5] Fetching stored messages for conversation {conv_id} ...")
        messages_res = await client.get(f"/api/v1/conversations/{conv_id}/messages")
        messages = messages_res.json()
        print(f"Total messages in thread: {len(messages)}")
        for i, m in enumerate(messages):
            print(f"  {i+1}. [{m['sender_role']}] {m['content'][:70]}...")
        assert len(messages) >= 4, "Thread should contain 2 user prompts + 2 assistant replies"

        # 6. Create and List Tasks
        print("\n[Step 6] Verifying Task management endpoints ...")
        task_res = await client.post("/api/v1/tasks", json={
            "title": "Send weekly briefing to executive team",
            "priority": "HIGH",
            "status": "TODO",
        })
        print("Created task:", task_res.json()["title"])
        tasks_list = await client.get("/api/v1/tasks")
        print(f"Active tasks count: {len(tasks_list.json())}")
        assert len(tasks_list.json()) >= 1

    print("\n" + "=" * 65)
    print("ALL LIVE END-TO-END FLOWS VERIFIED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(verify_live_chat_and_persistence())
