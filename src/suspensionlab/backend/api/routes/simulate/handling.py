"""
backend/api/routes/simulate/handling.py
=======================================
SuspensionLab PRO — Handling Dynamics & Understeer Analysis API Routes

Endpoints:
- POST /api/v1/simulate/handling     -> Asynchronous job submission for dynamic maneuvers
- POST /api/v1/handling/diagram      -> Synchronous steady-state handling diagram (Steer vs Ay, Kus, loads)
- POST /api/v1/handling/scenario     -> Dynamic yaw scenarios (Step Steer, Ramp Steer, Constant Radius, Speed Sweep)
- POST /api/v1/handling/compare      -> Setup A vs Setup B comparison with physical causality attribution
- POST /api/v1/handling/sweep        -> Bounded parameter sensitivity studies (roll stiffness, CG height, weight dist)
- POST /api/v1/handling/investigate  -> Direct creation of traceable EngineeringQuestion / DOE experiment
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
import numpy as np
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services.engineering_question_service import EngineeringQuestionService
from suspensionlab.backend.services.simulation_service import SimulationService
from suspensionlab.physics.handling_analysis import (
    assess_handling_validity,
    build_handling_provenance,
    compare_handling_setups,
    compute_handling_diagram,
    simulate_yaw_response_scenario,
)
from suspensionlab.physics.handling_model import HandlingParams
from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.shared.models import HandlingRequest

router = APIRouter()
logger = logging.getLogger(__name__)


class JobResponse(BaseModel):
    job_id: str
    status: str


class HandlingDiagramRequest(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict, description="Vehicle parameters dict")
    speed_kph: float = Field(100.0, ge=10.0, le=400.0, description="Vehicle test speed (km/h)")
    max_ay_g: float = Field(1.30, ge=0.2, le=2.5, description="Maximum lateral acceleration to sweep (G)")
    setup_id: Optional[str] = Field("SETUP-001", description="Identifier of vehicle setup")
    kinematics_study_id: Optional[str] = Field(None, description="Linked kinematics study ID")


class HandlingScenarioRequest(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict, description="Vehicle parameters dict")
    scenario_type: str = Field("step_steer", description="step_steer | ramp_steer | constant_radius | speed_sweep")
    v_kph: float = Field(100.0, ge=10.0, le=400.0, description="Initial vehicle speed (km/h)")
    steer_amplitude_deg: float = Field(3.0, ge=0.5, le=30.0, description="Steering input amplitude (deg)")
    duration_s: float = Field(6.0, ge=1.0, le=30.0, description="Simulation duration (s)")


class SetupComparisonRequest(BaseModel):
    setup_a: Dict[str, Any] = Field(..., description="Vehicle setup A parameters")
    setup_b: Dict[str, Any] = Field(..., description="Vehicle setup B parameters")
    name_a: str = Field("Setup A (Baseline)", description="Label for Setup A")
    name_b: str = Field("Setup B (Modified)", description="Label for Setup B")
    speed_kph: float = Field(100.0, ge=10.0, le=400.0, description="Evaluation speed (km/h)")


class ParameterSweepRequest(BaseModel):
    base_params: Dict[str, Any] = Field(default_factory=dict, description="Baseline vehicle parameters")
    parameter_name: str = Field("roll_dist", description="roll_dist | h_cg | K_arb_f | m")
    min_val: float = Field(0.40, description="Minimum parameter value")
    max_val: float = Field(0.70, description="Maximum parameter value")
    steps: int = Field(5, ge=3, le=10, description="Number of sweep increments")
    speed_kph: float = Field(100.0, description="Evaluation speed (km/h)")


class InvestigateHandlingRequest(BaseModel):
    title: str = Field(..., description="Title of the handling investigation question")
    finding_summary: str = Field(..., description="Observed understeer/oversteer discrepancy or limit")
    affected_regime: str = Field("Corner Entry", description="Driving regime: Entry, Mid-Corner, Exit")
    setup_a_name: str = Field("Setup A", description="Baseline setup name")
    setup_b_name: str = Field("Setup B", description="Comparison setup name")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Calculated metric deltas")
    notes: Optional[str] = Field(None, description="Optional engineering notes")


def _build_params_obj(pdump: Dict[str, Any]) -> HandlingParams:
    """Helper to instantiate HandlingParams safely from payload."""
    p_copy = pdump.copy()
    if p_copy.get("tire_coeffs"):
        p_copy["tire_coeffs"] = TireCoeffs(**p_copy["tire_coeffs"])
    else:
        p_copy.pop("tire_coeffs", None)

    if "h_cg" in p_copy and "h_cg_s" not in p_copy:
        p_copy["h_cg_s"] = p_copy["h_cg"]

    # Filter recognized parameters
    valid_keys = HandlingParams.__dataclass_fields__.keys()
    filtered = {k: v for k, v in p_copy.items() if k in valid_keys and v is not None}
    return HandlingParams(**filtered)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/simulate/handling", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def simulate_handling(
    payload: HandlingRequest,
    user: Any = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Enqueues asynchronous handling maneuver simulation."""
    try:
        job_id = await SimulationService.enqueue_simulation(
            user_id=user.user_id,
            plan=user.plan,
            job_type="SIMULATE_HANDLING",
            payload=payload.model_dump(),
            db=db,
            team_id=getattr(user, "team_id", None)
        )
        return {"job_id": job_id, "status": "PENDING"}
    except Exception as e:
        logger.exception("Unhandled error in /simulate/handling: %s", e)
        raise HTTPException(status_code=500, detail="Internal simulation error.")


