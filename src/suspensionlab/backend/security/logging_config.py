import time
import logging
import json
from fastapi import Request

from contextvars import ContextVar

request_id_ctx = ContextVar("request_id", default="system")

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_ctx.get()
        return True

# Apply globally to all root handlers
root_logger = logging.getLogger()
request_id_filter = RequestIdFilter()

for handler in root_logger.handlers:
    handler.addFilter(request_id_filter)
    fmt = handler.formatter
    if fmt:
        fmt_str = fmt._fmt
        if "%(request_id)s" not in fmt_str:
            new_fmt_str = f"[%(request_id)s] {fmt_str}"
            # Mutate in place to preserve subclasses (like uvicorn.logging.DefaultFormatter)
            try:
                fmt._style._fmt = new_fmt_str
                fmt._fmt = new_fmt_str
            except Exception:
                handler.setFormatter(logging.Formatter(new_fmt_str, fmt.datefmt))
            
# Specifically configure our app logger as well if it has its own handlers
logger = logging.getLogger("suspensionlab.api")
logger.setLevel(logging.INFO)
logger.addFilter(request_id_filter)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(request_id)s] %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

async def logging_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000.0
    
    log_data = {
        "method": request.method,
        "url": str(request.url.path),
        "status_code": response.status_code,
        "duration_ms": round(process_time, 2),
        "ip": request.client.host if request.client else "unknown"
    }
    
    if response.status_code >= 400:
        logger.warning(json.dumps(log_data))
    else:
        logger.info(json.dumps(log_data))
        
    return response
