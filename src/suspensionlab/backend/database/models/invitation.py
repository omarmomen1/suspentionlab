"""
backend/database/models/invitation.py
=====================================
Organization and Team Invitation model for SuspensionLab PRO Enterprise.
Enforces cryptographic token verification, explicit acceptance lifecycle,
expiration, and audit provenance.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from suspensionlab.backend.database.core import Base


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        Index("ix_org_invites_token_hash", "token_hash", unique=True),
        Index("ix_org_invites_org_status", "organization_id", "status"),
        Index("ix_org_invites_email_status", "invitee_email", "status"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invited_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invitee_email = Column(String(255), nullable=False)
    role = Column(String(32), default="MEMBER", nullable=False)  # ORG_ADMIN, BILLING_ADMIN, MEMBER
    team_role = Column(String(20), default="Engineer", nullable=True)  # Admin, Engineer, Crew, Viewer

    # Cryptographic Token Security
    token_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 hex digest
    token_prefix = Column(String(16), nullable=False)            # First 8-12 chars for display

    # Lifecycle State
    status = Column(String(20), default="PENDING", nullable=False)  # PENDING, ACCEPTED, REJECTED, REVOKED, EXPIRED
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="invitations")
    team = relationship("Team")
    invited_by = relationship("User", foreign_keys=[invited_by_user_id])
    accepted_by = relationship("User", foreign_keys=[accepted_by_user_id])

    def is_valid_for_acceptance(self, user_email: str) -> tuple[bool, str]:
        """Check if invitation can be accepted by the current user."""
        if self.status != "PENDING":
            return False, f"Invitation is not pending (current status: {self.status})."
        
        now = datetime.now(timezone.utc)
        if self.expires_at.tzinfo is None:
            expires = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires = self.expires_at
            
        if now > expires:
            return False, "Invitation has expired."
            
        if user_email.lower().strip() != self.invitee_email.lower().strip():
            return False, f"Invitation is intended for '{self.invitee_email}', not '{user_email}'."
            
        return True, ""
