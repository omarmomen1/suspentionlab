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

async def _worker_heartbeat_async(job_id: str, r_conn):
    """Background task to pulse heartbeat to Redis."""
    try:
        while True:
            await asyncio.sleep(1.0)
            
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
    from suspensionlab.backend.database.core import get_worker_session_maker
    
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    r_conn = aioredis.from_url(redis_url)
    
    SessionLocal = get_worker_session_maker()
    async with SessionLocal() as db:
        try:
            import uuid
            job_uuid = uuid.UUID(job_id)
            result = await db.execute(select(JobRecord).where(JobRecord.id == job_uuid))
            job_record = result.scalars().first()
            if not job_record:
                logger.error(f"Job {job_id} not found in DB.")
                return

            job_type = job_record.job_type
            span.set_attribute("job.type", job_type)
            job_record.status = "RUNNING"
            await db.commit()

            # Start the background heartbeat task for Redis only
            heartbeat_task = asyncio.create_task(_worker_heartbeat_async(job_id, r_conn))

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

                elif job_type == "SIMULATE_QUARTER":
                    from suspensionlab.physics.quarter_car import run_quarter_car_analysis
                    p = QuarterCarParams(**payload["params"])
                    r = RoadProfile(**payload["profile"])
                    # Run the heavy math simulation in a background thread and collect the dict
                    raw_res = await asyncio.to_thread(run_quarter_car_analysis, p, r)
                    import numpy as np
                    res_dict = raw_res.__dict__.copy()
                    for k, v in res_dict.items():
                        if isinstance(v, np.ndarray):
                            res_dict[k] = v.tolist()
                    res = res_dict
                    
                elif job_type == "SIMULATE_HALF":
                    from suspensionlab.physics.half_car import HalfCarParams, run_half_car_analysis
                    p = HalfCarParams(**payload["params"])
                    r = RoadProfile(**payload["profile"])
                    raw_res = await asyncio.to_thread(run_half_car_analysis, p, r)
                    import numpy as np
                    res_dict = raw_res.__dict__.copy()
                    for k, v in res_dict.items():
                        if isinstance(v, np.ndarray):
                            res_dict[k] = v.tolist()
                    res = res_dict
                    
                elif job_type == "SIMULATE_FULL":
                    from suspensionlab.physics.full_car import FullCarParams, run_full_car_analysis, FourCornerRoadProfile
                    from suspensionlab.physics.quarter_car import _road_profile_fn
                    import numpy as np

                    pdump = payload["params"].copy()
                    asymmetry = pdump.pop("road_asymmetry", 0.3)
                    # pop off unused damper keys that might cause validation errors
                    for k in ["damper_curve_v_f", "damper_curve_f_f", "damper_curve_v_r", "damper_curve_f_r"]:
                        pdump.pop(k, None)
                    p = FullCarParams(**pdump)
                    
                    base_profile = RoadProfile(**payload["profile"])
                    zr_fn, _ = _road_profile_fn(base_profile)
                    dt = 0.002
                    time_array = np.arange(0.0, base_profile.duration, dt)
                    
                    z_road_f = np.array([float(zr_fn(np.array([t]))[0]) for t in time_array])
                    t_delay = p.L / p.speed_mps if p.speed_mps > 0 else 0.0
                    z_road_r = np.array([float(zr_fn(np.array([t - t_delay]))[0]) if t - t_delay >= 0 else 0.0 for t in time_array])
                    
                    z_road_fr = z_road_f * asymmetry
                    z_road_rr = z_road_r * asymmetry
                    
                    profile = FourCornerRoadProfile(
                        time=time_array, 
                        z_rfl=z_road_f, 
                        z_rfr=z_road_fr, 
                        z_rrl=z_road_r, 
                        z_rrr=z_road_rr
                    )
                    raw_res = await asyncio.to_thread(run_full_car_analysis, p, profile)
                    res_dict = raw_res.__dict__.copy()
                    for k, v in res_dict.items():
                        if isinstance(v, np.ndarray):
                            res_dict[k] = v.tolist()
                    res = res_dict
                    
                elif job_type == "SIMULATE_ACTIVE":
                    from suspensionlab.physics.active_quarter_car import ActiveQuarterCarParams, simulate_active_time_response
                    from suspensionlab.physics.quarter_car import simulate_time_response, compute_metrics
                    p_active = ActiveQuarterCarParams(**payload["params"])
                    profile = RoadProfile(profile_type="step", amplitude=payload.get("bump_height", 0.1), duration=3.0)
                    
                    active_res = await asyncio.to_thread(simulate_active_time_response, p_active, profile)
                    p_passive = QuarterCarParams(
                        m_s=p_active.m_s, m_u=p_active.m_u, k_s=p_active.k_s, c=1500.0, k_t=p_active.k_t, MR=p_active.MR
                    )
                    passive_res = await asyncio.to_thread(simulate_time_response, p_passive, profile)
                    passive_metrics = compute_metrics(passive_res, p_passive)
                    
                    res = {
                        "time": active_res.time.tolist(),
                        "active_ddz_s": active_res.ddz_s.tolist(),
                        "active_susp_travel": active_res.susp_travel.tolist(),
                        "active_rms_accel": float(active_res.rms_body_accel),
                        "passive_ddz_s": passive_res["ddz_s"].tolist(),
                        "passive_susp_travel": passive_res["susp_travel"].tolist(),
                        "passive_rms_accel": float(passive_metrics["rms_body_accel"])
                    }
                    
                elif job_type == "SIMULATE_HANDLING":
                    from suspensionlab.physics.handling_model import HandlingParams, simulate_maneuver
                    import numpy as np
                    
                    pdump = payload["params"].copy()
                    if pdump.get("tire_coeffs"):
                        from suspensionlab.physics.magic_formula import TireCoeffs
                        pdump["tire_coeffs"] = TireCoeffs(**pdump["tire_coeffs"])
                    else:
                        pdump.pop("tire_coeffs", None)
                    params = HandlingParams(**pdump)
                    
                    v_init = payload.get("v_init_kph", 100.0) / 3.6
                    maneuver_type = payload.get("maneuver_type")
                    
                    if maneuver_type == "Step Steer (J-Turn)":
                        def steer(t): return 0.05 if t > 1.0 else 0.0
                        def throttle(t): return 0.0
                        def brake(t): return 0.0
                        duration = 5.0
                    elif maneuver_type == "Sine Sweep (Slalom)":
                        def steer(t): return 0.04 * np.sin(2 * np.pi * 0.5 * t) if t > 1.0 else 0.0
                        def throttle(t): return 0.2
                        def brake(t): return 0.0
                        duration = 8.0
                    elif maneuver_type == "Constant Radius Cornering":
                        def steer(t): return 0.03 * (t/2.0 if t < 2.0 else 1.0)
                        def throttle(t): return 0.4
                        def brake(t): return 0.0
                        duration = 10.0
                    else: # Brake in Turn
                        def steer(t): return 0.03 if t > 1.0 else 0.0
                        def throttle(t): return 0.0
                        def brake(t): return 0.8 if t > 3.0 else 0.0
                        duration = 6.0
                        
                    raw_res = await asyncio.to_thread(simulate_maneuver, params, v_init, steer, throttle, brake, duration)
                    for k, v in raw_res.items():
                        if isinstance(v, np.ndarray):
                            raw_res[k] = v.tolist()
                    res = raw_res
                    
                elif job_type == "SIMULATE_DURABILITY":
                    # For simplicity, fallback if not implemented
                    raise NotImplementedError("Durability worker not yet implemented")

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

            # Outbound webhooks (Tier C2) — fire-and-forget, never blocks.
            if user_id:
                from suspensionlab.backend.services.webhooks import fire_and_forget
                fire_and_forget(str(user_id), "job.completed", {
                    "job_id": job_id,
                    "status": "COMPLETED",
                    "finished_at": time.time(),
                })
            return res
            
        except (ValueError, MathConvergenceError, ZeroDivisionError) as math_err:
            if 'heartbeat_task' in locals() and not heartbeat_task.done():
                heartbeat_task.cancel()
            
            from sqlalchemy import update
            await db.execute(update(JobRecord).where(JobRecord.id == job_uuid).values(
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

            # Outbound webhooks (Tier C2)
            if user_id:
                from suspensionlab.backend.services.webhooks import fire_and_forget
                fire_and_forget(str(user_id), "job.failed", {
                    "job_id": job_id,
                    "status": "FAILED",
                    "error": f"Compute Error: {str(math_err)}",
                    "finished_at": time.time(),
                })
            raise NonRetryableJobError("Math/domain exception. Do not retry.") from math_err
            
        except Exception as e:
            if 'heartbeat_task' in locals() and not heartbeat_task.done():
                heartbeat_task.cancel()
            await db.rollback()
            
            # Explicitly mark as failed so it doesn't zombie if this is the last retry
            from sqlalchemy import update
            await db.execute(update(JobRecord).where(JobRecord.id == job_uuid).values(
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
    
    import copy
    base_p = QuarterCarParams(**p_dict)
    
    for i in range(iters):
        p = copy.copy(base_p)
        p.k_s = max(1000, float(ks_samples[i]))
        p.c = max(100, float(c_samples[i]))
        p.k_t = max(10000, float(kt_samples[i]))
        
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
