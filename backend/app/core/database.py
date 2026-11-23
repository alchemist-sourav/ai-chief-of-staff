import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from sqlalchemy import text
from app.core.config import get_settings

logger = logging.getLogger("ai_chief_of_staff.database")
settings = get_settings()

# Normalize PostgreSQL URL for asyncpg if standard postgresql:// was provided
db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Configure async engine
engine_kwargs = {"echo": settings.DB_ECHO}
if "sqlite" in db_url:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine: AsyncEngine = create_async_engine(db_url, **engine_kwargs)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for yielding an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> bool:
    """Run a fast SELECT 1 query to verify database connectivity."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def init_db() -> None:
    """Create all tables on application startup."""
    from app.models.base import Base
    # Import all models to ensure they are registered with Base.metadata
    from app.models.user import User
    from app.models.conversation import Conversation
    from app.models.message import Message
    from app.models.task import Task
    from app.models.memory import UserMemory
    from app.models.approval import ApprovalRequest

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully.")
