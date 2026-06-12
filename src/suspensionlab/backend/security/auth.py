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


async def verify_api_key(
    request:  Request,
    api_key:  str | None = Header(alias="X-API-Key",      default=None),
    bearer:   str | None = Header(alias="Authorization",  default=None),
    db:       AsyncSession = Depends(get_db_dependency),
) -> dict:
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
            result  = await db.execute(select(User).where(User.id == user_uuid))
            user: User | None = result.scalar_one_or_none()
            if not user:
                log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "JWT user not found"})
                raise AuthenticationError("User not found.")
            request.state.user_id = str(user.id)
            log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)
            return {
                "user_id": str(user.id),
                "plan":    user.plan,
                "email":   user.email,
                "name":    user.name or "",
                "onboarding_complete": user.onboarding_complete,
                "team_id": str(user.team_id) if user.team_id else None,
            }
        # Token present but invalid — do not fall through to API key
        log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "Invalid Bearer token"})
        raise AuthenticationError("Invalid or expired token.")

    # ── 2. X-API-Key header ───────────────────────────────────────────────
    if api_key:
        # 2a. Master admin key (dev/CI only — warn if used in PROD)
        from suspensionlab.backend.config import settings
        import os
        if api_key == settings.admin_api_key:
            if os.getenv("ENVIRONMENT", "DEV") == "PROD":
                raise AuthenticationError("Master API key is disabled in production.")
            # Use a deterministic UUID for the admin user so downstream uuid.UUID() calls succeed
            _ADMIN_UUID = "00000000-0000-0000-0000-000000000001"
            log_audit_event("LOGIN_SUCCESS", user_id=_ADMIN_UUID, ip=ip)
            return {
                "user_id": _ADMIN_UUID,
                "plan":    PlanTier.ENTERPRISE,
                "email":   "admin@suspensionlab.io",
                "name":    "Admin",
                "onboarding_complete": True,
                "team_id": None,
            }

        # 2b. Look up legacy single-key on User table
        result = await db.execute(select(User).where(User.api_key == api_key))
        user: User | None = result.scalar_one_or_none()

        if user:
            if not user.onboarding_complete and request.url.path not in [
                "/auth/me", "/auth/onboard", "/billing/checkout", "/billing/webhooks/stripe",
            ]:
                raise AuthenticationError("Please complete onboarding before using simulation features.")
            request.state.user_id = str(user.id)
            log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)
            return {
                "user_id": str(user.id),
                "plan":    user.plan,
                "email":   user.email,
                "name":    user.name or "",
                "onboarding_complete": user.onboarding_complete,
                "team_id": str(user.team_id) if user.team_id else None,
            }

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
                if verify_password(api_key, named_key.key_hash):
                    # Update last_used
                    named_key.last_used = datetime.now(timezone.utc)
                    await db.commit()

                    user_result = await db.execute(select(User).where(User.id == named_key.user_id))
                    user = user_result.scalar_one_or_none()
                    if user:
                        request.state.user_id = str(user.id)
                        log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)
                        return {
                            "user_id": str(user.id),
                            "plan":    user.plan,
                            "email":   user.email,
                            "name":    user.name or "",
                            "onboarding_complete": user.onboarding_complete,
                            "team_id": str(user.team_id) if user.team_id else None,
                        }

    # ── 3. No credentials found ───────────────────────────────────────────
    log_audit_event("LOGIN_FAILURE", ip=ip, metadata={"reason": "No credentials provided"})
    raise AuthenticationError("Authentication required. Provide a Bearer token or X-API-Key header.")


def require_plan(minimum_plan: str):
    """
    FastAPI dependency factory that enforces a minimum plan tier.
    Usage:  Depends(require_plan(PlanTier.PRO))
    """
    async def _check(user: dict = Depends(verify_api_key)):
        user_level = PLAN_LEVELS.get(user.get("plan", PlanTier.FREE), 0)
        required   = PLAN_LEVELS.get(minimum_plan, 0)
        if user_level < required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires the {minimum_plan} plan. "
                       f"Upgrade at /pricing to unlock it.",
            )
        return user
    return _check
