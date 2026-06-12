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

# Saturation: Queue Depth
QUEUE_DEPTH = Gauge(
    "suspensionlab_queue_depth",
    "Current number of pending jobs in queue",
    ["queue"]
)

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
