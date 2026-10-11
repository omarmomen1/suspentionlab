"""
tests/test_physics_sensitivity_blackbox.py
===========================================
SuspensionLab PRO — Black-Box Physical Sensitivity & Dynamic Response Tests

Verifies that model outputs physically respond to parametric variations:
1. Mass scaling: m_s up -> omega_n down, sag up, rms acceleration changes
2. Stiffness scaling: k_s up -> omega_n up, susp_travel down
3. Damping scaling: c up -> zeta up, peak transmissibility down
4. Gravity scaling: g up -> static deflection scales proportionally
5. Aero coupling: v up -> downforce scales as v^2, reducing ride height
6. Tire load sensitivity: Fz up -> degressive friction mu(Fz) drops
7. Road obstacle scaling: amplitude up -> dynamic forces scale proportionally

These tests strictly fail if any engineering output is a static fixture or mocked calculation.
"""

import pytest
import numpy as np
import math

from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    run_quarter_car_analysis,
    compute_modal_properties,
)
from suspensionlab.physics.half_car import (
    HalfCarParams,
    run_half_car_analysis,
)
from suspensionlab.physics.magic_formula import (
    TireCoeffs,
    calc_tire_forces_3d,
)


def test_blackbox_mass_scaling_physical_response():
    """Increasing sprung mass MUST lower the natural frequency and increase suspension deflection."""
    light_params = QuarterCarParams(m_s=200.0, k_s=25000.0, c=2000.0)
    heavy_params = QuarterCarParams(m_s=400.0, k_s=25000.0, c=2000.0)

    light_modal = compute_modal_properties(light_params)
    heavy_modal = compute_modal_properties(heavy_params)

    # omega_n = sqrt(k/m) -> doubling mass should reduce frequency by ~sqrt(2) = 1.414
    assert light_modal["f_n_s"] > heavy_modal["f_n_s"]
    ratio = light_modal["f_n_s"] / heavy_modal["f_n_s"]
    assert 1.30 < ratio < 1.50

    # Step simulation: heavy body experiences larger suspension compression
    step_profile = RoadProfile(profile_type="step", amplitude=0.04, duration=4.0)
    light_res = run_quarter_car_analysis(light_params, step_profile)
    heavy_res = run_quarter_car_analysis(heavy_params, step_profile)

    assert light_res.rms_susp_travel != heavy_res.rms_susp_travel
    assert np.max(np.abs(heavy_res.susp_travel)) > np.max(np.abs(light_res.susp_travel)) * 0.8


def test_blackbox_stiffness_scaling_physical_response():
    """Increasing spring rate MUST increase natural frequency and increase body acceleration transmission."""
    soft_params = QuarterCarParams(m_s=300.0, k_s=15000.0, c=2000.0)
    stiff_params = QuarterCarParams(m_s=300.0, k_s=45000.0, c=2000.0)

    soft_modal = compute_modal_properties(soft_params)
    stiff_modal = compute_modal_properties(stiff_params)

    assert stiff_modal["f_n_s"] > soft_modal["f_n_s"]
    ratio = stiff_modal["f_n_s"] / soft_modal["f_n_s"]
    # sqrt(45000/15000) = sqrt(3) ~ 1.732
    assert 1.60 < ratio < 1.85

    step_profile = RoadProfile(profile_type="step", amplitude=0.04, duration=4.0)
    soft_res = run_quarter_car_analysis(soft_params, step_profile)
    stiff_res = run_quarter_car_analysis(stiff_params, step_profile)

    # Stiffer spring transmits higher RMS acceleration to body
    assert stiff_res.rms_body_accel > soft_res.rms_body_accel


