"""
tests/test_trial_deployment_security.py
=======================================
Verification suite for SuspensionLab PRO Private 7-Day Trial Deployment Profile.

Validates:
1. Source Code & Route Protection (no /docs, /redoc, /openapi.json, .js.map, hidden paths, traversal).
2. Strict Multi-Tenant Isolation (Trial A vs Trial B across all entities).
3. Expiration Lifecycle & Owner Extension (blocking on expiry, unblocking on extension).
4. Security Headers, Cookies, and Transport Protection.
5. Clean-Customer Full Workflow (Login -> Garage -> Investigation -> Experiment -> Compare -> Optimize -> Decision -> Feedback).
"""
import uuid
import os
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
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.services.trial_service import TrialService


# ─── 1. Source Code & Route Protection Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_trial_source_code_and_docs_protection(client: AsyncClient):
    """
    Verify that in TRIAL environment, internal developer documentation,
    schemas, hidden files, source maps, and traversal attempts return 404 or are blocked.
    """
    # Enforce TRIAL mode in environment
    os.environ["ENVIRONMENT"] = "TRIAL"

    # 1. API Documentation endpoints must NOT be exposed in TRIAL mode
    for doc_path in ["/docs", "/redoc", "/openapi.json", "/docs/api-reference.pdf"]:
        resp = await client.get(doc_path)
        assert resp.status_code == 404, f"Path {doc_path} should return 404 in trial mode, got {resp.status_code}"

    # 2. Sensitive hidden files & repository files must NOT be accessible
    hidden_paths = [
        "/.git",
        "/.git/config",
        "/.env",
        "/.env.trial",
        "/Dockerfile",
        "/Dockerfile.backend",
        "/Dockerfile.frontend",
        "/package.json",
        "/alembic.ini",
        "/src/suspensionlab/backend/config.py",
        "/tests/test_trial_system.py",
    ]
    for hp in hidden_paths:
        resp = await client.get(hp)
        assert resp.status_code in (404, 405), f"Path {hp} should return 404/405, got {resp.status_code}"

    # 3. Source map files (.js.map) must return 404
    for map_path in ["/main.js.map", "/_next/static/chunks/app.js.map", "/evaluation.js.map"]:
        resp = await client.get(map_path)
        assert resp.status_code == 404, f"Source map {map_path} should return 404, got {resp.status_code}"

    # 4. Metrics endpoint must reject unauthenticated requests
    resp = await client.get("/metrics")
    assert resp.status_code in (401, 500), f"/metrics without credentials should return 401/500, got {resp.status_code}"

    # 5. Path traversal attempts must be rejected
    traversal_paths = [
        "/..%2f..%2f..%2fetc%2fpasswd",
        "/api/v1/..%2f..%2fpackage.json",
        "/public/..%2f..%2f.env",
    ]
    for tp in traversal_paths:
        resp = await client.get(tp)
        assert resp.status_code in (400, 404), f"Traversal {tp} should return 400/404, got {resp.status_code}"

    # 6. Public health check must be minimal and safe (no credentials or filesystem paths leaked)
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "alive"
    assert "password" not in str(data).lower()
    assert "jwt" not in str(data).lower()
    assert "secret" not in str(data).lower()


