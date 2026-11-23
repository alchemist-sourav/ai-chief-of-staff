import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.task import Task
from app.models.memory import UserMemory


@pytest.mark.asyncio
async def test_models_and_relationships(db_session: AsyncSession, test_user: User):
    """Test creating models and validating ORM relationships and cascade deletes."""
    # 1. Create Conversation
    conv = Conversation(user_id=test_user.id, title="Morning Briefing")
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    assert conv.id is not None
    assert conv.user_id == test_user.id

    # 2. Add Message
    msg = Message(
        conversation_id=conv.id,
        sender_role="user",
        content="What is on my calendar today?",
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    assert msg.id is not None
    assert msg.conversation_id == conv.id

    # 3. Add Task
    task = Task(
        user_id=test_user.id,
        title="Review Q4 Roadmap",
        priority="HIGH",
        status="TODO",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    assert task.priority == "HIGH"

    # 4. Add User Memory
    mem = UserMemory(
        user_id=test_user.id,
        category="PREFERENCE",
        key="coffee",
        value="Oat milk flat white",
    )
    db_session.add(mem)
    await db_session.commit()
    await db_session.refresh(mem)
    assert mem.key == "coffee"

    # 5. Verify Cascade Deletion
    await db_session.delete(test_user)
    await db_session.commit()

    # Assert child records are deleted
    conv_check = await db_session.execute(select(Conversation).where(Conversation.id == conv.id))
    assert conv_check.scalars().first() is None

    task_check = await db_session.execute(select(Task).where(Task.id == task.id))
    assert task_check.scalars().first() is None
