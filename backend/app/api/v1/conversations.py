from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.services.conversation_service import ConversationService
from app.schemas.conversation import ConversationRead, MessageRead

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("", response_model=List[ConversationRead])
async def list_conversations(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List recent conversation sessions for the current user."""
    return await ConversationService.list_user_conversations(
        session=session, user_id=current_user.id, limit=limit
    )


@router.get("/{conversation_id}/messages", response_model=List[MessageRead])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve message history for a conversation."""
    # Verify ownership
    conv = await ConversationService.get_or_create_conversation(
        session=session, user_id=current_user.id, conversation_id=conversation_id
    )
    if not conv or conv.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    return await ConversationService.get_conversation_history(
        session=session, conversation_id=conversation_id, limit=limit
    )
