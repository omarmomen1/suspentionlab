"""
backend/api/routes/auth_routes.py
Register, login, me, and logout endpoints.
"""
from __future__ import annotations

import secrets
import uuid
import json
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.jwt_utils import (
    hash_password, verify_password, create_access_token, create_refresh_token, decode_access_token, decode_refresh_token
)
from suspensionlab.backend.database.models.user_session import UserSession
from suspensionlab.backend.core.redis_client import get_async_redis_conn
from suspensionlab.shared.models import PlanTier

from suspensionlab.backend.security.jwt_utils import TokenRevocationRegistry, is_jti_revoked
from suspensionlab.backend.security.rate_limit import RateLimiter
from suspensionlab.backend.security.permissions import Permission, get_role_permissions
from suspensionlab.backend.config import settings


router = APIRouter(prefix="/auth", tags=["auth"])

async def _blacklist_jti(payload: dict, reason: str = "logout"):
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp: return
    TokenRevocationRegistry.revoke_jti(jti)
    now = datetime.now(timezone.utc).timestamp()
    ttl = int(exp - now)
    if ttl > 0:
        val = json.dumps({"jti": jti, "user_id": payload.get("sub"), "exp": exp, "reason": reason, "revoked_at": now})
        try:
            async_redis = get_async_redis_conn()
            if async_redis:
                await async_redis.setex(f"revoked:{jti}", ttl, val)
        except Exception:
            pass  # Handle redis failure gracefully

async def _is_revoked(jti: str) -> bool:
    return await is_jti_revoked(jti)


# ─── Schemas ─────────────────────────────────────────────────────────────────

class AuthResponse(BaseModel):
    token: str
    refresh_token: str
    user_id: str
    email: str
    name: str
    plan: str
    onboarding_complete: bool
    is_trial: bool = False
    trial_status: str | None = None
    trial_expires_at: str | None = None
    redirect_url: str = "/quarter-car"

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh", dependencies=[Depends(RateLimiter("rate_limit_refresh"))])
async def refresh_token_endpoint(
    request: Request,
    response: Response,
    req: RefreshRequest = None,
    db: AsyncSession = Depends(get_db_dependency)
):
    refresh_token = req.refresh_token if (req and req.refresh_token) else request.cookies.get("sl_refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing.")
        
    payload = decode_refresh_token(refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired.")
        
    if await _is_revoked(payload.get("jti")):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked.")
        
    # Rotate: Blacklist old refresh token
    await _blacklist_jti(payload, reason="rotation")
    
    if db:
        from sqlalchemy import delete
        await db.execute(delete(UserSession).where(UserSession.jti == payload.get("jti")))
        # FIXED: Added missing commit — without this, the DELETE was never persisted,
        # causing revoked session records to persist in the database.
        await db.commit()
    new_access_token = create_access_token({
        "sub": payload["sub"],
        "email": payload.get("email", ""),
        "plan": payload.get("plan", "FREE"),
    })
    new_refresh_token = create_refresh_token({
        "sub": payload["sub"],
        "email": payload.get("email", ""),
        "plan": payload.get("plan", "FREE"),
    })
    
    new_payload = decode_refresh_token(new_refresh_token)
    if new_payload:
        from user_agents import parse
        ua = request.headers.get("User-Agent", "Unknown")
        parsed_ua = parse(ua)
        user_agent_str = f"{parsed_ua.browser.family} on {parsed_ua.os.family}"
        device_type = "Mobile" if parsed_ua.is_mobile else ("Tablet" if parsed_ua.is_tablet else "Desktop")
        
        session = UserSession(
            user_id=uuid.UUID(payload["sub"]),
            jti=new_payload["jti"],
            user_agent=user_agent_str,
            ip_address=request.client.host if request.client else None,
            device_type=device_type,
            expires_at=datetime.fromtimestamp(new_payload["exp"], tz=timezone.utc).replace(tzinfo=None)
        )
        if db:
            db.add(session)
            await db.commit()
    
    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https" or (settings.environment == "PROD")
    response.set_cookie(key="sl_token", value=new_access_token, httponly=True, samesite="lax", secure=is_secure, path="/")
    response.set_cookie(key="sl_refresh_token", value=new_refresh_token, httponly=True, samesite="lax", secure=is_secure, path="/")
    
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, samesite="lax", secure=is_secure, path="/")
    
    return {"token": new_access_token, "refresh_token": new_refresh_token}

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = ""

    @field_validator("password")
    def password_complexity(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        import string
        if not any(c in string.punctuation for c in v):
            raise ValueError("Password must contain at least one special character")
        return v

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserMeResponse(BaseModel):
    user_id: str
    email: str
    name: str
    plan: str
    onboarding_complete: bool
    created_at: str
    team_id: str | None = None
    team_role: str | None = None
    org_role: str | None = None
    organization_id: str | None = None
    is_admin: bool = False
    is_trial: bool = False
    trial_status: str | None = None
    trial_expires_at: str | None = None
    redirect_url: str = "/quarter-car"
    permissions: list[str] = Field(default_factory=list)

# /set-cookie and /clear-cookie are no longer needed as login/logout set headers natively
@router.post("/clear-cookie")
async def clear_cookie(request: Request, response: Response, db: AsyncSession = Depends(get_db_dependency)):
    # Try to revoke the current refresh token
    rt = request.cookies.get("sl_refresh_token")
    if rt:
        payload = decode_refresh_token(rt)
        if payload:
            await _blacklist_jti(payload, reason="logout")
            from sqlalchemy import delete
            await db.execute(delete(UserSession).where(UserSession.jti == payload.get("jti")))
            await db.commit()
            
    # Also revoke access token if present
    at = request.cookies.get("sl_token")
    if at:
        payload = decode_access_token(at)
        if payload:
            await _blacklist_jti(payload, reason="logout")

    response.delete_cookie("sl_token", path="/")
    response.delete_cookie("sl_refresh_token", path="/")
    response.delete_cookie("sl_authed", path="/")
    response.delete_cookie("csrf_token", path="/")
    return {"status": "ok"}

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

@router.post("/forgot-password", dependencies=[Depends(RateLimiter("rate_limit_login"))])
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db_dependency)):
    """Generate a signed, time-limited reset token and send via email."""
    # FIXED: Accept email in request body (not query param) to prevent PII leaking
    # into server access logs, browser history, and proxy/CDN logs.
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user = result.scalar_one_or_none()
    
    if user:
        from suspensionlab.backend.services.email import send_password_reset_email
        from datetime import timedelta
        reset_token = create_access_token({"sub": str(user.id), "type": "password_reset"}, 
                                          expires_delta=timedelta(hours=1))
        await send_password_reset_email(user.email, reset_token)
    return {"status": "ok", "message": "If an account with that email exists, a reset link has been sent."}

