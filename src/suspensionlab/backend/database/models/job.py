from sqlalchemy import Column, String, DateTime, Text, Index, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from suspensionlab.backend.database.core import Base

JSON_TYPE = JSON().with_variant(JSONB, 'postgresql')

class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_user_status", "user_id", "status"),
        Index("ix_jobs_started_at",  "started_at"),
        Index("ix_jobs_team_id", "team_id"),
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    
    job_type = Column(String, nullable=False, default="OPTIMIZE_QUARTER")
    status = Column(String, default="PENDING")
    
    params = Column(JSON_TYPE)
    profile = Column(JSON_TYPE)
    result = Column(JSON_TYPE, nullable=True)
    
    error = Column(Text, nullable=True)
    schema_version = Column(Integer, default=1)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_heartbeat = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
