"""
backend/api/routes/teams_routes.py
CRUD for Team workspaces and members.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.shared.models import PlanTier

router = APIRouter(prefix="/teams", tags=["teams"])

# ─── Schemas ─────────────────────────────────────────────────────────────────

class CreateTeamRequest(BaseModel):
    name: str

class InviteMemberRequest(BaseModel):
    email: str

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
    members: List[TeamMemberResponse]

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/", response_model=TeamResponse, status_code=201)
async def create_team(
    req: CreateTeamRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if user.get("plan") != PlanTier.ENTERPRISE:
        raise HTTPException(status_code=403, detail="Team creation requires ENTERPRISE plan.")

    # Check if user already in team
    if user.get("team_id"):
        raise HTTPException(status_code=400, detail="You are already in a team.")

    team_id = uuid.uuid4()
    team = Team(
        id=team_id,
        name=req.name,
        owner_id=uuid.UUID(user["user_id"]),
        plan=PlanTier.ENTERPRISE,
    )
    db.add(team)
    
    # Update user to be in the team
    result = await db.execute(select(User).where(User.id == uuid.UUID(user["user_id"])))
    db_user = result.scalar_one()
    db_user.team_id = team_id

    await db.commit()
    await db.refresh(team)

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        owner_id=str(team.owner_id),
        plan=team.plan,
        members=[TeamMemberResponse(id=str(db_user.id), name=db_user.name or "", email=db_user.email, role="Owner")]
    )

@router.get("/", response_model=TeamResponse)
async def get_team(
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if not user.get("team_id"):
        raise HTTPException(status_code=404, detail="You are not in a team.")

    team_result = await db.execute(select(Team).where(Team.id == user["team_id"]))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")

    members_result = await db.execute(select(User).where(User.team_id == team.id))
    members = members_result.scalars().all()

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        owner_id=str(team.owner_id),
        plan=team.plan,
        members=[
            TeamMemberResponse(
                id=str(m.id),
                name=m.name or "",
                email=m.email,
                role="Owner" if m.id == team.owner_id else "Member"
            ) for m in members
        ]
    )

@router.post("/invite")
async def invite_member(
    req: InviteMemberRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if not user.get("team_id"):
        raise HTTPException(status_code=400, detail="You are not in a team.")

    team_result = await db.execute(select(Team).where(Team.id == user["team_id"]))
    team = team_result.scalar_one()

    if str(team.owner_id) != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only team owner can invite members.")

    user_result = await db.execute(select(User).where(User.email == req.email.lower()))
    target_user = user_result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User with this email not found. They must sign up first.")

    if target_user.team_id:
        raise HTTPException(status_code=400, detail="User is already in a team.")

    target_user.team_id = team.id
    target_user.plan = PlanTier.ENTERPRISE
    await db.commit()

    return {"status": "success", "message": f"{target_user.email} added to team."}

@router.delete("/members/{member_id}")
async def remove_member(
    member_id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if not user.get("team_id"):
        raise HTTPException(status_code=400, detail="You are not in a team.")

    team_result = await db.execute(select(Team).where(Team.id == user["team_id"]))
    team = team_result.scalar_one()

    if str(team.owner_id) != user["user_id"] and member_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only team owner can remove others.")

    if member_id == str(team.owner_id):
        raise HTTPException(status_code=400, detail="Owner cannot be removed. Transfer ownership first.")

    user_result = await db.execute(select(User).where(User.id == uuid.UUID(member_id), User.team_id == team.id))
    target_user = user_result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="Member not found in team.")

    target_user.team_id = None
    target_user.plan = PlanTier.FREE
    await db.commit()

    return {"status": "success", "message": "Member removed from team."}

@router.get("/analytics")
async def get_team_analytics(
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if not user.get("team_id"):
        raise HTTPException(status_code=400, detail="You are not in a team.")

    from sqlalchemy import func
    from suspensionlab.backend.database.models.job import JobRecord
    
    # Get all team members
    members_result = await db.execute(select(User.id).where(User.team_id == user["team_id"]))
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
