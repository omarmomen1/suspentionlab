"""
backend/security/logging_config.py
==================================
SuspensionLab PRO — Enterprise Log Correlation Engine (Step 3)

Ensures every log record emitted by the API, queues, workers, and physics engines
carries the full 7-tuple correlation context:
1. request_id
2. trace_id
3. job_id
4. user_id
5. organization_id
6. team_id
7. model_family
"""

import time
import logging
import json
from typing import Optional, Dict, Any
from fastapi import Request
from contextvars import ContextVar

# ── Correlation Context Variables ─────────────────────────────────────────────
request_id_ctx = ContextVar("request_id", default="system")
trace_id_ctx = ContextVar("trace_id", default="-")
job_id_ctx = ContextVar("job_id", default="-")
user_id_ctx = ContextVar("user_id", default="-")
organization_id_ctx = ContextVar("organization_id", default="-")
team_id_ctx = ContextVar("team_id", default="-")
model_family_ctx = ContextVar("model_family", default="-")


def set_job_correlation_context(
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    job_id: Optional[str] = None,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    team_id: Optional[str] = None,
    model_family: Optional[str] = None,
) -> None:
    """Sets correlation fields in contextvars for the current task/thread."""
    if request_id is not None:
        request_id_ctx.set(str(request_id or "-"))
    if trace_id is not None:
        trace_id_ctx.set(str(trace_id or "-"))
    if job_id is not None:
        job_id_ctx.set(str(job_id or "-"))
    if user_id is not None:
        user_id_ctx.set(str(user_id or "-"))
    if organization_id is not None:
        organization_id_ctx.set(str(organization_id or "-"))
    if team_id is not None:
        team_id_ctx.set(str(team_id or "-"))
    if model_family is not None:
        model_family_ctx.set(str(model_family or "-"))


def get_job_correlation_context() -> Dict[str, str]:
    """Returns a dictionary containing all 7 correlation context fields."""
    return {
        "request_id": request_id_ctx.get(),
        "trace_id": trace_id_ctx.get(),
        "job_id": job_id_ctx.get(),
        "user_id": user_id_ctx.get(),
        "organization_id": organization_id_ctx.get(),
        "team_id": team_id_ctx.get(),
        "model_family": model_family_ctx.get(),
    }


def clear_job_correlation_context() -> None:
    """Reset correlation context back to default empty state."""
    request_id_ctx.set("system")
    trace_id_ctx.set("-")
    job_id_ctx.set("-")
    user_id_ctx.set("-")
    organization_id_ctx.set("-")
    team_id_ctx.set("-")
    model_family_ctx.set("-")


class JobCorrelationFilter(logging.Filter):
    """Injects all 7 correlation identifiers into every LogRecord."""
    def filter(self, record):
        record.request_id = request_id_ctx.get()
        record.trace_id = trace_id_ctx.get()
        record.job_id = job_id_ctx.get()
        record.user_id = user_id_ctx.get()
        record.organization_id = organization_id_ctx.get()
        record.team_id = team_id_ctx.get()
        record.model_family = model_family_ctx.get()
        return True


# Backward-compatible alias
RequestIdFilter = JobCorrelationFilter

# Apply globally to root logger
root_logger = logging.getLogger()
job_correlation_filter = JobCorrelationFilter()
root_logger.addFilter(job_correlation_filter)

for handler in root_logger.handlers:
    handler.addFilter(job_correlation_filter)
    fmt = handler.formatter
    if fmt:
        fmt_str = fmt._fmt
        if "%(request_id)s" not in fmt_str:
            new_fmt_str = "[%(request_id)s %(trace_id)s %(job_id)s %(model_family)s] " + fmt_str
            try:
                fmt._style._fmt = new_fmt_str
                fmt._fmt = new_fmt_str
            except Exception:
                handler.setFormatter(logging.Formatter(new_fmt_str, fmt.datefmt))

# App logger configuration
logger = logging.getLogger("suspensionlab")
logger.setLevel(logging.INFO)
logger.addFilter(job_correlation_filter)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [req=%(request_id)s trace=%(trace_id)s job=%(job_id)s "
        "user=%(user_id)s org=%(organization_id)s team=%(team_id)s model=%(model_family)s] %(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(job_correlation_filter)
    logger.addHandler(handler)


async def logging_middleware(request: Request, call_next):
    start_time = time.time()
    
    # Extract trace ID from OpenTelemetry span if active
    from opentelemetry import trace
    current_span = trace.get_current_span()
    span_ctx = current_span.get_span_context() if current_span else None
    if span_ctx and span_ctx.is_valid:
        trace_id_hex = format(span_ctx.trace_id, "032x")
        trace_id_ctx.set(trace_id_hex)

    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000.0

    log_data = {
        "method": request.method,
        "url": str(request.url.path),
        "status_code": response.status_code,
        "duration_ms": round(process_time, 2),
        "ip": request.client.host if request.client else "unknown",
        "correlation": get_job_correlation_context(),
    }

    if response.status_code >= 400:
        logger.warning(json.dumps(log_data))
    else:
        logger.info(json.dumps(log_data))

    return response
