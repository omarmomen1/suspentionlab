"""
backend/metrics_registry.py
===========================
SuspensionLab PRO — Canonical Metric Registry

Single source of truth for all metric names, types, labels, and descriptions
used across:
- Python application instrumentation
- Kubernetes Helm charts
- Prometheus scraping & recording rules
- Prometheus alerting rules
- Grafana dashboards

Any metric queried in alerts or dashboards MUST exist in this registry.
Drift is enforced via CI in `tests/test_metric_consistency.py`.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Set, Literal, Any
import json

MetricType = Literal["counter", "gauge", "histogram", "summary"]


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    type: MetricType
    description: str
    labels: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "labels": self.labels,
        }


CANONICAL_METRICS: Dict[str, MetricDefinition] = {
    # ── API Layer ──
    "suspensionlab_api_requests_total": MetricDefinition(
        name="suspensionlab_api_requests_total",
        type="counter",
        description="Total API requests received by method, route, and status code",
        labels=["method", "route", "status_code"],
    ),
    "suspensionlab_api_request_duration_seconds": MetricDefinition(
        name="suspensionlab_api_request_duration_seconds",
        type="histogram",
        description="API request latency in seconds",
        labels=["method", "route"],
    ),

    # ── Database Pool ──
    "suspensionlab_db_connection_pool_active": MetricDefinition(
        name="suspensionlab_db_connection_pool_active",
        type="gauge",
        description="Active (checked out) connections in SQLAlchemy pool",
        labels=[],
    ),
    "suspensionlab_db_connection_pool_size": MetricDefinition(
        name="suspensionlab_db_connection_pool_size",
        type="gauge",
        description="Configured total size of SQLAlchemy connection pool",
        labels=[],
    ),
    "suspensionlab_db_connected": MetricDefinition(
        name="suspensionlab_db_connected",
        type="gauge",
        description="Database connectivity health indicator (1=connected, 0=unreachable)",
        labels=[],
    ),

    # ── Redis & Cache ──
    "suspensionlab_redis_connected": MetricDefinition(
        name="suspensionlab_redis_connected",
        type="gauge",
        description="Redis connectivity health indicator (1=connected, 0=unreachable)",
        labels=[],
    ),

    # ── Customer & Tenancy ──
    "suspensionlab_customer_jobs_total": MetricDefinition(
        name="suspensionlab_customer_jobs_total",
        type="counter",
        description="Jobs submitted per customer subscription tier",
        labels=["plan"],
    ),

    # ── Queue & Orchestrator ──
    "suspensionlab_queue_depth": MetricDefinition(
        name="suspensionlab_queue_depth",
        type="gauge",
        description="Current number of pending simulation jobs in queue",
        labels=["queue"],
    ),
    "suspensionlab_job_enqueue_latency_seconds": MetricDefinition(
        name="suspensionlab_job_enqueue_latency_seconds",
        type="histogram",
        description="Time spent submitting a job to Redis queue",
        labels=["queue"],
    ),
    "suspensionlab_queue_wait_duration_seconds": MetricDefinition(
        name="suspensionlab_queue_wait_duration_seconds",
        type="histogram",
        description="Time spent waiting in queue before a worker begins execution",
        labels=["queue"],
    ),

    # ── Worker Health & State ──
    "suspensionlab_worker_jobs_total": MetricDefinition(
        name="suspensionlab_worker_jobs_total",
        type="counter",
        description="Total worker jobs processed by queue and outcome status",
        labels=["queue", "status"],
    ),
    "suspensionlab_worker_job_duration_seconds": MetricDefinition(
        name="suspensionlab_worker_job_duration_seconds",
        type="histogram",
        description="Worker job execution time in seconds",
        labels=["queue"],
    ),
    "suspensionlab_worker_state": MetricDefinition(
        name="suspensionlab_worker_state",
        type="gauge",
        description="Current worker lifecycle state (1=active in state: idle, busy, stopping)",
        labels=["worker_id", "state"],
    ),
    "suspensionlab_worker_crashes_total": MetricDefinition(
        name="suspensionlab_worker_crashes_total",
        type="counter",
        description="Total worker unhandled crashes detected",
        labels=["worker_id"],
    ),
    "suspensionlab_worker_oom_kills_total": MetricDefinition(
        name="suspensionlab_worker_oom_kills_total",
        type="counter",
        description="Total worker out-of-memory terminations detected",
        labels=["worker_id"],
    ),

    # ── Solver & Physics Observability ──
    "suspensionlab_solver_runs_total": MetricDefinition(
        name="suspensionlab_solver_runs_total",
        type="counter",
        description="Solver executions by model, solver, backend, and outcome",
        labels=["model", "solver", "backend", "outcome"],
    ),
    "suspensionlab_physics_failures_total": MetricDefinition(
        name="suspensionlab_physics_failures_total",
        type="counter",
        description="Physics failure events (math_convergence, nan_inf, contact_loss, out_of_domain, validation_regression)",
        labels=["model", "failure_type"],
    ),
    "suspensionlab_fallback_events_total": MetricDefinition(
        name="suspensionlab_fallback_events_total",
        type="counter",
        description="Explicit solver or backend fallback transitions recorded",
        labels=["model", "from_backend", "to_backend", "reason"],
    ),
    "suspensionlab_model_validity_score": MetricDefinition(
        name="suspensionlab_model_validity_score",
        type="gauge",
        description="Latest model validity score (0-100) assessed per model",
        labels=["model"],
    ),
    "suspensionlab_simulation_cancellations_total": MetricDefinition(
        name="suspensionlab_simulation_cancellations_total",
        type="counter",
        description="Cancelled or timed-out simulations per model",
        labels=["model"],
    ),
    "suspensionlab_physics_solver_iterations": MetricDefinition(
        name="suspensionlab_physics_solver_iterations",
        type="histogram",
        description="Iteration count distribution for iterative physics solvers",
        labels=["model", "solver"],
    ),
    "suspensionlab_physics_solver_convergence": MetricDefinition(
        name="suspensionlab_physics_solver_convergence",
        type="gauge",
        description="Numerical solver convergence status indicator (1=converged, 0=diverged)",
        labels=["model", "solver"],
    ),
    "suspensionlab_physics_execution_duration_seconds": MetricDefinition(
        name="suspensionlab_physics_execution_duration_seconds",
        type="histogram",
        description="Pure physics computation execution time in seconds",
        labels=["model", "solver", "backend"],
    ),
    "suspensionlab_physics_contact_loss_events_total": MetricDefinition(
        name="suspensionlab_physics_contact_loss_events_total",
        type="counter",
        description="Tire-road contact loss events detected during dynamic simulation",
        labels=["model"],
    ),
    "suspensionlab_physics_out_of_domain_events_total": MetricDefinition(
        name="suspensionlab_physics_out_of_domain_events_total",
        type="counter",
        description="Out-of-domain geometry or physical parameter violations detected",
        labels=["model"],
    ),
    "suspensionlab_physics_nan_inf_events_total": MetricDefinition(
        name="suspensionlab_physics_nan_inf_events_total",
        type="counter",
        description="NaN or Inf numerical state violations detected",
        labels=["model"],
    ),
    "suspensionlab_physics_validation_score": MetricDefinition(
        name="suspensionlab_physics_validation_score",
        type="gauge",
        description="Rigorous numerical & physical validation score (0-100)",
        labels=["model"],
    ),
}


def get_all_metric_names() -> Set[str]:
    """Returns set of all registered canonical metric names."""
    return set(CANONICAL_METRICS.keys())


def is_registered_metric(name: str) -> bool:
    """Check whether a given metric name exists in the canonical registry."""
    base = name
    if base in CANONICAL_METRICS:
        return True
    if f"{base}_total" in CANONICAL_METRICS:
        return True
    for suffix in ("_bucket", "_sum", "_count"):
        if base.endswith(suffix):
            candidate = base[:-len(suffix)]
            if candidate in CANONICAL_METRICS:
                return True
            if f"{candidate}_total" in CANONICAL_METRICS:
                return True
    return False


def export_registry_json() -> str:
    """Serializes the canonical metric registry to formatted JSON."""
    data = {k: v.to_dict() for k, v in CANONICAL_METRICS.items()}
    return json.dumps(data, indent=2)
