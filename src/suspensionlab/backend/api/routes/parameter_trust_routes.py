"""
backend/api/routes/parameter_trust_routes.py
============================================
SuspensionLab PRO — Phase 6.1 Parameter Trust Map Read-Oriented API.

Exposes authenticated, tenant-isolated, deterministic trust query endpoints:
- GET /api/v1/parameter-trust/{entity_type}/{entity_id}/{parameter}
- GET /api/v1/parameter-trust/{entity_type}/{entity_id}/{parameter}/evidence
- GET /api/v1/parameter-trust/{entity_type}/{entity_id}/{parameter}/explain
- GET /api/v1/parameter-trust/{entity_type}/{entity_id}/{parameter}/history

Strictly READ-ONLY. No mutation endpoints (no manual trust score assignment).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.parameter_trust_service import (
    ParameterTrustService,
    ParameterNotFoundError,
    CURRENT_TRUST_POLICY_VERSION,
    CURRENT_TRUST_RECENCY_POLICY_VERSION,
)
from suspensionlab.backend.services.parameter_trust_ingestion_service import (
    ParameterTrustIngestionService,
)
from suspensionlab.backend.services.parameter_trust_fleet_service import (
    ParameterTrustFleetService,
    CURRENT_FLEET_TRUST_POLICY_VERSION,
    CURRENT_SENSITIVITY_PROPAGATION_POLICY_VERSION,
)
from suspensionlab.backend.services.parameter_trust_decision_service import (
    ParameterTrustDecisionService,
    DecisionNotFoundError,
    PreRevealFirewallViolation,
    CURRENT_DECISION_TRUST_POLICY_VERSION,
)
from suspensionlab.backend.services.parameter_trust_robustness_service import (
    ParameterTrustRobustnessService,
    InvalidUncertaintyInputError,
    MissingUncertaintyEvidenceError,
    NumericalConvergenceFailure,
)
from suspensionlab.backend.database.models.parameter_trust import (
    ParameterTrustFleetReport,
    ParameterTrustAssemblyImpactRecord,
    DecisionParameterDependencyRecord,
    DecisionExposureAssessmentRecord,
    DecisionRobustnessAnalysisRecord,
    CURRENT_ROBUSTNESS_POLICY_VERSION,
)
from suspensionlab.backend.services.evidence_graph_service import (
    EntityNotFoundError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
    MalformedIdentifierError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parameter-trust", tags=["parameter-trust"])



# ── RESPONSE DTO SCHEMAS ──────────────────────────────────────────────────────

class ParameterIdentityDTO(BaseModel):
    entity_type: str
    entity_id: str
    parameter_name: str
    parameter_path: str


class ValueReferenceDTO(BaseModel):
    value: Any
    value_identity: str
    unit: str
    source_entity: str


class EvidenceItemDTO(BaseModel):
    evidence_type: str
    evidence_id: str
    artifact_hash: str
    relationship: str
    timestamp: Optional[str] = None


class ConflictItemDTO(BaseModel):
    conflict_type: str
    source_a: str
    value_a: Optional[Any] = None
    verdict_a: Optional[str] = None
    source_b: str
    value_b: Optional[Any] = None
    verdict_b: Optional[str] = None
    delta: Optional[float] = None
    delta_pct: Optional[float] = None
    detail: str


class RecencyMetadataDTO(BaseModel):
    evidence_timestamp: Optional[str] = None
    validation_timestamp: Optional[str] = None
    source_version: Optional[str] = None
    latest_supporting_validation: Optional[str] = None
    age_days: Optional[float] = None


class ExplanationDTO(BaseModel):
    state: str
    reasons: List[str]
    supporting_evidence: List[EvidenceItemDTO]
    conflicts: List[ConflictItemDTO]
    scope: Dict[str, Any]
    limitations: List[str]


class ParameterTrustResponseDTO(BaseModel):
    parameter_identity: ParameterIdentityDTO
    value_reference: ValueReferenceDTO
    unit: str
    current_trust_state: str
    policy_version: str
    scope: Dict[str, Any]
    supporting_evidence: List[EvidenceItemDTO]
    validation_coverage: str
    recency: RecencyMetadataDTO
    conflicts: List[ConflictItemDTO]
    explanation: ExplanationDTO
    assessment_hash: str


class ParameterTrustEvidenceRecordDTO(BaseModel):
    id: str
    evidence_type: str
    evidence_id: str
    artifact_hash: str
    relationship: str
    evidence_timestamp: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ParameterTrustExplanationResponseDTO(BaseModel):
    parameter_identity: ParameterIdentityDTO
    trust_state: str
    policy_version: str
    assessment_hash: str
    explanation: ExplanationDTO


class ParameterTrustHistoryItemDTO(BaseModel):
    id: str
    trust_state: str
    validation_coverage: str
    policy_version: str
    assessment_hash: str
    value_identity: str
    supporting_evidence_hashes: List[str]
    explanation: Dict[str, Any]
    conflicts: List[Dict[str, Any]]
    recency_metadata: Dict[str, Any]
    created_at: str


class ParameterTrustHistoryResponseDTO(BaseModel):
    parameter_identity: ParameterIdentityDTO
    history: List[ParameterTrustHistoryItemDTO]
    total: int


# ── HELPER FUNCTION ───────────────────────────────────────────────────────────

def _extract_tenant_scope(user: UserContext) -> Tuple[Optional[str], Optional[str], str]:
    team_id = user.team_id if getattr(user, "team_id", None) else None
    org_id = user.organization_id if getattr(user, "organization_id", None) else None
    user_id = user.user_id
    return team_id, org_id, user_id


# ── PHASE 6.3 FLEET & PROPAGATION DTO SCHEMAS ─────────────────────────────────

class FleetMemberLocatorDTO(BaseModel):
    entity_type: str
    entity_id: str


class FleetCompareRequestDTO(BaseModel):
    fleet_id: str
    parameter_name: str
    members: List[FleetMemberLocatorDTO]
    canonical_unit: Optional[str] = None
    persist_report: bool = True


class FleetSynchronizationResponseDTO(BaseModel):
    fleet_id: str
    parameter_name: str
    policy_version: str
    canonical_unit: Optional[str] = None
    report_hash: str
    cohort_size: int
    comparable_count: int
    excluded_count: int
    missing_count: int
    summary_metrics: Dict[str, Any]
    comparable_instances: List[Dict[str, Any]]
    excluded_instances: List[Dict[str, Any]]
    missing_instances: List[Dict[str, Any]]
    conflicts: List[Dict[str, Any]]
    outliers: List[Dict[str, Any]]
    validation_coverage_breakdown: Dict[str, int]
    trust_state_breakdown: Dict[str, int]
    provenance_distribution: Dict[str, int]


class FleetSummaryItemDTO(BaseModel):
    id: str
    fleet_id: str
    parameter_name: str
    canonical_unit: Optional[str] = None
    report_hash: str
    cohort_size: int
    comparable_count: int
    excluded_count: int
    missing_count: int
    summary_metrics: Dict[str, Any]
    created_at: str


class FleetSummaryResponseDTO(BaseModel):
    fleet_id: str
    reports: List[FleetSummaryItemDTO]
    total: int


class AssemblyImpactAssessmentResponseDTO(BaseModel):
    vehicle_id: str
    parameter_name: str
    assembly_name: Optional[str] = None
    component_name: Optional[str] = None
    policy_version: str
    impact_hash: Optional[str] = None
    can_propagate: bool
    reason: Optional[str] = None
    dependency_path: Optional[List[str]] = None
    direct_trust_assessment: Optional[Dict[str, Any]] = None
    sensitivity_evidence: Optional[Dict[str, Any]] = None
    impact_assessment: Optional[Dict[str, Any]] = None
    threshold_provenance: Optional[str] = "PROVISIONAL"
    deployment_safety_inferred: bool = False
    lineage_note: Optional[str] = None


class SensitivityEvidenceResponseDTO(BaseModel):
    status: str
    input_parameter: str
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    artifact_hash: Optional[str] = None
    downstream_metrics: Optional[List[Dict[str, Any]]] = None
    method: Optional[str] = None
    model_version: Optional[str] = None
    solver_version: Optional[str] = None
    operating_regime: Optional[str] = None
    created_at: Optional[str] = None
    warning: Optional[str] = None


# ── PHASE 6.3 FLEET & PROPAGATION ENDPOINTS ───────────────────────────────────

@router.post(
    "/fleet/compare",
    response_model=FleetSynchronizationResponseDTO,
)
async def compare_fleet_parameter_endpoint(
    req: FleetCompareRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Fleet-Wide Parameter Trust Synchronization endpoint.
    Compares corresponding engineering parameters across authorized fleet vehicles
    under FLEET_TRUST_POLICY_V1 without merging incompatible evidence or overwriting local parameters.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    members_payload = [{"entity_type": m.entity_type, "entity_id": m.entity_id} for m in req.members]

    report = await ParameterTrustFleetService.synchronize_fleet_parameter(
        db=db,
        fleet_id=req.fleet_id,
        parameter_name=req.parameter_name,
        member_locators=members_payload,
        team_id=team_id,
        organization_id=org_id,
        user_id=user_id,
        canonical_unit=req.canonical_unit,
        persist_report=req.persist_report,
    )
    return FleetSynchronizationResponseDTO(**report)


@router.get(
    "/fleet/{fleet_id}/summary",
    response_model=FleetSummaryResponseDTO,
)
async def get_fleet_summary_endpoint(
    fleet_id: str,
    parameter_name: Optional[str] = None,
    limit: int = 50,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves historical fleet synchronization reports for a fleet cohort under tenant scoping.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    user_uuid = uuid.UUID(str(user_id)) if user_id else None
    team_uuid = uuid.UUID(str(team_id)) if team_id else None
    org_uuid = uuid.UUID(str(org_id)) if org_id else None

    query = select(ParameterTrustFleetReport).where(ParameterTrustFleetReport.fleet_id == fleet_id)
    if team_uuid:
        query = query.where(ParameterTrustFleetReport.team_id == team_uuid)
    elif org_uuid:
        query = query.where(ParameterTrustFleetReport.organization_id == org_uuid)
    elif user_uuid:
        query = query.where(ParameterTrustFleetReport.user_id == user_uuid)

    if parameter_name:
        query = query.where(ParameterTrustFleetReport.parameter_name == parameter_name.strip().lower())

    query = query.order_by(desc(ParameterTrustFleetReport.created_at)).limit(limit)
    res = await db.execute(query)
    records = res.scalars().all()

    items = [
        FleetSummaryItemDTO(
            id=str(r.id),
            fleet_id=r.fleet_id,
            parameter_name=r.parameter_name,
            canonical_unit=r.canonical_unit,
            report_hash=r.report_hash,
            cohort_size=r.cohort_size,
            comparable_count=r.comparable_count,
            excluded_count=r.excluded_count,
            missing_count=r.missing_count,
            summary_metrics=r.summary_metrics or {},
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in records
    ]

    return FleetSummaryResponseDTO(fleet_id=fleet_id, reports=items, total=len(items))


@router.get(
    "/assembly/impact",
    response_model=AssemblyImpactAssessmentResponseDTO,
)
async def assess_assembly_impact_endpoint(
    vehicle_id: str,
    parameter_name: str,
    assembly_name: Optional[str] = None,
    component_name: Optional[str] = None,
    persist_record: bool = True,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Assembly-Aware Trust Propagation endpoint under SENSITIVITY_PROPAGATION_POLICY_V1.
    Strict Invariant: DIRECT TRUST IS DECOUPLED FROM PROPAGATED IMPACT.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    result = await ParameterTrustFleetService.assess_assembly_impact(
        db=db,
        vehicle_id=vehicle_id,
        parameter_name=parameter_name,
        assembly_name=assembly_name,
        component_name=component_name,
        team_id=team_id,
        organization_id=org_id,
        user_id=user_id,
        persist_record=persist_record,
    )
    return AssemblyImpactAssessmentResponseDTO(**result)


@router.get(
    "/sensitivity/evidence",
    response_model=SensitivityEvidenceResponseDTO,
)
async def get_sensitivity_evidence_endpoint(
    parameter_name: str,
    vehicle_id: Optional[str] = None,
    setup_id: Optional[str] = None,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Authoritative sensitivity evidence lookup endpoint.
    Strict Invariant: Missing sensitivity is represented as SENSITIVITY_UNAVAILABLE, never zero.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    evidence = await ParameterTrustFleetService.resolve_sensitivity_evidence(
        db=db,
        parameter_name=parameter_name,
        vehicle_id=vehicle_id,
        setup_id=setup_id,
        team_id=team_id,
        organization_id=org_id,
        user_id=user_id,
    )
    return SensitivityEvidenceResponseDTO(**evidence)


# ── PHASE 6.4 DECISION TRUST DTO SCHEMAS ──────────────────────────────────────

class DecisionExposureAssessRequestDTO(BaseModel):
    decision_id: str
    decision_type: str = "EngineeringDecision"
    force_reassess: bool = False
    persist_record: bool = True


class DecisionReassessRequestDTO(BaseModel):
    decision_id: str
    decision_type: str = "EngineeringDecision"


class DecisionExposureAssessmentResponseDTO(BaseModel):
    decision_id: str
    decision_type: str
    policy_version: str
    assessment_id: Optional[str] = None
    assessment_hash: str
    input_snapshot_hash: str
    exposure_classification: str
    exposure_summary: str
    threshold_provenance: Optional[str] = "PROVISIONAL"
    threshold_metadata: Optional[Dict[str, Any]] = None
    parameter_dependencies: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_gaps: List[Dict[str, Any]] = Field(default_factory=list)
    actionable_recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    differential: Optional[Dict[str, Any]] = None
    governance_separation: Dict[str, Any]
    governance_separation_notice: str
    created_at: str


class DecisionDependenciesResponseDTO(BaseModel):
    decision_id: str
    decision_type: str
    dependencies: List[Dict[str, Any]]
    total: int


class DecisionGapsResponseDTO(BaseModel):
    decision_id: str
    decision_type: str
    exposure_classification: str
    evidence_gaps: List[Dict[str, Any]]
    actionable_recommendations: List[Dict[str, Any]]
    total_gaps: int


class DecisionHistoryItemDTO(BaseModel):
    assessment_id: str
    decision_id: str
    policy_version: str
    assessment_hash: str
    input_snapshot_hash: str
    exposure_classification: str
    exposure_summary: str
    gaps_count: int
    dependencies_count: int
    is_active: bool
    superseded_by: Optional[str] = None
    created_at: str


class DecisionHistoryResponseDTO(BaseModel):
    decision_id: str
    history: List[DecisionHistoryItemDTO]
    total: int


# ── PHASE 6.5 DECISION ROBUSTNESS DTOs ────────────────────────────────────────

class RobustnessPreflightRequestDTO(BaseModel):
    decision_id: str
    decision_type: str = "EngineeringDecision"
    uncertainty_inputs: List[Dict[str, Any]] = Field(default_factory=list)


class RobustnessPreflightResponseDTO(BaseModel):
    decision_id: str
    decision_type: str
    is_ready: bool
    validation_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    matched_parameters_count: int
    missing_evidence_parameters: List[str] = Field(default_factory=list)
    recomputable_kpis: List[Dict[str, Any]] = Field(default_factory=list)
    policy_version: str


class RobustnessAnalysisRequestDTO(BaseModel):
    decision_id: str
    decision_type: str = "EngineeringDecision"
    uncertainty_inputs: List[Dict[str, Any]] = Field(default_factory=list)
    correlated_groups: List[Dict[str, Any]] = Field(default_factory=list)
    target_kpi: str = "damping_ratio"
    decision_threshold: Optional[float] = None
    optimization_direction: str = "MAXIMIZE"
    threshold_range: Optional[Tuple[float, float]] = None
    persist_record: bool = True


class RobustnessAnalysisResponseDTO(BaseModel):
    decision_id: str
    decision_type: str
    policy_version: str
    analysis_hash: str
    input_snapshot_hash: str
    robustness_classification: str
    robustness_summary: str
    selected_option: str
    target_kpi: str
    evaluated_envelope: Dict[str, Any]
    evaluated_scenarios_count: int
    reversals_count: int
    reversal_scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    boundary_crossings: List[Dict[str, Any]] = Field(default_factory=list)
    dominant_uncertainties: List[Dict[str, Any]] = Field(default_factory=list)
    voi_prioritizations: List[Dict[str, Any]] = Field(default_factory=list)
    solver_failures: List[Dict[str, Any]] = Field(default_factory=list)
    governance_separation_notice: str
    deployment_safety_inferred: bool = False
    deployment_authorization: str = "NOT_ESTABLISHED"
    is_active: bool = True
    created_at: Optional[str] = None


class DecisionBoundariesResponseDTO(BaseModel):
    decision_id: str
    boundary_crossings: List[Dict[str, Any]]
    total: int


class DecisionVOIResponseDTO(BaseModel):
    decision_id: str
    voi_prioritizations: List[Dict[str, Any]]
    total: int


class RobustnessHistoryResponseDTO(BaseModel):
    decision_id: str
    history: List[Dict[str, Any]]
    total: int



# ── PHASE 6.4 DECISION TRUST ENDPOINTS ────────────────────────────────────────

@router.post(
    "/decision/assess",
    response_model=DecisionExposureAssessmentResponseDTO,
)
async def assess_decision_exposure_endpoint(
    req: DecisionExposureAssessRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Evaluates an engineering decision or problem's exposure to underlying parameter uncertainty
    under DECISION_TRUST_POLICY_V1. Enforces strict tenant boundaries and pre-reveal firewalls.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        res = await ParameterTrustDecisionService.assess_decision_exposure(
            db=db,
            decision_id=req.decision_id,
            decision_type=req.decision_type,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            force_reassess=req.force_reassess,
            persist_record=req.persist_record,
        )
        return DecisionExposureAssessmentResponseDTO(**res)
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except PreRevealFirewallViolation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/decision/{decision_id}",
    response_model=DecisionExposureAssessmentResponseDTO,
)
async def get_decision_exposure_endpoint(
    decision_id: str,
    decision_type: str = "EngineeringDecision",
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves the active exposure assessment for an engineering decision.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        res = await ParameterTrustDecisionService.assess_decision_exposure(
            db=db,
            decision_id=decision_id,
            decision_type=decision_type,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            force_reassess=False,
            persist_record=False,
        )
        return DecisionExposureAssessmentResponseDTO(**res)
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except PreRevealFirewallViolation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/decision/{decision_id}/dependencies",
    response_model=DecisionDependenciesResponseDTO,
)
async def get_decision_dependencies_endpoint(
    decision_id: str,
    decision_type: str = "EngineeringDecision",
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Inspects parameter dependencies relevant to an engineering decision,
    distinguishing directly evidenced, quantitative, qualitative, and unresolved associations.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        decision_info = await ParameterTrustDecisionService.resolve_decision(
            db=db,
            decision_id=decision_id,
            decision_type=decision_type,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        deps = await ParameterTrustDecisionService.discover_decision_dependencies(
            db=db,
            decision_info=decision_info,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return DecisionDependenciesResponseDTO(
            decision_id=decision_id,
            decision_type=decision_type,
            dependencies=deps,
            total=len(deps),
        )
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except PreRevealFirewallViolation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/decision/{decision_id}/gaps",
    response_model=DecisionGapsResponseDTO,
)
async def get_decision_gaps_endpoint(
    decision_id: str,
    decision_type: str = "EngineeringDecision",
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves prioritized actionable evidence gaps and candidate experiment recommendations.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        res = await ParameterTrustDecisionService.assess_decision_exposure(
            db=db,
            decision_id=decision_id,
            decision_type=decision_type,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            force_reassess=False,
            persist_record=False,
        )
        return DecisionGapsResponseDTO(
            decision_id=decision_id,
            decision_type=decision_type,
            exposure_classification=res["exposure_classification"],
            evidence_gaps=res["evidence_gaps"],
            actionable_recommendations=res["actionable_recommendations"],
            total_gaps=len(res["evidence_gaps"]),
        )
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except PreRevealFirewallViolation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/decision/{decision_id}/history",
    response_model=DecisionHistoryResponseDTO,
)
async def get_decision_history_endpoint(
    decision_id: str,
    limit: int = 50,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves chronological assessment revisions and supersession lineage.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        await ParameterTrustDecisionService.resolve_decision(
            db=db,
            decision_id=decision_id,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        hist = await ParameterTrustDecisionService.get_assessment_history(
            db=db,
            decision_id=decision_id,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            limit=limit,
        )
        items = [DecisionHistoryItemDTO(**h) for h in hist]
        return DecisionHistoryResponseDTO(
            decision_id=decision_id,
            history=items,
            total=len(items),
        )
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except PreRevealFirewallViolation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post(
    "/decision/reassess",
    response_model=DecisionExposureAssessmentResponseDTO,
)
async def reassess_decision_exposure_endpoint(
    req: DecisionReassessRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Forces a fresh assessment of decision exposure, superseding previous active assessments
    and providing an explicit differential rationale.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        res = await ParameterTrustDecisionService.assess_decision_exposure(
            db=db,
            decision_id=req.decision_id,
            decision_type=req.decision_type,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            force_reassess=True,
            persist_record=True,
        )
        return DecisionExposureAssessmentResponseDTO(**res)
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except PreRevealFirewallViolation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ── PHASE 6.5 DECISION ROBUSTNESS ENDPOINTS ────────────────────────────────────

@router.post(
    "/decision/robustness/preflight",
    response_model=RobustnessPreflightResponseDTO,
)
async def preflight_robustness_endpoint(
    req: RobustnessPreflightRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Validates parameter uncertainty inputs against decision premises and dependencies.
    Identifies missing uncertainty evidence, unsupported assumptions, and recomputable KPIs.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustRobustnessService.preflight_robustness(
            db=db,
            decision_id=req.decision_id,
            decision_type=req.decision_type,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            uncertainty_inputs=req.uncertainty_inputs,
        )
        return RobustnessPreflightResponseDTO(**res)
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidUncertaintyInputError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/decision/robustness/analyze",
    response_model=RobustnessAnalysisResponseDTO,
)
async def run_robustness_analysis_endpoint(
    req: RobustnessAnalysisRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Executes deterministic decision robustness evaluation across the documented uncertainty envelope.
    Evaluates extreme corner scenarios and sensitivity-directed search. Detects ranking reversals,
    constraint violations, dominant uncertainties, and value-of-information priorities.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustRobustnessService.run_robustness_analysis(
            db=db,
            decision_id=req.decision_id,
            decision_type=req.decision_type,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            uncertainty_inputs=req.uncertainty_inputs,
            correlated_groups=req.correlated_groups,
            target_kpi=req.target_kpi,
            decision_threshold=req.decision_threshold,
            optimization_direction=req.optimization_direction,
            threshold_range=req.threshold_range,
            persist_record=req.persist_record,
        )
        return RobustnessAnalysisResponseDTO(**res)
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidUncertaintyInputError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/decision/{decision_id}/robustness",
    response_model=RobustnessAnalysisResponseDTO,
)
async def get_decision_robustness_endpoint(
    decision_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves the active robustness assessment for an engineering decision.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustRobustnessService.get_active_robustness_analysis(
            db=db,
            decision_id=decision_id,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        if not res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active robustness analysis found for decision '{decision_id}'.",
            )
        return RobustnessAnalysisResponseDTO(**res)
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/decision/{decision_id}/robustness/boundaries",
    response_model=DecisionBoundariesResponseDTO,
)
async def get_decision_boundaries_endpoint(
    decision_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves demonstrated and numerically approximated decision boundary crossings.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustRobustnessService.get_active_robustness_analysis(
            db=db,
            decision_id=decision_id,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        if not res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active robustness analysis found for decision '{decision_id}'.",
            )
        crossings = res.get("boundary_crossings", [])
        return DecisionBoundariesResponseDTO(
            decision_id=decision_id,
            boundary_crossings=crossings,
            total=len(crossings),
        )
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/decision/{decision_id}/robustness/voi",
    response_model=DecisionVOIResponseDTO,
)
async def get_decision_voi_endpoint(
    decision_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves qualitative, traceable Value-of-Information (VOI) evidence prioritizations.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustRobustnessService.get_active_robustness_analysis(
            db=db,
            decision_id=decision_id,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        if not res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active robustness analysis found for decision '{decision_id}'.",
            )
        prioritizations = res.get("voi_prioritizations", [])
        return DecisionVOIResponseDTO(
            decision_id=decision_id,
            voi_prioritizations=prioritizations,
            total=len(prioritizations),
        )
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/decision/{decision_id}/robustness/history",
    response_model=RobustnessHistoryResponseDTO,
)
async def get_decision_robustness_history_endpoint(
    decision_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves audit history of robustness analyses for an engineering decision.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        hist_data = await ParameterTrustRobustnessService.get_robustness_history(
            db=db,
            decision_id=decision_id,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        items = hist_data.get("history", []) if isinstance(hist_data, dict) else list(hist_data)
        return RobustnessHistoryResponseDTO(
            decision_id=decision_id,
            history=[dict(h) for h in items],
            total=len(items),
        )
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ── ENDPOINTS ──────────────────────────────────────────────────────────────────

@router.get(
    "/{entity_type}/{entity_id}/{parameter}",
    response_model=ParameterTrustResponseDTO,
)
async def get_parameter_trust_endpoint(
    entity_type: str,
    entity_id: str,
    parameter: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves the authoritative trust posture for a specific engineering parameter.
    Enforces tenant boundaries and derives trust deterministically from evidence.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        profile = await ParameterTrustService.get_or_assess_parameter_trust(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            parameter_name=parameter,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
    except (EntityNotFoundError, ParameterNotFoundError, TenantIsolationError, MalformedIdentifierError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parameter '{parameter}' for '{entity_type}:{entity_id}' not found.",
        )
    except UnsupportedEntityTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    ev_list = [
        EvidenceItemDTO(
            evidence_type=e.get("evidence_type", ""),
            evidence_id=e.get("evidence_id", ""),
            artifact_hash=e.get("artifact_hash", ""),
            relationship=e.get("relationship", ""),
            timestamp=e.get("timestamp"),
        )
        for e in profile.explanation.get("supporting_evidence", [])
    ]

    conf_list = [
        ConflictItemDTO(
            conflict_type=c.get("conflict_type", ""),
            source_a=c.get("source_a", ""),
            value_a=c.get("value_a"),
            verdict_a=c.get("verdict_a"),
            source_b=c.get("source_b", ""),
            value_b=c.get("value_b"),
            verdict_b=c.get("verdict_b"),
            delta=c.get("delta"),
            delta_pct=c.get("delta_pct"),
            detail=c.get("detail", ""),
        )
        for c in (profile.conflicts or [])
    ]

    exp = profile.explanation or {}
    explanation_dto = ExplanationDTO(
        state=exp.get("state", profile.current_trust_state),
        reasons=exp.get("reasons", []),
        supporting_evidence=ev_list,
        conflicts=conf_list,
        scope=exp.get("scope", profile.scope or {}),
        limitations=exp.get("limitations", []),
    )

    rec_meta = profile.recency_metadata or {}
    recency_dto = RecencyMetadataDTO(
        evidence_timestamp=rec_meta.get("evidence_timestamp"),
        validation_timestamp=rec_meta.get("validation_timestamp"),
        source_version=rec_meta.get("source_version"),
        latest_supporting_validation=rec_meta.get("latest_supporting_validation"),
        age_days=rec_meta.get("age_days"),
    )

    val_ref = profile.value_reference or {}
    return ParameterTrustResponseDTO(
        parameter_identity=ParameterIdentityDTO(
            entity_type=profile.entity_type,
            entity_id=profile.entity_id,
            parameter_name=profile.parameter_name,
            parameter_path=profile.parameter_path,
        ),
        value_reference=ValueReferenceDTO(
            value=val_ref.get("value"),
            value_identity=val_ref.get("value_identity", ""),
            unit=val_ref.get("unit", profile.unit or ""),
            source_entity=val_ref.get("source_entity", f"{profile.entity_type}:{profile.entity_id}"),
        ),
        unit=profile.unit or val_ref.get("unit", ""),
        current_trust_state=profile.current_trust_state,
        policy_version=profile.policy_version,
        scope=profile.scope or {},
        supporting_evidence=ev_list,
        validation_coverage=profile.validation_coverage,
        recency=recency_dto,
        conflicts=conf_list,
        explanation=explanation_dto,
        assessment_hash=profile.assessment_hash,
    )


@router.get(
    "/{entity_type}/{entity_id}/{parameter}/evidence",
    response_model=List[ParameterTrustEvidenceRecordDTO],
)
async def get_parameter_evidence_endpoint(
    entity_type: str,
    entity_id: str,
    parameter: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Returns supporting evidence references linking this parameter to authoritative engineering artifacts.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        evs = await ParameterTrustService.get_parameter_evidence(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            parameter_name=parameter,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
    except (EntityNotFoundError, ParameterNotFoundError, TenantIsolationError, MalformedIdentifierError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parameter '{parameter}' for '{entity_type}:{entity_id}' not found.",
        )
    except UnsupportedEntityTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return [ParameterTrustEvidenceRecordDTO(**e) for e in evs]


@router.get(
    "/{entity_type}/{entity_id}/{parameter}/explain",
    response_model=ParameterTrustExplanationResponseDTO,
)
async def explain_parameter_trust_endpoint(
    entity_type: str,
    entity_id: str,
    parameter: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Returns the deterministic, auditable explanation object for this parameter's trust state.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        res = await ParameterTrustService.explain_parameter_trust(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            parameter_name=parameter,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
    except (EntityNotFoundError, ParameterNotFoundError, TenantIsolationError, MalformedIdentifierError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parameter '{parameter}' for '{entity_type}:{entity_id}' not found.",
        )
    except UnsupportedEntityTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    exp = res["explanation"]
    ev_list = [
        EvidenceItemDTO(
            evidence_type=e.get("evidence_type", ""),
            evidence_id=e.get("evidence_id", ""),
            artifact_hash=e.get("artifact_hash", ""),
            relationship=e.get("relationship", ""),
            timestamp=e.get("timestamp"),
        )
        for e in exp.get("supporting_evidence", [])
    ]
    conf_list = [
        ConflictItemDTO(
            conflict_type=c.get("conflict_type", ""),
            source_a=c.get("source_a", ""),
            value_a=c.get("value_a"),
            verdict_a=c.get("verdict_a"),
            source_b=c.get("source_b", ""),
            value_b=c.get("value_b"),
            verdict_b=c.get("verdict_b"),
            delta=c.get("delta"),
            delta_pct=c.get("delta_pct"),
            detail=c.get("detail", ""),
        )
        for c in exp.get("conflicts", [])
    ]

    return ParameterTrustExplanationResponseDTO(
        parameter_identity=ParameterIdentityDTO(**res["parameter_identity"]),
        trust_state=res["trust_state"],
        policy_version=res["policy_version"],
        assessment_hash=res["assessment_hash"],
        explanation=ExplanationDTO(
            state=exp.get("state", res["trust_state"]),
            reasons=exp.get("reasons", []),
            supporting_evidence=ev_list,
            conflicts=conf_list,
            scope=exp.get("scope", {}),
            limitations=exp.get("limitations", []),
        ),
    )


@router.get(
    "/{entity_type}/{entity_id}/{parameter}/history",
    response_model=ParameterTrustHistoryResponseDTO,
)
async def get_parameter_trust_history_endpoint(
    entity_type: str,
    entity_id: str,
    parameter: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Returns the chronological assessment history for this parameter.
    Deterministically ordered by created_at desc, id asc.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        history = await ParameterTrustService.get_parameter_trust_history(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            parameter_name=parameter,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
    except (EntityNotFoundError, ParameterNotFoundError, TenantIsolationError, MalformedIdentifierError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parameter '{parameter}' for '{entity_type}:{entity_id}' not found.",
        )
    except UnsupportedEntityTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    items = [ParameterTrustHistoryItemDTO(**h) for h in history]
    return ParameterTrustHistoryResponseDTO(
        parameter_identity=ParameterIdentityDTO(
            entity_type=entity_type,
            entity_id=entity_id,
            parameter_name=parameter,
            parameter_path="",
        ),
        history=items,
        total=len(items),
    )


# ── PHASE 6.2 INGESTION & SWEEP ANALYSIS DTOs ─────────────────────────────────

class EntityIngestRequestDTO(BaseModel):
    entity_type: str
    entity_id: str
    force_reassess: bool = False


class BatchEntityItemDTO(BaseModel):
    entity_type: str
    entity_id: str


class BatchIngestRequestDTO(BaseModel):
    entities: List[BatchEntityItemDTO]
    force_reassess: bool = False


class BatchIngestProfileSummaryDTO(BaseModel):
    entity_type: str
    entity_id: str
    parameter_name: str
    trust_state: str
    validation_coverage: str
    assessment_hash: str
    unit: str
    has_conflicts: bool
    recency_condition: str


class BatchIngestSummaryResponseDTO(BaseModel):
    batch_id: str
    batch_hash: str
    policy_version: str
    recency_policy_version: str
    discovered_entities: int
    discovered_parameters: int
    new_profiles: int
    refreshed_assessments: int
    unchanged_assessments: int
    linked_evidence_count: int
    conflicts_found: int
    skipped_entities: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    profiles: List[BatchIngestProfileSummaryDTO] = Field(default_factory=list)


class ParameterSweepCandidateDTO(BaseModel):
    entity_type: str
    entity_id: str


class ParameterSweepAnalysisRequestDTO(BaseModel):
    parameter_name: str
    candidates: List[ParameterSweepCandidateDTO]
    baseline_candidate: Optional[ParameterSweepCandidateDTO] = None


class ParameterSweepObservationDTO(BaseModel):
    entity_type: str
    entity_id: str
    value: Any
    numeric_value: Optional[float] = None
    unit: str
    trust_state: str
    validation_coverage: str
    provenance_class: str
    assessment_hash: str
    is_comparable: bool
    exclusion_reason: Optional[str] = None
    scope: Dict[str, Any] = Field(default_factory=dict)
    conflicts_count: int = 0


class ParameterSweepMetricsDTO(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    delta: Optional[float] = None
    mean: Optional[float] = None
    spread: Optional[float] = None
    unit: str = ""


class ParameterSweepEvidenceGapsDTO(BaseModel):
    unvalidated_candidates: List[str]
    validated_candidates: List[str]
    coverage_pct: float


class ParameterSweepAnalysisResponseDTO(BaseModel):
    parameter_name: str
    policy_version: str
    canonical_unit: str
    sweep_hash: str
    total_observations: int
    comparable_count: int
    excluded_count: int
    baseline_value: Optional[float] = None
    baseline_unit: Optional[str] = None
    summary_metrics: ParameterSweepMetricsDTO
    validation_coverage_breakdown: Dict[str, int]
    trust_state_breakdown: Dict[str, int]
    evidence_gaps: ParameterSweepEvidenceGapsDTO
    observations: List[ParameterSweepObservationDTO]
    excluded_observations: List[Dict[str, Any]] = Field(default_factory=list)
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    outcome_associations: List[Dict[str, Any]] = Field(default_factory=list)


# ── PHASE 6.2 INGESTION & SWEEP ENDPOINTS ──────────────────────────────────────

@router.post(
    "/ingest/entity",
    response_model=BatchIngestSummaryResponseDTO,
)
async def ingest_entity_endpoint(
    req: EntityIngestRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Automated ingestion of all parameters belonging to a single authoritative entity.
    Discovers parameters, reconciles profiles, links evidence, and computes deterministic assessments.
    Enforces tenant boundaries and idempotency.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    try:
        res = await ParameterTrustIngestionService.ingest_batch(
            db=db,
            entities=[{"entity_type": req.entity_type, "entity_id": req.entity_id}],
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            force_reassess=req.force_reassess,
        )
        return BatchIngestSummaryResponseDTO(**res)
    except (EntityNotFoundError, MalformedIdentifierError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except UnsupportedEntityTypeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/ingest/batch",
    response_model=BatchIngestSummaryResponseDTO,
)
async def ingest_batch_endpoint(
    req: BatchIngestRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Idempotent batch ingestion across multiple authoritative entities.
    Safely isolates partial failures, skips unsupported sources, and returns a deterministic batch report.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    entities_payload = [
        {"entity_type": item.entity_type, "entity_id": item.entity_id}
        for item in req.entities
    ]

    res = await ParameterTrustIngestionService.ingest_batch(
        db=db,
        entities=entities_payload,
        team_id=team_id,
        organization_id=org_id,
        user_id=user_id,
        force_reassess=req.force_reassess,
    )
    return BatchIngestSummaryResponseDTO(**res)


@router.post(
    "/sweep/analyze",
    response_model=ParameterSweepAnalysisResponseDTO,
)
async def analyze_parameter_sweep_endpoint(
    req: ParameterSweepAnalysisRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Performs cross-candidate parameter sweep analysis.
    Verifies physical and operating regime comparability, computes numerical range metrics,
    identifies validation coverage gaps, and highlights conflicting observations.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)

    candidates_payload = [
        {"entity_type": c.entity_type, "entity_id": c.entity_id}
        for c in req.candidates
    ]
    base_payload = None
    if req.baseline_candidate:
        base_payload = {
            "entity_type": req.baseline_candidate.entity_type,
            "entity_id": req.baseline_candidate.entity_id,
        }

    try:
        report = await ParameterTrustIngestionService.analyze_parameter_sweep(
            db=db,
            parameter_name=req.parameter_name,
            candidates=candidates_payload,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            baseline_candidate=base_payload,
        )
        return ParameterSweepAnalysisResponseDTO(**report)
    except UnsupportedEntityTypeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))





