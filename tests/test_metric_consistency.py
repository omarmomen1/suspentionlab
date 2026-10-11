"""
tests/test_metric_consistency.py
================================
Automated CI validation to enforce metric consistency and prevent drift across:
- Python (observability.py & metrics_registry.py)
- Kubernetes Helm templates
- Prometheus alerting rules
- Grafana dashboard panels

STEP 1 & STEP 6 validation:
Every metric queried in alerts or dashboards MUST exist in the canonical registry.
"""

import re
import yaml
import pytest
from suspensionlab.backend.metrics_registry import (
    CANONICAL_METRICS,
    get_all_metric_names,
    is_registered_metric,
)
from suspensionlab.backend import observability


def test_canonical_metric_registry_integrity():
    """All metrics in registry must start with suspensionlab_ and have valid types/descriptions."""
    assert len(CANONICAL_METRICS) >= 15
    for name, metric_def in CANONICAL_METRICS.items():
        assert name.startswith("suspensionlab_"), f"Metric '{name}' does not start with 'suspensionlab_'"
        assert metric_def.type in ("counter", "gauge", "histogram", "summary")
        assert len(metric_def.description.strip()) > 5
        assert isinstance(metric_def.labels, list)


def test_python_observability_metrics_match_registry():
    """All Prometheus metrics instantiated in observability.py must match the canonical registry."""
    registry_names = get_all_metric_names()

    # Verify key metric objects in observability module
    expected_metrics = [
        observability.API_REQUESTS_TOTAL,
        observability.API_REQUEST_DURATION,
        observability.DB_POOL_ACTIVE,
        observability.DB_POOL_SIZE,
        observability.DB_CONNECTED,
        observability.REDIS_CONNECTED,
        observability.CUSTOMER_JOBS_TOTAL,
        observability.QUEUE_DEPTH,
        observability.JOB_QUEUE_LATENCY,
        observability.QUEUE_WAIT_DURATION,
        observability.WORKER_JOBS_TOTAL,
        observability.WORKER_JOB_DURATION,
        observability.WORKER_STATE,
        observability.WORKER_CRASHES_TOTAL,
        observability.WORKER_OOM_KILLS_TOTAL,
        observability.SOLVER_RUNS_TOTAL,
        observability.PHYSICS_FAILURES_TOTAL,
        observability.FALLBACK_EVENTS_TOTAL,
        observability.MODEL_VALIDITY_SCORE,
        observability.SIMULATION_CANCELLATIONS_TOTAL,
        observability.PHYSICS_SOLVER_ITERATIONS,
        observability.PHYSICS_SOLVER_CONVERGENCE,
        observability.PHYSICS_EXECUTION_DURATION,
        observability.PHYSICS_CONTACT_LOSS_TOTAL,
        observability.PHYSICS_OUT_OF_DOMAIN_TOTAL,
        observability.PHYSICS_NAN_INF_TOTAL,
        observability.PHYSICS_VALIDATION_SCORE,
    ]

    for metric_obj in expected_metrics:
        # prometheus_client metric objects store name in _name (may omit _total)
        metric_name = getattr(metric_obj, "_name", "")
        assert is_registered_metric(metric_name), f"Python metric '{metric_name}' is not in canonical registry!"


def test_prometheus_alerting_rules_metric_consistency():
    """
    Extract all suspensionlab_* metric references from alerting-rules.yaml and
    verify 100% compliance with the canonical registry.
    """
    alert_path = "k8s/suspensionlab-chart/templates/monitoring/alerting-rules.yaml"
    with open(alert_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match all tokens starting with suspensionlab_[a-zA-Z0-9_]+
    metric_tokens = set(re.findall(r"\b(suspensionlab_[a-zA-Z0-9_]+)\b", content))
    assert len(metric_tokens) > 0, "No suspensionlab metrics found in alerting rules!"

    unregistered = []
    for token in metric_tokens:
        if not is_registered_metric(token):
            unregistered.append(token)

    assert not unregistered, f"Drift detected in alerting rules! Unregistered metrics: {unregistered}"


def test_grafana_dashboard_metric_consistency():
    """
    Extract all suspensionlab_* metric references from grafana-dashboard.yaml and
    verify 100% compliance with the canonical registry.
    """
    dashboard_path = "k8s/suspensionlab-chart/templates/monitoring/grafana-dashboard.yaml"
    with open(dashboard_path, "r", encoding="utf-8") as f:
        content = f.read()

    metric_tokens = set(re.findall(r"\b(suspensionlab_[a-zA-Z0-9_]+)\b", content))
    assert len(metric_tokens) > 0, "No suspensionlab metrics found in Grafana dashboard!"

    unregistered = []
    for token in metric_tokens:
        if not is_registered_metric(token):
            unregistered.append(token)

    assert not unregistered, f"Drift detected in Grafana dashboard! Unregistered metrics: {unregistered}"


def test_incident_alert_coverage_step6():
    """
    STEP 6 requirement: Ensure alerts exist for:
    - Redis outage
    - queue backlog
    - worker crash
    - OOM
    - solver failure spike
    - physics validation regression
    - DB saturation
    """
    alert_path = "k8s/suspensionlab-chart/templates/monitoring/alerting-rules.yaml"
    with open(alert_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check alert names / expressions
    required_alerts = [
        "RedisOutage",
        "WorkerQueueBacklog",
        "WorkerCrashDetected",
        "WorkerOOMKilled",
        "SolverFailureSpike",
        "PhysicsValidationRegression",
        "DatabaseSaturation",
    ]

    for alert_name in required_alerts:
        assert f"alert: {alert_name}" in content, f"Missing required alert: {alert_name}"


def test_drift_detection_negative_case():
    """Verify that is_registered_metric correctly rejects arbitrary or drifting names."""
    assert not is_registered_metric("suspensionlab_bogus_metric_not_exist")
    assert not is_registered_metric("http_requests_total")
    assert is_registered_metric("suspensionlab_api_requests_total")
    assert is_registered_metric("suspensionlab_api_request_duration_seconds_bucket")
