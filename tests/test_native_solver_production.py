"""
tests/test_native_solver_production.py
=======================================
Native Solver Production Certification & Error Injection Test Suite.

Verifies:
1. Native extension build provenance, compiler, Eigen 3.4 version, and ABI contract.
2. Solver result provenance metadata (requested_backend, active_backend, solver_version, build_hash).
3. Numerical parity between native C++ solver and Python reference implementation.
4. Strict mode vs Non-strict mode contract:
   - strict_mode=True: Hard failure (RuntimeError) on missing/broken binary (zero silent fallback).
   - strict_mode=False: Truthful fallback with explicit provenance metadata.
5. Error injection suite:
   - Corrupted native binary injection.
   - Incompatible ABI / missing symbol injection.
   - Missing dependency injection.
   - Runtime native exception injection on degenerate geometry.
"""

import sys
import unittest.mock as mock
import pytest

from suspensionlab.physics.kinematics_facade import (
    CppKinematicsBackend,
    PythonReferenceBackend,
    KinematicPoint,
    KinematicsResult,
)


@pytest.fixture
def baseline_hardpoints():
    return {
        "chassis_upper_front": [100.0, 400.0, 400.0],
        "chassis_upper_rear": [-100.0, 400.0, 400.0],
        "upright_upper": [0.0, 600.0, 450.0],
        "chassis_lower_front": [100.0, 300.0, 200.0],
        "chassis_lower_rear": [-100.0, 300.0, 200.0],
        "upright_lower": [0.0, 600.0, 200.0],
        "chassis_tie_rod": [100.0, 300.0, 300.0],
        "upright_tie_rod": [100.0, 600.0, 300.0],
        "wheel_center": [0.0, 650.0, 330.0],
    }


def test_native_solver_provenance_and_metadata(baseline_hardpoints):
    """Verify C++ native solver executes and reports authoritative build metadata."""
    backend = CppKinematicsBackend(strict_mode=True)
    pt = backend.solve_single(baseline_hardpoints, dz_mm=10.0)

    assert pt.active_backend == "cpp"
    assert pt.requested_backend == "cpp"
    assert "eigen-3.4" in pt.build_identifier.lower()
    assert "kinematics-core" in pt.solver_version.lower()
    assert pt.metadata.get("status") == "CONVERGED"
    assert pt.converged is True
    assert "runtime_proof" in pt.metadata
    assert "residual_norm" in pt.metadata["runtime_proof"]
    assert pt.metadata["runtime_proof"]["residual_norm"] < 1e-6


def test_native_vs_python_numerical_parity(baseline_hardpoints):
    """Verify numerical parity between C++ native solver and Python reference solver."""
    cpp_backend = CppKinematicsBackend(strict_mode=True)
    py_backend = PythonReferenceBackend()

    pt_cpp = cpp_backend.solve_single(baseline_hardpoints, dz_mm=15.0)
    pt_py = py_backend.solve_single(baseline_hardpoints, dz_mm=15.0)

    # Parity within kinematic manufacturing tolerances (< 0.05 deg camber/toe, < 0.1 mm track change)
    assert abs(pt_cpp.camber_deg - pt_py.camber_deg) < 0.05
    assert abs(pt_cpp.toe_deg - pt_py.toe_deg) < 0.05
    assert abs(pt_cpp.track_change_mm - pt_py.track_change_mm) < 0.1
    assert abs(pt_cpp.motion_ratio - pt_py.motion_ratio) < 0.05


def test_strict_mode_hard_failure_on_missing_module(baseline_hardpoints):
    """
    STRICT MODE CONTRACT:
    When strict_mode=True and the native C++ module is unavailable,
    system MUST raise RuntimeError (silent fallback strictly forbidden).
    """
    backend = CppKinematicsBackend(strict_mode=True)
    # Simulate missing C++ extension module
    with mock.patch.object(backend, "_get_cpp_module", return_value=None):
        with pytest.raises(RuntimeError) as exc_info:
            backend.solve_single(baseline_hardpoints, dz_mm=10.0)
        assert "fallback disabled" in str(exc_info.value).lower() or "strict" in str(exc_info.value).lower()

        # Also sweep method must fail hard
        with pytest.raises(RuntimeError) as exc_info_sw:
            backend.sweep(baseline_hardpoints, z_min_mm=-10.0, z_max_mm=10.0, n_steps=3)
        assert "fallback disabled" in str(exc_info_sw.value).lower() or "strict" in str(exc_info_sw.value).lower()


