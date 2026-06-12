import logging
import time
import json
import asyncio
import os
from datetime import datetime
from opentelemetry import trace
from opentelemetry.propagate import extract
from rq import get_current_job
import redis.asyncio as aioredis
from sqlalchemy import select

from suspensionlab.backend.observability import WORKER_JOBS_TOTAL, WORKER_JOB_DURATION

from suspensionlab.backend.database.models.job import JobRecord

from suspensionlab.physics.exceptions import MathConvergenceError
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile
from suspensionlab.physics.optimizer import optimize_setup

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class NonRetryableJobError(Exception):
    """Exception that tells RQ to fail immediately and not retry."""
    pass

async def _worker_heartbeat_async(job_id: str, db, r_conn):
    """Background task to pulse heartbeat to PostgreSQL and Redis."""
    try:
        while True:
            await asyncio.sleep(1.0)
            
            # DB heartbeat (sharing the same async session)
            try:
                result = await db.execute(select(JobRecord).where(JobRecord.id == job_id))
                hb_job = result.scalars().first()
                if hb_job:
                    hb_job.last_heartbeat = datetime.utcnow()
                    await db.commit()
            except Exception as e:
                logger.warning(f"Heartbeat DB error: {str(e)}")
            
            # Redis heartbeat
            try:
                cached = await r_conn.get(f"job_status:{job_id}")
                user_id = json.loads(cached).get("user_id") if cached else None
                res_data = {"job_id": job_id, "status": "RUNNING", "user_id": user_id, "result": None, "error": None}
                await r_conn.setex(f"job_status:{job_id}", 86400, json.dumps(res_data))
            except Exception:
                pass
    except asyncio.CancelledError:
        pass


async def _run_job_async(job_id: str, payload: dict, ctx, span, start_time: float):
    """Core async job lifecycle execution."""
    from suspensionlab.backend.database.core import SessionLocal
    
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    r_conn = aioredis.from_url(redis_url)
    
    async with SessionLocal() as db:
        try:
            result = await db.execute(select(JobRecord).where(JobRecord.id == job_id))
            job_record = result.scalars().first()
            if not job_record:
                logger.error(f"Job {job_id} not found in DB.")
                return

            job_type = job_record.job_type
            span.set_attribute("job.type", job_type)
            job_record.status = "RUNNING"
            await db.commit()

            # Start the background heartbeat task, passing the shared session
            heartbeat_task = asyncio.create_task(_worker_heartbeat_async(job_id, db, r_conn))

            res = None
            try:
                # --- Polimorphic Job Routing ---
                if job_type == "OPTIMIZE_QUARTER":
                    p = QuarterCarParams(**payload["params"])
                    r = RoadProfile(**payload["profile"])
                    objective = payload["objective_type"]
                    max_travel = payload["max_travel"]
                    span.set_attribute("objective.type", objective)
                    
                    # Execute CPU-bound math in a thread so it doesn't block the async heartbeat
                    res = await asyncio.to_thread(optimize_setup, p, r, objective, max_travel, None)
                    
                elif job_type == "SWEEP_QUARTER":
                    from suspensionlab.backend.api.routes.simulate.sweep import perform_sweep_sync
                    res = await asyncio.to_thread(perform_sweep_sync, payload)
                    
                elif job_type == "MONTE_CARLO_QUARTER":
                    res = await asyncio.to_thread(perform_monte_carlo_sync, payload)

                # elif job_type == "SIMULATE_HALF": ...
                # elif job_type == "SIMULATE_FULL": ...
                else:
                    raise ValueError(f"Unknown job_type: {job_type}")
                # ---------------------------------
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            job_record.status = "COMPLETED"
            job_record.result = res
            job_record.schema_version = 1
            await db.commit()
            span.set_attribute("job.status", "COMPLETED")
            
            cached = await r_conn.get(f"job_status:{job_id}")
            user_id = json.loads(cached).get("user_id") if cached else None
            res_data = {"job_id": job_id, "status": "COMPLETED", "user_id": user_id, "result": res, "error": None}
            await r_conn.setex(f"job_status:{job_id}", 300, json.dumps(res_data))
                
            WORKER_JOBS_TOTAL.labels(queue="default", status="completed").inc()
            WORKER_JOB_DURATION.labels(queue="default").observe(time.time() - start_time)
            return res
            
        except (ValueError, MathConvergenceError, ZeroDivisionError) as math_err:
            if 'heartbeat_task' in locals() and not heartbeat_task.done():
                heartbeat_task.cancel()
            
            from sqlalchemy import update
            await db.execute(update(JobRecord).where(JobRecord.id == job_id).values(
                status="FAILED",
                error=f"Compute Error: {str(math_err)}"
            ))
            await db.commit()
            span.record_exception(math_err)
            span.set_attribute("job.status", "FAILED")
            
            cached = await r_conn.get(f"job_status:{job_id}")
            user_id = json.loads(cached).get("user_id") if cached else None
            res_data = {"job_id": job_id, "status": "FAILED", "user_id": user_id, "result": None, "error": f"Compute Error: {str(math_err)}"}
            await r_conn.setex(f"job_status:{job_id}", 300, json.dumps(res_data))
                
            WORKER_JOBS_TOTAL.labels(queue="default", status="failed_math").inc()
            WORKER_JOB_DURATION.labels(queue="default").observe(time.time() - start_time)
            raise NonRetryableJobError("Math/domain exception. Do not retry.") from math_err
            
        except Exception as e:
            if 'heartbeat_task' in locals() and not heartbeat_task.done():
                heartbeat_task.cancel()
            await db.rollback()
            
            # Explicitly mark as failed so it doesn't zombie if this is the last retry
            from sqlalchemy import update
            await db.execute(update(JobRecord).where(JobRecord.id == job_id).values(
                status="FAILED",
                error=f"Transient Error: {str(e)}"
            ))
            await db.commit()
            
            logger.warning(f"Transient error in job {job_id}: {str(e)}")
            span.record_exception(e)
            WORKER_JOBS_TOTAL.labels(queue="default", status="failed_transient").inc()
            WORKER_JOB_DURATION.labels(queue="default").observe(time.time() - start_time)
            raise e
            
        finally:
            await r_conn.aclose()


