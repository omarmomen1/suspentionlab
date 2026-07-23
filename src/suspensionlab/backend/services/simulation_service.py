import uuid
import json
import asyncio
import redis.exceptions
from opentelemetry.propagate import inject
from rq import Retry
from sqlalchemy import update

from suspensionlab.backend.workers.task_queue import job_queue, priority_job_queue
from suspensionlab.backend.workers.unified_worker import run_job
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.core.errors import RedisUnavailableError

class SimulationService:
    """
    Domain service for orchestrating simulations, decoupling the API layer from
    the physics and worker layers (Phase 3 Architecture).
    """

    @staticmethod
    async def enqueue_simulation(user_id: str, plan: str, job_type: str, payload: dict, db) -> str:
        """Enqueues a simulation job and returns the job ID (Phase 2 Queue Rewrite)."""
        job_id = str(uuid.uuid4())
        
        # Create Job Record in DB
        new_job = JobRecord(
            id=uuid.UUID(job_id),
            user_id=uuid.UUID(user_id),
            job_type=job_type,
            status="PENDING",
            params=payload.get("params", {}),
            profile=payload.get("profile", {})
        )
        db.add(new_job)
        await db.commit()

        # Prime Redis cache for fast polling
        try:
            redis_conn = job_queue.connection
            res_data = {"job_id": job_id, "status": "PENDING", "user_id": user_id, "result": None, "error": None}
            await asyncio.to_thread(redis_conn.setex, f"job_status:{job_id}", 86400, json.dumps(res_data))
        except Exception:
            pass # Non-fatal if cache prime fails

        trace_carrier = {}
        inject(trace_carrier)

        try:
            target_queue = priority_job_queue if plan == "ENTERPRISE" else job_queue
            await asyncio.to_thread(
                target_queue.enqueue,
                run_job,
                args=(job_id, payload, trace_carrier),
                job_id=job_id,
                result_ttl=86400,
                failure_ttl=86400,
                retry=Retry(max=3, interval=[10, 30, 60])
            )
        except redis.exceptions.ConnectionError:
            await db.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id)
                .values(status="FAILED", error="Redis enqueue failed. Compute plane unavailable.")
            )
            await db.commit()
            raise RedisUnavailableError()
            
        return job_id
