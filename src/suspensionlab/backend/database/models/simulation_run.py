"""
backend/database/models/simulation_run.py
==========================================
Immutable Engineering Artifacts (Issue 32).

Every completed simulation becomes an immutable object — RUN-000183 — that
captures the complete engineering context:

    vehicle / setup / tire / track / telemetry references
    physics + kinematics + solver + software versions
    parameters, objective, constraints
    results, warnings, model validity
    input/result hashes, git/build id, timestamp, user

Immutability contract: rows are INSERT-only. The service layer never issues
UPDATEs against this table; comparisons are done by reading two artifacts.

This is what makes "Run A vs Run B vs Run C" trivial — and auditable forever.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Integer, Float, ForeignKey, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")
from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    __table_args__ = (
        Index("ix_simruns_user_ts", "user_id", "created_at"),
        Index("ix_simruns_team_ts", "team_id", "created_at"),
        Index("ix_simruns_job", "job_id"),
        Index("ix_simruns_label", "label", unique=True),
    )

    id         = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    seq        = Column(Integer, nullable=False, unique=True)   # global monotonic sequence
    label      = Column(String(24), nullable=False)             # "RUN-000183"
    job_id     = Column(UUID_TYPE, nullable=True)   # originating job (nullable for imported runs)
    user_id    = Column(UUID_TYPE, nullable=False)
    team_id    = Column(UUID_TYPE, nullable=True)

    # ── What was simulated ────────────────────────────────────────────────
    simulation_type = Column(String(50), nullable=False)        # quarter_car | full_car | lap_sim…
    title           = Column(String(200), nullable=False, default="")
    vehicle_ref     = Column(String(255), nullable=True)        # profile/vehicle name
    setup_ref       = Column(String(255), nullable=True)        # named setup e.g. 'Spain-R3'
    tire_ref        = Column(String(255), nullable=True)        # tire/TIR identifier
    track_ref       = Column(String(255), nullable=True)        # track/event identifier
    telemetry_ref   = Column(String(255), nullable=True)        # source telemetry session

    objective       = Column(String(100), nullable=True)        # optimisation objective if any
    constraints     = Column(JSON_TYPE, nullable=True)          # constraint set applied

    # ── Full payload snapshots ────────────────────────────────────────────
    params          = Column(JSON_TYPE, nullable=False)
    profile         = Column(JSON_TYPE, nullable=True)          # road/track definition
    result          = Column(JSON_TYPE, nullable=False)
    warnings        = Column(JSON_TYPE, nullable=True)          # solver/validation warnings
    model_validity  = Column(JSON_TYPE, nullable=True)          # Issue-16 validity report
    tire_snapshot   = Column(JSON_TYPE, nullable=True)          # Pacejka/empirical tire coeffs snapshot
    aero_snapshot   = Column(JSON_TYPE, nullable=True)          # Downforce/drag polar snapshot
    track_geometry_hash = Column(String(64), nullable=True)     # SHA-256 of track curvature/elevation profile

    # ── Version pinning ───────────────────────────────────────────────────
    software_version    = Column(String(32), nullable=False)
    physics_version     = Column(String(32), nullable=False)
    kinematics_version  = Column(String(32), nullable=False, default="unknown")
    solver_version      = Column(String(32), nullable=False)
    git_build_id        = Column(String(64), nullable=True)     # commit / CI build id

    # ── Integrity ─────────────────────────────────────────────────────────
    params_hash     = Column(String(64), nullable=False)
    result_hash     = Column(String(64), nullable=False)
    input_hash      = Column(String(64), nullable=True)
    compute_seconds = Column(Float, nullable=True)

    created_at      = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
