import re
import time
import uuid as uuid_module
from fastapi import Request
from suspensionlab.backend.security.logging_config import request_id_ctx
from suspensionlab.backend.observability import API_REQUESTS_TOTAL, API_REQUEST_DURATION

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

async def security_headers_middleware(request: Request, call_next):
    # FIXED: Wrap in try/finally to ensure security headers are set even on crashes.
    try:
        response = await call_next(request)
    except Exception as exc:
        import logging
        logging.exception("security_headers_middleware crash: %s", exc)
        from fastapi.responses import JSONResponse
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # X-XSS-Protection set to 0 intentionally: modern browsers ignore it and
    # the old IE XSS auditor could be weaponized to suppress legitimate content.
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://assets.lemonsqueezy.com https://cdn.plot.ly https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.lemonsqueezy.com; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none';"
    )
    return response

async def request_id_middleware(request: Request, call_next):
    raw_id = request.headers.get("X-Request-ID", "")
    # FIXED: Validate X-Request-ID to prevent log injection. Accept only valid UUIDs.
    if raw_id and _UUID_RE.match(raw_id):
        request_id = raw_id
    else:
        request_id = str(uuid_module.uuid4())
    request_id_ctx.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

async def prometheus_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
        
    start_time = time.time()
    method = request.method
    route = request.url.path
    
    try:
        response = await call_next(request)
        status_code = response.status_code
        route_obj = request.scope.get("route")
        route_path = route_obj.path if route_obj else route
        API_REQUESTS_TOTAL.labels(method=method, route=route_path, status_code=status_code).inc()
        API_REQUEST_DURATION.labels(method=method, route=route_path).observe(time.time() - start_time)
        return response
    except Exception:
        route_obj = request.scope.get("route")
        route_path = route_obj.path if route_obj else route
        API_REQUESTS_TOTAL.labels(method=method, route=route_path, status_code=500).inc()
        API_REQUEST_DURATION.labels(method=method, route=route_path).observe(time.time() - start_time)
        raise

async def payload_size_limit_middleware(request: Request, call_next, max_size_bytes: int = 10 * 1024 * 1024):
    """Reject requests with payloads exceeding max_size_bytes (default: 10MB) with HTTP 413."""
    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_size_bytes:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=413,
                    content={"error": "payload_too_large", "detail": f"Request body exceeds {max_size_bytes} bytes limit."},
                )
        except ValueError:
            pass
    return await call_next(request)
