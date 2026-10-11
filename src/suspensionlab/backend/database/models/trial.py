"""
backend/database/models/trial.py
================================
7-Day Evaluation / Trial Organization Model for SuspensionLab PRO.
Tracks trial lifecycle, server-authoritative expiration, and resource quotas:
- 7-day duration (server UTC time authoritative)
- 50 simulation/experiment executions limit
- 1 vehicle/project limit
- 50 MB telemetry storage limit
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    UUID,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from suspensionlab.backend.database.core import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Trial(Base):
    __tablename__ = "trials"
    __table_args__ = (
        Index("ix_trials_org_id", "organization_id", unique=True),
        Index("ix_trials_user_id", "user_id"),
        Index("ix_trials_status", "status"),
        Index("ix_trials_expires_at", "expires_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Server-Authoritative Lifecycle Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False)  # ACTIVE | EXPIRED | CONVERTED | CANCELLED

    # Quotas & Limits (Configurable)
    simulation_run_limit = Column(Integer, default=50, nullable=False)
    simulation_run_count = Column(Integer, default=0, nullable=False)

    telemetry_storage_limit_bytes = Column(BigInteger, default=52428800, nullable=False)  # 50 MB
    telemetry_storage_used_bytes = Column(BigInteger, default=0, nullable=False)

    vehicle_project_limit = Column(Integer, default=1, nullable=False)
    vehicle_project_count = Column(Integer, default=0, nullable=False)

    # Evaluation Metadata
    evaluation_title = Column(String(255), default="7-Day SuspensionLab PRO Evaluation", nullable=False)
    contact_email = Column(String(255), nullable=True)
    metadata_json = Column(JSON_TYPE, nullable=True)

    # Soft-deletion & Cleanup tracking
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", backref="trial_record")
    user = relationship("User", backref="trial_records")

    @property
    def trial_id(self) -> str:
        """Convenience synonym for id string."""
        return str(self.id)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """
        Determines whether the trial has expired using server-side time as the authority.
        Never trusts client or browser timestamps.
        """
        if self.status in ("EXPIRED", "CONVERTED", "CANCELLED"):
            return True

        now_utc = now or datetime.now(timezone.utc)
        target_exp = self.expires_at
        if target_exp is not None and target_exp.tzinfo is None:
            target_exp = target_exp.replace(tzinfo=timezone.utc)

        if target_exp is not None and now_utc >= target_exp:
            self.status = "EXPIRED"
            return True

        return False

    def days_remaining(self, now: Optional[datetime] = None) -> float:
        """Returns floating-point days remaining until expiration based on server time."""
        now_utc = now or datetime.now(timezone.utc)
        target_exp = self.expires_at
        if target_exp is not None and target_exp.tzinfo is None:
            target_exp = target_exp.replace(tzinfo=timezone.utc)

        if target_exp is None or now_utc >= target_exp:
            return 0.0

        delta = target_exp - now_utc
        return round(max(0.0, delta.total_seconds() / 86400.0), 2)

    def day_number(self, now: Optional[datetime] = None) -> int:
        """Returns 1-based current day of the 7-day evaluation (e.g., 1 for first 24 hours)."""
        now_utc = now or datetime.now(timezone.utc)
        c_at = self.created_at
        if c_at is not None and c_at.tzinfo is None:
            c_at = c_at.replace(tzinfo=timezone.utc)
        if not c_at:
            return 1
        elapsed_seconds = max(0.0, (now_utc - c_at).total_seconds())
        day = int(elapsed_seconds // 86400.0) + 1
        return min(7, max(1, day))

    def to_dict(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Returns serializable trial status summary."""
        expired = self.is_expired(now)
        day_num = self.day_number(now)
        return {
            "trial_id": str(self.id),
            "organization_id": str(self.organization_id),
            "user_id": str(self.user_id),
            "status": "EXPIRED" if expired else self.status,
            "is_expired": expired,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "days_remaining": self.days_remaining(now),
            "day_number": day_num,
            "day_label": f"Day {day_num} of 7",
            "simulation_run_limit": self.simulation_run_limit,
            "simulation_run_count": self.simulation_run_count,
            "simulations_remaining": max(0, self.simulation_run_limit - self.simulation_run_count),
            "telemetry_storage_limit_bytes": self.telemetry_storage_limit_bytes,
            "telemetry_storage_used_bytes": self.telemetry_storage_used_bytes,
            "telemetry_storage_remaining_bytes": max(0, self.telemetry_storage_limit_bytes - self.telemetry_storage_used_bytes),
            "vehicle_project_limit": self.vehicle_project_limit,
            "vehicle_project_count": self.vehicle_project_count,
            "vehicles_remaining": max(0, self.vehicle_project_limit - self.vehicle_project_count),
            "evaluation_title": self.evaluation_title,
            "contact_email": self.contact_email,
        }
