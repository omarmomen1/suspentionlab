import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user_session import UserSession
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.jwt_utils import decode_access_token
import uuid
import asyncio

router = APIRouter(prefix="/auth/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)

async def get_current_user_id(request: Request) -> uuid.UUID:
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    else:
        token = request.cookies.get("sl_token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    try:
        return uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid subject")

@router.get("")
async def get_sessions(request: Request, db: AsyncSession = Depends(get_db_dependency)):
    """List all active sessions for the current user."""
    user_id = await get_current_user_id(request)
    result = await db.execute(select(UserSession).where(UserSession.user_id == user_id))
    sessions = result.scalars().all()
    
    return {
        "sessions": [
            {
                "jti": s.jti,
                "user_agent": s.user_agent,
                "ip_address": s.ip_address,
                "device_type": s.device_type,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
            }
            for s in sessions
        ]
    }

@router.delete("/{jti}")
async def revoke_session(jti: str, request: Request, db: AsyncSession = Depends(get_db_dependency)):
    """Revoke a specific session by jti."""
    user_id = await get_current_user_id(request)
    
    result = await db.execute(select(UserSession).where(UserSession.user_id == user_id, UserSession.jti == jti))
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    from suspensionlab.backend.api.routes.auth_routes import _blacklist_jti
    await _blacklist_jti({"jti": jti, "sub": str(user_id), "exp": session.expires_at.timestamp()}, reason="user_revoked")
    
    await db.execute(delete(UserSession).where(UserSession.jti == jti))
    await db.commit()
    
    return {"status": "ok", "message": "Session revoked"}

@router.delete("")
async def revoke_all_other_sessions(request: Request, db: AsyncSession = Depends(get_db_dependency)):
    """Revoke all sessions except the current one."""
    user_id = await get_current_user_id(request)
    
    rt = request.cookies.get("sl_refresh_token")
    current_jti = None
    if rt:
        from suspensionlab.backend.security.jwt_utils import decode_refresh_token
        payload = decode_refresh_token(rt)
        if payload:
            current_jti = payload.get("jti")
            
    result = await db.execute(select(UserSession).where(UserSession.user_id == user_id))
    sessions = result.scalars().all()
    
    from suspensionlab.backend.api.routes.auth_routes import _blacklist_jti
    for session in sessions:
        if current_jti and session.jti == current_jti:
            continue
        await _blacklist_jti({"jti": session.jti, "sub": str(user_id), "exp": session.expires_at.timestamp()}, reason="user_revoked_all")
        await db.execute(delete(UserSession).where(UserSession.jti == session.jti))
        
    await db.commit()
    return {"status": "ok", "message": "All other sessions revoked"}
