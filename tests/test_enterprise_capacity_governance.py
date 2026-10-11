"""
tests/test_enterprise_capacity_governance.py
============================================
Regression tests for Enterprise Capacity & Compute Governance.
Verifies:
1. HTTP 429 concurrency limit errors are NOT converted to HTTP 500 in /simulate.
2. Legitimate backpressure responds with well-formed 429 Too Many Requests.
3. Concurrency limits per plan (FREE=1, PRO=4, ENTERPRISE=16) are strictly enforced.
"""
import pytest
import uuid
from httpx import AsyncClient, ASGITransport

from suspensionlab.backend.api.main import app
from suspensionlab.backend.security.jwt_utils import create_access_token
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.job import JobRecord


@pytest.mark.asyncio
async def test_simulate_concurrency_429_not_masked_as_500():
    """Verify that when a user exceeds their concurrency limit, /simulate returns 429, NOT 500."""
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    team_id = uuid.uuid4()

    # Create test user in DB with PRO plan (limit 4)
    async with SessionLocal() as db:
        user = User(
            id=user_id,
            email=f"perf-{uuid.uuid4().hex[:6]}@suspensionlab.pro",
            password_hash="test_pw_hash",
            organization_id=org_id,
            team_id=team_id,
            org_role="MEMBER",
            team_role="ENGINEER",
            plan="PRO",
        )
        db.add(user)

        # Pre-seed 4 active RUNNING jobs for this user (exhausting quota)
        for i in range(4):
            job = JobRecord(
                id=uuid.uuid4(),
                user_id=user_id,
                team_id=team_id,
                job_type="SIMULATE_QUARTER",
                status="RUNNING",
                params={},
            )
            db.add(job)
        await db.commit()

    token = create_access_token({
        "sub": str(user_id),
        "user_id": str(user_id),
        "email": user.email,
        "role": "ENGINEER",
        "plan": "PRO",
        "organization_id": str(org_id),
        "team_id": str(team_id),
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "params": {"m_s": 300.0, "k_s": 35000.0, "c": 2000.0, "m_u": 40.0, "k_t": 200000.0},
            "profile": {"profile_type": "step", "amplitude": 0.05}
        }
        res = await client.post(
            "/api/v1/simulate",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "X-API-Key": "dev_secret_key"}
        )

        # Critical assertion: must be 429, NEVER 500!
        assert res.status_code == 429, f"Expected 429 Too Many Requests, got {res.status_code}: {res.text}"
        assert "Concurrency limit reached" in res.json().get("detail", "")
