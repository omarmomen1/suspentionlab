import os
import time
from typing import Any, Dict, List, Optional
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from suspensionlab.backend.metrics_registry import CANONICAL_METRICS

# ── PROMETHEUS METRICS (Directly from Canonical Registry) ─────────────────────

# Rate/Error: API Requests
API_REQUESTS_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_api_requests_total"].name,
    CANONICAL_METRICS["suspensionlab_api_requests_total"].description,
    CANONICAL_METRICS["suspensionlab_api_requests_total"].labels,
)

# Duration: API Latency
API_REQUEST_DURATION = Histogram(
    CANONICAL_METRICS["suspensionlab_api_request_duration_seconds"].name,
    CANONICAL_METRICS["suspensionlab_api_request_duration_seconds"].description,
    CANONICAL_METRICS["suspensionlab_api_request_duration_seconds"].labels,
)

# Database Connection Pool
DB_POOL_ACTIVE = Gauge(
    CANONICAL_METRICS["suspensionlab_db_connection_pool_active"].name,
    CANONICAL_METRICS["suspensionlab_db_connection_pool_active"].description,
)

DB_POOL_SIZE = Gauge(
    CANONICAL_METRICS["suspensionlab_db_connection_pool_size"].name,
    CANONICAL_METRICS["suspensionlab_db_connection_pool_size"].description,
)

DB_CONNECTED = Gauge(
    CANONICAL_METRICS["suspensionlab_db_connected"].name,
    CANONICAL_METRICS["suspensionlab_db_connected"].description,
)

# Redis / Cache
REDIS_CONNECTED = Gauge(
    CANONICAL_METRICS["suspensionlab_redis_connected"].name,
    CANONICAL_METRICS["suspensionlab_redis_connected"].description,
)

# Customer Compute Usage
CUSTOMER_JOBS_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_customer_jobs_total"].name,
    CANONICAL_METRICS["suspensionlab_customer_jobs_total"].description,
    CANONICAL_METRICS["suspensionlab_customer_jobs_total"].labels,
)

# Queue Depth & Latency
QUEUE_DEPTH = Gauge(
    CANONICAL_METRICS["suspensionlab_queue_depth"].name,
    CANONICAL_METRICS["suspensionlab_queue_depth"].description,
    CANONICAL_METRICS["suspensionlab_queue_depth"].labels,
)

JOB_QUEUE_LATENCY = Histogram(
    CANONICAL_METRICS["suspensionlab_job_enqueue_latency_seconds"].name,
    CANONICAL_METRICS["suspensionlab_job_enqueue_latency_seconds"].description,
    CANONICAL_METRICS["suspensionlab_job_enqueue_latency_seconds"].labels,
)

QUEUE_WAIT_DURATION = Histogram(
    CANONICAL_METRICS["suspensionlab_queue_wait_duration_seconds"].name,
    CANONICAL_METRICS["suspensionlab_queue_wait_duration_seconds"].description,
    CANONICAL_METRICS["suspensionlab_queue_wait_duration_seconds"].labels,
)

# Worker Lifecycle & Jobs
WORKER_JOBS_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_worker_jobs_total"].name,
    CANONICAL_METRICS["suspensionlab_worker_jobs_total"].description,
    CANONICAL_METRICS["suspensionlab_worker_jobs_total"].labels,
)

WORKER_JOB_DURATION = Histogram(
    CANONICAL_METRICS["suspensionlab_worker_job_duration_seconds"].name,
    CANONICAL_METRICS["suspensionlab_worker_job_duration_seconds"].description,
    CANONICAL_METRICS["suspensionlab_worker_job_duration_seconds"].labels,
)

WORKER_STATE = Gauge(
    CANONICAL_METRICS["suspensionlab_worker_state"].name,
    CANONICAL_METRICS["suspensionlab_worker_state"].description,
    CANONICAL_METRICS["suspensionlab_worker_state"].labels,
)

WORKER_CRASHES_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_worker_crashes_total"].name,
    CANONICAL_METRICS["suspensionlab_worker_crashes_total"].description,
    CANONICAL_METRICS["suspensionlab_worker_crashes_total"].labels,
)

