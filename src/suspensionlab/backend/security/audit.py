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
    metadata: dict[str, Any] | None = None
) -> None:
    """
    Logs a structured JSON security audit event.
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
