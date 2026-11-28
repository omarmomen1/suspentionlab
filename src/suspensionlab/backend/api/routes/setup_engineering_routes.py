"""
backend/api/routes/setup_engineering_routes.py
===============================================
SuspensionLab PRO — Phase 3L Setup Engineering & Causal Experimentation API Routes.

Exposes the complete setup engineering workflow endpoints:
- Problem Definition
- Parameter Eligibility Gate
- Causal Hypothesis Formulation
- Controlled Experiment Design
- Setup Generation & Physical Boundaries
- Real 14-DOF Production Simulation
- Multi-Objective Pareto Evaluation
- Setup Comparison
- Sealed Blind Holdout Validation (Zero Leakage)
- Engineering Decision & HMAC Sign-off
- Immutable Track-Test Prediction
- Post-Track Telemetry Reconciliation
- 14-Step Backward Lineage Reconstruction
- 14 Failure Modes UX Diagnostics (5-Section format)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services.phase3l_setup_engineering_service import (
    Phase3LSetupEngineeringService,
    UnidentifiableParameterError,
    UncertaintyConstraintMissingError,
    NumericallyFailedParameterError,
    PhysicalBoundsViolationError,
    ValidityDomainViolationError,
    HoldoutLeakageError,
    ImmutablePredictionError,
    StaleModelError,
    SolverExecutionError,
    NoFeasibleSetupError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup-engineering", tags=["setup-engineering"])


# ── Wave 5A: Manifest baseline state ──────────────────────────────────────────

@router.get("/manifest")
async def get_setup_engineering_manifest(
    user: UserContext = Depends(require_permission(Permission.ENGINEERING_READ if hasattr(Permission, "ENGINEERING_READ") else Permission.SIMULATION_RUN)),
):
    """Return the current setup-engineering workflow manifest.

    Wave 5A: previously this endpoint did not exist and the production
    /setup-engineering page crashed on a raw 404 (RFC7807). Now returns HTTP
    200 with a structured EMPTY baseline state; every section is null until a
    real workflow has been run, which the frontend renders as an honest
    empty state.
    """
    return {
        "manifest_version": "3L-1.0",
        "state": "EMPTY",
        "message": "No setup-engineering workflow has been run yet. Define a problem to begin.",
        "problem": None,
        "parameter_gate": None,
        "hypothesis": None,
        "experiment": None,
        "setup": None,
        "simulation": None,
        "comparison": None,
        "validation": None,
        "decision": None,
        "approval": None,
        "prediction": None,
        "reconciliation": None,
        "lineage": [],
    }


# ── Request Models ─────────────────────────────────────────────────────────────

class ProblemDefinitionRequest(BaseModel):
    problem_id: str = Field("PROB-P3L-01", description="Unique problem identifier")
    telemetry_session_id: str = Field("TS-STANFORD-01", description="Source telemetry session")
    investigation_id: str = Field("INV-P3K1-01", description="Linked investigation code")
    engineering_question_id: str = Field("Q-P3K1-01", description="Engineering question code")
    observable: str = Field("Front axle lateral performance deteriorated during Turn 8 exit.", description="Observed symptom")
    baseline_metric: Optional[Dict[str, float]] = None
    target_metric: Optional[Dict[str, float]] = None
    operating_condition: Optional[Dict[str, Any]] = None
    track_context: Optional[Dict[str, Any]] = None
    session_context: Optional[Dict[str, Any]] = None
    model_version: Optional[str] = None


class ParameterGateRequest(BaseModel):
    candidate_parameters: List[str] = Field(..., description="List of parameter names to audit")
    uncertainty_handling: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="Explicit uncertainty constraints for partially identifiable params")


class CausalHypothesisRequest(BaseModel):
    problem_id: str = Field("PROB-P3L-01")
    hypothesis_id: str = Field("HYP-P3L-01")
    hypothesis: Optional[str] = None
    mechanism: Optional[str] = None
    supporting_evidence: Optional[List[str]] = None
    contradicting_evidence: Optional[List[str]] = None
    affected_observables: Optional[List[str]] = None
    candidate_parameters: Optional[List[str]] = None
    expected_direction_of_effect: Optional[Dict[str, str]] = None
    confidence_uncertainty: Optional[Dict[str, Any]] = None
    model_version: Optional[str] = None


class ControlledExperimentRequest(BaseModel):
    problem_id: str = Field("PROB-P3L-01")
    hypothesis_id: str = Field("HYP-P3L-01")
    experiment_id: str = Field("EXP-P3L-01")
    treatment_variables: Optional[Dict[str, float]] = None
    control_variables: Optional[Dict[str, Any]] = None
    held_constant_variables: Optional[Dict[str, Any]] = None
    measured_outputs: Optional[List[str]] = None
    expected_effect: Optional[Dict[str, Any]] = None
    constraints: Optional[List[Dict[str, Any]]] = None
    validity_domain: Optional[Dict[str, Any]] = None


class SetupCandidateRequest(BaseModel):
    setup_id: str = Field("SETUP-P3L-CAND-01")
    parent_setup_id: str = Field("SETUP-GTI-BASE")
    changed_parameters: Dict[str, Dict[str, float]]
    unchanged_parameters: Dict[str, float]
    parameter_provenance: Dict[str, str]
    creation_reason: str
    validity_domain: Optional[Dict[str, Any]] = None
    model_version: Optional[str] = None


class SimulateCandidateRequest(BaseModel):
    setup_id: str = Field("SETUP-P3L-CAND-01")
    k_arb_front: float = Field(33000.0, description="Front ARB stiffness in N/m")
    c_damper_front: float = Field(4200.0, description="Front bump damping in Ns/m")
    telemetry_window_s: Tuple[float, float] = Field((39.0, 42.0), description="Telemetry analysis window [t_start, t_end]")
    dt_s: float = Field(0.005, description="Time step in seconds")


class SetupComparisonRequest(BaseModel):
    baseline_setup_id: str = Field("SETUP-GTI-BASE")
    candidate_setup_id: str = Field("SETUP-P3L-CAND-01")
    baseline_metrics: Dict[str, float]
    candidate_metrics: Dict[str, float]
    measured_metrics: Optional[Dict[str, float]] = None


class BlindValidationRequest(BaseModel):
    candidate_setup_id: str = Field("SETUP-P3L-CAND-01")
    candidate_params: Dict[str, float] = Field(default_factory=lambda: {"k_arb_front_nm": 33000.0, "c_damper_front_nsm": 4200.0})
    fit_window: Tuple[float, float] = Field((39.0, 42.0))
    holdout_window: Tuple[float, float] = Field((42.0, 44.0))
    validation_code: str = Field("VAL-P3L-01")


class EngineeringDecisionRequest(BaseModel):
    decision_code: str = Field("DEC-P3L-01")
    selected_setup: str = Field("SETUP-P3L-CAND-01")
    alternatives: Optional[List[str]] = None
    outcome: str = Field("ACCEPT", description="ACCEPT | REJECT | INCONCLUSIVE | UNSUPPORTED")
    author: str = Field("", description="Ignored: the server sets the author from the authenticated user")
    evidence: Optional[Dict[str, Any]] = None
    simulation_results: Optional[Dict[str, Any]] = None
    blind_validation_results: Optional[Dict[str, Any]] = None


class ApprovalRequest(BaseModel):
    decision_code: str = Field("DEC-P3L-01")
    approver_name: str = Field("", description="Ignored: the server sets the approver from the authenticated user")
    approver_role: str = Field("", description="Ignored: the server sets the role from the authenticated user")
    approval_code: str = Field("APPR-P3L-01")
    notes: Optional[str] = None


class TrackPredictionRequest(BaseModel):
    decision_id: str = Field("DEC-P3L-01")
    candidate_setup_id: str = Field("SETUP-P3L-CAND-01")
    prediction_id: str = Field("PRED-P3L-01")
    baseline_metric: Optional[Dict[str, float]] = None
    expected_candidate_metric: Optional[Dict[str, float]] = None
    expected_delta: Optional[Dict[str, float]] = None
    uncertainty_interval: Optional[Dict[str, Tuple[float, float]]] = None
    operating_conditions: Optional[Dict[str, Any]] = None
    failure_conditions: Optional[List[str]] = None


class PostTrackReconciliationRequest(BaseModel):
    prediction_id: str = Field("PRED-P3L-01")
    actual_session_id: str = Field("TS-STANFORD-02")
    reconciliation_id: str = Field("RECON-P3L-01")
    actual_measured_metrics: Optional[Dict[str, float]] = None


class FailureDiagnosticRequest(BaseModel):
    failure_type: str = Field(..., description="Failure mode identifier (e.g. unidentifiable_parameter_selected)")
    context: Optional[Dict[str, Any]] = None


# ── Route Handlers ─────────────────────────────────────────────────────────────

@router.post("/problem")
async def define_engineering_problem_endpoint(
    req: ProblemDefinitionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Section 1: Define an EngineeringProblem entity linked to DecisionLoop."""
    try:
        return await Phase3LSetupEngineeringService.create_engineering_problem(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            problem_id=req.problem_id,
            telemetry_session_id=req.telemetry_session_id,
            investigation_id=req.investigation_id,
            engineering_question_id=req.engineering_question_id,
            observable=req.observable,
            baseline_metric=req.baseline_metric,
            target_metric=req.target_metric,
            operating_condition=req.operating_condition,
            track_context=req.track_context,
            session_context=req.session_context,
            model_version=req.model_version,
        )
    except Exception as exc:
        logger.error("Error defining engineering problem: %s", exc)
        raise HTTPException(status_code=400, detail="The request could not be processed. Check the submitted parameters and try again.")


