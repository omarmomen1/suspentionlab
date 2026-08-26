"""
backend/security/auth.py
Supports two auth methods:
  1. X-API-Key header (legacy + per-user named keys)
  2. Authorization: Bearer <JWT> (new email/password login)
"""
from __future__ import annotations

from fastapi import Header, HTTPException, Request, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.audit import log_audit_event
from suspensionlab.backend.security.jwt_utils import decode_access_token
from suspensionlab.shared.models import PlanTier

# Plan tiers ordered by privilege level
PLAN_LEVELS = {PlanTier.FREE: 0, PlanTier.PRO: 1, PlanTier.ENTERPRISE: 2}


from pydantic import BaseModel

class UserContext(BaseModel):
    user_id: str
    plan: str
    email: str
    name: str
    onboarding_complete: bool
    team_id: str | None = None
    team_role: str | None = None   # Owner | Admin | Engineer | Viewer | Crew


# Seat-role hierarchy (Tier A3). Higher number = more capability.
TEAM_ROLE_LEVELS = {
    "OWNER": 4,
    "ADMIN": 3,
    "ENGINEER": 2,
    "CREW": 1,
    "VIEWER": 0,
}


def require_team_role(minimum_role: str):
    """
    FastAPI dependency factory enforcing a minimum team seat role.
    Non-team members always fail. Usage:
        Depends(require_team_role("Engineer"))
    """
    minimum = TEAM_ROLE_LEVELS.get((minimum_role or "").upper(), 99)

    async def _check(user: UserContext = Depends(verify_api_key)):
        if not user.team_id or not user.team_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action requires a team workspace membership.",
            )
        level = TEAM_ROLE_LEVELS.get(user.team_role.upper(), -1)
        if level < minimum:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the {minimum_role} seat role or higher.",
            )
        return user
    return _check

async def verify_api_key(
    request:  Request,
    api_key:  str | None = Header(alias="X-API-Key",      default=None),
    bearer:   str | None = Header(alias="Authorization",  default=None),
    db:       AsyncSession = Depends(get_db_dependency),
) -> UserContext:
    """
    Authenticate the request via:
      - Bearer JWT token (preferred — from email/password login)
      - X-API-Key header (legacy admin key or per-user named key)
    Returns a dict with user_id, tier/plan, onboarding_complete.
    """
    from suspensionlab.backend.core.errors import AuthenticationError
    ip = request.client.host if request.client else "unknown"

    if not bearer:
        sl_token = request.cookies.get("sl_token")
        if sl_token:
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                csrf_token_header = request.headers.get("X-CSRF-Token")
                csrf_token_cookie = request.cookies.get("csrf_token")
                if not csrf_token_header or not csrf_token_cookie or csrf_token_header != csrf_token_cookie:
                    from suspensionlab.backend.core.errors import AuthenticationError
                    raise AuthenticationError("CSRF token missing or mismatch.")
            bearer = f"Bearer {sl_token}"

    # ── 1. Bearer JWT (preferred) ─────────────────────────────────────────
    if bearer and bearer.startswith("Bearer "):
        token   = bearer.removeprefix("Bearer ").strip()
        payload = decode_access_token(token)
        if payload:
            if payload.get("type") != "access":
                from suspensionlab.backend.core.errors import AuthenticationError
                raise AuthenticationError("Invalid token type. Only access tokens are allowed here.")
            user_id = payload.get("sub")
            plan    = payload.get("plan", PlanTier.FREE)
            import uuid
            try:
                user_uuid = uuid.UUID(str(user_id))
            except ValueError:
                from suspensionlab.backend.core.errors import AuthenticationError
                raise AuthenticationError("Invalid token subject")
            from sqlalchemy.orm import joinedload
            result  = await db.execute(select(User).options(joinedload(User.team)).where(User.id == user_uuid, User.deleted_at == None))
            user: User | None = result.scalar_one_or_none()
            if not user:
                log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "JWT user not found"})
                raise AuthenticationError("User not found.")
            request.state.user_id = str(user.id)
            log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)

            effective_plan = user.plan
            if user.team:
                effective_plan = user.team.plan
            return UserContext(
                user_id=str(user.id),
                plan=effective_plan,
                email=user.email,
                name=user.name or "",
                onboarding_complete=user.onboarding_complete,
                team_id=str(user.team_id) if user.team_id else None,
                team_role=user.team_role,
            )
        # Token present but invalid — do not fall through to API key
        log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "Invalid Bearer token"})
        raise AuthenticationError("Invalid or expired token.")

    # ── 2. X-API-Key header ───────────────────────────────────────────────
    if api_key:
        # 2c. Look up per-user named API key (O(1) prefix lookup)
        from suspensionlab.backend.database.models.user_api_key import UserApiKey
        from suspensionlab.backend.security.jwt_utils import verify_password
        from datetime import datetime, timezone
        
        # All valid generated keys start with slk_ and use 12 chars for prefix
        if api_key.startswith("slk_") and len(api_key) > 12:
            prefix = api_key[:12]
            key_results = await db.execute(
                select(UserApiKey).where(UserApiKey.key_prefix == prefix, UserApiKey.is_active == True)
            )
            for named_key in key_results.scalars():
                # Skip expired keys
                if named_key.expires_at and datetime.now(timezone.utc) > named_key.expires_at:
                    continue
                import asyncio
                is_valid, _ = await asyncio.to_thread(verify_password, api_key, named_key.key_hash)
                if is_valid:
                    # Update last_used
                    named_key.last_used = datetime.now(timezone.utc)
                    await db.commit()

                    from sqlalchemy.orm import joinedload
                    user_result = await db.execute(select(User).options(joinedload(User.team)).where(User.id == named_key.user_id, User.deleted_at == None))
                    user = user_result.scalar_one_or_none()
                    if user:
                        request.state.user_id = str(user.id)
                        log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)
                        return UserContext(
                            user_id=str(user.id),
                            plan=user.plan,
                            email=user.email,
                            name=user.name or "",
                            onboarding_complete=user.onboarding_complete,
                            team_id=str(user.team_id) if user.team_id else None,
                            team_role=user.team_role,
                        )

    # ── 3. No credentials found ───────────────────────────────────────────
    log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "No credentials provided"})
    raise AuthenticationError("Authentication required. Provide a Bearer token or X-API-Key header.")


def require_plan(minimum_plan: str):
    """
    FastAPI dependency factory that enforces a minimum plan tier.
    Usage:  Depends(require_plan(PlanTier.PRO))
    """
    async def _check(user: UserContext = Depends(verify_api_key)):
        user_level = PLAN_LEVELS.get(user.plan, 0)
        required   = PLAN_LEVELS.get(minimum_plan, 0)
        if user_level < required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires the {minimum_plan} plan. "
                       f"Upgrade at /pricing to unlock it.",
            )
        return user
    return _check
