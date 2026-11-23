"""
backend/database/models/scim_group.py
=====================================
SCIM 2.0 Group model and group membership mapping to Teams and Roles.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Table,
    func,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from suspensionlab.backend.database.core import Base

# Association table between SCIM groups and Users
scim_group_members = Table(
    "scim_group_members",
    Base.metadata,
    Column("group_id", PG_UUID(as_uuid=True), ForeignKey("scim_groups.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


class SCIMGroup(Base):
    __tablename__ = "scim_groups"
    __table_args__ = (
        Index("ix_scim_groups_org_display", "organization_id", "display_name", unique=True),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    display_name = Column(String(255), nullable=False)
    external_id = Column(String(255), nullable=True)

    # Dynamic mapping: Map IdP group to a SuspensionLab team and/or seat role
    team_id = Column(PG_UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    target_role = Column(String(50), default="Engineer", nullable=True)  # Admin, Engineer, Crew, Viewer

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="scim_groups", lazy="selectin")
    team = relationship("Team", lazy="selectin")
    members = relationship("User", secondary=scim_group_members, lazy="selectin", backref="scim_groups")
