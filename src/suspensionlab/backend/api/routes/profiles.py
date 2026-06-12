import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.security.auth import verify_api_key

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileCreate(BaseModel):
    name: str
    vehicle_type: str
    params: Dict[str, Any]


class ProfileResponse(BaseModel):
    id: str
    name: str
    vehicle_type: str
    params: Dict[str, Any]
    user_id: str
    team_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/", response_model=ProfileResponse)
async def create_profile(
    profile: ProfileCreate,
    db: AsyncSession = Depends(get_db_dependency),
    user: dict = Depends(verify_api_key),
):
    """Create a new vehicle profile scoped to the authenticated user."""
    profile_id = str(uuid.uuid4())
    db_profile = VehicleProfile(
        id=profile_id,
        name=profile.name,
        vehicle_type=profile.vehicle_type,
        params=profile.params,
        user_id=user["user_id"],  
        team_id=user.get("team_id"),
    )
    db.add(db_profile)
    await db.commit()
    await db.refresh(db_profile)
    return db_profile


@router.get("/", response_model=List[ProfileResponse])
async def list_profiles(
    vehicle_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_dependency),
    user: dict = Depends(verify_api_key),
):
    """List all profiles belonging to the authenticated user or their team."""
    if user.get("team_id"):
        query = select(VehicleProfile).where(VehicleProfile.team_id == user["team_id"])
    else:
        query = select(VehicleProfile).where(VehicleProfile.user_id == user["user_id"])
    if vehicle_type:
        query = query.where(VehicleProfile.vehicle_type == vehicle_type)

    result = await db.execute(query)
    profiles = result.scalars().all()
    return profiles


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db_dependency),
    user: dict = Depends(verify_api_key),
):
    """Fetch a single profile — validates ownership or team membership."""
    if user.get("team_id"):
        query = select(VehicleProfile).where(
            VehicleProfile.id == profile_id,
            VehicleProfile.team_id == user["team_id"],
        )
    else:
        query = select(VehicleProfile).where(
            VehicleProfile.id == profile_id,
            VehicleProfile.user_id == user["user_id"],
        )
    result = await db.execute(query)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db_dependency),
    user: dict = Depends(verify_api_key),
):
    """Delete a profile — validates ownership or team membership."""
    if user.get("team_id"):
        query = select(VehicleProfile).where(
            VehicleProfile.id == profile_id,
            VehicleProfile.team_id == user["team_id"],
        )
    else:
        query = select(VehicleProfile).where(
            VehicleProfile.id == profile_id,
            VehicleProfile.user_id == user["user_id"],
        )
    result = await db.execute(query)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    await db.delete(profile)
    await db.commit()
    return {"status": "success", "message": "Profile deleted"}
