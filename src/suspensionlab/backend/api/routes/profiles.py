import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Dict, Any, List, Optional
from datetime import datetime

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.security.auth import verify_api_key, require_permission
from suspensionlab.backend.security.permissions import Permission

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileCreate(BaseModel):
    name: str
    vehicle_type: str = "QUARTER_CAR"
    params: Dict[str, Any]

    @field_validator("vehicle_type", mode="before")
    @classmethod
    def normalize_vehicle_type(cls, v: Any) -> str:
        if not v:
            return "QUARTER_CAR"
        v_str = str(v).upper()
        if v_str in ("QUARTER_CAR", "HALF_CAR", "FULL_CAR"):
            return v_str
        return "QUARTER_CAR"


class ProfileResponse(BaseModel):
    id: Any
    name: str
    vehicle_type: str
    params: Dict[str, Any]
    user_id: Any
    team_id: Optional[Any] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _to_uuid(val: Any) -> Optional[uuid.UUID]:
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, TypeError):
        return None


@router.post("", response_model=ProfileResponse)
@router.post("/", response_model=ProfileResponse)
async def create_profile(
    profile: ProfileCreate,
    db: AsyncSession = Depends(get_db_dependency),
    user: Any = Depends(require_permission(Permission.VEHICLE_WRITE)),
):
    """Create a new vehicle profile scoped to the authenticated user."""
    t_id = _to_uuid(getattr(user, "team_id", None))

    profile_id = uuid.uuid4()
    u_id = _to_uuid(getattr(user, "user_id", None) or getattr(user, "id", None))
    db_profile = VehicleProfile(
        id=profile_id,
        name=profile.name,
        vehicle_type=profile.vehicle_type,
        params=profile.params,
        user_id=u_id,  
        team_id=t_id,
    )

    # ── Trial Governance: Enforce 1 vehicle limit & expiration ──
    from suspensionlab.backend.services.trial_service import TrialService
    trial = await TrialService.assert_trial_access(db, user, action="vehicle", delta=1)

    db.add(db_profile)
    await db.commit()
    await db.refresh(db_profile)
    if trial:
        await TrialService.record_trial_usage(db, user, action="vehicle", delta=1)

    try:
        from suspensionlab.backend.security.audit import record_audit_event
        await record_audit_event(
            db=db,
            event_type="VEHICLE_CREATED",
            user_id=str(u_id) if u_id else None,
            team_id=str(t_id) if t_id else None,
            artifact_id=str(db_profile.id),
            metadata={
                "profile_id": str(db_profile.id),
                "name": db_profile.name,
                "vehicle_type": db_profile.vehicle_type,
                "params": db_profile.params,
            }
        )
    except Exception as e:
        import logging
        logging.getLogger("security_audit").warning("Audit logging warning for vehicle creation: %s", e)

    return db_profile


