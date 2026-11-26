import logging
import time
import json
import asyncio
import os
import math
from datetime import datetime, timezone
from opentelemetry import trace
from opentelemetry.propagate import extract
from rq import get_current_job
import redis.asyncio as aioredis
from sqlalchemy import select, update

from suspensionlab.backend.observability import (
    WORKER_JOBS_TOTAL,
    WORKER_JOB_DURATION,
    record_worker_state,
    record_queue_wait_duration,
    record_solver_outcome,
    record_physics_failure,
    record_fallback_event,
    record_physics_observability,
    record_worker_crash,
)
from suspensionlab.backend.security.logging_config import (
    set_job_correlation_context,
    clear_job_correlation_context,
)
from suspensionlab.physics.provenance import MODEL_VERSIONS
from suspensionlab.physics.solver_contract import get_solver_contract

from suspensionlab.backend.database.models.job import JobRecord

from suspensionlab.physics.exceptions import MathConvergenceError
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile
from suspensionlab.physics.optimizer import optimize_setup

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class NonRetryableJobError(Exception):
    """Exception that tells RQ to fail immediately and not retry."""
    pass

def _serialize_for_json(obj, seen=None):
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return None

    import numpy as np
    from enum import Enum
    from dataclasses import is_dataclass, asdict

    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    elif hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        seen.add(obj_id)
        res = _serialize_for_json(obj.to_dict(), seen)
        seen.remove(obj_id)
        return res
    elif is_dataclass(obj) and not isinstance(obj, type):
        seen.add(obj_id)
        res = {k: _serialize_for_json(v, seen) for k, v in asdict(obj).items()}
        seen.remove(obj_id)
        return res
    elif isinstance(obj, (list, tuple, set)):
        seen.add(obj_id)
        res = [_serialize_for_json(item, seen) for item in obj]
        seen.remove(obj_id)
        return res
    elif isinstance(obj, dict):
        seen.add(obj_id)
        res = {str(k): _serialize_for_json(v, seen) for k, v in obj.items()}
        seen.remove(obj_id)
        return res
    elif hasattr(obj, "__dict__"):
        seen.add(obj_id)
        res = {str(k): _serialize_for_json(v, seen) for k, v in obj.__dict__.items()}
        seen.remove(obj_id)
        return res
    return str(obj)


