import hashlib
import json
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import iterate_in_threadpool
import re

logger = logging.getLogger(__name__)

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed idempotency middleware for mutating endpoints (POST, PATCH, PUT).
    Prevents double-submissions, frontend retries, and race conditions.
    """
    async def dispatch(self, request: Request, call_next):
        if request.method not in ("POST", "PATCH", "PUT"):
            return await call_next(request)
            
        path = request.url.path
        allowed_patterns = [r"^/billing/checkout.*", r"^/billing/webhook$", r"^/billing/webhooks/stripe$", r"^/optimize.*", r"^/simulate.*"]
        if not any(re.match(pattern, path) for pattern in allowed_patterns):
            return await call_next(request)
            
        from suspensionlab.backend.api.routes.optimize import async_redis_conn
        if async_redis_conn is None:
            if path.startswith("/billing"):
                logger.error("Redis not available, fail-closed for billing endpoint")
                return Response(
                    content=json.dumps({"error": "service_unavailable", "message": "Service temporarily unavailable", "request_id": "unknown"}),
                    status_code=503,
                    media_type="application/json"
                )
            else:
                logger.warning("Redis not available, fail-open for compute endpoint")
                return await call_next(request)
            
        api_key = request.headers.get("X-API-Key", "anonymous")
        idempotency_key = None
        
        # We need the request body to hash it for collision detection and potentially parsing Stripe event ID
        req_body = await request.body()
        
        # Stripe webhook specific logic
        if path in ("/billing/webhook", "/billing/webhooks/stripe"):
            try:
                payload = json.loads(req_body)
                idempotency_key = payload.get("id")
            except Exception:
                pass
            if not idempotency_key:
                idempotency_key = request.headers.get("Stripe-Signature")
        else:
            idempotency_key = request.headers.get("Idempotency-Key")
            
        if not idempotency_key:
            # Re-inject the body so the route can read it
            async def receive():
                return {"type": "http.request", "body": req_body}
            request._receive = receive
            return await call_next(request)
            
        # Calculate request body hash to detect collisions
        req_body_hash = hashlib.sha256(req_body).hexdigest()
        
        raw_key = f"{api_key}:{path}:{idempotency_key}"
        hash_key = hashlib.sha256(raw_key.encode()).hexdigest()
        redis_key = f"idempotency:{hash_key}"
        
        # Try to read or wait for cache
        MAX_WAIT_SECONDS = 3.0
        INITIAL_SLEEP   = 0.05  # 50ms
        MAX_SLEEP       = 0.5   # 500ms

        elapsed = 0.0
        sleep_time = INITIAL_SLEEP
        while elapsed < MAX_WAIT_SECONDS:
            try:
                cached = await async_redis_conn.get(redis_key)
                if cached and cached == b'"IN_PROGRESS"':
                    import asyncio
                    await asyncio.sleep(sleep_time)
                    elapsed += sleep_time
                    sleep_time = min(sleep_time * 2, MAX_SLEEP)
                    continue
                elif cached:
                    cached_data = json.loads(cached)
                    if cached_data.get("req_body_hash") != req_body_hash:
                        from suspensionlab.backend.security.audit import log_audit_event
                        log_audit_event(
                            "IDEMPOTENCY_CONFLICT",
                            ip=request.client.host if request.client else "unknown",
                            metadata={"key": idempotency_key, "path": path}
                        )
                        logger.warning(f"Idempotency conflict for {redis_key}")
                        return Response(
                            content=json.dumps({"error": "conflict", "message": "Idempotency key already used with different request body", "request_id": "unknown"}),
                            status_code=409,
                            media_type="application/json"
                        )
                    logger.info(f"Idempotency cache hit for {redis_key}")
                    return Response(
                        content=cached_data["body"],
                        status_code=cached_data["status_code"],
                        media_type="application/json",
                        headers={"X-Idempotent-Replay": "true"}
                    )
                
                # Not in cache — try to acquire lock
                lock_acquired = await async_redis_conn.set(redis_key, json.dumps("IN_PROGRESS"), nx=True, ex=30)
                if lock_acquired:
                    break
                
                import asyncio
                await asyncio.sleep(sleep_time)
                elapsed += sleep_time
                sleep_time = min(sleep_time * 2, MAX_SLEEP)
            except Exception as e:
                logger.warning(f"Failed to read idempotency cache: {e}")
                break
        else:
            # If we exhausted 100 retries without acquiring the lock
            from suspensionlab.backend.security.audit import log_audit_event
            log_audit_event(
                "IDEMPOTENCY_TIMEOUT",
                ip=request.client.host if request.client else "unknown",
                metadata={"key": idempotency_key, "path": path}
            )
            return Response(
                content=json.dumps({"error": "conflict", "message": "Request timed out waiting for idempotency lock", "request_id": "unknown"}),
                status_code=409,
                media_type="application/json"
            )
            
        # Re-inject body
        async def receive():
            return {"type": "http.request", "body": req_body}
        request._receive = receive
        
        response = await call_next(request)
        
        # Cache successful responses (2xx)
        if 200 <= response.status_code < 300:
            from starlette.responses import StreamingResponse, FileResponse
            if isinstance(response, (StreamingResponse, FileResponse)) or response.headers.get("transfer-encoding") == "chunked":
                logger.info(f"Skipping idempotency cache for streaming/file response: {redis_key}")
                return response
                
            try:
                response_body = [chunk async for chunk in response.body_iterator]
                response.body_iterator = iterate_in_threadpool(iter(response_body))
                
                body_bytes = b"".join(response_body)
                cache_payload = {
                    "status_code": response.status_code,
                    "body": body_bytes.decode("utf-8"),
                    "req_body_hash": req_body_hash
                }
                
                ttl = 86400 if path.startswith("/billing") else 3600
                await async_redis_conn.setex(redis_key, ttl, json.dumps(cache_payload))
            except Exception as e:
                logger.warning(f"Failed to write idempotency cache: {e}")
                
        return response
