"""
tests/test_trial_system.py
==========================
Comprehensive automated test suite for SuspensionLab PRO 7-Day Evaluation Architecture.

Tests cover:
1. Trial creation and evaluation workspace seeding (GT3 twin, profile, telemetry, question, simulation).
2. Trial login, JWT claims (is_trial=True), and frontend routing (/evaluation).
3. Trial workspace API retrieval with genuine backend objects.
4. Server-authoritative 7-day expiration enforcement (browser clock untrusted).
5. Simulation quota enforcement (50 runs limit) with 4-part structured response.
6. Vehicle project limit enforcement (1 vehicle limit).
7. Tenant isolation and IDOR prevention between trial tenants and standard tenants.
8. Role & permission boundaries (blocked from admin/retention/organization mutations).
9. Existing enterprise/pro user zero-regression verification (/quarter-car routing).
10. Clean trial deletion mechanism with dry_run safety by default.
11. Filesystem traversal prevention and path leakage protection.
"""
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.models.trial import Trial
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.session import SimSession
from suspensionlab.backend.database.models.engineering_question import EngineeringQuestion
from suspensionlab.backend.database.models.experiment import ExperimentRecord
from suspensionlab.backend.services.trial_service import TrialService


# ─── Helper Functions ────────────────────────────────────────────────────────

async def register_trial_helper(client: AsyncClient, email: str, org_name: str = "Apex GT3 Racing"):
    resp = await client.post(
        "/api/v1/trials/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "name": "Evaluation Engineer",
            "organization_name": org_name,
        },
    )
    return resp


# ─── Test Suite ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trial_creation_and_workspace_seeding(client: AsyncClient, db_session: AsyncSession):
    """
    Verify that trial registration provisions:
    - Organization with plan="TRIAL"
    - User with role="EVALUATOR"
    - Trial record with exact 7-day expiration and quotas (50 runs, 1 vehicle, 50MB)
    - Seeded real Porsche 911 GT3 R twin, setup profile, telemetry session, question, baseline experiment
    """
    resp = await register_trial_helper(client, "test_evaluator_1@apex.com", "Apex Motorsport GT3")
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["email"] == "test_evaluator_1@apex.com"
    assert data["is_trial"] is True
    assert data["redirect_url"] == "/evaluation"
    assert "token" in data
    assert "refresh_token" in data

    trial_info = data["trial"]
    assert trial_info["status"] == "ACTIVE"
    assert trial_info["simulation_run_limit"] == 50
    assert trial_info["vehicle_project_limit"] == 1
    assert trial_info["telemetry_storage_limit_bytes"] == 50 * 1024 * 1024
    assert trial_info["days_remaining"] == 7

    # Verify seeded records exist in DB
    user_uuid = uuid.UUID(str(data["user_id"]))
    trial_stmt = select(Trial).where(Trial.user_id == user_uuid)
    trial_res = (await db_session.execute(trial_stmt)).scalars().first()
    assert trial_res is not None
    assert trial_res.organization_id is not None
    org_id = trial_res.organization_id

    # Verify seeded vehicle twin (user_id scoped)
    twin_stmt = select(VehicleTwin).where(VehicleTwin.user_id == user_uuid)
    twins = (await db_session.execute(twin_stmt)).scalars().all()
    assert len(twins) == 1
    assert "SLP-FS-EV-01" in twins[0].car_ref

    # Verify seeded profiles (Setups A, B, C)
    prof_stmt = select(VehicleProfile).where(VehicleProfile.user_id == user_uuid)
    profiles = (await db_session.execute(prof_stmt)).scalars().all()
    assert len(profiles) == 3
    assert any("Setup A" in p.name for p in profiles)
    assert any("Setup B" in p.name for p in profiles)
    assert any("Setup C" in p.name for p in profiles)

    # Verify seeded telemetry session
    session_stmt = select(SimSession).where(SimSession.owner_id == user_uuid)
    sessions = (await db_session.execute(session_stmt)).scalars().all()
    assert len(sessions) == 1
    assert "Michigan" in sessions[0].name

    # Verify seeded question & investigation
    q_stmt = select(EngineeringQuestion).where(EngineeringQuestion.organization_id == org_id)
    questions = (await db_session.execute(q_stmt)).scalars().all()
    assert len(questions) == 1
    assert "tire-load variation" in questions[0].title.lower()
    assert "investigation" in questions[0].context

    # Verify seeded experiment (user_id scoped)
    exp_stmt = select(ExperimentRecord).where(ExperimentRecord.user_id == user_uuid)
    exps = (await db_session.execute(exp_stmt)).scalars().all()
    assert len(exps) == 1
    assert "roll stiffness" in exps[0].hypothesis.lower()


