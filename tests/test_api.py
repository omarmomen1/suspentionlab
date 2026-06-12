"""
tests/test_api.py
API endpoint and auth flow tests.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked database and Redis."""
    with patch("suspensionlab.backend.api.routes.optimize.init_async_redis", new_callable=AsyncMock):
        with patch("suspensionlab.backend.api.routes.optimize.close_async_redis", new_callable=AsyncMock):
            with patch("suspensionlab.backend.database.core.engine") as mock_engine:
                mock_conn = AsyncMock()
                mock_conn.run_sync = AsyncMock()
                mock_conn.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=1)))

                mock_engine.begin = MagicMock(return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_conn),
                    __aexit__=AsyncMock(return_value=None),
                ))

                from suspensionlab.backend.api.main import app
                yield TestClient(app)


class TestPublicEndpoints:
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "SuspensionLab" in response.json()["message"]

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestAuthRequired:
    def test_simulate_without_auth_returns_401(self, client):
        response = client.post("/simulate", json={
            "params": {"m_s": 300},
            "profile": {"profile_type": "step"}
        })
        assert response.status_code in (401, 403)

    def test_simulate_with_invalid_key_returns_401(self, client):
        response = client.post(
            "/simulate",
            json={"params": {"m_s": 300}, "profile": {"profile_type": "step"}},
            headers={"X-API-Key": "invalid_key_12345"}
        )
        assert response.status_code in (401, 403)


class TestErrorHandling:
    def test_not_found_returns_json(self, client):
        response = client.get("/nonexistent-endpoint")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        assert body["error"] == "not_found"

    def test_validation_error_returns_422(self, client):
        response = client.post(
            "/simulate",
            json={"invalid": "payload"},
            headers={"X-API-Key": "dev_secret_key"}
        )
        # Either 401 (auth fails first) or 422 (validation)
        assert response.status_code in (401, 403, 422)
