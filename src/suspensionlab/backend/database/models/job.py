from sqlalchemy.sql import func
from sqlalchemy import Column, Enum, CheckConstraint, String, DateTime, Text, Index, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from suspensionlab.backend.database.core import Base
from sqlalchemy.orm import relationship

JSON_TYPE = JSON().with_variant(JSONB, 'postgresql')

class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_user_status", "user_id", "status"),
        Index("ix_jobs_started_at",  "started_at"),
        Index("ix_jobs_team_id", "team_id"),
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    
    job_type = Column(String, nullable=False, default="OPTIMIZE_QUARTER")
    status = Column(String, CheckConstraint("status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELED')", name="chk_job_status"), default="PENDING")
    
    params = Column(JSON_TYPE)
    profile = Column(JSON_TYPE)
    result = Column(JSON_TYPE, nullable=True)
    
    error = Column(Text, nullable=True)
    schema_version = Column(Integer, default=1)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_heartbeat = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="jobs")
    team = relationship("Team", back_populates="jobs")
    session = relationship("SimSession", back_populates="jobs")
