from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.shared.models import PlanTier

TIER_LIMITS = {
    PlanTier.FREE: 1,
    PlanTier.PRO: 4,
    PlanTier.ENTERPRISE: 16,
}

async def get_active_job_count(db: AsyncSession, user_id: str) -> int:
    """Fetch the number of active jobs for a user."""
    result = await db.execute(
        select(func.count()).select_from(JobRecord).where(
            JobRecord.user_id == user_id,
            JobRecord.status.in_(["RUNNING", "PENDING"])
        )
    )
    return result.scalar()

async def assert_can_run_job(user: dict, db: AsyncSession):
    """
    Tier-based concurrency gate.
    ENTERPRISE users with is_admin=True are exempt.
    """
    from suspensionlab.backend.database.models.user import User
    import uuid as _uuid

    # 1. DB-Atomic Lock
    try:
        user_uuid = _uuid.UUID(str(user["user_id"]))
    except (ValueError, KeyError):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid token subject.")

    result = await db.execute(
        select(User).where(User.id == user_uuid).with_for_update()
    )
    db_user = result.scalar_one_or_none()
    if not db_user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="User not found.")

    # Admin flag checked from DB, not from a static literal
    if db_user.is_admin:
        return

    # 2. Enforce tier limits
    tier = user.get("tier", PlanTier.FREE)
    limit = TIER_LIMITS.get(tier, 1)
    active = await get_active_job_count(db, user["user_id"])

    if active >= limit:
        from suspensionlab.backend.core.errors import QuotaExceededError
        from suspensionlab.backend.security.audit import log_audit_event
        log_audit_event(
            "QUOTA_EXCEEDED",
            user_id=user["user_id"],
            metadata={"tier": tier, "limit": limit, "active": active}
        )
        raise QuotaExceededError(tier=tier, limit=limit)
