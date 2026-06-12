"""
tests/test_physics.py
Regression tests for the physics engine models.
"""
import pytest
import numpy as np
from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    build_state_space,
    compute_modal_properties,
    run_quarter_car_analysis,
)
from suspensionlab.physics.half_car import HalfCarParams, run_half_car_analysis
from suspensionlab.physics.magic_formula import TireCoeffs, calc_tire_forces


# ─── Quarter Car Model ────────────────────────────────────────────────────────

class TestQuarterCarParams:
    def test_default_params_valid(self):
        p = QuarterCarParams()
        assert p.m_s == 300.0
        assert p.k_w == p.k_s * p.MR ** 2

    def test_negative_mass_raises(self):
        with pytest.raises(ValueError, match="positive"):
            QuarterCarParams(m_s=-1)

    def test_zero_mass_raises(self):
        with pytest.raises(ValueError, match="positive"):
            QuarterCarParams(m_s=0)

    def test_invalid_motion_ratio_raises(self):
        with pytest.raises(ValueError, match="Motion ratio"):
            QuarterCarParams(MR=2.0)

    def test_wheel_rate_property(self):
        p = QuarterCarParams(k_s=25000, MR=0.8)
        assert p.k_w == pytest.approx(25000 * 0.64)


class TestQuarterCarModal:
    def test_heave_frequency_range(self):
        p = QuarterCarParams(m_s=350, m_u=40, k_s=25000, c=2050, k_t=200000, MR=0.8)
        modes = compute_modal_properties(p)
        assert 1.0 < modes["f_n_s"] < 2.0

    def test_wheel_hop_frequency_range(self):
        p = QuarterCarParams(m_s=350, m_u=40, k_s=25000, c=2050, k_t=200000, MR=0.8)
        modes = compute_modal_properties(p)
        assert 10.0 < modes["f_n_u"] < 15.0

    def test_heavier_sprung_mass_lowers_frequency(self):
        light = QuarterCarParams(m_s=200)
        heavy = QuarterCarParams(m_s=500)
        f_light = compute_modal_properties(light)["f_n_s"]
        f_heavy = compute_modal_properties(heavy)["f_n_s"]
        assert f_light > f_heavy


class TestQuarterCarStateSpace:
    def test_matrix_dimensions(self):
        p = QuarterCarParams()
        A, B = build_state_space(p)
        assert A.shape == (4, 4)
        assert B.shape == (4,)

    def test_matrix_stability(self):
        """All eigenvalues should have negative real part (stable system)."""
        p = QuarterCarParams()
        A, _ = build_state_space(p)
        eigenvalues = np.linalg.eigvals(A)
        assert all(ev.real < 0 for ev in eigenvalues)


class TestQuarterCarSimulation:
    def test_step_response_converges(self):
        p = QuarterCarParams(m_s=350, m_u=40, k_s=25000, c=2050, k_t=200000, MR=0.8)
        profile = RoadProfile(profile_type="step", amplitude=0.05, duration=5.0)
        result = run_quarter_car_analysis(p, profile)
        assert len(result.time) > 0
        assert np.isclose(result.z_s[-1], 0.05, atol=1e-3)

    def test_sine_response_bounded(self):
        p = QuarterCarParams()
        profile = RoadProfile(profile_type="sine", amplitude=0.02, frequency=2.0, duration=5.0)
        result = run_quarter_car_analysis(p, profile)
        assert np.max(np.abs(result.z_s)) < 0.2  # bounded response

    def test_impulse_response_decays(self):
        p = QuarterCarParams()
        profile = RoadProfile(profile_type="impulse", amplitude=0.05, duration=3.0)
        result = run_quarter_car_analysis(p, profile)
        assert abs(result.z_s[-1]) < 1e-3  # decays to ~zero

    def test_rms_metrics_positive(self):
        p = QuarterCarParams()
        profile = RoadProfile(profile_type="random", amplitude=0.01, duration=5.0)
        result = run_quarter_car_analysis(p, profile)
        assert result.rms_body_accel > 0
        assert result.rms_susp_travel > 0
        assert result.rms_tire_load > 0

    def test_frequency_response_has_data(self):
        p = QuarterCarParams()
        profile = RoadProfile(profile_type="step", amplitude=0.05)
        result = run_quarter_car_analysis(p, profile)
        assert len(result.freq_hz) > 0
        assert len(result.transmissibility_body) == len(result.freq_hz)


# ─── Half Car Model ───────────────────────────────────────────────────────────

class TestHalfCar:
    def test_default_params_valid(self):
        p = HalfCarParams()
        assert p.m_s == 1200.0
        assert p.L == pytest.approx(p.a + p.b)

    def test_simulation_runs(self):
        p = HalfCarParams()
        profile = RoadProfile(profile_type="step", amplitude=0.03, duration=3.0)
        result = run_half_car_analysis(p, profile)
        assert hasattr(result, "time")
        assert len(result.time) > 0

    def test_pitch_response_exists(self):
        p = HalfCarParams()
        profile = RoadProfile(profile_type="step", amplitude=0.03, duration=3.0)
        result = run_half_car_analysis(p, profile)
        assert hasattr(result, "theta")
        assert len(result.theta) > 0


# ─── Magic Formula Tire ───────────────────────────────────────────────────────

class TestMagicFormula:
    def test_zero_slip_zero_force(self):
        Fx, Fy = calc_tire_forces(Fz=4000.0, alpha_rad=0.0, kappa=0.0)
        assert abs(Fx) < 1.0
        assert abs(Fy) < 1.0

    def test_zero_load_zero_force(self):
        Fx, Fy = calc_tire_forces(Fz=0.0, alpha_rad=0.1, kappa=0.1)
        assert Fx == 0.0
        assert Fy == 0.0

    def test_longitudinal_force_sign(self):
        Fx, _ = calc_tire_forces(Fz=4000.0, alpha_rad=0.0, kappa=0.1)
        assert Fx > 0  # positive slip → positive force (braking/driving)

    def test_lateral_force_sign(self):
        _, Fy = calc_tire_forces(Fz=4000.0, alpha_rad=0.05, kappa=0.0)
        assert Fy != 0.0  # non-zero slip angle produces lateral force

    def test_force_saturation(self):
        """Force should saturate at high slip angles (mu * Fz)."""
        _, Fy_low = calc_tire_forces(Fz=4000.0, alpha_rad=0.02, kappa=0.0)
        _, Fy_high = calc_tire_forces(Fz=4000.0, alpha_rad=0.5, kappa=0.0)
        # At high slip, force doesn't keep growing linearly
        ratio = abs(Fy_high) / abs(Fy_low)
        assert ratio < 25  # saturation limits growth

    def test_load_sensitivity(self):
        """Higher normal load → higher force (but not linearly due to load sensitivity)."""
        Fx_light, _ = calc_tire_forces(Fz=2000.0, alpha_rad=0.0, kappa=0.1)
        Fx_heavy, _ = calc_tire_forces(Fz=6000.0, alpha_rad=0.0, kappa=0.1)
        assert abs(Fx_heavy) > abs(Fx_light)
