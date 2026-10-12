"""
backend/database/models/solver_exchange.py
==========================================
SuspensionLab PRO — Phase 7.2 Solver Interoperability Persistent Exchange Models.

Defines the auditable, tenant-scoped exchange operation lifecycle and artifact registry:
    SolverExchangeArtifact (Input/Output Artifact Files)
              ↓
    SolverExchangeOperation (Finite State Machine with Immutable Terminal States)

Core Invariants:
1. Immutable Terminal States: Once in COMPLETED, REJECTED, or FAILED, operations cannot be mutated.
2. Epistemic Invariants:
   - is_executed: Boolean strictly False (export != solver execution).
   - is_physically_validated: Boolean strictly False (parsing != physical validation).
3. Strict Tenant Isolation: Every operation and artifact is scoped by (organization_id, team_id, user_id).
4. Full Auditability: Content hashes (SHA-256), coordinate frames, units, mapping diagnostics, and timestamps.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")

from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExchangeOperationType(str, enum.Enum):
    """Direction of the solver exchange workflow."""
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"


class ExchangeOperationState(str, enum.Enum):
    """Finite State Machine states for solver exchange operations."""
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    TRANSFORMING = "TRANSFORMING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ArtifactDirection(str, enum.Enum):
    """Direction of the artifact file."""
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


TERMINAL_OPERATION_STATES: Set[ExchangeOperationState] = {
    ExchangeOperationState.COMPLETED,
    ExchangeOperationState.REJECTED,
    ExchangeOperationState.FAILED,
}

ALLOWED_STATE_TRANSITIONS: Dict[ExchangeOperationState, Set[ExchangeOperationState]] = {
    ExchangeOperationState.PENDING: {
        ExchangeOperationState.VALIDATING,
        ExchangeOperationState.REJECTED,
        ExchangeOperationState.FAILED,
    },
    ExchangeOperationState.VALIDATING: {
        ExchangeOperationState.TRANSFORMING,
        ExchangeOperationState.REJECTED,
        ExchangeOperationState.FAILED,
    },
    ExchangeOperationState.TRANSFORMING: {
        ExchangeOperationState.COMPLETED,
        ExchangeOperationState.FAILED,
    },
    ExchangeOperationState.COMPLETED: set(),
    ExchangeOperationState.REJECTED: set(),
    ExchangeOperationState.FAILED: set(),
}


class InteropLifecycleError(ValueError):
    """Base exception for solver exchange lifecycle violations."""
    pass


class InvalidStateTransitionError(InteropLifecycleError):
    """Raised when an illegal transition in the operation state machine is attempted."""
    pass


class ImmutableOperationError(InteropLifecycleError):
    """Raised when attempting to modify a terminal, immutable solver exchange operation."""
    pass


class SolverExchangeArtifact(Base):
    """
    Persisted record of an ingested or exported solver artifact.
    """
    __tablename__ = "solver_exchange_artifacts"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    artifact_name = Column(String(255), nullable=False)
    file_format = Column(String(64), nullable=False)
    mime_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256_hash = Column(String(64), nullable=False)
    storage_path = Column(String(512), nullable=False)
    direction = Column(String(32), nullable=False)  # INPUT or OUTPUT

    created_at = Column(DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_solver_exchange_artifacts_tenant", "team_id", "sha256_hash"),
        Index("ix_solver_exchange_artifacts_user", "user_id", "sha256_hash"),
        Index("ix_solver_exchange_artifacts_hash", "sha256_hash"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "team_id": str(self.team_id) if self.team_id else None,
            "user_id": str(self.user_id),
            "artifact_name": self.artifact_name,
            "file_format": self.file_format,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256_hash": self.sha256_hash,
            "direction": self.direction,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SolverExchangeOperation(Base):
    """
    Persisted audit record of a solver exchange operation with finite state machine lifecycle.
    """
    __tablename__ = "solver_exchange_operations"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    operation_type = Column(String(32), nullable=False)  # IMPORT or EXPORT
    adapter_id = Column(String(128), nullable=False)
    adapter_version = Column(String(32), nullable=False)
    solver_name = Column(String(64), nullable=False)

    state = Column(String(32), nullable=False, default=ExchangeOperationState.PENDING.value)
    input_artifact_id = Column(UUID_TYPE, ForeignKey("solver_exchange_artifacts.id", ondelete="SET NULL"), nullable=True)
    output_artifact_id = Column(UUID_TYPE, ForeignKey("solver_exchange_artifacts.id", ondelete="SET NULL"), nullable=True)

    canonical_manifest_version = Column(String(32), nullable=False, default="1.0.0")
    manifest_hash = Column(String(64), nullable=True)
    coordinate_frame = Column(JSON_TYPE, nullable=False, default=dict)
    units_summary = Column(JSON_TYPE, nullable=False, default=dict)
    mapping_diagnostics = Column(JSON_TYPE, nullable=False, default=dict)
    validation_diagnostics = Column(JSON_TYPE, nullable=False, default=dict)
    failure_reason = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=True)

    # Epistemic Invariants - strictly False
    is_executed = Column(Boolean, nullable=False, default=False)
    is_physically_validated = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, server_default=func.now(), onupdate=_utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_solver_exchange_ops_tenant", "team_id", "state", "created_at"),
        Index("ix_solver_exchange_ops_user", "user_id", "state", "created_at"),
        Index("ix_solver_exchange_ops_idemp", "user_id", "idempotency_key"),
        Index("ix_solver_exchange_ops_hash", "manifest_hash"),
    )

    def transition_to(self, new_state: ExchangeOperationState, failure_reason: Optional[str] = None) -> None:
        """
        Executes a formal state machine transition, enforcing terminal immutability.
        """
        curr = ExchangeOperationState(self.state)
        target = ExchangeOperationState(new_state)

        if curr in TERMINAL_OPERATION_STATES:
            raise ImmutableOperationError(
                f"Cannot transition operation '{self.id}' from terminal state '{curr.value}' to '{target.value}'."
            )

        if target not in ALLOWED_STATE_TRANSITIONS.get(curr, set()):
            raise InvalidStateTransitionError(
                f"Illegal state transition from '{curr.value}' to '{target.value}' for operation '{self.id}'."
            )

        self.state = target.value
        self.updated_at = _utcnow()

        if failure_reason:
            self.failure_reason = failure_reason

        if target in TERMINAL_OPERATION_STATES:
            self.completed_at = _utcnow()

    def assert_mutable(self) -> None:
        """Raises ImmutableOperationError if the operation is in a terminal state."""
        curr = ExchangeOperationState(self.state)
        if curr in TERMINAL_OPERATION_STATES:
            raise ImmutableOperationError(
                f"Operation '{self.id}' is in terminal state '{curr.value}' and cannot be modified."
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "team_id": str(self.team_id) if self.team_id else None,
            "user_id": str(self.user_id),
            "operation_type": self.operation_type,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "solver_name": self.solver_name,
            "state": self.state,
            "input_artifact_id": str(self.input_artifact_id) if self.input_artifact_id else None,
            "output_artifact_id": str(self.output_artifact_id) if self.output_artifact_id else None,
            "canonical_manifest_version": self.canonical_manifest_version,
            "manifest_hash": self.manifest_hash,
            "coordinate_frame": self.coordinate_frame or {},
            "units_summary": self.units_summary or {},
            "mapping_diagnostics": self.mapping_diagnostics or {},
            "validation_diagnostics": self.validation_diagnostics or {},
            "failure_reason": self.failure_reason,
            "idempotency_key": self.idempotency_key,
            "is_executed": bool(self.is_executed),
            "is_physically_validated": bool(self.is_physically_validated),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
