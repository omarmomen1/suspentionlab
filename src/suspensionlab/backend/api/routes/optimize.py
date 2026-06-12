import os
import uuid
import json
import redis.exceptions
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from rq import Retry
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry.propagate import inject

from suspensionlab.shared.models import OptimizeRequest
from suspensionlab.backend.core.errors import RedisUnavailableError, RateLimitExceededError, JobNotFoundError
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.workers.queue import job_queue
from suspensionlab.backend.workers.unified_worker import run_job
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord

router = APIRouter(tags=["optimize"])

async_redis_conn: aioredis.Redis | None = None

async def init_async_redis():
    global async_redis_conn
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    async_redis_conn = aioredis.from_url(redis_url)

async def close_async_redis():
    global async_redis_conn
    if async_redis_conn:
        await async_redis_conn.aclose()

class JobResponse(BaseModel):
    job_id: str
    status: str

@router.post("/optimize", response_model=JobResponse)
async def submit_optimization(
    req: OptimizeRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Submits an optimization job to the Redis worker queue and returns immediately.
    """
    redis_conn = job_queue.connection
    
    lock_key = f"lock:user_optimize:{user['user_id']}"
    
    if async_redis_conn is None:
        raise RedisUnavailableError("Redis not initialized")

    try:
        # 1. Atomic Redis Lock to prevent TOCTOU race conditions
        async with async_redis_conn.lock(lock_key, timeout=5.0, blocking_timeout=2.0):
            # 2. Safe Backpressure: Enforce quota inside the atomic lock
            from suspensionlab.backend.services.quota import assert_can_run_job
            await assert_can_run_job(user, db)

            # Create Job Record in DB safely inside the lock
            job_id = str(uuid.uuid4())
            new_job = JobRecord(
                id=job_id,
                user_id=user["user_id"],
                job_type="OPTIMIZE_QUARTER",
                status="PENDING",
                params=req.params.model_dump(),
                profile=req.profile.model_dump()
            )
            db.add(new_job)
            await db.commit()
    except redis.exceptions.LockError:
        raise RateLimitExceededError("Too many concurrent optimization requests. Please wait.")
    except redis.exceptions.ConnectionError:
        raise RedisUnavailableError()

    trace_carrier = {}
    inject(trace_carrier)

    import asyncio
    # Prime Redis status to guarantee authoritative read-through before enqueue
    res_data = {"job_id": job_id, "status": "PENDING", "user_id": user["user_id"], "result": None, "error": None}
    await asyncio.to_thread(redis_conn.setex, f"job_status:{job_id}", 86400, json.dumps(res_data))

    try:
        payload = {
            "params": req.params.model_dump(),
            "profile": req.profile.model_dump(),
            "objective_type": req.objective_type,
            "max_travel": req.max_travel
        }
        # Enqueue job with exponential transient retry (max 3 times)
        job = await asyncio.to_thread(
            job_queue.enqueue,
            run_job,
            args=(job_id, payload, trace_carrier),
            job_id=job_id,
            result_ttl=86400,
            failure_ttl=86400,
            retry=Retry(max=3, interval=[10, 30, 60])
        )
    except redis.exceptions.ConnectionError:
        # DB lock already committed. We must explicitly fail the job record, not just rollback.
        await db.execute(
            update(JobRecord)
            .where(JobRecord.id == job_id)
            .values(status="FAILED", error="Redis enqueue failed. Compute plane unavailable.")
        )
        await db.commit()
        # Clean up the primed cache
        try:
            redis_conn.delete(f"job_status:{job_id}")
        except redis.exceptions.ConnectionError:
            pass
        raise RedisUnavailableError()
    
    return JobResponse(job_id=job.id, status="PENDING")

@router.get("/optimize/active")
async def get_active_job(
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Returns any actively computing job to rehydrate the UI on refresh.
    """
    result = await db.execute(
        select(JobRecord).where(
            JobRecord.user_id == user["user_id"],
            JobRecord.status.in_(["PENDING", "RUNNING"])
        )
    )
    active_job = result.scalars().first()
    
    if not active_job:
        raise JobNotFoundError("No active jobs")
        
    return {"job_id": active_job.id, "status": active_job.status}

@router.get("/optimize/history")
async def get_job_history(
    limit: int = 20,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Returns the user's recent optimization job history."""
    from sqlalchemy import select, desc
    result = await db.execute(
        select(JobRecord)
        .where(JobRecord.user_id == user["user_id"])
        .order_by(desc(JobRecord.started_at))
        .limit(limit)
    )
    jobs = result.scalars().all()
    return [
        {
            "job_id": j.id,
            "status": j.status,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "result": j.result,
            "error": j.error,
        }
        for j in jobs
    ]
@router.post("/auto-tune")
async def auto_tune_suspension(
    req: OptimizeRequest,
    user: dict = Depends(verify_api_key)
):
    """
    Synchronous endpoint for AI-driven suspension tuning.
    Uses Scipy L-BFGS-B to minimise ISO 2631-1 Wk-weighted RMS body acceleration
    subject to a suspension travel penalty.
    """
    import numpy as np
    from scipy.optimize import minimize
    from suspensionlab.physics.quarter_car import (
        QuarterCarParams, RoadProfile, run_quarter_car_analysis
    )

    def objective(x: np.ndarray) -> float:
        k_s = float(np.clip(x[0], 5_000, 200_000))
        c   = float(np.clip(x[1],   500,  20_000))
        try:
            p = QuarterCarParams(
                m_s=req.params.m_s,
                m_u=req.params.m_u,
                k_s=k_s,
                c=c,
                k_t=req.params.k_t,
                MR=req.params.MR,
                c_t=req.params.c_t,
            )
            profile = RoadProfile(
                profile_type=req.profile.profile_type,
                amplitude=req.profile.amplitude,
                frequency=req.profile.frequency,
                # Cap duration at 3 s for speed; enough to capture transient response
                duration=min(req.profile.duration, 3.0),
            )
            result = run_quarter_car_analysis(p, profile)
            # Primary objective: minimise weighted RMS acceleration (ISO 2631-1 Wk)
            cost = result.rms_body_accel_wk
            # Penalty: suspension travel beyond the allowed limit
            excess = result.peak_susp_travel - req.max_travel
            if excess > 0:
                cost += excess * 500.0
            return cost
        except Exception:
            return 1e6  # High penalty for any instability or validation error

    x0 = np.array([req.params.k_s, req.params.c], dtype=float)
    bounds = [(5_000, 200_000), (500, 20_000)]

    import asyncio
    res = await asyncio.to_thread(
        minimize,
        objective,
        x0,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 300, "ftol": 1e-5, "gtol": 1e-4},
    )

    if res.success or res.fun < 1e5:
        return {
            "status": "success",
            "optimal_ks": float(res.x[0]),
            "optimal_c":  float(res.x[1]),
            "message": f"Converged in {res.nit} iterations. Cost: {res.fun:.4f}",
        }
    else:
        return {
            "status": "failed",
            "message": f"Optimisation did not fully converge: {res.message}",
        }
