import sys
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

from app.models.base import Base
from app.models.user import User
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app

# Prevent Windows ProactorEventLoop self-pipe race condition with aiosqlite threads
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# In-memory SQLite async test database using StaticPool to share state safely
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_test_db():
    """Create all tables before each test, enforce foreign keys in SQLite, and clean up after."""
    async with test_engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session for testing."""
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id="test-user-uuid-12345",
        email="test_executive@homingo.ai",
        full_name="Alex Chief",
        is_active=True,
        preferences={"timezone": "America/New_York"},
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient authenticated by default with test_user Bearer JWT."""
    token = create_access_token(user_id=test_user.id, email=test_user.email)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an unauthenticated AsyncClient without default Authorization header."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
