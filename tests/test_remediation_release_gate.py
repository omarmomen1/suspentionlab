"""
tests/test_remediation_release_gate.py
======================================
Automated Regression Test Suite for Production Release Remediations:
- DEF-P1-01: Native C++ Build & Linkage (pybind11, Dockerfile cmake masking, and Windows DLL portability)
- DEF-P1-02: Synchronize Decision Report API with Cryptographic Governance (Ed25519 and 13 canonical attributes in REST API)
- DEF-P2-01: Enforce Separation of Duty in RBAC (Remove SETUP_APPROVE from standard engineer)
- DEF-P2-02: Protect Multi-DOF Compute Endpoints (bounded_run and concurrency limits on half-car and full-car)
- DEF-P2-03: Add Worker Service to docker-compose.yml
"""

import os
import sys
import uuid
import random
import tomllib
import yaml
import pytest
from httpx import AsyncClient, ASGITransport

from suspensionlab.backend.api.main import app
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password
from suspensionlab.backend.security.permissions import Permission, ROLE_PERMISSIONS_MAP
from suspensionlab.backend.services import report_service
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team


# ── Test 1: Native C++ Solver Build & Linkage Portability ────────────────────

def test_native_solver_dll_and_loading():
    """Verify that native binary is co-located and kinematics loads cleanly."""
    physics_dir = os.path.join("src", "suspensionlab", "physics")
    if sys.platform == "win32":
        pyd_path = os.path.join(physics_dir, "kinematics_core.cp314-win_amd64.pyd")
        dll_path = os.path.join(physics_dir, "libwinpthread-1.dll")
        assert os.path.exists(pyd_path), f"Expected {pyd_path} to exist."
        assert os.path.exists(dll_path), f"Expected {dll_path} to exist alongside the .pyd extension."
    else:
        import glob
        so_files = glob.glob(os.path.join(physics_dir, "kinematics_core*.so"))
        assert len(so_files) > 0, f"Expected kinematics_core*.so to exist in {physics_dir}."

    import suspensionlab.physics.kinematics as pk
    assert pk._HAVE_CPP is True, "C++ kinematics extension failed to load."
    assert pk._kc is not None, "C++ kinematics module handle is None."


# ── Test 2: Dockerfile & pyproject.toml Build Integrity ──────────────────────

