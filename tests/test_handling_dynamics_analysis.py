"""
tests/test_handling_dynamics_analysis.py
========================================
Rigorous verification & validation tests for the Handling & Understeer module:

1. Zero lateral acceleration & zero steer verification
2. Left/right lateral symmetry test (+steer vs -steer)
3. Steady-state linear bicycle model analytical verification:
   K_us = (W_f / C_alpha_f) - (W_r / C_alpha_r)
4. Total axle vertical load transfer conservation:
   sum(Fz_i) == m*g + F_aero_z
5. Lateral load transfer decomposition verification:
   Total = Geometric + Elastic + Unsprung
6. Roll stiffness distribution sensitivity test:
   Stiffening front ARB shifts load transfer forward and increases Kus
7. Pacejka MF 5.2 combined-slip & saturation limits:
   Simultaneous braking reduces available lateral grip
8. Invalid vehicle & tire parameter guardrails
9. Exact numerical reproducibility across repeated runs
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.handling_model import (
    HandlingParams,
    simulate_maneuver,
)
from suspensionlab.physics.handling_analysis import (
    compute_handling_diagram,
    simulate_yaw_response_scenario,
    compare_handling_setups,
    assess_handling_validity,
)
from suspensionlab.physics.magic_formula import TireCoeffs, calc_tire_forces


# ─────────────────────────────────────────────────────────────────────────────
# 1. Zero Steer & Zero Lateral Acceleration Equilibrium
# ─────────────────────────────────────────────────────────────────────────────

def test_zero_steer_straight_line_equilibrium():
    """Verify vehicle traveling in a straight line produces zero lateral force, yaw, or roll."""
    p = HandlingParams()
    res = simulate_maneuver(
        p=p,
        v_x_init=30.0,
        steering_func=lambda t: 0.0,
        throttle_func=lambda t: 0.05,
        brake_func=lambda t: 0.0,
        duration=2.0,
        dt=0.01,
    )

    # Lateral acceleration and yaw rate must be zero within numerical tolerance
    np.testing.assert_allclose(res["a_y"], 0.0, atol=1e-3)
    np.testing.assert_allclose(res["yaw_rate"], 0.0, atol=1e-4)
    np.testing.assert_allclose(res["slip_angle"], 0.0, atol=1e-4)

    # Left and right wheel loads must be symmetric
    np.testing.assert_allclose(res["Fz_fl"], res["Fz_fr"], rtol=1e-4)
    np.testing.assert_allclose(res["Fz_rl"], res["Fz_rr"], rtol=1e-4)

    # Lateral load transfer must be zero
    np.testing.assert_allclose(res["delta_Fz_lat_f"], 0.0, atol=1e-3)
    np.testing.assert_allclose(res["delta_Fz_lat_r"], 0.0, atol=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Left / Right Symmetry
# ─────────────────────────────────────────────────────────────────────────────

def test_left_right_cornering_symmetry():
    """Verify that turning left (+steer) vs right (-steer) produces exact mirrored responses."""
    p = HandlingParams()
    steer_mag = 0.04  # ~2.3 deg

    res_left = simulate_maneuver(
        p=p,
        v_x_init=25.0,
        steering_func=lambda t: steer_mag if t > 0.5 else 0.0,
        throttle_func=lambda t: 0.0,
        brake_func=lambda t: 0.0,
        duration=3.0,
        dt=0.01,
    )

    res_right = simulate_maneuver(
        p=p,
        v_x_init=25.0,
        steering_func=lambda t: -steer_mag if t > 0.5 else 0.0,
        throttle_func=lambda t: 0.0,
        brake_func=lambda t: 0.0,
        duration=3.0,
        dt=0.01,
    )

    # Ay, yaw rate, and sideslip must be anti-symmetric
    np.testing.assert_allclose(res_left["a_y"], -res_right["a_y"], rtol=1e-3, atol=1e-3)
    np.testing.assert_allclose(res_left["yaw_rate"], -res_right["yaw_rate"], rtol=1e-3, atol=1e-3)

    # Normal loads must be mirrored across vehicle centerline:
    # Outer tire in left turn is FR -> matches outer tire in right turn which is FL
    np.testing.assert_allclose(res_left["Fz_fr"], res_right["Fz_fl"], rtol=1e-3, atol=1.0)
    np.testing.assert_allclose(res_left["Fz_fl"], res_right["Fz_fr"], rtol=1e-3, atol=1.0)
    np.testing.assert_allclose(res_left["Fz_rr"], res_right["Fz_rl"], rtol=1e-3, atol=1.0)
    np.testing.assert_allclose(res_left["Fz_rl"], res_right["Fz_rr"], rtol=1e-3, atol=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Analytical Linear Bicycle Model Comparison
# ─────────────────────────────────────────────────────────────────────────────

def test_steady_state_bicycle_model_analytical_reference():
    """
    Verify steady-state understeer gradient matches analytical bicycle model in the linear regime:
    K_us = (W_f / C_alpha_f) - (W_r / C_alpha_r)
    """
    p = HandlingParams()
    L = p.a + p.b
    W_f = (p.m_s * 9.81 * p.b / L) + (p.m_uf * 9.81)
    W_r = (p.m_s * 9.81 * p.a / L) + (p.m_ur * 9.81)

    # Calculate analytical linear cornering stiffness per axle from tire coefficients
    _, fy_front_small = calc_tire_forces(W_f / 2.0, 0.01, 0.0, 0.0, p.tire_coeffs)
    _, fy_rear_small = calc_tire_forces(W_r / 2.0, 0.01, 0.0, 0.0, p.tire_coeffs)

    C_alpha_f = 2.0 * (fy_front_small / 0.01)  # N/rad for front axle
    C_alpha_r = 2.0 * (fy_rear_small / 0.01)  # N/rad for rear axle

    # Analytical Kus in rad / (m/s^2)
    K_us_analytical_rad = (W_f / (C_alpha_f * 9.81)) - (W_r / (C_alpha_r * 9.81))
    # Convert to deg/G: K_us [deg/G] = K_us_analytical_rad * 9.81 * (180 / pi)
    K_us_analytical_deg_per_g = K_us_analytical_rad * 9.81 * (180.0 / np.pi)

    # Compute non-linear handling diagram at 80 km/h
    diag = compute_handling_diagram(p, speed_kph=80.0, max_ay_g=0.5, n_points=25)
    K_us_sim = diag["kus_linear_deg_per_g"]

    # In the linear pre-load-transfer regime (low Ay), simulation and analytical agree closely
    print(f"\n[BICYCLE MODEL CHECK] Analytical Kus: {K_us_analytical_deg_per_g:.3f} deg/G | Simulated Kus: {K_us_sim:.3f} deg/G")
    assert abs(K_us_sim - K_us_analytical_deg_per_g) < 0.6, (
        f"Kus discrepancy exceeds analytical envelope: sim={K_us_sim}, analytical={K_us_analytical_deg_per_g}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Vertical Load Transfer Conservation
# ─────────────────────────────────────────────────────────────────────────────

def test_vertical_load_transfer_conservation():
    """
    Verify sum of 4 wheel loads exactly equals total weight + aerodynamic downforce:
    sum(Fz_i) == m*g + F_aero_z
    for every time step across dynamic cornering.
    """
    p = HandlingParams()
    res = simulate_maneuver(
        p=p,
        v_x_init=30.0,
        steering_func=lambda t: 0.03 * (t / 2.0 if t < 2.0 else 1.0),
        throttle_func=lambda t: 0.1,
        brake_func=lambda t: 0.0,
        duration=4.0,
        dt=0.02,
    )

    fz_sum = (
        np.asarray(res["Fz_fl"]) +
        np.asarray(res["Fz_fr"]) +
        np.asarray(res["Fz_rl"]) +
        np.asarray(res["Fz_rr"])
    )

    expected_fz = (
        p.m * 9.81 +
        np.asarray(res["aero_downforce_f"]) +
        np.asarray(res["aero_downforce_r"])
    )

    # Difference must be essentially zero (conservation of vertical force)
    max_delta = np.max(np.abs(fz_sum - expected_fz))
    assert max_delta < 5.0, f"Vertical load conservation violated by {max_delta:.2f} N"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Lateral Load Transfer Decomposition
# ─────────────────────────────────────────────────────────────────────────────

def test_load_transfer_decomposition_consistency():
    """Verify that Total Axle Load Transfer == Geometric + Elastic + Unsprung."""
    diag = compute_handling_diagram(HandlingParams(), speed_kph=100.0)

    for pt in diag["points"]:
        if pt["ay_g"] < 0.1:
            continue

        total_front_delta = (pt["Fz_fr"] - pt["Fz_fl"]) / 2.0
        sum_front_components = (
            pt["delta_fz_geom_f"] +
            pt["delta_fz_elast_f"] +
            pt["delta_fz_unsprung_f"]
        )
        assert math.isclose(total_front_delta, sum_front_components, abs_tol=1.0), (
            f"Front load transfer mismatch: total={total_front_delta}, components={sum_front_components}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Roll Stiffness Distribution & Understeer Sensitivity
# ─────────────────────────────────────────────────────────────────────────────

def test_roll_stiffness_shift_increases_understeer():
    """
    RACE ENGINEER PRINCIPLE:
    Increasing front roll stiffness fraction (e.g. stiffer front ARB) MUST increase
    front lateral load transfer and increase the understeer gradient Kus.
    """
    setup_baseline = HandlingParams(roll_dist=0.50, K_arb_f=15000.0)
    setup_stiff_front = HandlingParams(roll_dist=0.65, K_arb_f=35000.0)

    cmp = compare_handling_setups(
        setup_baseline,
        setup_stiff_front,
        speed_kph=100.0,
        name_a="Soft Front ARB",
        name_b="Stiff Front ARB",
    )

    kus_base = cmp["metrics_summary"]["kus_linear_a"]
    kus_stiff = cmp["metrics_summary"]["kus_linear_b"]
    delta_kus = cmp["metrics_summary"]["delta_kus"]

    print(f"\n[ROLL STIFFNESS SENSITIVITY] Soft Front Kus: {kus_base:.3f} -> Stiff Front Kus: {kus_stiff:.3f} (Delta: {delta_kus:+.3f} deg/G)")
    assert delta_kus > 0.0, f"Expected higher Kus with stiffer front roll distribution, got delta={delta_kus}"
    assert "increases the elastic lateral load transfer" in cmp["why"]


# ─────────────────────────────────────────────────────────────────────────────
# 7. Pacejka MF 5.2 Combined-Slip Force Degradation
# ─────────────────────────────────────────────────────────────────────────────

def test_combined_slip_braking_reduces_lateral_force():
    """
    Verify Pacejka Similarity Method:
    Applying longitudinal braking slip (|kappa| > 0) MUST reduce the available
    lateral force Fy compared to pure cornering at the same normal load and slip angle.
    """
    c = TireCoeffs()
    Fz = 4000.0
    alpha = 0.08  # ~4.6 deg

    # Pure cornering (kappa = 0)
    _, fy_pure = calc_tire_forces(Fz, alpha, kappa=0.0, camber_rad=0.0, coeffs=c)

    # Combined cornering + heavy braking (kappa = -0.15)
    fx_comb, fy_comb = calc_tire_forces(Fz, alpha, kappa=-0.15, camber_rad=0.0, coeffs=c)

    assert abs(fx_comb) > 1000.0, "Longitudinal braking force not generated"
    assert abs(fy_comb) < abs(fy_pure) * 0.92, (
        f"Combined slip did not reduce lateral grip: pure Fy={fy_pure:.1f} N, combined Fy={fy_comb:.1f} N"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. Invalid Parameter Guardrails
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_parameters_raise_informative_errors():
    """Verify invalid vehicle or suspension parameters are caught immediately."""
    # Negative mass
    with pytest.raises(ValueError, match="strictly > 0.1"):
        HandlingParams(m_s=-500.0)

    # Zero track width
    with pytest.raises(ValueError, match="Track width"):
        HandlingParams(tw_f=0.0)

    # Infinite spring rate
    with pytest.raises(ValueError, match="cannot be NaN or infinite"):
        HandlingParams(K_spring_f=float('inf'))


# ─────────────────────────────────────────────────────────────────────────────
# 9. Deterministic Reproducibility
# ─────────────────────────────────────────────────────────────────────────────

def test_deterministic_reproducibility():
    """Verify that multiple runs with identical setups produce bit-identical results."""
    p = HandlingParams()
    diag1 = compute_handling_diagram(p, speed_kph=100.0, n_points=20)
    diag2 = compute_handling_diagram(p, speed_kph=100.0, n_points=20)

    assert math.isclose(diag1["kus_linear_deg_per_g"], diag2["kus_linear_deg_per_g"], abs_tol=1e-9)
    assert math.isclose(diag1["ay_peak_g"], diag2["ay_peak_g"], abs_tol=1e-9)
    assert len(diag1["points"]) == len(diag2["points"])

    for pt1, pt2 in zip(diag1["points"], diag2["points"]):
        assert pt1["ay_g"] == pt2["ay_g"]
        assert pt1["delta_steer_deg"] == pt2["delta_steer_deg"]
        assert pt1["Fz_fr"] == pt2["Fz_fr"]


# ─────────────────────────────────────────────────────────────────────────────
# 10. Model Validity Checklist
# ─────────────────────────────────────────────────────────────────────────────

def test_handling_validity_distinction():
    """Verify that validity report never claims 'VALIDATED' without track telemetry."""
    p = HandlingParams()
    val = assess_handling_validity(p)

    assert val.numerically_valid is True
    assert val.physically_valid is True
    assert val.model_validation_status == "PROVISIONAL"
    assert "PROVISIONAL" in val.summary