def run_job(job_id: str, payload: dict, trace_carrier: dict = None):
    """
    Unified worker entrypoint for all async compute tasks.
    RQ requires this to be a synchronous function. We immediately bridge
    into an asyncio event loop for the duration of the job.
    """
    ctx = extract(trace_carrier) if trace_carrier else None
    start_time = time.time()
    
    with tracer.start_as_current_span("rq.run_job", context=ctx) as span:
        span.set_attribute("job.id", job_id)
        return asyncio.run(_run_job_async(job_id, payload, ctx, span, start_time))

def perform_monte_carlo_sync(payload_dict: dict) -> dict:
    import numpy as np
    from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis
    
    iters = payload_dict["iterations"]
    tol = payload_dict["tolerance_pct"] / 100.0
    
    p_dict = payload_dict["params"]
    base_ks = p_dict.get("k_s", 25000.0)
    base_c = p_dict.get("c", 2050.0)
    base_kt = p_dict.get("k_t", 200000.0)
    
    # Generate samples
    ks_samples = np.random.normal(base_ks, base_ks * tol, iters)
    c_samples = np.random.normal(base_c, base_c * tol, iters)
    kt_samples = np.random.normal(base_kt, base_kt * tol, iters)
    
    profile = RoadProfile(**payload_dict["profile"])
    
    body_accel_list = []
    tire_load_list = []
    
    for i in range(iters):
        p = QuarterCarParams(**p_dict)
        p.k_s = max(1000, ks_samples[i])
        p.c = max(100, c_samples[i])
        p.k_t = max(10000, kt_samples[i])
        
        sim_res = run_quarter_car_analysis(p, profile)
        body_accel_list.append(sim_res.rms_body_accel_wk)
        tire_load_list.append(sim_res.rms_tire_load)
        
    mean_body = float(np.mean(body_accel_list))
    std_body = float(np.std(body_accel_list))
    p95_body = float(np.percentile(body_accel_list, 95))
    
    mean_tire = float(np.mean(tire_load_list))
    std_tire = float(np.std(tire_load_list))
    
    return {
        "iterations": iters,
        "tolerance_pct": payload_dict["tolerance_pct"],
        "mean_rms_body_accel_wk": mean_body,
        "std_rms_body_accel_wk": std_body,
        "p95_rms_body_accel_wk": p95_body,
        "mean_rms_tire_load": mean_tire,
        "std_rms_tire_load": std_tire
    }
