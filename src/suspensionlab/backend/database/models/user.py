"""
backend/database/models/user.py  (upgraded)
Added: email, password_hash, name, plan, team_id, billing_customer_id, billing_subscription_id
"""
from sqlalchemy import String, Boolean, DateTime, func, Column, Text, ForeignKey
from sqlalchemy import UUID
from sqlalchemy.orm import synonym, relationship
import uuid
from suspensionlab.backend.database.core import Base
from suspensionlab.shared.models import PlanTier


from sqlalchemy import Index

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email",        "email",   unique=True),
        Index("ix_users_api_key",      "api_key", unique=True),
        Index("ix_users_billing_cust",   "billing_customer_id"),
        Index("ix_users_team_id",      "team_id"),
    )

    id                     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email                  = Column(String(255), nullable=False)
    password_hash          = Column(Text, nullable=False)
    name                   = Column(String(255), nullable=True)

    # Billing / plan
    plan                   = Column(String(20), default=PlanTier.FREE, nullable=False)  # FREE | PRO | ENTERPRISE
    billing_customer_id    = Column(String(255), nullable=True)
    billing_subscription_id = Column(String(255), nullable=True)
    trial_ends_at          = Column(DateTime(timezone=True), nullable=True)

    # Legacy single API key (kept for backwards-compat with existing rows)
    api_key                = Column(String(255), nullable=True)

    # License key for PRO access
    gumroad_license_key    = Column(String(255), unique=True, nullable=True)

    # Onboarding
    onboarding_complete    = Column(Boolean, default=False)
    
    # Admin status
    is_admin               = Column(Boolean, default=False)

    # Team membership (null = personal account)
    team_id                = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL", use_alter=True), nullable=True)
    team_role              = Column(String(20), default="Viewer", nullable=True) # Owner | Admin | Viewer

    deleted_at             = Column(DateTime(timezone=True), nullable=True)
    created_at             = Column(DateTime(timezone=True), server_default=func.now())
    updated_at             = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    team = relationship("Team", back_populates="members", foreign_keys="[User.team_id]")
    jobs = relationship("JobRecord", back_populates="user")
    profiles = relationship("VehicleProfile", back_populates="user")
    sessions = relationship("SimSession", back_populates="owner")