def test_non_strict_mode_truthful_fallback(baseline_hardpoints):
    """
    NON-STRICT MODE CONTRACT:
    When strict_mode=False and native C++ is unavailable,
    system falls back to PythonReferenceBackend with EXPLICIT metadata recording the reason.
    """
    backend = CppKinematicsBackend(strict_mode=False)
    with mock.patch.object(backend, "_get_cpp_module", return_value=None):
        pt = backend.solve_single(baseline_hardpoints, dz_mm=10.0)

        # Must truthfully declare active_backend is python_reference, not cpp!
        assert pt.active_backend == "python_reference"
        assert pt.requested_backend == "cpp"
        assert pt.fallback_reason == "cpp_extension_not_loaded"
        assert pt.metadata.get("available_backend") is False


def test_error_injection_corrupted_native_binary(baseline_hardpoints):
    """
    ERROR INJECTION 1: Corrupted Native Binary
    Simulate a broken extension object where required methods raise or are missing.
    Strict mode must raise RuntimeError without crashing the interpreter.
    """
    corrupt_mock = mock.MagicMock()
    corrupt_mock.solve_single_corner.side_effect = Exception("FATAL: Memory corruption / missing symbol in .so/.pyd")

    backend = CppKinematicsBackend(strict_mode=True)
    with mock.patch.object(backend, "_get_cpp_module", return_value=corrupt_mock):
        with pytest.raises(RuntimeError) as exc_info:
            backend.solve_single(baseline_hardpoints, dz_mm=5.0)
        assert "execution failed in strict mode" in str(exc_info.value).lower()


def test_error_injection_incompatible_abi(baseline_hardpoints):
    """
    ERROR INJECTION 2: Incompatible ABI Signature
    Simulate pybind11 ABI mismatch (missing required method or mismatched arguments).
    """
    class IncompatibleABIModule:
        version = "v1.0-incompatible"
        # solve_single_corner method missing!

    backend = CppKinematicsBackend(strict_mode=True)
    with mock.patch.object(backend, "_get_cpp_module", return_value=IncompatibleABIModule()):
        with pytest.raises(RuntimeError) as exc_info:
            backend.solve_single(baseline_hardpoints, dz_mm=5.0)
        assert "fallback disabled" in str(exc_info.value).lower() or "unavailable" in str(exc_info.value).lower()


def test_error_injection_missing_dependency(baseline_hardpoints):
    """
    ERROR INJECTION 3: Missing Shared Library Dependency (ldd / DLL failure)
    Simulate import-time failure due to missing libwinpthread / libstdc++.
    """
    def mock_broken_import():
        raise ImportError("DLL load failed: The specified module could not be found.")

    backend = CppKinematicsBackend(strict_mode=True)
    with mock.patch.object(backend, "_get_cpp_module", side_effect=mock_broken_import):
        with pytest.raises((RuntimeError, ImportError)):
            backend.solve_single(baseline_hardpoints, dz_mm=5.0)


def test_error_injection_singular_geometry_native_exception():
    """
    ERROR INJECTION 4: Degenerate Hardpoint Geometry
    Feeding singular geometry (coincident points) causes native Newton-Raphson
    Jacobian to be singular. In strict mode, C++ must cleanly return or raise
    without core-dumping.
    """
    singular_hp = {
        "chassis_upper_front": [0.0, 0.0, 0.0],
        "chassis_upper_rear": [0.0, 0.0, 0.0],  # Coincident axis
        "upright_upper": [0.0, 0.0, 0.0],        # All points coincident
        "chassis_lower_front": [0.0, 0.0, 0.0],
        "chassis_lower_rear": [0.0, 0.0, 0.0],
        "upright_lower": [0.0, 0.0, 0.0],
        "chassis_tie_rod": [0.0, 0.0, 0.0],
        "upright_tie_rod": [0.0, 0.0, 0.0],
        "wheel_center": [0.0, 0.0, 0.0],
    }

    backend = CppKinematicsBackend(strict_mode=True)
    # Backend should either return converged=False or raise RuntimeError
    try:
        pt = backend.solve_single(singular_hp, dz_mm=10.0)
        assert pt.converged is False or pt.metadata.get("status") in ("FAILED", "SINGULAR", "DIVERGED")
    except RuntimeError as exc:
        assert "failed" in str(exc).lower() or "singular" in str(exc).lower()