WORKER_OOM_KILLS_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_worker_oom_kills_total"].name,
    CANONICAL_METRICS["suspensionlab_worker_oom_kills_total"].description,
    CANONICAL_METRICS["suspensionlab_worker_oom_kills_total"].labels,
)

# Physics Observability & Solver Execution
SOLVER_RUNS_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_solver_runs_total"].name,
    CANONICAL_METRICS["suspensionlab_solver_runs_total"].description,
    CANONICAL_METRICS["suspensionlab_solver_runs_total"].labels,
)

PHYSICS_FAILURES_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_physics_failures_total"].name,
    CANONICAL_METRICS["suspensionlab_physics_failures_total"].description,
    CANONICAL_METRICS["suspensionlab_physics_failures_total"].labels,
)

FALLBACK_EVENTS_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_fallback_events_total"].name,
    CANONICAL_METRICS["suspensionlab_fallback_events_total"].description,
    CANONICAL_METRICS["suspensionlab_fallback_events_total"].labels,
)

MODEL_VALIDITY_SCORE = Gauge(
    CANONICAL_METRICS["suspensionlab_model_validity_score"].name,
    CANONICAL_METRICS["suspensionlab_model_validity_score"].description,
    CANONICAL_METRICS["suspensionlab_model_validity_score"].labels,
)

SIMULATION_CANCELLATIONS_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_simulation_cancellations_total"].name,
    CANONICAL_METRICS["suspensionlab_simulation_cancellations_total"].description,
    CANONICAL_METRICS["suspensionlab_simulation_cancellations_total"].labels,
)

PHYSICS_SOLVER_ITERATIONS = Histogram(
    CANONICAL_METRICS["suspensionlab_physics_solver_iterations"].name,
    CANONICAL_METRICS["suspensionlab_physics_solver_iterations"].description,
    CANONICAL_METRICS["suspensionlab_physics_solver_iterations"].labels,
)

PHYSICS_SOLVER_CONVERGENCE = Gauge(
    CANONICAL_METRICS["suspensionlab_physics_solver_convergence"].name,
    CANONICAL_METRICS["suspensionlab_physics_solver_convergence"].description,
    CANONICAL_METRICS["suspensionlab_physics_solver_convergence"].labels,
)

PHYSICS_EXECUTION_DURATION = Histogram(
    CANONICAL_METRICS["suspensionlab_physics_execution_duration_seconds"].name,
    CANONICAL_METRICS["suspensionlab_physics_execution_duration_seconds"].description,
    CANONICAL_METRICS["suspensionlab_physics_execution_duration_seconds"].labels,
)

PHYSICS_CONTACT_LOSS_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_physics_contact_loss_events_total"].name,
    CANONICAL_METRICS["suspensionlab_physics_contact_loss_events_total"].description,
    CANONICAL_METRICS["suspensionlab_physics_contact_loss_events_total"].labels,
)

PHYSICS_OUT_OF_DOMAIN_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_physics_out_of_domain_events_total"].name,
    CANONICAL_METRICS["suspensionlab_physics_out_of_domain_events_total"].description,
    CANONICAL_METRICS["suspensionlab_physics_out_of_domain_events_total"].labels,
)

PHYSICS_NAN_INF_TOTAL = Counter(
    CANONICAL_METRICS["suspensionlab_physics_nan_inf_events_total"].name,
    CANONICAL_METRICS["suspensionlab_physics_nan_inf_events_total"].description,
    CANONICAL_METRICS["suspensionlab_physics_nan_inf_events_total"].labels,
)

PHYSICS_VALIDATION_SCORE = Gauge(
    CANONICAL_METRICS["suspensionlab_physics_validation_score"].name,
    CANONICAL_METRICS["suspensionlab_physics_validation_score"].description,
    CANONICAL_METRICS["suspensionlab_physics_validation_score"].labels,
)


# ── RECORDING HELPERS ─────────────────────────────────────────────────────────

def record_db_pool_metrics(active: int, size: int) -> None:
    """Publish real SQLAlchemy connection pool statistics."""
    try:
        DB_POOL_ACTIVE.set(float(active))
        DB_POOL_SIZE.set(float(size))
    except Exception:
        pass


def record_dependency_health(db_ok: bool, redis_ok: bool) -> None:
    """Publish external dependency connectivity indicators."""
    try:
        DB_CONNECTED.set(1.0 if db_ok else 0.0)
        REDIS_CONNECTED.set(1.0 if redis_ok else 0.0)
    except Exception:
        pass


