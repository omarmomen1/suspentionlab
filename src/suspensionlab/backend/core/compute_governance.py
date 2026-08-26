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

from fastapi import Depends
from suspensionlab.backend.security.auth import UserContext, verify_api_key

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

# ── Monthly simulation quota / metered overage (Tier A4) ─────────────────────
# "PRO includes 500 sims/mo" — every inline simulation request increments a
# monthly counter; exceeding the quota returns 402 with an upgrade CTA.
# The counter is the billing-grade metering record (Redis, TTL'd past month
# end so partial-month usage survives).

SIM_QUOTAS = {
    "FREE": 50,
    "PRO": 500,
    "ENTERPRISE": 5000,
}
MONTHLY_USAGE_TTL_S = 60 * 60 * 24 * 40  # 40 days — survives month boundary


def _month_key() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m")


def monthly_usage_key(user_id: str) -> str:
    return f"sim_usage:{user_id}:{_month_key()}"


async def get_monthly_usage(user_id: str) -> int:
    """Current-month simulation count for a user (0 when Redis is down)."""
    try:
        from suspensionlab.backend.core.redis_client import get_async_redis_conn
        redis_conn = get_async_redis_conn()
        if redis_conn is None:
            return 0
        value = await redis_conn.get(monthly_usage_key(user_id))
        return int(value or 0)
    except Exception:
        logger.warning("get_monthly_usage failed for user %s", user_id)
        return 0


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


# ── Inline-compute guard (round-2 hostile audit fix #2) ──────────────────────
#
# Inline simulation endpoints (AI engineer, model validity, kinematics,
# durability, analytics) execute in-request instead of going through the job
# orchestrator, so `assert_user_concurrency` never sees them. This dependency
# caps concurrently-executing inline simulations per user via a Redis counter
# with the same per-plan limits. Fail-open when Redis is unavailable (matches
# the codebase-wide DEV behaviour), fail-closed on limit breach.

INLINE_COUNTER_TTL_S = 300  # safety expiry so crashed requests cannot leak slots


async def inline_compute_guard(user: UserContext = Depends(verify_api_key)):
    """FastAPI dependency: cap in-flight inline simulations per user/plan."""
    from fastapi import HTTPException

    redis_conn = None
    try:
        from suspensionlab.backend.core.redis_client import get_async_redis_conn
        redis_conn = get_async_redis_conn()
    except Exception:
        redis_conn = None

    if redis_conn is None:
        logger.warning("inline_compute_guard: Redis unavailable — inline concurrency cap not enforced.")
        yield user
        return

    key = f"inline_conc:{user.user_id}"
    limit = PLAN_CONCURRENCY.get(str(user.plan), PLAN_CONCURRENCY["FREE"])
    current = await redis_conn.incr(key)
    await redis_conn.expire(key, INLINE_COUNTER_TTL_S)
    if current > limit:
        await redis_conn.decr(key)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Concurrency limit reached: your {user.plan} plan allows {limit} concurrent "
                f"simulation(s). Wait for the current one to finish or upgrade."
            ),
        )

    # ── Monthly quota metering (Tier A4) ─────────────────────────────────
    usage_key = monthly_usage_key(user.user_id)
    used = await redis_conn.incr(usage_key)
    await redis_conn.expire(usage_key, MONTHLY_USAGE_TTL_S)
    quota = SIM_QUOTAS.get(str(user.plan), SIM_QUOTAS["FREE"])
    if used > quota:
        await redis_conn.decr(usage_key)
        await redis_conn.decr(key)
        raise HTTPException(
            status_code=402,
            detail=(
                f"Monthly simulation quota reached ({quota}/{quota} on the {user.plan} plan "
                f"for {_month_key()}). Upgrade your plan or buy simulation credits to continue."
            ),
        )

    try:
        yield user
    finally:
        try:
            await redis_conn.decr(key)
        except Exception:
            logger.warning("inline_compute_guard: failed to release slot for user %s.", user.user_id)
