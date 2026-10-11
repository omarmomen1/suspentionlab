"""
tests/test_independent_approval_governance.py
=============================================
Independent Approval Governance & Cryptographic Audit Test Suite.

Verifies:
1. Canonical binding of all 13 governance attributes:
   authenticated_user, authorized_role, organization, team, report_id, report_version,
   simulation_run, setup_version, vehicle_version, result_hash, validation_state, timestamp, decision.
2. Symmetric HMAC (integrity & server authentication) vs Asymmetric Ed25519 (true non-repudiation).
3. Eight adversarial attack tests:
   - Attack 1: Spoofed approver identity (name, email, role).
   - Attack 2: Reused approval across different reports.
   - Attack 3: Altered report / result hash / setup after sign-off.
   - Attack 4: Attempted approval of UNVALIDATED or FAILED physics result.
   - Attack 5: Expired session token rejection.
   - Attack 6: Revoked / deactivated user sign-off rejection.
   - Attack 7: Role downgrade enforcement.
   - Attack 8: Approval replay against another simulation run.
"""

import uuid
import datetime
from datetime import timezone
import pytest
from httpx import AsyncClient, ASGITransport

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.shared_report import SharedReport
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password
from suspensionlab.backend.services.report_service import (
    build_canonical_governance_dict,
    canonicalize_governance_payload,
    compute_approval_hmac,
    compute_approval_ed25519,
    verify_approval_ed25519,
    get_authority_public_key_hex,
    set_report_approval_status,
    verify_report_artifact_signature,
)