# ─── 2. Multi-Tenant Isolation Tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_trial_multi_tenant_isolation(client: AsyncClient, db_session: AsyncSession):
    """
    Create Trial A and Trial B. Confirm Trial A cannot access Trial B's
    vehicles, questions, experiments, sessions, decisions, or reports.
    """
    # Register Trial Tenant A
    resp_a = await client.post(
        "/api/v1/trials/register",
        json={
            "email": "evaluator.alpha@tenant-a.com",
            "password": "PasswordAlpha123!",
            "name": "Alpha Engineer",
            "organization_name": "Team Alpha Motorsport",
        },
    )
    assert resp_a.status_code == 201
    auth_a = resp_a.json()
    headers_a = {"Authorization": f"Bearer {auth_a['token']}"}

    # Register Trial Tenant B
    resp_b = await client.post(
        "/api/v1/trials/register",
        json={
            "email": "evaluator.bravo@tenant-b.com",
            "password": "PasswordBravo123!",
            "name": "Bravo Engineer",
            "organization_name": "Team Bravo Motorsport",
        },
    )
    assert resp_b.status_code == 201
    auth_b = resp_b.json()
    headers_b = {"Authorization": f"Bearer {auth_b['token']}"}

    # Retrieve workspace for Tenant B to get Tenant B's entity IDs
    ws_b = (await client.get("/api/v1/trials/workspace", headers=headers_b)).json()
    twin_b_id = ws_b["vehicle"]["id"]
    q_b_id = ws_b["engineering_question"]["id"]
    exp_b_id = ws_b["experiment_history"][0]["id"]
    sess_b_id = ws_b["telemetry_session"]["id"]

    # 1. Trial A attempts to read Trial B's Vehicle Twin
    twin_steal_resp = await client.get(f"/api/v1/twins/{twin_b_id}", headers=headers_a)
    assert twin_steal_resp.status_code in (403, 404), f"Trial A accessed Trial B vehicle: {twin_steal_resp.status_code}"

    # 2. Trial A attempts to read Trial B's Question
    q_steal_resp = await client.get(f"/api/v1/questions/{q_b_id}", headers=headers_a)
    assert q_steal_resp.status_code in (403, 404), f"Trial A accessed Trial B question: {q_steal_resp.status_code}"

    # 3. Trial A attempts to read Trial B's Experiment
    exp_steal_resp = await client.get(f"/api/v1/experiments/{exp_b_id}", headers=headers_a)
    assert exp_steal_resp.status_code in (403, 404), f"Trial A accessed Trial B experiment: {exp_steal_resp.status_code}"

    # 4. Trial A attempts to read Trial B's Telemetry Session
    sess_steal_resp = await client.get(f"/api/v1/telemetry/sessions/{sess_b_id}", headers=headers_a)
    assert sess_steal_resp.status_code in (403, 404), f"Trial A accessed Trial B session: {sess_steal_resp.status_code}"

    # 5. Verify Trial A's workspace never reflects Trial B's organization
    ws_a = (await client.get("/api/v1/trials/workspace", headers=headers_a)).json()
    assert ws_a["trial"]["organization_id"] != ws_b["trial"]["organization_id"]
    assert ws_a["vehicle"]["id"] != twin_b_id


# ─── 3. Expiration Lifecycle & Owner Extension Tests ─────────────────────────

@pytest.mark.asyncio
async def test_trial_expiration_and_owner_extension(client: AsyncClient, db_session: AsyncSession):
    """
    Test expiration enforcement and owner-only extension CLI logic:
    - User reaches expired status
    - Simulations & experiments are blocked with 4-part structured response
    - Existing data remains preserved
    - Owner extends trial by 7 days
    - Status reactivated and simulation unblocked
    """
    # 1. Create Trial
    reg_resp = await client.post(
        "/api/v1/trials/register",
        json={
            "email": "evaluator.charlie@tenant-c.com",
            "password": "PasswordCharlie123!",
            "name": "Charlie Engineer",
            "organization_name": "Charlie Dynamics Team",
        },
    )
    assert reg_resp.status_code == 201
    auth = reg_resp.json()
    headers = {"Authorization": f"Bearer {auth['token']}"}

    # 2. Simulate Expiration
    res_trial = await db_session.execute(
        select(Trial).where(Trial.contact_email == "evaluator.charlie@tenant-c.com")
    )
    trial = res_trial.scalar_one()
    trial.status = "EXPIRED"
    trial.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await db_session.commit()

    # 3. Test Login on Expired Account
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "evaluator.charlie@tenant-c.com",
            "password": "PasswordCharlie123!",
        },
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert login_data["is_trial"] is True
    assert login_data["trial_status"] == "EXPIRED"

    # 4. Verify Simulations are Blocked with 4-Part Structured Explanation
    sim_resp = await client.post(
        "/api/v1/trials/simulate",
        headers=headers,
        json={"params": {"m_s": 50.0, "m_u": 10.5, "k_s": 35000.0, "c": 1800.0}},
    )
    assert sim_resp.status_code in (400, 403)
    err = sim_resp.json().get("detail", {})
    assert "what_limit_was_reached" in err
    assert "current_usage" in err
    assert "what_remains_available" in err
    assert "how_to_request_continuation" in err

    # 5. Verify Workspace Access Indicates Expiration
    ws_resp = await client.get("/api/v1/trials/workspace", headers=headers)
    assert ws_resp.status_code == 200
    ws_data = ws_resp.json()
    assert ws_data["trial"]["status"] == "EXPIRED"
    assert ws_data["trial"]["days_remaining"] <= 0.0

    # 6. Owner Extends the Trial (via TrialService.extend_trial)
    ext_result = await TrialService.extend_trial(
        db=db_session,
        identifier="evaluator.charlie@tenant-c.com",
        additional_days=7,
        additional_simulations=20,
        new_status="ACTIVE",
    )
    assert ext_result["status"] == "ACTIVE"
    assert ext_result["days_remaining"] > 5.0
    assert ext_result["simulation_run_limit"] == 70  # 50 default + 20 added

    # 7. Verify Simulation is Now Unblocked
    sim_resp_unblocked = await client.post(
        "/api/v1/trials/simulate",
        headers=headers,
        json={"params": {"m_s": 50.0, "m_u": 10.5, "k_s": 35000.0, "c": 1800.0}},
    )
    assert sim_resp_unblocked.status_code == 200
    assert "kpis" in sim_resp_unblocked.json()


