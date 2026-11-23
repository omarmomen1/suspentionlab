"""
backend/database/models/parameter_trust.py
==========================================
SuspensionLab PRO — Phase 6.1 Parameter Trust Map Canonical Database Models.

Defines the normalized, auditable trust layer entities:
    Authoritative Engineering Parameter
                 ↓
      ParameterTrustProfile
                 ↓
      ParameterTrustEvidenceRecord
                 ↓
      ParameterTrustAssessmentRecord

Core Invariants:
1. Pure provenance/trust layer: references authoritative parameters, NEVER overwrites them.
2. Zero duplicate parameter stores.
3. Explicit Trust States & Validation Coverage vocabularies (no magic scores).
4. Deterministic SHA-256 assessment hash.
5. Strict tenant isolation (organization_id, team_id, user_id).
6. Immutable historical assessments for auditable compliance.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")

from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


TRUST_POLICY_V1 = "TRUST_POLICY_V1"
CURRENT_TRUST_POLICY_VERSION = TRUST_POLICY_V1

TRUST_RECENCY_POLICY_V1 = "TRUST_RECENCY_POLICY_V1"
CURRENT_TRUST_RECENCY_POLICY_VERSION = TRUST_RECENCY_POLICY_V1
DEFAULT_RECENCY_ADVISORY_THRESHOLD_DAYS = 180.0

FLEET_TRUST_POLICY_V1 = "FLEET_TRUST_POLICY_V1"
CURRENT_FLEET_TRUST_POLICY_VERSION = FLEET_TRUST_POLICY_V1

SENSITIVITY_PROPAGATION_POLICY_V1 = "SENSITIVITY_PROPAGATION_POLICY_V1"
CURRENT_SENSITIVITY_PROPAGATION_POLICY_VERSION = SENSITIVITY_PROPAGATION_POLICY_V1

DECISION_TRUST_POLICY_V1 = "DECISION_TRUST_POLICY_V1"
CURRENT_DECISION_TRUST_POLICY_VERSION = DECISION_TRUST_POLICY_V1


class DependencyNature(str, enum.Enum):
    """
    Formal classification of parameter dependency nature relative to an engineering decision (Phase 6.4).
    Strictly distinguishes directly evidenced, quantitative, and qualitative associations.
    Never equates a qualitative hypothesis with a proven causal derivative.
    """
    DIRECTLY_EVIDENCED = "DIRECTLY_EVIDENCED"
    QUANTITATIVELY_SENSITIVE = "QUANTITATIVELY_SENSITIVE"
    QUALITATIVE_HYPOTHESIS = "QUALITATIVE_HYPOTHESIS"
    UNRESOLVED_DEPENDENCY = "UNRESOLVED_DEPENDENCY"


class DecisionExposureClassification(str, enum.Enum):
    """
    Versioned decision exposure classifications under DECISION_TRUST_POLICY_V1 (Phase 6.4).
    Explicit qualitative categories; zero arbitrary weighted scores.
    """
    LOW_EXPOSURE = "LOW_EXPOSURE"
    MODERATE_EXPOSURE = "MODERATE_EXPOSURE"
    HIGH_EXPOSURE = "HIGH_EXPOSURE"
    CRITICAL_CONFLICT_EXPOSURE = "CRITICAL_CONFLICT_EXPOSURE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_ASSESSED = "NOT_ASSESSED"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class EvidenceGapSeverity(str, enum.Enum):
    """
    Severity classification for actionable evidence gaps limiting an engineering decision (Phase 6.4).
    """
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    ADVISORY = "ADVISORY"


ROBUSTNESS_POLICY_V1 = "ROBUSTNESS_POLICY_V1"
CURRENT_ROBUSTNESS_POLICY_VERSION = ROBUSTNESS_POLICY_V1
GOVERNANCE_ROBUSTNESS_SEPARATION_NOTICE = (
    "GOVERNANCE & SAFETY SEPARATION: Analytical decision robustness does not constitute engineering approval, "
    "deployment safety certification, or vehicle commissioning authorization. "
    "Those determinations require independent role-based governance gates."
)


class UncertaintyRepresentationType(str, enum.Enum):
    """
    Classification of parameter uncertainty representation (Phase 6.5).
    Strictly distinguishes measured intervals, measurement tolerance, empirical samples,
    and correlated sets. Never invents unsupported distributions or independence.
    """
    INTERVAL_BOUNDED = "INTERVAL_BOUNDED"
    MEASUREMENT_TOLERANCE = "MEASUREMENT_TOLERANCE"
    EMPIRICAL_SAMPLES = "EMPIRICAL_SAMPLES"
    CORRELATED_SET = "CORRELATED_SET"
    UNKNOWN_INSUFFICIENT = "UNKNOWN_INSUFFICIENT"


class DecisionRobustnessClassification(str, enum.Enum):
    """
    Decision robustness classifications under ROBUSTNESS_POLICY_V1 (Phase 6.5).
    Evaluated strictly across the documented uncertainty envelope.
    No universal robustness percentage.
    """
    ROBUST_ACROSS_ENVELOPE = "ROBUST_ACROSS_ENVELOPE"
    FRAGILE_REVERSAL_DEMONSTRATED = "FRAGILE_REVERSAL_DEMONSTRATED"
    CONSTRAINT_VIOLATION_DEMONSTRATED = "CONSTRAINT_VIOLATION_DEMONSTRATED"
    SENSITIVITY_DOMINATED_UNSTABLE = "SENSITIVITY_DOMINATED_UNSTABLE"
    UNCERTAINTY_INSUFFICIENT_EVIDENCE = "UNCERTAINTY_INSUFFICIENT_EVIDENCE"


class BoundaryCrossingType(str, enum.Enum):
    """
    Classification of decision boundary crossings (Phase 6.5).
    """
    DEMONSTRATED_BOUNDARY_CROSSING = "DEMONSTRATED_BOUNDARY_CROSSING"
    NUMERICALLY_APPROXIMATED_CROSSING = "NUMERICALLY_APPROXIMATED_CROSSING"
    UNRESOLVED_BOUNDARY = "UNRESOLVED_BOUNDARY"
    OUTSIDE_MODEL_APPLICABILITY = "OUTSIDE_MODEL_APPLICABILITY"


class VOIPriorityLevel(str, enum.Enum):
    """
    Qualitative Value-of-Information evidence prioritization levels (Phase 6.5).
    Traceable to demonstrated decision reversal, sensitivity elasticity, and evidence gaps.
    Zero fabricated economic costs or expected information gain calculations.
    """
    CRITICAL_REVERSAL_RISK = "CRITICAL_REVERSAL_RISK"
    HIGH_SENSITIVITY_GAP = "HIGH_SENSITIVITY_GAP"
    MODERATE_UNCERTAINTY = "MODERATE_UNCERTAINTY"
    LOW_IMPACT_OR_VALIDATED = "LOW_IMPACT_OR_VALIDATED"


VALIDATION_PLANNING_POLICY_V1 = "VALIDATION_PLANNING_POLICY_V1"
CURRENT_VALIDATION_PLANNING_POLICY_VERSION = VALIDATION_PLANNING_POLICY_V1

GOVERNANCE_VALIDATION_SEPARATION_NOTICE = (
    "GOVERNANCE & SAFETY SEPARATION: Validation plan approval, evidence acceptance, and evidence gap closure "
    "do not constitute engineering decision approval, vehicle commissioning, or deployment safety authorization. "
    "Those actions strictly require independent role-based governance gates."
)

FINITE_SAMPLE_SCOPE_NOTICE = (
    "FINITE SAMPLE LIMITATION: Physical rig, bench, and track test observations provide finite empirical evidence "
    "under specific operating conditions. They narrow localized parameter uncertainty intervals but do NOT certify "
    "the full infinite operational envelope."
)


class ValidationPlanStatus(str, enum.Enum):
    """
    Lifecycle status of an Engineering Validation Plan (Phase 6.6).
    Distinguishes plan proposal, authorization, execution, review, and final disposition.
    """
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    AUTHORIZED = "AUTHORIZED"
    IN_PROGRESS = "IN_PROGRESS"
    EVIDENCE_SUBMITTED = "EVIDENCE_SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    SUPERSEDED = "SUPERSEDED"


class ValidationMethodType(str, enum.Enum):
    """
    Standardized engineering validation methods (Phase 6.6).
    """
    RIG_TEST_4_POST = "RIG_TEST_4_POST"
    SHOCK_DYNO_CHARACTERIZATION = "SHOCK_DYNO_CHARACTERIZATION"
    TRACK_K_AND_C_RIG_TEST = "TRACK_K&C_RIG_TEST"
    COMPONENT_BENCH_TEST = "COMPONENT_BENCH_TEST"
    CALIBRATED_TELEMETRY_SESSION = "CALIBRATED_TELEMETRY_SESSION"
    VERIFIED_PHYSICAL_SIMULATION = "VERIFIED_PHYSICAL_SIMULATION"
    SUPPLIER_CERTIFICATE_AUDIT = "SUPPLIER_CERTIFICATE_AUDIT"


class CriterionStatus(str, enum.Enum):
    """
    Status of an acceptance criterion within a validation plan (Phase 6.6).
    """
    PROPOSED = "PROPOSED"
    ESTABLISHED = "ESTABLISHED"
    AUTHORIZED = "AUTHORIZED"
    UNRESOLVED = "UNRESOLVED"


class EvidenceDataSourceType(str, enum.Enum):
    """
    Authoritative evidence source type for validation data (Phase 6.6).
    """
    PHYSICAL_RIG_MEASUREMENT = "PHYSICAL_RIG_MEASUREMENT"
    CALIBRATED_INSTRUMENT = "CALIBRATED_INSTRUMENT"
    VEHICLE_TELEMETRY_DATASET = "VEHICLE_TELEMETRY_DATASET"
    NUMERICAL_SIMULATION_RESULT = "NUMERICAL_SIMULATION_RESULT"
    SUPPLIER_TEST_CERTIFICATE = "SUPPLIER_TEST_CERTIFICATE"


class EvidenceClosureVerdict(str, enum.Enum):
    """
    Evidence gap closure evaluation verdict (Phase 6.6).
    """
    CLOSED_WITH_SUPPORTING_EVIDENCE = "CLOSED_WITH_SUPPORTING_EVIDENCE"
    REMAINS_OPEN = "REMAINS_OPEN"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    EVIDENCE_CONFLICTED = "EVIDENCE_CONFLICTED"
    EVIDENCE_NOT_APPLICABLE = "EVIDENCE_NOT_APPLICABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ReversalResolutionStatus(str, enum.Enum):
    """
    Status of demonstrated decision reversals following evidence ingestion and reassessment (Phase 6.6).
    """
    REVERSAL_RESOLVED = "REVERSAL_RESOLVED"
    REVERSAL_PERSISTS = "REVERSAL_PERSISTS"
    NEW_REVERSAL_INTRODUCED = "NEW_REVERSAL_INTRODUCED"
    NO_REVERSAL_DEMONSTRATED = "NO_REVERSAL_DEMONSTRATED"


VALIDATION_GATE_PROVENANCE = "THRESHOLD_PROVENANCE_UNRESOLVED"

# Sensitivity Threshold Provenance Classification (Phase 6.3 Hardening):
# Elasticity cutoffs (|elasticity| >= 0.20 for high, 0.05 <= |elasticity| < 0.20 for moderate, < 0.05 for low)
# are provisional analytical screening bins, NOT scientifically validated universal safety thresholds.
SENSITIVITY_THRESHOLDS_PROVENANCE = "PROVISIONAL"
SENSITIVITY_THRESHOLDS_METADATA = {
    "provenance": SENSITIVITY_THRESHOLDS_PROVENANCE,
    "high_threshold": 0.20,
    "moderate_threshold": 0.05,
    "classification_nature": "provisional_analytical_screening_heuristic",
    "scientific_basis": "Empirical vehicle dynamics screening heuristic; not a formal physical safety boundary or deployment certificate.",
}


class FleetComparabilityStatus(str, enum.Enum):
    """
    Comparability classifications under FLEET_TRUST_POLICY_V1.
    """
    COMPARABLE = "COMPARABLE"
    PARTIALLY_COMPARABLE = "PARTIALLY_COMPARABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class SensitivityStatus(str, enum.Enum):
    """
    Sensitivity evidence availability under SENSITIVITY_PROPAGATION_POLICY_V1.
    Strictly distinguishes available sensitivity from missing evidence and scope mismatches.
    Never represents missing sensitivity as zero.
    """
    AVAILABLE = "AVAILABLE"
    SENSITIVITY_UNAVAILABLE = "SENSITIVITY_UNAVAILABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"


class ImpactClassification(str, enum.Enum):
    """
    Downstream impact classifications under SENSITIVITY_PROPAGATION_POLICY_V1.
    Explicit qualitative categories based on documented boundaries; zero arbitrary weighted scores.
    """
    CRITICAL_VALIDATED = "CRITICAL_VALIDATED"
    HIGH_IMPACT_EVIDENCE_GAP = "HIGH_IMPACT_EVIDENCE_GAP"
    MODERATE_IMPACT_EVIDENCE_GAP = "MODERATE_IMPACT_EVIDENCE_GAP"
    LOW_IMPACT_EVIDENCE_GAP = "LOW_IMPACT_EVIDENCE_GAP"
    VALIDATED_LOW_IMPACT = "VALIDATED_LOW_IMPACT"
    CONFLICTED_IMPACT = "CONFLICTED_IMPACT"
    UNASSESSED_IMPACT = "UNASSESSED_IMPACT"
    SENSITIVITY_UNAVAILABLE = "SENSITIVITY_UNAVAILABLE"


class FleetOutlierClassification(str, enum.Enum):
    """
    Fleet outlier classifications under FLEET_TRUST_POLICY_V1.
    Distinguishes normal variance from statistical outliers and engineering conflicts.
    """
    NORMAL_VARIANCE = "NORMAL_VARIANCE"
    STATISTICAL_OUTLIER = "STATISTICAL_OUTLIER"
    VALUE_CONFLICT = "VALUE_CONFLICT"
    INSUFFICIENT_COHORT_SIZE = "INSUFFICIENT_COHORT_SIZE"


class RecencyCondition(str, enum.Enum):
    """
    Canonical recency classifications under TRUST_RECENCY_POLICY_V1.
    Strictly distinguishes evidence age from validity expiration and physical degradation.
    """
    VALID = "VALID"
    REASSESSMENT_RECOMMENDED = "REASSESSMENT_RECOMMENDED"
    VALIDITY_EXPIRED = "VALIDITY_EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    INSUFFICIENT_RECENCY_INFORMATION = "INSUFFICIENT_RECENCY_INFORMATION"


class TrustConflictType(str, enum.Enum):
    """
    Structured conflict classifications for Parameter Trust (Phase 6.2).
    """
    VALUE_DIVERGENCE = "VALUE_DIVERGENCE"
    CONTRADICTORY_VALIDATION = "CONTRADICTORY_VALIDATION"
    SOURCE_VERSION_CONFLICT = "SOURCE_VERSION_CONFLICT"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    INCOMPATIBLE_UNITS = "INCOMPATIBLE_UNITS"
    MISSING_SOURCE_PROVENANCE = "MISSING_SOURCE_PROVENANCE"


class TrustState(str, enum.Enum):
    """
    Constrained canonical vocabulary for Parameter Trust States (Phase 6.1).
    Every state is explainable from auditable evidence.
    """
    UNASSESSED = "UNASSESSED"
    SUPPORTED = "SUPPORTED"
    VALIDATED = "VALIDATED"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    PROVISIONAL = "PROVISIONAL"
    CONFLICTED = "CONFLICTED"
    STALE = "STALE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED = "REJECTED"


class ValidationCoverage(str, enum.Enum):
    """
    Authoritative physical/out-of-sample validation coverage classification.
    Simulation existence != physical validation.
    """
    NO_VALIDATION = "NO_VALIDATION"
    PARTIAL_VALIDATION = "PARTIAL_VALIDATION"
    VALIDATED = "VALIDATED"
    CONFLICTING_VALIDATION = "CONFLICTING_VALIDATION"


class ProvenanceClass(str, enum.Enum):
    """
    Canonical source classification for an engineering parameter.
    Must reflect proven source metadata, not textual assumptions.
    """
    MEASURED = "measured"
    CALIBRATED = "calibrated"
    SIMULATION_DERIVED = "simulation-derived"
    MANUALLY_ENTERED = "manually_entered"
    IMPORTED = "imported"
    LITERATURE_REFERENCE = "literature_reference"
    HISTORICAL_SETUP = "historical_setup"
    OPTIMIZATION = "optimization"
    INFERRED = "inferred"


class ParameterTrustProfile(Base):
    """
    Authoritative Parameter Trust Profile.
    Represents the active trust posture of a single parameter identity within a defined scope.
    """
    __tablename__ = "parameter_trust_profiles"
    __table_args__ = (
        Index("ix_param_trust_team_lookup", "team_id", "entity_type", "entity_id", "parameter_name"),
        Index("ix_param_trust_user_lookup", "created_by_user_id", "entity_type", "entity_id", "parameter_name"),
        Index("ix_param_trust_org", "organization_id"),
        Index("ix_param_trust_hash", "assessment_hash"),
        Index("ix_param_trust_state", "current_trust_state"),
        UniqueConstraint(
            "team_id",
            "entity_type",
            "entity_id",
            "parameter_name",
            "policy_version",
            name="uq_param_trust_team_scope",
        ),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    # ── Parameter Identity ────────────────────────────────────────────────────
    entity_type = Column(String(64), nullable=False)        # e.g. "SetupCandidate", "VehicleProfile"
    entity_id = Column(String(128), nullable=False)          # e.g. "SETUP-P3L-CAND-01"
    parameter_name = Column(String(128), nullable=False)     # e.g. "front_spring_rate", "k_s"
    parameter_path = Column(String(256), nullable=False)     # e.g. "changed_parameters.k_s.candidate"
    unit = Column(String(32), nullable=False, default="")    # e.g. "N/m"

    # ── Value Reference (Not duplicate store) ──────────────────────────────────
    # { "value": 85000.0, "value_identity": "...", "source_entity": "SetupCandidate:SETUP-P3L-CAND-01" }
    value_reference = Column(JSON_TYPE, nullable=False)

    # ── Provenance & Scope ────────────────────────────────────────────────────
    provenance_class = Column(String(64), nullable=False)   # ProvenanceClass value
    provenance_details = Column(JSON_TYPE, nullable=False, default=dict)
    # { "vehicle_id": "...", "setup_id": "...", "operating_regime": "...", "valid_from": "...", "valid_to": "..." }
    scope = Column(JSON_TYPE, nullable=False, default=dict)

    # ── Trust Posture ─────────────────────────────────────────────────────────
    current_trust_state = Column(String(32), nullable=False, default=TrustState.UNASSESSED.value)
    validation_coverage = Column(String(32), nullable=False, default=ValidationCoverage.NO_VALIDATION.value)
    policy_version = Column(String(32), nullable=False, default=CURRENT_TRUST_POLICY_VERSION)
    assessment_hash = Column(String(64), nullable=False)

    # ── Deterministic Explanation & Findings ──────────────────────────────────
    explanation = Column(JSON_TYPE, nullable=False, default=dict)
    conflicts = Column(JSON_TYPE, nullable=False, default=list)
    recency_metadata = Column(JSON_TYPE, nullable=False, default=dict)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class ParameterTrustEvidenceRecord(Base):
    """
    Normalized supporting evidence pointer linking a ParameterTrustProfile
    to an authoritative engineering entity.
    """
    __tablename__ = "parameter_trust_evidence"
    __table_args__ = (
        Index("ix_param_ev_profile", "profile_id"),
        Index("ix_param_ev_target", "evidence_type", "evidence_id"),
        Index("ix_param_ev_team", "team_id"),
        Index("ix_param_ev_hash", "artifact_hash"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    profile_id = Column(UUID_TYPE, ForeignKey("parameter_trust_profiles.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID_TYPE, nullable=True)
    team_id = Column(UUID_TYPE, nullable=True)

    evidence_type = Column(String(64), nullable=False)       # e.g. "BlindValidation", "SimulationRun"
    evidence_id = Column(String(128), nullable=False)
    artifact_hash = Column(String(64), nullable=False)
    relationship = Column(String(64), nullable=False)        # Canonical relationship from EvidenceGraph
    evidence_timestamp = Column(DateTime(timezone=True), nullable=True)
    metadata_ = Column("metadata", JSON_TYPE, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ParameterTrustAssessmentRecord(Base):
    """
    Append-only historical trust assessment log.
    Guarantees reproducibility and auditability over time.
    """
    __tablename__ = "parameter_trust_assessments"
    __table_args__ = (
        Index("ix_param_assess_profile_ts", "profile_id", "created_at"),
        Index("ix_param_assess_team", "team_id"),
        Index("ix_param_assess_hash", "assessment_hash"),
        Index("ix_param_assess_user", "user_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    profile_id = Column(UUID_TYPE, ForeignKey("parameter_trust_profiles.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID_TYPE, nullable=True)
    team_id = Column(UUID_TYPE, nullable=True)
    user_id = Column(UUID_TYPE, nullable=False)

    trust_state = Column(String(32), nullable=False)
    validation_coverage = Column(String(32), nullable=False)
    policy_version = Column(String(32), nullable=False)
    assessment_hash = Column(String(64), nullable=False)
    value_identity = Column(String(128), nullable=False)

    supporting_evidence_hashes = Column(JSON_TYPE, nullable=False, default=list)
    explanation = Column(JSON_TYPE, nullable=False, default=dict)
    conflicts = Column(JSON_TYPE, nullable=False, default=list)
    recency_metadata = Column(JSON_TYPE, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ParameterTrustFleetReport(Base):
    """
    Authoritative Fleet Parameter Trust Comparison Report (Phase 6.3).
    Captures multi-vehicle parameter synchronization, comparability states,
    cohort statistics, and outlier classifications under FLEET_TRUST_POLICY_V1.
    Strict Invariant: Fleet aggregation NEVER overwrites local source parameters or profiles.
    """
    __tablename__ = "parameter_trust_fleet_reports"
    __table_args__ = (
        Index("ix_fleet_report_fleet_lookup", "team_id", "fleet_id", "parameter_name"),
        Index("ix_fleet_report_user_lookup", "user_id", "fleet_id", "parameter_name"),
        Index("ix_fleet_report_hash", "report_hash"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    fleet_id = Column(String(128), nullable=False)
    parameter_name = Column(String(128), nullable=False)
    canonical_unit = Column(String(32), nullable=False, default="")

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    policy_version = Column(String(32), nullable=False, default=FLEET_TRUST_POLICY_V1)
    report_hash = Column(String(64), nullable=False)

    cohort_size = Column(Integer, nullable=False, default=0)
    comparable_count = Column(Integer, nullable=False, default=0)
    excluded_count = Column(Integer, nullable=False, default=0)
    missing_count = Column(Integer, nullable=False, default=0)

    summary_metrics = Column(JSON_TYPE, nullable=False, default=dict)
    comparable_instances = Column(JSON_TYPE, nullable=False, default=list)
    excluded_instances = Column(JSON_TYPE, nullable=False, default=list)
    missing_instances = Column(JSON_TYPE, nullable=False, default=list)
    conflicts = Column(JSON_TYPE, nullable=False, default=list)
    outliers = Column(JSON_TYPE, nullable=False, default=list)

    validation_coverage_breakdown = Column(JSON_TYPE, nullable=False, default=dict)
    trust_state_breakdown = Column(JSON_TYPE, nullable=False, default=dict)
    provenance_distribution = Column(JSON_TYPE, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ParameterTrustAssemblyImpactRecord(Base):
    """
    Assembly-Aware Parameter Trust & Sensitivity Impact Record (Phase 6.3).
    Maps component parameters through assembly hierarchies and couples them with
    authoritative sensitivity evidence to establish downstream engineering impacts.
    Strict Invariant: Direct parameter trust is decoupled from propagated assembly impact.
    """
    __tablename__ = "parameter_trust_assembly_impacts"
    __table_args__ = (
        Index("ix_assembly_impact_veh_lookup", "team_id", "vehicle_id", "assembly_name", "parameter_name"),
        Index("ix_assembly_impact_user_lookup", "user_id", "vehicle_id", "assembly_name", "parameter_name"),
        Index("ix_assembly_impact_hash", "impact_hash"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(String(128), nullable=False)
    assembly_name = Column(String(64), nullable=False)
    component_name = Column(String(64), nullable=False)
    parameter_name = Column(String(128), nullable=False)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    policy_version = Column(String(32), nullable=False, default=SENSITIVITY_PROPAGATION_POLICY_V1)
    impact_hash = Column(String(64), nullable=False)

    direct_trust_state = Column(String(32), nullable=False)
    validation_coverage = Column(String(32), nullable=False)

    sensitivity_status = Column(String(32), nullable=False)
    sensitivity_source = Column(String(128), nullable=True)
    sensitivity_unit = Column(String(64), nullable=True)
    sensitivity_magnitude = Column(JSON_TYPE, nullable=True)

    impact_classification = Column(String(64), nullable=False)
    downstream_metrics = Column(JSON_TYPE, nullable=False, default=list)
    dependency_path = Column(JSON_TYPE, nullable=False, default=list)
    evidence_gaps = Column(JSON_TYPE, nullable=False, default=list)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class DecisionParameterDependencyRecord(Base):
    """
    Formal Decision-Parameter Dependency Association (Phase 6.4).
    Traceably links an engineering decision or investigation to an affected parameter.
    Captures dependency nature (direct, quantitative, qualitative, unresolved),
    affected KPIs, sensitivity status, and source evidence hashes.
    """
    __tablename__ = "decision_parameter_dependencies"
    __table_args__ = (
        Index("ix_dec_param_dep_lookup", "team_id", "decision_id", "parameter_name"),
        Index("ix_dec_param_dep_user", "user_id", "decision_id"),
        Index("ix_dec_param_dep_nature", "dependency_nature"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    decision_id = Column(String(64), nullable=False)
    decision_type = Column(String(64), nullable=False, default="EngineeringDecision")
    parameter_name = Column(String(128), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(128), nullable=False)

    dependency_nature = Column(String(64), nullable=False)  # DependencyNature value
    kpi_metrics = Column(JSON_TYPE, nullable=False, default=list)
    sensitivity_status = Column(String(32), nullable=False)

    elasticity = Column(Float, nullable=True)  # Strictly None if qualitative!
    numerical_derivative = Column(Float, nullable=True)
    derivative_unit = Column(String(64), nullable=True)

    source_artifact_hashes = Column(JSON_TYPE, nullable=False, default=list)
    source_evidence_ids = Column(JSON_TYPE, nullable=False, default=list)
    operating_conditions = Column(JSON_TYPE, nullable=False, default=dict)
    model_version = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class DecisionExposureAssessmentRecord(Base):
    """
    Deterministic Decision Exposure Assessment Record (Phase 6.4).
    Captures versioned assessment of decision exposure to parameter uncertainty,
    reproducible input snapshot hash, prioritized actionable evidence gaps,
    and recommended candidate validation activities.
    Strict Invariant: Decision exposure is decoupled from human approval and deployment safety.
    """
    __tablename__ = "decision_exposure_assessments"
    __table_args__ = (
        Index("ix_dec_exposure_lookup", "team_id", "decision_id", "created_at"),
        Index("ix_dec_exposure_user", "user_id", "decision_id"),
        Index("ix_dec_exposure_hash", "assessment_hash"),
        Index("ix_dec_exposure_active", "decision_id", "is_active"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    decision_id = Column(String(64), nullable=False)
    decision_type = Column(String(64), nullable=False, default="EngineeringDecision")

    policy_version = Column(String(32), nullable=False, default=DECISION_TRUST_POLICY_V1)
    assessment_hash = Column(String(64), nullable=False)
    input_snapshot_hash = Column(String(64), nullable=False)

    exposure_classification = Column(String(64), nullable=False)  # DecisionExposureClassification value
    exposure_summary = Column(Text, nullable=False)

    parameter_dependencies = Column(JSON_TYPE, nullable=False, default=list)
    evidence_gaps = Column(JSON_TYPE, nullable=False, default=list)
    actionable_recommendations = Column(JSON_TYPE, nullable=False, default=list)
    governance_separation_notice = Column(Text, nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)
    superseded_by = Column(UUID_TYPE, nullable=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class DecisionRobustnessAnalysisRecord(Base):
    """
    Deterministic Decision Robustness Analysis Record (Phase 6.5).
    Persists immutable robustness evaluation of an engineering decision under parameter uncertainty,
    including evaluated envelope, demonstrated reversals, boundary crossings, dominant uncertainties,
    value-of-information prioritizations, and solver failure captures.
    """
    __tablename__ = "decision_robustness_analyses"
    __table_args__ = (
        Index("ix_dec_robustness_lookup", "team_id", "decision_id", "created_at"),
        Index("ix_dec_robustness_user", "user_id", "decision_id"),
        Index("ix_dec_robustness_hash", "analysis_hash"),
        Index("ix_dec_robustness_active", "decision_id", "is_active"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    decision_id = Column(String(64), nullable=False)
    decision_type = Column(String(64), nullable=False, default="EngineeringDecision")

    policy_version = Column(String(32), nullable=False, default=ROBUSTNESS_POLICY_V1)
    analysis_hash = Column(String(64), nullable=False)
    input_snapshot_hash = Column(String(64), nullable=False)

    robustness_classification = Column(String(64), nullable=False)  # DecisionRobustnessClassification value
    robustness_summary = Column(Text, nullable=False)

    evaluated_envelope = Column(JSON_TYPE, nullable=False, default=dict)
    parameter_uncertainties = Column(JSON_TYPE, nullable=False, default=list)
    reversal_scenarios = Column(JSON_TYPE, nullable=False, default=list)
    boundary_crossings = Column(JSON_TYPE, nullable=False, default=list)
    dominant_uncertainties = Column(JSON_TYPE, nullable=False, default=list)
    voi_prioritizations = Column(JSON_TYPE, nullable=False, default=list)
    solver_failures = Column(JSON_TYPE, nullable=False, default=list)
    governance_separation_notice = Column(Text, nullable=False, default=GOVERNANCE_ROBUSTNESS_SEPARATION_NOTICE)

    is_active = Column(Boolean, nullable=False, default=True)
    superseded_by = Column(UUID_TYPE, nullable=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class EngineeringValidationPlanRecord(Base):
    """
    Engineering Validation Plan Record (Phase 6.6).
    Versioned, tenant-scoped validation contract specifying target parameters, evidence gaps,
    validation objectives, required artifacts, operating scopes, and authorized acceptance criteria.
    Acceptance criteria become immutable once AUTHORIZED.
    """
    __tablename__ = "engineering_validation_plans"
    __table_args__ = (
        Index("ix_val_plans_decision_id", "decision_id"),
        Index("ix_val_plans_parameter_name", "parameter_name"),
        Index("ix_val_plans_status", "status"),
        Index("ix_val_plans_tenant", "organization_id", "team_id"),
        Index("ix_val_plans_active", "is_active"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    plan_id = Column(String(128), nullable=False)  # Human-readable code e.g. "VAL-PLAN-..."
    decision_id = Column(String(128), nullable=False)
    decision_type = Column(String(64), nullable=False, default="EngineeringDecision")

    parameter_name = Column(String(128), nullable=False)
    parameter_path = Column(String(256), nullable=True)
    evidence_gap_id = Column(String(128), nullable=True)

    validation_objective = Column(Text, nullable=False)
    validation_method = Column(String(64), nullable=False)  # ValidationMethodType value
    status = Column(String(32), nullable=False, default=ValidationPlanStatus.DRAFT.value)

    plan_version = Column(Integer, nullable=False, default=1)
    parent_plan_id = Column(UUID_TYPE, ForeignKey("engineering_validation_plans.id", ondelete="SET NULL"), nullable=True, index=True)

    exposure_assessment_id = Column(UUID_TYPE, ForeignKey("decision_exposure_assessments.id", ondelete="SET NULL"), nullable=True, index=True)
    robustness_analysis_id = Column(UUID_TYPE, ForeignKey("decision_robustness_analyses.id", ondelete="SET NULL"), nullable=True, index=True)
    analysis_snapshot_hash = Column(String(64), nullable=True)

    input_artifact_requirements = Column(JSON_TYPE, nullable=False, default=list)
    operating_conditions = Column(JSON_TYPE, nullable=False, default=dict)
    applicability_envelope = Column(JSON_TYPE, nullable=False, default=dict)
    unit = Column(String(32), nullable=False)
    measurement_definition = Column(Text, nullable=False)

    acceptance_criteria = Column(JSON_TYPE, nullable=False, default=list)
    criteria_established_at = Column(DateTime(timezone=True), nullable=True)
    criteria_authorized_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    expected_outputs = Column(JSON_TYPE, nullable=False, default=list)
    required_reviewer_role = Column(String(64), nullable=False, default="VALIDATION_LEAD")

    authorized_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    authorized_at = Column(DateTime(timezone=True), nullable=True)

    plan_hash = Column(String(64), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class ValidationEvidenceItemRecord(Base):
    """
    Validation Evidence Item Record (Phase 6.6).
    Represents actual ingested evidence (rig test, telemetry, calibrated bench measurement).
    Tracks source identity, timestamps, operating scope, unit, and cryptographic integrity hash.
    Requires reviewer verification before acceptance.
    """
    __tablename__ = "validation_evidence_items"
    __table_args__ = (
        Index("ix_val_evidence_plan_id", "plan_id"),
        Index("ix_val_evidence_param", "parameter_name"),
        Index("ix_val_evidence_review_status", "review_status"),
        Index("ix_val_evidence_tenant", "organization_id", "team_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID_TYPE, ForeignKey("engineering_validation_plans.id", ondelete="CASCADE"), nullable=False)

    evidence_source_type = Column(String(64), nullable=False)  # EvidenceDataSourceType
    source_identifier = Column(String(256), nullable=False)
    source_timestamp = Column(DateTime(timezone=True), nullable=False)

    parameter_name = Column(String(128), nullable=False)
    observed_value = Column(Float, nullable=True)
    observed_interval = Column(JSON_TYPE, nullable=True)
    observed_samples = Column(JSON_TYPE, nullable=True)

    unit = Column(String(32), nullable=False)
    operating_scope = Column(JSON_TYPE, nullable=False, default=dict)
    integrity_hash = Column(String(64), nullable=False)

    provenance = Column(JSON_TYPE, nullable=False, default=dict)
    calibration_metadata = Column(JSON_TYPE, nullable=False, default=dict)

    is_physically_validated = Column(Boolean, nullable=False, default=False)
    physical_limitations = Column(Text, nullable=True)

    review_status = Column(String(32), nullable=False, default="PENDING_REVIEW")  # PENDING_REVIEW, ACCEPTED, REJECTED, INCONCLUSIVE
    review_notes = Column(Text, nullable=True)
    reviewed_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # ── Phase 6.7 Source Verification & Integrity Tracking ───────────────────
    integrity_stage = Column(String(64), nullable=False, default="SOURCE_CLAIMED")
    source_verification_status = Column(String(32), nullable=False, default="UNVERIFIED")
    source_verification_id = Column(UUID_TYPE, ForeignKey("source_verification_records.id", ondelete="SET NULL", use_alter=True), nullable=True, index=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    submitted_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    @property
    def raw_artifact_hash(self) -> str:
        return self.integrity_hash


class ValidationEvidenceClosureRecord(Base):
    """
    Validation Evidence Closure Record (Phase 6.6).
    Evaluates whether submitted evidence legitimately closes the target evidence gap.
    Checks test execution, parameter matching, operating scope compatibility,
    unit alignment, criteria satisfaction, and conflict status.
    """
    __tablename__ = "validation_evidence_closures"
    __table_args__ = (
        Index("ix_val_closure_plan_id", "plan_id"),
        Index("ix_val_closure_decision_id", "decision_id"),
        Index("ix_val_closure_verdict", "closure_verdict"),
        Index("ix_val_closure_active", "is_active"),
        Index("ix_val_closure_tenant", "organization_id", "team_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID_TYPE, ForeignKey("engineering_validation_plans.id", ondelete="CASCADE"), nullable=False)
    decision_id = Column(String(128), nullable=False)
    parameter_name = Column(String(128), nullable=False)
    evidence_gap_id = Column(String(128), nullable=True)

    closure_verdict = Column(String(64), nullable=False)  # EvidenceClosureVerdict value
    criteria_met = Column(Boolean, nullable=False, default=False)
    criteria_evaluated = Column(JSON_TYPE, nullable=False, default=list)

    applicability_check = Column(JSON_TYPE, nullable=False, default=dict)
    conflict_assessment = Column(JSON_TYPE, nullable=False, default=dict)
    uncertainty_update = Column(JSON_TYPE, nullable=False, default=dict)

    requires_robustness_reassessment = Column(Boolean, nullable=False, default=False)
    closure_summary = Column(Text, nullable=False)
    closure_hash = Column(String(64), nullable=False)

    governance_separation_notice = Column(Text, nullable=False, default=GOVERNANCE_VALIDATION_SEPARATION_NOTICE)
    finite_sample_notice = Column(Text, nullable=False, default=FINITE_SAMPLE_SCOPE_NOTICE)
    deployment_safety_inferred = Column(Boolean, nullable=False, default=False)
    deployment_authorization = Column(String(32), nullable=False, default="NOT_ESTABLISHED")

    is_active = Column(Boolean, nullable=False, default=True)
    superseded_by = Column(UUID_TYPE, ForeignKey("validation_evidence_closures.id", ondelete="SET NULL"), nullable=True, index=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    evaluated_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ValidationDecisionReassessmentRecord(Base):
    """
    Validation Decision Reassessment Record (Phase 6.6).
    Links original Phase 6.4/6.5 assessments to new Phase 6.5 robustness analysis
    computed with updated evidence-backed parameter uncertainties.
    Quantifies before/after deltas: uncertainty intervals, reversal resolutions, and boundary margins.
    """
    __tablename__ = "validation_decision_reassessments"
    __table_args__ = (
        Index("ix_val_reassess_decision_id", "decision_id"),
        Index("ix_val_reassess_plan_id", "plan_id"),
        Index("ix_val_reassess_closure_id", "closure_id"),
        Index("ix_val_reassess_active", "is_active"),
        Index("ix_val_reassess_tenant", "organization_id", "team_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    decision_id = Column(String(128), nullable=False)
    decision_type = Column(String(64), nullable=False, default="EngineeringDecision")

    plan_id = Column(UUID_TYPE, ForeignKey("engineering_validation_plans.id", ondelete="CASCADE"), nullable=False)
    closure_id = Column(UUID_TYPE, ForeignKey("validation_evidence_closures.id", ondelete="CASCADE"), nullable=False)

    original_exposure_assessment_id = Column(UUID_TYPE, ForeignKey("decision_exposure_assessments.id", ondelete="SET NULL"), nullable=True, index=True)
    original_robustness_analysis_id = Column(UUID_TYPE, ForeignKey("decision_robustness_analyses.id", ondelete="SET NULL"), nullable=True, index=True)
    new_robustness_analysis_id = Column(UUID_TYPE, ForeignKey("decision_robustness_analyses.id", ondelete="SET NULL"), nullable=True, index=True)

    reassessment_delta = Column(JSON_TYPE, nullable=False, default=dict)
    reversal_status = Column(String(64), nullable=False)  # ReversalResolutionStatus value
    envelope_coverage_statement = Column(Text, nullable=False)

    governance_separation_notice = Column(Text, nullable=False, default=GOVERNANCE_VALIDATION_SEPARATION_NOTICE)
    deployment_safety_inferred = Column(Boolean, nullable=False, default=False)
    deployment_authorization = Column(String(32), nullable=False, default="NOT_ESTABLISHED")

    reassessment_hash = Column(String(64), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    superseded_by = Column(UUID_TYPE, ForeignKey("validation_decision_reassessments.id", ondelete="SET NULL"), nullable=True, index=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    reassessed_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6.7: VALIDATION EVIDENCE INTEGRITY & DECISION DOSSIER GOVERNANCE
# ═══════════════════════════════════════════════════════════════════════════════

class SourceVerificationMethod(str, enum.Enum):
    """
    Authoritative verification methods for evidence source authenticity (Phase 6.7).
    """
    TRUSTED_REGISTRY_CHECK = "TRUSTED_REGISTRY_CHECK"
    AUTHENTICATED_SUPPLIER_ATTESTATION = "AUTHENTICATED_SUPPLIER_ATTESTATION"
    AUTHORIZED_CUSTODIAN_REVIEW = "AUTHORIZED_CUSTODIAN_REVIEW"
    CRYPTOGRAPHIC_SIGNATURE = "CRYPTOGRAPHIC_SIGNATURE"


class SourceVerificationStatus(str, enum.Enum):
    """
    Authenticity status of an evidence item source identity (Phase 6.7).
    """
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class EvidenceIntegrityStage(str, enum.Enum):
    """
    Sequential integrity maturation stages for evidence closure (Phase 6.7).
    """
    SOURCE_CLAIMED = "SOURCE_CLAIMED"
    PROVENANCE_DOCUMENTED = "PROVENANCE_DOCUMENTED"
    SOURCE_IDENTITY_VERIFIED = "SOURCE_IDENTITY_VERIFIED"
    MEASUREMENT_QUALITY_ASSESSED = "MEASUREMENT_QUALITY_ASSESSED"
    CRITERIA_EVALUATED = "CRITERIA_EVALUATED"
    EVIDENCE_ACCEPTED = "EVIDENCE_ACCEPTED"


class DossierGovernanceState(str, enum.Enum):
    """
    Role-controlled engineering decision dossier review states (Phase 6.7).
    """
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    EVIDENCE_ACCEPTED = "EVIDENCE_ACCEPTED"
    CONCLUSION_REVIEWED = "CONCLUSION_REVIEWED"
    DECISION_APPROVED = "DECISION_APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ReviewActionType(str, enum.Enum):
    """
    Formally controlled review actions executed by authorized engineers (Phase 6.7).
    """
    ADMIT_EVIDENCE = "ADMIT_EVIDENCE"
    EVALUATE_CRITERIA = "EVALUATE_CRITERIA"
    CLOSE_GAP = "CLOSE_GAP"
    REVIEW_CONCLUSION = "REVIEW_CONCLUSION"
    APPROVE_DECISION = "APPROVE_DECISION"
    REJECT = "REJECT"
    SUPERSEDE = "SUPERSEDE"


GOVERNANCE_SEPARATION_NOTICE_V2 = (
    "GOVERNANCE & SAFETY SEPARATION: Engineering decision closure and evidence dossier approval "
    "establish verification and criteria satisfaction only. Deployment authorization, functional safety "
    "certification (ISO 26262), and operational release require separate statutory authorization and "
    "are NEVER established or inferred by evidence closure or parameter trust reassessments. "
    "STRICT NON-ELEVATION POLICY ENFORCED."
)

UNVERIFIED_SOURCE_NOTICE = (
    "UNVERIFIED EVIDENCE WARNING: The source identity of this evidence item has not been "
    "independently verified. Claimed provenance is not proof of authenticity. Acceptance or "
    "review does not establish source truthfulness."
)

EVIDENCE_INTEGRITY_POLICY_V1 = "PHASE_6_7_EVIDENCE_INTEGRITY_POLICY_V1"
CURRENT_EVIDENCE_INTEGRITY_POLICY_VERSION = "1.0.0"


class TrustedSourceRegistryRecord(Base):
    """
    Trusted Source Registry Record (Phase 6.7).
    Maintains an authoritative registry of known, certified evidence sources
    (e.g., specific calibrated rigs, certified test benches, supplier labs).
    """
    __tablename__ = "trusted_source_registries"
    __table_args__ = (
        Index("ix_trusted_source_identifier", "source_identifier"),
        Index("ix_trusted_source_tenant", "organization_id", "team_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    source_identifier = Column(String(256), nullable=False, unique=True)
    source_name = Column(String(128), nullable=False)
    source_type = Column(String(64), nullable=False)  # e.g. "AUTHORITATIVE_LAB_FACILITY"

    is_authorized = Column(Boolean, nullable=False, default=True)
    certificate_ref = Column(String(256), nullable=True)
    public_key_pem = Column(Text, nullable=True)

    valid_from = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    valid_until = Column(DateTime(timezone=True), nullable=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class SourceVerificationRecord(Base):
    """
    Source Verification Record (Phase 6.7).
    Documents the explicit verification of an evidence item's source authenticity.
    """
    __tablename__ = "source_verification_records"
    __table_args__ = (
        Index("ix_src_verif_evidence_id", "evidence_item_id"),
        Index("ix_src_verif_status", "verification_status"),
        Index("ix_src_verif_tenant", "organization_id", "team_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    evidence_item_id = Column(UUID_TYPE, ForeignKey("validation_evidence_items.id", ondelete="CASCADE"), nullable=False)

    verification_method = Column(String(64), nullable=False)  # SourceVerificationMethod value
    verification_status = Column(String(32), nullable=False, default="UNVERIFIED")
    verifier_identity = Column(String(256), nullable=False)
    verifier_role = Column(String(64), nullable=False)
    verifier_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    verification_timestamp = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    artifact_hash = Column(String(64), nullable=False)
    supporting_references = Column(JSON_TYPE, nullable=False, default=dict)
    scope = Column(JSON_TYPE, nullable=False, default=dict)
    verification_notes = Column(Text, nullable=True)
    verification_hash = Column(String(64), nullable=False)

    is_revoked = Column(Boolean, nullable=False, default=False)
    revocation_reason = Column(Text, nullable=True)
    revoked_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class EngineeringDecisionDossierRecord(Base):
    """
    Engineering Decision Dossier Record (Phase 6.7).
    A comprehensive, versioned, immutable engineering decision dossier linking:
    - Engineering question / decision
    - Parameter trust profiles & decision exposure assessment
    - Baseline robustness & uncertainty envelope
    - Sealed validation plan & immutable acceptance criteria
    - Evidence items & formal source verification records
    - Evidence closure verdicts & reassessed robustness delta
    - Contradictory evidence & unresolved assumptions
    - Review audit trail & historical supersession lineage
    """
    __tablename__ = "engineering_decision_dossiers"
    __table_args__ = (
        Index("ix_dossier_decision_lookup", "decision_id"),
        Index("ix_dossier_number", "dossier_number"),
        Index("ix_dossier_plan_id", "plan_id"),
        Index("ix_dossier_gov_state", "governance_state"),
        Index("ix_dossier_active", "is_active"),
        Index("ix_dossier_tenant", "organization_id", "team_id"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    dossier_number = Column(String(64), nullable=False, unique=True)
    decision_id = Column(String(128), nullable=False)
    decision_type = Column(String(64), nullable=False, default="EngineeringDecision")
    engineering_question = Column(Text, nullable=False)
    dossier_version = Column(Integer, nullable=False, default=1)
    parent_dossier_id = Column(UUID_TYPE, ForeignKey("engineering_decision_dossiers.id", ondelete="SET NULL"), nullable=True, index=True)

    plan_id = Column(UUID_TYPE, ForeignKey("engineering_validation_plans.id", ondelete="CASCADE"), nullable=False)
    plan_version = Column(Integer, nullable=False, default=1)
    plan_hash = Column(String(64), nullable=False)
    sealed_acceptance_criteria = Column(JSON_TYPE, nullable=False, default=list)

    exposure_assessment_id = Column(UUID_TYPE, ForeignKey("decision_exposure_assessments.id", ondelete="SET NULL"), nullable=True, index=True)
    exposure_hash = Column(String(64), nullable=True)

    baseline_robustness_analysis_id = Column(UUID_TYPE, ForeignKey("decision_robustness_analyses.id", ondelete="SET NULL"), nullable=True, index=True)
    baseline_robustness_hash = Column(String(64), nullable=True)

    closure_id = Column(UUID_TYPE, ForeignKey("validation_evidence_closures.id", ondelete="CASCADE"), nullable=False, index=True)
    closure_hash = Column(String(64), nullable=False)

    reassessment_id = Column(UUID_TYPE, ForeignKey("validation_decision_reassessments.id", ondelete="CASCADE"), nullable=False, index=True)
    reassessment_hash = Column(String(64), nullable=False)

    reassessed_robustness_analysis_id = Column(UUID_TYPE, ForeignKey("decision_robustness_analyses.id", ondelete="SET NULL"), nullable=True, index=True)
    reassessed_robustness_hash = Column(String(64), nullable=True)

    evidence_item_ids = Column(JSON_TYPE, nullable=False, default=list)
    source_verification_ids = Column(JSON_TYPE, nullable=False, default=list)

    evidence_lineage_summary = Column(JSON_TYPE, nullable=False, default=dict)
    contradictory_evidence_summary = Column(JSON_TYPE, nullable=False, default=dict)
    unresolved_assumptions = Column(JSON_TYPE, nullable=False, default=list)
    before_after_comparison = Column(JSON_TYPE, nullable=False, default=dict)

    governance_state = Column(String(64), nullable=False, default="DRAFT")
    admissibility_status = Column(String(32), nullable=False, default="PENDING")
    criteria_satisfaction_status = Column(String(32), nullable=False, default="PENDING")
    closure_status = Column(String(32), nullable=False, default="PENDING")
    conclusion_review_status = Column(String(32), nullable=False, default="PENDING")
    decision_approval_status = Column(String(32), nullable=False, default="PENDING")

    governance_separation_notice = Column(Text, nullable=False, default=GOVERNANCE_SEPARATION_NOTICE_V2)
    deployment_authorization_status = Column(String(32), nullable=False, default="NOT_ESTABLISHED")
    deployment_safety_inferred = Column(Boolean, nullable=False, default=False)

    review_audit_trail = Column(JSON_TYPE, nullable=False, default=list)
    dossier_content_hash = Column(String(64), nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)
    superseded_by = Column(UUID_TYPE, ForeignKey("engineering_decision_dossiers.id", ondelete="SET NULL"), nullable=True, index=True)

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    compiled_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)





