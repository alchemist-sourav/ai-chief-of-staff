from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.services.ai_service import ai_service
from app.schemas.ai import AIChatRequest, AIChatResponse, AITestRequest, AITestResponse

router = APIRouter(tags=["AI"])


@router.post("/test", response_model=AITestResponse)
def test_ai_completion(request: AITestRequest):
    """Direct test endpoint for Groq integration verification."""
    return ai_service.test_completion(request)


@router.post("/chat", response_model=AIChatResponse)
async def chat_with_chief_of_staff(
    request: AIChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Conversational endpoint with personal memory injection and message history persistence."""
    return await ai_service.chat(
        session=session,
        user_id=current_user.id,
        request=request,
    )
