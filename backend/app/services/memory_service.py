import re
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import UserMemory
from app.schemas.memory import UserMemoryCreate, UserMemoryUpdate

logger = logging.getLogger("ai_chief_of_staff.memory")


class MemoryService:
    """Service for managing personal knowledge, preferences, and situational memory."""

    @staticmethod
    async def get_user_memories(
        session: AsyncSession,
        user_id: str,
        category: Optional[str] = None,
        is_active: bool = True,
        limit: int = 50,
    ) -> List[UserMemory]:
        """Fetch memories for a user, optionally filtered by category."""
        filters = [UserMemory.user_id == user_id]
        if is_active is not None:
            filters.append(UserMemory.is_active == is_active)
        if category:
            filters.append(UserMemory.category == category.upper())

        query = (
            select(UserMemory)
            .where(and_(*filters))
            .order_by(UserMemory.updated_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create_or_update_memory(
        session: AsyncSession,
        user_id: str,
        category: str,
        key: str,
        value: str,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> UserMemory:
        """Create or update a memory item by category and key."""
        category_clean = category.strip().upper()
        key_clean = key.strip()

        # Check if memory key already exists for this user and category
        query = select(UserMemory).where(
            and_(
                UserMemory.user_id == user_id,
                UserMemory.category == category_clean,
                UserMemory.key == key_clean,
            )
        )
        result = await session.execute(query)
        existing = result.scalars().first()

        if existing:
            existing.value = value.strip()
            existing.is_active = True
            if metadata_json:
                existing.metadata_json = metadata_json
            await session.commit()
            await session.refresh(existing)
            logger.info(f"Updated memory [{category_clean}] {key_clean} for user {user_id}")
            return existing

        new_memory = UserMemory(
            user_id=user_id,
            category=category_clean,
            key=key_clean,
            value=value.strip(),
            metadata_json=metadata_json or {},
            is_active=True,
        )
        session.add(new_memory)
        await session.commit()
        await session.refresh(new_memory)
        logger.info(f"Created new memory [{category_clean}] {key_clean} for user {user_id}")
        return new_memory

    @staticmethod
    async def search_relevant_memories(
        session: AsyncSession,
        user_id: str,
        query_text: str,
        limit: int = 15,
    ) -> List[UserMemory]:
        """Retrieve relevant memories by combining core executive preferences with keyword matching."""
        # Clean query text: remove punctuation and split into alphanumeric tokens
        cleaned_query = re.sub(r"[^\w\s]", " ", query_text)
        tokens = [t.lower() for t in cleaned_query.split() if len(t) > 2]

        # 1. Fetch core active preferences & work styles (always relevant context for a Chief of Staff)
        core_query = (
            select(UserMemory)
            .where(
                and_(
                    UserMemory.user_id == user_id,
                    UserMemory.is_active.is_(True),
                    UserMemory.category.in_(["PREFERENCE", "WORK_STYLE"]),
                )
            )
            .order_by(UserMemory.updated_at.desc())
            .limit(limit)
        )
        core_res = await session.execute(core_query)
        memories_dict: Dict[str, UserMemory] = {m.id: m for m in core_res.scalars().all()}

        # 2. Add keyword matching for specific facts, contacts, and custom keys
        if tokens:
            conditions = []
            for token in tokens:
                pattern = f"%{token}%"
                conditions.append(UserMemory.key.ilike(pattern))
                conditions.append(UserMemory.value.ilike(pattern))
                conditions.append(UserMemory.category.ilike(pattern))

            token_query = (
                select(UserMemory)
                .where(
                    and_(
                        UserMemory.user_id == user_id,
                        UserMemory.is_active.is_(True),
                        or_(*conditions),
                    )
                )
                .order_by(UserMemory.updated_at.desc())
                .limit(limit)
            )
            token_res = await session.execute(token_query)
            for m in token_res.scalars().all():
                memories_dict[m.id] = m

        return list(memories_dict.values())[:limit]

    @staticmethod
    def format_memories_for_prompt(memories: List[UserMemory]) -> str:
        """Format a list of memories into an organized context block for the system prompt."""
        if not memories:
            return ""

        lines = ["[Personal Memory & Context for this User]"]
        for m in memories:
            lines.append(f"• [{m.category}] {m.key}: {m.value}")
        lines.append("[End of Personal Memory - Proactively apply these preferences in your responses]\n")
        return "\n".join(lines)
