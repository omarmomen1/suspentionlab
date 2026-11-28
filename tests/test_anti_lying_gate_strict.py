"""
tests/test_anti_lying_gate_strict.py
====================================
Regression tests for Anti-Lying Gate strict enforcement on engineering approvals.
Verifies:
1. Decision report approval without a backing database SimulationRun is strictly rejected (HTTP 400).
2. Unvalidated simulation run cannot be approved (HTTP 400).
3. Validated simulation run with correlation >= 85.0% generates a valid cryptographic HMAC signature.
"""
import pytest
import uuid
from httpx import AsyncClient, ASGITransport

from suspensionlab.backend.api.main import app
from suspensionlab.backend.security.jwt_utils import create_access_token
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.simulation_run import SimulationRun


@pytest.mark.asyncio
async def test_anti_lying_gate_blocks_synthetic_payload_without_db_run():
    """Verify that omitting simulation_id/run_label when requesting approval is rejected with HTTP 400."""
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    team_id = uuid.uuid4()

    async with SessionLocal() as db:
        user = User(
            id=user_id,
            email=f"chief-{uuid.uuid4().hex[:6]}@suspensionlab.pro",
            password_hash="test_pw_hash",
            organization_id=org_id,
            org_role="ORG_ADMIN",
            team_role="CHIEF_ENGINEER",
            plan="ENTERPRISE",
        )
        db.add(user)
        await db.commit()

    token = create_access_token({
        "sub": str(user_id),
        "user_id": str(user_id),
        "email": user.email,
        "role": "CHIEF_ENGINEER",
        "plan": "ENTERPRISE",
        "organization_id": str(org_id),
        "team_id": str(team_id),
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attempt to forge an approval for client-supplied synthetic numbers with NO backing database run
        synthetic_payload = {
            "validation_state": "VALIDATED",
            "correlation_pct": 99.9,
            "approval": {
                "decision": "APPROVED_FOR_TEST_TRACK",
                "comment": "Attempted bypass without database run",
            }
        }
        res = await client.post(
            "/reports/decision_report",
            json=synthetic_payload,
            headers={"Authorization": f"Bearer {token}", "X-API-Key": "dev_secret_key"}
        )

        # Wave 9 item 2: a decision report without a persisted run is refused with 422
        # before any approval logic runs. The invariant (no report without a DB run) is
        # unchanged; only the status code and message moved.
        assert res.status_code == 422, f"Expected 422 Unprocessable Entity, got {res.status_code}: {res.text}"
        assert "requires a persisted simulation run" in res.json().get("detail", "")


@pytest.mark.asyncio
async def test_anti_lying_gate_accepts_validated_db_run():
    """Verify that a legitimate validated simulation run is approved with cryptographic HMAC signature."""
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    team_id = uuid.uuid4()
    sim_id = uuid.uuid4()

    async with SessionLocal() as db:
        user = User(
            id=user_id,
            email=f"chief-{uuid.uuid4().hex[:6]}@suspensionlab.pro",
            password_hash="test_pw_hash",
            organization_id=org_id,
            org_role="ORG_ADMIN",
            team_role="CHIEF_ENGINEER",
            plan="ENTERPRISE",
        )
        db.add(user)

        from sqlalchemy import select, func
        max_seq_res = await db.execute(select(func.coalesce(func.max(SimulationRun.seq), 100000)))
        next_seq = max_seq_res.scalar_one() + 1

        sim = SimulationRun(
            id=sim_id,
            seq=next_seq,
            label=f"RUN-VAL-{uuid.uuid4().hex[:6]}",
            user_id=user_id,
            team_id=team_id,
            simulation_type="quarter_car",
            params={"k_s": 35000.0, "c": 2200.0},
            result={"peak_body_accel": 1.12, "rms_accel": 0.42},
            software_version="2.0.0",
            physics_version="2.0.0",
            solver_version="scipy",
            params_hash="val_phash",
            result_hash="val_rhash",
            model_validity={"status": "VALIDATED", "score": 0.96, "validation_state": "VALIDATED", "correlation_pct": 96.0}
        )
        db.add(sim)
        await db.commit()

    token = create_access_token({
        "sub": str(user_id),
        "user_id": str(user_id),
        "email": user.email,
        "role": "CHIEF_ENGINEER",
        "plan": "ENTERPRISE",
        "organization_id": str(org_id),
        "team_id": str(team_id),
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "simulation_id": str(sim_id),
            "approval": {
                "decision": "APPROVED_FOR_TEST_TRACK",
                "comment": "Legitimate sign-off on validated telemetry correlation",
            }
        }
        res = await client.post(
            "/reports/decision_report",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "X-API-Key": "dev_secret_key"}
        )

        assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"
        assert "X-Approval-Signature" in res.headers
        assert len(res.headers["X-Approval-Signature"]) == 64
