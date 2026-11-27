import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)


def _db_unavailable(exc: Exception) -> HTTPException:
    """Wave 5A: convert unexpected persistence-layer failures (serverless DB
    session errors, RLS context errors, missing columns, serialization
    failures) into an explicit, diagnosable 503 instead of an unhandled 500
    with an empty body."""
    logger.exception("Profiles persistence failure: %s", exc)
    return HTTPException(
        status_code=503,
        detail="Profile storage is temporarily unavailable. The engineering database connection failed; retry shortly or contact support if it persists.",
    )
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
    version: Optional[int] = None
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


async def _save_revision(db, profile, u_id, user, old_params: Optional[dict]):
    """Wave 6 §2: save a versioned revision (parent ID, params snapshot, diff,
    author/timestamp) for every profile create/update/rollback."""
    from sqlalchemy import select as _select, func as _func
    from suspensionlab.backend.database.models.profile import ProfileRevision, compute_params_diff

    res = await db.execute(
        _select(ProfileRevision)
        .where(ProfileRevision.profile_id == profile.id)
        .order_by(ProfileRevision.revision_number.desc())
        .limit(1)
    )
    parent = res.scalar_one_or_none()
    rev = ProfileRevision(
        profile_id=profile.id,
        revision_number=(parent.revision_number + 1) if parent else 1,
        parent_revision_id=parent.id if parent else None,
        params=profile.params,
        param_diff=compute_params_diff(old_params, profile.params),
        author_user_id=u_id,
        author_name=getattr(user, "name", None) or getattr(user, "email", None),
    )
    db.add(rev)
    # Atomic: no commit here. The caller commits the profile change and its
    # revision together in ONE transaction (flush only, so rev.id is assigned).
    await db.flush()
    return rev


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

    try:
        # Wave 6: profile + revision #1 are written in ONE transaction, so a failure
        # cannot leave an orphan profile without its revision.
        db.add(db_profile)
        await db.flush()
        await _save_revision(db, db_profile, u_id, user, old_params=None)
        if trial:
            # record_trial_usage commits: that single commit covers the profile,
            # its revision and the trial counter together.
            await TrialService.record_trial_usage(db, user, action="vehicle", delta=1)
        else:
            await db.commit()
        await db.refresh(db_profile)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise _db_unavailable(exc)

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

    # Wave 6: later audit/outbox commits may expire the instance; refresh before return
    await db.refresh(db_profile)
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

    try:
        result = await db.execute(query)
        profiles = result.scalars().all()
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_unavailable(exc)
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
    try:
        result = await db.execute(query)
        profile = result.scalar_one_or_none()
    except HTTPException:
        raise
    except Exception as exc:
        raise _db_unavailable(exc)
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
        profile.version = (profile.version or 1) + 1

    try:
        # Wave 6: a params change saves a revision (parent + diff) in the SAME
        # transaction as the profile update: flush, add revision, one commit.
        if update_data.params is not None:
            await db.flush()
            await _save_revision(db, profile, u_id, user, old_params=old_params)
        await db.commit()
        await db.refresh(profile)
    except Exception as exc:
        await db.rollback()
        raise _db_unavailable(exc)

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

    # Wave 6: later audit/outbox commits may expire the instance; refresh before return
    await db.refresh(profile)
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


# ── Wave 6 §2: versioned revision history, diff and rollback ────────────────

async def _load_owned_profile(db, profile_id: str, user: Any) -> VehicleProfile:
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
    return profile


@router.get("/{profile_id}/revisions")
async def list_profile_revisions(
    profile_id: str,
    db: AsyncSession = Depends(get_db_dependency),
    user: Any = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """List all saved revisions for a profile (newest first)."""
    from suspensionlab.backend.database.models.profile import ProfileRevision
    profile = await _load_owned_profile(db, profile_id, user)
    res = await db.execute(
        select(ProfileRevision)
        .where(ProfileRevision.profile_id == profile.id)
        .order_by(ProfileRevision.revision_number.desc())
    )
    revs = res.scalars().all()
    return {
        "profile_id": str(profile.id),
        "revisions": [
            {
                "id": str(r.id),
                "revision_number": r.revision_number,
                "parent_revision_id": str(r.parent_revision_id) if r.parent_revision_id else None,
                "params": r.params,
                "param_diff": r.param_diff,
                "author_user_id": str(r.author_user_id) if r.author_user_id else None,
                "author_name": r.author_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in revs
        ],
    }


@router.get("/{profile_id}/diff")
async def diff_profile_revisions(
    profile_id: str,
    from_revision: int,
    to_revision: int,
    db: AsyncSession = Depends(get_db_dependency),
    user: Any = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """Parameter diff between any two saved revisions of a profile."""
    from suspensionlab.backend.database.models.profile import ProfileRevision, compute_params_diff
    profile = await _load_owned_profile(db, profile_id, user)
    res = await db.execute(
        select(ProfileRevision).where(ProfileRevision.profile_id == profile.id)
    )
    by_num = {r.revision_number: r for r in res.scalars().all()}
    a = by_num.get(from_revision)
    b = by_num.get(to_revision)
    if not a or not b:
        raise HTTPException(status_code=404, detail="Revision not found for this profile")
    return {
        "profile_id": str(profile.id),
        "from_revision": from_revision,
        "to_revision": to_revision,
        "diff": compute_params_diff(a.params, b.params),
    }


@router.post("/{profile_id}/rollback/{revision_number}")
async def rollback_profile_revision(
    profile_id: str,
    revision_number: int,
    db: AsyncSession = Depends(get_db_dependency),
    user: Any = Depends(require_permission(Permission.VEHICLE_WRITE)),
):
    """Roll the profile back to a saved revision. The rollback itself is saved
    as a NEW revision (append-only history; nothing is rewritten)."""
    from suspensionlab.backend.database.models.profile import ProfileRevision
    profile = await _load_owned_profile(db, profile_id, user)
    res = await db.execute(
        select(ProfileRevision).where(
            ProfileRevision.profile_id == profile.id,
            ProfileRevision.revision_number == revision_number,
        )
    )
    target = res.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Revision not found for this profile")

    u_id = _to_uuid(getattr(user, "user_id", None) or getattr(user, "id", None))
    old_params = profile.params
    profile.params = target.params
    profile.version = (profile.version or 1) + 1
    try:
        await db.flush()
        new_rev = await _save_revision(db, profile, u_id, user, old_params=old_params)
        new_rev_number = new_rev.revision_number
        await db.commit()
        await db.refresh(profile)
    except Exception as exc:
        await db.rollback()
        raise _db_unavailable(exc)

    return {
        "profile_id": str(profile.id),
        "rolled_back_to": revision_number,
        "new_revision": new_rev_number,
        "version": profile.version,
        "params": profile.params,
    }
