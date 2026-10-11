"""
backend/database/models/audit.py
=================================
Durable audit models (Issue 23).

Two complementary ledgers:

1. AuditLog — security/compliance events (who did what, when, from where).
   Team-scoped so ENTERPRISE customers can retrieve their own trail.

2. EngineeringAuditLog — the durable engineering record for every simulation:
   who / what / when / vehicle / setup version / simulation version /
   physics version / parameters hash / result hash / software version /
   input dataset / output dataset. This is what makes a result defensible
   months later ("which exact code produced this number?").
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Integer, Text, ForeignKey, Index, Float
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """Security / compliance event ledger."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_team_ts", "team_id", "timestamp"),
        Index("ix_audit_logs_user_ts", "user_id", "timestamp"),
    )

    id         = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequence_number = Column(Integer, nullable=False, default=1, index=True)
    event      = Column(String(64), nullable=False)            # e.g. LOGIN_SUCCESS, SIMULATION_START
    user_id    = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    organization_id = Column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id    = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    ip         = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    artifact_id = Column(String(255), nullable=True, index=True)
    timestamp  = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    # NOTE: 'metadata' is reserved by SQLAlchemy's declarative API — the DB
    # column is still named "metadata" but the Python attribute is event_data.
    event_data = Column("metadata", JSON_TYPE, nullable=True)
    previous_hash = Column(String(64), nullable=True)
    hash = Column(String(64), nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="audit_logs")


class AuditOutbox(Base):
    """
    Transactional outbox for tamper-evident audit events (Step 4).
    Guarantees that no audit event is silently lost during transient failures.
    """
    __tablename__ = "audit_outbox"
    __table_args__ = (
        Index("ix_audit_outbox_status", "status"),
        Index("ix_audit_outbox_created", "created_at"),
    )

    id              = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = Column(String(128), nullable=True, unique=True, index=True)
    event_type      = Column(String(64), nullable=False)
    user_id         = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    organization_id = Column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id         = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    ip              = Column(String(64), nullable=True)
    user_agent      = Column(String(255), nullable=True)
    artifact_id     = Column(String(255), nullable=True, index=True)
    event_data      = Column("metadata", JSON_TYPE, nullable=True)
    status          = Column(String(20), nullable=False, default="PENDING")  # PENDING, PROCESSED, FAILED, DEAD_LETTER
    retry_count     = Column(Integer, nullable=False, default=0)
    max_retries     = Column(Integer, nullable=False, default=5)
    last_error      = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    processed_at    = Column(DateTime(timezone=True), nullable=True)


class EngineeringAuditLog(Base):
    """
    Immutable engineering provenance record — one row per completed simulation.

    Together with the SHA-256 hashes this answers, for any historical result:
      * WHO ran it and on which vehicle/setup
      * WHICH physics/simulation/software versions produced it
      * EXACTLY which inputs (hash of params + dataset) and outputs (hash of result)
    """
    __tablename__ = "engineering_audit_logs"
    __table_args__ = (
        Index("ix_eng_audit_user_ts", "user_id", "created_at"),
        Index("ix_eng_audit_team_ts", "team_id", "created_at"),
        Index("ix_eng_audit_job", "job_id"),
    )

    id                = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id            = Column(PG_UUID(as_uuid=True), nullable=True, index=True)   # FK-free ref to jobs.id
    user_id           = Column(PG_UUID(as_uuid=True), nullable=True)
    organization_id   = Column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id           = Column(PG_UUID(as_uuid=True), nullable=True)

    # What was simulated
    simulation_type   = Column(String(50), nullable=False)       # quarter_car | full_car | ...
    vehicle_ref       = Column(String(255), nullable=True)       # profile name / vehicle id
    setup_version     = Column(String(100), nullable=True)       # named setup (e.g. 'Spain-R3')
    dataset_ref       = Column(String(255), nullable=True)       # input dataset label (e.g. telemetry file)

    # Version pinning
    software_version  = Column(String(32), nullable=False, default="0.0.0")   # app version
    physics_version   = Column(String(32), nullable=False, default="unknown")  # physics model tag e.g. full-car-v3
    simulation_version= Column(String(32), nullable=False, default="unknown")  # solver/schema version

    # Integrity
    params_hash       = Column(String(64), nullable=False)       # SHA-256 of canonical params JSON
    result_hash       = Column(String(64), nullable=False)       # SHA-256 of canonical result JSON
    input_hash        = Column(String(64), nullable=True)        # SHA-256 of road/dataset payload
    compute_seconds   = Column(Float, nullable=True)

    created_at        = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
