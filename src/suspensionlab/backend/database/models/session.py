from sqlalchemy.sql import func
from sqlalchemy import Column, Index, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from suspensionlab.backend.database.core import Base

JSON_TYPE = JSON().with_variant(JSONB, 'postgresql')

class SimSession(Base):
    # Relationships
    owner = relationship('User', back_populates='sessions')
    team = relationship('Team', back_populates='sessions')
    jobs = relationship('JobRecord', back_populates='session')
    comments = relationship('SessionComment', back_populates='session')

    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    
    name = Column(String(255), nullable=True)
    params_snapshot = Column(JSON_TYPE, nullable=True)
    
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SessionComment(Base):
    # Relationships
    session = relationship('SimSession', back_populates='comments')
    author = relationship('User')

    __tablename__ = "session_comments"
    __table_args__ = (Index("ix_session_comments_author_id", "author_id"),)
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=False, index=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    
    content = Column(Text, nullable=False)
    chart_region = Column(JSON_TYPE, nullable=True)  # x-range bounds
    
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
