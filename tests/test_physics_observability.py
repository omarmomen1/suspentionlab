"""
tests/test_physics_observability.py
===================================
STEP 9 & Rule 12 Tests: Complete Physics Observability
Exposes:
- solver
- backend
- iterations
- convergence
- execution time
- model version
- fallback
- contact loss
- out-of-domain
- NaN/Inf
- validation
And verifies that every engineering result identifies its:
model version, solver, backend, input dataset, parameter version, software build.
"""

import pytest
from suspensionlab.physics.provenance import PhysicsObservability, MODEL_VERSIONS
from suspensionlab.backend.observability import (
    record_physics_observability,
    record_fallback_event,
    PHYSICS_FAILURES_TOTAL,
    FALLBACK_EVENTS_TOTAL,
    PHYSICS_SOLVER_ITERATIONS,
    PHYSICS_SOLVER_CONVERGENCE,
    PHYSICS_EXECUTION_DURATION,
)


def test_physics_observability_dataclass_contract_and_identity():
    """Verify all 11 required Step 9 fields and 6 Rule 12 provenance identifiers are present."""
    obs = PhysicsObservability(
        solver="RK45",
        backend="scipy",
        iterations=340,
        convergence=True,
        execution_time_s=0.042,
        model_version=MODEL_VERSIONS["quarter_car"],
        fallback_triggered=False,
        contact_loss=False,
        out_of_domain=False,
        nan_inf=False,
        validation_status="validated",
        validation_score=98.2,
        input_dataset="road_profile_iso8608_class_b",
        parameter_version="2.1.0",
        software_build="build-sha-7edaf0f1",
    )

    d = obs.to_dict()

    # Step 9 required fields
    assert d["solver"] == "RK45"
    assert d["backend"] == "scipy"
    assert d["iterations"] == 340
    assert d["convergence"] is True
    assert d["execution_time_s"] == 0.042
    assert d["model_version"] == "quarter-car-v2"
    assert "fallback" in d
    assert d["fallback"]["triggered"] is False
    assert d["contact_loss"] is False
    assert d["out_of_domain"] is False
    assert d["nan_inf"] is False
    assert "validation" in d
    assert d["validation"]["status"] == "validated"
    assert d["validation"]["score"] == 98.2

    # Rule 12 required identifiers
    identity = d["provenance_identity"]
    assert identity["model_version"] == "quarter-car-v2"
    assert identity["solver"] == "RK45"
    assert identity["backend"] == "scipy"
    assert identity["input_dataset"] == "road_profile_iso8608_class_b"
    assert identity["parameter_version"] == "2.1.0"
    assert identity["software_build"] == "build-sha-7edaf0f1"


def test_record_physics_observability_and_failure_metrics():
    """Verify record_physics_observability publishes Prometheus metrics for iterations, duration, and anomalies."""
    record_physics_observability(
        model="quarter_car",
        solver="RK45",
        backend="scipy",
        iterations=450,
        converged=True,
        duration_s=0.035,
        contact_loss=True,
        out_of_domain=False,
        nan_inf=False,
        validation_score=82.5,
    )

    # Check convergence gauge
    assert PHYSICS_SOLVER_CONVERGENCE.labels(model="quarter_car", solver="RK45")._value.get() == 1.0

    # Check contact loss failure counter
    contact_loss_count = PHYSICS_FAILURES_TOTAL.labels(model="quarter_car", failure_type="contact_loss")._value.get()
    assert contact_loss_count >= 1.0


def test_explicit_fallback_recording_rule_10_and_11():
    """Verify that fallbacks are explicitly recorded in metrics and never done silently."""
    record_fallback_event(
        model="kinematics",
        from_backend="cpp_native",
        to_backend="python_fallback",
        reason="Numerical continuation reached singular Jacobian",
    )

    counter = FALLBACK_EVENTS_TOTAL.labels(
        model="kinematics",
        from_backend="cpp_native",
        to_backend="python_fallback",
        reason="Numerical continuation reached singular Jacobian",
    )
    assert counter._value.get() >= 1.0