@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db_dependency)):
    """Consume reset token and update password."""
    payload = decode_access_token(req.token)
    if not payload or payload.get("type") != "password_reset":
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")
    
    import uuid as _uuid
    try:
        user_uuid = _uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid token subject.")
    
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found.")
        
    loop = asyncio.get_running_loop()
    user.password_hash = await loop.run_in_executor(None, hash_password, req.new_password)
    await db.commit()
    # FIXED: Blacklist the reset token immediately after use to prevent link reuse.
    # Without this, the reset link could be used multiple times within its 1-hour window.
    await _blacklist_jti(payload, reason="password_reset_used")
    return {"status": "ok"}

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(RateLimiter("rate_limit_login"))])
async def register(request: Request, req: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db_dependency)):
    """Create a new account. Free plan by default, 14-day Pro trial."""
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == req.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user_id = uuid.uuid4()
    trial_end = datetime.now(timezone.utc) + timedelta(days=14)

    loop = asyncio.get_running_loop()
    hashed = await loop.run_in_executor(None, hash_password, req.password)

    user = User(
        id=user_id,
        email=req.email.lower(),
        password_hash=hashed,
        name=req.name or req.email.split("@")[0],
        plan=PlanTier.FREE.value,
        trial_ends_at=None,
        api_key=f"sk_{secrets.token_urlsafe(32)}",  # legacy single key
        onboarding_complete=False,
    )
    from sqlalchemy.exc import IntegrityError
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    token = create_access_token({"sub": str(user.id), "email": user.email, "plan": user.plan})
    r_token = create_refresh_token({"sub": str(user.id), "email": user.email})
    
    # Extract values before post-commit expiration
    u_id_str = str(user.id)
    u_email = user.email
    u_name = user.name or ""
    u_plan = user.plan
    u_onboarding = user.onboarding_complete
    
    # Create DB Session
    r_payload = decode_refresh_token(r_token)
    if r_payload:
        from user_agents import parse
        ua = request.headers.get("User-Agent", "Unknown")
        parsed_ua = parse(ua)
        user_agent_str = f"{parsed_ua.browser.family} on {parsed_ua.os.family}"
        device_type = "Mobile" if parsed_ua.is_mobile else ("Tablet" if parsed_ua.is_tablet else "Desktop")
        
        session_obj = UserSession(
            user_id=user.id,
            jti=r_payload["jti"],
            user_agent=user_agent_str,
            ip_address=request.client.host if request.client else None,
            device_type=device_type,
            expires_at=datetime.fromtimestamp(r_payload["exp"], tz=timezone.utc).replace(tzinfo=None)
        )
        db.add(session_obj)
        await db.commit()
    
    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https" or (settings.environment == "PROD")
    response.set_cookie(key="sl_token", value=token, httponly=True, samesite="lax", secure=is_secure, path="/")
    response.set_cookie(key="sl_refresh_token", value=r_token, httponly=True, samesite="lax", secure=is_secure, path="/")
    response.set_cookie(key="sl_authed", value="true", httponly=False, samesite="lax", secure=is_secure, path="/") # Helper for middleware
    
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, samesite="lax", secure=is_secure, path="/")
    
    return AuthResponse(
        token=token,
        refresh_token=r_token,
        user_id=u_id_str,
        email=u_email,
        name=u_name,
        plan=u_plan,
        onboarding_complete=u_onboarding,
    )


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(RateLimiter("rate_limit_login"))])
async def login(request: Request, req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db_dependency)):
    """Authenticate with email + password, returns JWT."""
    from suspensionlab.backend.security.rate_limit import check_progressive_penalty, record_login_failure
    try:
        await check_progressive_penalty(request, req.email)
    except Exception as e:
        if isinstance(e, HTTPException) or e.__class__.__name__ == "RateLimitExceededError":
            raise HTTPException(status_code=429, detail=str(e))

    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user: User | None = result.scalar_one_or_none()

    if not user:
        await record_login_failure(request, req.email)
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
        
    loop = asyncio.get_running_loop()
    is_valid, needs_rehash = await loop.run_in_executor(None, verify_password, req.password, user.password_hash)
    if not is_valid:
        await record_login_failure(request, req.email)
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
        
    if needs_rehash:
        user.password_hash = await loop.run_in_executor(None, hash_password, req.password)
        await db.commit()

    # Downgrade from trial if expired
    if user.plan == PlanTier.PRO and user.trial_ends_at:
        trial_end = user.trial_ends_at
        # Ensure comparison is timezone-aware
        now_utc = datetime.now(timezone.utc)
        if trial_end.tzinfo is None:
            from datetime import timezone as _tz
            trial_end = trial_end.replace(tzinfo=_tz.utc)
        if now_utc > trial_end:
            user.plan = PlanTier.FREE
            await db.commit()
            await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email, "plan": user.plan})
    r_token = create_refresh_token({"sub": str(user.id), "email": user.email})
    
    # Extract values before post-commit expiration
    u_id_str = str(user.id)
    u_email = user.email
    u_name = user.name or ""
    u_plan = user.plan
    u_onboarding = user.onboarding_complete
    
    # Create DB Session
    r_payload = decode_refresh_token(r_token)
    if r_payload:
        from user_agents import parse
        ua = request.headers.get("User-Agent", "Unknown")
        parsed_ua = parse(ua)
        user_agent_str = f"{parsed_ua.browser.family} on {parsed_ua.os.family}"
        device_type = "Mobile" if parsed_ua.is_mobile else ("Tablet" if parsed_ua.is_tablet else "Desktop")
        
        session_obj = UserSession(
            user_id=user.id,
            jti=r_payload["jti"],
            user_agent=user_agent_str,
            ip_address=request.client.host if request.client else None,
            device_type=device_type,
            expires_at=datetime.fromtimestamp(r_payload["exp"], tz=timezone.utc).replace(tzinfo=None)
        )
        db.add(session_obj)
        await db.commit()
    
    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https" or (settings.environment == "PROD")
    response.set_cookie(key="sl_token", value=token, httponly=True, samesite="lax", secure=is_secure, path="/")
    response.set_cookie(key="sl_refresh_token", value=r_token, httponly=True, samesite="lax", secure=is_secure, path="/")
    response.set_cookie(key="sl_authed", value="true", httponly=False, samesite="lax", secure=is_secure, path="/") # Helper for middleware
    
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, samesite="lax", secure=is_secure, path="/")

    from suspensionlab.backend.database.models.trial import Trial
    from sqlalchemy import or_
    trial_res = await db.execute(
        select(Trial).where(
            or_(Trial.user_id == user.id, Trial.organization_id == user.organization_id),
            Trial.deleted_at.is_(None)
        )
    )
    user_trial = trial_res.scalar_one_or_none()
    is_trial_user = bool(user_trial) or (user.plan == PlanTier.TRIAL.value)
    target_redirect = "/evaluation" if is_trial_user else "/quarter-car"

    t_status = None
    t_expires = None
    if user_trial:
        if user_trial.is_expired():
            user_trial.status = "EXPIRED"
        t_status = user_trial.status
        t_expires = user_trial.expires_at.isoformat() if user_trial.expires_at else None

    return AuthResponse(
        token=token,
        refresh_token=r_token,
        user_id=u_id_str,
        email=u_email,
        name=u_name,
        plan=u_plan,
        onboarding_complete=u_onboarding,
        is_trial=is_trial_user,
        trial_status=t_status,
        trial_expires_at=t_expires,
        redirect_url=target_redirect,
    )


