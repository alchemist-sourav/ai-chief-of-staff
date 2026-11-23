import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.services.memory_service import MemoryService


@pytest.mark.asyncio
async def test_memory_service_lifecycle(db_session: AsyncSession, test_user: User):
    """Test memory creation, updating existing keys, search, and prompt formatting."""
    # 1. Create memories
    m1 = await MemoryService.create_or_update_memory(
        session=db_session,
        user_id=test_user.id,
        category="PREFERENCE",
        key="communication_style",
        value="Concise bullet points",
    )
    assert m1.key == "communication_style"
    assert m1.value == "Concise bullet points"

    m2 = await MemoryService.create_or_update_memory(
        session=db_session,
        user_id=test_user.id,
        category="CONTACT",
        key="investor_lead",
        value="Sarah Connor (sarah@venture.com)",
    )
    assert m2.category == "CONTACT"

    # 2. Update existing key (upsert behavior)
    m1_updated = await MemoryService.create_or_update_memory(
        session=db_session,
        user_id=test_user.id,
        category="PREFERENCE",
        key="communication_style",
        value="Ultra-brief, 2 bullets maximum",
    )
    assert m1_updated.id == m1.id
    assert m1_updated.value == "Ultra-brief, 2 bullets maximum"

    # 3. Retrieve by category
    prefs = await MemoryService.get_user_memories(
        session=db_session, user_id=test_user.id, category="PREFERENCE"
    )
    assert len(prefs) == 1
    assert prefs[0].key == "communication_style"

    # 4. Search relevant memories by keyword
    search_results = await MemoryService.search_relevant_memories(
        session=db_session, user_id=test_user.id, query_text="What is Sarah's contact info?"
    )
    assert len(search_results) >= 1
    assert any(m.key == "investor_lead" for m in search_results)

    # 5. Format prompt
    prompt_text = MemoryService.format_memories_for_prompt([m1_updated, m2])
    assert "[Personal Memory & Context for this User]" in prompt_text
    assert "Ultra-brief, 2 bullets maximum" in prompt_text
    assert "Sarah Connor" in prompt_text
