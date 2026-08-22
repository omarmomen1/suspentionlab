"""
backend/api/routes/audit_routes.py
===================================
Audit log endpoints — Enterprise teams track who ran what, when, from where.

Backed by the durable `audit_logs` table (#23). ENTERPRISE users see their
team's trail (plus their own personal events); plain users are rejected.
"""
from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.shared.models import PlanTier

router = APIRouter(prefix="/audit", tags=["audit"])

# ─── Schemas ─────────────────────────────────────────────────────────────────


class AuditLogEntry(BaseModel):
    id: str
    event: str
    user_id: str
    team_id: str | None = None
    ip: str
    timestamp: str
    metadata: dict


async def _scoped_logs(user: dict, db: AsyncSession, skip: int = 0, limit: int = 100):
    """Return audit rows visible to this user: own events + their team's."""
    conditions = [AuditLog.user_id == uuid.UUID(user.user_id)]
    if getattr(user, "team_id", None):
        conditions.append(AuditLog.team_id == uuid.UUID(user.team_id))
    result = await db.execute(
        select(AuditLog)
        .where(or_(*conditions))
        .order_by(desc(AuditLog.timestamp))
        .offset(skip)
        .limit(min(limit, 500))
    )
    return result.scalars().all()


def _require_enterprise(user: dict, action: str) -> None:
    if user.plan not in (PlanTier.ENTERPRISE,) and user.user_id != "admin-001":
        raise HTTPException(status_code=403, detail=f"{action} requires the Enterprise plan.")


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/logs", response_model=list[AuditLogEntry])
async def get_audit_logs(
    skip: int = 0,
    limit: int = 100,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Get durable audit logs — restricted to Enterprise tier, team-scoped."""
    _require_enterprise(user, "Audit logs")
    logs = await _scoped_logs(user, db, skip, limit)
    return [
        AuditLogEntry(
            id=str(log.id),
            event=log.event,
            user_id=str(log.user_id) if log.user_id else "anonymous",
            team_id=str(log.team_id) if log.team_id else None,
            ip=log.ip or "unknown",
            timestamp=log.timestamp.isoformat() if log.timestamp else "",
            metadata=log.event_data or {},
        )
        for log in logs
    ]


@router.get("/export")
async def export_audit_logs(
    format: str = "csv",
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    _require_enterprise(user, "Audit log export")
    logs = await _scoped_logs(user, db, skip=0, limit=500)

    if format == "json":
        data = [
            {
                "id": str(l.id),
                "event": l.event,
                "user_id": str(l.user_id) if l.user_id else None,
                "team_id": str(l.team_id) if l.team_id else None,
                "ip": l.ip,
                "timestamp": l.timestamp.isoformat() if l.timestamp else "",
                "metadata": l.event_data or {},
            }
            for l in logs
        ]
        return JSONResponse(content=data)

    elif format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Event", "User ID", "Team ID", "IP", "Timestamp"])
        for l in logs:
            writer.writerow([
                str(l.id), l.event,
                str(l.user_id) if l.user_id else "",
                str(l.team_id) if l.team_id else "",
                l.ip or "", l.timestamp.isoformat() if l.timestamp else "",
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'csv' or 'json'.")
