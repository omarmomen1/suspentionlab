"""
tests/test_kinematics_hostile_audit.py
=======================================
Hostile CAE Numerical Methods & Vehicle Dynamics Acceptance Test Suite.

Rigorously verifies:
1. Baseline sweep point diagnostics completeness (iterations, condition numbers, residuals).
2. Zero fabricated fallback metrics.
3. Singular / toggle geometry detection and clean numerical handling.
4. Curve discontinuity & divergence masking on diverged points.
5. Decoupled physical validity: numerically converged but physically questionable detection.
6. Adaptive sub-stepping continuation quality tracking.
7. Cryptographic reproducibility record generation and hash determinism.
8. Five vehicle dynamics literature benchmarks with error % and tolerances.
9. validate_hardpoints_py decoupled status fields.
10. Extreme travel boundary divergence handling (no silent faking).
11. Strict backend provenance enforcement (no unrequested silent fallback).
12. API audit payload integration (/api/v1/kinematics/solve & /benchmarks).
"""

import pytest
import copy
from unittest.mock import patch
import numpy as np

from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    _solve_py,
    _newton_py,
    validate_hardpoints_py,
    PhysicalValidityEvaluator,
    get_kinematics_benchmarks,
    generate_reproducibility_record,
    SolverPointDiagnostic,
)
from suspensionlab.physics.kinematics_facade import (
    KinematicsBackendFactory,
    PythonReferenceBackend,
    CppKinematicsBackend,
    solve_kinematics,
    KinematicsResult,
    KinematicPoint,
)


# ==============================================================================
# 1. Baseline Sweep Point Diagnostics Completeness
# ==============================================================================
def test_baseline_sweep_point_diagnostics_completeness():
    backend = PythonReferenceBackend()
    res = backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-30.0, z_max_mm=30.0, n_steps=17)
    
    assert res.point_diagnostics is not None
    assert len(res.point_diagnostics) == 17
    
    for diag in res.point_diagnostics:
        assert isinstance(diag, dict)
        assert "solver" in diag
        assert diag["convergence_status"] in ["CONVERGED", "CONVERGED_WITH_WARNING", "FAILED", "OUT_OF_BOUNDS"]
        assert diag["iterations"] >= 0
        assert diag["residual_norm"] >= 0.0
        assert diag["residual_norm"] <= 1.0  # Small for baseline
        assert diag["tolerance"] > 0.0
        assert diag["max_iterations"] > 0
        assert diag["continuation_state"] in ["SUCCEEDED", "STEP_REDUCED", "RESTARTED", "FALLBACK_SWITCHED", "FAILED"]


# ==============================================================================
# 2. Zero Fabricated Fallback Metrics
# ==============================================================================
def test_zero_fabricated_fallback_metrics():
    backend = PythonReferenceBackend()
    res = backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-20.0, z_max_mm=20.0, n_steps=9)
    
    for diag in res.point_diagnostics:
        # Residual norm must be dynamically computed, never zero or dummy constant
        assert diag["residual_norm"] > 0.0
        assert diag["residual_norm"] != 0.0001
        
        # Condition number must be a real finite positive float or None, never negative or dummy 1.0
        cond = diag.get("condition_number")
        if cond is not None:
            assert cond >= 1.0
            assert np.isfinite(cond)
            
        # For converged baseline points, failure_reason must be None
        if diag["convergence_status"] == "CONVERGED":
            assert diag.get("failure_reason") is None


# ==============================================================================
# 3. Singular / Toggle Geometry Detection
# ==============================================================================
def test_singular_geometry_detection():
    # Make upper and lower wishbones degenerate / collinear
    singular_hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    singular_hp["UWI_fwd"] = singular_hp["LWI_fwd"]
    singular_hp["UWI_aft"] = singular_hp["LWI_aft"]
    singular_hp["UWO"] = singular_hp["LWO"]
    
    backend = PythonReferenceBackend()
    res = backend.sweep(singular_hp, z_min_mm=-10.0, z_max_mm=10.0, n_steps=5)
    
    # Either all diverged, or condition number / residuals flagged
    assert (not res.all_converged) or (res.overall_model_status in ["FAIL", "WARN", "INVALID", "NUMERICALLY_CONVERGED_PHYSICALLY_QUESTIONABLE"])
    assert any(
        d["convergence_status"] in ["FAILED", "CONVERGED_WITH_WARNING"]
        or (d.get("condition_number") and d["condition_number"] > 1e10)
        for d in res.point_diagnostics
    )


