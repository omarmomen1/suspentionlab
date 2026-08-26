"""
backend/api/routes/teams_routes.py
CRUD for Team workspaces and members.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.shared.models import PlanTier

router = APIRouter(prefix="/teams", tags=["teams"])

# Seat roles (Tier A3): Owner > Admin > Engineer > Crew > Viewer.
# Crew = pit-lane access on mobile setup sheets; Viewer = read-only dashboards.
VALID_ROLES = ["Admin", "Engineer", "Crew", "Viewer"]

# ─── Schemas ─────────────────────────────────────────────────────────────────

class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)

class TeamMemberResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str

class TeamResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    plan: str
    data_region: str = "eu-central"
    members: List[TeamMemberResponse]

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/", response_model=TeamResponse, status_code=201)
async def create_team(
    req: CreateTeamRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if user.plan != PlanTier.ENTERPRISE:
        raise HTTPException(status_code=403, detail="Team creation requires ENTERPRISE plan.")

    # Check if user already in team
    if user.team_id:
        raise HTTPException(status_code=400, detail="You are already in a team.")

    # BUGFIX (#21): `slug` is NOT NULL + UNIQUE — generate a unique, URL-safe
    # slug from the team name and verify no collision before insert.
    import re as _re
    base_slug = _re.sub(r"[^a-z0-9]+", "-", req.name.lower()).strip("-") or "team"
    slug = base_slug
    suffix = 0
    while True:
        existing = await db.execute(select(Team).where(Team.slug == slug))
        if existing.scalar_one_or_none() is None:
            break
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    team_id = uuid.uuid4()
    team = Team(
        id=team_id,
        name=req.name,
        slug=slug,
        owner_id=uuid.UUID(user.user_id),
        plan=PlanTier.ENTERPRISE,
    )
    db.add(team)
    
    # Update user to be in the team
    result = await db.execute(select(User).where(User.id == uuid.UUID(user.user_id)))
    db_user = result.scalar_one()
    db_user.team_id = team_id
    db_user.team_role = "Owner"

    await db.commit()
    await db.refresh(team)

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        owner_id=str(team.owner_id),
        plan=team.plan,
        data_region=team.data_region,
        members=[TeamMemberResponse(id=str(db_user.id), name=db_user.name or "", email=db_user.email, role=db_user.team_role)]
    )

@router.get("/", response_model=TeamResponse)
async def get_team(
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if not user.team_id:
        raise HTTPException(status_code=404, detail="You are not in a team.")

    team_result = await db.execute(
        select(Team)
        .options(selectinload(Team.members))
        .where(Team.id == user.team_id)
    )
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    members = team.members

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        owner_id=str(team.owner_id),
        plan=team.plan,
        data_region=team.data_region,
        members=[
            TeamMemberResponse(
                id=str(m.id),
                name=m.name or "",
                email=m.email,
                role=m.team_role or "Viewer"
            ) for m in members
        ]
    )

class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = "Viewer"

@router.post("/{team_id}/invitations")
async def invite_member(
    team_id: str,
    req: InviteMemberRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if not user.team_id or str(user.team_id) != team_id:
        raise HTTPException(status_code=403, detail="Not authorized for this team.")
        
    # Check inviter role
    inviter_res = await db.execute(select(User).where(User.id == uuid.UUID(user.user_id)))
    inviter = inviter_res.scalar_one()
    if inviter.team_role not in ["Owner", "Admin"]:
        raise HTTPException(status_code=403, detail="Viewer cannot perform write operations.")

    team_result = await db.execute(select(Team).where(Team.id == user.team_id))
    team = team_result.scalar_one()

    user_result = await db.execute(select(User).where(User.email == req.email.lower()))
    target_user = user_result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User with this email not found. They must sign up first.")

    if target_user.team_id:
        raise HTTPException(status_code=400, detail="User is already in a team.")

    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role specified. Valid roles: {VALID_ROLES}.")
    if req.role == "Owner":
        raise HTTPException(status_code=400, detail="Cannot invite as Owner.")

    target_user.team_id = team.id
    target_user.team_role = req.role
    await db.commit()

    return {"status": "success", "message": f"{target_user.email} added to team."}

@router.delete("/{team_id}/members/{member_id}")
async def remove_member(
    team_id: str,
    member_id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if not user.team_id or str(user.team_id) != team_id:
        raise HTTPException(status_code=403, detail="Not authorized for this team.")
        
    inviter_res = await db.execute(select(User).where(User.id == uuid.UUID(user.user_id)))
    inviter = inviter_res.scalar_one()

    if inviter.team_role not in ["Owner", "Admin"] and member_id != user.user_id:
        raise HTTPException(status_code=403, detail="Viewer cannot perform write operations.")

    team_result = await db.execute(select(Team).where(Team.id == user.team_id))
    team = team_result.scalar_one()

    if member_id == str(team.owner_id):
        raise HTTPException(status_code=400, detail="Owner cannot be removed. Transfer ownership first.")

    user_result = await db.execute(select(User).where(User.id == uuid.UUID(member_id), User.team_id == team.id))
    target_user = user_result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="Member not found in team.")
        
    # Admin cannot remove another Admin or Owner
    if inviter.team_role == "Admin" and target_user.team_role in ["Owner", "Admin"] and member_id != user.user_id:
        raise HTTPException(status_code=403, detail="Admin cannot remove other Admins or Owners.")

    target_user.team_id = None
    target_user.team_role = None
    await db.commit()

    return {"status": "success", "message": "Member removed from team."}

@router.get("/analytics")
async def get_team_analytics(
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if not user.team_id:
        raise HTTPException(status_code=400, detail="You are not in a team.")

    from sqlalchemy import func
    from suspensionlab.backend.database.models.job import JobRecord
    
    # Get all team members
    members_result = await db.execute(select(User.id).where(User.team_id == user.team_id))
    member_ids = members_result.scalars().all()
    
    # Aggregate jobs for the team
    if not member_ids:
        return {"total_jobs": 0, "status_breakdown": {}}
        
    jobs_result = await db.execute(
        select(JobRecord.status, func.count(JobRecord.id))
        .where(JobRecord.user_id.in_(member_ids))
        .group_by(JobRecord.status)
    )
    
    status_breakdown = {}
    total_jobs = 0
    for status, count in jobs_result.all():
        status_breakdown[status] = count
        total_jobs += count
        
    return {
        "total_jobs": total_jobs,
        "status_breakdown": status_breakdown,
        "quota_limit": 1000,
        "quota_used": total_jobs
    }


class UpdateRoleRequest(BaseModel):
    role: str

@router.patch("/{team_id}/members/{member_id}/role")
async def update_member_role(
    team_id: str,
    member_id: str,
    req: UpdateRoleRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Change a member's seat role (Tier A3). Only Owners and Admins may change
    roles; Admins cannot modify Owners or other Admins.
    """
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Valid roles: {VALID_ROLES}.")

    if not user.team_id or str(user.team_id) != team_id:
        raise HTTPException(status_code=403, detail="Not authorized for this team.")

    actor_res = await db.execute(select(User).where(User.id == uuid.UUID(user.user_id)))
    actor = actor_res.scalar_one()
    if actor.team_role not in ("Owner", "Admin"):
        raise HTTPException(status_code=403, detail="Only Owners and Admins can change seat roles.")

    member_res = await db.execute(
        select(User).where(User.id == uuid.UUID(member_id), User.team_id == uuid.UUID(team_id))
    )
    member = member_res.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found in team.")

    if member.team_role == "Owner" or str(member.id) == str(actor.id):
        raise HTTPException(status_code=403, detail="Cannot change the Owner's role or your own role.")
    if actor.team_role == "Admin" and member.team_role == "Admin":
        raise HTTPException(status_code=403, detail="Admins cannot change other Admins' roles.")

    old_role = member.team_role
    member.team_role = req.role
    await db.commit()

    from suspensionlab.backend.security.audit import log_audit_event
    log_audit_event(
        "TEAM_ROLE_CHANGED",
        user_id=str(member.id),
        ip="-",
        metadata={"team_id": team_id, "old_role": old_role, "new_role": req.role, "changed_by": user.user_id},
    )
    return {"id": str(member.id), "role": member.team_role}


