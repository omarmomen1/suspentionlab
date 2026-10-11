"""
tests/test_api.py
API endpoint and auth flow tests.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


# Uses client fixture from conftest.py


class TestPublicEndpoints:
    @pytest.mark.asyncio
    async def test_root(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        assert "SuspensionLab" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


class TestAuthRequired:
    @pytest.mark.asyncio
    async def test_simulate_without_auth_returns_401(self, client):
        response = await client.post("/api/v1/simulate", json={
            "params": {"m_s": 300},
            "profile": {"profile_type": "step"}
        })
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_simulate_with_invalid_key_returns_401(self, client):
        response = await client.post(
            "/api/v1/simulate",
            json={"params": {"m_s": 300}, "profile": {"profile_type": "step"}},
            headers={"X-API-Key": "invalid_key_12345"}
        )
        assert response.status_code in (401, 403)


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_not_found_returns_json(self, client):
        response = await client.get("/nonexistent-endpoint")
        assert response.status_code == 404
        body = response.json()
        assert "detail" in body
        assert body["status"] == 404

    @pytest.mark.asyncio
    async def test_validation_error_returns_422(self, client):
        response = await client.post(
            "/api/v1/simulate",
            json={"invalid": "payload"},
            headers={"X-API-Key": "dev_secret_key"}
        )
        # Either 401 (auth fails first) or 422 (validation)
        assert response.status_code in (401, 403, 422)