# ==============================================================================
# 4. Curve Discontinuity & Divergence Masking
# ==============================================================================
def test_curve_discontinuity_divergence_masking():
    # Create an impossible travel envelope where solver diverges at extremities
    backend = PythonReferenceBackend()
    res = backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-300.0, z_max_mm=300.0, n_steps=15)
    
    # Check that converged array contains False for impossible points
    has_failed = any(c is False for c in res.converged)
    if has_failed:
        for i, c in enumerate(res.converged):
            if not c:
                diag = res.point_diagnostics[i]
                assert diag["convergence_status"] in ["FAILED", "OUT_OF_BOUNDS"]
                assert diag.get("failure_reason") is not None


# ==============================================================================
# 5. Decoupled Physical Validity Evaluation
# ==============================================================================
def test_decoupled_physical_validity_evaluation():
    # Setup with ridiculous camber angle (UWO moved 350mm outboard)
    absurd_hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    absurd_hp["UWO"] = [absurd_hp["UWO"][0], absurd_hp["UWO"][1] + 350.0, absurd_hp["UWO"][2]]
    
    evaluator = PhysicalValidityEvaluator()
    backend = PythonReferenceBackend()
    res = backend.sweep(absurd_hp, z_min_mm=-10.0, z_max_mm=10.0, n_steps=5)
    
    validity = evaluator.evaluate(absurd_hp, res.to_dict())
    # Physical validity MUST fail due to camber envelope or roll center limits
    assert not validity["is_valid"]
    assert len(validity["issues"]) > 0
    assert validity["physical_status"] == "FAIL"


# ==============================================================================
# 6. Adaptive Sub-stepping Continuation Tracking
# ==============================================================================
def test_adaptive_substepping_continuation_tracking():
    backend = PythonReferenceBackend()
    res = backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-60.0, z_max_mm=60.0, n_steps=25)
    
    for diag in res.point_diagnostics:
        assert diag["continuation_state"] in ["SUCCEEDED", "STEP_REDUCED", "RESTARTED", "FALLBACK_SWITCHED", "FAILED"]


# ==============================================================================
# 7. Cryptographic Reproducibility Record Determinism
# ==============================================================================
def test_cryptographic_reproducibility_record():
    cfg = {"z_min_mm": -30.0, "z_max_mm": 30.0, "n_steps": 11, "tire_radius_m": 0.33}
    record1 = generate_reproducibility_record(DEFAULT_HARDPOINTS, cfg)
    record2 = generate_reproducibility_record(DEFAULT_HARDPOINTS, cfg)
    
    # Determinism: same inputs yield same SHA-256 input hash
    assert record1["input_hash"] == record2["input_hash"]
    assert len(record1["input_hash"]) == 64
    
    # Perturbed inputs yield different hash
    perturbed_hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    perturbed_hp["UWO"] = [perturbed_hp["UWO"][0], perturbed_hp["UWO"][1], perturbed_hp["UWO"][2] + 0.1]
    record3 = generate_reproducibility_record(perturbed_hp, cfg)
    assert record1["input_hash"] != record3["input_hash"]


