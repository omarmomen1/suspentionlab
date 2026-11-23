from __future__ import annotations
import hashlib
import json
import logging
from typing import Any, Optional, Dict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import iterate_in_threadpool
import re

import time
from collections import OrderedDict

logger = logging.getLogger(__name__)


class MemoryIdempotencyCache:
    """Bounded in-memory LRU cache with TTL expiration to prevent OOM when Redis is down."""

    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._cache:
            return default
        val, expire_at = self._cache[key]
        if time.time() > expire_at:
            del self._cache[key]
            return default
        self._cache.move_to_end(key)
        return val

    def set(self, key: str, val: Any, ttl: float | None = None, nx: bool = False) -> bool:
        now = time.time()
        if key in self._cache:
            _, expire_at = self._cache[key]
            if now > expire_at:
                del self._cache[key]
            elif nx:
                return False
        if nx and key in self._cache:
            return False
        expire_at = now + (ttl if ttl is not None else self._default_ttl)
        self._cache[key] = (val, expire_at)
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        return True

    def __getitem__(self, key: str) -> Any:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, val: Any) -> None:
        self.set(key, val)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def clear(self) -> None:
        self._cache.clear()


_memory_idempotency_cache = MemoryIdempotencyCache(max_size=1000, default_ttl=300.0)

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Enterprise idempotency middleware for mutating endpoints (POST, PATCH, PUT).
    Backed by Redis in production with automatic in-memory fallback for local dev & testing.
    Prevents double-submissions, frontend retries, and race conditions.
    """
    async def dispatch(self, request: Request, call_next):
        if request.method not in ("POST", "PATCH", "PUT"):
            return await call_next(request)
            
        path = request.url.path
        allowed_patterns = [
            r"^/api/v1/billing/checkout.*",
            r"^/api/v1/billing/webhook.*",
            r"^/api/v1/billing/lemon-webhook.*",
            r"^/api/v1/billing/verify-license.*",
            r"^/api/v1/optimize.*",
            r"^/api/v1/simulate.*",
            r"^/api/v1/twins/.*/proposals.*",
            r"^/api/v1/organizations.*",
            r"^/api/v1/compliance.*",
            r"^/billing/checkout.*",
            r"^/billing/webhook.*",
            r"^/billing/webhooks/stripe.*",
            r"^/billing/lemon-webhook.*",
            r"^/billing/verify-license.*",
            r"^/optimize.*",
            r"^/simulate.*",
            r"^/twins/.*/proposals.*",
        ]
        if not any(re.match(pattern, path) for pattern in allowed_patterns):
            return await call_next(request)
            
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                from suspensionlab.backend.security.jwt_utils import decode_access_token
                payload = decode_access_token(auth_header.removeprefix("Bearer ").strip())
                if payload and payload.get("sub"):
                    user_id = payload.get("sub")
        if not user_id:
            user_id = request.headers.get("X-API-Key", "anonymous")
        idempotency_key = None
        
        # We need the request body to hash it for collision detection and potentially parsing Stripe event ID
        req_body = await request.body()
        
        # Webhook specific logic
        if path in ("/billing/webhook", "/billing/webhooks/stripe", "/api/v1/billing/webhook", "/api/v1/billing/lemon-webhook", "/api/v1/billing/verify-license"):
            try:
                payload = json.loads(req_body)
                idempotency_key = payload.get("id")
            except Exception:
                pass
            if not idempotency_key:
                idempotency_key = (
                    request.headers.get("Stripe-Signature") or 
                    request.headers.get("X-Signature") or 
                    request.headers.get("Gumroad-Signature")
                )
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
        
        raw_key = f"{user_id}:{path}:{idempotency_key}"
        hash_key = hashlib.sha256(raw_key.encode()).hexdigest()
        redis_key = f"idempotency:{hash_key}"
        
        from suspensionlab.backend.core.redis_client import get_async_redis_conn
        async_redis_conn = get_async_redis_conn()
        
        # Helper to get from Redis or memory
        async def _get_cache(key: str):
            if async_redis_conn:
                try:
                    return await async_redis_conn.get(key)
                except Exception:
                    pass
            return _memory_idempotency_cache.get(key)

        # Helper to set in Redis or memory
        async def _set_cache(key: str, val: bytes | str, ttl: int = 3600, nx: bool = False):
            if async_redis_conn:
                try:
                    if nx:
                        return await async_redis_conn.set(key, val, nx=True, ex=ttl)
                    return await async_redis_conn.setex(key, ttl, val)
                except Exception:
                    pass
            return _memory_idempotency_cache.set(key, val, ttl=ttl, nx=nx)

        # Try to read or wait for cache
        MAX_WAIT_SECONDS = 3.0
        INITIAL_SLEEP   = 0.05  # 50ms
        MAX_SLEEP       = 0.5   # 500ms

        elapsed = 0.0
        sleep_time = INITIAL_SLEEP
        while elapsed < MAX_WAIT_SECONDS:
            try:
                cached = await _get_cache(redis_key)
                if cached and (cached == b'"IN_PROGRESS"' or cached == '"IN_PROGRESS"'):
                    import asyncio
                    await asyncio.sleep(sleep_time)
                    elapsed += sleep_time
                    sleep_time = min(sleep_time * 2, MAX_SLEEP)
                    continue
                elif cached:
                    cached_str = cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
                    cached_data = json.loads(cached_str)
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
                lock_acquired = await _set_cache(redis_key, json.dumps("IN_PROGRESS"), ttl=30, nx=True)
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
                await _set_cache(redis_key, json.dumps(cache_payload), ttl=ttl)
            except Exception as e:
                logger.warning(f"Failed to write idempotency cache: {e}")
                
        return response
