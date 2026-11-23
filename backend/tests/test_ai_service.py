import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.services.ai_service import GroqAIService
from app.services.memory_service import MemoryService
from app.schemas.ai import AIChatRequest, AITestRequest


def test_ai_service_config():
    """Verify AI service configures the default model and settings."""
    service = GroqAIService()
    assert service.settings.GROQ_MODEL == "openai/gpt-oss-120b"
    assert service.settings.GROQ_TIMEOUT_SECONDS == 30.0


@pytest.mark.asyncio
async def test_ai_chat_with_memory_injection(db_session: AsyncSession, test_user: User):
    """Verify that chat retrieves relevant memories and injects them into the Groq prompt."""
    # 1. Seed a user preference memory
    await MemoryService.create_or_update_memory(
        session=db_session,
        user_id=test_user.id,
        category="PREFERENCE",
        key="briefing_format",
        value="Executive summary followed by 3 actionable next steps",
    )

    # 2. Mock Groq client response to verify context flow
    mock_choice = MagicMock()
    mock_choice.message.content = "Here is your morning briefing based on your preference."
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage.prompt_tokens = 45
    mock_completion.usage.completion_tokens = 15
    mock_completion.usage.total_tokens = 60

    service = GroqAIService()

    with patch.object(service, "_get_client") as mock_get_client:
        mock_groq_client = MagicMock()
        mock_groq_client.chat.completions.create.return_value = mock_completion
        mock_get_client.return_value = mock_groq_client

        request = AIChatRequest(
            message="Give me my briefing for today.",
            include_memory=True,
        )

        response = await service.chat(
            session=db_session,
            user_id=test_user.id,
            request=request,
        )

        assert response.reply == "Here is your morning briefing based on your preference."
        assert response.conversation_id is not None
        assert "PREFERENCE:briefing_format" in response.memories_used

        # Verify that create was called and system prompt contained the memory
        call_kwargs = mock_groq_client.chat.completions.create.call_args[1]
        sent_messages = call_kwargs["messages"]
        system_msg = next(m for m in sent_messages if m["role"] == "system")
        assert "Executive summary followed by 3 actionable next steps" in system_msg["content"]
