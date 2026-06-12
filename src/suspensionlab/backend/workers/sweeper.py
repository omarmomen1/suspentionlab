import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from suspensionlab.backend.database.core import get_async_db_session
from suspensionlab.backend.database.models.job import JobRecord

logger = logging.getLogger(__name__)

async def sweep_orphan_jobs(timeout_seconds: int = 60):
    """
    Finds jobs stuck in the RUNNING state where the last_heartbeat is older than timeout_seconds
    and safely marks them as FAILED. This frees up the user's queue limit
    in the event of a hard container crash or uncatchable segfault.
    """
    async with get_async_db_session() as db:
        # We use last_heartbeat to detect killed workers accurately.
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        
        result = await db.execute(
            select(JobRecord).where(
                JobRecord.status == "RUNNING",
                JobRecord.last_heartbeat < cutoff_time
            )
        )
        orphans = result.scalars().all()
        
        if orphans:
            logger.warning(f"Found {len(orphans)} orphaned jobs. Sweeping to FAILED.")
            import json
            import redis.asyncio as aioredis
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            r_conn = aioredis.from_url(redis_url)
            
            for job in orphans:
                job.status = "FAILED"
                job.error = "Job timed out and was swept by the background cron."
                job.finished_at = datetime.now(timezone.utc)
                
                # Must update Redis cache so the frontend sees the failure immediately
                try:
                    cached = await r_conn.get(f"job_status:{job.id}")
                    user_id = None
                    if cached:
                        try:
                            user_id = json.loads(cached).get("user_id")
                        except Exception:
                            pass
                    if not user_id:
                        user_id = job.user_id
                    res_data = {"job_id": job.id, "status": "FAILED", "user_id": user_id, "result": None, "error": job.error}
                    await r_conn.setex(f"job_status:{job.id}", 300, json.dumps(res_data))
                except Exception as e:
                    logger.error(f"Failed to update Redis cache for swept job {job.id}: {e}")
                
            await r_conn.aclose()
            await db.commit()
        else:
            logger.info("No orphaned jobs found. Queue is healthy.")

if __name__ == "__main__":
    asyncio.run(sweep_orphan_jobs())