@router.get("", response_model=List[ProfileResponse])
@router.get("/", response_model=List[ProfileResponse])
async def list_profiles(
    vehicle_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_dependency),
    user: Any = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """List all profiles belonging to the authenticated user or their team."""
    u_id = _to_uuid(getattr(user, "user_id", None) or getattr(user, "id", None))
    t_id = _to_uuid(getattr(user, "team_id", None))
    from sqlalchemy import or_
    if t_id:
        query = select(VehicleProfile).where(
            or_(VehicleProfile.team_id == t_id, VehicleProfile.user_id == u_id)
        )
    else:
        query = select(VehicleProfile).where(VehicleProfile.user_id == u_id)
    query = query.where(VehicleProfile.deleted_at.is_(None))
    if vehicle_type:
        query = query.where(VehicleProfile.vehicle_type == vehicle_type)

    result = await db.execute(query)
    profiles = result.scalars().all()
    return profiles


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db_dependency),
    user: Any = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """Fetch a single profile — validates ownership or team membership."""
    p_id = _to_uuid(profile_id)
    u_id = _to_uuid(getattr(user, "user_id", None) or getattr(user, "id", None))
    t_id = _to_uuid(getattr(user, "team_id", None))
    from sqlalchemy import or_
    if t_id:
        query = select(VehicleProfile).where(
            VehicleProfile.id == p_id,
            or_(VehicleProfile.team_id == t_id, VehicleProfile.user_id == u_id),
            VehicleProfile.deleted_at.is_(None),
        )
    else:
        query = select(VehicleProfile).where(
            VehicleProfile.id == p_id,
            VehicleProfile.user_id == u_id,
            VehicleProfile.deleted_at.is_(None),
        )
    result = await db.execute(query)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    vehicle_type: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    update_data: ProfileUpdate,
    db: AsyncSession = Depends(get_db_dependency),
    user: Any = Depends(require_permission(Permission.VEHICLE_WRITE)),
):
    """Update a profile — validates ownership or team membership and records SETUP_CHANGED / VEHICLE_UPDATED."""
    t_id = _to_uuid(getattr(user, "team_id", None))
    p_id = _to_uuid(profile_id)
    u_id = _to_uuid(getattr(user, "user_id", None) or getattr(user, "id", None))
    from sqlalchemy import or_
    if t_id:
        query = select(VehicleProfile).where(
            VehicleProfile.id == p_id,
            or_(VehicleProfile.team_id == t_id, VehicleProfile.user_id == u_id),
            VehicleProfile.deleted_at.is_(None),
        )
    else:
        query = select(VehicleProfile).where(
            VehicleProfile.id == p_id,
            VehicleProfile.user_id == u_id,
            VehicleProfile.deleted_at.is_(None),
        )
    result = await db.execute(query)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    old_params = profile.params
    if update_data.name is not None:
        profile.name = update_data.name
    if update_data.vehicle_type is not None:
        profile.vehicle_type = update_data.vehicle_type
    if update_data.params is not None:
        profile.params = update_data.params

    await db.commit()
    await db.refresh(profile)

    try:
        from suspensionlab.backend.security.audit import record_audit_event
        if update_data.params is not None:
            await record_audit_event(
                db=db,
                event_type="SETUP_CHANGED",
                user_id=str(u_id) if u_id else None,
                team_id=str(t_id) if t_id else None,
                artifact_id=str(profile.id),
                metadata={
                    "profile_id": str(profile.id),
                    "old_params": old_params,
                    "new_params": profile.params,
                }
            )
        await record_audit_event(
            db=db,
            event_type="VEHICLE_UPDATED",
            user_id=str(u_id) if u_id else None,
            team_id=str(t_id) if t_id else None,
            artifact_id=str(profile.id),
            metadata={
                "profile_id": str(profile.id),
                "name": profile.name,
                "vehicle_type": profile.vehicle_type,
            }
        )
    except Exception as e:
        import logging
        logging.getLogger("security_audit").warning("Audit logging warning for vehicle update: %s", e)

    return profile


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db_dependency),
    user: Any = Depends(require_permission(Permission.VEHICLE_DELETE)),
):
    """Delete a profile — validates ownership or team membership."""
    t_id = _to_uuid(getattr(user, "team_id", None))

    p_id = _to_uuid(profile_id)
    u_id = _to_uuid(getattr(user, "user_id", None) or getattr(user, "id", None))
    from sqlalchemy import or_
    if t_id:
        query = select(VehicleProfile).where(
            VehicleProfile.id == p_id,
            or_(VehicleProfile.team_id == t_id, VehicleProfile.user_id == u_id),
            VehicleProfile.deleted_at.is_(None),
        )
    else:
        query = select(VehicleProfile).where(
            VehicleProfile.id == p_id,
            VehicleProfile.user_id == u_id,
            VehicleProfile.deleted_at.is_(None),
        )
    result = await db.execute(query)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile.deleted_at = func.now()
    await db.commit()

    try:
        from suspensionlab.backend.security.audit import record_audit_event
        await record_audit_event(
            db=db,
            event_type="VEHICLE_DELETED",
            user_id=str(u_id) if u_id else None,
            team_id=str(t_id) if t_id else None,
            artifact_id=str(p_id),
            metadata={
                "profile_id": str(p_id),
                "name": profile.name,
            }
        )
    except Exception as e:
        import logging
        logging.getLogger("security_audit").warning("Audit logging warning for vehicle deletion: %s", e)

    return {"message": "Profile deleted"}
