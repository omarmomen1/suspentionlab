"""
backend/api/routes/audit_routes.py
===================================
Tamper-Evident Engineering Governance & Audit Endpoints.

Enterprise teams track, verify, filter, and export cryptographic proof of who ran what, when, from where.
Backed by the durable `audit_logs` and `audit_outbox` tables.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc, asc, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.audit import AuditLog, AuditOutbox
from suspensionlab.backend.security.audit import (
    verify_audit_db_chain_detailed,
    process_audit_outbox,
    build_canonical_audit_envelope,
    serialize_canonical_event,
)
from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.shared.models import PlanTier

router = APIRouter(prefix="/audit", tags=["audit"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    id: str
    sequence_number: int
    event: str
    user_id: str
    team_id: str | None = None
    artifact_id: str | None = None
    ip: str
    timestamp: str
    previous_hash: str
    hash: str
    metadata: dict
    canonical_event: Optional[str] = None


class VerificationResult(BaseModel):
    chain_integrity: str
    is_valid: bool
    total_records: int
    head_hash: Optional[str] = None
    error_details: Optional[dict] = None
    verified_at: str


class OutboxStatusResponse(BaseModel):
    pending: int
    processed: int
    failed: int
    dead_letter: int
    healthy: bool


def _require_enterprise(user: UserContext, action: str) -> None:
    if not user.can(Permission.AUDIT_READ):
        raise HTTPException(status_code=403, detail=f"Permission Denied: User lacks AUDIT_READ capability.")
    plan = getattr(user, "plan", "").upper()
    user_id = str(getattr(user, "user_id", ""))
    if plan not in ("ENTERPRISE", "PRO") and user_id != "admin-001":
        raise HTTPException(status_code=403, detail=f"{action} requires the Enterprise plan.")


async def _scoped_query(
    user: dict,
    db: AsyncSession,
    search: Optional[str] = None,
    event_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    artifact_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
):
    """Builds filtered query scoped to the user's team or individual permissions."""
    conditions = []

    # Cross-tenant organization access defense
    user_org = getattr(user, "organization_id", None)
    if organization_id is not None:
        if not user_org or str(organization_id) != str(user_org):
            raise HTTPException(status_code=403, detail="Cross-tenant access forbidden: Cannot access audit records of a different organization.")

    # Scope to user or team
    team_id = getattr(user, "team_id", None)
    if team_id:
        try:
            team_uuid = uuid.UUID(str(team_id))
            user_uuid = uuid.UUID(str(user.user_id))
            conditions.append(or_(AuditLog.team_id == team_uuid, AuditLog.user_id == user_uuid))
        except (ValueError, TypeError):
            conditions.append(AuditLog.user_id == uuid.UUID(str(user.user_id)))
    else:
        conditions.append(AuditLog.user_id == uuid.UUID(str(user.user_id)))

    if event_type:
        conditions.append(AuditLog.event.ilike(f"%{event_type}%"))

    if actor_id:
        try:
            conditions.append(AuditLog.user_id == uuid.UUID(str(actor_id)))
        except (ValueError, TypeError):
            pass

    if artifact_id:
        conditions.append(AuditLog.artifact_id.ilike(f"%{artifact_id}%"))

    if start_time:
        conditions.append(AuditLog.timestamp >= start_time)
    if end_time:
        conditions.append(AuditLog.timestamp <= end_time)

    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                AuditLog.event.ilike(search_pattern),
                AuditLog.artifact_id.ilike(search_pattern),
                AuditLog.ip.ilike(search_pattern),
                AuditLog.hash.ilike(search_pattern),
            )
        )

    return select(AuditLog).where(and_(*conditions))


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=list[AuditLogEntry])
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = None,
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    artifact_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    user: UserContext = Depends(require_permission(Permission.AUDIT_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Get durable, tamper-evident audit logs with filtering, search, and pagination."""
    _require_enterprise(user, "Audit logs")
    query = await _scoped_query(
        user, db,
        search=search,
        event_type=event_type,
        actor_id=user_id,
        artifact_id=artifact_id,
        organization_id=organization_id,
        start_time=start_time,
        end_time=end_time,
    )
    query = query.order_by(desc(AuditLog.sequence_number), desc(AuditLog.timestamp)).offset(skip).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    entries = []
    for log in logs:
        envelope = build_canonical_audit_envelope(
            event_type=log.event,
            user_id=str(log.user_id) if log.user_id else None,
            team_id=str(log.team_id) if log.team_id else None,
            organization_id=str(log.organization_id) if log.organization_id else None,
            ip=log.ip,
            artifact_id=log.artifact_id,
            sequence_number=log.sequence_number,
            timestamp=log.timestamp,
            event_data=log.event_data or {},
        )
        entries.append(
            AuditLogEntry(
                id=str(log.id),
                sequence_number=log.sequence_number or 1,
                event=log.event,
                user_id=str(log.user_id) if log.user_id else "anonymous",
                team_id=str(log.team_id) if log.team_id else None,
                artifact_id=log.artifact_id,
                ip=log.ip or "unknown",
                timestamp=log.timestamp.isoformat() if log.timestamp else "",
                previous_hash=log.previous_hash or "GENESIS",
                hash=log.hash or "",
                metadata=log.event_data or {},
                canonical_event=serialize_canonical_event(envelope),
            )
        )
    return entries


@router.get("/verify", response_model=VerificationResult)
async def verify_chain(
    user: UserContext = Depends(require_permission(Permission.AUDIT_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Live cryptographic verification of the team's tamper-evident hash chain."""
    _require_enterprise(user, "Audit verification")
    team_id_str = str(user.team_id) if getattr(user, "team_id", None) else None
    user_id_str = str(user.user_id) if not team_id_str else None

    is_valid, details = await verify_audit_db_chain_detailed(db, team_id=team_id_str, user_id=user_id_str)
    now_str = datetime.now(timezone.utc).isoformat()

    return VerificationResult(
        chain_integrity="VERIFIED_VALID" if is_valid else "TAMPER_DETECTED",
        is_valid=is_valid,
        total_records=details.get("total_records", 0),
        head_hash=details.get("head_hash"),
        error_details=details if not is_valid else None,
        verified_at=now_str,
    )


@router.get("/outbox/status", response_model=OutboxStatusResponse)
async def get_outbox_status(
    user: UserContext = Depends(require_permission(Permission.AUDIT_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Inspect transactional outbox health metrics (pending, processed, failed, dead-letter)."""
    _require_enterprise(user, "Outbox status")

    async def _count_status(s: str) -> int:
        q = select(func.count(AuditOutbox.id)).where(AuditOutbox.status == s)
        res = await db.execute(q)
        return int(res.scalar() or 0)

    pending = await _count_status("PENDING")
    processed = await _count_status("PROCESSED")
    failed = await _count_status("FAILED")
    dead_letter = await _count_status("DEAD_LETTER")

    return OutboxStatusResponse(
        pending=pending,
        processed=processed,
        failed=failed,
        dead_letter=dead_letter,
        healthy=(dead_letter == 0 and failed == 0),
    )


@router.post("/outbox/flush")
async def flush_outbox(
    max_batch: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(require_permission(Permission.AUDIT_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Process pending transactional outbox events sequentially into the hash chain."""
    _require_enterprise(user, "Outbox flush")
    result = await process_audit_outbox(db, max_batch=max_batch)
    return {"status": "ok", "processed_metrics": result}


@router.get("/export")
async def export_audit_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    search: Optional[str] = None,
    event_type: Optional[str] = None,
    organization_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    user: UserContext = Depends(require_permission(Permission.AUDIT_READ)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Export cryptographically verifiable tamper-evident audit records in CSV or JSON format."""
    _require_enterprise(user, "Audit log export")
    query = await _scoped_query(
        user, db,
        search=search,
        event_type=event_type,
        organization_id=organization_id,
        start_time=start_time,
        end_time=end_time,
    )
    query = query.order_by(asc(AuditLog.sequence_number), asc(AuditLog.timestamp)).limit(2000)
    res = await db.execute(query)
    logs = res.scalars().all()

    # Verify cryptographic integrity of the scoped chain
    team_id_str = str(user.team_id) if getattr(user, "team_id", None) else None
    user_id_str = str(user.user_id) if not team_id_str else None
    is_valid, details = await verify_audit_db_chain_detailed(db, team_id=team_id_str, user_id=user_id_str)
    integrity_status = "VERIFIED_VALID" if is_valid else "TAMPER_DETECTED"

    if format == "json":
        export_records = []
        for l in logs:
            env = build_canonical_audit_envelope(
                event_type=l.event,
                user_id=str(l.user_id) if l.user_id else None,
                team_id=str(l.team_id) if l.team_id else None,
                organization_id=str(l.organization_id) if l.organization_id else None,
                ip=l.ip,
                artifact_id=l.artifact_id,
                sequence_number=l.sequence_number,
                timestamp=l.timestamp,
                event_data=l.event_data or {},
            )
            export_records.append({
                "id": str(l.id),
                "sequence_number": l.sequence_number or 1,
                "event": l.event,
                "user_id": str(l.user_id) if l.user_id else None,
                "team_id": str(l.team_id) if l.team_id else None,
                "artifact_id": l.artifact_id,
                "ip": l.ip,
                "timestamp": l.timestamp.isoformat() if l.timestamp else "",
                "previous_hash": l.previous_hash or "GENESIS",
                "hash": l.hash or "",
                "metadata": l.event_data or {},
                "canonical_payload": serialize_canonical_event(env),
            })

        data = {
            "chain_integrity": integrity_status,
            "total_records": len(logs),
            "head_hash": details.get("head_hash"),
            "verification_algorithm": "SHA-256 Tamper-Evident Hash Chain",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "records": export_records,
        }
        return JSONResponse(content=data)

    elif format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Sequence #", "ID", "Event", "User ID", "Team ID", "Artifact ID", "IP", "Timestamp",
            "Previous Hash (SHA-256)", "Record Hash (SHA-256)", "Chain Integrity"
        ])
        for l in logs:
            writer.writerow([
                l.sequence_number or 1,
                str(l.id),
                l.event,
                str(l.user_id) if l.user_id else "",
                str(l.team_id) if l.team_id else "",
                l.artifact_id or "",
                l.ip or "",
                l.timestamp.isoformat() if l.timestamp else "",
                l.previous_hash or "GENESIS",
                l.hash or "",
                integrity_status,
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=audit_export.csv",
                "X-Audit-Chain-Integrity": integrity_status,
                "X-Audit-Head-Hash": details.get("head_hash") or "",
            },
        )