def record_customer_job(plan: str) -> None:
    """Record a simulation submitted by a customer subscription plan tier."""
    try:
        tier = (plan or "FREE").upper()
        CUSTOMER_JOBS_TOTAL.labels(plan=tier).inc()
    except Exception:
        pass


def record_queue_depth(queue: str, depth: int) -> None:
    """Record current pending queue length."""
    try:
        QUEUE_DEPTH.labels(queue=queue).set(float(depth))
    except Exception:
        pass


def record_queue_latency(queue: str, duration_seconds: float) -> None:
    """Record latency to enqueue a job."""
    try:
        JOB_QUEUE_LATENCY.labels(queue=queue).observe(duration_seconds)
    except Exception:
        pass


def record_queue_wait_duration(queue: str, duration_seconds: float) -> None:
    """Record latency spent waiting in queue before execution starts."""
    try:
        QUEUE_WAIT_DURATION.labels(queue=queue).observe(duration_seconds)
    except Exception:
        pass


def record_worker_state(worker_id: str, state: str) -> None:
    """
    Set worker lifecycle state (idle, busy, stopping, etc).
    Clears opposing states for this worker.
    """
    try:
        for s in ("idle", "busy", "stopping"):
            WORKER_STATE.labels(worker_id=worker_id, state=s).set(1.0 if s == state else 0.0)
    except Exception:
        pass


def record_worker_crash(worker_id: str) -> None:
    """Record unhandled worker crash."""
    try:
        WORKER_CRASHES_TOTAL.labels(worker_id=worker_id).inc()
    except Exception:
        pass


def record_worker_oom(worker_id: str) -> None:
    """Record worker OOM termination."""
    try:
        WORKER_OOM_KILLS_TOTAL.labels(worker_id=worker_id).inc()
    except Exception:
        pass


def record_solver_outcome(
    model: str,
    outcome: str,
    solver: str = "default",
    backend: str = "python",
) -> None:
    """
    Record a solver execution outcome:
    outcome: converged | convergence_failed | validation_failed | error
    """
    try:
        SOLVER_RUNS_TOTAL.labels(
            model=model,
            solver=solver,
            backend=backend,
            outcome=outcome,
        ).inc()
    except Exception:
        pass


def record_physics_failure(model: str, failure_type: str) -> None:
    """
    Record a physics failure event:
    failure_type: math_convergence | nan_inf | contact_loss | out_of_domain | validation_regression
    """
    try:
        PHYSICS_FAILURES_TOTAL.labels(model=model, failure_type=failure_type).inc()
        if failure_type == "contact_loss":
            PHYSICS_CONTACT_LOSS_TOTAL.labels(model=model).inc()
        elif failure_type == "out_of_domain":
            PHYSICS_OUT_OF_DOMAIN_TOTAL.labels(model=model).inc()
        elif failure_type == "nan_inf":
            PHYSICS_NAN_INF_TOTAL.labels(model=model).inc()
    except Exception:
        pass


def record_fallback_event(
    model: str,
    from_backend: str,
    to_backend: str,
    reason: str,
) -> None:
    """Explicitly record a solver or backend fallback transition (Rule 11)."""
    try:
        FALLBACK_EVENTS_TOTAL.labels(
            model=model,
            from_backend=from_backend,
            to_backend=to_backend,
            reason=reason[:64],
        ).inc()
    except Exception:
        pass


def record_model_validity(model: str, score: float) -> None:
    """Publish a MODEL VALIDITY score observation."""
    try:
        s = float(score)
        MODEL_VALIDITY_SCORE.labels(model=model).set(s)
        PHYSICS_VALIDATION_SCORE.labels(model=model).set(s)
    except Exception:
        pass


