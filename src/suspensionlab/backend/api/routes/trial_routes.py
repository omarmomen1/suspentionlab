"""
backend/api/routes/trial_routes.py
==================================
API Routes for SuspensionLab PRO 7-Day Evaluation & Dedicated Evaluation Workspace.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.security.jwt_utils import create_access_token, create_refresh_token, decode_refresh_token
from suspensionlab.backend.database.models.user_session import UserSession
from suspensionlab.backend.security.rate_limit import RateLimiter
from suspensionlab.backend.services.trial_service import TrialService
from suspensionlab.backend.services.experiment_service import (
    ExperimentService,
    evaluate_simulation_kpis,
)
from suspensionlab.backend.config import settings

router = APIRouter(prefix="/trials", tags=["trial-evaluation"])


# ─── Pydantic Request & Response Schemas ─────────────────────────────────────

class TrialRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = ""
    organization_name: Optional[str] = None

    @field_validator("password")
    def password_complexity(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        import string
        if not any(c in string.punctuation for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class TrialAuthResponse(BaseModel):
    token: str
    refresh_token: str
    user_id: str
    email: str
    name: str
    plan: str
    is_trial: bool = True
    redirect_url: str = "/evaluation"
    trial: Dict[str, Any]


class TrialSimulateRequest(BaseModel):
    params: Optional[Dict[str, float]] = None
    road_profile: Optional[Dict[str, Any]] = None


class TrialExperimentRequest(BaseModel):
    question: str = Field(..., min_length=5, description="Engineering hypothesis question")
    hypothesis: Optional[str] = None
    parameter_changes: Optional[Dict[str, Any]] = None
    parent_setup: Optional[Dict[str, float]] = None


class TrialOptimizeRequest(BaseModel):
    param_ranges: Optional[Dict[str, List[float]]] = None


class TrialKinematicsRequest(BaseModel):
    hardpoints: Optional[Dict[str, List[float]]] = None
    z_min_mm: float = -25.0
    z_max_mm: float = 25.0
    n_steps: int = 11


class TrialHandlingRequest(BaseModel):
    speed_kph: float = 70.0
    max_ay_g: float = 1.5
    n_points: int = 11
    setup_name: str = "Setup A — Baseline"


class TrialLapSimRequest(BaseModel):
    setup_a: str = "Setup A — Baseline"
    setup_b: str = "Setup B — High Roll Stiffness"


class TrialDecisionRequest(BaseModel):
    question: Optional[str] = None
    selected_option: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    tradeoffs: Optional[List[Dict[str, Any]]] = None
    candidates: Optional[List[Dict[str, Any]]] = None
    risks: Optional[List[str]] = None
    simulation_evidence: Optional[Dict[str, Any]] = None
    telemetry_evidence: Optional[Dict[str, Any]] = None
    validation_evidence: Optional[Dict[str, Any]] = None


class TrialCustomQuestionRequest(BaseModel):
    title: str = Field(..., min_length=5)
    question_text: str = Field(..., min_length=10)
    severity: str = "MEDIUM"
    setup_id: Optional[str] = "Setup A — Baseline"
    context: Optional[Dict[str, Any]] = None


class TrialFeedbackRequest(BaseModel):
    most_valuable_part: str = Field(..., min_length=2)
    prevented_more_use: str = Field(..., min_length=2)


class TrialAnalyticsEventRequest(BaseModel):
    event_name: str = Field(..., min_length=2)
    properties: Optional[Dict[str, Any]] = None


class TrialCleanupRequest(BaseModel):
    grace_period_days: int = 30
    dry_run: bool = True
    force: bool = False


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=TrialAuthResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter("rate_limit_login"))],
)
async def register_trial(
    req: TrialRegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Public 7-day evaluation onboarding endpoint.
    Provisions a private trial organization, user, seeds the evaluation workspace with
    real backend objects, and issues authentication tokens and HttpOnly session cookies.
    """
    trial_data = await TrialService.create_trial_organization(
        db=db,
        email=req.email,
        password=req.password,
        name=req.name,
        org_name=req.organization_name,
        duration_days=7,
    )

    user = trial_data["user"]
    trial = trial_data["trial"]
    u_id_str = str(user.id)

    token = create_access_token({
        "sub": u_id_str,
        "email": user.email,
        "plan": user.plan,
        "is_trial": True,
    })
    r_token = create_refresh_token({
        "sub": u_id_str,
        "email": user.email,
        "plan": user.plan,
        "is_trial": True,
    })

    # Record UserSession in DB
    r_payload = decode_refresh_token(r_token)
    if r_payload:
        from user_agents import parse
        ua = request.headers.get("User-Agent", "Unknown")
        parsed_ua = parse(ua)
        user_agent_str = f"{parsed_ua.browser.family} on {parsed_ua.os.family}"
        device_type = "Mobile" if parsed_ua.is_mobile else ("Tablet" if parsed_ua.is_tablet else "Desktop")

        session_obj = UserSession(
            user_id=user.id,
            jti=r_payload["jti"],
            user_agent=user_agent_str,
            ip_address=request.client.host if request.client else None,
            device_type=device_type,
            expires_at=datetime.fromtimestamp(r_payload["exp"], tz=timezone.utc).replace(tzinfo=None),
        )
        db.add(session_obj)
        await db.commit()

    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https" or (settings.environment == "PROD")
    response.set_cookie(key="sl_token", value=token, httponly=True, samesite="lax", secure=is_secure, path="/")
    response.set_cookie(key="sl_refresh_token", value=r_token, httponly=True, samesite="lax", secure=is_secure, path="/")
    response.set_cookie(key="sl_authed", value="true", httponly=False, samesite="lax", secure=is_secure, path="/")

    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, samesite="lax", secure=is_secure, path="/")

    return TrialAuthResponse(
        token=token,
        refresh_token=r_token,
        user_id=u_id_str,
        email=user.email,
        name=user.name or "",
        plan=user.plan,
        is_trial=True,
        redirect_url="/evaluation",
        trial=trial.to_dict(),
    )


