import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db
from app.api.v1.router import api_v1_router
from app.api.v1.health import health_check
from app.api.v1.ai import test_ai_completion

logger = logging.getLogger("ai_chief_of_staff")
logging.basicConfig(level=logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup and shutdown routines."""
    logger.info("Initializing database tables...")
    await init_db()
    yield
    logger.info("Shutting down AI Chief of Staff backend.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for AI Chief of Staff - A Personal Staff for Everyone",
    lifespan=lifespan,
)

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root-level backward-compatible endpoints (Phase 1 verified)
app.add_api_route("/api/health", health_check, methods=["GET"], tags=["Root Health"])
app.add_api_route("/api/ai/test", test_ai_completion, methods=["POST"], tags=["Root AI Test"])

# Include versioned v1 router
app.include_router(api_v1_router)
