import logging
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from groq import (
    Groq,
    AuthenticationError,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    APIStatusError,
    GroqError,
)

from app.core.config import Settings, get_settings
from app.services.memory_service import MemoryService
from app.services.conversation_service import ConversationService
from app.schemas.ai import AIChatRequest, AIChatResponse, AITestRequest, AITestResponse

logger = logging.getLogger("ai_chief_of_staff.ai_service")


class GroqAIService:
    """Modular AI service orchestrating Groq LLM calls, context assembly, and persistent history."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def _get_client(self) -> Groq:
        """Instantiate Groq client with validation."""
        api_key = self.settings.GROQ_API_KEY.strip() if self.settings.GROQ_API_KEY else ""
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Groq API key is not configured. Please set GROQ_API_KEY.",
            )
        return Groq(
            api_key=api_key,
            timeout=self.settings.GROQ_TIMEOUT_SECONDS,
        )

    def _handle_groq_exception(self, e: Exception) -> HTTPException:
        """Translate Groq SDK exceptions to clean FastAPI HTTPExceptions."""
        if isinstance(e, AuthenticationError):
            logger.error(f"Groq Auth Error: {e}")
            return HTTPException(status_code=401, detail=f"Groq API authentication failed: {str(e)}")
        elif isinstance(e, RateLimitError):
            logger.warning(f"Groq Rate Limit: {e}")
            return HTTPException(status_code=429, detail="Groq API rate limit exceeded. Please retry momentarily.")
        elif isinstance(e, APITimeoutError):
            logger.error(f"Groq Timeout: {e}")
            return HTTPException(status_code=504, detail=f"Groq API request timed out ({self.settings.GROQ_TIMEOUT_SECONDS}s).")
        elif isinstance(e, (APIConnectionError, APIStatusError)):
            logger.error(f"Groq Connection/Status Error: {e}")
            return HTTPException(status_code=502, detail=f"Groq API gateway error: {str(e)}")
        elif isinstance(e, GroqError):
            logger.error(f"Groq Generic Error: {e}")
            return HTTPException(status_code=500, detail=f"Groq error: {str(e)}")
        else:
            logger.exception("Unexpected AI service error")
            return HTTPException(status_code=500, detail=f"Unexpected AI error: {str(e)}")

    def test_completion(self, request: AITestRequest) -> AITestResponse:
        """Synchronous/direct completion for health verification and tests (preserves /api/ai/test)."""
        client = self._get_client()
        model_to_use = request.model or self.settings.GROQ_MODEL

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.message})

        try:
            completion = client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                max_tokens=request.max_tokens or 250,
                temperature=0.3,
            )
            content = completion.choices[0].message.content or ""
            usage_data = None
            if completion.usage:
                usage_data = {
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "total_tokens": completion.usage.total_tokens,
                }
            return AITestResponse(
                status="success",
                model=model_to_use,
                prompt=request.message,
                response=content.strip(),
                usage=usage_data,
            )
        except Exception as e:
            raise self._handle_groq_exception(e)

    async def chat(
        self,
        session: AsyncSession,
        user_id: str,
        request: AIChatRequest,
    ) -> AIChatResponse:
        """Multi-turn conversation with memory injection, Groq completion, and history persistence."""
        client = self._get_client()
        model_to_use = request.model or self.settings.GROQ_MODEL

        # 1. Get or create conversation thread
        conversation = await ConversationService.get_or_create_conversation(
            session=session,
            user_id=user_id,
            conversation_id=request.conversation_id,
        )

        # 2. Retrieve user memory context if requested
        memory_context = ""
        memories_used_keys = []
        if request.include_memory:
            relevant_memories = await MemoryService.search_relevant_memories(
                session=session,
                user_id=user_id,
                query_text=request.message,
                limit=10,
            )
            if relevant_memories:
                memory_context = MemoryService.format_memories_for_prompt(relevant_memories)
                memories_used_keys = [f"{m.category}:{m.key}" for m in relevant_memories]

        # 3. Build system instruction
        base_system_prompt = (
            "You are an elite, proactive AI Chief of Staff. "
            "Your objective is to help the user manage everyday responsibilities, organize their priorities, "
            "draft communications, and prepare action proposals. "
            "Communicate with executive precision: clear, concise, actionable, and courteous."
        )
        if memory_context:
            full_system_prompt = f"{base_system_prompt}\n\n{memory_context}"
        else:
            full_system_prompt = base_system_prompt

        # 4. Fetch prior message history (last 10 turns)
        history_messages = await ConversationService.get_conversation_history(
            session=session,
            conversation_id=conversation.id,
            limit=10,
        )

        # 5. Assemble messages array for Groq
        llm_messages: List[Dict[str, str]] = [{"role": "system", "content": full_system_prompt}]
        for msg in history_messages:
            if msg.sender_role in ["user", "assistant"]:
                llm_messages.append({"role": msg.sender_role, "content": msg.content})

        llm_messages.append({"role": "user", "content": request.message})

        # 6. Persist user message to DB
        user_msg_record = await ConversationService.add_message(
            session=session,
            conversation_id=conversation.id,
            sender_role="user",
            content=request.message,
            model=model_to_use,
        )

        # 7. Call Groq
        try:
            logger.info(f"Calling Groq LLM ({model_to_use}) for user {user_id}")
            completion = client.chat.completions.create(
                model=model_to_use,
                messages=llm_messages,
                max_tokens=1024,
                temperature=0.3,
            )
            reply_text = (completion.choices[0].message.content or "").strip()
            usage_dict = None
            if completion.usage:
                usage_dict = {
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "total_tokens": completion.usage.total_tokens,
                }
        except Exception as e:
            raise self._handle_groq_exception(e)

        # 8. Persist assistant reply to DB
        assistant_msg_record = await ConversationService.add_message(
            session=session,
            conversation_id=conversation.id,
            sender_role="assistant",
            content=reply_text,
            model=model_to_use,
            metadata_json={"usage": usage_dict, "memories_used": memories_used_keys},
        )

        return AIChatResponse(
            conversation_id=conversation.id,
            user_message_id=user_msg_record.id,
            assistant_message_id=assistant_msg_record.id,
            model=model_to_use,
            reply=reply_text,
            memories_used=memories_used_keys,
            usage=usage_dict,
        )


ai_service = GroqAIService()
