"""
backend/database/models/blind_engineering.py
============================================
SuspensionLab PRO — Phase 5.1 Blind Engineering Session & Submission Models.

Implements the information-governance core:
- BlindEngineeringSession: finite state machine, immutable configuration, tenant-isolated.
- BlindSubmission: immutable prediction record, deterministic content hash, lock boundary.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import relationship

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
UUID_TYPE = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")

from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BlindSessionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ARMED = "ARMED"
    BLIND_ACTIVE = "BLIND_ACTIVE"
    SUBMISSION_LOCKED = "SUBMISSION_LOCKED"
    READY_FOR_REVEAL = "READY_FOR_REVEAL"
    REVEALED = "REVEALED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class VisibilityClassification(str, enum.Enum):
    PUBLIC_TO_SESSION = "PUBLIC_TO_SESSION"
    VISIBLE_TO_EVALUATOR = "VISIBLE_TO_EVALUATOR"
    HIDDEN_FROM_EVALUATOR = "HIDDEN_FROM_EVALUATOR"
    SYSTEM_ONLY = "SYSTEM_ONLY"


class ConfigurationImmutabilityError(Exception):
    """Raised when an armed or active session configuration is mutated."""
    pass


class BlindSubmissionImmutabilityError(Exception):
    """Raised when a locked submission is updated or deleted."""
    pass


class BlindEngineeringSession(Base):
    """
    Authoritative Blind Engineering Session Entity.
    Acts as an information-governance boundary over existing engineering entities.
    """
    __tablename__ = "blind_engineering_sessions"
    __table_args__ = (
        Index("ix_blind_sessions_team_created", "team_id", "created_at"),
        Index("ix_blind_sessions_user_created", "created_by_user_id", "created_at"),
        Index("ix_blind_sessions_status", "status"),
        Index("ix_blind_sessions_session_hash", "session_hash"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID_TYPE, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    status = Column(String(32), nullable=False, default=BlindSessionStatus.DRAFT.value)
    name = Column(String(255), nullable=False)

    root_entity_type = Column(String(64), nullable=False)
    root_entity_id = Column(String(128), nullable=False)

    hidden_outcome_type = Column(String(64), nullable=False)
    hidden_outcome_id = Column(String(128), nullable=False)

    configuration = Column(JSON_TYPE, nullable=False, default=dict)
    session_hash = Column(String(64), nullable=False)
    visible_context_hash = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    revealed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    aborted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    submissions = relationship(
        "BlindSubmission",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="BlindSubmission.submitted_at",
    )
    comparisons = relationship(
        "BlindComparisonResult",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="BlindComparisonResult.computed_at",
    )


class BlindSubmission(Base):
    """
    Immutable Blind Engineering Submission.
    Stores the evaluator's prediction/decision with deterministic cryptographic identity.
    """
    __tablename__ = "blind_submissions"
    __table_args__ = (
        Index("ix_blind_submissions_sess_user", "session_id", "submitted_by_user_id"),
        Index("ix_blind_submissions_hash", "submission_hash"),
        UniqueConstraint("session_id", name="uq_blind_session_submission"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID_TYPE, ForeignKey("blind_engineering_sessions.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID_TYPE, nullable=True)
    team_id = Column(UUID_TYPE, nullable=True)
    submitted_by_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    submission_payload = Column(JSON_TYPE, nullable=False)
    submission_hash = Column(String(64), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    status = Column(String(32), nullable=False, default="LOCKED")

    # Relationships
    session = relationship("BlindEngineeringSession", back_populates="submissions")
    comparison = relationship(
        "BlindComparisonResult",
        back_populates="submission",
        uselist=False,
        cascade="all, delete-orphan",
    )


class BlindComparisonImmutabilityError(Exception):
    """Raised when a completed comparison result is updated or deleted."""
    pass


class BlindComparisonResult(Base):
    """
    First-Class Immutable Comparison Result (Phase 5.3).
    Stores deterministic comparison metrics, verdict, explanation, and hashes.
    Acts as derived engineering data over immutable prediction and authoritative outcome.
    """
    __tablename__ = "blind_comparison_results"
    __table_args__ = (
        Index("ix_blind_comparisons_session_policy", "session_id", "comparison_policy_version"),
        Index("ix_blind_comparisons_hash", "comparison_hash"),
        UniqueConstraint("session_id", "comparison_policy_version", name="uq_blind_session_comparison_policy"),
    )

    id = Column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID_TYPE, ForeignKey("blind_engineering_sessions.id", ondelete="CASCADE"), nullable=False)
    submission_id = Column(UUID_TYPE, ForeignKey("blind_submissions.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID_TYPE, nullable=True)
    team_id = Column(UUID_TYPE, nullable=True)

    outcome_identity = Column(JSON_TYPE, nullable=False)
    prediction_schema_version = Column(String(32), nullable=False, default="1")
    comparison_policy_version = Column(String(32), nullable=False, default="1")
    comparison_type = Column(String(64), nullable=False)

    verdict = Column(String(64), nullable=False)
    comparison_metrics = Column(JSON_TYPE, nullable=False)
    tolerance_applied = Column(JSON_TYPE, nullable=True)
    interpretation = Column(Text, nullable=False)
    comparison_hash = Column(String(64), nullable=False)
    computed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    session = relationship("BlindEngineeringSession", back_populates="comparisons")
    submission = relationship("BlindSubmission", back_populates="comparison")


# Immutability Event Listeners

@event.listens_for(BlindSubmission, "before_update")
def _prevent_submission_update(mapper, connection, target):
    raise BlindSubmissionImmutabilityError(
        f"BlindSubmission {target.id} is immutable and cannot be updated after submission."
    )


@event.listens_for(BlindSubmission, "before_delete")
def _prevent_submission_delete(mapper, connection, target):
    raise BlindSubmissionImmutabilityError(
        f"BlindSubmission {target.id} is immutable and cannot be deleted."
    )


@event.listens_for(BlindComparisonResult, "before_update")
def _prevent_comparison_update(mapper, connection, target):
    raise BlindComparisonImmutabilityError(
        f"BlindComparisonResult {target.id} is immutable and cannot be updated."
    )


@event.listens_for(BlindComparisonResult, "before_delete")
def _prevent_comparison_delete(mapper, connection, target):
    raise BlindComparisonImmutabilityError(
        f"BlindComparisonResult {target.id} is immutable and cannot be deleted."
    )


@event.listens_for(BlindEngineeringSession, "before_update")
def _check_session_mutation(mapper, connection, target):
    insp = inspect(target)
    config_history = insp.get_history("configuration", True)
    if config_history.has_changes():
        status_history = insp.get_history("status", True)
        old_status = status_history.deleted[0] if status_history.deleted else target.status
        if old_status not in (BlindSessionStatus.DRAFT.value, "DRAFT"):
            raise ConfigurationImmutabilityError(
                f"Blind session configuration is immutable once ARMED (status was {old_status})."
            )
