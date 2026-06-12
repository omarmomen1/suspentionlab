from sqlalchemy import Column, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from suspensionlab.backend.database.core import Base

JSON_TYPE = JSON().with_variant(JSONB, 'postgresql')

class SimSession(Base):
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True)
    
    name = Column(String(255), nullable=True)
    params_snapshot = Column(JSON_TYPE, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class SessionComment(Base):
    __tablename__ = "session_comments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    content = Column(Text, nullable=False)
    chart_region = Column(JSON_TYPE, nullable=True)  # x-range bounds
    
    created_at = Column(DateTime, default=datetime.utcnow)