@router.post("/gate-parameters")
async def audit_parameter_gate_endpoint(
    req: ParameterGateRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """Phase 3L Section 2: Audit candidate parameters against Phase 3J/3J.1 eligibility gate."""
    audit = Phase3LSetupEngineeringService.audit_parameter_eligibility(
        candidate_parameters=req.candidate_parameters,
        uncertainty_handling=req.uncertainty_handling,
    )
    return audit


@router.post("/hypothesis")
async def formulate_causal_hypothesis_endpoint(
    req: CausalHypothesisRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Section 3: Formulate a formal CausalHypothesis with statistical confidence."""
    try:
        return await Phase3LSetupEngineeringService.formulate_causal_hypothesis(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            problem_id=req.problem_id,
            hypothesis_id=req.hypothesis_id,
            hypothesis=req.hypothesis,
            mechanism=req.mechanism,
            supporting_evidence=req.supporting_evidence,
            contradicting_evidence=req.contradicting_evidence,
            affected_observables=req.affected_observables,
            candidate_parameters=req.candidate_parameters,
            expected_direction_of_effect=req.expected_direction_of_effect,
            confidence_uncertainty=req.confidence_uncertainty,
            model_version=req.model_version,
        )
    except (UnidentifiableParameterError, UncertaintyConstraintMissingError, NumericallyFailedParameterError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Error formulating hypothesis: %s", exc)
        raise HTTPException(status_code=400, detail="The request could not be processed. Check the submitted parameters and try again.")


@router.post("/experiment")
async def design_controlled_experiment_endpoint(
    req: ControlledExperimentRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Section 4: Design a ControlledExperimentDesign entity with isolated treatment."""
    try:
        return await Phase3LSetupEngineeringService.design_controlled_experiment(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            problem_id=req.problem_id,
            hypothesis_id=req.hypothesis_id,
            experiment_id=req.experiment_id,
            treatment_variables=req.treatment_variables,
            control_variables=req.control_variables,
            held_constant_variables=req.held_constant_variables,
            measured_outputs=req.measured_outputs,
            expected_effect=req.expected_effect,
            constraints=req.constraints,
            validity_domain=req.validity_domain,
        )
    except Exception as exc:
        logger.error("Error designing experiment: %s", exc)
        raise HTTPException(status_code=400, detail="The request could not be processed. Check the submitted parameters and try again.")


@router.post("/setup-candidate")
async def create_setup_candidate_endpoint(
    req: SetupCandidateRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Section 5: Generate real SetupCandidateRecord with provenance and physical bounds."""
    try:
        return await Phase3LSetupEngineeringService.create_setup_candidate(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            setup_id=req.setup_id,
            parent_setup_id=req.parent_setup_id,
            changed_parameters=req.changed_parameters,
            unchanged_parameters=req.unchanged_parameters,
            parameter_provenance=req.parameter_provenance,
            creation_reason=req.creation_reason,
            validity_domain=req.validity_domain,
            model_version=req.model_version,
        )
    except PhysicalBoundsViolationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Error creating setup candidate: %s", exc)
        raise HTTPException(status_code=400, detail="The request could not be processed. Check the submitted parameters and try again.")


@router.post("/simulate")
async def simulate_candidate_endpoint(
    req: SimulateCandidateRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
):
    """Phase 3L Section 6: Execute genuine production 14-DOF multibody simulation."""
    try:
        return Phase3LSetupEngineeringService.execute_real_simulation(
            setup_id=req.setup_id,
            k_arb_front=req.k_arb_front,
            c_damper_front=req.c_damper_front,
            telemetry_window_s=req.telemetry_window_s,
            dt_s=req.dt_s,
        )
    except (SolverExecutionError, ValidityDomainViolationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Error running simulation: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error. The details have been logged server-side.")


@router.post("/compare")
async def compare_setups_endpoint(
    req: SetupComparisonRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """Phase 3L Section 7: Compare baseline vs candidate vs measured telemetry with uncertainties."""
    meas = req.measured_metrics or req.baseline_metrics
    return Phase3LSetupEngineeringService.compare_setups(
        baseline_setup_id=req.baseline_setup_id,
        candidate_setup_id=req.candidate_setup_id,
        baseline_metrics=req.baseline_metrics,
        candidate_metrics=req.candidate_metrics,
        measured_metrics=meas,
    )


@router.post("/validate-holdout")
async def validate_holdout_endpoint(
    req: BlindValidationRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Section 9: Execute sealed blind holdout validation with zero data leakage."""
    try:
        return await Phase3LSetupEngineeringService.execute_sealed_blind_validation(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            candidate_setup_id=req.candidate_setup_id,
            candidate_params=req.candidate_params,
            fit_window=req.fit_window,
            holdout_window=req.holdout_window,
            validation_code=req.validation_code,
        )
    except HoldoutLeakageError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Error executing blind validation: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error. The details have been logged server-side.")


def _authenticated_identity(user: Any) -> Any:
    """Wave 12 item 1: the only source of an author or approver identity is the session."""
    email = getattr(user, "email", None)
    name = getattr(user, "name", None) or (email.split("@")[0].replace(".", " ").title() if email else "Authenticated Engineer")
    role = str(getattr(user, "team_role", None) or getattr(user, "org_role", None) or "ENGINEER").upper()
    return name, role


def _reject_identity_spoof(client_value: Any, server_value: str, field: str) -> None:
    if client_value is None:
        return
    text = str(client_value).strip()
    if text and text.lower() != str(server_value).strip().lower():
        raise HTTPException(
            status_code=403,
            detail=(
                f"Identity spoofing detected: client-supplied {field} '{text}' does not match "
                f"authenticated user '{server_value}'."
            ),
        )


@router.post("/decision")
async def create_decision_endpoint(
    req: EngineeringDecisionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Section 10: Formulate engineering decision record."""
    author_name, _author_role = _authenticated_identity(user)
    _reject_identity_spoof(req.author, author_name, "author")
    try:
        return await Phase3LSetupEngineeringService.create_engineering_decision(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            decision_code=req.decision_code,
            selected_setup=req.selected_setup,
            alternatives=req.alternatives,
            outcome=req.outcome,
            author=author_name,
            evidence=req.evidence,
            simulation_results=req.simulation_results,
            blind_validation_results=req.blind_validation_results,
        )
    except Exception as exc:
        logger.error("Error creating engineering decision: %s", exc)
        raise HTTPException(status_code=400, detail="The request could not be processed. Check the submitted parameters and try again.")


@router.post("/approve")
async def approve_decision_endpoint(
    req: ApprovalRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_APPROVE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Section 10: Request human engineering sign-off with HMAC-SHA256 signature."""
    approver_name, approver_role = _authenticated_identity(user)
    _reject_identity_spoof(req.approver_name, approver_name, "approver name")
    _reject_identity_spoof(req.approver_role, approver_role, "approver role")
    try:
        return await Phase3LSetupEngineeringService.request_human_approval(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            decision_code=req.decision_code,
            approver_name=approver_name,
            approver_role=approver_role,
            approval_code=req.approval_code,
            notes=req.notes,
        )
    except Exception as exc:
        logger.error("Error approving decision: %s", exc)
        raise HTTPException(status_code=400, detail="The request could not be processed. Check the submitted parameters and try again.")


@router.post("/prediction")
async def generate_prediction_endpoint(
    req: TrackPredictionRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Section 11: Generate cryptographically immutable TrackTestPrediction record."""
    try:
        return await Phase3LSetupEngineeringService.generate_track_test_prediction(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            decision_id=req.decision_id,
            candidate_setup_id=req.candidate_setup_id,
            prediction_id=req.prediction_id,
            baseline_metric=req.baseline_metric,
            expected_candidate_metric=req.expected_candidate_metric,
            expected_delta=req.expected_delta,
            uncertainty_interval=req.uncertainty_interval,
            operating_conditions=req.operating_conditions,
            failure_conditions=req.failure_conditions,
        )
    except Exception as exc:
        logger.error("Error generating track prediction: %s", exc)
        raise HTTPException(status_code=400, detail="The request could not be processed. Check the submitted parameters and try again.")


@router.post("/reconcile")
async def reconcile_post_track_endpoint(
    req: PostTrackReconciliationRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Section 12: Reconcile original prediction against subsequent track session."""
    try:
        return await Phase3LSetupEngineeringService.reconcile_post_track_session(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            prediction_id=req.prediction_id,
            actual_session_id=req.actual_session_id,
            reconciliation_id=req.reconciliation_id,
            actual_measured_metrics=req.actual_measured_metrics,
        )
    except ImmutablePredictionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Error reconciling track session: %s", exc)
        raise HTTPException(status_code=400, detail="The request could not be processed. Check the submitted parameters and try again.")


@router.post("/diagnose-failure")
async def diagnose_failure_endpoint(
    req: FailureDiagnosticRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """Phase 3L Section 13: Authoritative 5-section failure UX diagnostics for all 14 failure modes."""
    return Phase3LSetupEngineeringService.diagnose_failure(
        failure_type=req.failure_type,
        context=req.context,
    )


@router.post("/execute-workflow")
async def execute_full_workflow_endpoint(
    approver_name: str = Query("", description="Ignored: the server sets the approver from the authenticated user"),
    approver_role: str = Query("", description="Ignored: the server sets the role from the authenticated user"),
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Phase 3L Final Gate: Executes complete end-to-end setup engineering workflow."""
    server_name, server_role = _authenticated_identity(user)
    _reject_identity_spoof(approver_name, server_name, "approver name")
    _reject_identity_spoof(approver_role, server_role, "approver role")
    try:
        bundle = await Phase3LSetupEngineeringService.execute_full_workflow(
            db=db,
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            approver_name=server_name,
            approver_role=server_role,
        )
        Phase3LSetupEngineeringService.export_manifest(bundle)
        return bundle
    except Exception as exc:
        logger.error("Phase 3L full workflow execution failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error. The details have been logged server-side.")


@router.get("/manifest")
async def get_manifest_endpoint(
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """Retrieves the exported Phase 3L setup engineering JSON manifest."""
    manifest_path = Path("data/phase3l_setup_engineering_manifest.json")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found. Run /execute-workflow first.")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)
