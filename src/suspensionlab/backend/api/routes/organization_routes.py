"""
backend/api/routes/organization_routes.py
=========================================
Enterprise Organization Management Routes (Multi-Tenancy, Teams, Billing, Data Policies, Regions).
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.invitation import OrganizationInvitation
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.security.auth import UserContext, verify_api_key, require_permission
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.security.jwt_utils import hash_password
import hashlib

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateOrganizationRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255)
    plan: str = Field(default="ENTERPRISE")
    data_region: str = Field(default="eu-central")
    max_seats: int = Field(default=50, ge=1, le=10000)
    data_retention_days: int = Field(default=365, ge=30, le=3650)
    telemetry_retention_days: int = Field(default=90, ge=7, le=1825)


class UpdateOrganizationRequest(BaseModel):
    name: Optional[str] = None
    data_region: Optional[str] = None
    data_retention_days: Optional[int] = Field(None, ge=30, le=3650)
    telemetry_retention_days: Optional[int] = Field(None, ge=7, le=1825)
    audit_retention_days: Optional[int] = Field(None, ge=365, le=7300)
    auto_archive_enabled: Optional[bool] = None
    allowed_auth_providers: Optional[str] = None
    saml_enabled: Optional[bool] = None
    saml_idp_entity_id: Optional[str] = None
    saml_idp_sso_url: Optional[str] = None
    saml_idp_x509_cert: Optional[str] = None
    saml_sp_entity_id: Optional[str] = None
    scim_enabled: Optional[bool] = None


class CreateOrgTeamRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255)
    plan: str = Field(default="ENTERPRISE")
    data_region: Optional[str] = None


class AddOrgMemberRequest(BaseModel):
    email: str
    name: Optional[str] = None
    org_role: str = Field(default="MEMBER")  # ORG_ADMIN, BILLING_ADMIN, MEMBER
    team_id: Optional[str] = None
    team_role: Optional[str] = Field(default="Engineer")  # Admin, Engineer, Crew, Viewer


class CreateInvitationRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    role: str = Field(default="MEMBER")  # ORG_ADMIN, BILLING_ADMIN, MEMBER
    team_id: Optional[str] = None
    team_role: Optional[str] = Field(default="Engineer")  # Admin, Engineer, Crew, Viewer
    expires_days: int = Field(default=7, ge=1, le=30)


class InvitationResponse(BaseModel):
    id: str
    organization_id: str
    team_id: Optional[str] = None
    invitee_email: str
    role: str
    team_role: Optional[str] = None
    token: Optional[str] = None
    token_prefix: str
    status: str
    expires_at: datetime
    created_at: Optional[datetime] = None


class TransferOwnershipRequest(BaseModel):
    target_user_id: str


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    subscription_status: str
    data_region: str
    data_retention_days: int
    telemetry_retention_days: int
    audit_retention_days: int
    auto_archive_enabled: bool
    allowed_auth_providers: str
    saml_enabled: bool
    saml_idp_entity_id: Optional[str]
    saml_idp_sso_url: Optional[str]
    saml_sp_entity_id: Optional[str]
    scim_enabled: bool
    scim_token_prefix: Optional[str]
    scim_token_expires_at: Optional[datetime]
    created_at: Optional[datetime]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    req: CreateOrganizationRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Create a new top-level enterprise Organization."""
    # Check if slug already taken
    if user.is_trial or getattr(user, "plan", "") == "TRIAL":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trial evaluation accounts cannot create additional organizations.",
        )

    existing = (
        await db.execute(select(Organization).where(Organization.slug == req.slug.lower()))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"Organization slug '{req.slug}' is already taken.")

    # Safe Organization Creation: A user already assigned to Organization A must not silently become a member of Organization B
    current_user = (
        await db.execute(select(User).where(User.id == uuid.UUID(user.user_id)))
    ).scalar_one_or_none()
    if current_user and current_user.organization_id is not None:
        existing_org = (
            await db.execute(select(Organization).where(Organization.id == current_user.organization_id, Organization.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if existing_org:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User already belongs to Organization '{existing_org.name}'. You must explicitly leave or transfer before creating a new organization."
            )

    org = Organization(
        name=req.name,
        slug=req.slug.lower(),
        plan=req.plan.upper(),
        data_region=req.data_region,
        max_seats=req.max_seats,
        data_retention_days=req.data_retention_days,
        telemetry_retention_days=req.telemetry_retention_days,
        saml_sp_entity_id=f"https://suspensionlab.pro/saml/sp/{req.slug.lower()}",
    )
    db.add(org)
    await db.flush()

    if current_user:
        current_user.organization_id = org.id
        current_user.org_role = "ORG_ADMIN"

    # Record audit event
    audit_ev = AuditLog(
        event="ORGANIZATION_CREATED",
        user_id=uuid.UUID(user.user_id),
        organization_id=org.id,
        event_data={"name": org.name, "slug": org.slug, "plan": org.plan},
    )
    db.add(audit_ev)

    await db.commit()
    await db.refresh(org)
    return OrganizationResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        subscription_status=org.subscription_status,
        data_region=org.data_region,
        data_retention_days=org.data_retention_days,
        telemetry_retention_days=org.telemetry_retention_days,
        audit_retention_days=org.audit_retention_days,
        auto_archive_enabled=org.auto_archive_enabled,
        allowed_auth_providers=org.allowed_auth_providers,
        saml_enabled=org.saml_enabled,
        saml_idp_entity_id=org.saml_idp_entity_id,
        saml_idp_sso_url=org.saml_idp_sso_url,
        saml_sp_entity_id=org.saml_sp_entity_id,
        scim_enabled=org.scim_enabled,
        scim_token_prefix=org.scim_token_prefix,
        scim_token_expires_at=org.scim_token_expires_at,
        created_at=org.created_at,
    )


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Retrieve organization configuration and policy."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    org = (await db.execute(select(Organization).where(Organization.id == org_uuid))).scalar_one_or_none()
    if not org or org.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # Cross-tenant isolation check: user must belong to this org or be a platform admin
    if not user.is_admin and user.organization_id != str(org.id):
        raise HTTPException(status_code=403, detail="Access Denied: You do not have permission to view this organization.")

    return OrganizationResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        subscription_status=org.subscription_status,
        data_region=org.data_region,
        data_retention_days=org.data_retention_days,
        telemetry_retention_days=org.telemetry_retention_days,
        audit_retention_days=org.audit_retention_days,
        auto_archive_enabled=org.auto_archive_enabled,
        allowed_auth_providers=org.allowed_auth_providers,
        saml_enabled=org.saml_enabled,
        saml_idp_entity_id=org.saml_idp_entity_id,
        saml_idp_sso_url=org.saml_idp_sso_url,
        saml_sp_entity_id=org.saml_sp_entity_id,
        scim_enabled=org.scim_enabled,
        scim_token_prefix=org.scim_token_prefix,
        scim_token_expires_at=org.scim_token_expires_at,
        created_at=org.created_at,
    )


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: str,
    req: UpdateOrganizationRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Update organization settings, policies, regional residency, SAML, or SCIM."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    org = (await db.execute(select(Organization).where(Organization.id == org_uuid))).scalar_one_or_none()
    if not org or org.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # Authorization: Must be ORG_ADMIN or platform admin
    if not user.is_admin and (user.organization_id != str(org.id) or user.org_role != "ORG_ADMIN"):
        raise HTTPException(status_code=403, detail="Permission Denied: Only ORG_ADMIN can modify organization settings.")

    if req.name is not None:
        org.name = req.name
    if req.data_region is not None:
        org.data_region = req.data_region
    if req.data_retention_days is not None:
        org.data_retention_days = req.data_retention_days
    if req.telemetry_retention_days is not None:
        org.telemetry_retention_days = req.telemetry_retention_days
    if req.audit_retention_days is not None:
        org.audit_retention_days = req.audit_retention_days
    if req.auto_archive_enabled is not None:
        org.auto_archive_enabled = req.auto_archive_enabled
    if req.allowed_auth_providers is not None:
        org.allowed_auth_providers = req.allowed_auth_providers
    if req.saml_enabled is not None:
        org.saml_enabled = req.saml_enabled
    if req.saml_idp_entity_id is not None:
        org.saml_idp_entity_id = req.saml_idp_entity_id
    if req.saml_idp_sso_url is not None:
        org.saml_idp_sso_url = req.saml_idp_sso_url
    if req.saml_idp_x509_cert is not None:
        org.saml_idp_x509_cert = req.saml_idp_x509_cert
    if req.saml_sp_entity_id is not None:
        org.saml_sp_entity_id = req.saml_sp_entity_id
    if req.scim_enabled is not None:
        org.scim_enabled = req.scim_enabled

    await db.commit()
    await db.refresh(org)

    return OrganizationResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        subscription_status=org.subscription_status,
        data_region=org.data_region,
        data_retention_days=org.data_retention_days,
        telemetry_retention_days=org.telemetry_retention_days,
        audit_retention_days=org.audit_retention_days,
        auto_archive_enabled=org.auto_archive_enabled,
        allowed_auth_providers=org.allowed_auth_providers,
        saml_enabled=org.saml_enabled,
        saml_idp_entity_id=org.saml_idp_entity_id,
        saml_idp_sso_url=org.saml_idp_sso_url,
        saml_sp_entity_id=org.saml_sp_entity_id,
        scim_enabled=org.scim_enabled,
        scim_token_prefix=org.scim_token_prefix,
        scim_token_expires_at=org.scim_token_expires_at,
        created_at=org.created_at,
    )


