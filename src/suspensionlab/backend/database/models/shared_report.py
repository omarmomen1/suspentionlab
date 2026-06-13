"""
Shared Report DB model — stores simulation results for public sharing.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from suspensionlab.backend.database.core import Base


class SharedReport(Base):
    __tablename__ = "shared_reports"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    token = Column(String(36), unique=True, nullable=False, index=True,
                   default=lambda: str(uuid.uuid4()))
    simulation_type = Column(String(50), nullable=False, default="quarter_car")
    params = Column(JSON, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    view_count = Column(String, default="0")  # stored as string for SQLite compat
    is_public = Column(Boolean, default=True, nullable=False)
    title = Column(String(200), default="", nullable=False)
    notes = Column(String(2000), default="", nullable=False)
