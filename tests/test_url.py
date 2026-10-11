import os
import sys

print("DATABASE_URL:", os.environ.get("DATABASE_URL"))
print("REDIS_URL:", os.environ.get("REDIS_URL"))

import socket
import asyncio
import asyncpg
import redis.asyncio as aioredis

async def test_conns():
    db_url = os.environ.get("DATABASE_URL")
    print("Testing asyncpg connection...")
    try:
        # asyncpg takes connection string or host
        # replace postgresql+asyncpg with postgresql
        clean_url = db_url.replace("+asyncpg", "")
        conn = await asyncpg.connect(clean_url)
        val = await conn.fetchval("SELECT 1")
        print("Asyncpg SUCCESS, SELECT 1 =", val)
        await conn.close()
    except Exception as e:
        print("Asyncpg FAILED:", type(e), e)

    print("Testing redis connection...")
    try:
        r = aioredis.from_url(os.environ.get("REDIS_URL"))
        pong = await r.ping()
        print("Redis SUCCESS, PING =", pong)
        await r.aclose()
    except Exception as e:
        print("Redis FAILED:", type(e), e)

asyncio.run(test_conns())
