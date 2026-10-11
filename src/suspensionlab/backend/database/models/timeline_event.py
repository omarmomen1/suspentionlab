"""
backend/database/models/timeline_event.py
==========================================
Vehicle Development Timeline Event Record (Sections 10, 11, 12).

Persists the complete chronological timeline across all 11 engineering events:
    vehicle_change, setup_change, telemetry_session, calibration,
    simulation, optimization, validation, report, approval,
    track_session, engineering_decision.

Exposes who, when, what changed, why, vehicle/setup/model versions,
evidence, result, approval, and supports "What Changed?" diffing.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Text, Index, Uuid
from sqlalchemy.dialects.postgresql import JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimelineEventRecord(Base):
    """
    Chronological Vehicle Development Timeline Event.
    Enables historical tracking, lineage inspection, and "What Changed?" event comparison.
    """
    __tablename__ = "timeline_events"
    __table_args__ = (
        Index("ix_timeline_event_type", "event_type"),
        Index("ix_timeline_user_ts", "user_id", "created_at"),
        Index("ix_timeline_team_ts", "team_id", "created_at"),
        Index("ix_timeline_vehicle_setup", "vehicle_ref", "setup_ref"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(64), nullable=False)  # e.g. calibration, setup_change, track_session, etc.
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    author = Column(String(120), nullable=False)
    
    # Version Context
    vehicle_ref = Column(String(120), nullable=False)
    setup_ref = Column(String(120), nullable=False)
    model_version = Column(String(64), nullable=False)
    
    # What Changed & Engineering Effects (Section 11 & 12)
    before_state = Column(JSON_TYPE, nullable=True)          # State prior to event
    after_state = Column(JSON_TYPE, nullable=True)           # State resulting from event
    parameter_changes = Column(JSON_TYPE, nullable=True)     # [{parameter, before, after, delta_pct, unit}]
    engineering_effects = Column(JSON_TYPE, nullable=True)   # [{metric, baseline, result, delta_pct, explanation}]
    validation_effects = Column(JSON_TYPE, nullable=True)    # Changes to R², holdout, constraints
    decision_consequences = Column(JSON_TYPE, nullable=True) # Operational decisions stemming from this event
    
    # Evidence & Governance
    evidence = Column(JSON_TYPE, nullable=True)              # Rig data, session IDs, solver logs
    result = Column(JSON_TYPE, nullable=True)                # Final KPIs / metrics summary
    approval_status = Column(String(32), nullable=False, default="UNVALIDATED") # RECOMMENDED | VALIDATED | APPROVED
    approved_by = Column(String(120), nullable=True)
    
    # Cryptographic Provenance
    artifact_hashes = Column(JSON_TYPE, nullable=False)      # SHA-256 hashes of inputs, model, result
    
    # Linked Entity
    linked_entity_type = Column(String(64), nullable=True)   # e.g. "decision", "twin", "proposal", "simulation"
    linked_entity_id = Column(String(128), nullable=True)    # UUID or reference code of entity
    
    # Multi-tenancy & ownership
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    team_id = Column(Uuid(as_uuid=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