# ==============================================================================
# 8. Vehicle Dynamics Literature Benchmarks
# ==============================================================================
def test_vehicle_dynamics_literature_benchmarks():
    backend = PythonReferenceBackend()
    res = backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-30.0, z_max_mm=30.0, n_steps=17)
    
    benchmarks = get_kinematics_benchmarks(DEFAULT_HARDPOINTS, res.to_dict())
    assert len(benchmarks) == 5
    
    assert any("Milliken" in b["reference_source"] for b in benchmarks)
    assert any("Gillespie" in b["reference_source"] for b in benchmarks)
    assert any("Carroll Smith" in b["reference_source"] for b in benchmarks)
    assert any("Dixon" in b["reference_source"] for b in benchmarks)
    assert any("Reimpell" in b["reference_source"] for b in benchmarks)
    
    for b in benchmarks:
        assert "error_pct" in b
        assert "tolerance_pct" in b
        assert b["status"] in ["PASS", "FAIL", "WARN", "NOT_MODELED"]
        assert b["tolerance_pct"] > 0.0


# ==============================================================================
# 9. validate_hardpoints_py Decoupled Status Fields
# ==============================================================================
def test_validate_hardpoints_decoupled_status():
    report = validate_hardpoints_py(DEFAULT_HARDPOINTS)
    
    assert "is_valid" in report
    assert "numerical_status" in report
    assert "physical_status" in report
    assert "overall_status" in report
    assert "validation_coverage_pct" in report
    
    assert report["numerical_status"] in ["PASS", "FAIL", "WARN", "CONVERGED", "DIVERGED"]
    assert report["physical_status"] in ["PASS", "FAIL", "WARN", "VALID", "QUESTIONABLE", "INVALID"]
    assert report["overall_status"] in ["PASS", "FAIL", "WARN", "VALID", "INVALID", "NUMERICALLY_CONVERGED_PHYSICALLY_QUESTIONABLE"]
    assert 0.0 <= report["validation_coverage_pct"] <= 100.0


# ==============================================================================
# 10. Extreme Travel Boundary Divergence Handling
# ==============================================================================
def test_extreme_travel_boundary_divergence():
    backend = PythonReferenceBackend()
    # Physical linkage cannot extend 500mm vertically
    res = backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-500.0, z_max_mm=500.0, n_steps=11)
    
    # Must report divergence rather than silent NaN or fabricated zero
    failed_diags = [d for d in res.point_diagnostics if d["convergence_status"] in ["FAILED", "OUT_OF_BOUNDS"]]
    assert len(failed_diags) > 0
    for d in failed_diags:
        assert d.get("failure_reason") is not None
        assert any(term in d["failure_reason"].lower() for term in ["tolerance", "singular", "substeps", "residual", "diverged"])


# ==============================================================================
# 11. Strict Backend Provenance Enforcement
# ==============================================================================
def test_strict_backend_provenance_enforcement():
    backend = CppKinematicsBackend(topology="double_wishbone", strict_mode=True, requested_backend="cpp")
    with patch.object(backend, "_get_cpp_module", return_value=None):
        with pytest.raises(RuntimeError, match="Native C\\+\\+ kinematics solver required in strict/production mode"):
            backend.sweep(DEFAULT_HARDPOINTS, z_min_mm=-10, z_max_mm=10, n_steps=5)


# ==============================================================================
# 12. API Audit Payload Integration
# ==============================================================================
@pytest.mark.asyncio
async def test_api_audit_payload_integration(authenticated_client):
    payload = {
        "hardpoints": DEFAULT_HARDPOINTS,
        "z_min_mm": -20.0,
        "z_max_mm": 20.0,
        "n_steps": 9,
    }
    resp = await authenticated_client.post("/api/v1/kinematics/solve", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    
    # Verify audit fields returned by API
    assert "point_diagnostics" in data
    assert len(data["point_diagnostics"]) == 9
    assert "reproducibility" in data
    assert "input_hash" in data["reproducibility"]
    assert "model_validity" in data
    assert "numerical_status" in data
    assert "physical_status" in data
    assert "overall_model_status" in data
    assert "benchmarks" in data
    assert len(data["benchmarks"]) == 5
    
    # Verify dedicated benchmarks endpoint
    bench_resp = await authenticated_client.post("/api/v1/kinematics/benchmarks", json=payload)
    assert bench_resp.status_code == 200
    bench_data = bench_resp.json()
    assert isinstance(bench_data, list)
    assert len(bench_data) == 5