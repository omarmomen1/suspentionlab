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
    Column,
    DateTime,
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

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
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

    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
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

