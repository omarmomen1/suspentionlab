"""
tests/test_health_and_readiness.py
==================================
STEP 5 Tests: Strict separation of /health (liveness) and /ready (readiness).
- /health = process alive
- /ready = dependencies usable (PostgreSQL and Redis)
- Kubernetes deployment templates use /ready for readiness probe and /health for liveness.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from suspensionlab.backend.api.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_alive():
    """Liveness probe /health must return 200 and process status without checking dependencies."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_ready_endpoint_success_when_dependencies_healthy():
    """Readiness probe /ready returns 200 when both DB and Redis respond."""
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True

    with patch("suspensionlab.backend.core.redis_client.get_async_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["database"] == "healthy"
            assert data["redis"] == "healthy"


@pytest.mark.asyncio
async def test_ready_endpoint_fails_503_on_db_outage():
    """Readiness probe /ready must return 503 if database fails to connect."""
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True

    from sqlalchemy.ext.asyncio import AsyncEngine
    with patch("suspensionlab.backend.core.redis_client.get_async_redis", return_value=mock_redis):
        with patch.object(AsyncEngine, "connect", side_effect=Exception("Database connection refused")):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get("/ready")
                assert response.status_code == 503
                data = response.json()["detail"]
                assert data["status"] == "unready"
                assert data["database"] == "unreachable"


@pytest.mark.asyncio
async def test_ready_endpoint_fails_503_on_redis_outage():
    """Readiness probe /ready must return 503 if Redis ping fails."""
    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = Exception("Redis connection refused")

    with patch("suspensionlab.backend.core.redis_client.get_async_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/ready")
            assert response.status_code == 503
            data = response.json()["detail"]
            assert data["status"] == "unready"
            assert data["redis"] == "unreachable"


def test_k8s_api_readiness_probe_uses_ready_path():
    """Verify Kubernetes API deployment template specifically points readiness probe to /ready."""
    with open("k8s/suspensionlab-chart/templates/api/deployment.yaml", "r", encoding="utf-8") as f:
        content = f.read()

    import re
    # Match readinessProbe block
    readiness_block = re.search(r"readinessProbe:\s+httpGet:\s+path:\s*([^\s]+)", content)
    liveness_block = re.search(r"livenessProbe:\s+httpGet:\s+path:\s*([^\s]+)", content)

    assert readiness_block is not None, "readinessProbe httpGet not found in api deployment.yaml"
    assert liveness_block is not None, "livenessProbe httpGet not found in api deployment.yaml"

    assert readiness_block.group(1) == "/ready", f"readinessProbe must use /ready, got {readiness_block.group(1)}"
    assert liveness_block.group(1) == "/health", f"livenessProbe must use /health, got {liveness_block.group(1)}"
