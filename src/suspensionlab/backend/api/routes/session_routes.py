import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.session import SimSession, SessionComment
from suspensionlab.backend.security.auth import verify_api_key, require_plan
from suspensionlab.shared.models import PlanTier

router = APIRouter(prefix="/sessions", tags=["Collaboration Hub"])

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_session(
    name: str = "New Session",
    db: AsyncSession = Depends(get_db_dependency),
    user: dict = Depends(require_plan(PlanTier.ENTERPRISE))
):
    """Create a new shared simulation session (ENTERPRISE only)."""
    session = SimSession(
        owner_id=uuid.UUID(user["user_id"]),
        team_id=uuid.UUID(user["team_id"]) if user.get("team_id") else None,
        name=name,
        params_snapshot={}
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"session_id": str(session.id), "name": session.name}

@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db_dependency),
    user: dict = Depends(verify_api_key)
):
    """Fetch session details and its comments."""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")
        
    result = await db.execute(select(SimSession).where(SimSession.id == session_uuid))
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Team members or owner can access
    user_team = user.get("team_id")
    if str(session.owner_id) != user["user_id"] and str(session.team_id) != user_team:
        raise HTTPException(status_code=403, detail="Not authorized to view this session")
        
    comments_result = await db.execute(
        select(SessionComment).where(SessionComment.session_id == session_uuid).order_by(SessionComment.created_at)
    )
    comments = comments_result.scalars().all()
    
    return {
        "session_id": str(session.id),
        "name": session.name,
        "owner_id": str(session.owner_id),
        "team_id": str(session.team_id) if session.team_id else None,
        "params_snapshot": session.params_snapshot,
        "comments": [
            {
                "id": str(c.id),
                "author_id": str(c.author_id),
                "content": c.content,
                "chart_region": c.chart_region,
                "created_at": c.created_at.isoformat()
            } for c in comments
        ]
    }

@router.post("/{session_id}/join")
async def join_session(
    session_id: str,
    db: AsyncSession = Depends(get_db_dependency),
    user: dict = Depends(verify_api_key)
):
    """Join an active session. In this implementation, it validates access."""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")
        
    result = await db.execute(select(SimSession).where(SimSession.id == session_uuid))
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    user_team = user.get("team_id")
    if str(session.owner_id) != user["user_id"] and str(session.team_id) != user_team:
        raise HTTPException(status_code=403, detail="Not authorized to join this session")
        
    return {"status": "joined", "session_id": str(session.id)}
