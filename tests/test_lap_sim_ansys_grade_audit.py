"""ANSYS / MSC ADAMS Grade Lap Simulator Audit Test Suite.

Verifies:
1. Closed-loop work-energy balance residual <= 1.5% across Spa, Silverstone, Monza, and FSAE.
2. Standing start 0-100 km/h acceleration time between 2.8s and 4.0s (GT3 physical benchmark).
3. Exact analytical banked cornering physics within 2.0% of theoretical equilibrium limit.
4. Dynamic brake bias load transfer coupling and stopping distance sensitivity.
5. Strict physical bounding of tractive and braking forces and pedal percentages across entire laps.
6. True physical U-shaped convexity of lap time vs. Front ARB (LLTD) across all 4 circuits.
7. Setup response surface matches actual numerical solver within 0.02s.
8. Monotonic decrease of chassis max_roll_deg when roll stiffness is doubled.
9. Comprehensive chassis attitude telemetry trace (roll_deg, pitch_deg) and contract payload.
"""

import math
import pytest
import numpy as np
from suspensionlab.physics.lap_sim import (
    simulate_lap,
    LapSimVehicleParams,
    compute_ggv_surface,
    TrackSegment,
)


def test_closed_loop_work_energy_balance_across_circuits():
    """Verify that work-energy conservation error is <= 1.5% across Spa, Silverstone, Monza, and FSAE."""
    for track_name in ("spa", "silverstone", "monza", "fsae_endurance"):
        res = simulate_lap(track=track_name, is_closed=True, compute_surface=False)
        # 1. Closed loop speed closure
        assert abs(res.speeds[0] - res.speeds[-1]) < 0.01, (
            f"{track_name} failed speed closure: |{res.speeds[0]} - {res.speeds[-1]}|"
        )

        # 2. Work-energy balance residual
        assert res.energy_balance_error_pct <= 1.5, (
            f"{track_name} energy balance error {res.energy_balance_error_pct:.3f}% exceeds 1.5%"
        )

        # 3. Direct component summation audit
        e_sum = res.aero_drag_energy_kj + res.rolling_energy_kj + res.braking_energy_kj
        rel_diff = abs(res.energy_used_kj - e_sum) / max(res.energy_used_kj, 1.0)
        assert rel_diff <= 0.015, f"{track_name} direct residual {rel_diff * 100:.3f}% exceeds 1.5%"


def test_0_to_100_kmh_acceleration_time():
    """Verify 0-100 km/h standing start time is between 2.8s and 4.0s (GT3 physical benchmark)."""
    vp = LapSimVehicleParams()
    ggv = compute_ggv_surface(vp)
    speeds = ggv.speeds_ms
    ax = ggv.ax_accel_ay0

    target_v = 100.0 / 3.6
    t_accel = 0.0
    for i in range(len(speeds) - 1):
        v1 = speeds[i]
        v2 = min(speeds[i + 1], target_v)
        if v1 >= target_v:
            break
        a_mid = max(0.5 * (ax[i] + ax[i + 1]), 1.0)
        t_accel += (v2 - v1) / a_mid

    assert 2.8 <= t_accel <= 4.0, (
        f"0-100 km/h acceleration time {t_accel:.3f}s outside physical target window [2.8s, 4.0s]"
    )


def test_exact_banked_corner_physics():
    """Verify apex lateral acceleration on banked corner matches exact analytical formula <= 2.0%."""
    R = 100.0
    curv = 1.0 / R
    bank = 0.15  # rad (~8.6 deg)
    vp = LapSimVehicleParams()
    ggv = compute_ggv_surface(vp)

    segs = []
    for d in range(0, 300, 2):
        segs.append(TrackSegment(distance=float(d), curvature=0.0, bank_angle=0.0))
    for d in range(300, 500, 2):
        segs.append(TrackSegment(distance=float(d), curvature=curv, bank_angle=bank))
    for d in range(500, 800, 2):
        segs.append(TrackSegment(distance=float(d), curvature=0.0, bank_angle=0.0))

    res = simulate_lap(vehicle=vp, track=segs, is_closed=False, compute_surface=False)
    v_apex = min(res.speeds[150:250])
    ay_sim = (v_apex ** 2) * curv

    dv_grid = ggv.speeds_ms[1] - ggv.speeds_ms[0]
    iv = min(max(int((v_apex - ggv.speeds_ms[0]) / dv_grid), 0), len(ggv.speeds_ms) - 2)
    dv = (v_apex - ggv.speeds_ms[iv]) / dv_grid
    ay_cap = ggv.ay_max[iv] * (1.0 - dv) + ggv.ay_max[iv + 1] * dv
    mu_eff = ay_cap / 9.81
    denom = math.cos(bank) - mu_eff * math.sin(bank)
    ay_exact = 9.81 * (math.sin(bank) + mu_eff * math.cos(bank)) / denom

    rel_error = abs(ay_sim - ay_exact) / ay_exact
    assert rel_error <= 0.02, (
        f"Banked corner ay_sim {ay_sim:.3f} differs from exact analytical {ay_exact:.3f} by {rel_error*100:.2f}% (> 2%)"
    )


