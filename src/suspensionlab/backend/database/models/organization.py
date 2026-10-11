"""
backend/database/models/organization.py
=======================================
Top-level multi-tenant Organization model for SuspensionLab PRO Enterprise.
Encompasses Teams, Users, Billing, Data Policies, Regional Residency, SAML 2.0, and SCIM.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    func,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from suspensionlab.backend.database.core import Base
from suspensionlab.shared.models import PlanTier


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        Index("ix_orgs_slug", "slug", unique=True),
        Index("ix_orgs_billing_customer", "billing_customer_id"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)

    # Billing & Subscription
    plan = Column(String(20), default=PlanTier.ENTERPRISE, nullable=False)
    billing_customer_id = Column(String(255), nullable=True)
    billing_subscription_id = Column(String(255), nullable=True)
    subscription_status = Column(String(50), default="active", nullable=False)
    max_seats = Column(Integer, default=50, nullable=False)
    max_teams = Column(Integer, default=10, nullable=False)

    # Data Residency & Governance
    data_region = Column(String(32), default="eu-central", nullable=False)  # eu-central, us-east, etc.
    data_retention_days = Column(Integer, default=365, nullable=False)       # Default retention for general records
    telemetry_retention_days = Column(Integer, default=90, nullable=False)   # High-frequency telemetry retention
    audit_retention_days = Column(Integer, default=2555, nullable=False)     # Audit logs (7 years for compliance)
    auto_archive_enabled = Column(Boolean, default=True, nullable=False)

    # Allowed Authentication Providers (comma-separated: "local,oidc,saml")
    allowed_auth_providers = Column(String(255), default="local,oidc,saml", nullable=False)

    # SAML 2.0 Enterprise Configuration
    saml_enabled = Column(Boolean, default=False, nullable=False)
    saml_idp_entity_id = Column(String(512), nullable=True)
    saml_idp_sso_url = Column(String(1024), nullable=True)
    saml_idp_x509_cert = Column(Text, nullable=True)
    saml_sp_entity_id = Column(String(512), nullable=True)

    # SCIM 2.0 Enterprise Provisioning Configuration
    scim_enabled = Column(Boolean, default=False, nullable=False)
    scim_token_prefix = Column(String(32), nullable=True)
    scim_token_hash = Column(String(255), nullable=True)
    scim_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps & Soft-Delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    teams = relationship("Team", back_populates="organization", cascade="all, delete-orphan")
    users = relationship("User", back_populates="organization")
    invitations = relationship("OrganizationInvitation", back_populates="organization", cascade="all, delete-orphan")
    scim_groups = relationship("SCIMGroup", back_populates="organization", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="organization")

    def is_active(self) -> bool:
        return self.deleted_at is None and self.subscription_status in ("active", "trialing")
