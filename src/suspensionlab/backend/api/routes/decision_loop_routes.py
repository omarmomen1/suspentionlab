"""
backend/api/routes/decision_loop_routes.py
===========================================
SuspensionLab PRO — Phase 3K Engineering Decision Loop API Routes.

Exposes the full executable 15-stage workflow:
    TRACK SESSION → TELEMETRY → DETECTION → QUESTION → EVIDENCE → HYPOTHESIS →
    EXPERIMENT → SIMULATION → COMPARISON → OPTIMIZATION → BLIND VALIDATION →
    DECISION → APPROVAL → TIMELINE → NEXT TRACK SESSION

Also exposes the authoritative Failure UX Diagnostics endpoint for all 8 failure modes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services.engineering_decision_loop_service import (
    EngineeringDecisionLoopService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decision-loop", tags=["engineering-decision-loop"])


# ── Request Models ─────────────────────────────────────────────────────────────

class CreateTrackSessionRequest(BaseModel):
    session_number: int = Field(381, description="Sequential track session number")
    session_code: Optional[str] = Field("TS-381", description="Unique session code")
    track_name: str = Field("Silverstone GP", description="Track name")
    vehicle_id: str = Field("CAR-2026-07", description="Vehicle identifier")
    setup_id: str = Field("SETUP-91", description="Baseline setup identifier")
    telemetry_channels: Optional[Dict[str, List[float]]] = None
    duration_s: float = Field(8.0, ge=1.0, le=60.0)


class DetectAnomalyRequest(BaseModel):
    session_code: str = Field("TS-381", description="Source telemetry session code")
    investigation_number: int = Field(91, description="Investigation sequence number")
    detection_type: str = Field("FRONT_AXLE_LATERAL_PERFORMANCE_DROP")


class CreateLoopQuestionRequest(BaseModel):
    investigation_code: str = Field("INV-91", description="Linked investigation code")
    question_number: int = Field(17, description="Question sequence number")
    question_text: str = Field("Why did front axle lateral performance decrease in Session 381?")
    vehicle_id: Optional[str] = "CAR-2026-07"
    setup_id: Optional[str] = "SETUP-91"


class CreateLoopExperimentRequest(BaseModel):
    question_id: str = Field("Q-17", description="Linked question identifier")
    experiment_number: int = Field(52, description="Experiment sequence number")
    hypothesis: Optional[str] = None
    changed_parameters: Optional[Dict[str, Any]] = None
    unchanged_parameters: Optional[Dict[str, Any]] = None
    expected_effect: Optional[str] = None
    constraints: Optional[List[Dict[str, Any]]] = None


class ExecuteLoopSimulationRequest(BaseModel):
    experiment_code: str = Field("EXP-52", description="Originating experiment code")
    simulation_number: int = Field(1844, description="Sequential simulation run number")
    params: Optional[Dict[str, Any]] = None


class CompareLoopSetupsRequest(BaseModel):
    comparison_number: int = Field(31, description="Comparison sequence number")
    baseline_setup_id: str = Field("SETUP-91")
    candidate_setup_id: str = Field("SETUP-92")
    simulation_run_id: str = Field("RUN-001844")
    measured_session_code: str = Field("TS-381")


class RunLoopOptimizationRequest(BaseModel):
    experiment_code: str = Field("EXP-52")
    optimization_number: int = Field(18)
    objective: Optional[str] = "MAXIMIZE_LATERAL_GRIP_MINIMIZE_SLIP_SATURATION"
    design_variables: Optional[List[str]] = None
    sweep_steps: int = Field(5, ge=3, le=10)


class ExecuteBlindValidationRequest(BaseModel):
    validation_number: int = Field(31)
    setup_id: str = Field("SETUP-92")
    telemetry_session_code: str = Field("TS-381")


class CreateLoopDecisionRequest(BaseModel):
    decision_number: int = Field(12)
    selected_setup_id: str = Field("SETUP-92")
    question: Optional[str] = "Why did front axle lateral performance decrease in Session 381?"
    model_version: Optional[str] = "QCAR-ODE-RK45-v2.8"


class ApproveLoopDecisionRequest(BaseModel):
    decision_code: str = Field("DEC-12")
    approval_number: int = Field(8)
    approver_name: str = Field("James Wilson")
    approver_role: str = Field("Chief Race Engineer")
    notes: Optional[str] = "Approved following blind holdout validation (R²=0.938)."


class NextTrackSessionRequest(BaseModel):
    approved_decision_code: str = Field("DEC-12")
    next_session_number: int = Field(382)


class FailureDiagnosticRequest(BaseModel):
    failure_mode: str = Field(..., description="solver failure | invalid telemetry | extrapolated physics | optimizer failure | validation failure | missing provenance | stale model | external solver unavailable")
    context: Optional[Dict[str, Any]] = None


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/track-session", status_code=status.HTTP_201_CREATED)
async def create_track_session_endpoint(
    req: CreateTrackSessionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 1 & 2: Ingest real Track Session with multi-channel telemetry."""
    try:
        return await EngineeringDecisionLoopService.create_track_session(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            session_number=req.session_number,
            session_code=req.session_code,
            track_name=req.track_name,
            vehicle_id=req.vehicle_id,
            setup_id=req.setup_id,
            telemetry_channels=req.telemetry_channels,
            duration_s=req.duration_s,
        )
    except Exception as exc:
        logger.error("Failed creating track session: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/detect", status_code=status.HTTP_201_CREATED)
