import uuid
import time
import json
import asyncio
import redis.exceptions
from opentelemetry.propagate import inject
from opentelemetry import trace
from rq import Retry
from sqlalchemy import update, select

from suspensionlab.backend.workers.task_queue import job_queue, priority_job_queue
from suspensionlab.backend.workers.unified_worker import run_job
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.core.errors import RedisUnavailableError
from suspensionlab.backend.security.logging_config import request_id_ctx
from suspensionlab.backend.observability import record_customer_job

class SimulationService:
    """
    Domain service for orchestrating simulations, decoupling the API layer from
    the physics and worker layers (Phase 3 Architecture).
    """

    @staticmethod
    async def enqueue_simulation(
        user_id: str,
        plan: str,
        job_type: str,
        payload: dict,
        db,
        team_id: str | None = None,
        organization_id: str | None = None,
    ) -> str:
        """Enqueues a simulation job and returns the job ID.

        - Propagates team_id and organization_id for multi-tenant telemetry.
        - Enforces per-plan concurrency cap before accepting the job.
        - Records real customer jobs metric by subscription tier.
        - Injects distributed trace context and full 7-tuple log correlation metadata.
        """
        # ── Compute governance (#26) — per-user/per-plan concurrency cap ──
        from suspensionlab.backend.core.compute_governance import assert_user_concurrency
        await assert_user_concurrency(db, user_id, plan)

        # Record real customer compute usage metric (Step 2)
        record_customer_job(plan)

        # Lookup organization_id if not provided
        if not organization_id:
            try:
                user_res = await db.execute(select(User.organization_id).where(User.id == uuid.UUID(str(user_id))))
                org_val = user_res.scalar()
                if org_val:
                    organization_id = str(org_val)
            except Exception:
                pass

        # ── Trial Governance: Enforce 7-day expiration & 50 simulation quota ──
        from suspensionlab.backend.services.trial_service import TrialService
        trial = await TrialService.assert_trial_access(
            db,
            user={"user_id": user_id, "organization_id": organization_id, "plan": plan},
            action="simulate",
            delta=1,
        )
        if trial:
            await TrialService.record_trial_usage(
                db,
                user={"user_id": user_id, "organization_id": organization_id, "plan": plan},
                action="simulate",
                delta=1,
            )

        job_id = str(uuid.uuid4())
        
        # Create Job Record in DB
        new_job = JobRecord(
            id=uuid.UUID(job_id),
            user_id=uuid.UUID(str(user_id)),
            team_id=uuid.UUID(str(team_id)) if team_id else None,
            job_type=job_type,
            status="PENDING",
            params=payload.get("params", {}),
            profile=payload.get("profile", {}),
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

        # Map job type to model family
        model_family_map = {
            "OPTIMIZE_QUARTER": "quarter_car",
            "SIMULATE_QUARTER": "quarter_car",
            "SWEEP_QUARTER": "quarter_car",
            "MONTE_CARLO_QUARTER": "quarter_car",
            "SIMULATE_HALF": "half_car",
            "SIMULATE_FULL": "full_car",
            "SIMULATE_ACTIVE": "active_quarter_car",
            "SIMULATE_HANDLING": "handling",
            "SIMULATE_DURABILITY": "durability",
        }
        model_family = model_family_map.get(job_type, "quarter_car")

        # Capture distributed trace context and full 7-tuple correlation (Step 3 & 4)
        current_span = trace.get_current_span()
        span_ctx = current_span.get_span_context() if current_span else None
        trace_id = format(span_ctx.trace_id, "032x") if (span_ctx and span_ctx.is_valid) else str(uuid.uuid4().hex)
        req_id = request_id_ctx.get()

        correlation_meta = {
            "request_id": req_id,
            "trace_id": trace_id,
            "job_id": job_id,
            "user_id": str(user_id),
            "organization_id": str(organization_id or "-"),
            "team_id": str(team_id or "-"),
            "model_family": model_family,
            "enqueued_at": time.time(),
        }

        trace_carrier = {}
        inject(trace_carrier)
        trace_carrier["correlation"] = correlation_meta
        payload["_correlation"] = correlation_meta

        from suspensionlab.backend.workers.orchestrator import submit_simulation_job
        try:
            await submit_simulation_job(
                run_job,
                job_id=job_id,
                payload=payload,
                trace_carrier=trace_carrier,
                plan=plan,
                dedicated=(plan == "ENTERPRISE"),
                result_ttl=86400,
                failure_ttl=86400,
                retry=Retry(max=3, interval=[10, 30, 60]),
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Redis unavailable (%s), executing job %s via bounded compute pool", e, job_id)
            from suspensionlab.backend.core.compute_governance import bounded_run
            loop = asyncio.get_running_loop()
            loop.create_task(bounded_run(run_job, job_id, payload, trace_carrier))
            
        return job_id
