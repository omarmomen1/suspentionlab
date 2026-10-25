"""
backend/database/models/cosim_contract.py
=========================================
SuspensionLab PRO — Phase 7.5 Co-Simulation Coupling Contract Models.

Defines the persistent, versioned interface contract for multi-domain co-simulation:
    CoSimulationCouplingContract

Core Invariants:
1. Strict Signal Causality: Source variables must be 'output'; target variables must be 'input'.
2. Dimensional and Unit Consistency: Signals must match or provide explicit conversion factor and offset.
3. Time-Base & Synchronization Governance: Explicit communication step size, synchronization policy,
   interpolation mode, and algebraic loop detection.
4. Cryptographic Provenance: Participating models are locked to verified SHA-256 artifact hashes.
5. Strict Multi-Tenant Isolation: Bounded by (organization_id, team_id, created_by_user_id).
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
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")

from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContractStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class SynchronizationPolicy(str, enum.Enum):
    GAUSS_SEIDEL = "GAUSS_SEIDEL"  # Sequential exchange (Model A -> Model B)
    JACOBI = "JACOBI"              # Parallel exchange (both models use outputs from t_k)
    ITERATIVE_GAUSS_SEIDEL = "ITERATIVE_GAUSS_SEIDEL"  # Fixed-point iteration for algebraic loops


class InterpolationMode(str, enum.Enum):
    ZERO_ORDER_HOLD = "ZERO_ORDER_HOLD"  # Constant throughout step
    FIRST_ORDER_HOLD = "FIRST_ORDER_HOLD"  # Linear ramp throughout step


class CoSimulationCouplingContract(Base):
    """
    Persisted, tenant-scoped versioned co-simulation interface coupling contract.
    Governs signal routing, units, causality, and time synchronization for multi-model runs.
    """
    __tablename__ = "co_simulation_coupling_contracts"

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    contract_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    version = Column(String(32), nullable=False, default="1.0.0")
    description = Column(Text, nullable=True)

    status = Column(String(32), nullable=False, default=ContractStatus.DRAFT.value, index=True)

    # Multi-Tenant Ownership
    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    # Participating Models Specification
    # List of dicts: [{model_id, name, role, artifact_id, sha256_hash, fmi_version, variables, capabilities}]
    participating_models = Column(JSON_TYPE, nullable=False, default=list)

    # Signal Routing Connections
    # List of dicts: [{source_model, source_variable, target_model, target_variable,
    #                  source_unit, target_unit, conversion_scale, conversion_offset}]
    connections = Column(JSON_TYPE, nullable=False, default=list)

    # Time Synchronization & Master Configuration
    # {communication_step_size, min_step_size, max_step_size, sync_policy, interpolation_mode,
    #  extrapolation_allowed, max_iterations, convergence_tolerance}
    time_sync_config = Column(JSON_TYPE, nullable=False, default=dict)

    # Operating Bounds & Failure Handling
    # {signal_bounds: {signal_name: [min, max]}, on_breach: "TERMINATE_IMMEDIATELY", energy_conservation_tolerance}
    operating_bounds = Column(JSON_TYPE, nullable=False, default=dict)

    # Preflight Validation Diagnostics Report
    # {is_valid, validation_errors, warnings, algebraic_loops_detected, feedthrough_summary, validated_at}
    validation_report = Column(JSON_TYPE, nullable=False, default=dict)

    # Phase 7.6 Genuine Feedback Co-Simulation Fields
    feedback_topology = Column(String(64), nullable=False, default="FEEDFORWARD", index=True)
    staggered_execution_order = Column(JSON_TYPE, nullable=False, default=list)
    energy_residual_tolerance = Column(Float, nullable=False, default=0.05)

    created_at = Column(DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_cosim_contracts_tenant_status", "team_id", "status", "created_at"),
        Index("ix_cosim_contracts_user_status", "created_by_user_id", "status", "created_at"),
        Index("ix_cosim_contracts_org_status", "organization_id", "status"),
    )
