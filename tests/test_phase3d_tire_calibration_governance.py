"""
tests/test_phase3d_tire_calibration_governance.py
=================================================
Verification tests for Phase 3D Change #5: Tire Calibration Architecture & Governance.
Ensures:
1. Default solver instantiation preserves uncalibrated nominal Pacejka tire parameters (s_tire = 1.0).
2. Setup-level calibration attaches full provenance, timestamp, version, dataset, and cryptographic hash.
3. s_tire = 1.3161 is strictly prevented from becoming a hardcoded global physics constant.
4. Core solver executes independently with or without calibrated setup profiles.
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
    TireCalibrationRecord,
)


def test_default_nominal_tire_parameters_preserved():
    """Verify default DynamicVehicleParams has uncalibrated nominal tire parameters (s_tire=1.0)."""
    p = DynamicVehicleParams()
    assert hasattr(p, "tire_calibration")
    assert p.tire_calibration.s_tire == 1.0
    assert p.tire_calibration.is_calibrated is False
    assert "nominal" in p.tire_calibration.calibration_version.lower()
    # Nominal Pacejka cornering stiffness pKy1 = 15.0
    assert math.isclose(p.tire_coeffs.pKy1, 15.0, abs_tol=1e-5)


def test_setup_level_tire_calibration_with_provenance_and_hash():
    """Verify applying a calibrated tire setup updates pKy1 and records immutable provenance and hash."""
    p = DynamicVehicleParams()

    # Apply Turn 4 Sweeper calibration (optimal s_tire = 1.16)
    p.apply_tire_calibration(
        s_tire=1.16,
        version="golf_gti_turn4_v1",
        dataset="stanford_vw_golf_thunderhill_2023_11",
        provenance="Empirically fitted on Turn 4 High-Speed Sweeper (Phase 3C.2 fine sweep)"
    )

    assert p.tire_calibration.is_calibrated is True
    assert p.tire_calibration.s_tire == 1.16
    assert p.tire_calibration.calibration_version == "golf_gti_turn4_v1"
    assert p.tire_calibration.dataset_association == "stanford_vw_golf_thunderhill_2023_11"
    assert len(p.tire_calibration.parameter_hash) == 64
    assert len(p.tire_calibration.timestamp_iso) > 10
    # pKy1 scaled to 15.0 * 1.16 = 17.4
    assert math.isclose(p.tire_coeffs.pKy1, 17.4, abs_tol=1e-5)


def test_core_solver_usable_with_nominal_or_calibrated_tires():
    """Verify core simulation engine steps cleanly with both nominal and calibrated tires."""
    p_nom = DynamicVehicleParams() # s_tire = 1.0
    p_cal = DynamicVehicleParams()
    p_cal.apply_tire_calibration(s_tire=1.16, version="test_v1")

    sim_nom = DynamicLapSimulator(params=p_nom, dt_fixed_s=0.001)
    sim_cal = DynamicLapSimulator(params=p_cal, dt_fixed_s=0.001)

    st = DynamicVehicleState(u_mps=25.0)
    ctrl = DriverControls(steering_deg=20.0, throttle=0.2)

    st_nom = sim_nom.step(st, ctrl)
    st_cal = sim_cal.step(st, ctrl)

    assert not math.isnan(st_nom.yaw_rate_rads)
    assert not math.isnan(st_cal.yaw_rate_rads)
    # Higher tire cornering stiffness produces slightly faster yaw response
    assert st_cal.yaw_rate_rads > st_nom.yaw_rate_rads


def test_invalid_s_tire_rejected():
    """Verify non-physical tire stiffness scaling is rejected with ValueError."""
    p = DynamicVehicleParams()
    with pytest.raises(ValueError, match="out of physical range"):
        p.apply_tire_calibration(s_tire=-0.5)
    with pytest.raises(ValueError, match="out of physical range"):
        p.apply_tire_calibration(s_tire=15.0)
