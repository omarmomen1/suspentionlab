"""
backend/database/models/setup_proposal.py
==========================================
Setup Proposal artifacts (Issue 50) — the final step of the workflow:

    Diagnose → Simulate → Optimize → SETUP RECOMMENDATION → Engineer

A proposal is an immutable record of: the engineer's problem, the twin it
was generated for, how many feasible candidates were tested, the winning
parameter changes, predicted effects, constraint compliance, and confidence.
Engineers click "Create Setup Proposal" and get a traceable object they can
approve, reject, or export — never a chat bubble.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Integer, Float, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SetupProposal(Base):
    __tablename__ = "setup_proposals"
    __table_args__ = (
        Index("ix_proposals_twin_ts", "twin_id", "created_at"),
        Index("ix_proposals_user_ts", "user_id", "created_at"),
    )

    id         = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    twin_id    = Column(PG_UUID(as_uuid=True), ForeignKey("vehicle_twins.id", ondelete="CASCADE"), nullable=False)
    user_id    = Column(PG_UUID(as_uuid=True), nullable=False)
    team_id    = Column(PG_UUID(as_uuid=True), nullable=True)

    problem        = Column(Text, nullable=False)            # engineer's verbatim problem statement
    focus          = Column(String(32), nullable=False)      # comfort | grip | handling | balanced
    baseline_params = Column(JSON_TYPE, nullable=False)      # twin params at proposal time

    tested_setups  = Column(Integer, nullable=False)
    feasible_found = Column(Integer, nullable=False)

    recommended_params = Column(JSON_TYPE, nullable=False)   # full winning parameter set
    param_changes      = Column(JSON_TYPE, nullable=False)   # [{parameter, current, recommended, change_pct}]
    predicted_effects  = Column(JSON_TYPE, nullable=False)   # [{metric, unit, baseline, predicted, change_pct, improved}]
    constraint_violations = Column(JSON_TYPE, nullable=True) # empty list = fully feasible
    confidence         = Column(Float, nullable=False, default=0.0)

    status       = Column(String(16), nullable=False, default="PROPOSED")  # PROPOSED | APPROVED | REJECTED | EXPORTED
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
