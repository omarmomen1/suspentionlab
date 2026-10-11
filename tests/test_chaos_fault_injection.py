"""
tests/test_chaos_fault_injection.py
===================================
STEP 8 Tests: Staging fault injection and empirical RPO / RTO validation.
Verifies all 5 fault vectors:
1. DB failure
2. Redis failure
3. Worker kill
4. Pod kill
5. Network disruption
Asserts that measured RTO <= 1800s and measured RPO <= 300s.
"""

import pytest
from suspensionlab.backend.chaos.fault_injector import StagingFaultInjector
from suspensionlab.backend.observability import (
    DB_CONNECTED,
    REDIS_CONNECTED,
    WORKER_CRASHES_TOTAL,
)


@pytest.mark.asyncio
async def test_chaos_db_failure_injection_and_metrics():
    """Verify DB failure injection updates health gauges and measures RTO/RPO."""
    injector = StagingFaultInjector()
    report = await injector.inject_db_failure(disruption_seconds=0.1)

    assert report.fault_type == "DB_FAILURE"
    assert report.rto_seconds >= 0.1
    assert report.rto_seconds <= 1800.0  # RTO SLA
    assert report.rpo_seconds <= 300.0   # RPO SLA
    assert report.status == "PASSED"
    # Verify gauge is restored to healthy (1.0)
    assert DB_CONNECTED._value.get() == 1.0


@pytest.mark.asyncio
async def test_chaos_redis_failure_injection_and_metrics():
    """Verify Redis failure injection updates health gauges and measures RTO/RPO."""
    injector = StagingFaultInjector()
    report = await injector.inject_redis_failure(disruption_seconds=0.1)

    assert report.fault_type == "REDIS_FAILURE"
    assert report.rto_seconds >= 0.1
    assert report.rto_seconds <= 1800.0
    assert report.rpo_seconds <= 300.0
    assert report.status == "PASSED"
    assert REDIS_CONNECTED._value.get() == 1.0


@pytest.mark.asyncio
async def test_chaos_worker_kill_and_crash_metric():
    """Verify worker kill increments worker crash counter and measures recovery."""
    injector = StagingFaultInjector()
    report = await injector.inject_worker_kill("worker-test-crash")

    assert report.fault_type == "WORKER_KILL"
    assert report.rto_seconds <= 1800.0
    assert report.rpo_seconds <= 300.0
    assert report.status == "PASSED"
    assert WORKER_CRASHES_TOTAL.labels(worker_id="worker-test-crash")._value.get() >= 1.0


@pytest.mark.asyncio
async def test_chaos_pod_kill():
    """Verify pod kill simulation measures seamless failover and RTO."""
    injector = StagingFaultInjector()
    report = await injector.inject_pod_kill("api-pod-simulated")

    assert report.fault_type == "POD_KILL"
    assert report.rto_seconds <= 1800.0
    assert report.rpo_seconds == 0.0
    assert report.status == "PASSED"


@pytest.mark.asyncio
async def test_chaos_network_disruption():
    """Verify network disruption injector tests timeout/recovery bounds."""
    injector = StagingFaultInjector()
    report = await injector.inject_network_disruption(duration_seconds=0.1, latency_ms=200.0)

    assert report.fault_type == "NETWORK_DISRUPTION"
    assert report.rto_seconds >= 0.1
    assert report.rto_seconds <= 1800.0
    assert report.rpo_seconds <= 300.0
    assert report.status == "PASSED"


@pytest.mark.asyncio
async def test_full_chaos_drill_summary():
    """Verify full drill runner executes all 5 scenarios and certifies SLA compliance."""
    injector = StagingFaultInjector()
    summary = await injector.run_full_chaos_drill()

    assert summary["scenarios_executed"] == 5
    assert summary["all_passed"] is True
    assert summary["measured_max_rto_seconds"] <= summary["official_target_rto_seconds"]
    assert summary["measured_max_rpo_seconds"] <= summary["official_target_rpo_seconds"]
