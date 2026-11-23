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

from datetime import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, or_, select
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
from suspensionlab.backend.services.parameter_trust_validation_service import (
    ParameterTrustValidationService,
    ValidationPlanningError,
    PlanNotFoundError,
    InvalidPlanStateTransitionError,
    CriteriaImmutableAfterAuthorizationError,
    MissingEvidenceProvenanceError,
    SimulationMasqueradingAsPhysicalError,
    InvalidEvidenceScopeError,
    UnauthorizedValidationActionError,
)
from suspensionlab.backend.services.parameter_trust_dossier_service import (
    ParameterTrustDossierService,
    DossierGovernanceError,
    EvidenceNotFoundError,
    DossierNotFoundError,
    UnverifiedSourceError,
    RevokedSourceAuthorizationError,
    InvalidSignatureError,
    ArtifactIntegrityBreachError,
    UnauthorizedReviewerError,
    InvalidGovernanceTransitionError,
    ImmutableDossierError,
    ContradictoryEvidenceError,
    CrossTenantAccessError,
    _safe_uuid,
)
from suspensionlab.backend.database.models.parameter_trust import (
    ParameterTrustFleetReport,
    ParameterTrustAssemblyImpactRecord,
    DecisionParameterDependencyRecord,
    DecisionExposureAssessmentRecord,
    DecisionRobustnessAnalysisRecord,
    EngineeringValidationPlanRecord,
    ValidationEvidenceItemRecord,
    ValidationEvidenceClosureRecord,
    ValidationDecisionReassessmentRecord,
    TrustedSourceRegistryRecord,
    SourceVerificationRecord,
    EngineeringDecisionDossierRecord,
    SourceVerificationMethod,
    SourceVerificationStatus,
    EvidenceIntegrityStage,
    DossierGovernanceState,
    ReviewActionType,
    CURRENT_ROBUSTNESS_POLICY_VERSION,
    CURRENT_VALIDATION_PLANNING_POLICY_VERSION,
    EVIDENCE_INTEGRITY_POLICY_V1,
    CURRENT_EVIDENCE_INTEGRITY_POLICY_VERSION,
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


# ── PHASE 6.6 VALIDATION PLANNING & EVIDENCE CLOSURE DTO SCHEMAS ─────────────

class ValidationPlanCreateRequestDTO(BaseModel):
    decision_id: str
    parameter_name: str
    evidence_gap_id: Optional[str] = None
    parameter_path: Optional[str] = None
    validation_objective: Optional[str] = None
    validation_method: Optional[str] = None
    unit: Optional[str] = None
    measurement_definition: Optional[str] = None
    acceptance_criteria: Optional[List[Dict[str, Any]]] = None
    input_artifact_requirements: Optional[List[str]] = None
    operating_conditions: Optional[Dict[str, Any]] = None
    applicability_envelope: Optional[Dict[str, Any]] = None
    expected_outputs: Optional[List[str]] = None
    required_reviewer_role: Optional[str] = "VALIDATION_LEAD"


class ValidationPlanResponseDTO(BaseModel):
    id: str
    plan_id: str
    decision_id: str
    decision_type: Optional[str] = None
    parameter_name: str
    parameter_path: Optional[str] = None
    evidence_gap_id: Optional[str] = None
    validation_objective: Optional[str] = None
    validation_method: Optional[str] = None
    status: str
    plan_version: int
    parent_plan_id: Optional[str] = None
    exposure_assessment_id: Optional[str] = None
    robustness_analysis_id: Optional[str] = None
    analysis_snapshot_hash: Optional[str] = None
    input_artifact_requirements: Optional[List[str]] = None
    operating_conditions: Optional[Dict[str, Any]] = None
    applicability_envelope: Optional[Dict[str, Any]] = None
    unit: Optional[str] = None
    measurement_definition: Optional[str] = None
    acceptance_criteria: Optional[List[Dict[str, Any]]] = None
    criteria_established_at: Optional[str] = None
    criteria_authorized_by_user_id: Optional[str] = None
    expected_outputs: Optional[List[str]] = None
    required_reviewer_role: Optional[str] = None
    authorized_by_user_id: Optional[str] = None
    authorized_at: Optional[str] = None
    plan_hash: Optional[str] = None
    is_active: bool = True
    governance_separation_notice: Optional[str] = None
    deployment_safety_inferred: bool = False
    deployment_authorization: str = "NOT_ESTABLISHED"
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    evidence_items: Optional[List[Dict[str, Any]]] = None
    closures: Optional[List[Dict[str, Any]]] = None
    reassessments: Optional[List[Dict[str, Any]]] = None


class ValidationPlanListResponseDTO(BaseModel):
    decision_id: str
    plans: List[ValidationPlanResponseDTO]
    total: int


class ValidationPlanTransitionRequestDTO(BaseModel):
    target_status: str
    reason: Optional[str] = None
    authorized_by_role: Optional[str] = None


class EvidenceSubmissionRequestDTO(BaseModel):
    evidence_source_type: str = "PHYSICAL_RIG_MEASUREMENT"
    source_identifier: str
    parameter_name: Optional[str] = None
    observed_value: Optional[float] = None
    observed_interval: Optional[List[float]] = None
    observed_samples: Optional[List[float]] = None
    unit: Optional[str] = None
    operating_scope: Optional[Dict[str, Any]] = None
    integrity_hash: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None
    calibration_metadata: Optional[Dict[str, Any]] = None
    is_physically_validated: bool = False
    physical_limitations: Optional[str] = None
    source_timestamp: Optional[str] = None


class EvidenceItemResponseDTO(BaseModel):
    id: str
    plan_id: str
    evidence_source_type: str
    source_identifier: str
    source_timestamp: Optional[str] = None
    parameter_name: str
    observed_value: Optional[float] = None
    observed_interval: Optional[List[float]] = None
    observed_samples: Optional[List[float]] = None
    unit: Optional[str] = None
    operating_scope: Optional[Dict[str, Any]] = None
    integrity_hash: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None
    calibration_metadata: Optional[Dict[str, Any]] = None
    is_physically_validated: bool = False
    physical_limitations: Optional[str] = None
    review_status: str
    review_notes: Optional[str] = None
    reviewed_by_user_id: Optional[str] = None
    reviewed_at: Optional[str] = None
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    submitted_by_user_id: Optional[str] = None
    created_at: Optional[str] = None


class EvidenceReviewRequestDTO(BaseModel):
    review_status: str
    review_notes: Optional[str] = None
    reviewer_role: Optional[str] = None


class ClosureAssessmentRequestDTO(BaseModel):
    reviewer_notes: Optional[str] = None
    evidence_item_ids: Optional[List[str]] = None


class ClosureAssessmentResponseDTO(BaseModel):
    id: str
    plan_id: str
    decision_id: str
    parameter_name: str
    evidence_gap_id: Optional[str] = None
    closure_verdict: str
    criteria_met: bool
    criteria_evaluated: Optional[List[Dict[str, Any]]] = None
    applicability_check: Optional[Dict[str, Any]] = None
    conflict_assessment: Optional[Dict[str, Any]] = None
    uncertainty_update: Optional[Dict[str, Any]] = None
    requires_robustness_reassessment: bool = False
    closure_summary: Optional[str] = None
    closure_hash: Optional[str] = None
    governance_separation_notice: Optional[str] = None
    finite_sample_notice: Optional[str] = None
    deployment_safety_inferred: bool = False
    deployment_authorization: str = "NOT_ESTABLISHED"
    is_active: bool = True
    superseded_by: Optional[str] = None
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    evaluated_by_user_id: Optional[str] = None
    created_at: Optional[str] = None


class DecisionReassessmentRequestDTO(BaseModel):
    closure_id: Optional[str] = None
    rationale: Optional[str] = None


class DecisionReassessmentResponseDTO(BaseModel):
    id: str
    decision_id: str
    decision_type: Optional[str] = None
    plan_id: str
    closure_id: str
    original_exposure_assessment_id: Optional[str] = None
    original_robustness_analysis_id: Optional[str] = None
    new_robustness_analysis_id: Optional[str] = None
    reassessment_delta: Optional[Dict[str, Any]] = None
    reversal_status: str
    envelope_coverage_statement: Optional[str] = None
    governance_separation_notice: Optional[str] = None
    deployment_safety_inferred: bool = False
    deployment_authorization: str = "NOT_ESTABLISHED"
    reassessment_hash: Optional[str] = None
    is_active: bool = True
    superseded_by: Optional[str] = None
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    reassessed_by_user_id: Optional[str] = None
    created_at: Optional[str] = None


class DecisionReassessmentHistoryResponseDTO(BaseModel):
    decision_id: str
    reassessments: List[DecisionReassessmentResponseDTO]
    total: int


# ── PHASE 6.7 EVIDENCE INTEGRITY & DECISION DOSSIERS DTO SCHEMAS ─────────────

class SourceVerificationRequestDTO(BaseModel):
    verification_method: str
    verifier_identity: Optional[str] = None
    supporting_references: Optional[Dict[str, Any]] = None
    scope: Optional[Dict[str, Any]] = None
    verification_notes: Optional[str] = None
    signature_hex: Optional[str] = None
    public_key_pem: Optional[str] = None
    expected_artifact_hash: Optional[str] = None


class SourceVerificationResponseDTO(BaseModel):
    id: str
    evidence_item_id: str
    verification_method: str
    verification_status: str
    verifier_identity: str
    verifier_role: str
    verifier_user_id: Optional[str] = None
    verification_timestamp: str
    artifact_hash: str
    supporting_references: Dict[str, Any]
    scope: Dict[str, Any]
    verification_notes: Optional[str] = None
    verification_hash: str
    is_revoked: bool
    revocation_reason: Optional[str] = None
    created_at: str


class SourceRevocationRequestDTO(BaseModel):
    reason: Optional[str] = "Source verification revoked by authorized engineer."


class DecisionDossierCompileRequestDTO(BaseModel):
    decision_id: str
    plan_id: str
    closure_id: str
    reassessment_id: str
    engineering_question: Optional[str] = None
    decision_type: Optional[str] = "EngineeringDecision"


class DecisionDossierGovernanceTransitionRequestDTO(BaseModel):
    action_type: str
    rationale: Optional[str] = ""


class DecisionDossierSupersedeRequestDTO(BaseModel):
    new_plan_id: Optional[str] = None
    new_closure_id: Optional[str] = None
    new_reassessment_id: Optional[str] = None
    reason: Optional[str] = "Dossier superseded with updated evidence."


class TrustedSourceRegisterRequestDTO(BaseModel):
    source_identifier: str
    source_name: str
    source_type: str
    certificate_ref: Optional[str] = None
    public_key_pem: Optional[str] = None
    valid_until: Optional[str] = None


class TrustedSourceRegistryResponseDTO(BaseModel):
    id: str
    source_identifier: str
    source_name: str
    source_type: str
    is_authorized: bool
    certificate_ref: Optional[str] = None
    public_key_pem: Optional[str] = None
    valid_from: str
    valid_until: Optional[str] = None
    created_at: str


class EngineeringDecisionDossierResponseDTO(BaseModel):
    id: str
    dossier_number: str
    decision_id: str
    decision_type: str
    engineering_question: str
    dossier_version: int
    parent_dossier_id: Optional[str] = None
    plan_id: str
    plan_version: int
    plan_hash: str
    sealed_acceptance_criteria: List[Dict[str, Any]]
    exposure_assessment_id: Optional[str] = None
    exposure_hash: Optional[str] = None
    baseline_robustness_analysis_id: Optional[str] = None
    baseline_robustness_hash: Optional[str] = None
    closure_id: str
    closure_hash: str
    reassessment_id: str
    reassessment_hash: str
    reassessed_robustness_analysis_id: Optional[str] = None
    reassessed_robustness_hash: Optional[str] = None
    evidence_item_ids: List[str]
    source_verification_ids: List[str]
    evidence_lineage_summary: Dict[str, Any]
    contradictory_evidence_summary: Dict[str, Any]
    unresolved_assumptions: List[Dict[str, Any]]
    before_after_comparison: Dict[str, Any]
    governance_state: str
    admissibility_status: str
    criteria_satisfaction_status: str
    closure_status: str
    conclusion_review_status: str
    decision_approval_status: str
    governance_separation_notice: str
    deployment_authorization_status: str
    deployment_safety_inferred: bool
    review_audit_trail: List[Dict[str, Any]]
    dossier_content_hash: str
    is_active: bool
    superseded_by: Optional[str] = None
    created_at: str
    updated_at: str


class DecisionDossierListResponseDTO(BaseModel):
    decision_id: str
    dossiers: List[EngineeringDecisionDossierResponseDTO]
    total: int


# ── PHASE 6.6 VALIDATION PLANNING & EVIDENCE CLOSURE ENDPOINTS ───────────────

@router.post(
    "/validation/plans",
    response_model=ValidationPlanResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def create_validation_plan_endpoint(
    req: ValidationPlanCreateRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Creates an Engineering Validation Plan bound to an engineering decision,
    target parameter, and specific evidence gap.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustValidationService.create_validation_plan(
            db=db,
            decision_id=req.decision_id,
            parameter_name=req.parameter_name,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            evidence_gap_id=req.evidence_gap_id,
            parameter_path=req.parameter_path,
            validation_objective=req.validation_objective,
            validation_method=req.validation_method,
            unit=req.unit,
            measurement_definition=req.measurement_definition,
            acceptance_criteria=req.acceptance_criteria or [],
            input_artifact_requirements=req.input_artifact_requirements or [],
            operating_conditions=req.operating_conditions or {},
            applicability_envelope=req.applicability_envelope or {},
            expected_outputs=req.expected_outputs or [],
            required_reviewer_role=req.required_reviewer_role or "VALIDATION_LEAD",
        )
        return ValidationPlanResponseDTO(**res)
    except (DecisionNotFoundError, EntityNotFoundError, MalformedIdentifierError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (TenantIsolationError, PreRevealFirewallViolation, UnauthorizedValidationActionError) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (
        CriteriaImmutableAfterAuthorizationError,
        SimulationMasqueradingAsPhysicalError,
        MissingEvidenceProvenanceError,
        InvalidPlanStateTransitionError,
        InvalidEvidenceScopeError,
        ValidationPlanningError,
        ValueError,
    ) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/validation/plans/{plan_id}",
    response_model=ValidationPlanResponseDTO,
)
async def get_validation_plan_endpoint(
    plan_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves a validation plan, including criteria, status, and related evidence items.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustValidationService.get_validation_plan(
            db=db,
            plan_id=plan_id,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return ValidationPlanResponseDTO(**res)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/decision/{decision_id}/validation-plans",
    response_model=ValidationPlanListResponseDTO,
)
async def list_decision_validation_plans_endpoint(
    decision_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Lists all validation plans associated with an engineering decision.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustValidationService.list_plans_for_decision(
            db=db,
            decision_id=decision_id,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return ValidationPlanListResponseDTO(**res)
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post(
    "/validation/plans/{plan_id}/transition",
    response_model=ValidationPlanResponseDTO,
)
async def transition_validation_plan_endpoint(
    plan_id: str,
    req: ValidationPlanTransitionRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Transitions plan status (DRAFT -> PROPOSED -> AUTHORIZED -> IN_PROGRESS -> etc.).
    Enforces criteria sealing upon authorization and RBAC reviewer validation.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustValidationService.transition_plan_status(
            db=db,
            plan_id=plan_id,
            target_status=req.target_status,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return ValidationPlanResponseDTO(**res)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedValidationActionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (InvalidPlanStateTransitionError, ValidationPlanningError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/validation/plans/{plan_id}/version",
    response_model=ValidationPlanResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def create_new_plan_version_endpoint(
    plan_id: str,
    req: ValidationPlanCreateRequestDTO = None,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Creates a new immutable version of a plan when authorized criteria require modification.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    kwargs = {}
    if req:
        if req.acceptance_criteria is not None:
            kwargs["acceptance_criteria"] = req.acceptance_criteria
        if req.validation_objective is not None:
            kwargs["validation_objective"] = req.validation_objective
        if req.validation_method is not None:
            kwargs["validation_method"] = req.validation_method
        if req.operating_conditions is not None:
            kwargs["operating_conditions"] = req.operating_conditions
    try:
        res = await ParameterTrustValidationService.create_new_plan_version(
            db=db,
            plan_id=plan_id,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            **kwargs,
        )
        return ValidationPlanResponseDTO(**res)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedValidationActionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValidationPlanningError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/validation/plans/{plan_id}/evidence",
    response_model=EvidenceItemResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def submit_validation_evidence_endpoint(
    plan_id: str,
    req: EvidenceSubmissionRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Submits an observed validation evidence item. Enforces provenance tracking,
    Phase 5 pre-reveal firewall, and blocks simulated data masquerading as physical evidence.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        evidence_dict = req.model_dump()
        res = await ParameterTrustValidationService.submit_evidence(
            db=db,
            plan_id=plan_id,
            evidence_data=evidence_dict,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return EvidenceItemResponseDTO(**res)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PreRevealFirewallViolation as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (
        SimulationMasqueradingAsPhysicalError,
        MissingEvidenceProvenanceError,
        InvalidPlanStateTransitionError,
        InvalidEvidenceScopeError,
        ValidationPlanningError,
        ValueError,
    ) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/validation/plans/{plan_id}/evidence/{evidence_id}/review",
    response_model=EvidenceItemResponseDTO,
)
async def review_validation_evidence_endpoint(
    plan_id: str,
    evidence_id: str,
    req: EvidenceReviewRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Reviews a submitted validation evidence item (ACCEPTED, REJECTED, REVISION_REQUESTED).
    Requires authorized reviewer role.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustValidationService.review_evidence_item(
            db=db,
            evidence_id=evidence_id,
            disposition=req.review_status,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            review_notes=req.review_notes,
        )
        return EvidenceItemResponseDTO(**res)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedValidationActionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValidationPlanningError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/validation/plans/{plan_id}/closure-assessment",
    response_model=ClosureAssessmentResponseDTO,
)
async def evaluate_evidence_closure_endpoint(
    plan_id: str,
    req: Optional[ClosureAssessmentRequestDTO] = None,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Evaluates whether submitted evidence satisfies authorized acceptance criteria and closes the gap.
    Emits an immutable closure verdict without inferring deployment safety.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    reviewer_notes = req.reviewer_notes if req else None
    evidence_ids = req.evidence_item_ids if req else None
    try:
        res = await ParameterTrustValidationService.evaluate_evidence_closure(
            db=db,
            plan_id=plan_id,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            reviewer_notes=reviewer_notes,
            evidence_item_ids=evidence_ids,
        )
        return ClosureAssessmentResponseDTO(**res)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValidationPlanningError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/validation/plans/{plan_id}/reassess",
    response_model=DecisionReassessmentResponseDTO,
)
async def execute_decision_reassessment_endpoint(
    plan_id: str,
    req: Optional[DecisionReassessmentRequestDTO] = None,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Triggers decision robustness reassessment using newly closed evidence.
    Computes before-and-after deltas, reversal resolution status, and finite-sample notice.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    closure_id = req.closure_id if req else None
    rationale = req.rationale if req else None
    try:
        res = await ParameterTrustValidationService.execute_decision_reassessment(
            db=db,
            plan_id=plan_id,
            closure_id=closure_id,
            rationale=rationale,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return DecisionReassessmentResponseDTO(**res)
    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValidationPlanningError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/decision/{decision_id}/reassessments",
    response_model=DecisionReassessmentHistoryResponseDTO,
)
async def get_decision_reassessments_endpoint(
    decision_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves historical decision reassessments for an engineering decision.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        res = await ParameterTrustValidationService.get_decision_reassessments(
            db=db,
            decision_id=decision_id,
            user_context=user,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return DecisionReassessmentHistoryResponseDTO(**res)
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TenantIsolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ── PHASE 6.7 EVIDENCE INTEGRITY & DECISION DOSSIERS ENDPOINTS ────────────────

def _source_verif_to_dto(rec: SourceVerificationRecord) -> SourceVerificationResponseDTO:
    return SourceVerificationResponseDTO(
        id=str(rec.id),
        evidence_item_id=str(rec.evidence_item_id),
        verification_method=rec.verification_method,
        verification_status=rec.verification_status,
        verifier_identity=rec.verifier_identity,
        verifier_role=rec.verifier_role,
        verifier_user_id=str(rec.verifier_user_id) if rec.verifier_user_id else None,
        verification_timestamp=rec.verification_timestamp.isoformat() if rec.verification_timestamp else "",
        artifact_hash=rec.artifact_hash,
        supporting_references=rec.supporting_references or {},
        scope=rec.scope or {},
        verification_notes=rec.verification_notes,
        verification_hash=rec.verification_hash,
        is_revoked=rec.is_revoked,
        revocation_reason=rec.revocation_reason,
        created_at=rec.created_at.isoformat() if rec.created_at else "",
    )


def _dossier_to_dto(d: EngineeringDecisionDossierRecord) -> EngineeringDecisionDossierResponseDTO:
    return EngineeringDecisionDossierResponseDTO(
        id=str(d.id),
        dossier_number=d.dossier_number,
        decision_id=d.decision_id,
        decision_type=d.decision_type,
        engineering_question=d.engineering_question,
        dossier_version=d.dossier_version,
        parent_dossier_id=str(d.parent_dossier_id) if d.parent_dossier_id else None,
        plan_id=str(d.plan_id),
        plan_version=d.plan_version,
        plan_hash=d.plan_hash,
        sealed_acceptance_criteria=d.sealed_acceptance_criteria or [],
        exposure_assessment_id=str(d.exposure_assessment_id) if d.exposure_assessment_id else None,
        exposure_hash=d.exposure_hash,
        baseline_robustness_analysis_id=str(d.baseline_robustness_analysis_id) if d.baseline_robustness_analysis_id else None,
        baseline_robustness_hash=d.baseline_robustness_hash,
        closure_id=str(d.closure_id),
        closure_hash=d.closure_hash,
        reassessment_id=str(d.reassessment_id),
        reassessment_hash=d.reassessment_hash,
        reassessed_robustness_analysis_id=str(d.reassessed_robustness_analysis_id) if d.reassessed_robustness_analysis_id else None,
        reassessed_robustness_hash=d.reassessed_robustness_hash,
        evidence_item_ids=d.evidence_item_ids or [],
        source_verification_ids=d.source_verification_ids or [],
        evidence_lineage_summary=d.evidence_lineage_summary or {},
        contradictory_evidence_summary=d.contradictory_evidence_summary or {},
        unresolved_assumptions=d.unresolved_assumptions or [],
        before_after_comparison=d.before_after_comparison or {},
        governance_state=d.governance_state,
        admissibility_status=d.admissibility_status,
        criteria_satisfaction_status=d.criteria_satisfaction_status,
        closure_status=d.closure_status,
        conclusion_review_status=d.conclusion_review_status,
        decision_approval_status=d.decision_approval_status,
        governance_separation_notice=d.governance_separation_notice,
        deployment_authorization_status="NOT_ESTABLISHED",
        deployment_safety_inferred=False,
        review_audit_trail=d.review_audit_trail or [],
        dossier_content_hash=d.dossier_content_hash,
        is_active=d.is_active,
        superseded_by=str(d.superseded_by) if d.superseded_by else None,
        created_at=d.created_at.isoformat() if d.created_at else "",
        updated_at=d.updated_at.isoformat() if d.updated_at else "",
    )


def _reg_to_dto(r: TrustedSourceRegistryRecord) -> TrustedSourceRegistryResponseDTO:
    return TrustedSourceRegistryResponseDTO(
        id=str(r.id),
        source_identifier=r.source_identifier,
        source_name=r.source_name,
        source_type=r.source_type,
        is_authorized=r.is_authorized,
        certificate_ref=r.certificate_ref,
        public_key_pem=r.public_key_pem,
        valid_from=r.valid_from.isoformat() if r.valid_from else "",
        valid_until=r.valid_until.isoformat() if r.valid_until else None,
        created_at=r.created_at.isoformat() if r.created_at else "",
    )


@router.post(
    "/validation/evidence/{item_id}/verify-source",
    response_model=SourceVerificationResponseDTO,
)
async def verify_evidence_source_endpoint(
    item_id: str,
    req: SourceVerificationRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Formally verifies source identity of an ingested evidence item.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        rec = await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=item_id,
            verification_method=req.verification_method,
            user_context=user,
            supporting_references=req.supporting_references,
            scope=req.scope,
            verification_notes=req.verification_notes,
            signature_hex=req.signature_hex,
            public_key_pem=req.public_key_pem,
            expected_artifact_hash=req.expected_artifact_hash,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return _source_verif_to_dto(rec)
    except EvidenceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (PreRevealFirewallViolation, UnauthorizedReviewerError, CrossTenantAccessError) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (SimulationMasqueradingAsPhysicalError, ArtifactIntegrityBreachError, InvalidSignatureError, RevokedSourceAuthorizationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/validation/evidence/{item_id}/revoke-source",
    response_model=SourceVerificationResponseDTO,
)
async def revoke_evidence_source_endpoint(
    item_id: str,
    req: SourceRevocationRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Revokes source authorization for an evidence verification record.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        stmt = select(SourceVerificationRecord).where(
            SourceVerificationRecord.evidence_item_id == _safe_uuid(item_id),
            SourceVerificationRecord.is_revoked == False,
        ).order_by(desc(SourceVerificationRecord.created_at))
        res = await db.execute(stmt)
        verif = res.scalar_one_or_none()
        if not verif:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active verification found for evidence '{item_id}'.")

        rec = await ParameterTrustDossierService.revoke_source_verification(
            db=db,
            verification_id=verif.id,
            user_context=user,
            reason=req.reason,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return _source_verif_to_dto(rec)
    except UnauthorizedReviewerError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except DossierGovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/validation/evidence/{item_id}/source-verification",
    response_model=SourceVerificationResponseDTO,
)
async def get_evidence_source_verification_endpoint(
    item_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves the source verification record for an evidence item.
    """
    stmt = select(SourceVerificationRecord).where(
        SourceVerificationRecord.evidence_item_id == _safe_uuid(item_id)
    ).order_by(desc(SourceVerificationRecord.created_at))
    res = await db.execute(stmt)
    rec = res.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No source verification record found for evidence '{item_id}'.")
    return _source_verif_to_dto(rec)


@router.post(
    "/validation/dossiers/compile",
    response_model=EngineeringDecisionDossierResponseDTO,
)
async def compile_decision_dossier_endpoint(
    req: DecisionDossierCompileRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Compiles an authoritative Engineering Decision Dossier.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        dossier = await ParameterTrustDossierService.compile_decision_dossier(
            db=db,
            decision_id=req.decision_id,
            plan_id=req.plan_id,
            closure_id=req.closure_id,
            reassessment_id=req.reassessment_id,
            user_context=user,
            engineering_question=req.engineering_question,
            decision_type=req.decision_type or "EngineeringDecision",
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return _dossier_to_dto(dossier)
    except DossierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CrossTenantAccessError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except DossierGovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/validation/dossiers/{dossier_id}",
    response_model=EngineeringDecisionDossierResponseDTO,
)
async def get_decision_dossier_endpoint(
    dossier_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Retrieves an Engineering Decision Dossier by ID.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    team_uuid = _safe_uuid(team_id)
    org_uuid = _safe_uuid(org_id)
    stmt = select(EngineeringDecisionDossierRecord).where(
        EngineeringDecisionDossierRecord.id == _safe_uuid(dossier_id)
    )
    if org_uuid:
        stmt = stmt.where(or_(EngineeringDecisionDossierRecord.organization_id == org_uuid, EngineeringDecisionDossierRecord.organization_id.is_(None)))
    if team_uuid:
        stmt = stmt.where(or_(EngineeringDecisionDossierRecord.team_id == team_uuid, EngineeringDecisionDossierRecord.team_id.is_(None)))

    res = await db.execute(stmt)
    d = res.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Decision dossier '{dossier_id}' not found.")
    return _dossier_to_dto(d)


@router.get(
    "/validation/dossiers/by-decision/{decision_id}",
    response_model=DecisionDossierListResponseDTO,
)
async def get_decision_dossiers_for_decision_endpoint(
    decision_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Lists all decision dossiers compiled for an engineering decision.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    team_uuid = _safe_uuid(team_id)
    org_uuid = _safe_uuid(org_id)
    stmt = select(EngineeringDecisionDossierRecord).where(
        EngineeringDecisionDossierRecord.decision_id == str(decision_id)
    )
    if org_uuid:
        stmt = stmt.where(or_(EngineeringDecisionDossierRecord.organization_id == org_uuid, EngineeringDecisionDossierRecord.organization_id.is_(None)))
    if team_uuid:
        stmt = stmt.where(or_(EngineeringDecisionDossierRecord.team_id == team_uuid, EngineeringDecisionDossierRecord.team_id.is_(None)))

    stmt = stmt.order_by(desc(EngineeringDecisionDossierRecord.dossier_version))
    res = await db.execute(stmt)
    dossiers = list(res.scalars().all())
    return DecisionDossierListResponseDTO(
        decision_id=decision_id,
        dossiers=[_dossier_to_dto(d) for d in dossiers],
        total=len(dossiers),
    )


@router.post(
    "/validation/dossiers/{dossier_id}/governance-transition",
    response_model=EngineeringDecisionDossierResponseDTO,
)
async def advance_dossier_governance_endpoint(
    dossier_id: str,
    req: DecisionDossierGovernanceTransitionRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Advances a decision dossier through formal, role-controlled governance gates.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        d = await ParameterTrustDossierService.advance_dossier_governance(
            db=db,
            dossier_id=dossier_id,
            action_type=req.action_type,
            user_context=user,
            rationale=req.rationale,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return _dossier_to_dto(d)
    except DossierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (UnauthorizedReviewerError, CrossTenantAccessError) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (InvalidGovernanceTransitionError, ImmutableDossierError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/validation/dossiers/{dossier_id}/supersede",
    response_model=EngineeringDecisionDossierResponseDTO,
)
async def supersede_dossier_endpoint(
    dossier_id: str,
    req: DecisionDossierSupersedeRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Supersedes an existing decision dossier, creating version N+1.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        d = await ParameterTrustDossierService.supersede_dossier(
            db=db,
            parent_dossier_id=dossier_id,
            user_context=user,
            new_plan_id=req.new_plan_id,
            new_closure_id=req.new_closure_id,
            new_reassessment_id=req.new_reassessment_id,
            reason=req.reason,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return _dossier_to_dto(d)
    except DossierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (UnauthorizedReviewerError, CrossTenantAccessError) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except DossierGovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/validation/registries/trusted-sources",
    response_model=TrustedSourceRegistryResponseDTO,
)
async def register_trusted_source_endpoint(
    req: TrustedSourceRegisterRequestDTO,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Registers an authoritative trusted evidence source in the registry.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    try:
        valid_until_dt = datetime.fromisoformat(req.valid_until) if req.valid_until else None
        rec = await ParameterTrustDossierService.register_trusted_source(
            db=db,
            source_identifier=req.source_identifier,
            source_name=req.source_name,
            source_type=req.source_type,
            user_context=user,
            certificate_ref=req.certificate_ref,
            public_key_pem=req.public_key_pem,
            valid_until=valid_until_dt,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
        )
        return _reg_to_dto(rec)
    except UnauthorizedReviewerError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except DossierGovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/validation/registries/trusted-sources",
    response_model=List[TrustedSourceRegistryResponseDTO],
)
async def list_trusted_sources_endpoint(
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Lists registered trusted evidence sources for the tenant.
    """
    team_id, org_id, user_id = _extract_tenant_scope(user)
    team_uuid = _safe_uuid(team_id)
    org_uuid = _safe_uuid(org_id)
    stmt = select(TrustedSourceRegistryRecord)
    if org_uuid:
        stmt = stmt.where(or_(TrustedSourceRegistryRecord.organization_id == org_uuid, TrustedSourceRegistryRecord.organization_id.is_(None)))
    if team_uuid:
        stmt = stmt.where(or_(TrustedSourceRegistryRecord.team_id == team_uuid, TrustedSourceRegistryRecord.team_id.is_(None)))

    res = await db.execute(stmt)
    records = list(res.scalars().all())
    return [_reg_to_dto(r) for r in records]


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


