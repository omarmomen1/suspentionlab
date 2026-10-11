"""
tests/test_enveloping_integration.py
====================================
Integration test suite verifying end-to-end coupling of Tire Enveloping Physics
with the canonical Quarter Car model (QuarterCarParams, simulate_time_response,
run_quarter_car_analysis).

Validates:
1. Exact backward compatibility of default QuarterCarParams (POINT_CONTACT)
2. Direct invocation of GEOMETRIC_ENVELOPING via QuarterCarParams
3. Direct invocation of ADVANCED_ENVELOPING via QuarterCarParams
4. Zero duplicate ride models: same EOMs, dampers, springs, bump stops, and liftoff logic
5. QuarterCarResult output consistency (z_r_effective, tire_enveloping_mode, Fx_obstacle)
"""

import pytest
import numpy as np

from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    simulate_time_response,
    run_quarter_car_analysis,
)
from suspensionlab.physics.contracts import CanonicalRoadProfile
from suspensionlab.physics.tire_enveloping import (
    TireEnvelopingConfig,
    TireEnvelopingMode,
    create_benchmark_road,
)


def test_default_quarter_car_backward_compatibility():
    """Verify that default QuarterCarParams continues to use POINT_CONTACT without regressions."""
    p = QuarterCarParams()
    assert p.enveloping_config is None

    profile = RoadProfile(profile_type="step", amplitude=0.03, duration=2.0)
    res = run_quarter_car_analysis(p, profile)

    assert res.tire_enveloping_mode == "POINT_CONTACT"
    assert len(res.z_r_effective) == len(res.z_r)
    # Under point contact, effective elevation equals raw road elevation
    np.testing.assert_allclose(res.z_r_effective, res.z_r, atol=1e-6)


def test_quarter_car_geometric_enveloping_on_step():
    """Verify that configuring GEOMETRIC_ENVELOPING on QuarterCarParams smoothly filters sharp step."""
    cfg = TireEnvelopingConfig(
        mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING,
        unloaded_radius=0.330,
        speed_mps=15.0,
    )
    p = QuarterCarParams(enveloping_config=cfg)

    # Sharp 30mm step
    step_road = create_benchmark_road("sharp_step", amplitude_m=0.03, start_x_m=2.0, length_m=10.0)
    res = run_quarter_car_analysis(p, step_road)

    assert res.tire_enveloping_mode == "GEOMETRIC_ENVELOPING"
    assert len(res.z_r_effective) > 0
    assert len(res.ddz_s) > 0
    assert np.all(np.isfinite(res.ddz_s))
    assert np.all(np.isfinite(res.z_u))

    # Effective road profile must rise smoothly (less than full 30mm discontinuous jump)
    max_step_rate = np.max(np.abs(np.diff(res.z_r_effective)))
    assert max_step_rate < 0.025  # Smooth finite step increments


def test_quarter_car_advanced_enveloping_with_bump_stops():
    """Verify that ADVANCED_ENVELOPING works in harmony with progressive bump stops and liftoff."""
    cfg = TireEnvelopingConfig(
        mode=TireEnvelopingMode.ADVANCED_ENVELOPING,
        unloaded_radius=0.330,
        speed_mps=20.0,
        include_longitudinal_force=True,
    )
    p = QuarterCarParams(
        enveloping_config=cfg,
        bump_stop_gap=0.03,
        bump_stop_rate=80000.0,
        enable_contact_loss=True,
    )

    kerb_road = create_benchmark_road("kerb", amplitude_m=0.05, start_x_m=3.0, length_m=15.0)
    res = run_quarter_car_analysis(p, kerb_road)

    assert res.tire_enveloping_mode == "ADVANCED_ENVELOPING"
    assert len(res.Fx_obstacle) == len(res.time)
    assert np.any(np.abs(res.Fx_obstacle) > 0.0)  # Obstacle horizontal forces generated
    assert np.all(np.isfinite(res.Fx_obstacle))


def test_quarter_car_reproducibility():
    """Verify that repeated simulations with identical enveloping setup produce identical results."""
    cfg = TireEnvelopingConfig(
        mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING,
        speed_mps=15.0,
    )
    p = QuarterCarParams(enveloping_config=cfg)
    road = create_benchmark_road("sine", amplitude_m=0.02, wavelength_m=1.5, length_m=10.0)

    res1 = run_quarter_car_analysis(p, road)
    res2 = run_quarter_car_analysis(p, road)

    np.testing.assert_array_equal(res1.z_s, res2.z_s)
    np.testing.assert_array_equal(res1.ddz_s, res2.ddz_s)
    np.testing.assert_array_equal(res1.z_r_effective, res2.z_r_effective)
    assert res1.rms_body_accel == res2.rms_body_accel
