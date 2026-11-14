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

# Cryptographically compliant test secrets before app import
if "JWT_KEYS" not in os.environ and "JWT_SECRET_KEY" not in os.environ:
    os.environ["JWT_KEYS"] = json.dumps({"v1": "9871239847192837491827349182739481723948712934871928374918273491"})
if "DECISION_HMAC_SECRET" not in os.environ:
    os.environ["DECISION_HMAC_SECRET"] = "8172938471928374918273948172394871293487192837491827349182736451"
if "STRIPE_WEBHOOK_SECRET" not in os.environ:
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_8172938471928374918273948172394871293487192837491827349182736451"
if "ED25519_AUTHORITY_PRIVATE_KEY_HEX" not in os.environ:
    os.environ["ED25519_AUTHORITY_PRIVATE_KEY_HEX"] = "4a" * 32
if "REDIS_URL" not in os.environ:
    os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/0"

# Mitigate C parser heap memory exhaustion for large scientific datasets (17MB telemetry)
import pandas as pd
_orig_read_csv = pd.read_csv
_dataset_cache = {}

def _caching_read_csv(filepath_or_buffer, *args, **kwargs):
    fp_str = str(filepath_or_buffer) if isinstance(filepath_or_buffer, (str, os.PathLike)) else ""
    if "stanford_vw_golf_thunderhill_2023_11.csv" in fp_str:
        cache_key = (fp_str, kwargs.get("comment"), kwargs.get("nrows"))
        if cache_key not in _dataset_cache:
            _dataset_cache[cache_key] = _orig_read_csv(filepath_or_buffer, *args, **kwargs)
        return _dataset_cache[cache_key].copy()
    return _orig_read_csv(filepath_or_buffer, *args, **kwargs)

pd.read_csv = _caching_read_csv

# Ensure xdist workers do not collide on default SQLite file
_worker_id = os.environ.get("PYTEST_XDIST_WORKER")
if _worker_id and "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./data/test_{_worker_id}.db"

# Ensure local worktree src is strictly prioritized on path for all tests
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path = [p for p in sys.path if not p.rstrip("/\\").endswith("src")]
sys.path.insert(0, src_path)

@pytest.fixture(autouse=True)
def reset_authority_key_cache():
    """Reset Ed25519 authority key cache to prevent inter-test key leakage."""
    if "suspensionlab.backend.services.report_service" in sys.modules:
        try:
            from suspensionlab.backend.services.report_service import reset_authority_keypair_cache
            reset_authority_keypair_cache()
        except Exception:
            pass
    yield
    if "suspensionlab.backend.services.report_service" in sys.modules:
        try:
            from suspensionlab.backend.services.report_service import reset_authority_keypair_cache
            reset_authority_keypair_cache()
        except Exception:
            pass

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(autouse=True)
def bypass_rate_limiter(request):
    node_str = f"{request.node.name} {request.node.nodeid}".lower()
    if "rate_limit" in node_str or "security" in node_str or "rate_limit" in request.keywords or "security" in request.keywords:
        yield None
        return
    with patch("suspensionlab.backend.security.rate_limit.RateLimiter.__call__", autospec=True) as mock:
        mock.return_value = True
        yield mock

@pytest.fixture(autouse=True)
def mock_redis():
    with patch("suspensionlab.backend.core.redis_client.get_async_redis_conn") as mock_get:
        _store = {}
        mock = MagicMock()
        mock_get.return_value = mock
        pipeline_mock = MagicMock()
        pipeline_mock.execute = AsyncMock()
        mock.pipeline.return_value = pipeline_mock
        
        async def _mock_get(k):
            return _store.get(k)

        async def _mock_set(k, v, **kw):
            if kw.get("nx") and k in _store:
                return False
            _store[k] = v.encode() if isinstance(v, str) else v
            return True

        async def _mock_setex(k, ttl, v):
            _store[k] = v.encode() if isinstance(v, str) else v
            return True

        mock.get = AsyncMock(side_effect=_mock_get)
        mock.set = AsyncMock(side_effect=_mock_set)
        mock.setex = AsyncMock(side_effect=_mock_setex)
        mock.incr = AsyncMock(return_value=1)
        mock.decr = AsyncMock(return_value=0)
        mock.expire = AsyncMock(return_value=True)
        mock.zcard = AsyncMock(return_value=0)
        mock.zrange = AsyncMock(return_value=[])
        mock.aclose = AsyncMock()
        mock.lock.return_value.__aenter__ = AsyncMock()
        mock.lock.return_value.__aexit__ = AsyncMock()
        
        sync_mock = MagicMock()
        sync_mock.get.side_effect = lambda k: _store.get(k)
        sync_mock.set.side_effect = lambda k, v: _store.update({k: v}) or True
        
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
    import suspensionlab.backend.database.models  # noqa: F401

    if postgres_container:
        db_url = postgres_container.get_connection_url()
        engine = create_async_engine(db_url, echo=False)
    else:
        from sqlalchemy.pool import StaticPool
        db_url = "sqlite+aiosqlite:///:memory:"
        engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        from sqlalchemy import event
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

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
def app_instance():
    from suspensionlab.backend.api.main import app
    return app

@pytest.fixture
async def client(db_session, app_instance):
    from suspensionlab.backend.database.core import get_db_dependency
    async def override_get_db():
        yield db_session
    app_instance.dependency_overrides[get_db_dependency] = override_get_db
    
    async with AsyncClient(transport=ASGITransport(app=app_instance), base_url="http://test") as ac:
        yield ac
    
    app_instance.dependency_overrides.pop(get_db_dependency, None)

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

@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    """Ensure no test leaks global FastAPI dependency overrides into subsequent tests."""
    yield
    if "suspensionlab.backend.api.main" in sys.modules:
        from suspensionlab.backend.api.main import app
        app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(client, mock_user, app_instance):
    from suspensionlab.backend.security.auth import verify_api_key
    app_instance.dependency_overrides[verify_api_key] = lambda: mock_user
    with patch("suspensionlab.backend.api.routes.billing_routes._get_user_id_from_request", return_value="00000000-0000-0000-0000-000000000000"):
        yield client
    app_instance.dependency_overrides.pop(verify_api_key, None)
