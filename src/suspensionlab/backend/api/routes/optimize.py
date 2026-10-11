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
from suspensionlab.backend.security.auth import require_permission, verify_api_key, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.workers.task_queue import job_queue
from suspensionlab.backend.workers.unified_worker import run_job
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.job import JobRecord

router = APIRouter(tags=["optimize"])

from suspensionlab.backend.core import redis_client

class JobResponse(BaseModel):
    job_id: str
    status: str

import hashlib
import json

def generate_idempotency_hash(user_id: str, req: OptimizeRequest) -> str:
    data_to_hash = {
        "user_id": user_id,
        "vehicle_id": getattr(req.profile, 'vehicle_id', 'default'),
        "params": req.params.model_dump(),
        "profile": req.profile.model_dump(),
        "objective_type": req.objective_type,
        "max_travel": req.max_travel,
        "solver_version": "1.0",
        "physics_version": "1.0"
    }
    json_str = json.dumps(data_to_hash, sort_keys=True)
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

@router.post("/optimize", response_model=JobResponse)
async def submit_optimization(
    req: OptimizeRequest,
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN)),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Submits an optimization job to the Redis worker queue and returns immediately.
    """
    # Check Redis availability
    redis_conn = None
    try:
        redis_conn = job_queue.connection
    except Exception:
        pass
    
    idem_hash = generate_idempotency_hash(user.user_id, req)
    idem_key = f"idem:optimize:{idem_hash}"
    lock_key = f"lock:user_optimize:{user.user_id}"
    
    async_redis_conn = None
    try:
        async_redis_conn = redis_client.get_async_redis_conn()
    except Exception:
        pass

    if async_redis_conn is not None and redis_conn is not None:
        # 1. Versioned Idempotency Check
        try:
            existing_job_id = await async_redis_conn.get(idem_key)
            if existing_job_id:
                return JobResponse(job_id=existing_job_id.decode('utf-8'), status="PENDING")
        except Exception:
            pass

        try:
            # 2. Atomic Redis Lock to prevent TOCTOU race conditions
            async with async_redis_conn.lock(lock_key, timeout=5.0, blocking_timeout=2.0):
                # 3. Safe Backpressure: Enforce quota inside the atomic lock
                from suspensionlab.backend.services.quota import assert_can_run_job
                await assert_can_run_job(user, db)

                # Create Job Record in DB safely inside the lock
                job_id = str(uuid.uuid4())
                opt_params = req.params.model_dump()
                opt_params["objective_type"] = req.objective_type
                opt_params["max_travel"] = req.max_travel
                new_job = JobRecord(
                    id=uuid.UUID(job_id),
                    user_id=uuid.UUID(user.user_id),
                    team_id=uuid.UUID(user.team_id) if getattr(user, "team_id", None) else None,  # (#22) team analytics
                    job_type="OPTIMIZE_QUARTER",
                    status="PENDING",
                    params=opt_params,
                    profile=req.profile.model_dump()
                )
                db.add(new_job)
                await db.commit()

                try:
                    from suspensionlab.backend.security.audit import record_audit_event
                    await record_audit_event(
                        db=db,
                        event_type="OPTIMIZATION_SUBMITTED",
                        user_id=str(user.user_id),
                        team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
                        artifact_id=job_id,
                        metadata={
                            "job_id": job_id,
                            "job_type": "OPTIMIZE_QUARTER",
                            "objective_type": req.objective_type,
                            "max_travel": req.max_travel,
                            "idempotency_hash": idem_hash,
                        }
                    )
                except Exception as e:
                    import logging
                    logging.getLogger("security_audit").warning("Audit logging warning for optimization: %s", e)
                
                # Store idempotency key mapping for 12 hours
                try:
                    await async_redis_conn.setex(idem_key, 43200, job_id)
                except Exception:
                    pass

        except redis.exceptions.LockError:
            raise RateLimitExceededError("Too many concurrent optimization requests. Please wait.")
        except redis.exceptions.ConnectionError:
            raise RedisUnavailableError()

        trace_carrier = {}
        inject(trace_carrier)

        import asyncio
        # Prime Redis status to guarantee authoritative read-through before enqueue
        res_data = {"job_id": job_id, "status": "PENDING", "user_id": user.user_id, "result": None, "error": None}
        try:
            await asyncio.to_thread(redis_conn.setex, f"job_status:{job_id}", 86400, json.dumps(res_data))
        except Exception:
            pass

        payload = {
            "params": req.params.model_dump(),
            "profile": req.profile.model_dump(),
            "objective_type": req.objective_type,
            "max_travel": req.max_travel
        }

        try:
            target_queue = job_queue
            if user.plan == "ENTERPRISE":
                from suspensionlab.backend.workers.task_queue import priority_job_queue
                target_queue = priority_job_queue
                
            # Enqueue job with exponential transient retry (max 3 times)
            job = await asyncio.to_thread(
                target_queue.enqueue,
                run_job,
                args=(job_id, payload, trace_carrier),
                job_id=job_id,
                result_ttl=86400,
                failure_ttl=86400,
                retry=Retry(max=5, interval=[10, 30, 60, 120, 300])
            )
            return JobResponse(job_id=str(job.id), status="PENDING")
        except (redis.exceptions.ConnectionError, RuntimeError) as exc:
            import logging
            logging.getLogger(__name__).warning("Redis enqueue failed (%s), running via bounded compute pool", exc)
            from suspensionlab.backend.core.compute_governance import bounded_run
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(bounded_run(run_job, job_id, payload, trace_carrier))
            return JobResponse(job_id=job_id, status="PENDING")

    # Redis unavailable: Graceful in-process bounded execution fallback
    from suspensionlab.backend.services.quota import assert_can_run_job
    await assert_can_run_job(user, db)

    job_id = str(uuid.uuid4())
    opt_params = req.params.model_dump()
    opt_params["objective_type"] = req.objective_type
    opt_params["max_travel"] = req.max_travel
    new_job = JobRecord(
        id=uuid.UUID(job_id),
        user_id=uuid.UUID(user.user_id),
        team_id=uuid.UUID(user.team_id) if getattr(user, "team_id", None) else None,
        job_type="OPTIMIZE_QUARTER",
        status="PENDING",
        params=opt_params,
        profile=req.profile.model_dump()
    )
    db.add(new_job)
    await db.commit()

    try:
        from suspensionlab.backend.security.audit import record_audit_event
        await record_audit_event(
            db=db,
            event_type="OPTIMIZATION_SUBMITTED",
            user_id=str(user.user_id),
            team_id=str(user.team_id) if getattr(user, "team_id", None) else None,
            artifact_id=job_id,
            metadata={
                "job_id": job_id,
                "job_type": "OPTIMIZE_QUARTER",
                "objective_type": req.objective_type,
                "max_travel": req.max_travel,
                "idempotency_hash": idem_hash,
            }
        )
    except Exception as e:
        import logging
        logging.getLogger("security_audit").warning("Audit logging warning for optimization: %s", e)

    payload = {
        "params": req.params.model_dump(),
        "profile": req.profile.model_dump(),
        "objective_type": req.objective_type,
        "max_travel": req.max_travel
    }
    trace_carrier = {}
    inject(trace_carrier)

    from suspensionlab.backend.core.compute_governance import bounded_run
    import asyncio
    loop = asyncio.get_running_loop()
    loop.create_task(bounded_run(run_job, job_id, payload, trace_carrier))

    return JobResponse(job_id=job_id, status="PENDING")

@router.get("/optimize/active")
async def get_active_job(
    user: UserContext = Depends(require_permission(Permission.SIMULATION_READ)),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Returns any actively computing job to rehydrate the UI on refresh.
    """
    uid = uuid.UUID(str(user.user_id))
    result = await db.execute(
        select(JobRecord).where(
            JobRecord.user_id == uid,
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
    user: UserContext = Depends(require_permission(Permission.SIMULATION_READ)),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Returns the user's recent optimization job history."""
    from sqlalchemy import select, desc
    uid = uuid.UUID(str(user.user_id))
    result = await db.execute(
        select(JobRecord)
        .where(JobRecord.user_id == uid)
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
    user: UserContext = Depends(require_permission(Permission.SIMULATION_RUN))
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
