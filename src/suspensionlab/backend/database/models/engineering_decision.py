"""
backend/database/models/engineering_decision.py
================================================
Formal Engineering Decision Record (Section 13).

Persists the immutable, audit-defensible engineering decision:
    Decision ID, Question, Context, Evidence, Candidates,
    Selected Option, Reason, Tradeoffs, Simulation Evidence,
    Telemetry Evidence, Validation Evidence, Risks, Author,
    Approver, Timestamp, Artifact Hashes.

Strictly maintains distinct uncertainty states:
    RECOMMENDED ≠ VALIDATED ≠ APPROVED
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Text, ForeignKey, Index, Uuid
from sqlalchemy.dialects.postgresql import JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringDecision(Base):
    """
    Formal Engineering Decision Record.
    Captures complete hypothesis, options, tradeoffs, evidence, and non-repudiable sign-off.
    """
    __tablename__ = "engineering_decisions"
    __table_args__ = (
        Index("ix_decisions_decision_id", "decision_id", unique=True),
        Index("ix_decisions_user_ts", "user_id", "created_at"),
        Index("ix_decisions_team_ts", "team_id", "created_at"),
        Index("ix_decisions_status", "status"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id = Column(String(64), nullable=False)  # e.g. DEC-2026-0042
    question = Column(Text, nullable=False)           # Engineering problem/question statement
    
    # 8-Dimension Context
    context = Column(JSON_TYPE, nullable=False)       # {vehicle, setup, track, session, model_version, etc.}
    
    # Options & Candidate Analysis
    candidates = Column(JSON_TYPE, nullable=False)    # List of candidate setups evaluated
    selected_option = Column(JSON_TYPE, nullable=False)# The winning setup option
    reason = Column(Text, nullable=False)             # Engineering justification for selection
    tradeoffs = Column(JSON_TYPE, nullable=False)     # Mandatory exposed tradeoffs
    risks = Column(JSON_TYPE, nullable=False)         # Identified risks & operational envelope boundaries
    
    # Three-Pillar Evidence
    simulation_evidence = Column(JSON_TYPE, nullable=False) # Solver, run_ids, deltas, metrics
    telemetry_evidence = Column(JSON_TYPE, nullable=False)  # Telemetry sessions, correlation R², residuals
    validation_evidence = Column(JSON_TYPE, nullable=False) # Holdout R², rig dyno tests, constraints passed
    evidence_summary = Column(Text, nullable=True)          # Concise executive summary of evidence
    
    # State & Governance
    # RECOMMENDED ≠ VALIDATED ≠ APPROVED
    status = Column(String(32), nullable=False, default="RECOMMENDED")
    author = Column(String(120), nullable=False)
    approver = Column(String(120), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_signature = Column(String(128), nullable=True)  # HMAC-SHA256 server-verifiable authenticated approval token (tamper-evident)
    
    # Provenance
    artifact_hashes = Column(JSON_TYPE, nullable=False)  # {simulation_hash, telemetry_hash, decision_hash}
    
    # Multi-tenancy & ownership
    user_id = Column(Uuid(as_uuid=True), nullable=False)
    team_id = Column(Uuid(as_uuid=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