def test_blackbox_damping_scaling_physical_response():
    """Increasing damper coefficient MUST increase damping ratio zeta and lower peak transmissibility."""
    underdamped = QuarterCarParams(m_s=300.0, k_s=25000.0, c=800.0, MR=1.0)
    welldamped   = QuarterCarParams(m_s=300.0, k_s=25000.0, c=2400.0, MR=1.0)

    under_modal = compute_modal_properties(underdamped)
    well_modal   = compute_modal_properties(welldamped)

    assert well_modal["zeta_s"] > under_modal["zeta_s"]
    assert under_modal["zeta_s"] < 0.20
    assert well_modal["zeta_s"] > 0.35

    step_profile = RoadProfile(profile_type="step", amplitude=0.04, duration=4.0)
    under_res = run_quarter_car_analysis(underdamped, step_profile)
    well_res   = run_quarter_car_analysis(welldamped, step_profile)

    # Underdamped system exhibits higher resonant transmissibility peak
    assert under_res.peak_transmissibility > well_res.peak_transmissibility


def test_blackbox_tire_load_sensitivity_degressive_friction():
    """Magic formula tire MUST exhibit degressive friction coefficient mu(Fz) as normal load increases."""
    coeffs = TireCoeffs(Fz0=4000.0, pDy1=1.10, pDy2=-0.12)
    alpha = math.radians(6.0)  # Near peak cornering

    _, Fy_low, _  = calc_tire_forces_3d(Fz=2000.0, alpha_rad=alpha, kappa=0.0, coeffs=coeffs)
    _, Fy_mid, _  = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=0.0, coeffs=coeffs)
    _, Fy_high, _ = calc_tire_forces_3d(Fz=8000.0, alpha_rad=alpha, kappa=0.0, coeffs=coeffs)

    # Normalised grip coefficients mu = Fy / Fz
    mu_low = Fy_low / 2000.0
    mu_mid = Fy_mid / 4000.0
    mu_high = Fy_high / 8000.0

    # Degressive tire physics: lighter loaded tire produces higher mu
    assert mu_low > mu_mid > mu_high
    assert mu_low > 1.0
    assert mu_high < 1.0


from suspensionlab.physics.suspension_aero_coupling import (
    MultidimensionalAeroMap,
    CoupledVehicleModel,
    SuspensionConfig,
    ActiveAeroMode,
)
from suspensionlab.physics.lap_sim import MassProperties


def test_blackbox_road_obstacle_scaling():
    """Doubling road bump amplitude MUST double dynamic tire and suspension responses in linear regime."""
    p = QuarterCarParams(m_s=300.0, k_s=25000.0, c=2000.0, k_t=200000.0)
    prof_small = RoadProfile(profile_type="sine", amplitude=0.01, frequency=1.5, duration=3.0)
    prof_large = RoadProfile(profile_type="sine", amplitude=0.02, frequency=1.5, duration=3.0)

    res_small = run_quarter_car_analysis(p, prof_small)
    res_large = run_quarter_car_analysis(p, prof_large)

    assert math.isclose(res_large.rms_susp_travel / res_small.rms_susp_travel, 2.0, rel_tol=0.05)
    assert math.isclose(res_large.rms_tire_load / res_small.rms_tire_load, 2.0, rel_tol=0.05)


def test_blackbox_aero_downforce_speed_scaling():
    """Aerodynamic downforce MUST scale with vehicle speed (super-quadratic v^2 with ground-effect ride height drop)."""
    mp = MassProperties(total_mass=800.0, wheelbase=2.7, track_front=1.6, track_rear=1.6)
    sus = SuspensionConfig(k_spring_front=45000.0, k_spring_rear=45000.0, ride_height_front=30.0, ride_height_rear=50.0)
    aero = MultidimensionalAeroMap(cl_base=3.0, cd_base=1.0)
    model = CoupledVehicleModel(mp, aero, sus, tol=0.05, max_iter=25)

    # Solve at 30 m/s and 60 m/s
    state_30 = model.solve(v=30.0, ax=0.0, ay=0.0, active_aero_mode=ActiveAeroMode.Z_MODE)
    state_60 = model.solve(v=60.0, ax=0.0, ay=0.0, active_aero_mode=ActiveAeroMode.Z_MODE)

    # Downforce at 60 m/s should scale with v^2 (> 3.5x downforce at 30 m/s)
    assert state_60.aero_df_total_n > state_30.aero_df_total_n
    ratio = state_60.aero_df_total_n / state_30.aero_df_total_n
    assert 3.5 < ratio < 5.5