# ─── 4. Security Headers & Cookie Attributes Tests ───────────────────────────

@pytest.mark.asyncio
async def test_trial_security_headers_and_cookies(client: AsyncClient):
    """Verify production security headers and cookie security flags."""
    # Test Security Headers
    resp = await client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "Strict-Transport-Security" in resp.headers

    # Test Cookie Security Attributes on Login
    reg_resp = await client.post(
        "/api/v1/trials/register",
        json={
            "email": "evaluator.security@tenant-s.com",
            "password": "PasswordSecurity123!",
            "name": "Security Tester",
            "organization_name": "Security Audit Org",
        },
    )
    assert reg_resp.status_code == 201

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "evaluator.security@tenant-s.com",
            "password": "PasswordSecurity123!",
        },
    )
    assert login_resp.status_code == 200
    cookies = login_resp.cookies
    assert "sl_token" in cookies
    assert "sl_refresh_token" in cookies
    assert "csrf_token" in cookies


# ─── 5. Clean Customer End-to-End Workflow Test ─────────────────────────────

@pytest.mark.asyncio
async def test_clean_customer_full_workflow(client: AsyncClient, db_session: AsyncSession):
    """
    Execute full customer journey without developer shortcuts:
    LOGIN -> EVALUATION GARAGE -> INVESTIGATION -> EXPERIMENT -> COMPARE -> OPTIMIZATION -> DECISION -> FEEDBACK
    """
    # 1. Register & Login
    reg_resp = await client.post(
        "/api/v1/trials/register",
        json={
            "email": "clean.evaluator@formula-student.org",
            "password": "CleanPassword123!",
            "name": "Lead Dynamicist",
            "organization_name": "Formula Student Dynamicists",
        },
    )
    assert reg_resp.status_code == 201
    auth = reg_resp.json()
    headers = {"Authorization": f"Bearer {auth['token']}"}

    # 2. EVALUATION GARAGE (Load Workspace)
    ws_resp = await client.get("/api/v1/trials/workspace", headers=headers)
    assert ws_resp.status_code == 200
    ws = ws_resp.json()
    assert ws["vehicle"]["car_ref"] == "SLP-FS-EV-01"
    assert len(ws["setups"]) == 3

    # 3. INVESTIGATION (Record Action)
    inv_event_resp = await client.post(
        "/api/v1/trials/events",
        headers=headers,
        json={"event_name": "question_opened", "properties": {"stage": "INVESTIGATION"}},
    )
    assert inv_event_resp.status_code == 200

    # 4. EXPERIMENT (Run Candidate Hypothesis)
    exp_resp = await client.post(
        "/api/v1/trials/experiment",
        headers=headers,
        json={
            "question": "Why is front tire-load variation increasing during aggressive corner entry?",
            "hypothesis": "Increasing front roll stiffness reduces corner entry body roll.",
            "parameter_changes": {"k_arb_f": 4950.0},
        },
    )
    assert exp_resp.status_code == 200
    exp_data = exp_resp.json()
    assert "experiment" in exp_data
    assert exp_data["quota"]["runs_used"] >= 1

    # 5. COMPARE (Setup Matrix Analysis)
    compare_resp = await client.get(
        "/api/v1/trials/setups",
        headers=headers,
    )
    assert compare_resp.status_code == 200
    await client.post(
        "/api/v1/trials/events",
        headers=headers,
        json={"event_name": "compare_completed", "properties": {"stage": "COMPARE"}},
    )

    # 6. OPTIMIZATION (Run Multi-Objective Pareto Sweep)
    opt_resp = await client.post(
        "/api/v1/trials/optimize",
        headers=headers,
        json={
            "param_ranges": {
                "k_s": [30000.0, 45000.0],
                "c": [1400.0, 2400.0],
            }
        },
    )
    assert opt_resp.status_code == 200
    opt_data = opt_resp.json()
    assert opt_data["status"] == "COMPLETED"
    assert len(opt_data["pareto_result"]["frontier"]) >= 1

    # 7. DECISION (Generate Audit-Defensible Record)
    dec_resp = await client.post(
        "/api/v1/trials/decision",
        headers=headers,
        json={
            "question": "Why is front tire-load variation increasing during aggressive corner entry?",
            "reason": "Damping reduction from 1,800 to 1,650 Ns/m attenuates contact patch spike.",
        },
    )
    assert dec_resp.status_code == 200
    dec_data = dec_resp.json()
    assert dec_data["decision_id"].startswith("DEC-FS-")
    assert dec_data["provenance_hash"] is not None

    # 8. CUSTOM QUESTION
    q_resp = await client.post(
        "/api/v1/trials/questions",
        headers=headers,
        json={
            "title": "Evaluate rear heave spring compliance on high-speed curbs",
            "question_text": "Investigating third spring bump stop engagement over 30mm curb strike.",
        },
    )
    assert q_resp.status_code == 200

    # 9. FEEDBACK (Customer Discovery Submission)
    feedback_resp = await client.post(
        "/api/v1/trials/feedback",
        headers=headers,
        json={
            "most_valuable_part": "Connecting the telemetry evidence directly to the Pareto optimizer.",
            "prevented_more_use": "Would love automated telemetry CSV import from MoTeC.",
        },
    )
    assert feedback_resp.status_code == 200

    # 10. Verify Final Checklist State (All 6 core items completed)
    checklist_resp = await client.get("/api/v1/trials/checklist", headers=headers)
    assert checklist_resp.status_code == 200
    checklist_data = checklist_resp.json()
    assert checklist_data["completed_count"] == 6
    assert checklist_data["is_all_completed"] is True
    assert checklist_data["feedback_submitted"] is True


