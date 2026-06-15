"""
backend/api/routes/api_key_routes.py
CRUD for per-user named API keys (Enterprise tier).
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user_api_key import UserApiKey
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.security.jwt_utils import hash_password
from suspensionlab.shared.models import PlanTier

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

PLAN_LIMITS = {PlanTier.FREE: 0, PlanTier.PRO: 2, PlanTier.ENTERPRISE: 20}

# ─── Schemas ─────────────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    name: str
    expires_days: int | None = None  # None = never expires

class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    created_at: str
    expires_at: str | None
    last_used: str | None

class CreateKeyResponse(ApiKeyResponse):
    key: str  # Shown ONCE at creation — not stored in plaintext

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ApiKeyResponse])
async def list_keys(
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    try:
        user_uuid = uuid.UUID(str(user["user_id"]))
    except (ValueError, KeyError):
        return []
    result = await db.execute(
        select(UserApiKey).where(UserApiKey.user_id == user_uuid, UserApiKey.is_active == True)
    )
    keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=str(k.id), name=k.name, key_prefix=k.key_prefix,
            is_active=k.is_active,
            created_at=k.created_at.isoformat() if k.created_at else "",
            expires_at=k.expires_at.isoformat() if k.expires_at else None,
            last_used=k.last_used.isoformat() if k.last_used else None,
        )
        for k in keys
    ]


@router.post("/", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    req: CreateKeyRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    plan  = user.get("plan", PlanTier.FREE)
    limit = PLAN_LIMITS.get(plan, 0)
    if limit == 0:
        raise HTTPException(status_code=403, detail="API key access requires PRO or ENTERPRISE plan.")

    user_uuid = uuid.UUID(str(user["user_id"]))
    existing = await db.execute(
        select(UserApiKey).where(UserApiKey.user_id == user_uuid, UserApiKey.is_active == True)
    )
    if len(existing.scalars().all()) >= limit:
        raise HTTPException(status_code=403, detail=f"Your plan allows a maximum of {limit} API keys.")

    raw_key    = f"slk_{secrets.token_urlsafe(40)}"
    key_prefix = raw_key[:12]
    key_hash   = hash_password(raw_key)
    expires_at = None
    if req.expires_days:
        from datetime import timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_days)

    key = UserApiKey(
        id=uuid.uuid4(),
        user_id=uuid.UUID(str(user["user_id"])),
        name=req.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        expires_at=expires_at,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)

    return CreateKeyResponse(
        id=str(key.id), name=key.name, key_prefix=key_prefix,
        is_active=True, key=raw_key,
        created_at=key.created_at.isoformat() if key.created_at else "",
        expires_at=key.expires_at.isoformat() if key.expires_at else None,
        last_used=None,
    )


@router.delete("/{key_id}")
async def revoke_key(
    key_id: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    try:
        key_uuid  = uuid.UUID(str(key_id))
        user_uuid = uuid.UUID(str(user["user_id"]))
    except ValueError:
        raise HTTPException(status_code=404, detail="API key not found.")
    result = await db.execute(
        select(UserApiKey).where(UserApiKey.id == key_uuid, UserApiKey.user_id == user_uuid)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found.")
    key.is_active = False
    await db.commit()
    return {"status": "revoked"}
