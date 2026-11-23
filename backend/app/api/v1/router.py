from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.ai import router as ai_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.memory import router as memory_router
from app.api.v1.agent import router as agent_router
from app.api.v1.approvals import router as approvals_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health_router)
api_v1_router.include_router(ai_router, prefix="/ai")
api_v1_router.include_router(conversations_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(memory_router)
api_v1_router.include_router(agent_router)
api_v1_router.include_router(approvals_router)
