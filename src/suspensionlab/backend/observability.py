import os
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# ── PROMETHEUS METRICS ────────────────────────────────────────────────────────
# Rate/Error: API Requests
API_REQUESTS_TOTAL = Counter(
    "suspensionlab_api_requests_total",
    "Total API requests received",
    ["method", "route", "status_code"]
)

# Duration: API Latency
API_REQUEST_DURATION = Histogram(
    "suspensionlab_api_request_duration_seconds",
    "API request latency in seconds",
    ["method", "route"]
)

# Rate/Error: Worker Jobs
WORKER_JOBS_TOTAL = Counter(
    "suspensionlab_worker_jobs_total",
    "Total worker jobs processed",
    ["queue", "status"]
)

# Duration: Worker Execution
WORKER_JOB_DURATION = Histogram(
    "suspensionlab_worker_job_duration_seconds",
    "Worker job execution time in seconds",
    ["queue"]
)

# Saturation: Queue Depth  (#28 — actually updated by workers/orchestrator.py)
QUEUE_DEPTH = Gauge(
    "suspensionlab_queue_depth",
    "Current number of pending jobs in queue",
    ["queue"]
)

# Duration: time spent enqueueing (Redis round-trip + RQ bookkeeping)
JOB_QUEUE_LATENCY = Histogram(
    "suspensionlab_job_enqueue_latency_seconds",
    "Time spent submitting a job to the queue",
    ["queue"]
)

# Physics observability: solver outcomes per model
SOLVER_RUNS_TOTAL = Counter(
    "suspensionlab_solver_runs_total",
    "Solver executions by model and outcome",
    ["model", "outcome"]   # outcome: converged | convergence_failed | validation_failed | error
)

# Physics observability: model validity scores seen by the validity engine
MODEL_VALIDITY_SCORE = Gauge(
    "suspensionlab_model_validity_score",
    "Latest MODEL VALIDITY score (0-100) assessed per model",
    ["model"]
)

# Rate: simulation cancellations (client aborts / timeouts)
SIMULATION_CANCELLATIONS_TOTAL = Counter(
    "suspensionlab_simulation_cancellations_total",
    "Cancelled or timed-out simulations",
    ["model"]
)

# Per-customer compute usage (bytes-free label = user id hash prefix)
CUSTOMER_JOBS_TOTAL = Counter(
    "suspensionlab_customer_jobs_total",
    "Jobs submitted per customer",
    ["plan"]
)


def record_model_validity(model: str, score: float) -> None:
    """Publish a MODEL VALIDITY score observation. Non-fatal."""
    try:
        MODEL_VALIDITY_SCORE.labels(model=model).set(float(score))
    except Exception:
        pass


def record_solver_outcome(model: str, outcome: str) -> None:
    """Record a solver run outcome: converged|convergence_failed|validation_failed|error."""
    try:
        SOLVER_RUNS_TOTAL.labels(model=model, outcome=outcome).inc()
    except Exception:
        pass

# Utilization: DB Pool
DB_POOL_ACTIVE = Gauge(
    "suspensionlab_db_connection_pool_active",
    "Active connections in SQLAlchemy pool"
)

# ── OPENTELEMETRY TRACING ─────────────────────────────────────────────────────

def setup_opentelemetry():
    """Initializes the OpenTelemetry TracerProvider."""
    # In production, this would use OTLPSpanExporter to send to a collector.
    # We use ConsoleSpanExporter for local debugging unless OTLP is configured.
    provider = TracerProvider()
    
    # We'll export to console in development, or nowhere if we don't want noise.
    if os.getenv("ENABLE_OTEL_CONSOLE_EXPORT", "false").lower() == "true":
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        
    trace.set_tracer_provider(provider)

def get_tracer(name: str):
    """Returns an OpenTelemetry tracer for the given module name."""
    return trace.get_tracer(name)
