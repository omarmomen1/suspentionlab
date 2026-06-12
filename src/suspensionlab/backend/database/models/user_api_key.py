"""
backend/database/models/user_api_key.py
Named per-user API keys for programmatic access (Enterprise tier).
"""
from sqlalchemy import String, Boolean, DateTime, func, Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from suspensionlab.backend.database.core import Base


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name       = Column(String(255), nullable=False)          # e.g. "CI Pipeline", "Python Script"
    key_hash   = Column(Text, nullable=False, unique=True)    # bcrypt hash of the actual key
    key_prefix = Column(String(12), nullable=False)           # first 8 chars shown in UI
    is_active  = Column(Boolean, default=True)
    last_used  = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # None = never expires
