"""
backend/database/models/team.py
Team model for Enterprise workspace sharing.
"""
from sqlalchemy import String, DateTime, func, Column, Text, ForeignKey, Uuid
from sqlalchemy.orm import relationship
import uuid
from suspensionlab.backend.database.core import Base


class Team(Base):
    __tablename__ = "teams"

    id         = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name       = Column(String(255), nullable=False)
    slug       = Column(String(255), unique=True, index=True, nullable=False)
    owner_id   = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan       = Column(String(20), default="ENTERPRISE", nullable=False)
    # Data residency (Tier C1): which regional stack holds this team's data.
    data_region = Column(String(32), nullable=False, server_default="eu-central")
    # Organization Hierarchy (Enterprise Multi-Tenancy)
    organization_id = Column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="teams")
    members = relationship("User", back_populates="team", foreign_keys="[User.team_id]")
    jobs = relationship("JobRecord", back_populates="team")
    profiles = relationship("VehicleProfile", back_populates="team")
    sessions = relationship("SimSession", back_populates="team")
