import os
import redis.asyncio as aioredis
import logging

_async_redis_conn: aioredis.Redis | None = None

def get_async_redis_conn() -> aioredis.Redis | None:
    return _async_redis_conn

def get_async_redis() -> aioredis.Redis | None:
    return _async_redis_conn

async def init_async_redis():
    global _async_redis_conn
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        logging.warning("REDIS_URL not set \u2014 async Redis features (job locking) will be unavailable.")
        return
    _async_redis_conn = aioredis.from_url(redis_url)

async def close_async_redis():
    global _async_redis_conn
    if _async_redis_conn:
        await _async_redis_conn.aclose()
        _async_redis_conn = None
