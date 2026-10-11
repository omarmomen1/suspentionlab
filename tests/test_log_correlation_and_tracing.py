"""
tests/test_log_correlation_and_tracing.py
=========================================
STEP 3 & STEP 4 Tests:
- Step 3: Every important job carries the 7 correlation fields into worker logs:
  request_id, trace_id, job_id, user_id, organization_id, team_id, model_family.
- Step 4: Distributed tracing propagates context:
  HTTP -> queue -> worker -> physics with child spans for major solver stages
  (prepare_inputs, solve, post_process, model_validity).
"""

import uuid
import time
import logging
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import set_tracer_provider

from suspensionlab.backend.security.logging_config import (
    set_job_correlation_context,
    get_job_correlation_context,
    clear_job_correlation_context,
    JobCorrelationFilter,
)
from suspensionlab.backend.workers.unified_worker import run_job


def test_log_correlation_context_and_filter():
    """Verify that setting correlation context injects all 7 fields into logger records."""
    clear_job_correlation_context()

    req_id = str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    job_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    model_family = "quarter_car"

    set_job_correlation_context(
        request_id=req_id,
        trace_id=trace_id,
        job_id=job_id,
        user_id=user_id,
        organization_id=org_id,
        team_id=team_id,
        model_family=model_family,
    )

    ctx = get_job_correlation_context()
    assert ctx["request_id"] == req_id
    assert ctx["trace_id"] == trace_id
    assert ctx["job_id"] == job_id
    assert ctx["user_id"] == user_id
    assert ctx["organization_id"] == org_id
    assert ctx["team_id"] == team_id
    assert ctx["model_family"] == model_family

    # Test that logging filter attaches these to LogRecord
    flt = JobCorrelationFilter()
    record = logging.LogRecord("test_logger", logging.INFO, "test.py", 10, "Simulating quarter car", (), None)
    flt.filter(record)

    assert record.request_id == req_id
    assert record.trace_id == trace_id
    assert record.job_id == job_id
    assert record.user_id == user_id
    assert record.organization_id == org_id
    assert record.team_id == team_id
    assert record.model_family == model_family

    clear_job_correlation_context()


def test_distributed_tracing_hierarchy_and_child_spans(monkeypatch):
    """
    Verify distributed trace propagation and major solver child span hierarchy:
    rq.run_job -> physics.prepare_inputs
               -> physics.solve
               -> physics.post_process
               -> physics.model_validity
    Ensures zero per-iteration spans exist.
    """
    # Reset global OpenTelemetry provider to allow re-registration
    trace._TRACER_PROVIDER = None

    # Configure in-memory span exporter
    provider = TracerProvider()
    memory_exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
    set_tracer_provider(provider)

    from suspensionlab.backend.workers import unified_worker
    unified_worker.tracer = provider.get_tracer("unified_worker_test")

    job_id = str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    req_id = str(uuid.uuid4())

    correlation = {
        "request_id": req_id,
        "trace_id": trace_id,
        "job_id": job_id,
        "user_id": str(uuid.uuid4()),
        "organization_id": str(uuid.uuid4()),
        "team_id": str(uuid.uuid4()),
        "model_family": "quarter_car",
        "enqueued_at": time.time(),
    }

    payload = {
        "params": {
            "m_s": 250.0,
            "m_u": 35.0,
            "k_s": 25000.0,
            "c": 2000.0,
            "k_t": 190000.0,
        },
        "profile": {
            "profile_type": "sine",
            "amplitude": 0.05,
            "frequency": 2.0,
            "duration": 0.5,
        },
        "empirical_telemetry": [{"t": i * 0.01, "accel": 0.2} for i in range(120)],
        "correlation_pct": 95.0,
        "tire_calibrated": True,
        "aero_calibrated": True,
        "kinematics_valid": "PASS",
        "_correlation": correlation,
    }

    # Mock DB record and redis
    from unittest.mock import AsyncMock, MagicMock, patch
    mock_db = AsyncMock()
    mock_job_record = MagicMock()
    mock_job_record.id = uuid.UUID(job_id)
    mock_job_record.job_type = "SIMULATE_QUARTER"
    mock_job_record.user_id = uuid.UUID(correlation["user_id"])
    mock_job_record.status = "PENDING"

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_job_record
    mock_db.execute.return_value = mock_result

    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = mock_db

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True

    with patch("suspensionlab.backend.database.core.get_worker_session_maker", return_value=mock_session_maker):
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = run_job(job_id, payload, trace_carrier={"correlation": correlation})

    assert result is not None
    assert "observability" in result
    obs = result["observability"]
    assert obs["solver"] == "RK45"
    assert obs["backend"] == "scipy"
    assert obs["convergence"] is True
    assert obs["validation"]["score"] >= 70.0

    # Inspect captured spans
    spans = memory_exporter.get_finished_spans()
    span_names = [s.name for s in spans]

    # Verify meaningful hierarchical stages exist
    assert "rq.run_job" in span_names
    assert "physics.prepare_inputs" in span_names
    assert "physics.solve" in span_names
    assert "physics.post_process" in span_names
    assert "physics.model_validity" in span_names

    # Verify no per-numerical-iteration spans exist
    iteration_spans = [name for name in span_names if "step" in name.lower() or "iteration" in name.lower()]
    assert len(iteration_spans) == 0, f"Found per-iteration spans: {iteration_spans}"

    # Clean up global TracerProvider to prevent test pollution
    trace._TRACER_PROVIDER = None
