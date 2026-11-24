"""
backend/database/models/webhook.py
===================================
Outbound webhooks (Tier C2): let customers pipe simulation lifecycle events
into their own pipelines (CI rigs, data lakes, Slack bots).

Endpoints are per-user; deliveries are HMAC-SHA256 signed so receivers can
verify authenticity without trusting the transport.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from suspensionlab.backend.database.core import Base


def _get_encryption_key() -> bytes:
    key_src = os.getenv("SECRET_KEY")
    if not key_src:
        key_src = os.getenv("JWT_SECRET_KEY")
    if not key_src:
        raw_keys = os.getenv("JWT_KEYS")
        if raw_keys:
            try:
                parsed = json.loads(raw_keys)
                if isinstance(parsed, dict) and parsed:
                    key_src = next(iter(parsed.values()))
            except Exception:
                pass
    if not key_src:
        raise RuntimeError("CRITICAL: SECRET_KEY or JWT_SECRET_KEY is required for webhook encryption.")
    derived = hashlib.sha256(key_src.encode()).digest()
    return base64.urlsafe_b64encode(derived)


class EncryptedSecret(TypeDecorator):
    """Encrypts webhook secret at rest; decrypts transparently on read. Preserves plaintext compatibility."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str) and value.startswith("enc:"):
            return value
        try:
            from cryptography.fernet import Fernet
            f = Fernet(_get_encryption_key())
            enc_bytes = f.encrypt(str(value).encode("utf-8"))
            return f"enc:{enc_bytes.decode('utf-8')}"
        except Exception:
            return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str) and value.startswith("enc:"):
            try:
                from cryptography.fernet import Fernet
                f = Fernet(_get_encryption_key())
                token = value.removeprefix("enc:").encode("utf-8")
                return f.decrypt(token).decode("utf-8")
            except Exception:
                return value
        return value


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
    secret     = Column(EncryptedSecret, nullable=False)          # encrypted at rest; transparent on read
    # Comma-separated subscribed events, e.g. "job.completed,job.failed"
    events     = Column(String(255), nullable=False, default="job.completed,job.failed")
    description = Column(String(255), nullable=True)
    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
