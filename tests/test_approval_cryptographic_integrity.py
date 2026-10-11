"""
tests/test_approval_cryptographic_integrity.py
==============================================
SuspensionLab PRO — Engineering Approval & Cryptographic Integrity Test Suite

Verifies:
1. Approver identity derivation exclusively from authenticated UserContext.
2. Rejection (HTTP 403) of spoofed approver name, email, role, or authority (e.g., Adrian Newey exploit).
3. Track release approval blocking (HTTP 400) for unvalidated or failing models.
4. Independent cryptographic verification of signed decision reports via HMAC-SHA256.
5. Tamper detection when results or artifact hashes are altered post-approval.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.shared_report import SharedReport
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password
from suspensionlab.backend.security.permissions import Permission


@pytest.fixture
async def approval_environment():
    org_id = uuid.uuid4()
    team_id = uuid.uuid4()
    eng_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    eng_email = f"junior_eng_{uuid.uuid4().hex[:6]}@williamsf1.com"
    admin_email = f"chief_eng_{uuid.uuid4().hex[:6]}@williamsf1.com"

    async with SessionLocal() as db:
        org = Organization(id=org_id, name="Williams Racing", slug=f"williams-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        team = Team(id=team_id, name="Vehicle Dynamics", slug=f"williams-vd-{uuid.uuid4().hex[:6]}", organization_id=org_id, owner_id=admin_id, plan="ENTERPRISE")

        eng_user = User(
            id=eng_id,
            email=eng_email,
            name="Junior Dynamicist",
            password_hash=hash_password("WillPass123!"),
            organization_id=org_id,
            team_id=team_id,
            team_role="Engineer",
            org_role="MEMBER",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        admin_user = User(
            id=admin_id,
            email=admin_email,
            name="Pat Fry",
            password_hash=hash_password("ChiefPass123!"),
            organization_id=org_id,
            team_id=team_id,
            team_role="Admin",
            org_role="MEMBER",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )

        import random
        # 1. Validated simulation run
        sim_valid_id = uuid.uuid4()
        sim_valid = SimulationRun(
            id=sim_valid_id,
            seq=random.randint(100000, 999999),
            label=f"RUN-{uuid.uuid4().hex[:6]}",
            user_id=eng_id,
            team_id=team_id,
            vehicle_ref="FW46-01",
            simulation_type="quarter_car",
            params={"k_s": 30000.0, "c": 2000.0, "k_t": 200000.0, "m_s": 250.0, "m_u": 40.0},
            result={"peak_body_accel": 1.1, "rms_body_accel_wk": 0.35, "status": "PASS"},
            model_validity={"validation_state": "VALIDATED", "correlation_pct": 92.5},
            software_version="2.0.0",
            physics_version="2.0.0",
            solver_version="scipy-1.11.0",
            params_hash="hash_valid_params",
            result_hash="hash_valid_result",
            created_at=datetime.now(timezone.utc),
        )

        # 2. Unvalidated simulation run (zero empirical data)
        sim_unval_id = uuid.uuid4()
        sim_unval = SimulationRun(
            id=sim_unval_id,
            seq=random.randint(100000, 999999),
            label=f"RUN-{uuid.uuid4().hex[:6]}",
            user_id=eng_id,
            team_id=team_id,
            vehicle_ref="FW46-02",
            simulation_type="quarter_car",
            params={"k_s": 30000.0, "c": 2000.0, "k_t": 200000.0, "m_s": 250.0, "m_u": 40.0},
            result={"peak_body_accel": 1.1, "rms_body_accel_wk": 0.35, "status": "PASS"},
            model_validity={"validation_state": "UNVALIDATED", "correlation_pct": None},
            software_version="2.0.0",
            physics_version="2.0.0",
            solver_version="scipy-1.11.0",
            params_hash="hash_unval_params",
            result_hash="hash_unval_result",
            created_at=datetime.now(timezone.utc),
        )

        db.add_all([org, team, eng_user, admin_user, sim_valid, sim_unval])
        await db.commit()

    eng_token = create_access_token({
        "sub": str(eng_id), "email": eng_email,
        "organization_id": str(org_id), "team_id": str(team_id),
        "team_role": "Engineer", "plan": "ENTERPRISE",
    })
    admin_token = create_access_token({
        "sub": str(admin_id), "email": admin_email,
        "organization_id": str(org_id), "team_id": str(team_id),
        "team_role": "Admin", "plan": "ENTERPRISE",
    })

    return {
        "eng_id": str(eng_id), "eng_email": eng_email, "eng_token": eng_token,
        "admin_id": str(admin_id), "admin_email": admin_email, "admin_token": admin_token,
        "sim_valid_id": str(sim_valid_id), "sim_unval_id": str(sim_unval_id),
    }


@pytest.mark.asyncio
async def test_identity_spoofing_adrian_newey_rejection(approval_environment):
    """
    Finding Remediation:
    POST /reports/decision_report MUST reject client-supplied approver identity
    when it conflicts with the authenticated UserContext.
    """
    ctx = approval_environment
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Client attempts to spoof Adrian Newey as the Chief Technical Officer
        spoofed_payload = {
            "simulation_id": ctx["sim_valid_id"],
            "approver_name": "Adrian Newey",
            "approver_email": "adrian@redbullracing.com",
            "approver_role": "Chief Technical Officer",
            "approval_status": "APPROVED_FOR_TRACK",
            "approval_comment": "Flawless front wing vortex shedding dynamics.",
        }

        resp = await client.post("/reports/decision_report", json=spoofed_payload, headers=headers)
        assert resp.status_code == 403
        detail = resp.json()["detail"].lower()
        assert "approver identity" in detail or "spoofing" in detail or "permission denied" in detail


@pytest.mark.asyncio
async def test_unvalidated_model_cannot_be_approved_for_track(approval_environment):
    """
    Scientific Integrity Enforcement:
    A simulation run with status UNVALIDATED, DATA_MISSING, or FAILED
    CANNOT be approved for track release. Server must return HTTP 400.
    """
    ctx = approval_environment
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attempt to approve unvalidated simulation run for track
        payload = {
            "simulation_id": ctx["sim_unval_id"],
            "approver_name": "Pat Fry",
            "approver_email": ctx["admin_email"],
            "approver_role": "Admin",
            "approval_status": "APPROVED_FOR_TRACK",
            "approval_comment": "Approved despite zero empirical data.",
        }

        resp = await client.post("/reports/decision_report", json=payload, headers=headers)
        assert resp.status_code == 400
        assert "unvalidated" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_decision_report_signing_and_tamper_detection(approval_environment):
    """
    Test authentic signing and cryptographic verification:
    1. Authorized Chief Engineer signs a validated simulation.
    2. Verification endpoint confirms signature authenticity.
    3. Tampering with artifact hash or simulation parameters invalidates the signature.
    """
    ctx = approval_environment
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {ctx['admin_token']}"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Generate legitimately signed decision report
        valid_payload = {
            "simulation_id": ctx["sim_valid_id"],
            "approver_name": "Pat Fry",
            "approver_email": ctx["admin_email"],
            "approver_role": "Admin",
            "approval_status": "APPROVED_FOR_TRACK",
            "approval_comment": "Meets FIA ride comfort and load criteria.",
        }

        resp = await client.post("/reports/decision_report", json=valid_payload, headers=headers)
        assert resp.status_code == 200
        html_content = resp.text
        assert "Pat Fry" in html_content
        assert "APPROVED_FOR_TRACK" in html_content
        assert "Cryptographic Approval Signature" in html_content

        # Extract the signature from header
        sig = resp.headers.get("X-Approval-Signature")
        result_hash = resp.headers.get("X-Result-Hash")
        approval_time = resp.headers.get("X-Approval-Time")
        approver_email = resp.headers.get("X-Approver-Email")
        approver_role = resp.headers.get("X-Approver-Role")
        approval_decision = resp.headers.get("X-Approval-Decision")
        sim_id = resp.headers.get("X-Simulation-ID")
        assert sig is not None
        assert result_hash is not None

        # 2. Independent cryptographic verification
        verify_resp = await client.post(
            "/reports/decision_report/verify",
            json={
                "sim_id": sim_id,
                "user_id": ctx["admin_id"],
                "approver_email": approver_email,
                "approver_role": approver_role,
                "approval_decision": approval_decision,
                "result_hash": result_hash,
                "approval_time": approval_time,
                "signature": sig,
            },
            headers=headers,
        )
        assert verify_resp.status_code == 200
        verify_data = verify_resp.json()
        assert verify_data["signature_valid"] is True
        assert verify_data["tamper_detected"] is False

        # 3. Post-approval tamper detection (tamper with result_hash)
        tampered_resp = await client.post(
            "/reports/decision_report/verify",
            json={
                "sim_id": sim_id,
                "user_id": ctx["admin_id"],
                "approver_email": approver_email,
                "approver_role": approver_role,
                "approval_decision": approval_decision,
                "result_hash": "tampered_result_hash_999999",
                "approval_time": approval_time,
                "signature": sig,
            },
            headers=headers,
        )
        assert tampered_resp.status_code == 200
        tampered_data = tampered_resp.json()
        assert tampered_data["signature_valid"] is False
        assert tampered_data["tamper_detected"] is True
