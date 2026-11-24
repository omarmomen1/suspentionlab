import os
import pytest
import asyncpg
import redis.asyncio as aioredis


@pytest.fixture(autouse=True)
def mock_redis():
    """Bypass the autouse mock_redis fixture in conftest.py for live URL testing."""
    yield


@pytest.mark.asyncio
async def test_database_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        pytest.skip("DATABASE_URL environment variable is not configured")

    clean_url = db_url.replace("+asyncpg", "")
    if clean_url.startswith("sqlite") or not clean_url.startswith(("postgres://", "postgresql://")):
        pytest.skip("DATABASE_URL is not configured for PostgreSQL (skipping asyncpg live check)")

    conn = await asyncpg.connect(clean_url)
    try:
        val = await conn.fetchval("SELECT 1")
        assert val == 1, f"Expected SELECT 1 to return 1, got {val}"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_redis_connection():
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url or redis_url == "redis://127.0.0.1:6379/0":
        pytest.skip("REDIS_URL environment variable is not configured")

    r = aioredis.from_url(redis_url)
    try:
        pong = await r.ping()
        assert pong is True, f"Expected redis ping to return True, got {pong}"
    finally:
        await r.aclose()
