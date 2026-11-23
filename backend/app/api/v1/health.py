from fastapi import APIRouter
from app.core.config import get_settings
from app.core.database import check_db_health
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Verify backend, database connectivity, and Groq configuration status."""
    db_alive = await check_db_health()
    groq_ok = bool(settings.GROQ_API_KEY and settings.GROQ_API_KEY.strip())

    overall_status = "healthy" if db_alive and groq_ok else "degraded"

    return HealthResponse(
        status=overall_status,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        database_connected=db_alive,
        groq_configured=groq_ok,
        default_model=settings.GROQ_MODEL,
    )
