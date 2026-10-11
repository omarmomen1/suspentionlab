"""
backend/database/models/evidence_graph.py
=========================================
SuspensionLab PRO — Phase 4 Engineering Evidence Graph Canonical Edge Model.

Defines the singular, canonical directed edge entity:
    source entity  (source_type, source_id)
          ↓
    typed semantic relationship
          ↓
    target entity  (target_type, target_id)

Core Invariants:
1. Pure relationship layer: does NOT duplicate engineering objects.
2. Explicit semantic relationship vocabulary.
3. Multi-tenant scoped (organization_id, team_id).
4. Cryptographic provenance with deterministic edge_hash.
5. Captures historical endpoint artifact hashes at creation time.
6. Strictly INSERT-ONLY: edges cannot be updated or deleted.
7. Service-level referential integrity across polymorphic endpoints.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")

from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceGraphRelationship(str, enum.Enum):
    """
    Constrained canonical vocabulary for Evidence Graph semantic relationships.

    Every relationship has an explicit semantic direction:
    Forward traversal: 'What downstream engineering objects depend on this object?'
    Backward traversal: 'What upstream objects support or explain this object?'

    Defined directions:
    - OBSERVED_IN:       Investigation --OBSERVED_IN--> TelemetrySession
    - DETECTED_FROM:     Investigation --DETECTED_FROM--> TelemetrySession
    - FORMULATED_FROM:   Question --FORMULATED_FROM--> Investigation
    - EVIDENCED_BY:      Question / Decision --EVIDENCED_BY--> TelemetrySession / Run
    - HYPOTHESIZED_FROM: Hypothesis --HYPOTHESIZED_FROM--> Question / Problem
    - TESTED_BY:         Question / Hypothesis --TESTED_BY--> Experiment
    - EXECUTED_AS:       Experiment --EXECUTED_AS--> SimulationRun
    - USES_SETUP:        SimulationRun --USES_SETUP--> SetupCandidate
    - PRODUCED_SETUP:    SimulationRun / Optimization --PRODUCED_SETUP--> SetupCandidate
    - EVALUATED_IN:      SetupComparison --EVALUATED_IN--> BlindValidation
    - OPTIMIZED_TO:      Optimization --OPTIMIZED_TO--> SetupCandidate
    - VALIDATED_BY:      SetupCandidate --VALIDATED_BY--> BlindValidation
    - JUSTIFIED_BY:      Decision --JUSTIFIED_BY--> BlindValidation / Comparison
    - APPROVED_UNDER:    Approval --APPROVED_UNDER--> Decision
    - PREDICTED_FOR:     Prediction --PREDICTED_FOR--> Decision
    - RECONCILED_WITH:   Reconciliation --RECONCILED_WITH--> Prediction
    - SUPERSEDES:        New_Entity --SUPERSEDES--> Old_Entity
    """
    OBSERVED_IN = "OBSERVED_IN"
    DETECTED_FROM = "DETECTED_FROM"
    FORMULATED_FROM = "FORMULATED_FROM"
    EVIDENCED_BY = "EVIDENCED_BY"
    HYPOTHESIZED_FROM = "HYPOTHESIZED_FROM"
    TESTED_BY = "TESTED_BY"
    EXECUTED_AS = "EXECUTED_AS"
    USES_SETUP = "USES_SETUP"
    PRODUCED_SETUP = "PRODUCED_SETUP"
    EVALUATED_IN = "EVALUATED_IN"
    OPTIMIZED_TO = "OPTIMIZED_TO"
    VALIDATED_BY = "VALIDATED_BY"
    JUSTIFIED_BY = "JUSTIFIED_BY"
    APPROVED_UNDER = "APPROVED_UNDER"
    PREDICTED_FOR = "PREDICTED_FOR"
    RECONCILED_WITH = "RECONCILED_WITH"
    SUPERSEDES = "SUPERSEDES"


class SupportedEntityType(str, enum.Enum):
    """
    Canonical registry of authoritative engineering entities supported
    as endpoints in the Evidence Graph.
    """
    TELEMETRY_SESSION = "TelemetrySession"
    INVESTIGATION = "Investigation"
    ENGINEERING_QUESTION = "EngineeringQuestion"
    ENGINEERING_PROBLEM = "EngineeringProblem"
    CAUSAL_HYPOTHESIS = "CausalHypothesis"
    EXPERIMENT = "Experiment"
    CONTROLLED_EXPERIMENT = "ControlledExperiment"
    SIMULATION_RUN = "SimulationRun"
    SETUP_CANDIDATE = "SetupCandidate"
    VEHICLE_PROFILE = "VehicleProfile"
    VEHICLE_TWIN = "VehicleTwin"
    SETUP_PROPOSAL = "SetupProposal"
    SETUP_COMPARISON = "SetupComparison"
    OPTIMIZATION = "Optimization"
    BLIND_VALIDATION = "BlindValidation"
    ENGINEERING_DECISION = "EngineeringDecision"
    APPROVAL = "Approval"
    TRACK_TEST_PREDICTION = "TrackTestPrediction"
    POST_TRACK_RECONCILIATION = "PostTrackReconciliation"
    TIMELINE_EVENT = "TimelineEvent"


class EdgeImmutabilityError(Exception):
    """Raised when an update or delete operation is attempted on an immutable edge."""
    pass


class EvidenceGraphEdgeRecord(Base):
    """
    Canonical Evidence Graph Edge Model.
    Represents an immutable, auditable, tenant-scoped directed relationship
    between two existing authoritative engineering entities.
    """
    __tablename__ = "evidence_graph_edges"
    __table_args__ = (
        Index("ix_edges_source", "team_id", "source_type", "source_id"),
        Index("ix_edges_target", "team_id", "target_type", "target_id"),
        Index("ix_edges_rel", "team_id", "relationship"),
        Index("ix_edges_user", "created_by_user_id"),
        Index("ix_edges_org", "organization_id"),
        Index("ix_edges_edge_hash", "edge_hash"),
        Index("ix_edges_created_at", "created_at"),
        UniqueConstraint(
            "team_id",
            "source_type",
            "source_id",
            "relationship",
            "target_type",
            "target_id",
            name="uq_evidence_graph_edge",
        ),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID_TYPE, nullable=True)
    team_id = Column(UUID_TYPE, nullable=True)
    created_by_user_id = Column(UUID_TYPE, nullable=False)

    source_type = Column(String(64), nullable=False)
    source_id = Column(String(128), nullable=False)

    relationship = Column(String(64), nullable=False)

    target_type = Column(String(64), nullable=False)
    target_id = Column(String(128), nullable=False)

    source_artifact_hash = Column(String(64), nullable=True)
    target_artifact_hash = Column(String(64), nullable=True)

    # Declarative Base reserves 'metadata', so attribute name is metadata_
    metadata_ = Column("metadata", JSON_TYPE, nullable=False, default=dict)

    edge_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


# ── ORM-LEVEL IMMUTABILITY ENFORCEMENT ────────────────────────────────────────

@event.listens_for(EvidenceGraphEdgeRecord, "before_update")
def _prevent_edge_update(mapper, connection, target):
    raise EdgeImmutabilityError(
        f"EvidenceGraphEdge {target.id} is immutable and cannot be updated. Use SUPERSEDES relationship for obsolescence."
    )


@event.listens_for(EvidenceGraphEdgeRecord, "before_delete")
def _prevent_edge_delete(mapper, connection, target):
    raise EdgeImmutabilityError(
        f"EvidenceGraphEdge {target.id} is immutable and cannot be deleted. Historical decision lineage must not be destroyed."
    )
