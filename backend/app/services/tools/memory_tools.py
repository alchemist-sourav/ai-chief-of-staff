import logging
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory_service import MemoryService
from app.services.tools.base import BaseTool, ToolResult, ToolSecurityLevel

logger = logging.getLogger("ai_chief_of_staff.tools.memory")


class SaveMemoryArgs(BaseModel):
    category: str = Field(
        default="PREFERENCE",
        pattern="^(PREFERENCE|FACT|WORK_STYLE|CONTACT)$",
        description="Category of the memory",
    )
    key: str = Field(..., min_length=1, max_length=100, description="Short descriptive key for the memory")
    value: str = Field(..., min_length=1, description="Information, fact, or preference to remember")


class SaveMemoryTool(BaseTool):
    name = "save_memory"
    description = "Save or update a personal preference, fact, work style, or contact in user memory."
    security_level = ToolSecurityLevel.SAFE
    args_schema = SaveMemoryArgs

    async def execute(self, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
        memory = await MemoryService.create_or_update_memory(
            session=session,
            user_id=user_id,
            category=kwargs.get("category", "PREFERENCE"),
            key=kwargs["key"],
            value=kwargs["value"],
        )
        return ToolResult(
            success=True,
            message=f"Saved memory [{memory.category}] '{memory.key}'.",
            data={
                "id": memory.id,
                "category": memory.category,
                "key": memory.key,
                "value": memory.value,
            },
        )


class RetrieveMemoryArgs(BaseModel):
    query: str = Field(..., min_length=1, description="Keywords or topic to search for in memory")
    category: Optional[str] = Field(
        None,
        pattern="^(PREFERENCE|FACT|WORK_STYLE|CONTACT)$",
        description="Optional category filter",
    )
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of items to retrieve")


class RetrieveMemoryTool(BaseTool):
    name = "retrieve_memory"
    description = "Search and retrieve stored personal memories, preferences, and facts."
    security_level = ToolSecurityLevel.SAFE
    args_schema = RetrieveMemoryArgs

    async def execute(self, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
        category = kwargs.get("category")
        if category:
            memories = await MemoryService.get_user_memories(
                session=session,
                user_id=user_id,
                category=category,
                limit=kwargs.get("limit", 10),
            )
        else:
            memories = await MemoryService.search_relevant_memories(
                session=session,
                user_id=user_id,
                query_text=kwargs["query"],
                limit=kwargs.get("limit", 10),
            )

        items = [
            {"id": m.id, "category": m.category, "key": m.key, "value": m.value}
            for m in memories
        ]
        return ToolResult(
            success=True,
            message=f"Found {len(items)} memory items.",
            data={"memories": items, "count": len(items)},
        )
