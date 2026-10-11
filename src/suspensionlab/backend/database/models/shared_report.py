from __future__ import annotations
from sqlalchemy.sql import func
"""
Shared Report DB model — stores simulation results for public sharing.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Boolean, Integer, Index, Text, Float
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

JSON_TYPE = JSON().with_variant(JSONB, 'postgresql')
from suspensionlab.backend.database.core import Base


class SharedReport(Base):
    __tablename__ = "shared_reports"
    __table_args__ = (
        Index("ix_shared_reports_owner_ts", "owner_id", "created_at"),
        Index("ix_shared_reports_team_ts", "team_id", "created_at"),
        Index("ix_shared_reports_status", "status"),
    )

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    token = Column(String(36), unique=True, nullable=False, index=True,
                   default=lambda: str(uuid.uuid4()))
    simulation_type = Column(String(50), nullable=False, default="quarter_car")
    params = Column(JSON_TYPE, nullable=False)
    result = Column(JSON_TYPE, nullable=False)

    # ── Provenance & Lineage (#24 & Enterprise Reporting) ──────────────────────
    owner_id        = Column(PG_UUID(as_uuid=True), nullable=True, index=True)   # who shared it
    team_id         = Column(PG_UUID(as_uuid=True), nullable=True, index=True)   # team isolation partition
    organization_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)   # organization isolation partition
    simulation_id   = Column(PG_UUID(as_uuid=True), nullable=True)   # jobs.id / simulation_run.id artifact reference
    doc_id          = Column(String(32), nullable=True)              # formatted DOC ID e.g. DOC-2026-SL-0001
    vehicle_ref     = Column(String(255), nullable=True)
    setup_ref       = Column(String(255), nullable=True)
    tire_ref        = Column(String(255), nullable=True)
    track_ref       = Column(String(255), nullable=True)
    telemetry_ref   = Column(String(255), nullable=True)
    solver_version  = Column(String(64), nullable=True)
    software_build  = Column(String(64), nullable=True)
    validation_status = Column(String(32), nullable=True, default="UNVALIDATED")
    correlation_pct = Column(Float, nullable=True)

    params_hash     = Column(String(64), nullable=True)              # SHA-256 of canonical params
    result_hash     = Column(String(64), nullable=True)              # SHA-256 of canonical result
    input_hash      = Column(String(64), nullable=True)              # SHA-256 of road/dataset payload
    artifact_hash   = Column(String(64), nullable=True)              # SHA-256 of canonical full report artifact
    software_version= Column(String(32), nullable=True)
    physics_version = Column(String(32), nullable=True)
    provenance      = Column(String(20), nullable=False, default="client-asserted")  # verified | client-asserted
    signature       = Column(String(128), nullable=True)             # HMAC-SHA256 over token+hashes

    # ── Approval Lifecycle (PROPOSED | APPROVED | REJECTED | EXPORTED) ────────
    status          = Column(String(16), nullable=False, default="PROPOSED")
    approved_by_user_id = Column(PG_UUID(as_uuid=True), nullable=True)
    approved_by_email   = Column(String(255), nullable=True)
    approved_by_role    = Column(String(50), nullable=True)
    approved_at         = Column(DateTime(timezone=True), nullable=True)
    approval_comment    = Column(Text, nullable=True)
    approval_signature  = Column(String(128), nullable=True)

    # ── Hydrated Engineering Facets ───────────────────────────────────────────
    metrics             = Column(JSON_TYPE, nullable=True)
    telemetry_analysis  = Column(JSON_TYPE, nullable=True)
    optimization_data   = Column(JSON_TYPE, nullable=True)
    validation_data     = Column(JSON_TYPE, nullable=True)
    plot_data           = Column(JSON_TYPE, nullable=True)

    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    view_count = Column(Integer, default=0)
    is_public = Column(Boolean, default=False, nullable=False)
    title = Column(String(200), default="", nullable=False)
    notes = Column(String(2000), default="", nullable=False)