@router.get("/me", response_model=UserMeResponse, dependencies=[Depends(RateLimiter("rate_limit_session"))])
async def get_me(request: Request, db: AsyncSession = Depends(get_db_dependency)):
    """Get current user info from Bearer token or HttpOnly cookie."""
    from suspensionlab.backend.security.jwt_utils import decode_access_token
    auth_header = request.headers.get("Authorization", "")
    token = None
    
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    else:
        token = request.cookies.get("sl_token")
        
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header or cookie.")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token is invalid or expired.")
    if await _is_revoked(payload.get("jti")):
        raise HTTPException(status_code=401, detail="Token has been revoked.")

    import uuid as _uuid
    try:
        user_uuid = _uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid token subject.")
    result = await db.execute(select(User).where(User.id == user_uuid))
    user: User | None = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    perms = set()
    if user.team_role:
        perms.update(get_role_permissions(user.team_role))
    if user.org_role:
        perms.update(get_role_permissions(user.org_role))
    if user.is_admin:
        perms.update([p.value for p in Permission])
    if not user.team_id and not user.organization_id and not user.team_role and not user.org_role:
        perms.update(get_role_permissions("owner"))

    from suspensionlab.backend.database.models.trial import Trial
    from sqlalchemy import or_
    trial_res = await db.execute(
        select(Trial).where(
            or_(Trial.user_id == user.id, Trial.organization_id == user.organization_id),
            Trial.deleted_at.is_(None)
        )
    )
    user_trial = trial_res.scalar_one_or_none()
    is_trial_user = bool(user_trial) or (user.plan == PlanTier.TRIAL.value)
    target_redirect = "/evaluation" if is_trial_user else "/quarter-car"
    t_status = None
    t_expires = None
    if user_trial:
        if user_trial.is_expired():
            user_trial.status = "EXPIRED"
        t_status = user_trial.status
        t_expires = user_trial.expires_at.isoformat() if user_trial.expires_at else None

    return UserMeResponse(
        user_id=str(user.id),
        email=user.email,
        name=user.name or "",
        plan=user.plan,
        onboarding_complete=user.onboarding_complete,
        created_at=user.created_at.isoformat() if user.created_at else "",
        team_id=str(user.team_id) if user.team_id else None,
        team_role=user.team_role,
        org_role=user.org_role,
        organization_id=str(user.organization_id) if user.organization_id else None,
        is_admin=False if is_trial_user else bool(user.is_admin),
        is_trial=is_trial_user,
        trial_status=t_status,
        trial_expires_at=t_expires,
        redirect_url=target_redirect,
        permissions=sorted(list(perms)),
    )


