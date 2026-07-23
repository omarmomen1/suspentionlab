import logging
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.auth import verify_api_key, UserContext

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", deprecated=True, include_in_schema=False)
async def get_me(user: UserContext = Depends(verify_api_key)):
    """Deprecated: Use /auth/me. Will be removed in v2."""
    user_copy = user.model_dump()
    user_copy.pop("key", None)
    return user_copy

@router.patch("/me/onboarding")
async def complete_onboarding(
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    try:
        import uuid as _uuid
        result = await db.execute(
            select(User).where(User.id == _uuid.UUID(str(user.user_id)))
        )
        db_user = result.scalars().first()
        
        if db_user:
            db_user.onboarding_complete = True
            await db.commit()
            # FIXED: Removed superfluous db.refresh(db_user) — the refreshed object
            # is never used; we return {"status": "ok"} immediately after.
            
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        # FIXED: Log the exception so operators can investigate — previously swallowed silently.
        logger.exception("Onboarding update failed for user %s: %s", user.user_id, e)
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Database transaction failed")
