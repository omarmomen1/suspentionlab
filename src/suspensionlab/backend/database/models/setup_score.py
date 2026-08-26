"""
backend/database/models/setup_score.py
=======================================
Setup Score fleet benchmark store (Tier A1).

Rows are ANONYMOUS by design: no user_id, no team_id, no free-text fields.
Only the aggregate distribution is queryable — that's what makes engineers
willing to opt in ("compare me against the fleet") and what makes the
benchmark defensible as a data moat.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SetupScore(Base):
    __tablename__ = "setup_scores"
    __table_args__ = (
        Index("ix_setup_scores_class_score", "vehicle_class", "score"),
    )

    id            = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_class = Column(String(32), nullable=False)   # road|track|gt|rally|offroad|formula
    score         = Column(Float, nullable=False)
    comfort       = Column(Float, nullable=False)
    grip          = Column(Float, nullable=False)
    control       = Column(Float, nullable=False)
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
