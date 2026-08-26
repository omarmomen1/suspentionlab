"""
backend/database/models/webhook.py
===================================
Outbound webhooks (Tier C2): let customers pipe simulation lifecycle events
into their own pipelines (CI rigs, data lakes, Slack bots).

Endpoints are per-user; deliveries are HMAC-SHA256 signed so receivers can
verify authenticity without trusting the transport.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from suspensionlab.backend.database.core import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        Index("ix_webhooks_user_active", "user_id", "is_active"),
    )

    id         = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    url        = Column(String(2048), nullable=False)
    secret     = Column(Text, nullable=False)          # hex secret for HMAC signatures
    # Comma-separated subscribed events, e.g. "job.completed,job.failed"
    events     = Column(String(255), nullable=False, default="job.completed,job.failed")
    description = Column(String(255), nullable=True)
    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
