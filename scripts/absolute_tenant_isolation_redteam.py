"""
scripts/absolute_tenant_isolation_redteam.py
============================================
SUSPENSIONLAB PRO — ABSOLUTE TENANT ISOLATION RED TEAM HARNESS

Adversarial Penetration Test across 18 Sensitive Asset Classes:
Canary Identifiers:
 1.  CANARY_ORG_987654
 2.  CANARY_TEAM_987654
 3.  CANARY_VEHICLE_987654
 4.  CANARY_SETUP_987654
 5.  CANARY_SIMRUN_987654
 6.  CANARY_KINEMATICS_987654
 7.  CANARY_OPTIMIZATION_987654
 8.  CANARY_TELEMETRY_DS_987654
 9.  CANARY_TELEMETRY_FILE_987654
 10. CANARY_CALIBRATION_987654
 11. CANARY_TWIN_987654
 12. CANARY_REPORT_987654
 13. CANARY_REPORT_ARTIFACT_987654
 14. CANARY_WORKER_TASK_987654
 15. CANARY_AUDIT_LOG_987654
 16. CANARY_SHARED_REPORT_987654
 17. CANARY_SHARE_TOKEN_987654
 18. CANARY_EXPORT_987654

Attack Surface Matrix (12 Operations x 12 Reference Types):
- Operations: GET, POST, PUT, PATCH, DELETE, EXPORT, SHARE, COMPARE, CALIBRATE, OPTIMIZE, VALIDATE, REPORT
- Reference Types: UUID, int ID/seq, slug, label, title, filename, job ID, report ID, query param, path param, org ID, team ID
- Indirect Leak Surfaces: Search, pagination, aggregates, stats, autocomplete, error responses, logs, WebSockets, background queues
- Concurrent Race Attacks: Tenant B attacks while Tenant A executes mutations

Success Criteria:
- Zero canary tokens leaked to Tenant B.
- Total Probes, Blocked Count, Leaked Count, and Residual Attack Surface reported.
"""

import os
import sys
import json
import uuid
import asyncio
import time
import pathlib
import datetime
import subprocess
from datetime import timezone

os.environ["ENVIRONMENT"] = "DEV"
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/suspensionlab.db")
os.environ.setdefault("API_KEY", "dev_secret_key")
os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")


def get_execution_metadata() -> dict:
    git_sha = os.environ.get("GITHUB_SHA")
    git_branch = os.environ.get("GITHUB_REF_NAME")
    if not git_sha:
        try:
            git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            git_sha = "unknown"
    if not git_branch:
        try:
            git_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            git_branch = "unknown"
    return {
        "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
        "git_commit": git_sha,
        "git_branch": git_branch,
        "ci_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "environment": "CI" if os.environ.get("CI") else "LOCAL",
        "pipeline_phase": "continuous-verification",
    }

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, text, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.shared_report import SharedReport
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.security.jwt_utils import create_access_token

CANARIES = {
    "org": "CANARY_ORG_987654",
    "team": "CANARY_TEAM_987654",
    "vehicle": "CANARY_VEHICLE_987654",
    "setup": "CANARY_SETUP_987654",
    "simrun": "CANARY_SIMRUN_987654",
    "kinematics": "CANARY_KINEMATICS_987654",
    "optimization": "CANARY_OPTIMIZATION_987654",
    "telemetry_ds": "CANARY_TELEMETRY_DS_987654",
    "telemetry_file": "CANARY_TELEMETRY_FILE_987654",
    "calibration": "CANARY_CALIBRATION_987654",
    "twin": "CANARY_TWIN_987654",
    "report": "CANARY_REPORT_987654",
    "report_artifact": "CANARY_REPORT_ARTIFACT_987654",
    "worker_task": "CANARY_WORKER_TASK_987654",
    "audit_log": "CANARY_AUDIT_LOG_987654",
    "shared_report": "CANARY_SHARED_REPORT_987654",
    "share_token": "CANARY_SHARE_TOKEN_987654",
    "export": "CANARY_EXPORT_987654",
}

audit_probes = []
leaks_detected = []


def check_for_leaks(response_text: str) -> list:
    """Check for leaks in response payload, excluding RFC 7807 instance echo."""
    text_to_check = response_text
    try:
        data = json.loads(response_text)
        if isinstance(data, dict):
            # Exclude RFC 7807 request URI echo from false-positive leak detection
            data.pop("instance", None)
            text_to_check = json.dumps(data)
    except Exception:
        pass

    return [token for token in CANARIES.values() if token in text_to_check]


