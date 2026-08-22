"""
backend/core/compute_governance.py
===================================
Compute-plane protection (#25 / #26).

Two mechanisms:

1. `bounded_run()` — runs blocking simulations on a FIXED-SIZE thread pool.
   Unlike bare `asyncio.wait_for(asyncio.to_thread(...))` — which abandons the
   awaitable on timeout while the thread keeps running (unbounded thread
   accumulation → self-inflicted DoS under load) — the pool size caps total
   concurrent computations at MAX_COMPUTE_WORKERS regardless of traffic.
   Timed-out work still occupies a worker slot until it finishes, so overload
   degrades to queueing instead of CPU saturation.

2. `assert_user_concurrency()` — per-plan cap on concurrently PENDING/RUNNING
   jobs per user, enforced at enqueue time:
       FREE        → 1 concurrent job
       PRO         → 4 concurrent jobs
       ENTERPRISE  → 16 concurrent jobs
   Counted from the authoritative jobs table (no Redis release bookkeeping).
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Bounded compute pool (#25) ────────────────────────────────────────────────

MAX_COMPUTE_WORKERS = max(2, min(8, os.cpu_count() or 4))
_compute_pool = ThreadPoolExecutor(
    max_workers=MAX_COMPUTE_WORKERS,
    thread_name_prefix="sl-compute",
)


async def bounded_run(fn: Callable[..., Any], *args: Any, timeout: float | None = None,
                      model: str | None = None) -> Any:
    """
    Run a blocking callable on the fixed-size compute pool with an optional timeout.

    Guarantees:
      * At most MAX_COMPUTE_WORKERS simulations execute simultaneously process-wide.
      * On timeout the caller gets TimeoutError immediately; the underlying job
        keeps its single worker slot until it exits (it can never spawn siblings).

    (#28) Records solver outcomes to Prometheus physics observability when a
    model name is supplied.
    """
    from suspensionlab.backend.observability import (
        record_solver_outcome, SIMULATION_CANCELLATIONS_TOTAL,
    )
    from suspensionlab.physics.exceptions import MathConvergenceError, PhysicsValidationError

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(_compute_pool, fn, *args)
    try:
        if timeout is not None:
            result = await asyncio.wait_for(future, timeout=timeout)
        else:
            result = await future
    except asyncio.TimeoutError:
        if model:
            try:
                SIMULATION_CANCELLATIONS_TOTAL.labels(model=model).inc()
                record_solver_outcome(model, "cancelled")
            except Exception:
                pass
        raise
    except MathConvergenceError:
        if model:
            try:
                record_solver_outcome(model, "convergence_failed")
            except Exception:
                pass
        raise
    except PhysicsValidationError:
        if model:
            try:
                record_solver_outcome(model, "validation_failed")
            except Exception:
                pass
        raise
    except Exception:
        if model:
            try:
                record_solver_outcome(model, "error")
            except Exception:
                pass
        raise

    if model:
        try:
            record_solver_outcome(model, "converged")
        except Exception:
            pass
    return result


# ── Per-plan concurrency caps (#26) ───────────────────────────────────────────

PLAN_CONCURRENCY = {
    "FREE": 1,
    "PRO": 4,
    "ENTERPRISE": 16,
}


async def assert_user_concurrency(db, user_id: str, plan: str) -> None:
    """
    Reject new jobs when the user already has too many PENDING/RUNNING jobs.
    Raises HTTPException(429) — mapped by the exception handlers.
    """
    import uuid as _uuid
    from sqlalchemy import select, func
    from fastapi import HTTPException
    from suspensionlab.backend.database.models.job import JobRecord

    limit = PLAN_CONCURRENCY.get(plan, PLAN_CONCURRENCY["FREE"])
    active_states = ("PENDING", "RUNNING")

    result = await db.execute(
        select(func.count())
        .select_from(JobRecord)
        .where(
            JobRecord.user_id == _uuid.UUID(user_id),
            JobRecord.status.in_(active_states),
            JobRecord.deleted_at.is_(None),
        )
    )
    active = int(result.scalar_one())

    if active >= limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Concurrency limit reached: your {plan} plan allows {limit} concurrent "
                f"job(s) and you have {active} running. Wait for jobs to finish or upgrade."
            ),
        )
