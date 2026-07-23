"""
tests/conftest.py
Shared test fixtures.
"""
import sys
import os
import json
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock

# Mock JWT_KEYS for testing before app import
if "JWT_KEYS" not in os.environ and "JWT_SECRET_KEY" not in os.environ:
    os.environ["JWT_KEYS"] = json.dumps({"v1": "test_secret_key"})

# Ensure src is on path for all tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from suspensionlab.backend.api.main import app
from suspensionlab.backend.security.auth import verify_api_key

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(autouse=True)
def bypass_rate_limiter():
    with patch("suspensionlab.backend.security.rate_limit.RateLimiter.__call__", autospec=True) as mock:
        mock.return_value = True
        yield mock

@pytest.fixture(autouse=True)
def mock_redis():
    with patch("suspensionlab.backend.core.redis_client.get_async_redis_conn") as mock_get:
        mock = MagicMock()
        mock_get.return_value = mock
        pipeline_mock = MagicMock()
        pipeline_mock.execute = AsyncMock()
        mock.pipeline.return_value = pipeline_mock
        # Mock other async methods on the redis connection itself
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock()
        mock.setex = AsyncMock()
        mock.zcard = AsyncMock(return_value=0)
        mock.zrange = AsyncMock(return_value=[])
        mock.aclose = AsyncMock()
        mock.lock.return_value.__aenter__ = AsyncMock()
        mock.lock.return_value.__aexit__ = AsyncMock()
        
        sync_mock = MagicMock()
        sync_mock.get.return_value = None
        sync_mock.set = MagicMock()
        
        with patch("redis.asyncio.from_url", return_value=mock), \
             patch("redis.Redis.from_url", return_value=sync_mock):
            yield mock

@pytest.fixture(autouse=True)
def mock_stripe_env():
    yield

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from suspensionlab.backend.database.core import Base, get_db_dependency
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@pytest.fixture(scope="session")
def postgres_container():
    try:
        from testcontainers.postgres import PostgresContainer
        with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
            yield postgres
    except ImportError:
        # Fallback if testcontainers is not installed locally
        yield None

@pytest.fixture
async def db_engine(postgres_container):
    # Import all models here to ensure they are registered with Base.metadata
    from suspensionlab.backend.database.models.user import User
    from suspensionlab.backend.database.models.profile import VehicleProfile
    from suspensionlab.backend.database.models.job import JobRecord
    from suspensionlab.backend.database.models.billing import StripeEvent

    if postgres_container:
        db_url = postgres_container.get_connection_url()
    else:
        db_url = "sqlite+aiosqlite:///:memory:"

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def db_session(db_engine):
    TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=db_engine, class_=AsyncSession)
    async with TestingSessionLocal() as session:
        yield session

from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db_dependency] = override_get_db
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.pop(get_db_dependency, None)

@pytest.fixture
def mock_user():
    from suspensionlab.backend.security.auth import UserContext
    return UserContext(
        user_id="00000000-0000-0000-0000-000000000000",
        plan="pro",
        email="test@suspensionlab.pro",
        name="Test User",
        onboarding_complete=True,
        team_id=None
    )

@pytest.fixture
async def authenticated_client(client, mock_user):
    app.dependency_overrides[verify_api_key] = lambda: mock_user
    with patch("suspensionlab.backend.api.routes.billing_routes._get_user_id_from_request", return_value="00000000-0000-0000-0000-000000000000"):
        yield client
    app.dependency_overrides.pop(verify_api_key, None)
