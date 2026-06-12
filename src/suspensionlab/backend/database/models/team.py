"""
backend/database/models/team.py
Team model for Enterprise workspace sharing.
"""
from sqlalchemy import String, DateTime, func, Column, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from suspensionlab.backend.database.core import Base


class Team(Base):
    __tablename__ = "teams"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name       = Column(String(255), nullable=False)
    slug       = Column(String(255), unique=True, index=True, nullable=False)
    owner_id   = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan       = Column(String(20), default="ENTERPRISE", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
