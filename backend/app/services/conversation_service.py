import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.conversation import Conversation
from app.models.message import Message

logger = logging.getLogger("ai_chief_of_staff.conversation")


class ConversationService:
    """Service managing conversation sessions and message history persistence."""

    @staticmethod
    async def get_or_create_conversation(
        session: AsyncSession,
        user_id: str,
        conversation_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Conversation:
        """Retrieve existing conversation or create a new session."""
        if conversation_id:
            query = (
                select(Conversation)
                .where(and_(Conversation.id == conversation_id, Conversation.user_id == user_id))
                .options(selectinload(Conversation.messages))
            )
            result = await session.execute(query)
            conversation = result.scalars().first()
            if conversation:
                return conversation
            logger.warning(f"Conversation {conversation_id} not found for user {user_id}. Creating new.")

        new_conversation = Conversation(
            user_id=user_id,
            title=title or "Executive Briefing Session",
        )
        session.add(new_conversation)
        await session.commit()
        await session.refresh(new_conversation)
        return new_conversation

    @staticmethod
    async def add_message(
        session: AsyncSession,
        conversation_id: str,
        sender_role: str,
        content: str,
        model: Optional[str] = None,
        tool_calls: Optional[Any] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Persist a message in the conversation thread."""
        message = Message(
            conversation_id=conversation_id,
            sender_role=sender_role,
            content=content,
            model=model,
            tool_calls=tool_calls,
            metadata_json=metadata_json or {},
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return message

    @staticmethod
    async def get_conversation_history(
        session: AsyncSession,
        conversation_id: str,
        limit: int = 20,
    ) -> List[Message]:
        """Fetch the latest messages from a conversation in chronological order."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        messages = list(result.scalars().all())
        messages.reverse()  # Return in chronological order
        return messages

    @staticmethod
    async def list_user_conversations(
        session: AsyncSession,
        user_id: str,
        limit: int = 20,
    ) -> List[Conversation]:
        """List recent conversations for a user."""
        query = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return list(result.scalars().all())
