import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={
            "email": "newuser@test.com",
            "password": "Password123!",
            "name": "New User"
        }
    )
    assert response.status_code == 201, response.json()
    data = response.json()
    assert "token" in data
    assert "refresh_token" in data
    assert data["email"] == "newuser@test.com"
    assert data["name"] == "New User"

@pytest.mark.asyncio
async def test_register_duplicate(client: AsyncClient):
    # Register once
    await client.post(
        "/auth/register",
        json={"email": "dupuser@test.com", "password": "Password123!"}
    )
    
    # Register again
    response = await client.post(
        "/auth/register",
        json={"email": "dupuser@test.com", "password": "Password123!"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "An account with this email already exists."

@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    # Setup: Create user
    await client.post(
        "/auth/register",
        json={"email": "loginuser@test.com", "password": "Password123!"}
    )
    
    # Login
    response = await client.post(
        "/auth/login",
        json={"email": "loginuser@test.com", "password": "Password123!"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "refresh_token" in data
    assert data["email"] == "loginuser@test.com"

@pytest.mark.asyncio
async def test_login_invalid(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={"email": "nonexistent@test.com", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."

@pytest.mark.asyncio
async def test_get_me(client: AsyncClient):
    # Setup
    reg_response = await client.post(
        "/auth/register",
        json={"email": "meuser@test.com", "password": "Password123!"}
    )
    token = reg_response.json()["token"]
    
    # Request with bearer
    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "meuser@test.com"