@router.get("/status", dependencies=[Depends(RateLimiter("rate_limit_session"))])
async def get_auth_status(request: Request):
    """Lightweight session/health validation endpoint."""
    from suspensionlab.backend.security.jwt_utils import decode_access_token
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    else:
        token = request.cookies.get("sl_token")

    if not token:
        return {"authenticated": False, "status": "unauthenticated"}
    payload = decode_access_token(token)
    if not payload:
        return {"authenticated": False, "status": "expired"}
    if await _is_revoked(payload.get("jti")):
        return {"authenticated": False, "status": "revoked"}
    return {
        "authenticated": True,
        "user_id": payload.get("sub"),
        "status": "active",
        "plan": payload.get("plan", "FREE"),
    }


@router.post("/onboard")
async def complete_onboarding(request: Request, db: AsyncSession = Depends(get_db_dependency)):
    """Mark the user's onboarding as complete."""
    from suspensionlab.backend.security.jwt_utils import decode_access_token
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        token = request.cookies.get("sl_token", "").strip()

    payload = decode_access_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token.")

    # FIXED: Check token revocation — a logged-out token must not complete onboarding.
    if await _is_revoked(payload.get("jti", "")):
        raise HTTPException(status_code=401, detail="Token has been revoked.")

    import uuid as _uuid
    try:
        user_uuid = _uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid token subject.")
    result = await db.execute(select(User).where(User.id == user_uuid, User.deleted_at == None))
    user: User | None = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.onboarding_complete = True
    await db.commit()
    return {"status": "ok"}
