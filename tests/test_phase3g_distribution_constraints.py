"""
tests/test_phase3g_distribution_constraints.py
==============================================
Test Suite 1 for Phase 3G: Physical Distribution Constraints & Invariants.

Verifies:
  1. Non-negative pressure guarantee: P_i >= 0.0 under all operating states.
  2. Pressure ceiling constraint: P_i <= P_max.
  3. Total axle demand conservation: P_fl + P_fr + P_rl + P_rr == 2 * P_demand.
  4. Physically plausible left/right asymmetry under lateral acceleration.
  5. Actuator bandwidth / slew rate limit compliance.
"""

import pytest
import numpy as np
from suspensionlab.physics.brake_distribution import (
    BrakeDistributionController,
    BrakeDistributionMechanism,
)


@pytest.fixture
def controller():
    return BrakeDistributionController(
        static_front_bias=0.614,
        p_max_bar=80.0,
        p_min_bar=0.0,
        dp_dt_max_barps=400.0,
    )


def test_non_negative_pressure_invariant(controller):
    """Verify corner pressures remain strictly non-negative across extreme inputs."""
    test_cases = [
        {"demand": 0.0, "steer": 0.0, "vx": 20.0, "yr": 0.0, "ay": 0.0},
        {"demand": 10.0, "steer": 0.2, "vx": 30.0, "yr": 0.8, "ay": 12.0},
        {"demand": 50.0, "steer": -0.2, "vx": 15.0, "yr": -0.8, "ay": -12.0},
        {"demand": 100.0, "steer": 0.0, "vx": 2.0, "yr": 0.0, "ay": 0.0},
    ]
    for tc in test_cases:
        st = controller.predict_pressures(
            driver_demand_bar=tc["demand"],
            steering_rad=tc["steer"],
            vx_mps=tc["vx"],
            yaw_rate_radps=tc["yr"],
            ay_mps2=tc["ay"],
        )
        assert st.p_fl_bar >= 0.0
        assert st.p_fr_bar >= 0.0
        assert st.p_rl_bar >= 0.0
        assert st.p_rr_bar >= 0.0


def test_pressure_ceiling_bound(controller):
    """Verify corner pressures never exceed specified physical system ceiling."""
    st = controller.predict_pressures(
        driver_demand_bar=150.0,  # Demands above 80 bar ceiling
        steering_rad=0.3,
        vx_mps=35.0,
        yaw_rate_radps=0.9,
        ay_mps2=15.0,
    )
    assert st.p_fl_bar <= 80.0
    assert st.p_fr_bar <= 80.0
    assert st.p_rl_bar <= 80.0
    assert st.p_rr_bar <= 80.0


def test_axle_balance_demand_conservation(controller):
    """Verify total front and rear axle pressures conserve commanded demand in straight line."""
    p_demand = 35.0
    st = controller.predict_pressures(
        driver_demand_bar=p_demand,
        steering_rad=0.0,
        vx_mps=25.0,
        yaw_rate_radps=0.0,
        ay_mps2=0.0,
        apply_rate_limiting=False,
    )
    # Total sum across 4 wheels must equal 2 * p_demand (p_f_axle_mean * 2 + p_r_axle_mean * 2)
    # p_f_axle_mean = 2 * 0.614 * 35 = 42.98 bar (front total = 42.98 * 2 = 85.96 bar)
    # p_r_axle_mean = 2 * 0.386 * 35 = 27.02 bar (rear total = 27.02 * 2 = 54.04 bar)
    # Average across all 4 wheels = (85.96 + 54.04)/4 = 140 / 4 = 35.0 bar = p_demand!
    avg_p = 0.25 * (st.p_fl_bar + st.p_fr_bar + st.p_rl_bar + st.p_rr_bar)
    assert pytest.approx(avg_p, rel=1e-4) == p_demand

    # Front bias verification
    front_sum = st.p_fl_bar + st.p_fr_bar
    total_sum = front_sum + st.p_rl_bar + st.p_rr_bar
    assert pytest.approx(front_sum / total_sum, rel=1e-4) == 0.614


def test_left_right_asymmetry_cornering_direction(controller):
    """Verify cornering produces physically consistent outside-heavy pressure allocation."""
    # 1. Left turn (ay > 0): right wheels are outside -> P_FR > P_FL and P_RR > P_RL
    st_left = controller.predict_pressures(
        driver_demand_bar=30.0,
        steering_rad=0.06,
        vx_mps=25.0,
        yaw_rate_radps=0.35,
        ay_mps2=6.0,
        apply_rate_limiting=False,
    )
    assert st_left.p_fr_bar > st_left.p_fl_bar, "In left turn, FR (outside) must have higher pressure than FL (inside)"
    assert st_left.p_rr_bar > st_left.p_rl_bar, "In left turn, RR (outside) must have higher pressure than RL (inside)"
    assert st_left.active_mechanism in (
        BrakeDistributionMechanism.LEFT_RIGHT_LOAD_COMPENSATION,
        BrakeDistributionMechanism.YAW_STABILITY_INTERVENTION,
    )

    # 2. Right turn (ay < 0): left wheels are outside -> P_FL > P_FR and P_RL > P_RR
    st_right = controller.predict_pressures(
        driver_demand_bar=30.0,
        steering_rad=-0.06,
        vx_mps=25.0,
        yaw_rate_radps=-0.35,
        ay_mps2=-6.0,
        apply_rate_limiting=False,
    )
    assert st_right.p_fl_bar > st_right.p_fr_bar, "In right turn, FL (outside) must have higher pressure than FR (inside)"
    assert st_right.p_rl_bar > st_right.p_rr_bar, "In right turn, RL (outside) must have higher pressure than RR (inside)"


def test_hydraulic_slew_rate_limit(controller):
    """Verify hydraulic bandwidth limit prevents step discontinuities when rate limiting is enabled."""
    controller.reset_internal_state()
    dt = 0.005  # 5 ms step
    max_step = controller.dp_dt_max_barps * dt  # 400 * 0.005 = 2.0 bar

    # Instantaneous step demand of 40 bar
    st1 = controller.predict_pressures(
        driver_demand_bar=40.0,
        steering_rad=0.0,
        vx_mps=25.0,
        yaw_rate_radps=0.0,
        ay_mps2=0.0,
        dt=dt,
        apply_rate_limiting=True,
    )
    # Each corner must not exceed max_step
    assert st1.p_fl_bar <= max_step + 1e-6
    assert st1.p_fr_bar <= max_step + 1e-6
    assert st1.p_rl_bar <= max_step + 1e-6
    assert st1.p_rr_bar <= max_step + 1e-6
