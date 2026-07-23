"""
backend/database/models/team.py
Team model for Enterprise workspace sharing.
"""
from sqlalchemy import String, DateTime, func, Column, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from suspensionlab.backend.database.core import Base


class Team(Base):
    __tablename__ = "teams"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name       = Column(String(255), nullable=False)
    slug       = Column(String(255), unique=True, index=True, nullable=False)
    owner_id   = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan       = Column(String(20), default="ENTERPRISE", nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    members = relationship("User", back_populates="team", foreign_keys="[User.team_id]")
    jobs = relationship("JobRecord", back_populates="team")
    profiles = relationship("VehicleProfile", back_populates="team")
    sessions = relationship("SimSession", back_populates="team")
