"""
backend/database/models/solver_execution.py
===========================================
SuspensionLab PRO — Phase 7.3 Controlled Solver Execution & Reconciliation Models.

Defines the persistent, tenant-isolated execution lifecycle and reconciliation records:
    SolverExecutionJob (FSM with Terminal State Immutability and Provenance Recording)

Core Invariants:
1. Immutable Terminal States: Once COMPLETED, FAILED, CANCELLED, or TIMED_OUT, records cannot be mutated.
2. Epistemic Invariants:
   - is_executed: Boolean set to True ONLY following verified real external process completion with exit code 0.
   - is_physically_validated: Boolean strictly False (numerical execution != physical proving-ground validation).
3. Strict Tenant Isolation: Every job is bounded by (organization_id, team_id, user_id).
4. Provenance Preserved: Process PID, start/end timestamps, stdout/stderr excerpts, exit codes, and output hashes.
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


class ExecutionJobState(str, enum.Enum):
    """Finite State Machine states for solver execution jobs."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


TERMINAL_EXECUTION_STATES: Set[str] = {
    ExecutionJobState.COMPLETED.value,
    ExecutionJobState.FAILED.value,
    ExecutionJobState.CANCELLED.value,
    ExecutionJobState.TIMED_OUT.value,
}

VALID_EXECUTION_TRANSITIONS: Dict[str, Set[str]] = {
    ExecutionJobState.QUEUED.value: {
        ExecutionJobState.RUNNING.value,
        ExecutionJobState.CANCELLED.value,
        ExecutionJobState.FAILED.value,
    },
    ExecutionJobState.RUNNING.value: {
        ExecutionJobState.COMPLETED.value,
        ExecutionJobState.FAILED.value,
        ExecutionJobState.CANCELLED.value,
        ExecutionJobState.TIMED_OUT.value,
    },
    ExecutionJobState.COMPLETED.value: set(),
    ExecutionJobState.FAILED.value: set(),
    ExecutionJobState.CANCELLED.value: set(),
    ExecutionJobState.TIMED_OUT.value: set(),
}


class ImmutableExecutionError(RuntimeError):
    """Raised when an operation attempts to mutate an execution job in a terminal state."""
    pass


class InvalidExecutionStateTransitionError(ValueError):
    """Raised when an illegal state transition is attempted on a solver execution job."""
    pass


class SolverExecutionJob(Base):
    """
    Persisted, tenant-scoped external solver execution job.
    Manages process sandbox state, resource tracking, provenance, and output artifacts.
    """
    __tablename__ = "solver_execution_jobs"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    solver_name = Column(String(64), nullable=False)
    solver_version = Column(String(32), nullable=False)
    adapter_id = Column(String(128), nullable=False)

    state = Column(String(32), nullable=False, default=ExecutionJobState.QUEUED.value, index=True)

    input_artifact_id = Column(UUID_TYPE, ForeignKey("solver_exchange_artifacts.id", ondelete="SET NULL"), nullable=True)
    input_artifact_hash = Column(String(64), nullable=False)
    output_artifact_ids = Column(JSON_TYPE, nullable=False, default=list)

    execution_config = Column(JSON_TYPE, nullable=False, default=dict)
    resource_limits = Column(JSON_TYPE, nullable=False, default=dict)

    pid = Column(Integer, nullable=True)
    exit_code = Column(Integer, nullable=True)

    stdout_excerpt = Column(Text, nullable=True)
    stderr_excerpt = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    error_category = Column(String(64), nullable=True)

    # Lease & Concurrency Hardening (Phase 7.4)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    execution_mode = Column(String(32), nullable=False, default="TRUSTED_ALLOWLIST")
    benchmark_reference_type = Column(String(64), nullable=True)

    # Epistemic Invariants
    is_executed = Column(Boolean, nullable=False, default=False)
    is_physically_validated = Column(Boolean, nullable=False, default=False)

    execution_provenance = Column(JSON_TYPE, nullable=False, default=dict)
    reconciliation_summary = Column(JSON_TYPE, nullable=False, default=dict)

    idempotency_key = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_solver_execution_jobs_tenant_state", "team_id", "state", "created_at"),
        Index("ix_solver_execution_jobs_user_state", "user_id", "state", "created_at"),
        Index("ix_solver_execution_jobs_idemp", "user_id", "idempotency_key"),
        Index("ix_solver_execution_jobs_hash", "input_artifact_hash"),
        Index("ix_solver_execution_jobs_lease", "state", "lease_expires_at"),
    )

    def assert_mutable(self) -> None:
        """Enforces that the execution record cannot be modified if in a terminal state."""
        if self.state in TERMINAL_EXECUTION_STATES:
            raise ImmutableExecutionError(
                f"Cannot mutate execution job '{self.id}': Record is in immutable terminal state '{self.state}'."
            )

    def transition_to(
        self,
        new_state: ExecutionJobState,
        exit_code: Optional[int] = None,
        failure_reason: Optional[str] = None,
        error_category: Optional[str] = None,
    ) -> None:
        """
        Transitions the job to a new state under strict FSM governance rules.
        """
        target = new_state.value if isinstance(new_state, ExecutionJobState) else new_state

        if self.state in TERMINAL_EXECUTION_STATES:
            raise ImmutableExecutionError(
                f"Illegal transition from terminal state '{self.state}' to '{target}' for job '{self.id}'."
            )

        valid_targets = VALID_EXECUTION_TRANSITIONS.get(self.state, set())
        if target not in valid_targets:
            raise InvalidExecutionStateTransitionError(
                f"Illegal state transition from '{self.state}' to '{target}' for job '{self.id}'. "
                f"Permitted next states: {sorted(list(valid_targets))}."
            )

        self.state = target
        self.updated_at = _utcnow()

        if target == ExecutionJobState.RUNNING.value and self.started_at is None:
            self.started_at = _utcnow()

        if target in TERMINAL_EXECUTION_STATES:
            self.completed_at = _utcnow()
            if exit_code is not None:
                self.exit_code = exit_code
            if failure_reason is not None:
                self.failure_reason = failure_reason
            if error_category is not None:
                self.error_category = error_category
            if target == ExecutionJobState.COMPLETED.value:
                # Real external execution verified
                self.is_executed = True
                self.is_physically_validated = False  # NEVER fabricate physical validation
