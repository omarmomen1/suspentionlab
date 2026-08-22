from __future__ import annotations
from sqlalchemy.sql import func
"""
Shared Report DB model — stores simulation results for public sharing.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

JSON_TYPE = JSON().with_variant(JSONB, 'postgresql')
from suspensionlab.backend.database.core import Base


class SharedReport(Base):
    __tablename__ = "shared_reports"

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

    # ── Provenance (#24) — enterprise reports must be traceable to a real run ──
    owner_id        = Column(PG_UUID(as_uuid=True), nullable=True)   # who shared it
    simulation_id   = Column(PG_UUID(as_uuid=True), nullable=True)   # jobs.id artifact reference
    params_hash     = Column(String(64), nullable=True)              # SHA-256 of canonical params
    result_hash     = Column(String(64), nullable=True)              # SHA-256 of canonical result
    input_hash      = Column(String(64), nullable=True)              # SHA-256 of road/dataset payload
    software_version= Column(String(32), nullable=True)
    physics_version = Column(String(32), nullable=True)
    provenance      = Column(String(20), nullable=False, default="client-asserted")  # verified | client-asserted
    signature       = Column(String(128), nullable=True)             # HMAC-SHA256 over token+hashes
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    view_count = Column(Integer, default=0)
    is_public = Column(Boolean, default=True, nullable=False)
    title = Column(String(200), default="", nullable=False)
    notes = Column(String(2000), default="", nullable=False)
