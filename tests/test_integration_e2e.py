import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

import pytest
from fastapi.testclient import TestClient
from suspensionlab.backend.api.main import app

from unittest.mock import AsyncMock, MagicMock, patch

# We can use the TestClient as a context manager so it persists cookies across requests!
def test_e2e_flow():
    with TestClient(app, base_url="https://testserver") as client:
        # 1. Register and Login to get cookies
        import uuid
        test_email = f"test_{uuid.uuid4().hex[:8]}@suspensionlab.io"
        reg_resp = client.post(
            "/api/v1/auth/register",
            json={"email": test_email, "password": "Testpassword1!", "name": "Test User"}
        )
        assert reg_resp.status_code == 201, f"Register failed: {reg_resp.text}"
        
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": "Testpassword1!"}
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("token")
        assert token is not None
        
        # Verify the cookie was set
        assert "sl_token" in client.cookies
        
        # 2. Simulate quarter car
        from suspensionlab.backend.services.simulation_service import SimulationService
        from suspensionlab.backend.workers.unified_worker import run_job
        import uuid
        import asyncio

        async def mock_enqueue(user_id, plan, job_type, payload, db, team_id=None, **kwargs):
            from suspensionlab.backend.database.models.job import JobRecord
            from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis
            import uuid
            import json

            job_id = str(uuid.uuid4())
            p = QuarterCarParams(**payload["params"])
            r = RoadProfile(**payload["profile"])
            res = run_quarter_car_analysis(p, r)

            result_data = {
                "comfort_rating": res.comfort_rating,
                "rms_body_accel": res.rms_body_accel
            }

            new_job = JobRecord(
                id=uuid.UUID(job_id),
                user_id=uuid.UUID(user_id),
                job_type=job_type,
                status="COMPLETED",
                params=payload.get("params", {}),
                profile=payload.get("profile", {}),
                result=result_data,
            )
            db.add(new_job)
            await db.commit()
            
            from suspensionlab.backend.core.redis_client import get_async_redis_conn
            r_conn = get_async_redis_conn()
            if r_conn:
                await r_conn.set(f"job_status:{job_id}", json.dumps({
                    "job_id": job_id,
                    "user_id": str(user_id),
                    "status": "COMPLETED",
                    "result": result_data,
                }))
            return job_id

        async def mock_execute(user_id, plan, job_type, payload, db, team_id=None, **kwargs):
            job_id = await mock_enqueue(user_id, plan, job_type, payload, db, team_id=team_id, **kwargs)
            return {"job_id": job_id, "status": "PENDING", "result": None, "error": None}

        with patch("suspensionlab.backend.api.routes.simulate.quarter_car.SimulationService.execute_or_enqueue", new=mock_execute):
            sim_resp = client.post(
                "/api/v1/simulate",
                json={
                    "params": {
                        "m_s": 350.0,
                        "m_u": 45.0,
                        "k_s": 25000.0,
                        "c": 2000.0,
                        "k_t": 200000.0,
                        "MR": 0.8
                    },
                    "profile": {
                        "profile_type": "step",
                        "speed_kph": 60.0
                    }
                },
                headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")}
            )
            assert sim_resp.status_code == 202, f"Simulation failed: {sim_resp.text}"
            sim_data = sim_resp.json()
            assert "job_id" in sim_data
            job_id = sim_data["job_id"]
            
            # Poll for job completion
            import time
            for _ in range(10):
                job_resp = client.get(f"/api/v1/jobs/{job_id}")
                if job_resp.status_code == 200:
                    job_data = job_resp.json()
                    if job_data["status"] == "COMPLETED":
                        sim_result = job_data["result"]
                        assert "comfort_rating" in sim_result
                        assert "rms_body_accel" in sim_result
                        break
                time.sleep(1)
            else:
                pytest.fail("Job did not complete in time")
        
        # 3. Billing checkout (properly verified with mocked Stripe session)
        with patch("stripe.checkout.Session.create") as mock_stripe_create, \
             patch("suspensionlab.backend.api.routes.billing_routes.STRIPE_PRO_PRICE_ID", "price_test_pro_123"):
            mock_stripe_create.return_value = MagicMock(url="https://checkout.stripe.com/c/pay/cs_test_mock")
            checkout_resp = client.post(
                "/api/v1/billing/checkout",
                json={"plan": "pro"},
                headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")}
            )
            assert checkout_resp.status_code == 200, f"Checkout failed: {checkout_resp.text}"
            assert checkout_resp.json() == {"checkout_url": "https://checkout.stripe.com/c/pay/cs_test_mock"}


if __name__ == "__main__":
    test_e2e_flow()

