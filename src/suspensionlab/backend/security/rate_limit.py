import time
import threading
from collections import defaultdict, deque
from fastapi import Request, HTTPException, status, Response
from suspensionlab.backend.config import settings
from suspensionlab.backend.core.errors import RateLimitExceededError
import logging

logger = logging.getLogger(__name__)

def parse_rate_limit(limit_str: str) -> tuple[int, int]:
    try:
        count_str, window_str = limit_str.split("/")
        count = int(count_str)
        if window_str == "minute":
            window = 60
        elif window_str == "second":
            window = 1
        elif window_str == "hour":
            window = 3600
        else:
            window = 60
        return count, window
    except Exception:
        return 5, 60


# ── In-memory fallback rate limiter (thread-safe sliding window) ──────────────
# Used when Redis is unavailable. Keeps per-key deques of request timestamps.
_fallback_lock = threading.Lock()
_fallback_store: dict[str, deque] = defaultdict(deque)

def _in_memory_check(redis_key: str, limit_count: int, window_seconds: int) -> int:
    """
    Thread-safe sliding window check using an in-memory deque.
    Returns the current request count after adding this request.
    Raises RateLimitExceededError if limit exceeded.
    """
    now = time.time()
    cutoff = now - window_seconds
    with _fallback_lock:
        dq = _fallback_store[redis_key]
        # Prevent memory leak from abandoned keys
        if len(_fallback_store) > 100000:
            keys_to_delete = [k for k, v in _fallback_store.items() if not v or v[-1] < cutoff]
            for k in keys_to_delete:
                del _fallback_store[k]
        
        # Remove expired timestamps
        while dq and dq[0] < cutoff:
            dq.popleft()
        count = len(dq)
        if count >= limit_count:
            raise RateLimitExceededError("Rate limit exceeded. Please try again later.")
        dq.append(now)
        return count + 1


class RateLimiter:
    def __init__(self, limit_config_key: str):
        self.limit_config_key = limit_config_key

    async def __call__(self, request: Request, response: Response):
        from suspensionlab.backend.core import redis_client
        async_redis_conn = redis_client.get_async_redis_conn()

        limit_str = getattr(settings, self.limit_config_key, "5/minute")
        limit_count, window_seconds = parse_rate_limit(limit_str)

        # Determine user_id to correctly scope the rate limit
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            from suspensionlab.backend.security.jwt_utils import decode_access_token
            token = request.cookies.get("sl_token")
            if not token:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header.removeprefix("Bearer ").strip()
            if token:
                payload = decode_access_token(token)
                if payload and payload.get("sub"):
                    user_id = payload.get("sub")

        if user_id:
            redis_key = f"rate_limit:{self.limit_config_key}:user:{user_id}"
            audit_id = user_id
        else:
            # For unauthenticated requests (e.g. login, register, forgot-password, public endpoints),
            # rate limit strictly by client IP to prevent header-spoofing brute force bypasses.
            client_ip = request.client.host if request.client else "unknown"
            redis_key = f"rate_limit:{self.limit_config_key}:ip:{client_ip}"
            audit_id = None

        now = time.time()

        # ── Redis path (preferred) ────────────────────────────────────────────
        if async_redis_conn is not None:
            try:
                import uuid
                pipeline = async_redis_conn.pipeline(transaction=True)
                pipeline.zremrangebyscore(redis_key, 0, now - window_seconds)
                pipeline.zadd(redis_key, {f"{now}:{uuid.uuid4()}": now})
                pipeline.zcard(redis_key)
                pipeline.expire(redis_key, window_seconds)
                results = await pipeline.execute()
                current_count = results[2]

                remaining = max(0, limit_count - current_count)
                response.headers["X-RateLimit-Limit"] = str(limit_count)
                response.headers["X-RateLimit-Remaining"] = str(remaining)

                if current_count > limit_count:
                    response.headers["Retry-After"] = str(window_seconds)
                    from suspensionlab.backend.security.audit import log_audit_event
                    log_audit_event(
                        "RATE_LIMIT_VIOLATION",
                        user_id=audit_id,
                        ip=request.client.host if request.client else "unknown",
                        metadata={"route": request.url.path, "limit_key": self.limit_config_key}
                    )
                    raise RateLimitExceededError("Rate limit exceeded. Please try again later.")
                return True

            except RateLimitExceededError:
                raise
            except Exception as redis_err:
                # Redis command failed — fall through to in-memory fallback
                logger.warning(
                    "Redis rate limit command failed (%s), switching to in-memory fallback for %s",
                    redis_err, redis_key
                )

        # ── In-memory fallback (fail-CLOSED — never fully open) ───────────────
        # Billing endpoints get a tighter fallback to prevent financial abuse
        path = request.url.path
        is_billing = path.startswith("/billing")
        fallback_limit = min(limit_count, 50) if is_billing else limit_count

        try:
            current_count = _in_memory_check(redis_key, fallback_limit, window_seconds)
            remaining = max(0, fallback_limit - current_count)
            response.headers["X-RateLimit-Limit"] = str(fallback_limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Fallback"] = "in-memory"
            return True
        except RateLimitExceededError:
            logger.warning(
                "In-memory rate limit exceeded for %s on %s",
                redis_key, path
            )
            response.headers["Retry-After"] = str(window_seconds)
            raise

async def record_login_failure(request: Request, email: str):
    from suspensionlab.backend.core import redis_client
    async_redis_conn = redis_client.get_async_redis_conn()
    if not async_redis_conn:
        return
    now = time.time()
    ip = request.client.host if request.client else "unknown"
    redis_key = f"login_failures:{email.lower()}:{ip}"
    try:
        pipeline = async_redis_conn.pipeline(transaction=True)
        # Keep failures for 1 hour window
        pipeline.zremrangebyscore(redis_key, 0, now - 3600)
        import uuid
        pipeline.zadd(redis_key, {f"{now}:{uuid.uuid4()}": now})
        pipeline.expire(redis_key, 3600)
        await pipeline.execute()
    except Exception:
        pass

async def check_progressive_penalty(request: Request, email: str):
    from suspensionlab.backend.core import redis_client
    async_redis_conn = redis_client.get_async_redis_conn()
    if not async_redis_conn:
        return
    now = time.time()
    ip = request.client.host if request.client else "unknown"
    redis_key = f"login_failures:{email.lower()}:{ip}"
    try:
        count = await async_redis_conn.zcard(redis_key)
        if count >= 20:
            raise RateLimitExceededError("Too many failed attempts. Try again in 1 hour.")
        elif count >= 10:
            last = await async_redis_conn.zrange(redis_key, -1, -1, withscores=True)
            if last and now - last[0][1] < 300:
                raise RateLimitExceededError("Too many failed attempts. Try again in 5 minutes.")
        elif count >= 5:
            last = await async_redis_conn.zrange(redis_key, -1, -1, withscores=True)
            if last and now - last[0][1] < 30:
                raise RateLimitExceededError("Too many failed attempts. Try again in 30 seconds.")
    except RateLimitExceededError:
        raise
    except Exception:
        pass
