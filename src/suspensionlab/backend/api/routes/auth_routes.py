"""
backend/api/routes/auth_routes.py
Register, login, me, and logout endpoints.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.jwt_utils import (
    hash_password, verify_password, create_access_token, create_refresh_token, decode_access_token
)
from suspensionlab.shared.models import PlanTier

router = APIRouter(prefix="/auth", tags=["auth"])

# ─── Schemas ─────────────────────────────────────────────────────────────────

class AuthResponse(BaseModel):
    token: str
    refresh_token: str
    user_id: str
    email: str
    name: str
    plan: str
    onboarding_complete: bool

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh")
async def refresh_token_endpoint(request: Request, response: Response, req: RefreshRequest = None):
    from suspensionlab.backend.security.jwt_utils import decode_refresh_token, create_access_token
    
    refresh_token = (req.refresh_token if req else None) or request.cookies.get("sl_refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing.")
        
    payload = decode_refresh_token(refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired.")
    
    new_access_token = create_access_token({
        "sub": payload["sub"],
        "email": payload.get("email", ""),
        "plan": payload.get("plan", "FREE"),
    })
    
    response.set_cookie(
        key="sl_token",
        value=new_access_token,
        httponly=True,
        samesite="strict",
        path="/"
    )
    
    return {"token": new_access_token}

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""

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
    team_id: str | None

# /set-cookie and /clear-cookie are no longer needed as login/logout set headers natively
@router.post("/clear-cookie")
async def clear_cookie(response: Response):
    response.delete_cookie("sl_token", path="/")
    response.delete_cookie("sl_refresh_token", path="/")
    response.delete_cookie("sl_authed", path="/")
    return {"status": "ok"}

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@router.post("/forgot-password")
async def forgot_password(email: str, db: AsyncSession = Depends(get_db_dependency)):
    """Generate a signed, time-limited reset token and send via email."""
    result = await db.execute(select(User).where(User.email == email.lower()))
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
        
    user.password_hash = hash_password(req.new_password)
    await db.commit()
    return {"status": "ok"}

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db_dependency)):
    """Create a new account. Free plan by default, 14-day Pro trial."""
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == req.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user_id = uuid.uuid4()
    trial_end = datetime.now(timezone.utc) + timedelta(days=14)

    user = User(
        id=user_id,
        email=req.email.lower(),
        password_hash=hash_password(req.password),
        name=req.name or req.email.split("@")[0],
        plan=PlanTier.FREE.value,
        trial_ends_at=None,
        api_key=f"sk_{secrets.token_urlsafe(32)}",  # legacy single key
        onboarding_complete=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email, "plan": user.plan})
    r_token = create_refresh_token({"sub": str(user.id), "email": user.email})
    
    response.set_cookie(key="sl_token", value=token, httponly=True, samesite="strict", path="/")
    response.set_cookie(key="sl_refresh_token", value=r_token, httponly=True, samesite="strict", path="/")
    response.set_cookie(key="sl_authed", value="true", httponly=False, samesite="strict", path="/") # Helper for middleware
    
    return AuthResponse(
        token=token,
        refresh_token=r_token,
        user_id=str(user.id),
        email=user.email,
        name=user.name or "",
        plan=user.plan,
        onboarding_complete=user.onboarding_complete,
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db_dependency)):
    """Authenticate with email + password, returns JWT."""
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user: User | None = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

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
    
    response.set_cookie(key="sl_token", value=token, httponly=True, samesite="strict", path="/")
    response.set_cookie(key="sl_refresh_token", value=r_token, httponly=True, samesite="strict", path="/")
    response.set_cookie(key="sl_authed", value="true", httponly=False, samesite="strict", path="/") # Helper for middleware
    
    return AuthResponse(
        token=token,
        refresh_token=r_token,
        user_id=str(user.id),
        email=user.email,
        name=user.name or "",
        plan=user.plan,
        onboarding_complete=user.onboarding_complete,
    )


@router.get("/me", response_model=UserMeResponse)
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

    import uuid as _uuid
    try:
        user_uuid = _uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid token subject.")
    result = await db.execute(select(User).where(User.id == user_uuid))
    user: User | None = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return UserMeResponse(
        user_id=str(user.id),
        email=user.email,
        name=user.name or "",
        plan=user.plan,
        onboarding_complete=user.onboarding_complete,
        created_at=user.created_at.isoformat() if user.created_at else "",
        team_id=str(user.team_id) if user.team_id else None,
    )


@router.post("/onboard")
async def complete_onboarding(request: Request, db: AsyncSession = Depends(get_db_dependency)):
    """Mark the user's onboarding as complete."""
    from suspensionlab.backend.security.jwt_utils import decode_access_token
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token.")

    import uuid as _uuid
    try:
        user_uuid = _uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid token subject.")
    result = await db.execute(select(User).where(User.id == user_uuid))
    user: User | None = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.onboarding_complete = True
    await db.commit()
    return {"status": "ok"}
