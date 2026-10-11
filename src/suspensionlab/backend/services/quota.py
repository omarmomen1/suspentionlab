from typing import Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.shared.models import PlanTier
import uuid as _uuid

TIER_LIMITS = {
    PlanTier.FREE: 1,
    PlanTier.PRO: 4,
    PlanTier.ENTERPRISE: 16,
}

async def get_active_job_count(db: AsyncSession, user_id: str | _uuid.UUID, team_id: Optional[str | _uuid.UUID] = None) -> int:
    """Fetch the authoritative number of active jobs for a user or team, excluding stale crashed workers."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import or_

    u_uuid = _uuid.UUID(str(user_id)) if not isinstance(user_id, _uuid.UUID) else user_id
    t_uuid = _uuid.UUID(str(team_id)) if team_id and not isinstance(team_id, _uuid.UUID) else team_id

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=300)
    active_statuses = ["PENDING", "QUEUED", "RUNNING", "CANCEL_REQUESTED", "RETRYING"]

    tenant_filter = JobRecord.user_id == u_uuid
    if t_uuid:
        tenant_filter = or_(JobRecord.team_id == t_uuid, JobRecord.user_id == u_uuid)

    result = await db.execute(
        select(func.count()).select_from(JobRecord).where(
            tenant_filter,
            JobRecord.status.in_(active_statuses),
            JobRecord.deleted_at.is_(None),
            or_(JobRecord.last_heartbeat.is_(None), JobRecord.last_heartbeat > cutoff),
        )
    )
    return result.scalar() or 0

async def assert_can_run_job(user: dict | Any, db: AsyncSession):
    """
    Tier-based concurrency gate.
    ENTERPRISE users with is_admin=True are exempt.
    """
    from suspensionlab.backend.database.models.user import User

    # Extract user_id and plan safely from dict or UserContext
    raw_uid = user.get("user_id") if isinstance(user, dict) else getattr(user, "user_id", None)
    if not raw_uid:
        raw_uid = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)

    try:
        user_uuid = _uuid.UUID(str(raw_uid))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token subject.")

    result = await db.execute(
        select(User).where(User.id == user_uuid).with_for_update()
    )
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=401, detail="User not found.")

    # Admin flag checked from DB, not from a static literal
    if db_user.is_admin:
        return

    # 2. Enforce tier limits
    tier = user.get("plan", PlanTier.FREE) if isinstance(user, dict) else getattr(user, "plan", PlanTier.FREE)
    limit = TIER_LIMITS.get(tier, 1)
    active = await get_active_job_count(db, user_uuid, team_id=getattr(db_user, "team_id", None))

    if active >= limit:
        from suspensionlab.backend.core.errors import QuotaExceededError
        from suspensionlab.backend.security.audit import log_audit_event
        log_audit_event(
            "QUOTA_EXCEEDED",
            user_id=str(user_uuid),
            metadata={"tier": str(tier), "limit": limit, "active": active}
        )
        raise QuotaExceededError(tier=tier, limit=limit)
