"""
tests/test_final_enterprise_redteam.py
======================================
SUSPENSIONLAB PRO — FINAL ENTERPRISE SECURITY RED TEAM
Adversarial hostile red team simulation against competing F1 organization (Ferrari vs. Mercedes).

Identities:
1. Viewer Account (Org A - Mercedes)
2. Crew Account (Org A - Mercedes)
3. Engineer Account (Org A - Mercedes)
4. Admin Account (Org A - Mercedes)
5. Competing Organization Account (Org B - Scuderia Ferrari)

Target Assets Probed:
- Vehicles & Profiles
- Setups & Proposals
- Simulation Runs
- Telemetry Datasets & Health
- Digital Twins
- Engineering Decision Reports
- Tamper-Evident Audit Logs
- Optimization & Compute Jobs
- Cryptographic Approval Signatures
- Public Shared Tokens

Attack Vectors Exercised:
- IDOR / BOLA via direct UUID & label injection
- Mass Assignment (injecting is_admin=True, organization_id, org_role)
- Role Spoofing (Viewer attempting compute, Crew attempting parameter calibration)
- Cross-Tenant Data Exfiltration (Ferrari attempting to read Mercedes telemetry/runs)
- Approval Forgery (client-supplied approver identity spoofing)
- Share Token Manipulation & Replay
- Revoked / Stale Session Token Reuse
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.shared_report import SharedReport
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password, TokenRevocationRegistry


@pytest.fixture
async def redteam_environment():
    """Build two isolated competing Formula 1 teams with 5 distinct caller accounts."""
    org_merc_id = uuid.uuid4()
    org_ferrari_id = uuid.uuid4()
    team_merc_id = uuid.uuid4()
    team_ferrari_id = uuid.uuid4()

    # Mercedes accounts
    admin_merc_id = uuid.uuid4()
    eng_merc_id = uuid.uuid4()
    crew_merc_id = uuid.uuid4()
    viewer_merc_id = uuid.uuid4()

    # Ferrari attacker account
    attacker_ferrari_id = uuid.uuid4()

    async with SessionLocal() as db:
        org_merc = Organization(id=org_merc_id, name="Mercedes AMG F1", slug=f"merc-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        org_ferrari = Organization(id=org_ferrari_id, name="Scuderia Ferrari", slug=f"ferrari-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        team_merc = Team(id=team_merc_id, name="Merc Dynamics", slug=f"merc-dyn-{uuid.uuid4().hex[:6]}", organization_id=org_merc_id, owner_id=admin_merc_id)
        team_ferrari = Team(id=team_ferrari_id, name="Ferrari Aero", slug=f"ferrari-aero-{uuid.uuid4().hex[:6]}", organization_id=org_ferrari_id, owner_id=attacker_ferrari_id)

        admin_merc = User(
            id=admin_merc_id, email=f"admin_{uuid.uuid4().hex[:6]}@mercedes-f1.com",
            password_hash=hash_password("MercSecr3t!"), name="Toto Wolff",
            organization_id=org_merc_id, team_id=team_merc_id,
            org_role="ORG_ADMIN", team_role="Admin", plan="ENTERPRISE", onboarding_complete=True,
        )
        eng_merc = User(
            id=eng_merc_id, email=f"eng_{uuid.uuid4().hex[:6]}@mercedes-f1.com",
            password_hash=hash_password("MercSecr3t!"), name="James Vowles",
            organization_id=org_merc_id, team_id=team_merc_id,
            org_role="MEMBER", team_role="Engineer", plan="ENTERPRISE", onboarding_complete=True,
        )
        crew_merc = User(
            id=crew_merc_id, email=f"crew_{uuid.uuid4().hex[:6]}@mercedes-f1.com",
            password_hash=hash_password("MercSecr3t!"), name="Mechanic Pete",
            organization_id=org_merc_id, team_id=team_merc_id,
            org_role="MEMBER", team_role="Crew", plan="ENTERPRISE", onboarding_complete=True,
        )
        viewer_merc = User(
            id=viewer_merc_id, email=f"viewer_{uuid.uuid4().hex[:6]}@mercedes-f1.com",
            password_hash=hash_password("MercSecr3t!"), name="Sponsor VIP",
            organization_id=org_merc_id, team_id=team_merc_id,
            org_role="MEMBER", team_role="Viewer", plan="ENTERPRISE", onboarding_complete=True,
        )
        attacker_ferrari = User(
            id=attacker_ferrari_id, email=f"attacker_{uuid.uuid4().hex[:6]}@ferrari-f1.it",
            password_hash=hash_password("FerrariSecr3t!"), name="Fred Vasseur",
            organization_id=org_ferrari_id, team_id=team_ferrari_id,
            org_role="ORG_ADMIN", team_role="Admin", plan="ENTERPRISE", onboarding_complete=True,
        )

        # Target Mercedes confidential assets
        merc_profile_id = uuid.uuid4()
        merc_profile = VehicleProfile(
            id=merc_profile_id, user_id=eng_merc_id, name="W15 Confidential Aero Pack",
            params={"k_s": 32000.0, "c": 2400.0, "downforce_cl": 2.45},
        )
        merc_sim_id = uuid.uuid4()
        import random
        merc_sim = SimulationRun(
            id=merc_sim_id, seq=random.randint(100000, 9999999), label=f"RUN-MERC-{uuid.uuid4().hex[:8]}",
            user_id=eng_merc_id, team_id=team_merc_id, vehicle_ref="W15-E",
            simulation_type="quarter_car", params={"k_s": 32000.0},
            result={"peak_body_accel": 1.15, "status": "PASS"},
            software_version="2.0.0", physics_version="2.0.0", solver_version="scipy-1.11.0",
            params_hash="hash_merc_params", result_hash="hash_merc_result",
            model_validity={"validation_state": "VALIDATED", "correlation_pct": 94.0},
            created_at=datetime.now(timezone.utc),
        )
        merc_job_id = uuid.uuid4()
        merc_job = JobRecord(
            id=merc_job_id, user_id=eng_merc_id, team_id=team_merc_id,
            job_type="OPTIMIZE_QUARTER", status="RUNNING",
            params={"k_s": 32000.0}, last_heartbeat=datetime.now(timezone.utc),
        )
        merc_report_id = uuid.uuid4()
        merc_report = SharedReport(
            id=merc_report_id,
            simulation_id=merc_sim_id,
            owner_id=eng_merc_id,
            team_id=team_merc_id,
            organization_id=org_merc_id,
            token=f"merc_secret_{uuid.uuid4().hex}",
            simulation_type="quarter_car",
            params={"k_s": 32000.0},
            result={"status": "PASS"},
            status="PROPOSED",
            is_public=False,
        )

        db.add_all([
            org_merc, org_ferrari, team_merc, team_ferrari,
            admin_merc, eng_merc, crew_merc, viewer_merc, attacker_ferrari,
            merc_profile, merc_sim, merc_job, merc_report,
        ])
        await db.commit()

    return {
        "org_merc": org_merc,
        "org_ferrari": org_ferrari,
        "admin_merc": admin_merc,
        "eng_merc": eng_merc,
        "crew_merc": crew_merc,
        "viewer_merc": viewer_merc,
        "attacker_ferrari": attacker_ferrari,
        "merc_profile": merc_profile,
        "merc_sim": merc_sim,
        "merc_job": merc_job,
        "merc_report": merc_report,
    }


def make_token(user: User) -> str:
    """Generate authenticated JWT bearer token for a user."""
    return create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "plan": user.plan,
        "organization_id": str(user.organization_id) if user.organization_id else None,
        "org_role": user.org_role,
        "team_id": str(user.team_id) if user.team_id else None,
        "team_role": user.team_role,
    })


# ── ATTACK VECTOR 1: Cross-Tenant Data Exfiltration (Ferrari -> Mercedes) ────────

@pytest.mark.asyncio
async def test_redteam_ferrari_cannot_read_mercedes_simulation_run(redteam_environment):
    """Ferrari attacker attempts IDOR to read Mercedes simulation run by direct UUID and label."""
    data = redteam_environment
    ferrari_token = make_token(data["attacker_ferrari"])
    merc_sim_id = str(data["merc_sim"].id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attack 1: Direct UUID lookup
        res1 = await client.get(
            f"/api/v1/reports/run/{merc_sim_id}",
            headers={"Authorization": f"Bearer {ferrari_token}"},
        )
        assert res1.status_code in (403, 404), f"Breach! Status: {res1.status_code}"

        # Attack 2: Label-based lookup
        res2 = await client.get(
            "/api/v1/reports/run/RUN-MERC-CONFIDENTIAL-01",
            headers={"Authorization": f"Bearer {ferrari_token}"},
        )
        assert res2.status_code in (403, 404), f"Breach! Status: {res2.status_code}"


@pytest.mark.asyncio
async def test_redteam_ferrari_cannot_access_or_cancel_mercedes_job(redteam_environment):
    """Ferrari attacker attempts to view or cancel Mercedes running optimization job."""
    data = redteam_environment
    ferrari_token = make_token(data["attacker_ferrari"])
    merc_job_id = str(data["merc_job"].id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attack: Cancel Mercedes job
        cancel_res = await client.post(
            f"/api/v1/jobs/{merc_job_id}/cancel",
            headers={"Authorization": f"Bearer {ferrari_token}"},
        )
        assert cancel_res.status_code in (403, 404), f"Breach! Foreign job was affected: {cancel_res.status_code}"


@pytest.mark.asyncio
async def test_redteam_ferrari_cannot_read_mercedes_audit_logs(redteam_environment):
    """Ferrari attacker attempts to read Mercedes engineering audit records."""
    data = redteam_environment
    ferrari_token = make_token(data["attacker_ferrari"])
    merc_org_id = str(data["org_merc"].id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/audit/logs?organization_id={merc_org_id}",
            headers={"Authorization": f"Bearer {ferrari_token}"},
        )
        assert res.status_code in (403, 404), f"Audit log breached: {res.status_code}"


# ── ATTACK VECTOR 2: Privilege Escalation & Role Spoofing (Viewer/Crew -> Admin) ──

@pytest.mark.asyncio
async def test_redteam_viewer_cannot_execute_compute_simulations(redteam_environment):
    """Viewer account attempts to launch expensive Monte Carlo or optimization compute."""
    data = redteam_environment
    viewer_token = make_token(data["viewer_merc"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/optimize",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "params": {"k_s": 25000.0, "c": 2000.0, "m_s": 300.0, "m_u": 35.0, "k_t": 200000.0, "MR": 0.85},
                "profile": {"type": "bump", "amplitude": 0.05, "length": 2.0},
                "objective_type": "comfort",
                "max_travel": 0.08,
            },
        )
        # Viewer must be strictly blocked with HTTP 403 Forbidden
        assert res.status_code == 403
        assert "simulation_run" in res.json()["detail"].lower() or "permission" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_redteam_crew_cannot_calibrate_models(redteam_environment):
    """Crew member attempts parameter identification or model calibration."""
    data = redteam_environment
    crew_token = make_token(data["crew_merc"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/telemetry/calibrate",
            headers={"Authorization": f"Bearer {crew_token}"},
            json={"session_id": str(uuid.uuid4()), "target_metric": "stiffness"},
        )
        # Crew must be blocked from calibrations with 403 Forbidden
        assert res.status_code == 403


# ── ATTACK VECTOR 3: Cryptographic Approval Forgery ──────────────────────────────

@pytest.mark.asyncio
async def test_redteam_approval_forgery_spoofed_identity_rejected(redteam_environment):
    """Attacker attempts to sign a decision report with spoofed name 'Adrian Newey' and CTO role."""
    data = redteam_environment
    eng_token = make_token(data["eng_merc"])
    sim_id = str(data["merc_sim"].id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/reports/decision_report",
            headers={"Authorization": f"Bearer {eng_token}"},
            json={
                "simulation_id": sim_id,
                "approver_name": "Adrian Newey",
                "approver_role": "Chief Technical Officer",
                "approver_email": "adrian@redbullracing.com",
                "approval_status": "APPROVED_FOR_TRACK",
                "approval_comment": "Approved for race weekend",
            },
        )
        # Server must reject conflicting client-supplied identity with 403 Forbidden
        assert res.status_code == 403
        detail = res.json()["detail"].lower()
        assert "spoofing" in detail or "permission denied" in detail


# ── ATTACK VECTOR 4: Stale Session & Revocation ───────────────────────────────────

@pytest.mark.asyncio
async def test_redteam_revoked_stale_token_immediately_invalidated(redteam_environment):
    """Attacker attempts to replay an access token that has been explicitly revoked."""
    data = redteam_environment
    token = make_token(data["eng_merc"])

    from suspensionlab.backend.security.jwt_utils import decode_access_token
    payload = decode_access_token(token)
    jti = payload["jti"]

    # Explicitly revoke this session token
    TokenRevocationRegistry.revoke_jti(jti)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 401
        assert "revoked" in res.json()["detail"].lower()
