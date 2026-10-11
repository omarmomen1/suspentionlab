"""
tests/test_kinematics_backend_protocol.py
=========================================
Comprehensive tests for KinematicsBackend protocol, C++ production engine,
Python reference fallback, hardpoint validation, elastokinematic compliance,
and rigorous C++/Python numerical parity within engineering tolerances.
"""

import os
import pytest
import numpy as np

from suspensionlab.physics.kinematics import DEFAULT_HARDPOINTS
from suspensionlab.physics.kinematics_facade import (
    KinematicsBackendFactory,
    PythonReferenceBackend,
    CppKinematicsBackend,
    solve_kinematics,
    KinematicsResult,
    KinematicPoint,
)

# Canonical API hardpoints format
DEFAULT_API_HARDPOINTS = {
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

DEFAULT_MACPHERSON_HARDPOINTS = {
    "chassis_lower_front": [-80.0,  80.0, 155.0],
    "chassis_lower_rear":  [ 80.0,  80.0, 155.0],
    "chassis_strut_top":   [  0.0, 550.0, 650.0],
    "upright_lower":       [  0.0, 720.0, 145.0],
    "upright_strut_mount": [  0.0, 620.0, 350.0],
    "chassis_tie_rod":     [  0.0, 150.0, 220.0],
    "upright_tie_rod":     [-15.0, 710.0, 205.0],
    "wheel_center":        [  0.0, 760.0, 220.0],
}


def test_factory_creates_backends():
    py_backend = KinematicsBackendFactory.create(mode="python")
    assert isinstance(py_backend, PythonReferenceBackend)

    cpp_backend = KinematicsBackendFactory.create(mode="cpp")
    assert isinstance(cpp_backend, CppKinematicsBackend)

    auto_backend = KinematicsBackendFactory.create(mode="auto")
    assert hasattr(auto_backend, "sweep")
    assert hasattr(auto_backend, "solve_single")
    assert hasattr(auto_backend, "validate_hardpoints")


def test_cpp_backend_single_point_execution():
    backend = CppKinematicsBackend(topology="double_wishbone")
    pt = backend.solve_single(DEFAULT_API_HARDPOINTS, dz_mm=0.0)
    
    assert isinstance(pt, KinematicPoint)
    assert pt.converged is True
    assert abs(pt.camber_deg) < 1.0
    assert abs(pt.toe_deg) < 1.0
    assert pt.motion_ratio > 0.2
    assert pt.metadata["active_backend"] in ("cpp", "python_reference")
    if pt.metadata["active_backend"] == "python_reference":
        assert pt.metadata["fallback_reason"] is not None
    else:
        assert pt.metadata["solver_version"] == "kinematics-core-v3.0-authoritative-cpp20"
        assert pt.metadata["build_hash"] == "eigen-3.4.0-simd-x86_64"


def test_sweep_metadata_transparency():
    res = solve_kinematics(
        topology="double_wishbone",
        hardpoints=DEFAULT_HARDPOINTS,
        z_min_mm=-40.0,
        z_max_mm=40.0,
        n_steps=17,
        mode="cpp",
    )
    assert isinstance(res, KinematicsResult)
    assert len(res.wheel_travel_mm) == 17
    assert len(res.camber_deg) == 17
    assert len(res.motion_ratio) == 17
    assert all(res.converged)

    # Verify provenance metadata
    assert res.metadata["requested_backend"] == "cpp"
    assert res.metadata["active_backend"] in ("cpp", "python_reference")
    if res.metadata["active_backend"] == "python_reference":
        assert res.metadata["fallback_reason"] is not None
    assert "execution_time_ms" in res.metadata
    assert res.metadata["execution_time_ms"] >= 0.0


def test_numerical_parity_python_vs_cpp():
    """Verify tight numerical parity between C++ production engine and Python reference."""
    py_backend  = PythonReferenceBackend(topology="double_wishbone")
    cpp_backend = CppKinematicsBackend(topology="double_wishbone")

    z_sweep = [-40.0, -20.0, -10.0, 0.0, 10.0, 20.0, 40.0]
    for z in z_sweep:
        pt_py  = py_backend.solve_single(DEFAULT_API_HARDPOINTS, dz_mm=z)
        pt_cpp = cpp_backend.solve_single(DEFAULT_API_HARDPOINTS, dz_mm=z)

        assert pt_py.converged is True
        assert pt_cpp.converged is True

        # Camber within 0.05 degrees
        assert abs(pt_py.camber_deg - pt_cpp.camber_deg) < 0.05, f"Camber mismatch at z={z}"
        # Toe within 0.05 degrees
        assert abs(pt_py.toe_deg - pt_cpp.toe_deg) < 0.05, f"Toe mismatch at z={z}"
        # Roll center height within 2.0 mm
        assert abs(pt_py.roll_center_height_mm - pt_cpp.roll_center_height_mm) < 2.0, f"RC mismatch at z={z}"
        # Motion ratio within 0.02
        assert abs(pt_py.motion_ratio - pt_cpp.motion_ratio) < 0.02, f"MR mismatch at z={z}"


def test_motion_ratio_step_size_convergence():
    """Verify finite difference motion ratio MR = ds/dz converges as step size dz -> 0 (Step 7)."""
    backend = CppKinematicsBackend(topology="double_wishbone")
    
    pt_base = backend.solve_single(DEFAULT_API_HARDPOINTS, dz_mm=0.0)
    pt_050  = backend.solve_single(DEFAULT_API_HARDPOINTS, dz_mm=0.5)
    pt_010  = backend.solve_single(DEFAULT_API_HARDPOINTS, dz_mm=0.1)
    pt_002  = backend.solve_single(DEFAULT_API_HARDPOINTS, dz_mm=0.02)
    
    # Motion ratios should vary smoothly and converge tightly
    assert abs(pt_010.motion_ratio - pt_002.motion_ratio) < 0.02
    assert abs(pt_050.motion_ratio - pt_010.motion_ratio) < 0.05


def test_macpherson_topology_solving():
    """Verify MacPherson strut topology solves cleanly in C++ backend."""
    backend = CppKinematicsBackend(topology="macpherson")
    val = backend.validate_hardpoints(DEFAULT_MACPHERSON_HARDPOINTS, tire_radius_m=0.33)
    assert val["is_valid"] is True

    pt = backend.solve_single(DEFAULT_MACPHERSON_HARDPOINTS, dz_mm=0.0)
    assert pt.converged is True
    assert abs(pt.camber_deg) < 3.0
    assert abs(pt.toe_deg) < 3.0
    assert pt.motion_ratio > 0.5


def test_bushing_compliance_mode():
    """Verify coupled elastokinematic compliance introduces load-dependent deflections (Step 9)."""
    backend = CppKinematicsBackend(topology="double_wishbone")
    
    # Rigid mode (zero loads or compliance disabled)
    pt_rigid = backend.solve_single(
        DEFAULT_API_HARDPOINTS, dz_mm=0.0, compliance_mode=False
    )

    # Compliant mode under 4 kN lateral cornering load
    corner_loads = {"Fy_N": 4000.0, "Fx_N": -2000.0, "Mz_Nm": 60.0}
    pt_compliant = backend.solve_single(
        DEFAULT_API_HARDPOINTS, dz_mm=0.0, compliance_mode=True, forces=corner_loads
    )

    assert pt_compliant.converged is True
    # Under lateral load, camber and toe must deflect relative to rigid
    assert abs(pt_compliant.camber_deg - pt_rigid.camber_deg) > 0.1
    assert abs(pt_compliant.toe_deg - pt_rigid.toe_deg) > 0.05


def test_hardpoint_validation_catches_degenerate_geometry():
    """Verify hardpoint validator rejects degenerate geometry before solving (Step 4)."""
    backend = CppKinematicsBackend(topology="double_wishbone")
    
    bad_hp = dict(DEFAULT_API_HARDPOINTS)
    # Collinear/overlapping inboard wishbone pivots
    bad_hp["chassis_upper_rear"] = bad_hp["chassis_upper_front"]
    
    val = backend.validate_hardpoints(bad_hp, tire_radius_m=0.33)
    assert val["is_valid"] is False
    assert len(val["errors"]) > 0


def test_strict_production_mode_guards():
    """Verify strict production mode forbids defaulting hardpoints and enforces valid geometry."""
    with pytest.raises(ValueError, match="Missing required suspension hardpoints"):
        solve_kinematics(
            topology="double_wishbone",
            hardpoints=None,
            strict_mode=True,
        )

    bad_hp = dict(DEFAULT_API_HARDPOINTS)
    bad_hp["chassis_upper_rear"] = bad_hp["chassis_upper_front"]
    with pytest.raises(ValueError, match="Hardpoint validation failed"):
        solve_kinematics(
            topology="double_wishbone",
            hardpoints=bad_hp,
            strict_mode=True,
        )
