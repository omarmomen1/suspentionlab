import json
import logging
from datetime import datetime, timezone
from typing import Any
from suspensionlab.backend.security.logging_config import request_id_ctx

class JSONAuditFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "request_id": request_id_ctx.get(),
            "user_id": getattr(record, "user_id", None),
            "ip": getattr(record, "ip", None),
            "event_type": getattr(record, "event_type", "UNKNOWN"),
            "metadata": getattr(record, "metadata", {})
        }
        return json.dumps(payload)

_audit_logger = logging.getLogger("security_audit")
_audit_logger.setLevel(logging.INFO)
# Remove all default handlers to prevent double logging
_audit_logger.propagate = False

if not _audit_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(JSONAuditFormatter())
    _audit_logger.addHandler(_handler)

def log_audit_event(
    event_type: str,
    user_id: str | None = None,
    ip: str | None = None,
    metadata: dict[str, Any] | None = None,
    team_id: str | None = None,
    user_agent: str | None = None,
) -> None:
    """
    Logs a structured JSON security audit event (stream handler).
    For a durable, queryable record use `record_audit_event()` which also
    persists to the audit_logs table.
    """
    if metadata is None:
        metadata = {}
        
    extra = {
        "user_id": user_id,
        "ip": ip,
        "event_type": event_type,
        "metadata": metadata
    }
    
    _audit_logger.info(f"Audit event: {event_type}", extra=extra)


async def record_audit_event(
    db,  # AsyncSession
    event_type: str,
    user_id: str | None = None,
    team_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Durable audit: writes the JSON stream event AND persists an AuditLog row.
    (#23) Never raises — audit failures must not break the request path.
    """
    import uuid as _uuid
    from datetime import datetime, timezone as _tz

    log_audit_event(event_type, user_id=user_id, ip=ip, metadata=metadata)

    try:
        from suspensionlab.backend.database.models.audit import AuditLog
        row = AuditLog(
            event=event_type,
            user_id=_uuid.UUID(user_id) if user_id else None,
            team_id=_uuid.UUID(team_id) if team_id else None,
            ip=ip,
            user_agent=user_agent[:255] if user_agent else None,
            timestamp=datetime.now(_tz.utc),
            event_data=metadata or {},
        )
        db.add(row)
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass


def canonical_hash(obj: Any) -> str:
    """SHA-256 over a canonical (sorted-key, stable-separator) JSON dump.

    Used for provenance hashing of simulation params/results so that any
    byte-level difference in inputs or outputs is detectable.
    """
    import hashlib
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
