import pytest
from httpx import AsyncClient
from typing import AsyncGenerator

from suspensionlab.backend.api.main import app

@pytest.mark.asyncio
async def test_simulate_quarter_car(test_client: AsyncClient, pro_user_token: str):
    payload = {
        "mass_sprung": 300.0,
        "mass_unsprung": 40.0,
        "stiffness_suspension": 20000.0,
        "damping_suspension": 1500.0,
        "stiffness_tire": 150000.0,
        "speed_kmh": 60.0
    }
    
    response = await test_client.post(
        "/api/v1/simulate/quarter-car",
        json=payload,
        headers={"Authorization": f"Bearer {pro_user_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "time" in data
    assert "sprung_accel" in data
    assert "suspension_deflection" in data
    assert len(data["time"]) > 0
    assert len(data["sprung_accel"]) == len(data["time"])

@pytest.mark.asyncio
async def test_simulate_unauthorized(test_client: AsyncClient):
    payload = {
        "mass_sprung": 300.0,
        "mass_unsprung": 40.0,
        "stiffness_suspension": 20000.0,
        "damping_suspension": 1500.0,
        "stiffness_tire": 150000.0,
        "speed_kmh": 60.0
    }
    
    response = await test_client.post(
        "/api/v1/simulate/quarter-car",
        json=payload
    )
    
    assert response.status_code == 401