def _check_has_nan_or_inf(obj) -> bool:
    """Recursively checks if any numerical value in a data structure contains NaN or Inf."""
    import numpy as np
    if isinstance(obj, (float, int)):
        return math.isnan(obj) or math.isinf(obj)
    if isinstance(obj, np.ndarray):
        return bool(np.isnan(obj).any() or np.isinf(obj).any())
    if isinstance(obj, dict):
        return any(_check_has_nan_or_inf(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_check_has_nan_or_inf(v) for v in obj)
    return False


async def _worker_heartbeat_async(job_id: str, r_conn):
    """Background task to pulse heartbeat to Redis and update SQL last_heartbeat."""
    from sqlalchemy import update
    import uuid as _uuid
    from suspensionlab.backend.database.core import get_worker_session_maker
    SessionLocal = get_worker_session_maker()
    tick = 0
    try:
        while True:
            await asyncio.sleep(1.0)
            tick += 1
            
            # Redis heartbeat
            if r_conn:
                try:
                    cached = await r_conn.get(f"job_status:{job_id}")
                    user_id = json.loads(cached).get("user_id") if cached else None
                    res_data = {"job_id": job_id, "status": "RUNNING", "user_id": user_id, "result": None, "error": None}
                    await r_conn.setex(f"job_status:{job_id}", 86400, json.dumps(res_data))
                except Exception:
                    pass

            # Update SQL JobRecord.last_heartbeat every 5s
            if tick % 5 == 0:
                try:
                    async with SessionLocal() as db:
                        await db.execute(
                            update(JobRecord)
                            .where(JobRecord.id == _uuid.UUID(str(job_id)))
                            .values(last_heartbeat=datetime.now(timezone.utc))
                        )
                        await db.commit()
                except Exception as e:
                    logger.debug("Failed to update SQL heartbeat for job %s: %s", job_id, e)
    except asyncio.CancelledError:
        pass


async def _run_job_async(job_id: str, payload: dict, ctx, span, start_time: float, correlation: dict):
    """Core async job lifecycle execution with distributed tracing stages and physics observability."""
    from suspensionlab.backend.database.core import get_worker_session_maker
    
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    r_conn = None
    if redis_url:
        try:
            r_conn = aioredis.from_url(redis_url)
        except Exception as e:
            logger.warning(f"Redis connection init failed for job {job_id}: {e}. Continuing without Redis.")
            r_conn = None
    else:
        logger.info(f"REDIS_URL not set; executing job {job_id} in-process without Redis.")
    
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

            # Start the background heartbeat task only when Redis is available
            heartbeat_task = asyncio.create_task(_worker_heartbeat_async(job_id, r_conn)) if r_conn is not None else None

            res = None
            model_family = correlation.get("model_family", "durability" if job_type == "SIMULATE_DURABILITY" else "quarter_car")
            solver_name = "RK45"
            backend_name = "python"
            iterations = 1
            converged = True
            contact_loss = False
            out_of_domain = False
            nan_inf = False
            validation_score = 0.0
            fallback_triggered = False
            from_backend = backend_name
            to_backend = backend_name
            fallback_reason = "none"

            try:
                # ── STAGE 1: PREPARE INPUTS (Child Span) ──────────────────────
                with tracer.start_as_current_span("physics.prepare_inputs") as prep_span:
                    prep_span.set_attribute("physics.model_family", model_family)
                    params_dict = payload.get("params", {})
                    # Domain validation checks
                    for key in ("m_s", "m_u", "k_s", "k_t", "K_spring_f", "K_spring_r"):
                        if key in params_dict:
                            try:
                                val = float(params_dict[key])
                                if math.isnan(val) or math.isinf(val) or val <= 0:
                                    out_of_domain = True
                                    record_physics_failure(model_family, "out_of_domain")
                                    raise ValueError(f"Input parameter '{key}' is invalid ({val}). Must be finite and positive.")
                                if key in ("k_s", "K_spring_f", "K_spring_r") and val < 1000.0:
                                    out_of_domain = True
                                    record_physics_failure(model_family, "out_of_domain")
                                    raise ValueError(f"Input parameter '{key}' ({val} N/m) violates minimum stiffness bound of 1000.0 N/m.")
                                if key == "k_t" and val < 10000.0:
                                    out_of_domain = True
                                    record_physics_failure(model_family, "out_of_domain")
                                    raise ValueError(f"Input parameter '{key}' ({val} N/m) violates minimum tire stiffness bound of 10000.0 N/m.")
                            except (TypeError, ValueError) as ve:
                                out_of_domain = True
                                record_physics_failure(model_family, "out_of_domain")
                                raise ValueError(f"Input parameter '{key}' failed domain validation: {str(ve)}")

                # ── STAGE 2: SOLVER EXECUTION (Child Span) ────────────────────
                solve_start = time.perf_counter()
                with tracer.start_as_current_span("physics.solve") as solve_span:
                    if job_type == "OPTIMIZE_QUARTER":
                        solver_name = "SLSQP"
                        backend_name = "scipy"
                        raw_p = payload.get("params", payload)
                        p = QuarterCarParams(**raw_p)
                        raw_r = payload.get("profile", {"profile_type": "step", "amplitude": 0.04, "duration": 1.0})
                        r = RoadProfile(**raw_r)
                        objective = payload.get("objective_type", "comfort")
                        max_travel = float(payload.get("max_travel", 0.08))
                        solve_span.set_attribute("objective.type", objective)
                        res = await asyncio.to_thread(optimize_setup, p, r, objective, max_travel, None)
                        iterations = 25

                    elif job_type == "SWEEP_QUARTER":
                        solver_name = "RK45"
                        backend_name = "python"
                        from suspensionlab.backend.api.routes.simulate.sweep import perform_sweep_sync
                        res = await asyncio.to_thread(perform_sweep_sync, payload)
                        iterations = len(payload.get("values", [1]))

                    elif job_type == "MONTE_CARLO_QUARTER":
                        solver_name = "RK45"
                        backend_name = "numpy"
                        iterations = payload.get("iterations", 100)
                        res = await asyncio.to_thread(perform_monte_carlo_sync, payload)

                    elif job_type == "SIMULATE_QUARTER":
                        solver_name = "RK45"
                        backend_name = "scipy"
                        from suspensionlab.physics.quarter_car import run_quarter_car_analysis
                        p = QuarterCarParams(**payload["params"])
                        r = RoadProfile(**payload["profile"])
                        raw_res = await asyncio.to_thread(run_quarter_car_analysis, p, r)
                        iterations = getattr(raw_res, "step_count", 500)
                        if getattr(raw_res, "liftoff_time", None) is not None or getattr(raw_res, "minimum_Fz", 1.0) <= 0.0:
                            contact_loss = True
                        res = _serialize_for_json(raw_res)

                    elif job_type == "SIMULATE_HALF":
                        solver_name = "BDF"
                        backend_name = "scipy"
                        from suspensionlab.physics.half_car import HalfCarParams, run_half_car_analysis
                        p = HalfCarParams(**payload["params"])
                        r = RoadProfile(**payload["profile"])
                        raw_res = await asyncio.to_thread(run_half_car_analysis, p, r)
                        iterations = getattr(raw_res, "step_count", 600)
                        res = _serialize_for_json(raw_res)

                    elif job_type == "SIMULATE_FULL":
                        solver_name = "BDF"
                        backend_name = "scipy"
                        from suspensionlab.physics.full_car import FullCarParams, run_full_car_analysis, FourCornerRoadProfile
                        from suspensionlab.physics.quarter_car import _road_profile_fn
                        import numpy as np

                        pdump = payload["params"].copy()
                        asymmetry = pdump.pop("road_asymmetry", 0.3)
                        if "lateral_accel_mps2" in pdump and "lateral_accel_g" not in pdump:
                            pdump["lateral_accel_g"] = float(pdump.pop("lateral_accel_mps2")) / 9.81
                        else:
                            pdump.pop("lateral_accel_mps2", None)
                        p = FullCarParams(**pdump)
                        
                        base_profile = RoadProfile(**payload["profile"])
                        zr_fn, _ = _road_profile_fn(base_profile)
                        dt = 0.002
                        time_array = np.arange(0.0, base_profile.duration, dt)
                        
                        z_road_f = np.array([float(zr_fn(np.array([t]))[0]) for t in time_array])
                        t_delay = p.L / p.speed_mps if p.speed_mps > 0 else 0.0
                        z_road_r = np.array([float(zr_fn(np.array([t - t_delay]))[0]) if t - t_delay >= 0 else 0.0 for t in time_array])
                        
                        profile = FourCornerRoadProfile(
                            time=time_array, 
                            z_rfl=z_road_f, 
                            z_rfr=z_road_f * asymmetry, 
                            z_rrl=z_road_r, 
                            z_rrr=z_road_r * asymmetry,
                        )
                        raw_res = await asyncio.to_thread(run_full_car_analysis, p, profile)
                        iterations = 750
                        res = _serialize_for_json(raw_res)

                    elif job_type == "SIMULATE_ACTIVE":
                        solver_name = "RK45"
                        backend_name = "python"
                        from suspensionlab.physics.active_quarter_car import ActiveQuarterCarParams, simulate_active_time_response
                        from suspensionlab.physics.quarter_car import simulate_time_response, compute_metrics
                        p_active = ActiveQuarterCarParams(**payload["params"])
                        bump_height = float(payload.get("bump_height", 0.1))
                        duration_active = float(payload.get("duration", 3.0))
                        profile = RoadProfile(profile_type="step", amplitude=bump_height, duration=duration_active)
                        
                        # Wave 5A fix: force BOTH active and passive simulations onto
                        # the identical output time grid. Previously the active model
                        # defaulted to t_eval_dt=0.002 while the passive baseline
                        # defaulted to 0.001, so the two responses had different
                        # lengths and did not sample the step bump at the same
                        # timestamps (onset at t = 0.5 s).
                        shared_t_eval_dt = float(payload.get("t_eval_dt", 0.002))
                        active_res = await asyncio.to_thread(
                            simulate_active_time_response, p_active, profile, shared_t_eval_dt
                        )
                        passive_c = float(payload.get("passive_c", payload.get("c", payload.get("params", {}).get("c", 1500.0))))
                        p_passive = QuarterCarParams(
                            m_s=p_active.m_s, m_u=p_active.m_u, k_s=p_active.k_s, c=passive_c, k_t=p_active.k_t, MR=p_active.MR
                        )
                        passive_res = await asyncio.to_thread(
                            simulate_time_response, p_passive, profile, shared_t_eval_dt
                        )
                        # Hard guarantee: identical grids (same duration & dt).
                        if len(passive_res["time"]) != len(active_res.time) or not np.allclose(
                            passive_res["time"], active_res.time, rtol=0.0, atol=1e-12
                        ):
                            raise ValueError(
                                "Active/passive time-grid misalignment: "
                                f"active n={len(active_res.time)}, passive n={len(passive_res['time'])}"
                            )
                        passive_metrics = compute_metrics(passive_res, p_passive)
                        
                        res = {
                            "time": active_res.time.tolist(),
                            "active_ddz_s": active_res.ddz_s.tolist(),
                            "active_susp_travel": active_res.susp_travel.tolist(),
                            "active_rms_accel": float(active_res.rms_body_accel),
                            "passive_ddz_s": passive_res["ddz_s"].tolist(),
                            "passive_susp_travel": passive_res["susp_travel"].tolist(),
                            "passive_rms_accel": float(passive_metrics["rms_body_accel"]),
                        }

                    elif job_type == "SIMULATE_HANDLING":
                        solver_name = "BDF"
                        backend_name = "scipy"
                        from suspensionlab.physics.handling_model import HandlingParams, simulate_maneuver
                        import numpy as np
                        
                        pdump = payload["params"].copy()
                        if pdump.get("tire_coeffs"):
                            from suspensionlab.physics.magic_formula import TireCoeffs
                            pdump["tire_coeffs"] = TireCoeffs(**pdump["tire_coeffs"])
                        else:
                            pdump.pop("tire_coeffs", None)
                        if "h_cg" in pdump and "h_cg_s" not in pdump:
                            pdump["h_cg_s"] = pdump["h_cg"]
                        params = HandlingParams(**pdump)
                        
                        v_init = payload.get("v_init_kph", 100.0) / 3.6
                        maneuver_type = payload.get("maneuver_type")
                        
                        payload_steer = payload.get("steer_amplitude") or payload.get("steer_amp") or payload.get("steer_amplitude_deg")
                        steer_val = None
                        if payload_steer is not None:
                            val = float(payload_steer)
                            steer_val = np.radians(val) if val > 0.5 else val

                        custom_duration = payload.get("duration") or payload.get("duration_s")

                        if maneuver_type == "Step Steer (J-Turn)":
                            amp = steer_val if steer_val is not None else 0.05
                            duration = float(custom_duration) if custom_duration is not None else 5.0
                            def steer(t): return amp if t > 1.0 else 0.0
                            def throttle(t): return 0.0
                            def brake(t): return 0.0
                        elif maneuver_type == "Sine Sweep (Slalom)":
                            amp = steer_val if steer_val is not None else 0.04
                            duration = float(custom_duration) if custom_duration is not None else 8.0
                            freq = float(payload.get("frequency", payload.get("freq", 0.5)))
                            def steer(t): return amp * np.sin(2 * np.pi * freq * t) if t > 1.0 else 0.0
                            def throttle(t): return 0.2
                            def brake(t): return 0.0
                        elif maneuver_type == "Constant Radius Cornering":
                            amp = steer_val if steer_val is not None else 0.03
                            duration = float(custom_duration) if custom_duration is not None else 10.0
                            def steer(t): return amp * (t/2.0 if t < 2.0 else 1.0)
                            def throttle(t): return 0.4
                            def brake(t): return 0.0
                        else:
                            amp = steer_val if steer_val is not None else 0.03
                            duration = float(custom_duration) if custom_duration is not None else 6.0
                            def steer(t): return amp if t > 1.0 else 0.0
                            def throttle(t): return 0.0
                            def brake(t): return 0.8 if t > 3.0 else 0.0
                            
                        raw_res = await asyncio.to_thread(simulate_maneuver, params, v_init, steer, throttle, brake, duration)
                        for k, v in raw_res.items():
                            if isinstance(v, np.ndarray):
                                raw_res[k] = v.tolist()
                        res = raw_res
                        iterations = 600

                    elif job_type == "SIMULATE_DURABILITY":
                        solver_name = "RK45"
                        backend_name = "scipy"
                        from suspensionlab.backend.api.routes.durability_routes import DurabilityRequest, _compute_durability
                        req_data = payload.copy()
                        if "params" in req_data and isinstance(req_data["params"], dict):
                            params_sub = req_data.pop("params")
                            req_data.update(params_sub)
                        dur_req = DurabilityRequest(**req_data)
                        raw_res = await asyncio.to_thread(_compute_durability, dur_req)
                        iterations = 1000
                        res = raw_res.model_dump() if hasattr(raw_res, "model_dump") else raw_res.dict()

                    else:
                        raise ValueError(f"Unknown job_type: {job_type}")

                    solve_duration = time.perf_counter() - solve_start
                    solve_span.set_attribute("physics.solver", solver_name)
                    solve_span.set_attribute("physics.backend", backend_name)
                    solve_span.set_attribute("physics.duration_s", solve_duration)

                # ── STAGE 3: POST-PROCESS (Child Span) ────────────────────────
                with tracer.start_as_current_span("physics.post_process") as post_span:
                    res = _serialize_for_json(res)
                    nan_inf = _check_has_nan_or_inf(res)
                    if nan_inf:
                        record_physics_failure(model_family, "nan_inf")
                    post_span.set_attribute("physics.nan_inf", nan_inf)
                    post_span.set_attribute("physics.contact_loss", contact_loss)

                # ── STAGE 4: MODEL VALIDITY & OBSERVABILITY (Child Span) ───────
                with tracer.start_as_current_span("physics.model_validity") as val_span:
                    from suspensionlab.physics.confidence_banner import (
                        SimulationConfidenceBanner,
                        ValidityStatus,
                    )

                    # Determine scientific solver status according to explicit 7-state contract
                    if nan_inf:
                        final_status = "FAILED_NUMERICAL"
                        validation_status = ValidityStatus.FAILED.value
                        validation_score = 0.0
                    elif not converged:
                        final_status = "FAILED_NUMERICAL"
                        validation_status = ValidityStatus.FAILED.value
                        validation_score = 0.0
                    elif out_of_domain:
                        final_status = "FAILED_INPUT"
                        validation_status = ValidityStatus.OUT_OF_DOMAIN.value
                        validation_score = 0.0
                    elif contact_loss:
                        final_status = "COMPLETED_WITH_WARNINGS"
                        validation_status = ValidityStatus.UNVALIDATED.value
                        validation_score = 0.0
                    else:
                        final_status = "COMPLETED_VALID"
                        validation_status = ValidityStatus.UNVALIDATED.value
                        validation_score = 0.0

                    # Strictly enforce NO DATA = NO CLAIM
                    empirical_data = payload.get("empirical_telemetry")
                    if empirical_data and isinstance(empirical_data, (list, dict)) and len(empirical_data) > 0:
                        eval_banner = SimulationConfidenceBanner.evaluate(
                            correlation_pct=payload.get("correlation_pct"),
                            sample_count=len(empirical_data),
                            model_version=MODEL_VERSIONS.get(model_family, "v2.0"),
                            is_synthetic=payload.get("is_synthetic_telemetry", False),
                            tire_calibrated=payload.get("tire_calibrated", False),
                            aero_calibrated=payload.get("aero_calibrated", False),
                            kinematics_valid=payload.get("kinematics_valid", "NOT_EVALUATED"),
                        )
                        validation_status = eval_banner.validity_status.value
                        validation_score = eval_banner.confidence_score_pct
                        provenance_dict = eval_banner.provenance.to_dict() if eval_banner.provenance else None
                    else:
                        provenance_dict = {
                            "data_source": "none",
                            "sample_count": 0,
                            "metric_name": "unvalidated_simulation",
                            "calculation_method": "none",
                            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                            "model_version": MODEL_VERSIONS.get(model_family, "v2.0"),
                            "validation_protocol": "strict_empirical_verification",
                            "is_synthetic": False,
                        }

                    val_span.set_attribute("physics.validation_score", validation_score)
                    val_span.set_attribute("physics.converged", converged)

                    model_version = MODEL_VERSIONS.get(model_family, "v2.0")
                    observability_block = {
                        "solver": solver_name,
                        "backend": backend_name,
                        "iterations": int(iterations),
                        "convergence": bool(converged),
                        "execution_time_s": round(solve_duration, 4),
                        "model_version": model_version,
                        "fallback": {
                            "triggered": fallback_triggered,
                            "from_backend": from_backend,
                            "to_backend": to_backend,
                            "reason": fallback_reason,
                        },
                        "contact_loss": contact_loss,
                        "out_of_domain": out_of_domain,
                        "nan_inf": nan_inf,
                        "validation": {
                            "status": validation_status,
                            "score": round(validation_score, 1),
                            "provenance": provenance_dict,
                        },
                    }

                    # Attach observability metadata into output
                    if isinstance(res, dict):
                        res["observability"] = observability_block

                    # Publish Prometheus metrics
                    record_physics_observability(
                        model=model_family,
                        solver=solver_name,
                        backend=backend_name,
                        iterations=iterations,
                        converged=converged,
                        duration_s=solve_duration,
                        contact_loss=contact_loss,
                        out_of_domain=out_of_domain,
                        nan_inf=nan_inf,
                        validation_score=validation_score,
                    )
                    record_solver_outcome(
                        model=model_family,
                        solver=solver_name,
                        backend=backend_name,
                        outcome="converged" if (converged and not nan_inf) else "numerical_failure",
                    )

            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass

            # Wave 6: stamp real solver provenance (git-commit build stamp,
            # run_id, input_sha256) onto every successful solver response.
            if isinstance(res, dict):
                try:
                    from suspensionlab.physics.provenance import stamp_solver_result
                    prov_inputs = {k: v for k, v in payload.items() if not k.startswith("_")}
                    stamp_solver_result(res, inputs=prov_inputs, run_id=job_id)
                except Exception as prov_exc:
                    logger.warning("Provenance stamping failed for job %s: %s", job_id, prov_exc)

            job_record.status = final_status
            if final_status.startswith("FAILED"):
                job_record.error = "Numerical failure: NaN or Inf detected in solver output" if nan_inf else "Solver divergence"
            job_record.result = res
            job_record.schema_version = 1
            await db.commit()
            span.set_attribute("job.status", final_status)
            
            user_id = str(job_record.user_id) if job_record and job_record.user_id else None
            if r_conn is not None:
                try:
                    if not user_id:
                        cached = await r_conn.get(f"job_status:{job_id}")
                        user_id = json.loads(cached).get("user_id") if cached else None
                    res_data = {"job_id": job_id, "status": final_status, "user_id": user_id, "result": res, "error": job_record.error}
                    await r_conn.setex(f"job_status:{job_id}", 300, json.dumps(res_data))
                except Exception:
                    pass
                
            WORKER_JOBS_TOTAL.labels(queue="default", status=final_status.lower()).inc()
            WORKER_JOB_DURATION.labels(queue="default").observe(time.time() - start_time)

            if user_id:
                from suspensionlab.backend.services.webhooks import fire_and_forget
                fire_and_forget(str(user_id), f"job.{final_status.lower()}", {
                    "job_id": job_id,
                    "status": final_status,
                    "error": job_record.error,
                    "finished_at": time.time(),
                })
            return res
            
        except ValueError as val_err:
            if 'heartbeat_task' in locals() and heartbeat_task is not None and not heartbeat_task.done():
                heartbeat_task.cancel()
            
            record_solver_outcome(
                model=correlation.get("model_family", "quarter_car"),
                outcome="invalid_input",
            )
            record_physics_failure(
                model=correlation.get("model_family", "quarter_car"),
                failure_type="out_of_domain",
            )

            await db.execute(update(JobRecord).where(JobRecord.id == job_uuid).values(
                status="FAILED_INPUT",
                error=f"Input Validation Error: {str(val_err)}"
            ))
            await db.commit()
            span.record_exception(val_err)
            span.set_attribute("job.status", "FAILED_INPUT")
            
            user_id = None
            if r_conn is not None:
                try:
                    cached = await r_conn.get(f"job_status:{job_id}")
                    user_id = json.loads(cached).get("user_id") if cached else None
                    res_data = {"job_id": job_id, "status": "FAILED_INPUT", "user_id": user_id, "result": None, "error": f"Input Validation Error: {str(val_err)}"}
                    await r_conn.setex(f"job_status:{job_id}", 300, json.dumps(res_data))
                except Exception:
                    pass
                
            WORKER_JOBS_TOTAL.labels(queue="default", status="failed_input").inc()
            WORKER_JOB_DURATION.labels(queue="default").observe(time.time() - start_time)

            if user_id:
                from suspensionlab.backend.services.webhooks import fire_and_forget
                fire_and_forget(str(user_id), "job.failed", {
                    "job_id": job_id,
                    "status": "FAILED_INPUT",
                    "error": f"Input Validation Error: {str(val_err)}",
                    "finished_at": time.time(),
                })
            raise NonRetryableJobError("Input domain exception. Do not retry.") from val_err

        except (MathConvergenceError, ZeroDivisionError) as math_err:
            if 'heartbeat_task' in locals() and heartbeat_task is not None and not heartbeat_task.done():
                heartbeat_task.cancel()
            
            record_solver_outcome(
                model=correlation.get("model_family", "quarter_car"),
                outcome="convergence_failed",
            )
            record_physics_failure(
                model=correlation.get("model_family", "quarter_car"),
                failure_type="math_convergence",
            )

            await db.execute(update(JobRecord).where(JobRecord.id == job_uuid).values(
                status="FAILED_NUMERICAL",
                error=f"Numerical Convergence Error: {str(math_err)}"
            ))
            await db.commit()
            span.record_exception(math_err)
            span.set_attribute("job.status", "FAILED_NUMERICAL")
            
            user_id = None
            if r_conn is not None:
                try:
                    cached = await r_conn.get(f"job_status:{job_id}")
                    user_id = json.loads(cached).get("user_id") if cached else None
                    res_data = {"job_id": job_id, "status": "FAILED_NUMERICAL", "user_id": user_id, "result": None, "error": f"Numerical Convergence Error: {str(math_err)}"}
                    await r_conn.setex(f"job_status:{job_id}", 300, json.dumps(res_data))
                except Exception:
                    pass
                
            WORKER_JOBS_TOTAL.labels(queue="default", status="failed_numerical").inc()
            WORKER_JOB_DURATION.labels(queue="default").observe(time.time() - start_time)

            if user_id:
                from suspensionlab.backend.services.webhooks import fire_and_forget
                fire_and_forget(str(user_id), "job.failed", {
                    "job_id": job_id,
                    "status": "FAILED_NUMERICAL",
                    "error": f"Numerical Convergence Error: {str(math_err)}",
                    "finished_at": time.time(),
                })
            raise NonRetryableJobError("Math convergence exception. Do not retry.") from math_err
            
        except Exception as e:
            if 'heartbeat_task' in locals() and heartbeat_task is not None and not heartbeat_task.done():
                heartbeat_task.cancel()
            await db.rollback()

            record_solver_outcome(
                model=correlation.get("model_family", "quarter_car"),
                outcome="error",
            )
            worker_id = os.environ.get("WORKER_ID") or f"worker-{os.getpid()}"
            record_worker_crash(worker_id)
            
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
            if r_conn is not None:
                try:
                    await r_conn.aclose()
                except Exception:
                    pass


def run_job(job_id: str, payload: dict, trace_carrier: dict = None):
    """
    Unified worker entrypoint for all async compute tasks.
    RQ requires this to be a synchronous function. Bridges into asyncio.
    """
    # ── Step 3: Extract & Set Log Correlation Context ─────────────────────────
    correlation = {}
    if trace_carrier and isinstance(trace_carrier, dict) and "correlation" in trace_carrier:
        correlation = trace_carrier["correlation"]
    elif payload and isinstance(payload, dict) and "_correlation" in payload:
        correlation = payload["_correlation"]

    set_job_correlation_context(
        request_id=correlation.get("request_id"),
        trace_id=correlation.get("trace_id"),
        job_id=job_id,
        user_id=correlation.get("user_id"),
        organization_id=correlation.get("organization_id"),
        team_id=correlation.get("team_id"),
        model_family=correlation.get("model_family"),
    )

    # ── Step 2: Record Worker State & Queue Wait Duration ─────────────────────
    worker_id = os.environ.get("WORKER_ID") or f"worker-{os.getpid()}"
    record_worker_state(worker_id, "busy")

    enqueued_at = correlation.get("enqueued_at")
    if enqueued_at:
        try:
            record_queue_wait_duration("default", max(0.0, time.time() - float(enqueued_at)))
        except Exception:
            pass

    ctx = extract(trace_carrier) if trace_carrier else None
    start_time = time.time()
    
    try:
        with tracer.start_as_current_span("rq.run_job", context=ctx) as span:
            span.set_attribute("job.id", job_id)
            span.set_attribute("job.worker_id", worker_id)
            for k, v in correlation.items():
                if k != "enqueued_at":
                    span.set_attribute(f"job.correlation.{k}", str(v))

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    return executor.submit(
                        asyncio.run,
                        _run_job_async(job_id, payload, ctx, span, start_time, correlation)
                    ).result()
            else:
                return asyncio.run(_run_job_async(job_id, payload, ctx, span, start_time, correlation))
    finally:
        record_worker_state(worker_id, "idle")
        clear_job_correlation_context()


def perform_monte_carlo_sync(payload_dict: dict) -> dict:
    import numpy as np
    from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis
    
    iters = payload_dict["iterations"]
    tol = payload_dict["tolerance_pct"] / 100.0
    
    p_dict = payload_dict["params"]
    base_ks = p_dict.get("k_s", 25000.0)
    base_c = p_dict.get("c", 2050.0)
    base_kt = p_dict.get("k_t", 200000.0)
    
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
