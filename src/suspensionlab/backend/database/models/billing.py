from sqlalchemy.sql import func
from sqlalchemy import Column, String, DateTime, JSON
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from suspensionlab.backend.database.core import Base

JSON_TYPE = JSON().with_variant(JSONB, 'postgresql')

class LemonEvent(Base):
    __tablename__ = "lemon_events"
    
    event_id = Column(String, primary_key=True)
    payload = Column(JSON_TYPE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class StripeEvent(Base):
    __tablename__ = "stripe_events"
    
    event_id = Column(String, primary_key=True)
    payload = Column(JSON_TYPE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

