"""
backend/database/models/usage_counter.py
=========================================
Durable monthly simulation-usage counters (Pass B, Tier A4 fallback).

Redis is the primary metering store; when Redis is unavailable the meter fell
back to 0/500 and stopped reflecting actual runs. This table is the DB
fallback so usage is always recorded and readable.
"""
from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from suspensionlab.backend.database.core import Base


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    user_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    month = Column(String(7), primary_key=True)  # "YYYY-MM" (UTC)
    count = Column(Integer, nullable=False, default=0)
