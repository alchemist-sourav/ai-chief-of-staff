from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.services.agent_service import agent_orchestrator

router = APIRouter(prefix="/agent", tags=["AI Agent"])


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    summary="Agent Chat Loop",
    description="Send a command or query to the autonomous AI Chief of Staff. Executes multi-step tool calls and returns final response.",
    responses={
        200: {"description": "Agent completed reasoning and generated response."},
        401: {"description": "Unauthenticated access."},
        429: {"description": "Groq rate limit exceeded."},
        500: {"description": "Internal agent error."},
    },
)
async def agent_chat(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AgentChatResponse:
    """Autonomous agent orchestration endpoint with tool calling, memory context, and approval generation."""
    try:
        return await agent_orchestrator.run(
            session=session,
            user_id=current_user.id,
            request=request,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during agent execution: {str(e)}",
        )