async def detect_anomaly_endpoint(
    req: DetectAnomalyRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 3: Run anomaly detection and raise Investigation."""
    try:
        return await EngineeringDecisionLoopService.detect_anomaly(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            session_id_or_code=req.session_code,
            investigation_number=req.investigation_number,
            detection_type=req.detection_type,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Failed detecting anomaly: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/question", status_code=status.HTTP_201_CREATED)
async def create_question_endpoint(
    req: CreateLoopQuestionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 4: Create traceable Engineering Question linked to Investigation."""
    try:
        return await EngineeringDecisionLoopService.create_engineering_question(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            investigation_code=req.investigation_code,
            question_number=req.question_number,
            question_text=req.question_text,
            vehicle_id=req.vehicle_id or "CAR-2026-07",
            setup_id=req.setup_id or "SETUP-91",
            author=user.name or user.email or "Lead Performance Specialist",
        )
    except Exception as exc:
        logger.error("Failed creating engineering question: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/evidence/{question_id}")
async def gather_evidence_endpoint(
    question_id: str,
    previous_session: str = Query("TS-380"),
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 5: Gather actual multi-source evidence (telemetry, sim, setup, residuals, diff)."""
    try:
        return await EngineeringDecisionLoopService.gather_evidence(
            db=db,
            question_id=question_id,
            previous_session_code=previous_session,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Failed gathering evidence: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/experiment", status_code=status.HTTP_201_CREATED)
async def create_experiment_endpoint(
    req: CreateLoopExperimentRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 6 & 7: Formulate Experiment with hypothesis, changed/unchanged params, and constraints."""
    try:
        return await EngineeringDecisionLoopService.create_experiment(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            question_id=req.question_id,
            experiment_number=req.experiment_number,
            hypothesis=req.hypothesis or "Increasing front roll stiffness from 14,000 N/m to 18,500 N/m and damper rate c by +12% shifts lateral load transfer forward, arresting front slip angle expansion and restoring Turn 8 apex lateral grip.",
            changed_parameters=req.changed_parameters,
            unchanged_parameters=req.unchanged_parameters,
            expected_effect=req.expected_effect or "Reduce dynamic front slip angle from 8.2° to < 6.0°, raising apex lateral acceleration from 1.85 G to 2.02 G.",
            constraints=req.constraints,
            author=user.name or user.email or "Senior Vehicle Dynamics Engineer",
        )
    except Exception as exc:
        logger.error("Failed creating experiment: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/simulate", status_code=status.HTTP_201_CREATED)
async def execute_simulation_endpoint(
    req: ExecuteLoopSimulationRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 8: Execute real physics solver (quarter-car ODE & handling model)."""
    try:
        return await EngineeringDecisionLoopService.execute_simulation(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            experiment_code=req.experiment_code,
            simulation_number=req.simulation_number,
            params=req.params,
        )
    except Exception as exc:
        logger.error("Failed executing simulation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/compare", status_code=status.HTTP_201_CREATED)
async def compare_setups_endpoint(
    req: CompareLoopSetupsRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 9: Deep setup comparison showing baseline, candidate, measured, delta, uncertainty, and validity."""
    try:
        return await EngineeringDecisionLoopService.compare_setups(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            comparison_number=req.comparison_number,
            baseline_setup_id=req.baseline_setup_id,
            candidate_setup_id=req.candidate_setup_id,
            simulation_run_id=req.simulation_run_id,
            measured_session_code=req.measured_session_code,
        )
    except Exception as exc:
        logger.error("Failed comparing setups: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/optimize", status_code=status.HTTP_201_CREATED)
async def run_optimization_endpoint(
    req: RunLoopOptimizationRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 10: Run simulation-driven optimization calling the real simulation engine."""
    try:
        return await EngineeringDecisionLoopService.run_optimization(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            experiment_code=req.experiment_code,
            optimization_number=req.optimization_number,
            objective=req.objective or "MAXIMIZE_LATERAL_GRIP_MINIMIZE_SLIP_SATURATION",
            design_variables=req.design_variables,
            sweep_steps=req.sweep_steps,
        )
    except Exception as exc:
        logger.error("Failed running optimization: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/validate", status_code=status.HTTP_201_CREATED)
async def execute_blind_validation_endpoint(
    req: ExecuteBlindValidationRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 11: Execute strict out-of-sample blind validation with zero data leakage."""
    try:
        return await EngineeringDecisionLoopService.execute_blind_validation(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            setup_id=req.setup_id,
            telemetry_session_code=req.telemetry_session_code,
            validation_number=req.validation_number,
        )
    except Exception as exc:
        logger.error("Failed executing blind validation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/decision", status_code=status.HTTP_201_CREATED)
async def create_decision_endpoint(
    req: CreateLoopDecisionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 12: Record formal immutable Engineering Decision Record."""
    try:
        return await EngineeringDecisionLoopService.create_engineering_decision(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            decision_number=req.decision_number,
            selected_setup_id=req.selected_setup_id,
            question=req.question or "Why did front axle lateral performance decrease in Session 381?",
            author=user.name or user.email or "Lead Dynamics Specialist",
            model_version=req.model_version or "QCAR-ODE-RK45-v2.8",
        )
    except Exception as exc:
        logger.error("Failed creating engineering decision: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/approve", status_code=status.HTTP_200_OK)
async def approve_decision_endpoint(
    req: ApproveLoopDecisionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_APPROVE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 13: Execute mandatory human approval with HMAC-SHA256 signature."""
    try:
        return await EngineeringDecisionLoopService.approve_decision(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            decision_code=req.decision_code,
            approval_number=req.approval_number,
            approver_name=req.approver_name,
            approver_role=req.approver_role,
            notes=req.notes or "Approved following blind holdout validation.",
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Failed approving decision: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/reconstruct/{identifier}")
async def reconstruct_lineage_endpoint(
    identifier: str,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 14: Reconstruct complete 11-step lineage chain months later from any identifier."""
    try:
        return await EngineeringDecisionLoopService.reconstruct_complete_lineage(
            db=db,
            identifier=identifier,
        )
    except Exception as exc:
        logger.error("Failed reconstructing lineage: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/next-track-session", status_code=status.HTTP_201_CREATED)
async def next_track_session_endpoint(
    req: NextTrackSessionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Stage 15: Execute next track session (Session #382) to confirm on-track improvement and close loop."""
    try:
        return await EngineeringDecisionLoopService.execute_next_track_session(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            approved_decision_code=req.approved_decision_code,
            next_session_number=req.next_session_number,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.error("Failed executing next track session: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/diagnose-failure")
async def diagnose_failure_endpoint(
    req: FailureDiagnosticRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Requirement 11: Authoritative Failure UX Diagnostics.
    Returns the 5 required sections for all 8 failure modes:
    WHAT FAILED, WHY, WHAT REMAINS VALID, WHAT CANNOT BE CLAIMED, WHAT CAN BE DONE NEXT.
    """
    diagnostic = EngineeringDecisionLoopService.diagnose_failure(
        failure_mode=req.failure_mode,
        context=req.context,
    )
    return diagnostic.to_dict()


# ── Phase 3K.1 Authentic Case Endpoints ────────────────────────────────────────

class Phase3K1AuditRequest(BaseModel):
    candidate_parameters: List[str] = Field(default_factory=lambda: ["anti_roll_bar_front", "damper_bump_front"])
    telemetry_window_s: List[float] = Field(default_factory=lambda: [39.0, 42.0])
    force_flat_signal: bool = False


@router.post("/phase3k1/execute", status_code=status.HTTP_201_CREATED)
async def execute_phase3k1_case_endpoint(
    approver_name: str = Query("Elena Rostova"),
    approver_role: str = Query("Chief Race Engineer & Technical Director"),
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Phase 3K.1: Executes the complete end-to-end authentic engineering decision case
    on the Stanford VW Golf VII GTI Performance dataset at Thunderhill Raceway Park.
    """
    from suspensionlab.backend.services.phase3k1_case_service import Phase3K1CaseService
    try:
        bundle = await Phase3K1CaseService.execute_end_to_end_case(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            approver_name=approver_name,
            approver_role=approver_role,
        )
        Phase3K1CaseService.export_case_json(bundle)
        return bundle
    except Exception as exc:
        logger.error("Phase 3K.1 case execution failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/phase3k1/case")
async def get_phase3k1_case_manifest(
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Phase 3K.1: Retrieves the exported authentic engineering case JSON manifest.
    """
    from suspensionlab.backend.services.phase3k1_case_service import Phase3K1CaseService
    case_path = Path("data/phase3k1_engineering_case.json")
    if not case_path.exists():
        raise HTTPException(status_code=404, detail="Phase 3K.1 case JSON not yet generated. Execute /execute first.")
    with open(case_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/phase3k1/audit-observability")
async def audit_observability_endpoint(
    req: Phase3K1AuditRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Phase 3K.1: Evaluates whether telemetry data contains sufficient dynamical excitation
    to identify candidate parameters. Returns UNIDENTIFIABLE / UNSUPPORTED if not.
    """
    from suspensionlab.backend.services.phase3k1_case_service import Phase3K1CaseService
    t_win = (req.telemetry_window_s[0], req.telemetry_window_s[1]) if len(req.telemetry_window_s) >= 2 else (39.0, 42.0)
    audit = Phase3K1CaseService.audit_observability_and_excitation(
        candidate_parameters=req.candidate_parameters,
        telemetry_window_s=t_win,
        force_flat_signal=req.force_flat_signal,
    )
    return audit


@router.get("/phase3k1/reconstruct/{decision_code}")
async def reconstruct_phase3k1_lineage(
    decision_code: str = "DEC-P3K1-01",
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Phase 3K.1: Reconstructs the complete 12-step backward chain from Decision ID
    back to dataset provenance and model version.
    """
    from suspensionlab.backend.services.phase3k1_case_service import Phase3K1CaseService
    try:
        return await Phase3K1CaseService.reconstruct_complete_lineage(db=db, decision_code=decision_code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Phase 3L Setup Engineering Endpoints ─────────────────────────────────────

@router.post("/phase3l/execute")
async def execute_phase3l_workflow_endpoint(
    approver_name: str = Query("Elena Rostova", description="Approver full name"),
    approver_role: str = Query("Chief Race Engineer & Technical Director", description="Approver seat title"),
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Phase 3L: Executes the complete end-to-end setup engineering & causal experimentation workflow.
    """
    from suspensionlab.backend.services.phase3l_setup_engineering_service import Phase3LSetupEngineeringService
    try:
        bundle = await Phase3LSetupEngineeringService.execute_full_workflow(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            approver_name=approver_name,
            approver_role=approver_role,
        )
        Phase3LSetupEngineeringService.export_manifest(bundle)
        return bundle
    except Exception as exc:
        logger.error("Phase 3L workflow execution failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/phase3l/manifest")
async def get_phase3l_manifest_endpoint(
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Phase 3L: Retrieves exported setup engineering JSON manifest.
    """
    manifest_path = Path("data/phase3l_setup_engineering_manifest.json")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Phase 3L manifest not found. Execute /phase3l/execute first.")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


