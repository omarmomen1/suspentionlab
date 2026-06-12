import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_me_deprecated(authenticated_client: AsyncClient, mock_user):
    response = await authenticated_client.get("/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == mock_user["user_id"]
    assert data["email"] == mock_user["email"]
    assert "key" not in data

@pytest.mark.asyncio
async def test_complete_onboarding(client: AsyncClient):
    # Setup user
    reg_res = await client.post(
        "/auth/register",
        json={"email": "onboard@test.com", "password": "Password123!"}
    )
    token = reg_res.json()["token"]
    
    # Complete onboarding
    response = await client.patch(
        "/users/me/onboarding",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    
    # Verify onboarding status
    me_res = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_res.json()["onboarding_complete"] is True
