"""
backend/database/models/engineering_question.py
================================================
Engineering Question Ingestion and Lifecycle Record.

Persists real engineering questions submitted by engineers:
    question_id, organization_id, team_id, vehicle_id, setup_id,
    title, question_text, context, severity, source, created_by,
    created_at, status, linked_telemetry_ids, linked_evidence,
    linked_experiments, linked_decisions.
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


class EngineeringQuestion(Base):
    """
    Formal Engineering Question Ingestion Record.
    Drives anomaly investigations, hypothesis generation, simulations, and decisions.
    """
    __tablename__ = "engineering_questions"
    __table_args__ = (
        Index("ix_questions_question_id", "question_id", unique=True),
        Index("ix_questions_user_ts", "created_by_user_id", "created_at"),
        Index("ix_questions_org_ts", "organization_id", "created_at"),
        Index("ix_questions_team_ts", "team_id", "created_at"),
        Index("ix_questions_status", "status"),
        Index("ix_questions_severity", "severity"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(String(64), nullable=False, unique=True)  # e.g. Q-2026-0001 or q-damper-t9

    # Multi-tenancy & Ownership
    organization_id = Column(Uuid(as_uuid=True), nullable=True)
    team_id = Column(Uuid(as_uuid=True), nullable=True)
    created_by_user_id = Column(Uuid(as_uuid=True), nullable=False)
    created_by = Column(String(128), nullable=False)

    # Core Engineering Context
    vehicle_id = Column(String(128), nullable=False, default="Formula 1 2026 Spec (CAR 07)")
    setup_id = Column(String(128), nullable=False, default="Spa-Francorchamps Aero Rev 28")
    title = Column(String(256), nullable=False)
    question_text = Column(Text, nullable=False)
    context = Column(JSON_TYPE, nullable=False, default=dict)

    # Classification & Lifecycle
    severity = Column(String(32), nullable=False, default="CRITICAL")  # CRITICAL | WARNING | INFO
    source = Column(String(64), nullable=False, default="ENGINEER_INPUT")  # TELEMETRY_ANOMALY | DRIVER_FEEDBACK | SIMULATION_DISCREPANCY | ENGINEER_INPUT
    status = Column(String(32), nullable=False, default="OPEN")  # OPEN | INVESTIGATING | HYPOTHESIS_FORMED | RESOLVED | CLOSED

    # Relational Evidence & Workflow Linkage
    linked_telemetry_ids = Column(JSON_TYPE, nullable=False, default=list)
    linked_evidence = Column(JSON_TYPE, nullable=False, default=list)  # [{label, value, residual, source, state, provenance}]
    linked_experiments = Column(JSON_TYPE, nullable=False, default=list)  # [exp_id | run_label]
    linked_decisions = Column(JSON_TYPE, nullable=False, default=list)  # [decision_id]

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
