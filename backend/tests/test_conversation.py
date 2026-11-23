import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.services.conversation_service import ConversationService


@pytest.mark.asyncio
async def test_conversation_history_persistence(db_session: AsyncSession, test_user: User):
    """Test conversation thread creation, message additions, and chronological history retrieval."""
    # 1. Create conversation
    conv = await ConversationService.get_or_create_conversation(
        session=db_session,
        user_id=test_user.id,
        title="Weekly Planning",
    )
    assert conv.id is not None
    assert conv.title == "Weekly Planning"

    # 2. Add multiple messages
    msg1 = await ConversationService.add_message(
        session=db_session,
        conversation_id=conv.id,
        sender_role="user",
        content="Good morning, Chief.",
    )
    msg2 = await ConversationService.add_message(
        session=db_session,
        conversation_id=conv.id,
        sender_role="assistant",
        content="Good morning. Here are your 3 top priorities today.",
        model="openai/gpt-oss-120b",
    )
    msg3 = await ConversationService.add_message(
        session=db_session,
        conversation_id=conv.id,
        sender_role="user",
        content="Reschedule my 2 PM meeting.",
    )

    # 3. Retrieve history with limit
    history = await ConversationService.get_conversation_history(
        session=db_session,
        conversation_id=conv.id,
        limit=2,
    )
    # Chronological ordering of last 2 messages
    assert len(history) == 2
    assert history[0].content == msg2.content
    assert history[1].content == msg3.content

    # 4. List user conversations
    convs = await ConversationService.list_user_conversations(
        session=db_session, user_id=test_user.id
    )
    assert len(convs) >= 1
    assert convs[0].id == conv.id