class DataRegionRequest(BaseModel):
    region: str = Field(..., description="eu-central | us-east")

@router.patch("/{team_id}/data-region")
async def set_data_region(
    team_id: str,
    req: DataRegionRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Data residency selection (Tier C1). Owner/Admin only. The choice is
    recorded on the team and enforced by the regional deployment topology.
    """
    if req.region not in ("eu-central", "us-east"):
        raise HTTPException(status_code=400, detail="region must be 'eu-central' or 'us-east'.")
    if not user.team_id or str(user.team_id) != team_id:
        raise HTTPException(status_code=403, detail="Not authorized for this team.")

    actor_res = await db.execute(select(User).where(User.id == uuid.UUID(user.user_id)))
    actor = actor_res.scalar_one()
    if actor.team_role not in ("Owner", "Admin"):
        raise HTTPException(status_code=403, detail="Only Owners and Admins can change data residency.")

    team_res = await db.execute(select(Team).where(Team.id == uuid.UUID(team_id)))
    team = team_res.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found.")

    old_region = team.data_region
    team.data_region = req.region
    await db.commit()

    from suspensionlab.backend.security.audit import log_audit_event
    log_audit_event(
        "TEAM_DATA_REGION_CHANGED",
        user_id=user.user_id,
        ip="-",
        metadata={"team_id": team_id, "old_region": old_region, "new_region": req.region},
    )
    return {"team_id": team_id, "data_region": team.data_region}