@router.get("/{org_id}/teams")
async def list_organization_teams(
    org_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """List all teams nested under an organization."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    if not user.is_admin and user.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Access Denied to organization teams.")

    teams_res = await db.execute(
        select(Team).where(Team.organization_id == org_uuid, Team.deleted_at == None)
    )
    teams = teams_res.scalars().all()
    return {
        "organization_id": org_id,
        "teams": [
            {
                "id": str(t.id),
                "name": t.name,
                "slug": t.slug,
                "plan": t.plan,
                "data_region": t.data_region,
                "created_at": t.created_at,
            }
            for t in teams
        ]
    }


@router.post("/{org_id}/teams", status_code=status.HTTP_201_CREATED)
async def create_organization_team(
    org_id: str,
    req: CreateOrgTeamRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Create a new team under an organization."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    if not user.is_admin and (user.organization_id != org_id or user.org_role != "ORG_ADMIN"):
        raise HTTPException(status_code=403, detail="Only ORG_ADMIN can create teams in this organization.")

    org = (await db.execute(select(Organization).where(Organization.id == org_uuid))).scalar_one_or_none()
    if not org or org.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # Check slug uniqueness
    existing = (await db.execute(select(Team).where(Team.slug == req.slug.lower()))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"Team slug '{req.slug}' is already taken.")

    team = Team(
        name=req.name,
        slug=req.slug.lower(),
        owner_id=uuid.UUID(user.user_id),
        organization_id=org_uuid,
        plan=req.plan or org.plan,
        data_region=req.data_region or org.data_region,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)

    return {
        "id": str(team.id),
        "organization_id": str(team.organization_id),
        "name": team.name,
        "slug": team.slug,
        "plan": team.plan,
        "data_region": team.data_region,
        "created_at": team.created_at,
    }


@router.get("/{org_id}/members")
async def list_organization_members(
    org_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """List all user members of an organization."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    if not user.is_admin and user.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Access Denied to organization members.")

    members_res = await db.execute(
        select(User).where(User.organization_id == org_uuid, User.deleted_at == None)
    )
    members = members_res.scalars().all()
    return {
        "organization_id": org_id,
        "members": [
            {
                "id": str(m.id),
                "email": m.email,
                "name": m.name,
                "org_role": m.org_role,
                "team_id": str(m.team_id) if m.team_id else None,
                "team_role": m.team_role,
                "auth_provider": m.auth_provider,
                "created_at": m.created_at,
            }
            for m in members
        ]
    }


