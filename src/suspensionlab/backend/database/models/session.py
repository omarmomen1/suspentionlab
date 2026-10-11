from sqlalchemy.sql import func
from sqlalchemy import Column, Index, String, DateTime, Text, ForeignKey, JSON, Uuid
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from suspensionlab.backend.database.core import Base

from sqlalchemy.dialects.postgresql import JSONB

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

class SimSession(Base):
    __tablename__ = "sessions"
    
    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    owner_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    
    name = Column(String(255), nullable=True)
    params_snapshot = Column(JSON_TYPE, nullable=True)
    
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    owner = relationship('User', back_populates='sessions')
    team = relationship('Team', back_populates='sessions')
    jobs = relationship('JobRecord', back_populates='session')
    comments = relationship('SessionComment', back_populates='session', cascade="all, delete-orphan")

class SessionComment(Base):
    __tablename__ = "session_comments"
    __table_args__ = (
        Index("ix_session_comments_author_id", "author_id"),
        Index("ix_session_comments_session_ts", "session_id", "created_at"),
    )
    
    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    session_id = Column(Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    content = Column(Text, nullable=False)
    chart_region = Column(JSON_TYPE, nullable=True)  # x-range bounds
    
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship('SimSession', back_populates='comments')
    author = relationship('User')
