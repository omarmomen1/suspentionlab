from sqlalchemy.sql import func
from sqlalchemy import Column, CheckConstraint, String, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from suspensionlab.backend.database.core import Base
from sqlalchemy.orm import relationship

JSON_TYPE = JSON().with_variant(JSONB, 'postgresql')

class VehicleProfile(Base):
    __tablename__ = "vehicle_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False, index=True)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True) # Creator
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True) # Workspace
    
    vehicle_type = Column(String, CheckConstraint("vehicle_type IN ('QUARTER_CAR', 'HALF_CAR', 'FULL_CAR')", name="chk_vehicle_type"), default="QUARTER_CAR")
    params = Column(JSON_TYPE, nullable=False)
    
    # Lineage tracking (Git for setups)
    version = Column(Integer, default=1, nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("vehicle_profiles.id", ondelete="SET NULL"), nullable=True)
    
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="profiles")
    team = relationship("Team", back_populates="profiles")
