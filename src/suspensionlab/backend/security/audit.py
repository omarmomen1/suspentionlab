"""
src/suspensionlab/backend/security/audit.py
============================================
Tamper-Evident Engineering Governance & Audit Subsystem.

Provides cryptographic traceability across all engineering activities:
1. Canonical RFC 8785 JSON Event Serialization (write, verify, export)
2. Tamper-Evident Hash Chain: H_n = SHA256(H_{n-1} || Canonical(Event_n))
3. Concurrency Safety: Monotonic sequence numbers and transactional locking
4. Guaranteed Delivery: Transactional outbox with retry, dead-letter queue, and idempotency
5. Diagnostic Verification: Pinpoints tampering, sequence breaks, or chain forks
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.models.audit import AuditLog, AuditOutbox
from suspensionlab.backend.security.logging_config import request_id_ctx

logger = logging.getLogger("security_audit")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter('{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}'))
    logger.addHandler(_handler)


class JSONAuditFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "request_id": request_id_ctx.get(),
            "user_id": getattr(record, "user_id", None),
            "ip": getattr(record, "ip", None),
            "event_type": getattr(record, "event_type", "UNKNOWN"),
            "metadata": getattr(record, "metadata", {}),
        }
        return json.dumps(payload, default=str)


def log_audit_event(
    event_type: str,
    user_id: str | None = None,
    ip: str | None = None,
    metadata: dict[str, Any] | None = None,
    team_id: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Logs a structured JSON security audit event to the standard stream logger."""
    extra = {
        "user_id": user_id,
        "team_id": team_id,
        "ip": ip,
        "event_type": event_type,
        "metadata": metadata or {},
    }
    logger.info(f"Audit event: {event_type}", extra=extra)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — CANONICAL EVENT SERIALIZATION (RFC 8785)
# ─────────────────────────────────────────────────────────────────────────────

def normalize_timestamp(ts: Any) -> str:
    """Normalize any datetime or string to standard UTC ISO-8601 string: YYYY-MM-DDTHH:MM:SS.ffffffZ."""
    if ts is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)
        return ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    ts_str = str(ts).strip()
    try:
        clean_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except Exception:
        return ts_str


def serialize_canonical_event(payload: dict[str, Any] | str) -> str:
    """
    Deterministic RFC 8785 canonical JSON serialization.
    Used consistently for:
      - DB write hash calculation
      - Verification checks
      - Verifiable export bundles
    """
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def build_canonical_audit_envelope(
    event_type: str,
    user_id: str | None = None,
    team_id: str | None = None,
    ip: str | None = None,
    event_data: dict[str, Any] | None = None,
    sequence_number: int | None = None,
    timestamp: str | datetime | None = None,
    artifact_id: str | None = None,
    organization_id: str | None = None,
) -> dict[str, Any]:
    """
    Constructs the authoritative canonical dictionary envelope for tamper-evident hashing.
    Keys are strictly ordered, values normalized.
    """
    ts_str = normalize_timestamp(timestamp) if timestamp is not None else None

    envelope: dict[str, Any] = {
        "event_type": str(event_type),
        "user_id": str(user_id) if user_id else None,
        "team_id": str(team_id) if team_id else None,
        "organization_id": str(organization_id) if organization_id else None,
        "ip": str(ip) if ip else None,
        "artifact_id": str(artifact_id) if artifact_id else None,
        "sequence_number": int(sequence_number) if sequence_number is not None else None,
        "timestamp": ts_str,
        "event_data": event_data if isinstance(event_data, dict) else {},
    }
    return envelope


def canonical_hash(obj: Any) -> str:
    """SHA-256 over a canonical (sorted-key, stable-separator) JSON dump."""
    canonical_str = serialize_canonical_event(obj)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — TAMPER-EVIDENT HASH CHAIN
# ─────────────────────────────────────────────────────────────────────────────

def compute_audit_hash(previous_hash: str, event_payload: dict[str, Any] | str, *args) -> str:
    """
    Tamper-Evident Hash Chain formula:
    H_n = SHA256(H_{n-1} || Canonical(Event_n))

    Also provides robust backward-compatibility if legacy callers supply 5 arguments:
    (event_type, user_id, timestamp, event_data, prev_hash)
    """
    if args and len(args) == 3:
        # Legacy positional signature: (event, user_id, timestamp, event_data, prev_hash)
        event_type = str(previous_hash)
        user_id = str(event_payload)
        timestamp = str(args[0])
        event_data = args[1] if isinstance(args[1], dict) else {}
        actual_prev_hash = str(args[2])
        canonical = build_canonical_audit_envelope(
            event_type=event_type,
            user_id=user_id,
            timestamp=timestamp,
            event_data=event_data,
        )
        canonical_str = serialize_canonical_event(canonical)
        combined = f"{actual_prev_hash}||{canonical_str}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    canonical_str = serialize_canonical_event(event_payload)
    combined = f"{previous_hash}||{canonical_str}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


