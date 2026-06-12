from fastapi import APIRouter, HTTPException, Depends, Request
import json
import asyncio
from sqlalchemy import update
import redis.asyncio as aioredis
from suspensionlab.shared.models import JobResponse, MonteCarloRequest
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry.propagate import inject

router = APIRouter()

@router.post("/simulate/monte-carlo", response_model=JobResponse)
async def simulate_monte_carlo(payload: MonteCarloRequest, request: Request, db: AsyncSession = Depends(get_db_dependency)):
    from suspensionlab.backend.workers.unified_worker import run_job
    from suspensionlab.backend.api.routes.optimize import job_queue, async_redis_conn, RedisUnavailableError
    from rq import Retry
    import redis
    
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
        
    from suspensionlab.backend.services.quota import assert_can_run_job
    tier = getattr(request.state, "plan", "FREE")
    user = {"user_id": user_id, "tier": tier}
    await assert_can_run_job(user, db)

    job_id = str(uuid.uuid4())
    
    job_record = JobRecord(
        id=job_id,
        user_id=uuid.UUID(user_id),
        job_type="MONTE_CARLO_QUARTER",
        status="PENDING",
    )
    db.add(job_record)
    await db.commit()

    trace_carrier = {}
    inject(trace_carrier)

    res_data = {"job_id": job_id, "status": "PENDING", "user_id": user_id, "result": None, "error": None}
    await async_redis_conn.setex(f"job_status:{job_id}", 86400, json.dumps(res_data))

    try:
        job = await asyncio.to_thread(
            job_queue.enqueue,
            run_job,
            args=(job_id, payload.model_dump(), trace_carrier),
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
        try:
            await async_redis_conn.delete(f"job_status:{job_id}")
        except redis.exceptions.ConnectionError:
            pass
        raise HTTPException(status_code=503, detail="Queue unavailable.")
    
    return JobResponse(job_id=job.id, status="PENDING")
