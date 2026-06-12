import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_checkout(authenticated_client: AsyncClient):
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_create.return_value = MagicMock(url="http://mock-stripe/checkout")
        response = await authenticated_client.post("/billing/checkout", json={"plan": "pro"})
        assert response.status_code == 200
        assert response.json() == {"checkout_url": "http://mock-stripe/checkout"}

@pytest.mark.asyncio
async def test_checkout_invalid_plan(authenticated_client: AsyncClient):
    response = await authenticated_client.post("/billing/checkout", json={"plan": "invalid_plan"})
    assert response.status_code == 400
    assert "Unknown plan" in response.json()["detail"]

@pytest.mark.asyncio
async def test_portal_no_subscription(authenticated_client: AsyncClient):
    response = await authenticated_client.post("/billing/portal")
    assert response.status_code == 404
    assert response.json()["message"] == "No billing account found. Subscribe first."
