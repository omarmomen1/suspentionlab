"""
backend/workers/orchestrator.py
================================
Job Orchestrator (#27) — single routing brain between the API and the compute plane.

    API
     │
     ▼
Job Orchestrator  ──►  Standard Queue   (FREE)
     │            ──►  Priority Queue   (PRO)
     │            ──►  Dedicated Queue  (ENTERPRISE, reserved workers)
     ▼
Compute Plane (RQ workers → Python physics / C++ kinematics core)

Also wires real queue telemetry (#28): every submit updates the QUEUE_DEPTH
gauge and records enqueue latency per queue.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from suspensionlab.backend.observability import QUEUE_DEPTH, JOB_QUEUE_LATENCY
from suspensionlab.backend.workers.task_queue import (
    job_queue,
    priority_job_queue,
    dedicated_job_queue,
    QUEUE_NAMES,
)

logger = logging.getLogger(__name__)


def select_queue(plan: str, dedicated: bool = False):
    """Route a job to the correct queue for the customer's plan."""
    if plan == "ENTERPRISE" and dedicated:
        return dedicated_job_queue, "dedicated"
    if plan == "ENTERPRISE":
        return priority_job_queue, "priority_queue"
    if plan == "PRO":
        return priority_job_queue, "priority_queue"
    return job_queue, "default"


def refresh_queue_depth() -> dict[str, int]:
    """
    Poll RQ for real pending-job counts and publish them to Prometheus.
    Called after each submit and exposed via /metrics scrape helpers.
    Failures are non-fatal — metrics must never break submission.
    """
    depths: dict[str, int] = {}
    queues = {"default": job_queue, "priority_queue": priority_job_queue, "dedicated": dedicated_job_queue}
    for name, q in queues.items():
        try:
            depth = len(q)  # RQ Queue supports len() = count of jobs in Redis
        except Exception:
            continue
        depths[name] = depth
        try:
            QUEUE_DEPTH.labels(queue=name).set(depth)
        except Exception:
            pass
    return depths


async def submit_simulation_job(
    run_fn,                      # worker entrypoint (unified_worker.run_job)
    job_id: str,
    payload: dict,
    trace_carrier: dict,
    plan: str,
    dedicated: bool = False,
    **enqueue_kwargs: Any,
):
    """
    Enqueue a simulation onto the plan-appropriate queue with telemetry.
    Returns the name of the queue the job was submitted to.
    """
    queue, queue_name = select_queue(plan, dedicated)

    start = time.perf_counter()
    await __import__("asyncio").to_thread(
        queue.enqueue,
        run_fn,
        args=(job_id, payload, trace_carrier),
        job_id=job_id,
        **enqueue_kwargs,
    )
    elapsed = time.perf_counter() - start

    try:
        JOB_QUEUE_LATENCY.labels(queue=queue_name).observe(elapsed)
    except Exception:
        pass

    # Publish fresh depth (cheap; non-fatal on Redis issues)
    try:
        refresh_queue_depth()
    except Exception:
        pass

    logger.info("Job %s submitted to '%s' queue (plan=%s, %.3fs)", job_id, queue_name, plan, elapsed)
    return queue_name