def test_docker_and_pyproject_build_readiness():
    """Verify pybind11 is in dependencies and Dockerfiles do not mask build errors."""
    with open("pyproject.toml", "rb") as f:
        pyproj = tomllib.load(f)

    deps = pyproj.get("project", {}).get("dependencies", [])
    prod_deps = pyproj.get("project", {}).get("optional-dependencies", {}).get("prod", [])
    all_deps = deps + prod_deps

    has_pybind11 = any("pybind11" in d.lower() for d in all_deps)
    assert has_pybind11, "pybind11 must be declared in pyproject.toml dependencies."

    for df_path in ("Dockerfile", "Dockerfile.backend"):
        with open(df_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "|| true" not in content, f"{df_path} must not mask cmake build failure with '|| true'."


# ── Test 3: Decision Report API Returns Ed25519 & 13 Canonical Attributes ───

@pytest.mark.asyncio
async def test_decision_report_ed25519_api_and_13_attributes():
    """Verify /reports/decision_report generates genuine Ed25519 signatures and 13 attributes."""
    user_uuid = uuid.uuid4()
    team_uuid = uuid.uuid4()
    org_uuid = uuid.uuid4()
    run_label = f"RUN-TEST-{uuid.uuid4().hex[:6].upper()}"

    async with SessionLocal() as db:
        org = Organization(id=org_uuid, name="Test Org", slug=f"org-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        db.add(org)
        user = User(
            id=user_uuid,
            email=f"chief-{uuid.uuid4().hex[:6]}@f1-team.com",
            name="Chief Engineer",
            password_hash=hash_password("Secret123!"),
            organization_id=org_uuid,
            team_role="CHIEF_ENGINEER",
            org_role="ORG_ADMIN",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add(user)
        await db.flush()

        team = Team(
            id=team_uuid,
            organization_id=org_uuid,
            owner_id=user_uuid,
            name="Test Team",
            slug=f"team-{uuid.uuid4().hex[:6]}",
            plan="ENTERPRISE",
        )
        db.add(team)
        user.team_id = team_uuid

        run = SimulationRun(
            id=uuid.uuid4(),
            seq=random.randint(100000, 999999),
            label=run_label,
            user_id=user_uuid,
            team_id=team_uuid,
            simulation_type="quarter_car",
            vehicle_ref="CAR-TEST-F1",
            setup_ref="SETUP-AERO-01",
            track_ref="SILVERSTONE-2026",
            tire_ref="TIRE-SOFT-MF52",
            params={"m_s": 320.0, "k_s": 35000.0, "c": 2200.0},
            result={"rms_body_accel": 0.28, "rms_susp_travel": 0.012},
            model_validity={"validation_state": "VALIDATED", "correlation_pct": 94.5},
            params_hash="a" * 64,
            result_hash="b" * 64,
            solver_version="rk45-authoritative",
            physics_version="multibody-v3",
            software_version="BUILD-REL-2026.1",
        )
        db.add(run)
        await db.commit()

    token = create_access_token({
        "sub": str(user_uuid),
        "email": user.email,
        "team_role": "CHIEF_ENGINEER",
        "organization_id": str(org_uuid),
        "team_id": str(team_uuid),
        "plan": "ENTERPRISE",
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "run_label": run_label,
            "approval": {
                "decision": "APPROVED_FOR_TEST_TRACK",
                "comment": "Fully correlated against track dyno data. Released for testing.",
            }
        }
        resp = await client.post(
            "/api/v1/reports/decision_report",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        headers = resp.headers
        assert headers.get("X-Governance-Attributes") == "13"
        assert "X-Ed25519-Signature" in headers
        assert "X-Authority-Public-Key" in headers
        assert "X-Approval-Signature" in headers

        ed25519_sig = headers["X-Ed25519-Signature"]
        pubkey_hex = headers["X-Authority-Public-Key"]
        res_hash = headers["X-Result-Hash"]
        appr_time = headers["X-Approval-Time"]

        # Verify the signature independently using the exported public key
        gov_dict = report_service.build_canonical_governance_dict(
            authenticated_user=str(user_uuid),
            authorized_role="CHIEF_ENGINEER",
            organization=str(org_uuid),
            team=str(team_uuid),
            report_id=run_label,
            report_version="BUILD-REL-2026.1",
            simulation_run=run_label,
            setup_version="SETUP-AERO-01",
            vehicle_version="CAR-TEST-F1",
            result_hash=res_hash,
            validation_state="VALIDATED",
            timestamp=appr_time,
            decision="APPROVED_FOR_TEST_TRACK",
        )
        gov_payload = report_service.canonicalize_governance_payload(gov_dict)

        verified = report_service.verify_approval_ed25519(gov_payload, ed25519_sig, pubkey_hex)
        assert verified is True, "Ed25519 independent signature verification failed."


# ── Test 4: Decision Report Verification Endpoint with Ed25519 ───────────────

@pytest.mark.asyncio
async def test_decision_report_verify_endpoint_catches_tampering():
    """Verify /reports/decision_report/verify validates authentic signatures and catches tampering."""
    user_uuid = uuid.uuid4()
    org_uuid = uuid.uuid4()
    team_uuid = uuid.uuid4()

    async with SessionLocal() as db:
        org = Organization(id=org_uuid, name="Test Org", slug=f"org-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        db.add(org)
        user = User(
            id=user_uuid,
            email=f"chief-{uuid.uuid4().hex[:6]}@team.com",
            name="Chief",
            password_hash=hash_password("Pass123!"),
            organization_id=org_uuid,
            team_role="CHIEF_ENGINEER",
            org_role="ORG_ADMIN",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add(user)
        await db.flush()

        team = Team(
            id=team_uuid,
            organization_id=org_uuid,
            owner_id=user_uuid,
            name="Test Team",
            slug=f"team-{uuid.uuid4().hex[:6]}",
            plan="ENTERPRISE",
        )
        db.add(team)
        user.team_id = team_uuid
        await db.commit()

    token = create_access_token({
        "sub": str(user_uuid),
        "email": user.email,
        "team_role": "CHIEF_ENGINEER",
        "organization_id": str(org_uuid),
        "team_id": str(team_uuid),
        "plan": "ENTERPRISE",
    })

    sim_id = "SIM-CANONICAL-TEST-01"
    appr_time = "2026-09-05T12:00:00+00:00"
    res_hash = "f" * 64

    gov_dict = report_service.build_canonical_governance_dict(
        authenticated_user=str(user_uuid),
        authorized_role="CHIEF_ENGINEER",
        organization="ORG-TEST",
        team="TEAM-TEST",
        report_id=sim_id,
        report_version="v1.0",
        simulation_run=sim_id,
        setup_version="REV-01",
        vehicle_version="VEHICLE-01",
        result_hash=res_hash,
        validation_state="VALIDATED",
        timestamp=appr_time,
        decision="APPROVED_FOR_TRACK",
    )
    gov_payload = report_service.canonicalize_governance_payload(gov_dict)
    ed25519_sig = report_service.compute_approval_ed25519(gov_payload)
    pubkey = report_service.get_authority_public_key_hex()

    hmac_sig = report_service.compute_approval_hmac(
        report_id=sim_id,
        user_id=str(user_uuid),
        user_role="CHIEF_ENGINEER",
        status="APPROVED_FOR_TRACK",
        artifact_hash=res_hash,
        timestamp_iso=appr_time,
        organization="ORG-TEST",
        team="TEAM-TEST",
        report_version="v1.0",
        simulation_run=sim_id,
        setup_version="REV-01",
        vehicle_version="VEHICLE-01",
        result_hash=res_hash,
        validation_state="VALIDATED",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Case 1: Authentic payload
        verify_payload = {
            "sim_id": sim_id,
            "user_id": str(user_uuid),
            "approver_email": user.email,
            "approver_role": "CHIEF_ENGINEER",
            "approval_decision": "APPROVED_FOR_TRACK",
            "result_hash": res_hash,
            "approval_time": appr_time,
            "signature": hmac_sig,
            "organization": "ORG-TEST",
            "team": "TEAM-TEST",
            "report_id": sim_id,
            "report_version": "v1.0",
            "simulation_run": sim_id,
            "setup_version": "REV-01",
            "vehicle_version": "VEHICLE-01",
            "validation_state": "VALIDATED",
            "ed25519_signature": ed25519_sig,
            "public_key_hex": pubkey,
        }

        resp = await client.post(
            "/api/v1/reports/decision_report/verify",
            json=verify_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["signature_valid"] is True
        assert data["tamper_detected"] is False
        assert data["ed25519_valid"] is True

        # Case 2: Tampered result hash
        tampered_payload = dict(verify_payload)
        tampered_payload["result_hash"] = "e" * 64

        resp_t = await client.post(
            "/api/v1/reports/decision_report/verify",
            json=tampered_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        data_t = resp_t.json()
        assert data_t["signature_valid"] is False
        assert data_t["tamper_detected"] is True


# ── Test 5: RBAC Separation of Duty Enforcement ──────────────────────────────

def test_rbac_separation_of_duty_role_mapping():
    """Verify standard engineer lacks SETUP_APPROVE, while Chief Engineer has it."""
    eng_perms = ROLE_PERMISSIONS_MAP["engineer"]
    assert Permission.SETUP_APPROVE not in eng_perms, "Standard engineer must NOT possess SETUP_APPROVE."

    chief_perms = ROLE_PERMISSIONS_MAP["chief_engineer"]
    assert Permission.SETUP_APPROVE in chief_perms, "Chief Engineer must possess SETUP_APPROVE."

    lead_perms = ROLE_PERMISSIONS_MAP["lead_engineer"]
    assert Permission.SETUP_APPROVE in lead_perms, "Lead Engineer must possess SETUP_APPROVE."


@pytest.mark.asyncio
async def test_standard_engineer_rejected_from_release_approval():
    """Verify standard engineer receives HTTP 403 when attempting track sign-off."""
    eng_uuid = uuid.uuid4()
    org_uuid = uuid.uuid4()
    team_uuid = uuid.uuid4()

    async with SessionLocal() as db:
        org = Organization(id=org_uuid, name="Org", slug=f"org-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        db.add(org)
        eng_user = User(
            id=eng_uuid,
            email=f"junior-{uuid.uuid4().hex[:6]}@f1-team.com",
            name="Junior Engineer",
            password_hash=hash_password("Secret123!"),
            organization_id=org_uuid,
            team_role="ENGINEER",
            org_role="MEMBER",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add(eng_user)
        await db.flush()

        team = Team(
            id=team_uuid,
            organization_id=org_uuid,
            owner_id=eng_uuid,
            name="Team",
            slug=f"team-{uuid.uuid4().hex[:6]}",
            plan="ENTERPRISE",
        )
        db.add(team)
        eng_user.team_id = team_uuid

        run_label = f"RUN-ENG-{uuid.uuid4().hex[:6].upper()}"
        run = SimulationRun(
            id=uuid.uuid4(),
            seq=random.randint(100000, 999999),
            label=run_label,
            user_id=eng_uuid,
            team_id=team_uuid,
            simulation_type="quarter_car",
            vehicle_ref="CAR-TEST-F1",
            setup_ref="SETUP-AERO-01",
            track_ref="SILVERSTONE-2026",
            tire_ref="TIRE-SOFT-MF52",
            params={"m_s": 320.0, "k_s": 35000.0, "c": 2200.0},
            result={"rms_body_accel": 0.28, "rms_susp_travel": 0.012},
            model_validity={"validation_state": "VALIDATED", "correlation_pct": 94.5},
            params_hash="a" * 64,
            result_hash="b" * 64,
            solver_version="rk45-authoritative",
            physics_version="multibody-v3",
            software_version="BUILD-REL-2026.1",
        )
        db.add(run)
        await db.commit()

    token = create_access_token({
        "sub": str(eng_uuid),
        "email": eng_user.email,
        "team_role": "ENGINEER",
        "organization_id": str(org_uuid),
        "team_id": str(team_uuid),
        "plan": "ENTERPRISE",
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "run_label": run_label,
            "approval": {
                "decision": "APPROVED_FOR_TEST_TRACK",
                "comment": "Self-approving my own setup.",
            }
        }
        resp = await client.post(
            "/api/v1/reports/decision_report",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, f"Expected 403 Forbidden for standard engineer, got {resp.status_code}"
        assert "separation of duty" in resp.text.lower() or "lacks" in resp.text.lower()


# ── Test 6: Multi-DOF Simulation Protected by Compute Governance ─────────────

@pytest.mark.asyncio
async def test_full_car_and_half_car_concurrency_protection():
    """Verify simulate/full-car and simulate/half-car use bounded_run and respect concurrency limits."""
    with open("src/suspensionlab/backend/api/routes/simulate/half_car.py", "r", encoding="utf-8") as f:
        src_half = f.read()
    assert "bounded_run" in src_half
    assert "assert_user_concurrency" in src_half
    assert "except HTTPException:\n        raise" in src_half

    with open("src/suspensionlab/backend/api/routes/simulate/full_car.py", "r", encoding="utf-8") as f:
        src_full = f.read()
    assert "bounded_run" in src_full
    assert "assert_user_concurrency" in src_full
    assert "except HTTPException:\n        raise" in src_full


# ── Test 7: Docker Compose Worker Service ────────────────────────────────────

def test_docker_compose_worker_service():
    """Verify worker service is declared in docker-compose.yml running rq worker."""
    with open("docker-compose.yml", "r", encoding="utf-8") as f:
        dc = yaml.safe_load(f)

    services = dc.get("services", {})
    assert "worker" in services, "worker service missing from docker-compose.yml"

    worker_svc = services["worker"]
    command = worker_svc.get("command", "")
    cmd_str = " ".join(command) if isinstance(command, list) else str(command)
    assert "rq worker" in cmd_str, f"worker command must invoke rq worker, got: {command}"
    assert "redis" in worker_svc.get("depends_on", []), "worker must depend on redis"