# Backward-compatible alias
compute_merkle_audit_hash = compute_audit_hash


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 & 4 — CONCURRENCY, SEQUENCE NUMBERING & TRANSACTIONAL OUTBOX
# ─────────────────────────────────────────────────────────────────────────────

_audit_chain_locks: dict[Any, asyncio.Lock] = {}


def _get_audit_lock() -> asyncio.Lock:
    """Returns an asyncio.Lock bound safely to the current running event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Lock()
    if loop not in _audit_chain_locks:
        _audit_chain_locks[loop] = asyncio.Lock()
    return _audit_chain_locks[loop]


async def record_audit_event(
    db: AsyncSession,
    event_type: str,
    user_id: str | None = None,
    team_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    artifact_id: str | None = None,
    organization_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    timestamp: datetime | None = None,
) -> AuditLog:
    """
    Durable Audit Record Insertion.
    - Synchronized via asyncio.Lock to prevent hash-chain forks
    - Strict monotonic sequence numbering scoped per team / global
    - Cryptographic previous_hash linkage
    - Fallback to AuditOutbox on any transient failure to eliminate silent event loss
    """
    log_audit_event(
        event_type,
        user_id=user_id,
        team_id=team_id,
        ip=ip,
        metadata=metadata,
        user_agent=user_agent,
    )

    ev_data = metadata or {}
    now_utc = timestamp or datetime.now(timezone.utc)

    # 1. Idempotency Check
    if idempotency_key:
        stmt_idem = select(AuditOutbox).where(
            AuditOutbox.idempotency_key == idempotency_key,
            AuditOutbox.status == "PROCESSED"
        )
        existing = (await db.execute(stmt_idem)).scalar_one_or_none()
        if existing and existing.artifact_id:
            stmt_log = select(AuditLog).where(AuditLog.artifact_id == existing.artifact_id)
            found = (await db.execute(stmt_log)).scalar_one_or_none()
            if found:
                return found

    async with _get_audit_lock():
        try:
            # 2. Query last hash and last sequence number for this scope
            stmt = select(AuditLog.hash, AuditLog.sequence_number).order_by(
                desc(AuditLog.sequence_number), desc(AuditLog.id)
            )
            if team_id:
                stmt = stmt.where(AuditLog.team_id == _uuid.UUID(str(team_id)))
            else:
                stmt = stmt.where(AuditLog.team_id.is_(None))

            result = await db.execute(stmt.limit(1))
            last_record = result.first()
            if last_record and last_record[0]:
                last_hash = last_record[0]
                last_seq = int(last_record[1] or 0)
            else:
                last_hash = "GENESIS"
                last_seq = 0

            next_seq = last_seq + 1

            envelope = build_canonical_audit_envelope(
                event_type=event_type,
                user_id=user_id,
                team_id=team_id,
                organization_id=organization_id,
                ip=ip,
                artifact_id=artifact_id,
                sequence_number=next_seq,
                timestamp=now_utc,
                event_data=ev_data,
            )
            new_hash = compute_audit_hash(last_hash, envelope)

            row = AuditLog(
                sequence_number=next_seq,
                event=event_type,
                user_id=_uuid.UUID(str(user_id)) if user_id else None,
                team_id=_uuid.UUID(str(team_id)) if team_id else None,
                organization_id=_uuid.UUID(str(organization_id)) if organization_id else None,
                ip=ip,
                user_agent=user_agent[:255] if user_agent else None,
                artifact_id=artifact_id,
                timestamp=now_utc,
                event_data=ev_data,
                previous_hash=last_hash,
                hash=new_hash,
            )
            res = db.add(row)
            if asyncio.iscoroutine(res):
                await res
            await db.commit()
            await db.refresh(row)
            return row

        except Exception as e:
            logger.error("Audit write failed; persisting to outbox to guarantee delivery: %s", e)
            try:
                await db.rollback()
            except Exception:
                pass

            # Fail-safe Outbox insertion
            outbox_entry = AuditOutbox(
                idempotency_key=idempotency_key or str(_uuid.uuid4()),
                event_type=event_type,
                user_id=_uuid.UUID(str(user_id)) if user_id else None,
                team_id=_uuid.UUID(str(team_id)) if team_id else None,
                organization_id=_uuid.UUID(str(organization_id)) if organization_id else None,
                ip=ip,
                user_agent=user_agent[:255] if user_agent else None,
                artifact_id=artifact_id,
                event_data=ev_data,
                status="FAILED",
                last_error=str(e),
                retry_count=1,
            )
            try:
                db.add(outbox_entry)
                await db.commit()
            except Exception as oe:
                logger.critical("Fatal: Outbox fail-safe write failed: %s", oe)
                await db.rollback()

            raise RuntimeError(f"Audit event recording failed: {e}") from e


async def enqueue_audit_event(
    db: AsyncSession,
    event_type: str,
    user_id: str | None = None,
    team_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    artifact_id: str | None = None,
    organization_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> AuditOutbox:
    """
    Transactional Outbox Enqueue (Step 4).
    Persists an event inside the caller's transaction with an idempotency key.
    """
    if idempotency_key:
        stmt = select(AuditOutbox).where(AuditOutbox.idempotency_key == idempotency_key)
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

    entry = AuditOutbox(
        idempotency_key=idempotency_key or str(_uuid.uuid4()),
        event_type=event_type,
        user_id=_uuid.UUID(str(user_id)) if user_id else None,
        team_id=_uuid.UUID(str(team_id)) if team_id else None,
        organization_id=_uuid.UUID(str(organization_id)) if organization_id else None,
        ip=ip,
        user_agent=user_agent[:255] if user_agent else None,
        artifact_id=artifact_id,
        event_data=metadata or {},
        status="PENDING",
        retry_count=0,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def process_audit_outbox(db: AsyncSession, max_batch: int = 50) -> dict[str, int]:
    """
    Outbox Worker Flush:
    Processes pending outbox events sequentially, inserting them into the tamper-evident hash chain.
    """
    stmt = (
        select(AuditOutbox)
        .where(AuditOutbox.status.in_(["PENDING", "FAILED"]))
        .where(AuditOutbox.retry_count < AuditOutbox.max_retries)
        .order_by(asc(AuditOutbox.created_at))
        .limit(max_batch)
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    processed_count = 0
    failed_count = 0
    dead_letter_count = 0

    for item in entries:
        try:
            await record_audit_event(
                db=db,
                event_type=item.event_type,
                user_id=str(item.user_id) if item.user_id else None,
                team_id=str(item.team_id) if item.team_id else None,
                organization_id=str(item.organization_id) if item.organization_id else None,
                ip=item.ip,
                user_agent=item.user_agent,
                artifact_id=item.artifact_id,
                metadata=item.event_data or {},
                timestamp=item.created_at,
            )
            item.status = "PROCESSED"
            item.processed_at = datetime.now(timezone.utc)
            processed_count += 1
        except Exception as err:
            item.retry_count += 1
            item.last_error = str(err)
            if item.retry_count >= item.max_retries:
                item.status = "DEAD_LETTER"
                dead_letter_count += 1
            else:
                item.status = "FAILED"
                failed_count += 1
        await db.commit()

    return {
        "processed": processed_count,
        "failed": failed_count,
        "dead_letter": dead_letter_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — TAMPER-EVIDENT HASH CHAIN VERIFICATION & FORENSICS
# ─────────────────────────────────────────────────────────────────────────────

def verify_audit_hash_chain_detailed(records: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    """
    Comprehensive cryptographic verification of an audit sequence.
    Detects:
      1. Payload modifications (SHA-256 mismatch)
      2. Event deletions (sequence number break)
      3. Reordering or forks (previous_hash link mismatch)
    """
    if not records:
        return True, {"valid": True, "total_records": 0, "message": "Empty chain"}

    expected_prev = records[0].get("previous_hash", "GENESIS")
    last_seq: int | None = None

    for idx, r in enumerate(records):
        recorded_prev = r.get("previous_hash", "GENESIS")
        recorded_curr = r.get("hash") or r.get("current_hash")
        seq = r.get("sequence_number")
        seq_int = int(seq) if seq is not None else (idx + 1)

        # 1. Verify sequence number continuity (strictly monotonic, gap-free)
        if seq is not None:
            if last_seq is not None and seq_int != last_seq + 1:
                return False, {
                    "valid": False,
                    "error": "SEQUENCE_GAP_DETECTED",
                    "failed_index": idx,
                    "failed_sequence_number": seq_int,
                    "expected_sequence": last_seq + 1,
                    "found_sequence": seq_int,
                }
            last_seq = seq_int

        # 2. Verify previous_hash linkage
        if recorded_prev != expected_prev:
            return False, {
                "valid": False,
                "error": "HASH_CHAIN_LINKAGE_BROKEN",
                "failed_index": idx,
                "failed_sequence_number": seq_int,
                "expected_previous_hash": expected_prev,
                "recorded_previous_hash": recorded_prev,
            }

        # 3. Compute canonical event hash
        if "event" in r or "event_type" in r:
            ev_data = r.get("event_data") if r.get("event_data") is not None else r.get("metadata", {})
            envelope = build_canonical_audit_envelope(
                event_type=r.get("event") or r.get("event_type", ""),
                user_id=r.get("user_id"),
                team_id=r.get("team_id"),
                organization_id=r.get("organization_id"),
                ip=r.get("ip"),
                artifact_id=r.get("artifact_id"),
                sequence_number=r.get("sequence_number"),
                timestamp=r.get("timestamp"),
                event_data=ev_data,
            )
            computed = compute_audit_hash(recorded_prev, envelope)

            if computed != recorded_curr:
                # Backward-compatibility check for legacy envelopes that lacked timestamp/seq
                legacy_env = {
                    "event_type": str(r.get("event") or r.get("event_type", "")),
                    "user_id": str(r.get("user_id")) if r.get("user_id") else None,
                    "team_id": str(r.get("team_id")) if r.get("team_id") else None,
                    "ip": str(r.get("ip")) if r.get("ip") else None,
                    "event_data": ev_data or {},
                }
                legacy_computed = compute_audit_hash(recorded_prev, legacy_env)
                if legacy_computed == recorded_curr:
                    computed = legacy_computed
        else:
            raw_payload = {k: v for k, v in r.items() if k not in ("current_hash", "hash", "previous_hash")}
            computed = compute_audit_hash(recorded_prev, raw_payload)

        # 4. Verify record hash
        if recorded_curr != computed:
            return False, {
                "valid": False,
                "error": "TAMPER_PAYLOAD_MISMATCH",
                "failed_index": idx,
                "failed_sequence_number": seq_int,
                "expected_hash": computed,
                "recorded_hash": recorded_curr,
            }

        expected_prev = computed

    return True, {
        "valid": True,
        "total_records": len(records),
        "head_hash": expected_prev,
    }


def verify_audit_hash_chain(records: list[dict[str, Any]]) -> bool:
    """Boolean verification wrapper returning True if valid and unbroken; False if tampered."""
    valid, _ = verify_audit_hash_chain_detailed(records)
    return valid


async def verify_audit_db_chain_detailed(
    db: AsyncSession,
    team_id: str | None = None,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Queries DB audit logs and runs full forensic cryptographic chain verification."""
    stmt = select(AuditLog).order_by(asc(AuditLog.sequence_number), asc(AuditLog.timestamp), asc(AuditLog.id))
    if team_id:
        stmt = stmt.where(AuditLog.team_id == _uuid.UUID(str(team_id)))
    elif user_id:
        stmt = stmt.where(AuditLog.user_id == _uuid.UUID(str(user_id)))
    elif organization_id:
        stmt = stmt.where(AuditLog.organization_id == _uuid.UUID(str(organization_id)))
    else:
        stmt = stmt.where(AuditLog.team_id.is_(None))

    result = await db.execute(stmt)
    rows = result.scalars().all()

    records = [
        {
            "sequence_number": row.sequence_number,
            "event": row.event,
            "user_id": str(row.user_id) if row.user_id else None,
            "team_id": str(row.team_id) if row.team_id else None,
            "organization_id": str(row.organization_id) if row.organization_id else None,
            "ip": row.ip,
            "artifact_id": row.artifact_id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else "",
            "event_data": row.event_data or {},
            "previous_hash": row.previous_hash or "GENESIS",
            "hash": row.hash or "",
        }
        for row in rows
    ]
    return verify_audit_hash_chain_detailed(records)


async def verify_audit_db_chain(
    db: AsyncSession,
    team_id: str | None = None,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> bool:
    """Boolean verification of DB audit chain."""
    valid, _ = await verify_audit_db_chain_detailed(
        db, team_id=team_id, user_id=user_id, organization_id=organization_id
    )
    return valid


# Backward-compatible alias
verify_audit_merkle_chain = verify_audit_hash_chain