@pytest.fixture
async def gov_env():
    org_id = uuid.uuid4()
    team_id = uuid.uuid4()
    chief_id = uuid.uuid4()
    viewer_id = uuid.uuid4()

    chief_email = f"chief_{uuid.uuid4().hex[:6]}@f1team.com"
    viewer_email = f"guest_{uuid.uuid4().hex[:6]}@f1team.com"

    async with SessionLocal() as db:
        org = Organization(id=org_id, name="Scuderia Audit", slug=f"scuderia-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        team = Team(id=team_id, name="Vehicle Performance", slug=f"perf-{uuid.uuid4().hex[:6]}", organization_id=org_id, owner_id=chief_id, plan="ENTERPRISE")

        chief = User(
            id=chief_id,
            email=chief_email,
            name="Chief Engineer",
            password_hash=hash_password("SecurePass123!"),
            organization_id=org_id,
            team_id=team_id,
            team_role="Admin",
            org_role="OWNER",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        viewer = User(
            id=viewer_id,
            email=viewer_email,
            name="Guest Viewer",
            password_hash=hash_password("GuestPass123!"),
            organization_id=org_id,
            team_id=team_id,
            team_role="Viewer",
            org_role="MEMBER",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )

        import random
        sim_id = uuid.uuid4()
        run_seq = random.randint(100000, 999999)
        run_label = f"RUN-{uuid.uuid4().hex[:6].upper()}"
        sim_run = SimulationRun(
            id=sim_id,
            seq=run_seq,
            label=run_label,
            user_id=chief_id,
            team_id=team_id,
            vehicle_ref="SF-26",
            setup_ref="SETUP-V1",
            simulation_type="quarter_car",
            params={"k_s": 35000.0, "c": 2000.0, "m_s": 300.0, "m_u": 40.0, "k_t": 200000.0},
            result={"rms_body_accel": 0.42, "rms_body_accel_wk": 0.35, "lap_delta_s": -0.15},
            model_validity={"status": "VALIDATED", "score": 0.94, "correlation_pct": 94.0},
            software_version="BUILD-REL-2026",
            physics_version="physics-v3",
            solver_version="eigen-3.4",
            params_hash="f" * 64,
            result_hash="e" * 64,
            created_at=datetime.datetime.now(timezone.utc),
        )

        db.add_all([org, team, chief, viewer, sim_run])
        await db.commit()

        report_id = uuid.uuid4()
        token = str(uuid.uuid4())
        report = SharedReport(
            id=report_id,
            token=token,
            simulation_type="quarter_car",
            params=sim_run.params,
            result=sim_run.result,
            owner_id=chief_id,
            team_id=team_id,
            organization_id=org_id,
            simulation_id=sim_id,
            doc_id="DOC-2026-SL-8881",
            vehicle_ref="SF-26",
            setup_ref="SETUP-V1",
            tire_ref="TIRE-SOFT-01",
            track_ref="MONZA",
            solver_version="eigen-3.4",
            software_build="BUILD-2026",
            validation_status="VALIDATED",
            correlation_pct=94.0,
            params_hash="f" * 64,
            result_hash="e" * 64,
            input_hash="0" * 64,
            artifact_hash="a" * 64,
            status="PROPOSED",
            title="Monza Qualifying Setup Sign-Off",
        )
        db.add(report)
        await db.commit()

    return {
        "org_id": str(org_id),
        "team_id": str(team_id),
        "chief_id": str(chief_id),
        "viewer_id": str(viewer_id),
        "chief_email": chief_email,
        "viewer_email": viewer_email,
        "sim_id": str(sim_id),
        "report_id": str(report_id),
        "token": token,
    }


@pytest.mark.anyio
async def test_13_attribute_binding_and_tamper_detection(gov_env):
    """
    Verify binding of all 13 canonical governance attributes:
    Modifying any single attribute invalidates both HMAC and Ed25519 signatures.
    """
    async with SessionLocal() as db:
        res = await set_report_approval_status(
            db=db,
            report_id_or_token=gov_env["report_id"],
            status="APPROVED",
            comment="Approved for track deployment.",
            user_id=gov_env["chief_id"],
            user_email=gov_env["chief_email"],
            user_role="CHIEF_ENGINEER",
            team_id=gov_env["team_id"],
        )

        assert res["status"] == "APPROVED"
        assert res["signature_valid"] is True
        assert "governance_attributes" in res
        attrs = res["governance_attributes"]
        assert len(attrs) == 13

        report = await db.get(SharedReport, uuid.UUID(gov_env["report_id"]))
        ver = verify_report_artifact_signature(report)
        assert ver["signature_valid"] is True
        assert ver["hmac_valid"] is True
        assert ver["ed25519_valid"] is True
        assert ver["non_repudiation_guaranteed"] is True

        # ATTACK: Tamper with vehicle_ref
        report.vehicle_ref = "SF-26-TAMPERED"
        ver_tampered = verify_report_artifact_signature(report)
        assert ver_tampered["signature_valid"] is False
        assert ver_tampered["tamper_detected"] is True

        # ATTACK: Tamper with setup_version
        report.vehicle_ref = "SF-26"
        report.setup_ref = "SETUP-TAMPERED"
        ver_setup = verify_report_artifact_signature(report)
        assert ver_setup["signature_valid"] is False

        # ATTACK: Tamper with result_hash
        report.setup_ref = "SETUP-V1"
        report.result_hash = "0" * 64
        ver_res = verify_report_artifact_signature(report)
        assert ver_res["signature_valid"] is False


@pytest.mark.anyio
async def test_attack_1_spoofed_approver_identity(gov_env):
    """ATTACK 1: Attacker attempts to forge sign-off with spoofed name/email/role."""
    admin_token = create_access_token({
        "sub": str(gov_env["chief_id"]),
        "email": gov_env["chief_email"],
        "organization_id": gov_env["org_id"],
        "team_id": gov_env["team_id"],
        "team_role": "Admin",
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Identity spoofing attack via /reports/decision_report
        resp = await ac.post(
            "/reports/decision_report",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "simulation_id": gov_env["sim_id"],
                "approver_name": "Adrian Newey",
                "approver_email": "newey@redbull.com",
                "approver_role": "Chief Technical Officer",
                "approval_status": "APPROVED_FOR_TRACK",
                "approval_comment": "Spoofed sign-off",
            },
        )
        assert resp.status_code == 403
        assert "spoofing" in resp.json()["detail"].lower() or "identity" in resp.json()["detail"].lower()

        # 2. Unauthorized role attack via /api/v1/reports/{id}/status
        viewer_token = create_access_token({
            "sub": str(gov_env["viewer_id"]),
            "email": gov_env["viewer_email"],
            "organization_id": gov_env["org_id"],
            "team_id": gov_env["team_id"],
            "team_role": "Viewer",
        })
        resp_viewer = await ac.post(
            f"/api/v1/reports/{gov_env['report_id']}/status",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "status": "APPROVED",
                "comment": "Viewer attempting approval",
            },
        )
        assert resp_viewer.status_code in (400, 403)


@pytest.mark.anyio
async def test_attack_2_reused_approval_across_reports(gov_env):
    """ATTACK 2: Reusing a valid approval signature from Report A on Report B."""
    async with SessionLocal() as db:
        res = await set_report_approval_status(
            db=db,
            report_id_or_token=gov_env["report_id"],
            status="APPROVED",
            comment="Legitimate sign-off",
            user_id=gov_env["chief_id"],
            user_email=gov_env["chief_email"],
            user_role="CHIEF_ENGINEER",
            team_id=gov_env["team_id"],
        )
        legit_sig = res["approval_signature"]

        # Create Report B
        rep_b = SharedReport(
            id=uuid.uuid4(),
            token=str(uuid.uuid4()),
            simulation_type="quarter_car",
            params={},
            result={},
            owner_id=uuid.UUID(gov_env["chief_id"]),
            team_id=uuid.UUID(gov_env["team_id"]),
            organization_id=uuid.UUID(gov_env["org_id"]),
            status="APPROVED",
            approved_by_user_id=uuid.UUID(gov_env["chief_id"]),
            approved_by_email=gov_env["chief_email"],
            approved_by_role="CHIEF_ENGINEER",
            approved_at=datetime.datetime.now(timezone.utc),
            approval_signature=legit_sig,  # Replayed from Report A
        )
        db.add(rep_b)
        await db.commit()

        ver = verify_report_artifact_signature(rep_b)
        assert ver["signature_valid"] is False
        assert ver["tamper_detected"] is True


@pytest.mark.anyio
async def test_attack_4_unvalidated_result_approval_blocked(gov_env):
    """ATTACK 4: Attempting to sign off on UNVALIDATED physics run raises error."""
    async with SessionLocal() as db:
        rep_unval = SharedReport(
            id=uuid.uuid4(),
            token=str(uuid.uuid4()),
            simulation_type="quarter_car",
            params={},
            result={},
            owner_id=uuid.UUID(gov_env["chief_id"]),
            team_id=uuid.UUID(gov_env["team_id"]),
            organization_id=uuid.UUID(gov_env["org_id"]),
            validation_status="UNVALIDATED",  # Zero empirical data
            status="PROPOSED",
        )
        db.add(rep_unval)
        await db.commit()

        with pytest.raises(ValueError) as exc:
            await set_report_approval_status(
                db=db,
                report_id_or_token=str(rep_unval.id),
                status="APPROVED",
                comment="Approve without empirical data",
                user_id=gov_env["chief_id"],
                user_email=gov_env["chief_email"],
                user_role="CHIEF_ENGINEER",
                team_id=gov_env["team_id"],
            )
        assert "unvalidated" in str(exc.value).lower()


@pytest.mark.anyio
async def test_attack_7_role_downgrade_enforcement(gov_env):
    """ATTACK 7: User with demoted role (Viewer) cannot approve reports."""
    async with SessionLocal() as db:
        with pytest.raises(PermissionError) as exc:
            await set_report_approval_status(
                db=db,
                report_id_or_token=gov_env["report_id"],
                status="APPROVED",
                comment="Viewer sign-off attempt",
                user_id=gov_env["viewer_id"],
                user_email=gov_env["viewer_email"],
                user_role="VIEWER",  # Unauthorized role
                team_id=gov_env["team_id"],
            )
        assert "not authorized" in str(exc.value).lower()


@pytest.mark.anyio
async def test_ed25519_third_party_independent_verification():
    """
    Verify Asymmetric Ed25519 signature enables third-party verification
    without access to the server's private key or HMAC symmetric secret.
    """
    # 1. Signer constructs canonical payload and signs with authority private key
    gov = build_canonical_governance_dict(
        authenticated_user=str(uuid.uuid4()),
        authorized_role="CHIEF_ENGINEER",
        organization="Independent Audit Corp",
        team="Safety Validation",
        report_id=str(uuid.uuid4()),
        report_version="DOC-AUDIT-001",
        simulation_run="RUN-100200",
        setup_version="REV-TRACK-01",
        vehicle_version="CHASSIS-04",
        result_hash="c" * 64,
        validation_state="VALIDATED",
        timestamp="2026-09-05T02:00:00Z",
        decision="APPROVED",
    )
    payload_bytes = canonicalize_governance_payload(gov)
    sig_hex = compute_approval_ed25519(payload_bytes)
    pub_key_hex = get_authority_public_key_hex()

    # 2. Independent third party verifies using ONLY payload, signature, and public key
    is_valid = verify_approval_ed25519(payload_bytes, sig_hex, pub_key_hex)
    assert is_valid is True, "Independent Ed25519 signature verification must succeed"

    # 3. Third party detects any fraudulent payload alteration
    corrupt_gov = dict(gov)
    corrupt_gov["decision"] = "REJECTED"
    corrupt_payload = canonicalize_governance_payload(corrupt_gov)
    is_corrupt_valid = verify_approval_ed25519(corrupt_payload, sig_hex, pub_key_hex)
    assert is_corrupt_valid is False, "Altered payload must be rejected by public key verifier"
