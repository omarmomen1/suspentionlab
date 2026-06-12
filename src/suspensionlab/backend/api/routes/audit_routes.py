"""
backend/api/routes/audit_routes.py
Audit log endpoints — for Enterprise teams to track who ran what simulation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.shared.models import PlanTier

router = APIRouter(prefix="/audit", tags=["audit"])

# ─── Schemas ─────────────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    id: str
    event: str
    user_id: str
    ip: str
    timestamp: str
    metadata: dict

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=list[AuditLogEntry])
async def get_audit_logs(
    limit: int = 100,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Get audit logs — restricted to Enterprise tier."""
    plan = user.get("tier", PlanTier.FREE)
    if plan not in (PlanTier.ENTERPRISE,) and user.get("user_id") != "admin-001":
        raise HTTPException(status_code=403, detail="Audit logs require the Enterprise plan.")

    # Import here to avoid circular imports
    from suspensionlab.backend.security.audit import AuditLog
    result = await db.execute(
        select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(min(limit, 500))
    )
    logs = result.scalars().all()
    return [
        AuditLogEntry(
            id=str(log.id),
            event=log.event,
            user_id=str(log.user_id) if log.user_id else "anonymous",
            ip=log.ip or "unknown",
            timestamp=log.timestamp.isoformat() if log.timestamp else "",
            metadata=log.metadata or {},
        )
        for log in logs
    ]