def record_physics_observability(
    model: str,
    solver: str,
    backend: str,
    iterations: int,
    converged: bool,
    duration_s: float,
    contact_loss: bool = False,
    out_of_domain: bool = False,
    nan_inf: bool = False,
    validation_score: Optional[float] = None,
) -> None:
    """Publish comprehensive physics observability telemetry."""
    try:
        PHYSICS_SOLVER_ITERATIONS.labels(model=model, solver=solver).observe(float(iterations))
        PHYSICS_SOLVER_CONVERGENCE.labels(model=model, solver=solver).set(1.0 if converged else 0.0)
        PHYSICS_EXECUTION_DURATION.labels(model=model, solver=solver, backend=backend).observe(float(duration_s))

        if contact_loss:
            record_physics_failure(model, "contact_loss")
        if out_of_domain:
            record_physics_failure(model, "out_of_domain")
        if nan_inf:
            record_physics_failure(model, "nan_inf")
        if not converged:
            record_physics_failure(model, "math_convergence")
        if validation_score is not None:
            record_model_validity(model, validation_score)
    except Exception:
        pass


# ── OPENTELEMETRY TRACING ─────────────────────────────────────────────────────

def setup_opentelemetry():
    """Initializes the OpenTelemetry TracerProvider."""
    provider = TracerProvider()
    if os.getenv("ENABLE_OTEL_CONSOLE_EXPORT", "false").lower() == "true":
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


def get_tracer(name: str):
    """Returns an OpenTelemetry tracer for the given module name."""
    return trace.get_tracer(name)


# ── CONFIGURATION & ALERTING VALIDATION ────────────────────────────────────────

def validate_alerting_configuration(raise_on_error: bool = False) -> dict[str, Any]:
    """
    Validates alerting destination configuration on production startup.
    Ensures external alert webhooks/credentials are properly configured if enabled,
    and prevents silent deployment of placeholder values.
    """
    env = os.getenv("ENVIRONMENT", "dev").lower()
    enable_alerts = os.getenv("ENABLE_EXTERNAL_ALERTS", "false").lower() == "true"
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    pagerduty_key = os.getenv("PAGERDUTY_ROUTING_KEY", "").strip()

    status = {
        "enabled": enable_alerts,
        "environment": env,
        "slack_configured": bool(slack_webhook and not slack_webhook.startswith("https://hooks.slack.com/services/YOUR")),
        "pagerduty_configured": bool(pagerduty_key and pagerduty_key != "YOUR_PAGERDUTY_KEY"),
        "is_valid": True,
        "errors": [],
    }

    if enable_alerts or env in ("production", "prod", "staging"):
        if not status["slack_configured"] and not status["pagerduty_configured"]:
            error_msg = (
                "CRITICAL: External alerting is enabled in production/staging, but neither SLACK_WEBHOOK_URL "
                "nor PAGERDUTY_ROUTING_KEY contains valid destination credentials!"
            )
            status["is_valid"] = False
            status["errors"].append(error_msg)
            if raise_on_error:
                raise RuntimeError(error_msg)

    return status


def validate_production_configuration(raise_on_error: bool = False) -> dict[str, Any]:
    """
    Validates configuration secrets and prevents placeholder strings from slipping into production.
    Rejects: 'REPLACE_WITH_', 'changeme', 'default-secret', 'YOUR_'.
    """
    env = os.getenv("ENVIRONMENT", "dev").lower()
    is_prod_or_staging = env in ("production", "prod", "staging")

    FORBIDDEN_PLACEHOLDERS = [
        "REPLACE_WITH_",
        "changeme",
        "default-secret",
        "YOUR_PAGERDUTY_KEY",
        "YOUR_SLACK_WEBHOOK",
    ]

    errors = []
    checked_keys = [
        "SECRET_KEY", "JWT_SECRET_KEY", "DATABASE_URL", "REDIS_HOST",
        "SLACK_WEBHOOK_URL", "PAGERDUTY_ROUTING_KEY", "STRIPE_SECRET_KEY"
    ]

    for key in checked_keys:
        val = os.getenv(key, "")
        if val:
            for forbidden in FORBIDDEN_PLACEHOLDERS:
                if forbidden.lower() in val.lower():
                    errors.append(f"Configuration error: Key '{key}' contains placeholder '{forbidden}'.")

    if is_prod_or_staging and not os.getenv("DATABASE_URL"):
        errors.append("Configuration error: DATABASE_URL must be specified in production/staging.")

    is_valid = len(errors) == 0
    if not is_valid and raise_on_error:
        raise ValueError("\n".join(errors))

    return {
        "is_valid": is_valid,
        "environment": env,
        "errors": errors,
    }