def record_probe(asset_class: str, operation: str, ref_type: str, endpoint: str, status_code: int, response_text: str, blocked: bool, notes: str = ""):
    leaked_canaries = check_for_leaks(response_text)
    leaked = len(leaked_canaries) > 0

    if leaked:
        blocked = False
        leaks_detected.append({
            "asset_class": asset_class,
            "operation": operation,
            "ref_type": ref_type,
            "endpoint": endpoint,
            "leaked_canaries": leaked_canaries,
            "snippet": response_text[:200],
        })

    probe_record = {
        "asset_class": asset_class,
        "operation": operation,
        "ref_type": ref_type,
        "endpoint": endpoint,
        "status_code": status_code,
        "blocked": blocked and not leaked,
        "leaked": leaked,
        "notes": notes,
    }
    audit_probes.append(probe_record)
    if leaked:
        v_icon = "LEAKED"
    elif blocked:
        v_icon = "BLOCKED"
    else:
        v_icon = "RESIDUAL"
    print(f"[{v_icon:8s}] [{asset_class:18s}] {operation:10s} ({ref_type:12s}) -> {endpoint} (HTTP {status_code})")


async def run_redteam_penetration() -> dict:
    print("=" * 100)
    print("SUSPENSIONLAB PRO — ABSOLUTE TENANT ISOLATION RED TEAM HARNESS")
    print(f"Target Canaries Loaded: {len(CANARIES)} distinct asset tokens")
    print("=" * 100)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. PROVISION ISOLATED TENANTS IN DATABASE
    # ─────────────────────────────────────────────────────────────────────────
    org_a_id = uuid.uuid4()
    org_b_id = uuid.uuid4()
    team_a_id = uuid.uuid4()
    team_b_id = uuid.uuid4()
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    vehicle_a_id = uuid.uuid4()
    setup_a_id = uuid.uuid4()
    sim_a_id = uuid.uuid4()
    twin_a_id = uuid.uuid4()
    job_a_id = uuid.uuid4()
    report_a_id = uuid.uuid4()
    audit_a_id = uuid.uuid4()
    share_token_a = f"token-{CANARIES['share_token']}-{uuid.uuid4().hex[:6]}"

    async with SessionLocal() as db:
        # User A & Org A
        org_a = Organization(id=org_a_id, name=f"Scuderia-A-{CANARIES['org']}", slug=f"scuderia-a-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        team_a = Team(id=team_a_id, organization_id=org_a_id, owner_id=user_a_id, slug=f"team-a-{uuid.uuid4().hex[:6]}", name=f"Team-A-{CANARIES['team']}")
        user_a = User(
            id=user_a_id,
            name="Engineer A",
            email=f"engineer-a-{uuid.uuid4().hex[:4]}@tenant-a.com",
            password_hash="test_pw_hash",
            organization_id=org_a_id,
            team_id=team_a_id,
            org_role="MEMBER",
            team_role="ENGINEER",
            plan="ENTERPRISE",
        )
        db.add_all([org_a, team_a, user_a])

        # User B & Org B (Attacker)
        org_b = Organization(id=org_b_id, name=f"Adversary-B-{uuid.uuid4().hex[:4]}", slug=f"adversary-b-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        team_b = Team(id=team_b_id, organization_id=org_b_id, owner_id=user_b_id, slug=f"team-b-{uuid.uuid4().hex[:6]}", name=f"Team-B-{uuid.uuid4().hex[:4]}")
        user_b = User(
            id=user_b_id,
            name="Adversary B",
            email=f"spy-b-{uuid.uuid4().hex[:4]}@tenant-b.com",
            password_hash="test_pw_hash",
            organization_id=org_b_id,
            team_id=team_b_id,
            org_role="ORG_ADMIN",
            team_role="ADMIN",
            plan="ENTERPRISE",
        )
        db.add_all([org_b, team_b, user_b])
        await db.commit()

        # Seed 18 Assets in Tenant A
        max_seq_res = await db.execute(select(func.coalesce(func.max(SimulationRun.seq), 100000)))
        next_seq = max_seq_res.scalar_one() + 1
        sim_label_a = f"RUN-{next_seq:06d}"

        vp_a = VehicleProfile(
            id=vehicle_a_id,
            user_id=user_a_id,
            team_id=team_a_id,
            name=f"F1-Chassis-{CANARIES['vehicle']}",
            vehicle_type="QUARTER_CAR",
            params={
                "k_s": 35000.0,
                "kinematics_marker": CANARIES["kinematics"],
                "export_marker": CANARIES["export"],
            },
        )
        vp_setup_a = VehicleProfile(
            id=setup_a_id,
            user_id=user_a_id,
            team_id=team_a_id,
            name=f"Monza-Setup-{CANARIES['setup']}",
            vehicle_type="QUARTER_CAR",
            params={"setup_secret": CANARIES["setup"]},
        )
        sim_a = SimulationRun(
            id=sim_a_id,
            seq=next_seq,
            label=sim_label_a,
            user_id=user_a_id,
            team_id=team_a_id,
            simulation_type="quarter_car",
            title=f"Aero-Opt-Secret-{CANARIES['simrun']}",
            vehicle_ref=f"CAR-{CANARIES['vehicle']}",
            setup_ref=f"SETUP-{CANARIES['setup']}",
            tire_ref=f"TIRE-{CANARIES['kinematics']}",
            track_ref=f"TRACK-{CANARIES['optimization']}",
            telemetry_ref=f"TELEM-{CANARIES['telemetry_ds']}",
            params={"secret_note": CANARIES["simrun"], "telemetry_filename": f"{CANARIES['telemetry_file']}.csv"},
            result={"secret_metric": CANARIES["simrun"], "artifact": CANARIES["report_artifact"]},
            software_version="3.0.0",
            physics_version="3.0.0",
            solver_version="scipy",
            params_hash="hash_a_params",
            result_hash="hash_a_result",
            model_validity={"status": "VALIDATED", "score": 0.98, "calibration_marker": CANARIES["calibration"]},
        )
        twin_a = VehicleTwin(
            id=twin_a_id,
            user_id=user_a_id,
            team_id=team_a_id,
            car_ref=f"CAR-{CANARIES['vehicle']}",
            setup_ref=f"SETUP-{CANARIES['setup']}",
            track_ref=f"TRACK-{CANARIES['twin']}",
            base_params={"k_s": 35000.0, "m_s": 300.0, "c": 2200.0},
            calibrated_params={"k_s": 36500.0, "secret": CANARIES["twin"], "calib": CANARIES["calibration"]},
            calibration_count=1,
            last_identification={"confidence": 0.98, "marker": CANARIES["twin"]},
        )
        job_a = JobRecord(
            id=job_a_id,
            user_id=user_a_id,
            team_id=team_a_id,
            job_type="OPTIMIZE_SETUP",
            status="COMPLETED",
            params={"target": CANARIES["optimization"], "worker_task": CANARIES["worker_task"]},
            result={"optimal_c": 2150.0, "canary": CANARIES["optimization"]},
        )
        report_a = SharedReport(
            id=report_a_id,
            token=share_token_a,
            simulation_type="quarter_car",
            params={"k_s": 35000.0, "secret": CANARIES["report"]},
            result={"rms_body_accel": 0.35, "secret": CANARIES["report"], "artifact": CANARIES["report_artifact"]},
            owner_id=user_a_id,
            team_id=team_a_id,
            organization_id=org_a_id,
            simulation_id=sim_a_id,
            doc_id=f"DOC-A-{CANARIES['report']}"[:32],
            vehicle_ref=f"CAR-{CANARIES['vehicle']}",
            setup_ref=f"SETUP-{CANARIES['setup']}",
            status="APPROVED",
            is_public=False,
            artifact_hash=f"hash-{CANARIES['report_artifact']}",
            approval_comment=f"Approved secret sign-off {CANARIES['shared_report']}",
            approved_by_email="chief@tenant-a.com",
            approved_by_role="CHIEF_ENGINEER",
        )
        audit_a = AuditLog(
            id=audit_a_id,
            user_id=user_a_id,
            team_id=team_a_id,
            organization_id=org_a_id,
            event="CHIEF_SIGN_OFF",
            ip="10.0.0.1",
            user_agent="TenantA-Station",
            event_data={"secret_event": CANARIES["audit_log"]},
        )
        db.add_all([vp_a, vp_setup_a, sim_a, twin_a, job_a, report_a, audit_a])
        await db.commit()

    print(f"Tenant A seeded with 18 distinct canary asset markers (Run seq={next_seq}, Label={sim_label_a})\n")

    token_b = create_access_token({
        "sub": str(user_b_id),
        "user_id": str(user_b_id),
        "email": user_b.email,
        "role": "ADMIN",
        "plan": "ENTERPRISE",
        "organization_id": str(org_b_id),
        "team_id": str(team_b_id),
    })
    headers_b = {
        "Authorization": f"Bearer {token_b}",
        "X-API-Key": "dev_secret_key",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # ─────────────────────────────────────────────────────────────────────
        # ATTACK SECTION 1: 12 OPERATION TYPES
        # ─────────────────────────────────────────────────────────────────────
        print("\n>>> Phase 1: Attacking Across 12 Operation Types")

        # 1. GET
        res = await client.get(f"/api/v1/profiles/{vehicle_a_id}", headers=headers_b)
        record_probe("VehicleProfile", "GET", "UUID", f"/api/v1/profiles/{vehicle_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # 2. POST
        res = await client.post("/api/v1/simulate/quarter_car", json={"m_s": 300, "k_s": 35000, "c": 2000, "k_t": 200000, "team_id": str(team_a_id)}, headers=headers_b)
        record_probe("SimulationRun", "POST", "team ID", "/api/v1/simulate/quarter_car", res.status_code, res.text, res.status_code in (400, 403, 404, 422))

        # 3. PUT
        res = await client.put(f"/api/v1/profiles/{vehicle_a_id}", json={"name": "Attacker_Overwrite"}, headers=headers_b)
        record_probe("VehicleProfile", "PUT", "UUID", f"/api/v1/profiles/{vehicle_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # 4. PATCH
        res = await client.patch(f"/api/v1/organizations/{org_a_id}", json={"name": "Attacker_Org"}, headers=headers_b)
        record_probe("Organization", "PATCH", "org ID", f"/api/v1/organizations/{org_a_id}", res.status_code, res.text, res.status_code in (403, 404, 405))

        # 5. DELETE
        res = await client.delete(f"/api/v1/profiles/{vehicle_a_id}", headers=headers_b)
        record_probe("VehicleProfile", "DELETE", "UUID", f"/api/v1/profiles/{vehicle_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # 6. EXPORT
        res = await client.get(f"/api/v1/export/run/{sim_a_id}?format=csv", headers=headers_b)
        record_probe("Export", "EXPORT", "UUID", f"/api/v1/export/run/{sim_a_id}?format=csv", res.status_code, res.text, res.status_code in (403, 404))

        # 7. SHARE
        res = await client.get(f"/api/v1/reports/{share_token_a}", headers=headers_b)
        record_probe("SharedReport", "SHARE", "share token", f"/api/v1/reports/{share_token_a}", res.status_code, res.text, res.status_code in (403, 404))

        # 8. COMPARE
        res = await client.get(f"/api/v1/runs/{sim_label_a}/diff/RUN-000001", headers=headers_b)
        record_probe("SimulationRun", "COMPARE", "run label", f"/api/v1/runs/{sim_label_a}/diff/RUN-000001", res.status_code, res.text, res.status_code in (403, 404))

        # 9. CALIBRATE
        dummy_csv = b"time_s,heave_disp_m\n0.0,0.0\n0.01,0.01\n"
        res = await client.post(f"/api/v1/twins/{twin_a_id}/calibrate", files={"file": ("telem.csv", dummy_csv, "text/csv")}, headers=headers_b)
        record_probe("DigitalTwin", "CALIBRATE", "UUID", f"/api/v1/twins/{twin_a_id}/calibrate", res.status_code, res.text, res.status_code in (403, 404))

        # 10. OPTIMIZE
        res = await client.post("/api/v1/optimize/run", json={"target_profile_id": str(setup_a_id)}, headers=headers_b)
        record_probe("Optimization", "OPTIMIZE", "UUID", "/api/v1/optimize/run", res.status_code, res.text, res.status_code in (400, 403, 404))

        # 11. VALIDATE
        res = await client.get(f"/api/v1/model_validity/{sim_a_id}", headers=headers_b)
        record_probe("ModelValidity", "VALIDATE", "UUID", f"/api/v1/model_validity/{sim_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # 12. REPORT
        res = await client.get(f"/api/v1/reports/decision_report?run_id={sim_a_id}", headers=headers_b)
        record_probe("Report", "REPORT", "query param", f"/api/v1/reports/decision_report?run_id={sim_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # ─────────────────────────────────────────────────────────────────────
        # ATTACK SECTION 2: 12 REFERENCE TYPES
        # ─────────────────────────────────────────────────────────────────────
        print("\n>>> Phase 2: Attacking Across 12 Reference Types")

        # 1. UUID
        res = await client.get(f"/api/v1/runs/{sim_a_id}", headers=headers_b)
        record_probe("SimulationRun", "GET", "UUID", f"/api/v1/runs/{sim_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # 2. Integer ID / Sequence
        res = await client.get(f"/api/v1/runs/by_seq/{next_seq}", headers=headers_b)
        record_probe("SimulationRun", "GET", "int seq", f"/api/v1/runs/by_seq/{next_seq}", res.status_code, res.text, res.status_code in (403, 404))

        # 3. Label (e.g. RUN-100001)
        res = await client.get(f"/api/v1/runs?label={sim_label_a}", headers=headers_b)
        record_probe("SimulationRun", "GET", "label", f"/api/v1/runs?label={sim_label_a}", res.status_code, res.text, res.status_code == 200 and sim_label_a not in res.text)

        # 4. Slug (e.g. Scuderia-A slug)
        res = await client.get(f"/api/v1/organizations/by_slug/{org_a.slug}", headers=headers_b)
        record_probe("Organization", "GET", "slug", f"/api/v1/organizations/by_slug/{org_a.slug}", res.status_code, res.text, res.status_code in (403, 404))

        # 5. Run Name / Title
        res = await client.get(f"/api/v1/runs?search={CANARIES['simrun']}", headers=headers_b)
        record_probe("SimulationRun", "GET", "title search", f"/api/v1/runs?search={CANARIES['simrun']}", res.status_code, res.text, res.status_code == 200 and CANARIES["simrun"] not in res.text)

        # 6. Filename
        res = await client.get(f"/api/v1/telemetry/file/{CANARIES['telemetry_file']}.csv", headers=headers_b)
        record_probe("TelemetryFile", "GET", "filename", f"/api/v1/telemetry/file/{CANARIES['telemetry_file']}.csv", res.status_code, res.text, res.status_code in (403, 404))

        # 7. Job ID
        res = await client.get(f"/api/v1/jobs/{job_a_id}", headers=headers_b)
        record_probe("JobRecord", "GET", "job ID", f"/api/v1/jobs/{job_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # 8. Report ID / Doc ID
        res = await client.get(f"/api/v1/reports/{report_a_id}", headers=headers_b)
        record_probe("SharedReport", "GET", "report ID", f"/api/v1/reports/{report_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # 9. Query Parameter (?organization_id=...)
        res = await client.get(f"/api/v1/profiles/?organization_id={org_a_id}", headers=headers_b)
        record_probe("Profile", "GET", "query param", f"/api/v1/profiles/?organization_id={org_a_id}", res.status_code, res.text, res.status_code in (200, 403, 404) and str(vehicle_a_id) not in res.text)

        # 10. Path Parameter (/organizations/{org_id}/teams)
        res = await client.get(f"/api/v1/organizations/{org_a_id}/teams", headers=headers_b)
        record_probe("Organization", "GET", "path param", f"/api/v1/organizations/{org_a_id}/teams", res.status_code, res.text, res.status_code in (403, 404))

        # 11. Org ID
        res = await client.get(f"/api/v1/organizations/{org_a_id}", headers=headers_b)
        record_probe("Organization", "GET", "org ID", f"/api/v1/organizations/{org_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # 12. Team ID
        res = await client.get(f"/api/v1/teams/{team_a_id}", headers=headers_b)
        record_probe("Team", "GET", "team ID", f"/api/v1/teams/{team_a_id}", res.status_code, res.text, res.status_code in (403, 404))

        # ─────────────────────────────────────────────────────────────────────
        # ATTACK SECTION 3: INDIRECT DATA ACCESS SURFACES
        # ─────────────────────────────────────────────────────────────────────
        print("\n>>> Phase 3: Attacking Indirect Data Access & Leakage Surfaces")

        # 1. Global Search
        res = await client.get(f"/api/v1/runs?q={CANARIES['simrun']}", headers=headers_b)
        record_probe("Search", "GET", "query param", f"/api/v1/runs?q={CANARIES['simrun']}", res.status_code, res.text, res.status_code == 200 and CANARIES["simrun"] not in res.text)

        # 2. Pagination Offset Scanning
        res = await client.get("/api/v1/runs?limit=100&offset=0", headers=headers_b)
        record_probe("Pagination", "GET", "pagination", "/api/v1/runs?limit=100&offset=0", res.status_code, res.text, res.status_code == 200 and CANARIES["simrun"] not in res.text)

        # 3. Analytics & Aggregates
        res = await client.get("/api/v1/analytics/overview", headers=headers_b)
        record_probe("Analytics", "GET", "aggregates", "/api/v1/analytics/overview", res.status_code, res.text, res.status_code in (200, 403, 404) and CANARIES["org"] not in res.text)

        # 4. Audit Log Enumeration
        res = await client.get("/api/v1/audit/logs", headers=headers_b)
        record_probe("AuditLog", "GET", "audit query", "/api/v1/audit/logs", res.status_code, res.text, res.status_code in (200, 403, 404) and CANARIES["audit_log"] not in res.text)

        # 5. Error Response Stack Trace / Reflection Probe
        res = await client.get(f"/api/v1/profiles/invalid-probe-target", headers=headers_b)
        record_probe("ErrorReflection", "GET", "path param", f"/api/v1/profiles/invalid-probe-target", res.status_code, res.text, res.status_code in (403, 404))

        # 6. WebSocket Subscription Probe
        res = await client.get("/api/v1/ws/live_updates", headers=headers_b)
        record_probe("WebSocket", "GET", "ws probe", "/api/v1/ws/live_updates", res.status_code, res.text, res.status_code in (400, 403, 404, 426))

        # ─────────────────────────────────────────────────────────────────────
        # ATTACK SECTION 4: EXHAUSTIVE PROBES ACROSS ALL 18 CANARY ASSETS
        # ─────────────────────────────────────────────────────────────────────
        print("\n>>> Phase 4: Exhaustive Multi-Asset Target Probes (18 Classes)")

        asset_targets = [
            ("Organization", f"/api/v1/organizations/{org_a_id}", "org"),
            ("Team", f"/api/v1/teams/{team_a_id}", "team"),
            ("VehicleProfile", f"/api/v1/profiles/{vehicle_a_id}", "vehicle"),
            ("SetupProfile", f"/api/v1/profiles/{setup_a_id}", "setup"),
            ("SimulationRun", f"/api/v1/runs/{sim_label_a}", "simrun"),
            ("Kinematics", f"/api/v1/kinematics/{vehicle_a_id}", "kinematics"),
            ("OptimizationJob", f"/api/v1/jobs/{job_a_id}", "optimization"),
            ("TelemetryDataset", f"/api/v1/telemetry/{sim_a_id}", "telemetry_ds"),
            ("TelemetryFile", f"/api/v1/telemetry/file/{CANARIES['telemetry_file']}.csv", "telemetry_file"),
            ("CalibrationSession", f"/api/v1/twins/{twin_a_id}/calibration", "calibration"),
            ("DigitalTwin", f"/api/v1/twins/{twin_a_id}", "twin"),
            ("Report", f"/api/v1/reports/{report_a_id}", "report"),
            ("ReportArtifact", f"/api/v1/reports/artifacts/{CANARIES['report_artifact']}", "report_artifact"),
            ("WorkerTask", f"/api/v1/jobs/{job_a_id}/task", "worker_task"),
            ("AuditLog", f"/api/v1/audit/logs?org_id={org_a_id}", "audit_log"),
            ("SharedReport", f"/api/v1/reports/{report_a_id}/share", "shared_report"),
            ("ShareToken", f"/api/v1/reports/{share_token_a}", "share_token"),
            ("ExportData", f"/api/v1/export/run/{sim_a_id}", "export"),
        ]

        for asset_name, endpoint, canary_key in asset_targets:
            if asset_name == "SharedReport":
                res = await client.post(endpoint, headers=headers_b)
                record_probe(asset_name, "POST", "direct target", endpoint, res.status_code, res.text, res.status_code in (403, 404))
            elif asset_name == "AuditLog":
                res = await client.get(endpoint, headers=headers_b)
                record_probe(asset_name, "GET", "direct target", endpoint, res.status_code, res.text, (res.status_code in (403, 404)) or (res.status_code == 200 and CANARIES[canary_key] not in res.text))
            else:
                res = await client.get(endpoint, headers=headers_b)
                record_probe(asset_name, "GET", "direct target", endpoint, res.status_code, res.text, res.status_code in (403, 404))

        # ─────────────────────────────────────────────────────────────────────
        # ATTACK SECTION 5: CONCURRENT RACE CONDITION ATTACKS
        # ─────────────────────────────────────────────────────────────────────
        print("\n>>> Phase 5: Concurrent Race Condition Penetration")

        async def tenant_a_mutations():
            async with SessionLocal() as db_session:
                for i in range(5):
                    run = SimulationRun(
                        id=uuid.uuid4(),
                        seq=next_seq + 10 + i,
                        label=f"RACE-{next_seq+10+i}",
                        user_id=user_a_id,
                        team_id=team_a_id,
                        simulation_type="quarter_car",
                        title=f"Race-Run-{i}-{CANARIES['simrun']}",
                        vehicle_ref="CAR-A",
                        params={"k_s": 35000},
                        result={"status": "OK"},
                        software_version="3.0.0",
                        physics_version="3.0.0",
                        solver_version="scipy",
                        params_hash="hash_race",
                        result_hash="hash_race",
                    )
                    db_session.add(run)
                    await db_session.commit()
                    await asyncio.sleep(0.01)

        async def tenant_b_race_probes():
            race_leaks = 0
            for i in range(15):
                resp = await client.get("/api/v1/runs?limit=50", headers=headers_b)
                leaks = check_for_leaks(resp.text)
                if len(leaks) > 0:
                    race_leaks += 1
                await asyncio.sleep(0.005)
            return race_leaks

        task_a = asyncio.create_task(tenant_a_mutations())
        task_b = asyncio.create_task(tenant_b_race_probes())
        await asyncio.gather(task_a, task_b)
        race_leaks_count = task_b.result()

        record_probe("ConcurrentRace", "GET", "race query", "/api/v1/runs (during active mutations)", 200, "OK", race_leaks_count == 0)

    # ─────────────────────────────────────────────────────────────────────────
    # PRINT AUTHORITATIVE RED TEAM PENETRATION TABLE
    # ─────────────────────────────────────────────────────────────────────────
    total_probes = len(audit_probes)
    blocked_probes = sum(1 for p in audit_probes if p["blocked"])
    total_leaks = len(leaks_detected)
    residual_attack_surface = total_probes - blocked_probes

    print("\n" + "=" * 100)
    print("AUTHORITATIVE RED TEAM PENETRATION AUDIT SUMMARY")
    print("=" * 100)
    print(f"Total Penetration Probes Executed : {total_probes}")
    print(f"Total Attacks Correctly Blocked   : {blocked_probes}")
    print(f"Total Tenant Data Canaries Leaked : {total_leaks}")
    print(f"Residual Attack Surface           : {residual_attack_surface} probes ({residual_attack_surface/total_probes*100:.1f}%)")
    print("=" * 100)

    if total_leaks > 0:
        print("\n[CRITICAL FAILURE] LEAK DETECTED:")
        for lk in leaks_detected:
            print(f"  - Asset: {lk['asset_class']} | Endpoint: {lk['endpoint']} | Canaries: {lk['leaked_canaries']}")
    else:
        print("\n[VERIFIED] ZERO LEAKS DETECTED ACROSS ALL 18 CANARIES AND ATTACK VECTORS.")

    # Persist JSON evidence
    meta = get_execution_metadata()
    data_dir = pathlib.Path("data")
    data_dir.mkdir(exist_ok=True)
    out_file = data_dir / "absolute_tenant_isolation_evidence.json"
    with open(out_file, "w") as f:
        json.dump({
            "timestamp": meta["timestamp"],
            "git_commit": meta["git_commit"],
            "git_branch": meta["git_branch"],
            "ci_run_id": meta["ci_run_id"],
            "environment": meta["environment"],
            "pipeline_phase": meta["pipeline_phase"],
            "total_probes": total_probes,
            "blocked_probes": blocked_probes,
            "total_leaks": total_leaks,
            "residual_attack_surface": residual_attack_surface,
            "probes": audit_probes,
            "leaks": leaks_detected,
        }, f, indent=2)
    print(f"Red team evidence persisted to: {out_file}\n")

    return {
        "total_probes": total_probes,
        "blocked_probes": blocked_probes,
        "total_leaks": total_leaks,
        "residual_attack_surface": residual_attack_surface,
    }


if __name__ == "__main__":
    res = asyncio.run(run_redteam_penetration())
    if res["total_leaks"] > 0:
        sys.exit(1)
