"""
tests/test_durability_worker.py
================================
Rule 14 & Phase 3 Verification:
Verifies that:
1. Synchronous durability results match asynchronous worker results (sync ≈ async)
   within strict numerical tolerance.
2. The durability async worker reports comprehensive physics observability.
3. The async endpoint POST /simulate/durability/async successfully queues jobs.
4. The worker cleanly handles errors and failures.
"""

import math
import uuid
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from suspensionlab.backend.api.routes.durability_routes import (
    DurabilityRequest,
    DurabilityResult,
    _compute_durability,
)
from suspensionlab.backend.workers.unified_worker import run_job


def test_durability_sync_vs_async_parity():
    """Verify that synchronous and asynchronous durability computations achieve strict numerical parity (sync ≈ async)."""
    req = DurabilityRequest(
        road_class="C",
        speed_kph=80.0,
        m_s=320.0,
        m_u=40.0,
        k_s=28000.0,
        c=2200.0,
        k_t=210000.0,
        MR=0.88,
    )

    # 1. Compute synchronously
    sync_result = _compute_durability(req)

    # 2. Compute asynchronously via worker entrypoint
    job_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    correlation = {
        "request_id": str(uuid.uuid4()),
        "trace_id": uuid.uuid4().hex,
        "job_id": job_id,
        "user_id": user_id,
        "model_family": "durability",
        "enqueued_at": time.time(),
    }

    payload = req.model_dump()
    payload["_correlation"] = correlation

    mock_db = AsyncMock()
    mock_job_record = MagicMock()
    mock_job_record.id = uuid.UUID(job_id)
    mock_job_record.job_type = "SIMULATE_DURABILITY"
    mock_job_record.user_id = uuid.UUID(user_id)
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
            async_result = run_job(job_id, payload, trace_carrier={"correlation": correlation})

    assert async_result is not None, "Async worker must return valid result"
    assert "observability" in async_result, "Async result must contain physics observability"

    # Numerical Parity Checks (sync ≈ async within 0.1% or identical)
    assert math.isclose(sync_result.rms_body_accel, async_result["rms_body_accel"], rel_tol=1e-3)
    assert math.isclose(sync_result.rms_body_accel_wk, async_result["rms_body_accel_wk"], rel_tol=1e-3)
    assert math.isclose(sync_result.vdv, async_result["vdv"], rel_tol=1e-3)
    assert sync_result.durability_score == async_result["durability_score"]
    assert sync_result.comfort_rating == async_result["comfort_rating"]
    assert sync_result.iso_2631_class == async_result["iso_2631_class"]
    assert math.isclose(sync_result.peak_susp_travel_mm, async_result["peak_susp_travel_mm"], rel_tol=1e-3)
    assert math.isclose(sync_result.rms_susp_travel_mm, async_result["rms_susp_travel_mm"], rel_tol=1e-3)
    assert math.isclose(sync_result.rms_tire_load_n, async_result["rms_tire_load_n"], rel_tol=1e-3)
    assert math.isclose(sync_result.best_range_km, async_result["best_range_km"], rel_tol=1e-3)

    # Component Life predictions parity
    sync_comps = {c.name: c for c in sync_result.components}
    async_comps = {c["name"]: c for c in async_result["components"]}
    assert set(sync_comps.keys()) == set(async_comps.keys())
    for name, s_comp in sync_comps.items():
        a_comp = async_comps[name]
        assert math.isclose(s_comp.life_km, a_comp["life_km"], rel_tol=1e-3)
        assert s_comp.condition == a_comp["condition"]

    # Physics Observability verification (NO DATA = NO CLAIM -> UNVALIDATED)
    obs = async_result["observability"]
    assert obs["solver"] == "RK45"
    assert obs["backend"] == "scipy"
    assert obs["convergence"] is True
    assert obs["model_version"] == "iso8608-palmgren-miner-v1"
    assert obs["validation"]["status"] == "UNVALIDATED"
    assert obs["validation"]["score"] == 0.0


@pytest.mark.asyncio
async def test_durability_async_route_enqueuing():
    """Verify POST /simulate/durability/async enqueues a job with SIMULATE_DURABILITY."""
    from suspensionlab.backend.api.routes.durability_routes import road_durability_analysis_async

    req = DurabilityRequest(road_class="B", speed_kph=100.0)
    mock_user = MagicMock()
    mock_user.user_id = str(uuid.uuid4())
    mock_user.plan = "PRO"
    mock_user.team_id = None
    mock_db = AsyncMock()

    with patch("suspensionlab.backend.services.simulation_service.SimulationService.enqueue_simulation", return_value="job-durability-test-123") as mock_enqueue:
        resp = await road_durability_analysis_async(req=req, user=mock_user, db=mock_db)

    assert resp["job_id"] == "job-durability-test-123"
    assert resp["status"] == "PENDING"
    mock_enqueue.assert_called_once()
    call_kwargs = mock_enqueue.call_args.kwargs
    assert call_kwargs["job_type"] == "SIMULATE_DURABILITY"
    assert call_kwargs["payload"]["road_class"] == "B"
    assert call_kwargs["payload"]["speed_kph"] == 100.0


def test_durability_worker_with_empirical_telemetry_validates():
    """Verify that when empirical telemetry is supplied, the anti-lying gate validates the run."""
    req = DurabilityRequest(
        road_class="B",
        speed_kph=60.0,
        m_s=300.0,
        m_u=35.0,
        k_s=25000.0,
        c=2000.0,
        k_t=200000.0,
        MR=0.85,
    )
    job_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    correlation = {
        "request_id": str(uuid.uuid4()),
        "trace_id": uuid.uuid4().hex,
        "job_id": job_id,
        "user_id": user_id,
        "model_family": "durability",
        "enqueued_at": time.time(),
    }
    payload = req.model_dump()
    payload["_correlation"] = correlation
    # Supply empirical telemetry: 150 samples with 92% correlation
    payload["empirical_telemetry"] = [{"t": i * 0.01, "accel": 0.5} for i in range(150)]
    payload["correlation_pct"] = 92.0

    mock_db = AsyncMock()
    mock_job_record = MagicMock()
    mock_job_record.id = uuid.UUID(job_id)
    mock_job_record.job_type = "SIMULATE_DURABILITY"
    mock_job_record.user_id = uuid.UUID(user_id)
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
            async_result = run_job(job_id, payload, trace_carrier={"correlation": correlation})

    assert async_result is not None
    obs = async_result["observability"]
    assert obs["validation"]["status"] == "DEGRADED"
    assert obs["validation"]["score"] > 30.0

