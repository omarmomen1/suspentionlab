from sqlalchemy import Column, String, DateTime, JSON
from datetime import datetime
from suspensionlab.backend.database.core import Base

class LemonEvent(Base):
    __tablename__ = "lemon_events"
    
    event_id = Column(String, primary_key=True, index=True)
    payload = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
