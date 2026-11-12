from typing import AsyncGenerator
import fakeredis
import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.dependencies import get_redis_client
from app.core.models.base import Base
from app.main import app

# Test database URL using in-memory SQLite with aiosqlite
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def get_test_settings() -> Settings:
    """Return test settings with isolated database and in-memory test configs."""
    return Settings(
        ENVIRONMENT="test",
        DEBUG=True,
        DATABASE_URL=TEST_DB_URL,
        SECRET_KEY="test-super-secret-key-for-veritas-jwt-testing-only",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create isolated async SQLite engine for each test function."""
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        future=True,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Teardown tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh async database session for tests."""
    session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def fake_redis():
    """Provide an in-memory async fake Redis instance."""
    server = fakeredis.FakeServer()
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture(scope="function")
async def client(test_db_session: AsyncSession, fake_redis) -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient wired with mocked DB and Redis dependencies."""
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    app.dependency_overrides[get_settings] = get_test_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client

    app.dependency_overrides.clear()