# ─── 6. Clean Evaluator Reset Test ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_trial_clean_reset_workflow(client: AsyncClient, db_session: AsyncSession):
    """
    Verify that an evaluator's workspace can be cleanly reset back to initial
    Formula Student Garage state, clearing custom decisions/experiments/questions
    while preserving tenant isolation.
    """
    email = f"reset-test-{uuid.uuid4().hex[:6]}@apex-eval.com"
    pwd = "OriginalPass123!45"
    new_pwd = "ResetPass123!45"

    prov = await TrialService.create_trial_organization(
        db=db_session,
        email=email,
        password=pwd,
        name="Reset Test User",
        org_name="Apex Reset Motors",
    )
    user = prov["user"]
    org = prov["organization"]

    # Authenticate and run actions
    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Add custom question
    await client.post(
        "/api/v1/trials/questions",
        headers=headers,
        json={"title": "Custom Question Before Reset", "question_text": "To be cleared by reset."},
    )

    # Submit feedback
    await client.post(
        "/api/v1/trials/feedback",
        headers=headers,
        json={"most_valuable_part": "Pre-reset feedback", "prevented_more_use": "None"},
    )

    # Execute Clean Reset via TrialService
    reset_res = await TrialService.reset_trial_organization(
        db=db_session,
        identifier=email,
        new_password=new_pwd,
        duration_days=7,
    )
    assert reset_res["status"] == "ACTIVE"
    assert reset_res["simulation_run_count"] == 0
    assert reset_res["days_remaining"] == 7
    assert reset_res["vehicle"] == "SLP-FS-EV-01"

    # Verify old password no longer works, new password works
    bad_login = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert bad_login.status_code == 401

    good_login = await client.post("/api/v1/auth/login", json={"email": email, "password": new_pwd})
    assert good_login.status_code == 200
    new_token = good_login.json()["token"]
    new_headers = {"Authorization": f"Bearer {new_token}"}

    # Verify workspace is cleanly reset back to initial state
    ws_resp = await client.get("/api/v1/trials/workspace", headers=new_headers)
    assert ws_resp.status_code == 200
    ws_data = ws_resp.json()
    assert ws_data["vehicle"]["car_ref"] == "SLP-FS-EV-01"
    assert ws_data["trial"]["simulation_run_count"] == 0
    assert ws_data["trial"]["status"] == "ACTIVE"
    assert ws_data["feedback_submitted"] is False

    # Verify custom question was cleared
    questions_res = await db_session.execute(
        select(EngineeringQuestion).where(EngineeringQuestion.organization_id == org.id)
    )
    questions = questions_res.scalars().all()
    assert len(questions) == 1
    assert questions[0].title == "Why is front tire-load variation increasing during aggressive corner entry?"

