from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.services.memory_service import MemoryService
from app.schemas.memory import UserMemoryCreate, UserMemoryRead

router = APIRouter(prefix="/memory", tags=["Personal Memory"])


@router.get("", response_model=List[UserMemoryRead])
async def list_memories(
    category: Optional[str] = Query(None, description="Optional category filter"),
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List structured memories and preferences for the current user."""
    return await MemoryService.get_user_memories(
        session=session,
        user_id=current_user.id,
        category=category,
        limit=limit,
    )


@router.post("", response_model=UserMemoryRead)
async def create_or_update_memory(
    data: UserMemoryCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Store or update a personal preference, contact, or fact."""
    return await MemoryService.create_or_update_memory(
        session=session,
        user_id=current_user.id,
        category=data.category,
        key=data.key,
        value=data.value,
        metadata_json=data.metadata_json,
    )