@router.post("/handling/diagram")
async def get_handling_diagram(
    req: HandlingDiagramRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Computes steady-state handling diagram:
    - Steering Angle vs Lateral Acceleration (with Ackermann line)
    - Understeer Gradient Kus (deg/G)
    - Front/Rear Axle Utilization
    - Wheel Loads & Load Transfer Decomposition (Geometric, Elastic, Unsprung, Aero)
    - Pacejka MF 5.2 Tire Force Envelopes
    - Validity Report & Provenance Metadata
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    try:
        p = _build_params_obj(req.params)
        diagram = compute_handling_diagram(
            p=p,
            speed_kph=req.speed_kph,
            max_ay_g=req.max_ay_g,
        )
        validity = assess_handling_validity(p)
        provenance = build_handling_provenance(
            setup_id=req.setup_id or "SETUP-001",
            kinematics_study_id=req.kinematics_study_id
        )

        return {
            "diagram": diagram,
            "validity": validity.to_dict(),
            "provenance": provenance,
        }
    except Exception as exc:
        logger.exception("Handling diagram generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Handling diagram calculation failed: {exc}")


@router.post("/handling/scenario")
async def run_handling_scenario(
    req: HandlingScenarioRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Runs dynamic vehicle dynamics scenarios:
    - step_steer
    - ramp_steer
    - constant_radius
    - speed_sweep
    Returns full time-series traces, yaw rate gain, yaw time constant, sideslip, and load transfer.
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    try:
        p = _build_params_obj(req.params)
        res = simulate_yaw_response_scenario(
            p=p,
            scenario_type=req.scenario_type,
            v_kph=req.v_kph,
            steer_amplitude_deg=req.steer_amplitude_deg,
            duration_s=req.duration_s,
        )
        validity = assess_handling_validity(p, res.get("time_series"))
        res["validity"] = validity.to_dict()
        return res
    except Exception as exc:
        logger.exception("Handling scenario failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Handling scenario simulation failed: {exc}")


@router.post("/handling/compare")
async def compare_setups_endpoint(
    req: SetupComparisonRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Authoritative Setup A vs Setup B Comparison:
    - WHAT CHANGED (Parameter deltas table)
    - WHAT IMPROVED (Stability or agility gains)
    - WHAT GOT WORSE (Tradeoffs or safety margins)
    - WHY (Physical causality chain connecting roll stiffness, load transfer, tire load degressivity, and Kus)
    - CONFIDENCE & LIMITATIONS
    - Both handling diagrams and step steer responses
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    try:
        p_a = _build_params_obj(req.setup_a)
        p_b = _build_params_obj(req.setup_b)
        report = compare_handling_setups(
            setup_a=p_a,
            setup_b=p_b,
            speed_kph=req.speed_kph,
            name_a=req.name_a,
            name_b=req.name_b,
        )
        return report
    except Exception as exc:
        logger.exception("Handling setup comparison failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Setup comparison failed: {exc}")


@router.post("/handling/sweep")
async def parameter_sweep_endpoint(
    req: ParameterSweepRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Runs bounded sensitivity parameter studies (roll stiffness distribution, CG height, mass):
    Shows how Kus and peak Ay vary with setup changes.
    """
    if user and getattr(user, "is_trial", False):
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="simulate", delta=1)
        await TrialService.record_trial_usage(db, user, action="simulate", delta=1)

    try:
        p_base = _build_params_obj(req.base_params)
        vals = np.linspace(req.min_val, req.max_val, req.steps)
        sweep_results = []

        for v in vals:
            p_mod = _build_params_obj(req.base_params)
            setattr(p_mod, req.parameter_name, float(v))
            if req.parameter_name == "h_cg":
                p_mod.h_cg_s = float(v)

            diag = compute_handling_diagram(p_mod, speed_kph=req.speed_kph)
            sweep_results.append({
                "value": round(float(v), 4),
                "kus_linear_deg_per_g": diag["kus_linear_deg_per_g"],
                "ay_peak_g": diag["ay_peak_g"],
                "limiting_axle": diag["limiting_axle"],
            })

        return {
            "parameter_name": req.parameter_name,
            "speed_kph": req.speed_kph,
            "sweep_results": sweep_results,
        }
    except Exception as exc:
        logger.exception("Handling parameter sweep failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Parameter sweep failed: {exc}")


@router.post("/handling/investigate")
async def investigate_handling_finding(
    req: InvestigateHandlingRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Converts a handling finding or understeer discrepancy into a formal EngineeringQuestion / DOE experiment.
    Enforces the scientific chain: MEASURED DATA -> EVENT -> EVIDENCE -> QUESTION -> EXPERIMENT.
    """
    try:
        from suspensionlab.backend.services.trial_service import TrialService
        await TrialService.assert_trial_access(db, user, action="decision")

        question_text = (
            f"Handling analysis identified balance shift in {req.affected_regime} between {req.setup_a_name} and {req.setup_b_name}.\n"
            f"Finding: {req.finding_summary}\n"
            f"Key metrics: {req.metrics}\n"
            f"What setup adjustments (anti-roll bars, spring rates, or ride heights) are recommended to achieve the target vehicle balance?"
        )
        if req.notes:
            question_text += f"\nEngineer notes: {req.notes}"

        context = {
            "source": "HANDLING_ANALYSIS",
            "setup_a": req.setup_a_name,
            "setup_b": req.setup_b_name,
            "affected_regime": req.affected_regime,
            "metrics": req.metrics,
        }

        created = await EngineeringQuestionService.create_question(
            db=db,
            user_id=user.user_id,
            user_name=user.name or user.email,
            title=req.title,
            question_text=question_text,
            vehicle_id="Formula 1 2026 Spec (CAR 07)",
            setup_id=req.setup_b_name,
            severity="MEDIUM",
            source="HANDLING_ANALYSIS",
            context_data=context,
        )

        return {
            "question_id": created.id,
            "title": created.title,
            "status": "CREATED",
            "message": f"Successfully created Engineering Question #{created.id} from Handling Analysis.",
        }
    except Exception as exc:
        logger.exception("Investigate handling question creation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Question creation failed: {exc}")
