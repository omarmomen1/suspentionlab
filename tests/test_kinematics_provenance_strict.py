"""
tests/test_kinematics_provenance_strict.py
===========================================
Hostile enterprise audit tests verifying truthful kinematics provenance:
1. Distinguishes requested, available, selected, active backends.
2. Truthful active_backend when fallback occurs (never claims "cpp" when Python ran).
3. Strict mode hard failure when C++ is unavailable (no silent fallback).
4. Strict mode hard failure when C++ solver throws runtime error.
5. Non-strict mode captures fallback reason honestly.
6. Runtime proof originates from solver execution.
"""

import pytest
from unittest.mock import patch, MagicMock

from suspensionlab.physics.kinematics import DEFAULT_HARDPOINTS
from suspensionlab.physics.kinematics_facade import (
    solve_kinematics,
    CppKinematicsBackend,
    PythonReferenceBackend,
    KinematicsBackendFactory,
)

DEFAULT_API_HPS = {
    "chassis_upper_front": DEFAULT_HARDPOINTS["UWI_fwd"],
    "chassis_upper_rear":  DEFAULT_HARDPOINTS["UWI_aft"],
    "upright_upper":       DEFAULT_HARDPOINTS["UWO"],
    "chassis_lower_front": DEFAULT_HARDPOINTS["LWI_fwd"],
    "chassis_lower_rear":  DEFAULT_HARDPOINTS["LWI_aft"],
    "upright_lower":       DEFAULT_HARDPOINTS["LWO"],
    "chassis_tie_rod":     DEFAULT_HARDPOINTS["TRI"],
    "upright_tie_rod":     DEFAULT_HARDPOINTS["TRO"],
    "wheel_center":        DEFAULT_HARDPOINTS["WC"],
    "pushrod_chassis":     DEFAULT_HARDPOINTS["PRI"],
    "pushrod_upright":     DEFAULT_HARDPOINTS["PRO"],
}


def test_provenance_fields_present_and_distinguished():
    res = solve_kinematics(hardpoints=DEFAULT_API_HPS, mode="python", z_min_mm=-10, z_max_mm=10, n_steps=5)
    meta = res.metadata
    required_keys = [
        "requested_backend", "available_backend", "selected_backend", "active_backend",
        "fallback_reason", "solver_version", "native_library_version", "build_identifier", "runtime_proof"
    ]
    for k in required_keys:
        assert k in meta, f"Missing provenance key: {k}"

    assert res.requested_backend == "python"
    assert res.active_backend == "python_reference"
    assert res.solver_version == "python-reference-v3.0"
    assert res.build_identifier == "cpython-pure-math"
    assert res.fallback_reason is None


def test_truthful_active_backend_when_cpp_available():
    from suspensionlab.physics import kinematics as py_kin
    if not py_kin._HAVE_CPP:
        pytest.skip("Native C++ extension not present in this test environment.")

    res = solve_kinematics(hardpoints=DEFAULT_API_HPS, mode="cpp", z_min_mm=-10, z_max_mm=10, n_steps=5)
    assert res.requested_backend == "cpp"
    assert res.available_backend is True
    assert res.selected_backend == "cpp"
    assert res.active_backend == "cpp"
    assert res.fallback_reason is None
    assert res.solver_version == "kinematics-core-v3.0-authoritative-cpp20"
    assert res.native_library_version == "kinematics-core-v3.0-authoritative-cpp20"
    assert res.build_identifier == "eigen-3.4.0-simd-x86_64"
    assert "status" in res.runtime_proof


def test_truthful_active_backend_when_cpp_unavailable_fallback():
    backend = CppKinematicsBackend(topology="double_wishbone", strict_mode=False, requested_backend="cpp")
    with patch.object(backend, "_get_cpp_module", return_value=None):
        pt = backend.solve_single(DEFAULT_API_HPS, dz_mm=0.0)
        # MUST report python_reference as active_backend, NEVER "cpp"
        assert pt.metadata["requested_backend"] == "cpp"
        assert pt.metadata["available_backend"] is False
        assert pt.metadata["selected_backend"] == "cpp"
        assert pt.metadata["active_backend"] == "python_reference"
        assert pt.metadata["fallback_reason"] == "cpp_extension_not_loaded"
        assert pt.metadata["solver_version"] == "python-reference-v3.0"
        assert pt.metadata["build_identifier"] == "cpython-pure-math"
        assert pt.metadata["native_library_version"] is None


def test_truthful_sweep_when_cpp_unavailable_fallback():
    backend = CppKinematicsBackend(topology="double_wishbone", strict_mode=False, requested_backend="cpp")
    with patch.object(backend, "_get_cpp_module", return_value=None):
        res = backend.sweep(DEFAULT_API_HPS, z_min_mm=-10, z_max_mm=10, n_steps=5)
        assert res.requested_backend == "cpp"
        assert res.available_backend is False
        assert res.selected_backend == "cpp"
        assert res.active_backend == "python_reference"
        assert res.fallback_reason == "cpp_extension_not_loaded"
        assert res.solver_version == "python-reference-v3.0"
        assert res.build_identifier == "cpython-pure-math"


def test_strict_mode_fails_hard_when_cpp_unavailable():
    backend = CppKinematicsBackend(topology="double_wishbone", strict_mode=True, requested_backend="cpp")
    with patch.object(backend, "_get_cpp_module", return_value=None):
        with pytest.raises(RuntimeError, match="Native C\\+\\+ kinematics solver required in strict/production mode"):
            backend.solve_single(DEFAULT_API_HPS, dz_mm=0.0)

        with pytest.raises(RuntimeError, match="Native C\\+\\+ kinematics solver required in strict/production mode"):
            backend.sweep(DEFAULT_API_HPS, z_min_mm=-10, z_max_mm=10, n_steps=5)


def test_strict_mode_fails_hard_when_cpp_solver_throws():
    backend = CppKinematicsBackend(topology="double_wishbone", strict_mode=True, requested_backend="cpp")
    mock_kc = MagicMock()
    mock_kc.solve_single_corner.side_effect = ArithmeticError("Jacobian singular at singularity limit")
    mock_kc.generate_kinematic_lut.side_effect = ArithmeticError("Jacobian singular at singularity limit")

    with patch.object(backend, "_get_cpp_module", return_value=mock_kc):
        with pytest.raises(RuntimeError, match="C\\+\\+ kinematics solver execution failed in strict mode"):
            backend.solve_single(DEFAULT_API_HPS, dz_mm=0.0)

        with pytest.raises(RuntimeError, match="C\\+\\+ kinematics solver sweep failed in strict mode"):
            backend.sweep(DEFAULT_API_HPS, z_min_mm=-10, z_max_mm=10, n_steps=5)


def test_non_strict_reports_solver_error_fallback():
    backend = CppKinematicsBackend(topology="double_wishbone", strict_mode=False, requested_backend="cpp")
    mock_kc = MagicMock()
    mock_kc.solve_single_corner.side_effect = ArithmeticError("Jacobian singular")

    with patch.object(backend, "_get_cpp_module", return_value=mock_kc):
        pt = backend.solve_single(DEFAULT_API_HPS, dz_mm=0.0)
        assert pt.metadata["requested_backend"] == "cpp"
        assert pt.metadata["active_backend"] == "python_reference"
        assert "cpp_solver_error" in pt.metadata["fallback_reason"]
        assert pt.metadata["solver_version"] == "python-reference-v3.0"
