"""
backend/database/models/revoked_token.py
=========================================
Persistent JTI revocation registry (Pass B).

The in-memory registry and Redis are the fast paths; this table is the durable
fallback so revocation still fails closed when Redis is unavailable. Rows are
written best-effort on every blacklist operation and can be purged once the
underlying token expires.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

from suspensionlab.backend.database.core import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti = Column(String(255), primary_key=True)
    reason = Column(String(64), nullable=True)
    revoked_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # token exp; row is dead weight after this