def test_brake_bias_sensitivity_on_stopping_distance():
    """Verify optimal brake bias yields strictly shorter stopping distance than front or rear saturated bias."""
    def calc_stopping_dist(bf: float) -> float:
        vp = LapSimVehicleParams(brake_bias_front=bf)
        ggv = compute_ggv_surface(vp)
        speeds = ggv.speeds_ms
        ax_brk = ggv.ax_brake_ay0
        v_target = 200.0 / 3.6
        dist = 0.0
        for i in range(len(speeds) - 1):
            v1 = speeds[i]
            v2 = min(speeds[i + 1], v_target)
            if v1 >= v_target:
                break
            a_mid = max(0.5 * (ax_brk[i] + ax_brk[i + 1]), 1.0)
            dist += (v2 ** 2 - v1 ** 2) / (2.0 * a_mid)
        return dist

    d_opt = calc_stopping_dist(0.60)
    d_front_heavy = calc_stopping_dist(0.85)
    d_rear_heavy = calc_stopping_dist(0.35)

    assert d_opt < d_front_heavy, (
        f"Optimal brake bias stopping distance {d_opt:.2f}m not shorter than front-saturated {d_front_heavy:.2f}m"
    )
    assert d_opt < d_rear_heavy, (
        f"Optimal brake bias stopping distance {d_opt:.2f}m not shorter than rear-saturated {d_rear_heavy:.2f}m"
    )


def test_tractive_and_braking_forces_never_exceed_physical_envelope():
    """Verify pedal throttle and brake percentages stay strictly bounded in [0.0, 100.0]%."""
    for track_name in ("spa", "silverstone", "monza", "fsae_endurance"):
        res = simulate_lap(track=track_name, is_closed=True, compute_surface=False)
        trace = res.trace

        for i, thr in enumerate(trace["throttle_pct"]):
            assert 0.0 <= thr <= 100.0, f"{track_name} node {i}: throttle {thr}% outside [0, 100]"
        for i, brk in enumerate(trace["brake_pct"]):
            assert 0.0 <= brk <= 100.0, f"{track_name} node {i}: brake {brk}% outside [0, 100]"


def test_lltd_u_shaped_convexity_all_four_circuits():
    """Verify true U-shaped convexity of lap time vs. Front ARB across all 4 built-in championship tracks."""
    for track_name in ("spa", "silverstone", "monza", "fsae_endurance"):
        t_soft = simulate_lap(track=track_name, front_arb=15.0, compute_surface=False).lap_time_s
        t_mid = simulate_lap(track=track_name, front_arb=45.0, compute_surface=False).lap_time_s
        t_stiff = simulate_lap(track=track_name, front_arb=90.0, compute_surface=False).lap_time_s

        assert t_mid < t_soft, (
            f"{track_name}: baseline setup {t_mid:.2f}s not faster than oversteering soft ARB {t_soft:.2f}s"
        )
        assert t_mid < t_stiff, (
            f"{track_name}: baseline setup {t_mid:.2f}s not faster than understeering stiff ARB {t_stiff:.2f}s"
        )


def test_setup_response_surface_matches_actual_solver():
    """Verify optimal setup recommended by setup_surface matches direct simulation within <= 0.02s."""
    res = simulate_lap(track="fsae_endurance", compute_surface=True)
    assert res.setup_surface is not None
    opt = res.setup_surface["optimal_setup"]
    opt_arb = opt["front_arb_n_mm"]
    opt_aero = opt["aero_balance_front_pct"]
    expected_time = opt["lap_time_s"]

    res_check = simulate_lap(
        track="fsae_endurance",
        front_arb=opt_arb,
        aero_balance_front=opt_aero / 100.0,
        compute_surface=False,
    )
    diff = abs(res_check.lap_time_s - expected_time)
    assert diff <= 0.02, (
        f"Setup surface optimal lap time {expected_time:.3f}s differs from actual simulation {res_check.lap_time_s:.3f}s by {diff:.4f}s (> 0.02s)"
    )


def test_max_roll_deg_decreases_monotonically():
    """Verify max_roll_deg decreases monotonically when Front ARB + Rear ARB stiffness is doubled."""
    res_base = simulate_lap(track="spa", front_arb=45.0, rear_arb=30.0, compute_surface=False)
    res_double = simulate_lap(track="spa", front_arb=90.0, rear_arb=60.0, compute_surface=False)
    res_quad = simulate_lap(track="spa", front_arb=180.0, rear_arb=120.0, compute_surface=False)

    assert res_base.max_roll_deg > res_double.max_roll_deg, (
        f"Doubling ARB did not decrease max_roll_deg: base={res_base.max_roll_deg}, double={res_double.max_roll_deg}"
    )
    assert res_double.max_roll_deg > res_quad.max_roll_deg, (
        f"Quadrupling ARB did not decrease max_roll_deg: double={res_double.max_roll_deg}, quad={res_quad.max_roll_deg}"
    )


def test_chassis_attitude_trace_and_contract_payload():
    """Verify roll_deg and pitch_deg in trace, and summary fields in JSON payload."""
    res = simulate_lap(track="spa", compute_surface=False)
    payload = res.to_contract_dict()

    assert "roll_deg" in payload["trace"]
    assert "pitch_deg" in payload["trace"]
    assert len(payload["trace"]["roll_deg"]) == len(payload["trace"]["s_m"])
    assert len(payload["trace"]["pitch_deg"]) == len(payload["trace"]["s_m"])

    # Roll sign reflects left (< 0) vs right (> 0) turns
    assert any(r > 0.05 for r in payload["trace"]["roll_deg"]), "Expected positive roll_deg for right corners"
    assert any(r < -0.05 for r in payload["trace"]["roll_deg"]), "Expected negative roll_deg for left corners"

    assert "max_roll_deg" in payload and payload["max_roll_deg"] > 0.0
    assert "max_pitch_deg" in payload and payload["max_pitch_deg"] > 0.0
    assert "aero_drag_energy_kj" in payload and payload["aero_drag_energy_kj"] > 0.0
    assert "rolling_energy_kj" in payload and payload["rolling_energy_kj"] > 0.0
    assert "energy_balance_error_pct" in payload