@router.get("/status")
async def get_trial_status(
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Returns real-time, server-authoritative status of the evaluation:
    - Expiration timestamp and countdown
    - Status ('ACTIVE' or 'EXPIRED')
    - Simulation, vehicle, and telemetry quotas vs current usage
    """
    trial = await TrialService.get_trial_for_user(db, user_id=user.user_id, organization_id=user.organization_id)
    if not trial:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No trial evaluation record found for this user/organization.",
        )
    return trial.to_dict()


@router.get("/workspace")
async def get_evaluation_workspace(
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Fetches the complete private evaluation workspace containing genuine backend objects:
    - Vehicle Twin & parameters
    - Setup spec
    - Telemetry session
    - Engineering question
    - Baseline simulation KPIs
    - Experiment history
    """
    workspace = await TrialService.get_evaluation_workspace(db, user)
    return workspace


@router.post(
    "/simulate",
    dependencies=[Depends(RateLimiter("rate_limit_simulate"))],
)
async def run_trial_simulation(
    req: TrialSimulateRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes a real quarter-car simulation within the evaluation workspace.
    Enforces server-authoritative 7-day expiration and 50-run simulation quota.
    """
    # 1. Assert Trial Access & Quota
    trial = await TrialService.assert_trial_access(db, user, action="simulate", delta=1)

    # 2. Extract baseline parameters or requested overrides
    base_params = {
        "m_s": 50.0,
        "m_u": 10.5,
        "k_s": 35000.0,
        "c": 1800.0,
        "k_t": 110000.0,
        "MR": 0.92,
        "k_arb_f": 4500.0,
        "k_arb_r": 3800.0,
        "ride_height_mm": 28.0,
    }
    if req.params:
        base_params.update(req.params)

    # 3. Compute Real Physics KPIs
    kpis = evaluate_simulation_kpis(base_params, req.road_profile)

    # 4. Record Quota Usage
    updated_trial = await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    return {
        "status": "COMPLETED",
        "simulation_type": "QUARTER_CAR",
        "kpis": kpis,
        "params": base_params,
        "quota": {
            "runs_used": updated_trial.simulation_run_count if updated_trial else None,
            "runs_limit": updated_trial.simulation_run_limit if updated_trial else 50,
            "runs_remaining": max(0, updated_trial.simulation_run_limit - updated_trial.simulation_run_count) if updated_trial else None,
        },
    }


@router.post(
    "/experiment",
    dependencies=[Depends(RateLimiter("rate_limit_simulate"))],
)
async def run_trial_experiment(
    req: TrialExperimentRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes a hypothesis-driven setup experiment within the evaluation workspace.
    Computes real candidate solver results, exposes mandatory tradeoffs ('What Got Worse' vs 'What Improved'),
    and computes a SHA-256 reproducibility hash.
    Enforces server-authoritative 7-day expiration and simulation run quota.
    """
    # 1. Assert Trial Access & Quota
    await TrialService.assert_trial_access(db, user, action="simulate", delta=1)

    # Baseline setup
    parent_setup = req.parent_setup or {
        "m_s": 50.0,
        "m_u": 10.5,
        "k_s": 35000.0,
        "c": 1800.0,
        "k_t": 110000.0,
        "MR": 0.92,
        "k_arb_f": 4500.0,
        "k_arb_r": 3800.0,
        "ride_height_mm": 28.0,
    }

    # 2. Run real experiment via ExperimentService
    exp_result = await ExperimentService.run_experiment(
        db=db,
        user_id=user.user_id,
        team_id=getattr(user, "team_id", None),
        question=req.question,
        hypothesis=req.hypothesis or "Front roll stiffness tuning for corner entry tire load stability.",
        parent_setup=parent_setup,
        parameter_changes=req.parameter_changes or {"k_arb_f": 4950.0},
        author=user.name or "Evaluation Dynamics Engineer",
    )

    # 3. Record Quota Usage
    updated_trial = await TrialService.record_trial_usage(db, user, action="simulate", delta=1)
    if updated_trial:
        meta = dict(updated_trial.metadata_json or {})
        actions = dict(meta.get("completed_actions") or {})
        actions["run_experiment"] = True
        meta["completed_actions"] = actions
        updated_trial.metadata_json = meta
        await db.commit()

    return {
        "experiment": exp_result,
        "quota": {
            "runs_used": updated_trial.simulation_run_count if updated_trial else None,
            "runs_limit": updated_trial.simulation_run_limit if updated_trial else 50,
            "runs_remaining": max(0, updated_trial.simulation_run_limit - updated_trial.simulation_run_count) if updated_trial else None,
        },
    }


@router.get("/setups")
async def get_trial_setups_endpoint(
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Returns Setups A, B, and C with calculated KPIs and comparative deltas."""
    return await TrialService.get_trial_setups(db, user)


@router.post(
    "/optimize",
    dependencies=[Depends(RateLimiter("rate_limit_simulate"))],
)
async def run_trial_pareto_optimization_endpoint(
    req: TrialOptimizeRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes a real multi-objective Pareto optimization across candidate suspension setups.
    Returns the non-dominated Pareto frontier, feasible solutions, and best compromise point.
    """
    return await TrialService.run_trial_pareto_optimization(db, user, req.param_ranges)


@router.post(
    "/kinematics",
    dependencies=[Depends(RateLimiter("rate_limit_simulate"))],
)
async def run_trial_kinematics_endpoint(
    req: TrialKinematicsRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes a real double-wishbone kinematics solve and sensitivity matrix
    for the Formula Student EV within the trial workspace.
    Enforces server-authoritative 7-day expiration and simulation run quota.
    """
    return await TrialService.run_trial_kinematics(
        db, user,
        hardpoints=req.hardpoints,
        z_min_mm=req.z_min_mm,
        z_max_mm=req.z_max_mm,
        n_steps=req.n_steps,
    )


@router.post(
    "/handling",
    dependencies=[Depends(RateLimiter("rate_limit_simulate"))],
)
async def run_trial_handling_endpoint(
    req: TrialHandlingRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes a real non-linear handling diagram and understeer gradient analysis
    for the Formula Student EV within the trial workspace.
    Enforces server-authoritative 7-day expiration and simulation run quota.
    """
    return await TrialService.run_trial_handling(
        db, user,
        speed_kph=req.speed_kph,
        max_ay_g=req.max_ay_g,
        n_points=req.n_points,
        setup_name=req.setup_name,
    )


@router.post(
    "/lapsim",
    dependencies=[Depends(RateLimiter("rate_limit_simulate"))],
)
async def run_trial_lapsim_endpoint(
    req: TrialLapSimRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes a real 2D circuit lap simulation, delta attribution, and Race Engineer Decision
    for the Formula Student EV within the trial workspace.
    Enforces server-authoritative 7-day expiration and simulation run quota.
    """
    return await TrialService.run_trial_lapsim(
        db, user,
        setup_a_name=req.setup_a,
        setup_b_name=req.setup_b,
    )


@router.post(
    "/decision",
    dependencies=[Depends(RateLimiter("rate_limit_login"))],
)
async def create_trial_decision_endpoint(
    req: TrialDecisionRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Creates a formal audit-defensible EngineeringDecision record with cryptographic hash
    (Decision Workflow Demo).
    """
    return await TrialService.create_trial_decision(db, user, req.model_dump(exclude_none=True))


@router.post(
    "/questions",
    dependencies=[Depends(RateLimiter("rate_limit_login"))],
)
async def create_trial_custom_question_endpoint(
    req: TrialCustomQuestionRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Allows the trial user to formulate their own engineering question
    ('TRY YOUR OWN ENGINEERING QUESTION').
    """
    return await TrialService.create_custom_question(db, user, req.model_dump())


@router.get("/telemetry")
async def get_trial_telemetry_endpoint(
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Returns the 101-point deterministic synthetic telemetry dataset for the Formula Student EV.
    """
    workspace = await TrialService.get_evaluation_workspace(db, user)
    return workspace.get("telemetry_dataset")


@router.get("/checklist")
async def get_trial_checklist_endpoint(
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Returns authentic backend state for the 6 core evaluation checklist items.
    """
    return await TrialService.get_trial_checklist_state(db, user)


@router.post("/feedback")
async def submit_trial_feedback_endpoint(
    req: TrialFeedbackRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Persists customer discovery feedback to the trial organization.
    """
    return await TrialService.save_trial_feedback(db, user, req.model_dump())


@router.post("/events")
async def record_trial_event_endpoint(
    req: TrialAnalyticsEventRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Records non-sensitive product analytics events for trial engagement.
    """
    return await TrialService.record_trial_event(db, user, req.event_name, req.properties)


@router.post("/cleanup")
async def trigger_trial_cleanup(
    req: TrialCleanupRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Expiration cleanup endpoint for purging expired trial organizations.
    Restricted to system administrators.
    Defaults to dry_run=True to prevent accidental data loss.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Only system administrators may trigger trial cleanup.",
        )

    res = await TrialService.cleanup_expired_trials(
        db=db,
        grace_period_days=req.grace_period_days,
        dry_run=req.dry_run,
        force=req.force,
    )
    return res
