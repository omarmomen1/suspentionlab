"""
backend/database/models/experiment.py
======================================
Reproducible Engineering Experiment Artifacts (Phase 3 Platform).

Captures the full hypothesis-testing workflow:
QUESTION → EXPERIMENT → SIMULATION → COMPARISON → OPTIMIZATION → VALIDATION → DECISION

Every experiment is an immutable, auditable entity that can be completely
reproduced from its stored definition.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Integer, Float, ForeignKey, Index, Text, Boolean, Uuid
from sqlalchemy.dialects.postgresql import JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExperimentRecord(Base):
    __tablename__ = "engineering_experiments"
    __table_args__ = (
        Index("ix_experiments_user_ts", "user_id", "created_at"),
        Index("ix_experiments_team_ts", "team_id", "created_at"),
        Index("ix_experiments_status", "status"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    team_id = Column(Uuid(as_uuid=True), nullable=True)

    # ── Engineering Intent & Context ──────────────────────────────────────────
    question = Column(Text, nullable=False)          # e.g. "What happens if I increase front roll stiffness by 10%?"
    hypothesis = Column(Text, nullable=False)        # Physical hypothesis to test
    author = Column(String(100), nullable=False, default="Lead Dynamics Engineer")

    # ── Versions & Traceability ───────────────────────────────────────────────
    vehicle_version = Column(String(50), nullable=False, default="v2026.1-Aero")
    setup_version = Column(String(50), nullable=False, default="rev-04")
    model_version = Column(String(50), nullable=False, default="QCAR-ODE-RK45-v2.1")
    solver = Column(String(100), nullable=False, default="scipy.integrate.solve_ivp(RK45, rtol=1e-6)")
    backend = Column(String(100), nullable=False, default="NumPy 1.26 / SciPy Vectorized C-Extension")
    simulation_id = Column(String(50), nullable=True)

    # ── Setup Snapshots & Parameter Deltas ────────────────────────────────────
    parent_setup = Column(JSON_TYPE, nullable=False)      # Baseline parameters snapshot
    candidate_setup = Column(JSON_TYPE, nullable=False)   # Candidate parameters snapshot
    parameter_changes = Column(JSON_TYPE, nullable=False) # [{parameter, unit, baseline, candidate, delta_abs, delta_pct}]

    # ── Simulation Results & Tradeoff Comparison ──────────────────────────────
    baseline_metrics = Column(JSON_TYPE, nullable=False)  # Raw baseline KPI metrics
    candidate_metrics = Column(JSON_TYPE, nullable=False) # Raw candidate KPI metrics
    improvements = Column(JSON_TYPE, nullable=False)      # [{metric, unit, baseline, candidate, delta_pct, reason}]
    regressions = Column(JSON_TYPE, nullable=False)       # [{metric, unit, baseline, candidate, delta_pct, reason}] - MANDATORY TRADEOFFS
    causal_chain = Column(JSON_TYPE, nullable=False)      # Physical step-by-step causality explanation

    # ── Constraints & Validation Status ───────────────────────────────────────
    constraints_passed = Column(Boolean, nullable=False, default=True)
    constraint_details = Column(JSON_TYPE, nullable=True) # [{constraint, limit, actual, unit, passed}]
    validation_state = Column(String(32), nullable=False, default="UNVALIDATED") # VALIDATED | UNVALIDATED | DEGRADED | FAILED
    confidence = Column(Float, nullable=False, default=0.0)
    recommendation = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="COMPLETED") # COMPLETED | FAILED | VIOLATED

    # ── Cryptographic Reproducibility ─────────────────────────────────────────
    result_hash = Column(String(64), nullable=False)      # SHA-256 canonical hash of parameters + results

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
