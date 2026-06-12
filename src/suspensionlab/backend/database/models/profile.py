from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from suspensionlab.backend.database.core import Base

JSON_TYPE = JSON().with_variant(JSONB, 'postgresql')

class VehicleProfile(Base):
    __tablename__ = "vehicle_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False, index=True)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True) # Creator
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True) # Workspace
    
    vehicle_type = Column(String, default="QUARTER_CAR") # e.g. QUARTER_CAR, HALF_CAR, FULL_CAR
    params = Column(JSON_TYPE, nullable=False)
    
    # Lineage tracking (Git for setups)
    version = Column(Integer, default=1, nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("vehicle_profiles.id", ondelete="SET NULL"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