@pytest.mark.asyncio
async def test_trial_login_and_auth_redirection(client: AsyncClient):
    """
    Verify that logging in via standard /api/v1/auth/login correctly detects trial users,
    populates is_trial=True and routes them to /evaluation.
    """
    reg_resp = await register_trial_helper(client, "login_test@apex.com")
    assert reg_resp.status_code == 201

    # Standard login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "login_test@apex.com", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert login_data["is_trial"] is True
    assert login_data["redirect_url"] == "/evaluation"
    assert login_data["trial_status"] == "ACTIVE"

    token = login_data["token"]
    # Verify /api/v1/auth/me
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["is_trial"] is True
    assert me_data["redirect_url"] == "/evaluation"
    assert me_data["trial_status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_trial_workspace_endpoint(client: AsyncClient):
    """
    Verify that GET /api/v1/trials/workspace returns complete evaluation payload
    with real backend objects and KPIs.
    """
    reg_resp = await register_trial_helper(client, "workspace_test@apex.com")
    token = reg_resp.json()["token"]

    ws_resp = await client.get(
        "/api/v1/trials/workspace",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ws_resp.status_code == 200
    ws = ws_resp.json()

    assert "trial" in ws
    assert ws["trial"]["status"] == "ACTIVE"
    assert ws["trial"]["days_remaining"] == 7

    assert "vehicle" in ws
    assert ws["vehicle"]["car_ref"] == "SLP-FS-EV-01"
    assert ws["vehicle"]["base_params"]["k_s"] == 35000.0

    assert "setups" in ws
    assert len(ws["setups"]) == 3

    assert "telemetry_dataset" in ws
    assert len(ws["telemetry_dataset"]["channels"]) == 101

    assert "investigation" in ws
    assert "what_is_happening" in ws["investigation"]
    assert "evidence" in ws["investigation"]

    assert "telemetry_session" in ws
    assert "Michigan" in ws["telemetry_session"]["name"]

    assert "engineering_question" in ws
    assert "tire-load variation" in ws["engineering_question"]["title"].lower()

    assert "baseline_simulation" in ws
    assert ws["baseline_simulation"]["kpis"] is not None
    assert "rms_body_accel" in ws["baseline_simulation"]["kpis"]


@pytest.mark.asyncio
async def test_trial_setups_and_pareto_optimization(client: AsyncClient):
    """
    Verify GET /api/v1/trials/setups and POST /api/v1/trials/optimize for Pareto multi-objective search.
    """
    reg_resp = await register_trial_helper(client, "pareto_test@apex.com")
    token = reg_resp.json()["token"]

    # 1. Test setups
    setups_resp = await client.get(
        "/api/v1/trials/setups",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert setups_resp.status_code == 200
    setups = setups_resp.json()
    assert len(setups) == 3
    assert any("Setup A" in s["name"] for s in setups)

    # 2. Test Pareto optimization
    opt_resp = await client.post(
        "/api/v1/trials/optimize",
        headers={"Authorization": f"Bearer {token}"},
        json={"param_ranges": {"k_s": [25000.0, 45000.0], "c": [1200.0, 2600.0]}},
    )
    assert opt_resp.status_code == 200
    opt_data = opt_resp.json()
    assert opt_data["status"] == "COMPLETED"
    assert "pareto_result" in opt_data
    assert "frontier" in opt_data["pareto_result"]
    assert len(opt_data["pareto_result"]["frontier"]) >= 1


@pytest.mark.asyncio
async def test_trial_decision_and_custom_question(client: AsyncClient):
    """
    Verify POST /api/v1/trials/decision (Decision Workflow Demo) and POST /api/v1/trials/questions.
    """
    reg_resp = await register_trial_helper(client, "decision_test@apex.com")
    token = reg_resp.json()["token"]

    # 1. Decision Creation
    dec_resp = await client.post(
        "/api/v1/trials/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": "Why is front tire-load variation increasing during aggressive corner entry?",
            "reason": "Damping reduction from 1,800 to 1,650 Ns/m attenuates contact patch spike.",
        },
    )
    assert dec_resp.status_code == 200
    dec_data = dec_resp.json()
    assert dec_data["decision_id"].startswith("DEC-FS-")
    assert dec_data["provenance_hash"] is not None

    # 2. Custom Question Creation
    q_resp = await client.post(
        "/api/v1/trials/questions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Evaluate rear heave spring compliance on high-speed curbs",
            "question_text": "Investigating third spring bump stop engagement over 30mm curb strike.",
        },
    )
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert q_data["question_id"].startswith("Q-USER-")


@pytest.mark.asyncio
async def test_trial_simulation_execution_and_counter(client: AsyncClient):
    """
    Verify that running a simulation via POST /api/v1/trials/simulate executes real physics,
    increments the quota counter, and returns real KPIs.
    """
    reg_resp = await register_trial_helper(client, "sim_test@apex.com")
    token = reg_resp.json()["token"]

    sim_resp = await client.post(
        "/api/v1/trials/simulate",
        json={
            "params": {"c": 2800.0, "k_s": 42000.0},
            "road_profile": {"profile_type": "kerb_strike", "height_mm": 50.0},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sim_resp.status_code == 200, sim_resp.text
    res = sim_resp.json()
    assert res["status"] == "COMPLETED"
    assert "kpis" in res
    assert res["kpis"]["rms_body_accel"] > 0
    assert res["quota"]["runs_used"] == 1
    assert res["quota"]["runs_remaining"] == 49


@pytest.mark.asyncio
async def test_trial_experiment_creation(client: AsyncClient):
    """
    Verify that creating an experiment via POST /api/v1/trials/experiment computes delta
    against baseline and increments simulation runs quota.
    """
    reg_resp = await register_trial_helper(client, "exp_test@apex.com")
    token = reg_resp.json()["token"]

    exp_resp = await client.post(
        "/api/v1/trials/experiment",
        json={
            "question": "EQ-EVAL-01: Low-Speed Kerb Strike Stability",
            "hypothesis": "Increasing damper rating to 2800 Ns/m suppresses secondary wheel hop",
            "parameter_changes": {"c": 2800.0},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert exp_resp.status_code == 200, exp_resp.text
    data = exp_resp.json()
    exp = data["experiment"]
    assert exp["status"] in ("COMPLETED", "VIOLATED")
    assert "improvements" in exp
    assert "candidate_metrics" in exp
    assert data["quota"]["runs_used"] == 1


@pytest.mark.asyncio
async def test_seven_day_expiry_server_authoritative(client: AsyncClient, db_session: AsyncSession):
    """
    Verify that server-side UTC time is authoritative. Setting expires_at in the past
    causes immediate mutation rejection with structured 4-part explanation.
    """
    reg_resp = await register_trial_helper(client, "expired_test@apex.com")
    user_uuid = uuid.UUID(str(reg_resp.json()["user_id"]))
    token = reg_resp.json()["token"]

    # Manually expire trial in database (simulate time travel / 7 days elapsed)
    trial_stmt = select(Trial).where(Trial.user_id == user_uuid)
    trial = (await db_session.execute(trial_stmt)).scalars().first()
    assert trial is not None
    trial.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    trial.status = "EXPIRED"
    await db_session.commit()

    # Attempt trial simulation
    sim_resp = await client.post(
        "/api/v1/trials/simulate",
        json={"params": {"c": 2500.0}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sim_resp.status_code == 403
    err = sim_resp.json()["detail"]
    assert err["error"] == "TRIAL_LIMIT_EXCEEDED"
    assert err["limit_type"] == "TRIAL_EXPIRED"

    # Verify structured 4-part message
    assert "what_limit_was_reached" in err
    assert "7-Day Evaluation Duration Expired" in err["what_limit_was_reached"]
    assert "current_usage" in err
    assert "what_remains_available" in err
    assert "how_to_request_continuation" in err
    assert "enterprise@suspensionlab.pro" in err["how_to_request_continuation"]

    # Attempt trial experiment
    exp_resp = await client.post(
        "/api/v1/trials/experiment",
        json={"question": "Test Exp", "parameter_changes": {"c": 2500.0}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert exp_resp.status_code == 403
    assert exp_resp.json()["detail"]["limit_type"] == "TRIAL_EXPIRED"


@pytest.mark.asyncio
async def test_simulation_quota_enforcement(client: AsyncClient, db_session: AsyncSession):
    """
    Verify that reaching the 50 simulation runs quota triggers HTTP 403 with structured 4-part message.
    """
    reg_resp = await register_trial_helper(client, "quota_test@apex.com")
    user_uuid = uuid.UUID(str(reg_resp.json()["user_id"]))
    token = reg_resp.json()["token"]

    # Set run count to 50
    trial_stmt = select(Trial).where(Trial.user_id == user_uuid)
    trial = (await db_session.execute(trial_stmt)).scalars().first()
    assert trial is not None
    trial.simulation_run_count = 50
    await db_session.commit()

    # Attempt simulation
    sim_resp = await client.post(
        "/api/v1/trials/simulate",
        json={"params": {"c": 2600.0}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sim_resp.status_code == 403
    err = sim_resp.json()["detail"]
    assert err["error"] == "TRIAL_LIMIT_EXCEEDED"
    assert err["limit_type"] == "SIMULATION_LIMIT"
    assert "50 runs limit" in err["what_limit_was_reached"]
    assert "Read-only access" in err["what_remains_available"][0]
    assert "enterprise@suspensionlab.pro" in err["how_to_request_continuation"]


@pytest.mark.asyncio
async def test_vehicle_project_quota_enforcement(client: AsyncClient, db_session: AsyncSession):
    """
    Verify that trial users cannot create additional vehicle projects (limit is 1).
    """
    reg_resp = await register_trial_helper(client, "vehicle_limit_test@apex.com")
    token = reg_resp.json()["token"]

    # Attempt to create another vehicle twin
    twin_resp = await client.post(
        "/api/v1/twins",
        json={
            "car_ref": "Ferrari-296-GT3",
            "setup_ref": "SETUP-SPA-R1",
            "base_params": {"m_s": 350.0, "k_s": 40000.0, "c": 2500.0},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert twin_resp.status_code == 403
    err = twin_resp.json()["detail"]
    assert err["error"] == "TRIAL_LIMIT_EXCEEDED"
    assert err["limit_type"] == "VEHICLE_LIMIT"
    assert "1 vehicle limit" in err["what_limit_was_reached"]


@pytest.mark.asyncio
async def test_tenant_isolation_and_idor_prevention(client: AsyncClient, db_session: AsyncSession):
    """
    Verify strict tenant isolation:
    - Tenant A cannot access Tenant B's vehicle twin or evaluation data.
    - Attempted IDOR returns 404 or 403.
    """
    # Create Tenant A
    resp_a = await register_trial_helper(client, "tenant_a@team-a.com", "Team A")
    token_a = resp_a.json()["token"]

    # Create Tenant B
    resp_b = await register_trial_helper(client, "tenant_b@team-b.com", "Team B")
    token_b = resp_b.json()["token"]
    user_b_uuid = uuid.UUID(str(resp_b.json()["user_id"]))

    # Get Tenant B's vehicle twin ID from DB
    trial_b = (await db_session.execute(select(Trial).where(Trial.user_id == user_b_uuid))).scalars().first()
    twin_b = (await db_session.execute(select(VehicleTwin).where(VehicleTwin.user_id == trial_b.user_id))).scalars().first()
    assert twin_b is not None

    # Tenant A tries to access Tenant B's vehicle twin
    access_resp = await client.get(
        f"/api/v1/twins/{twin_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    # Must be 404 (not found in tenant's org) or 403 (unauthorized)
    assert access_resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_trial_user_blocked_from_admin_and_org_mutations(client: AsyncClient):
    """
    Verify that trial users cannot create new organizations or trigger data retention purges.
    """
    reg_resp = await register_trial_helper(client, "admin_block_test@apex.com")
    token = reg_resp.json()["token"]

    # Attempt organization creation
    org_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Second Organization", "slug": "second-org"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert org_resp.status_code == 403
    assert "Trial evaluation accounts cannot create additional organizations" in org_resp.json()["detail"]

    # Attempt retention purge
    purge_resp = await client.post(
        "/api/v1/compliance/retention/purge",
        json={"dry_run": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert purge_resp.status_code == 403
    assert "Trial users cannot execute retention purge" in purge_resp.json()["detail"]


@pytest.mark.asyncio
async def test_existing_enterprise_user_regression_free_flow(client: AsyncClient, db_session: AsyncSession):
    """
    Verify that enterprise/pro users are unaffected by trial logic:
    - is_trial is False
    - redirect_url is /quarter-car
    - No 50-simulation limit applies
    """
    # Standard user registration
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "pro_engineer@enterprise.com", "password": "Password123!", "name": "Enterprise Pro"},
    )
    assert reg_resp.status_code == 201
    data = reg_resp.json()
    assert data["is_trial"] is False
    assert data["redirect_url"] == "/quarter-car"

    # Login check
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "pro_engineer@enterprise.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert login_data["is_trial"] is False
    assert login_data["redirect_url"] == "/quarter-car"

    # Me check
    token = login_data["token"]
    me_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["is_trial"] is False
    assert me_data["redirect_url"] == "/quarter-car"


@pytest.mark.asyncio
async def test_clean_trial_deletion_safety(client: AsyncClient, db_session: AsyncSession):
    """
    Verify clean trial deletion:
    - Non-admin user cannot trigger cleanup (403).
    - TrialService.cleanup_expired_trials with dry_run=True identifies candidates safely.
    - TrialService.cleanup_expired_trials with dry_run=False and force=True removes expired trial.
    """
    reg_resp = await register_trial_helper(client, "cleanup_test@apex.com")
    user_uuid = uuid.UUID(str(reg_resp.json()["user_id"]))
    token = reg_resp.json()["token"]

    # Non-admin attempting endpoint gets 403
    non_admin_resp = await client.post(
        "/api/v1/trials/cleanup",
        json={"grace_period_days": 30, "dry_run": True, "force": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert non_admin_resp.status_code == 403

    # Expire trial 35 days in the past (beyond 30-day grace period)
    trial_stmt = select(Trial).where(Trial.user_id == user_uuid)
    trial = (await db_session.execute(trial_stmt)).scalars().first()
    assert trial is not None
    org_id = trial.organization_id
    trial.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=35)
    trial.status = "EXPIRED"
    await db_session.commit()

    # Dry run cleanup via TrialService
    dry_res = await TrialService.cleanup_expired_trials(
        db=db_session,
        grace_period_days=30,
        dry_run=True,
        force=False,
    )
    assert dry_res["dry_run"] is True
    assert dry_res["candidates_count"] >= 1

    # Verify org still exists
    org_check = (await db_session.execute(select(Organization).where(Organization.id == org_id))).scalars().first()
    assert org_check is not None

    # Actual cleanup execution with force=True
    act_res = await TrialService.cleanup_expired_trials(
        db=db_session,
        grace_period_days=30,
        dry_run=False,
        force=True,
    )
    assert act_res["dry_run"] is False
    assert act_res["deleted_count"] >= 1

    # Verify trial record is deleted
    trial_after = (await db_session.execute(select(Trial).where(Trial.organization_id == org_id))).scalars().first()
    assert trial_after is None


@pytest.mark.asyncio
async def test_security_no_filesystem_leakage(client: AsyncClient):
    """
    Verify path traversal attacks to /telemetry/replay/start are rejected with 400
    and do not leak internal filesystem paths.
    """
    reg_resp = await register_trial_helper(client, "security_path_test@apex.com")
    token = reg_resp.json()["token"]

    traversal_paths = [
        "../../etc/passwd",
        r"..\..\..\windows\win.ini",
        "/etc/shadow",
        "....//....//config.json",
    ]
    for path in traversal_paths:
        resp = await client.post(
            "/api/v1/telemetry/replay/start",
            json={"session_id": "test_session", "dataset_path": path},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "Path traversal detected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trial_feedback_persistence(client: AsyncClient, db_session: AsyncSession):
    """
    Verify that customer discovery feedback persists to the trial organization and is reflected in workspace state.
    """
    reg_resp = await register_trial_helper(client, "feedback_test@apex.com", "Feedback Tester")
    token = reg_resp.json()["token"]
    u_id = uuid.UUID(str(reg_resp.json()["user_id"]))

    fb_resp = await client.post(
        "/api/v1/trials/feedback",
        json={
            "most_valuable_part": "Connected link between telemetry spike and candidate setup comparison.",
            "prevented_more_use": "Wanted custom road profile CSV upload directly in trial.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert fb_resp.status_code == 200
    fb_data = fb_resp.json()
    assert fb_data["status"] == "SAVED"
    assert fb_data["feedback"]["most_valuable_part"] == "Connected link between telemetry spike and candidate setup comparison."

    # Verify workspace reflection
    ws_resp = await client.get("/api/v1/trials/workspace", headers={"Authorization": f"Bearer {token}"})
    assert ws_resp.status_code == 200
    assert ws_resp.json()["feedback_submitted"] is True

    # Direct database verification
    trial = (await db_session.execute(select(Trial).where(Trial.user_id == u_id))).scalars().first()
    assert trial is not None
    assert trial.metadata_json is not None
    assert trial.metadata_json["feedback"]["most_valuable_part"] == "Connected link between telemetry spike and candidate setup comparison."


@pytest.mark.asyncio
async def test_trial_analytics_events(client: AsyncClient, db_session: AsyncSession):
    """
    Verify tracking of non-sensitive product analytics events on trial organization.
    """
    reg_resp = await register_trial_helper(client, "analytics_test@apex.com")
    token = reg_resp.json()["token"]
    u_id = uuid.UUID(str(reg_resp.json()["user_id"]))

    evt_resp = await client.post(
        "/api/v1/trials/events",
        json={
            "event_name": "question_opened",
            "properties": {"question_id": "q-fs-01", "severity": "CRITICAL"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert evt_resp.status_code == 200
    assert evt_resp.json()["status"] == "RECORDED"
    assert evt_resp.json()["event"] == "question_opened"

    # Verify database persistence
    trial = (await db_session.execute(select(Trial).where(Trial.user_id == u_id))).scalars().first()
    assert trial is not None
    assert len(trial.metadata_json.get("analytics_events", [])) >= 2  # initial evaluation_started + question_opened


@pytest.mark.asyncio
async def test_trial_checklist_backend_verification(client: AsyncClient):
    """
    Verify that the evaluation checklist is derived from actual database state.
    """
    reg_resp = await register_trial_helper(client, "checklist_test@apex.com")
    token = reg_resp.json()["token"]

    # Initial checklist
    chk_resp = await client.get("/api/v1/trials/checklist", headers={"Authorization": f"Bearer {token}"})
    assert chk_resp.status_code == 200
    chk_data = chk_resp.json()
    assert chk_data["total_count"] == 6
    assert chk_data["items"]["compare_setups"] is False
    assert chk_data["items"]["run_optimization"] is False
    assert chk_data["items"]["create_decision"] is False
    assert chk_data["items"]["try_own_question"] is False

    # 1. Log compare event
    await client.post(
        "/api/v1/trials/events",
        json={"event_name": "compare_completed"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 2. Run Pareto optimization
    opt_resp = await client.post(
        "/api/v1/trials/optimize",
        json={"param_ranges": {"k_s": [30000.0, 40000.0], "c": [1500.0, 2100.0]}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert opt_resp.status_code == 200

    # 3. Create Decision
    dec_resp = await client.post(
        "/api/v1/trials/decision",
        json={
            "question": "Front tire load variation spike resolution",
            "reason": "Optimal compromise between heave settle time and tire grip consistency",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dec_resp.status_code == 200

    # 4. Create Custom Question
    q_resp = await client.post(
        "/api/v1/trials/questions",
        json={
            "title": "Custom Aero Balance vs Ride Height Sensitivity",
            "question_text": "Investigate if lower rear ride height preserves mechanical grip without grounding.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert q_resp.status_code == 200

    # Verify updated checklist
    updated_chk = await client.get("/api/v1/trials/checklist", headers={"Authorization": f"Bearer {token}"})
    assert updated_chk.status_code == 200
    u_data = updated_chk.json()
    assert u_data["items"]["compare_setups"] is True
    assert u_data["items"]["run_optimization"] is True
    assert u_data["items"]["create_decision"] is True
    assert u_data["items"]["try_own_question"] is True
    assert u_data["completed_count"] >= 4