@router.post("/{org_id}/members", status_code=status.HTTP_201_CREATED)
async def add_organization_member(
    org_id: str,
    req: AddOrgMemberRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Add or invite a member to an organization and assign org/team roles."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    if not user.is_admin and (user.organization_id != org_id or user.org_role != "ORG_ADMIN"):
        raise HTTPException(status_code=403, detail="Only ORG_ADMIN can add members to this organization.")

    email = req.email.lower().strip()
    existing_user = (
        await db.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()

    team_uuid = uuid.UUID(req.team_id) if req.team_id else None

    if existing_user:
        if existing_user.organization_id is not None and existing_user.organization_id != org_uuid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already belongs to another organization. Team/org membership cannot be forcibly changed without invitation acceptance."
            )
        existing_user.organization_id = org_uuid
        existing_user.org_role = req.org_role
        if team_uuid:
            existing_user.team_id = team_uuid
            existing_user.team_role = req.team_role
        existing_user.deleted_at = None
        target_user = existing_user
    else:
        target_user = User(
            email=email,
            name=req.name,
            password_hash=hash_password(secrets.token_urlsafe(24)),
            organization_id=org_uuid,
            org_role=req.org_role,
            team_id=team_uuid,
            team_role=req.team_role,
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add(target_user)

    await db.commit()
    await db.refresh(target_user)

    return {
        "id": str(target_user.id),
        "email": target_user.email,
        "organization_id": str(target_user.organization_id),
        "org_role": target_user.org_role,
        "team_id": str(target_user.team_id) if target_user.team_id else None,
        "team_role": target_user.team_role,
    }


# ── Organization Invitations & Governance Lifecycle ─────────────────────────────

@router.post("/{org_id}/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization_invitation(
    org_id: str,
    req: CreateInvitationRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Create a secure invitation token for a user to join an organization/team."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    if not user.is_admin and (user.organization_id != org_id or user.org_role != "ORG_ADMIN"):
        raise HTTPException(status_code=403, detail="Only ORG_ADMIN can create invitations.")

    # Privilege escalation defense: non-admin cannot invite as ORG_ADMIN
    if req.role == "ORG_ADMIN" and not user.is_admin and user.org_role != "ORG_ADMIN":
        raise HTTPException(status_code=403, detail="Privilege escalation: Cannot invite ORG_ADMIN.")

    org = (await db.execute(select(Organization).where(Organization.id == org_uuid))).scalar_one_or_none()
    if not org or org.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Organization not found.")

    team_uuid = uuid.UUID(req.team_id) if req.team_id else None
    if team_uuid:
        team = (await db.execute(select(Team).where(Team.id == team_uuid, Team.organization_id == org_uuid))).scalar_one_or_none()
        if not team or team.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Specified team does not exist in this organization.")

    # Generate secure 256-bit token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    prefix = raw_token[:10]
    expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_days)

    invitation = OrganizationInvitation(
        organization_id=org_uuid,
        team_id=team_uuid,
        invited_by_user_id=uuid.UUID(user.user_id),
        invitee_email=req.email.lower().strip(),
        role=req.role,
        team_role=req.team_role,
        token_hash=token_hash,
        token_prefix=prefix,
        status="PENDING",
        expires_at=expires_at,
    )
    db.add(invitation)

    # Audit log
    audit_ev = AuditLog(
        event="INVITATION_CREATED",
        user_id=uuid.UUID(user.user_id),
        organization_id=org_uuid,
        event_data={
            "invitee_email": req.email.lower().strip(),
            "role": req.role,
            "team_id": str(team_uuid) if team_uuid else None,
            "token_prefix": prefix,
            "expires_at": expires_at.isoformat(),
        },
    )
    db.add(audit_ev)

    await db.commit()
    await db.refresh(invitation)

    return InvitationResponse(
        id=str(invitation.id),
        organization_id=str(invitation.organization_id),
        team_id=str(invitation.team_id) if invitation.team_id else None,
        invitee_email=invitation.invitee_email,
        role=invitation.role,
        team_role=invitation.team_role,
        token=raw_token,
        token_prefix=invitation.token_prefix,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@router.get("/{org_id}/invitations", response_model=List[InvitationResponse])
async def list_organization_invitations(
    org_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """List pending and active invitations for an organization."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    if not user.is_admin and (user.organization_id != org_id or user.org_role != "ORG_ADMIN"):
        raise HTTPException(status_code=403, detail="Only ORG_ADMIN can view invitations.")

    invites_res = await db.execute(
        select(OrganizationInvitation).where(OrganizationInvitation.organization_id == org_uuid)
    )
    invites = invites_res.scalars().all()
    return [
        InvitationResponse(
            id=str(inv.id),
            organization_id=str(inv.organization_id),
            team_id=str(inv.team_id) if inv.team_id else None,
            invitee_email=inv.invitee_email,
            role=inv.role,
            team_role=inv.team_role,
            token=None,
            token_prefix=inv.token_prefix,
            status=inv.status,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
        )
        for inv in invites
    ]


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Accept an organization invitation using the secure token."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    invitation = (
        await db.execute(select(OrganizationInvitation).where(OrganizationInvitation.token_hash == token_hash))
    ).scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid or non-existent invitation token.")

    # Validate eligibility (status, expiration, target email)
    caller = (await db.execute(select(User).where(User.id == uuid.UUID(user.user_id)))).scalar_one_or_none()
    if not caller:
        raise HTTPException(status_code=401, detail="Caller not authenticated.")

    is_valid, reason = invitation.is_valid_for_acceptance(caller.email)
    if not is_valid:
        if "not pending" in reason.lower() or "expired" in reason.lower():
            raise HTTPException(status_code=400, detail=reason)
        else:
            raise HTTPException(status_code=403, detail=f"Forbidden: {reason}")

    # Prevent silently abandoning an existing organization without leaving first
    if caller.organization_id is not None and caller.organization_id != invitation.organization_id:
        existing_org = (
            await db.execute(select(Organization).where(Organization.id == caller.organization_id, Organization.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if existing_org:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"You already belong to Organization '{existing_org.name}'. You must explicitly leave before accepting a new organization invitation."
            )

    # Bind membership
    caller.organization_id = invitation.organization_id
    caller.org_role = invitation.role
    if invitation.team_id:
        caller.team_id = invitation.team_id
        caller.team_role = invitation.team_role

    invitation.status = "ACCEPTED"
    invitation.accepted_at = datetime.now(timezone.utc)
    invitation.accepted_by_user_id = caller.id

    audit_ev = AuditLog(
        event="INVITATION_ACCEPTED",
        user_id=caller.id,
        organization_id=invitation.organization_id,
        event_data={
            "invitation_id": str(invitation.id),
            "role_granted": invitation.role,
            "team_id": str(invitation.team_id) if invitation.team_id else None,
            "team_role": invitation.team_role,
        },
    )
    db.add(audit_ev)

    await db.commit()

    return {
        "status": "ACCEPTED",
        "message": f"Successfully joined organization as {invitation.role}.",
        "organization_id": str(invitation.organization_id),
        "team_id": str(invitation.team_id) if invitation.team_id else None,
        "role": invitation.role,
        "team_role": invitation.team_role,
    }


@router.post("/invitations/{token}/reject")
async def reject_invitation(
    token: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Reject an organization invitation."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    invitation = (
        await db.execute(select(OrganizationInvitation).where(OrganizationInvitation.token_hash == token_hash))
    ).scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid or non-existent invitation token.")

    if invitation.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Cannot reject invitation in status '{invitation.status}'.")

    invitation.status = "REJECTED"
    await db.commit()

    return {"status": "REJECTED", "message": "Invitation rejected."}


@router.delete("/{org_id}/invitations/{invitation_id}")
async def revoke_invitation(
    org_id: str,
    invitation_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Revoke a pending invitation."""
    try:
        org_uuid = uuid.UUID(org_id)
        inv_uuid = uuid.UUID(invitation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format.")

    if not user.is_admin and (user.organization_id != org_id or user.org_role != "ORG_ADMIN"):
        raise HTTPException(status_code=403, detail="Only ORG_ADMIN can revoke invitations.")

    invitation = (
        await db.execute(select(OrganizationInvitation).where(OrganizationInvitation.id == inv_uuid, OrganizationInvitation.organization_id == org_uuid))
    ).scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    invitation.status = "REVOKED"
    await db.commit()
    return {"status": "REVOKED", "message": "Invitation successfully revoked."}


@router.delete("/{org_id}/members/{target_user_id}")
async def remove_organization_member(
    org_id: str,
    target_user_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Remove a user from an organization."""
    try:
        org_uuid = uuid.UUID(org_id)
        target_uuid = uuid.UUID(target_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format.")

    caller_is_admin = user.is_admin or (user.organization_id == org_id and user.org_role == "ORG_ADMIN")
    caller_is_self = (user.user_id == target_user_id)

    if not (caller_is_admin or caller_is_self):
        raise HTTPException(status_code=403, detail="Permission Denied: Only ORG_ADMIN or the user themselves can remove membership.")

    target_user = (
        await db.execute(select(User).where(User.id == target_uuid, User.organization_id == org_uuid))
    ).scalar_one_or_none()

    if not target_user or target_user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Member not found in this organization.")

    # Guard: Cannot remove the sole remaining ORG_ADMIN
    if target_user.org_role == "ORG_ADMIN":
        admin_count_res = await db.execute(
            select(func.count(User.id)).where(User.organization_id == org_uuid, User.org_role == "ORG_ADMIN", User.deleted_at == None)
        )
        admin_count = admin_count_res.scalar() or 0
        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove the sole ORG_ADMIN. Transfer ownership before leaving or removing this member."
            )

    target_user.organization_id = None
    target_user.org_role = "MEMBER"
    target_user.team_id = None
    target_user.team_role = "Viewer"

    audit_ev = AuditLog(
        event="MEMBER_REMOVED",
        user_id=uuid.UUID(user.user_id),
        organization_id=org_uuid,
        event_data={"removed_user_id": str(target_uuid), "remover_user_id": user.user_id},
    )
    db.add(audit_ev)

    await db.commit()
    return {"message": "Member removed from organization successfully."}


@router.post("/{org_id}/leave")
async def leave_organization(
    org_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Explicitly leave an organization."""
    return await remove_organization_member(org_id=org_id, target_user_id=user.user_id, user=user, db=db)


@router.post("/{org_id}/transfer-ownership")
async def transfer_organization_ownership(
    org_id: str,
    req: TransferOwnershipRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Transfer primary organization ownership to another existing member."""
    try:
        org_uuid = uuid.UUID(org_id)
        target_uuid = uuid.UUID(req.target_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format.")

    if not user.is_admin and (user.organization_id != org_id or user.org_role != "ORG_ADMIN"):
        raise HTTPException(status_code=403, detail="Only current ORG_ADMIN can transfer ownership.")

    target_user = (
        await db.execute(select(User).where(User.id == target_uuid, User.organization_id == org_uuid))
    ).scalar_one_or_none()
    if not target_user or target_user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Target user is not a member of this organization.")

    target_user.org_role = "ORG_ADMIN"

    # Demote caller or retain co-admin
    caller = (await db.execute(select(User).where(User.id == uuid.UUID(user.user_id)))).scalar_one_or_none()
    if caller and caller.id != target_user.id:
        caller.org_role = "MEMBER"

    audit_ev = AuditLog(
        event="ORGANIZATION_OWNERSHIP_TRANSFERRED",
        user_id=uuid.UUID(user.user_id),
        organization_id=org_uuid,
        event_data={"transferred_to_user_id": str(target_uuid), "transferred_by": user.user_id},
    )
    db.add(audit_ev)

    await db.commit()
    return {"message": "Ownership transferred successfully.", "new_org_admin_id": str(target_uuid)}


@router.post("/{org_id}/scim/rotate-token")
async def rotate_organization_scim_token(
    org_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Generate or rotate the SCIM 2.0 bearer credential for an organization."""
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    if not user.is_admin and (user.organization_id != org_id or user.org_role != "ORG_ADMIN"):
        raise HTTPException(status_code=403, detail="Only ORG_ADMIN can rotate SCIM credentials.")

    org = (await db.execute(select(Organization).where(Organization.id == org_uuid))).scalar_one_or_none()
    if not org or org.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Organization not found.")

    raw_token = f"scim_live_{secrets.token_urlsafe(32)}"
    prefix = raw_token[:12]
    token_hash = hash_password(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=180)

    org.scim_enabled = True
    org.scim_token_prefix = prefix
    org.scim_token_hash = token_hash
    org.scim_token_expires_at = expires_at

    # Audit log entry for SCIM credential rotation
    audit_ev = AuditLog(
        event="SCIM_TOKEN_ROTATED",
        user_id=uuid.UUID(user.user_id),
        organization_id=org_uuid,
        event_data={"token_prefix": prefix, "expires_at": expires_at.isoformat()},
    )
    db.add(audit_ev)

    await db.commit()

    return {
        "organization_id": str(org.id),
        "scim_token": raw_token,
        "token_prefix": prefix,
        "expires_at": expires_at.isoformat(),
        "warning": "Copy this token now. It will not be shown again in plain text.",
    }
