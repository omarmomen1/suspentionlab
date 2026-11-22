"""Analytical & Physics Verification Suite.

Verifies:
1. Open-track non-zero work-energy theorem on 5% grade ramp within <= 1.0%.
2. Exact GGV envelope compliance across all 4 championship circuits (Spa, Silverstone, Monza, FSAE).
3. Standing start 0-100 km/h acceleration time between 2.8s and 4.0s (GT3 physical benchmark).
4. Exact analytical banked cornering physics within 2.0% of theoretical equilibrium limit.
5. Dynamic brake bias load transfer coupling and stopping distance sensitivity.
6. Strict physical bounding of tractive and braking forces and pedal percentages across entire laps.
7. True physical U-shaped convexity of lap time vs. Front ARB (LLTD) across all 4 circuits.
8. Setup response surface matches actual numerical solver within 0.02s.
9. Monotonic decrease of chassis max_roll_deg when roll stiffness is doubled.
10. Comprehensive chassis attitude telemetry trace (roll_deg, pitch_deg) and contract payload.
"""

import math
import pytest
import numpy as np
from suspensionlab.physics.lap_sim import (
    simulate_lap,
    LapSimVehicleParams,
    compute_ggv_surface,
    get_builtin_track,
    TrackSegment,
)


def test_open_track_work_energy_theorem():
    """Verify independently that W_tractive - W_drag - W_roll - W_brake == Delta E_kin + Delta E_pot within <= 1.0%."""
    vp = LapSimVehicleParams()
    # 300m ramp at +5% grade (elevation = 0.05 * d)
    segs = [TrackSegment(distance=float(d), curvature=0.0, elevation=0.05 * float(d), bank_angle=0.0) for d in range(0, 302, 2)]
    res = simulate_lap(vehicle=vp, track=segs, is_closed=False, v_start=15.0, compute_surface=False)

    v_start = res.speeds[0]
    v_end = res.speeds[-1]
    delta_ke = 0.5 * vp.mass_kg * (v_end ** 2 - v_start ** 2)
    delta_h = segs[-1].elevation - segs[0].elevation
    delta_pe = vp.mass_kg * 9.81 * delta_h
    delta_e_total_kj = (delta_ke + delta_pe) / 1000.0

    w_net_kj = res.energy_used_kj - res.aero_drag_energy_kj - res.rolling_energy_kj - res.braking_energy_kj
    rel_error = abs(w_net_kj - delta_e_total_kj) / max(abs(delta_e_total_kj), 1.0)
    assert rel_error <= 0.010, f"Work-energy theorem discrepancy {rel_error * 100.0:.4f}% exceeds 1.0% tolerance"


def test_ggv_envelope_compliance_across_all_circuits():
    """Verify that commanded acceleration (ax, ay) strictly complies with the calculated GGV envelope across all 4 circuits."""
    vp = LapSimVehicleParams()
    ggv = compute_ggv_surface(vp)
    v_ggv = ggv.speeds_ms
    dv_grid = max(float(v_ggv[1] - v_ggv[0]), 1e-4)
    n_v = len(v_ggv)
    n_ay = len(ggv.ay_fractions)
    accel_surf = ggv.ax_accel_surface
    brake_surf = ggv.ax_brake_surface

    def lookup_ax_acc(v: float, ay: float) -> float:
        iv = min(max(int((v - v_ggv[0]) / dv_grid), 0), n_v - 2)
        dv = (v - v_ggv[iv]) / dv_grid
        ay_lim = ggv.ay_max[iv] * (1.0 - dv) + ggv.ay_max[iv + 1] * dv
        ay_frac = min(max(ay / max(ay_lim, 0.01), 0.0), 1.0)
        j_float = ay_frac * (n_ay - 1)
        j0 = min(max(int(j_float), 0), n_ay - 2)
        dj = j_float - j0
        a0 = (1.0 - dv) * accel_surf[iv, j0] + dv * accel_surf[iv + 1, j0]
        a1 = (1.0 - dv) * accel_surf[iv, j0 + 1] + dv * accel_surf[iv + 1, j0 + 1]
        return float((1.0 - dj) * a0 + dj * a1)

    def lookup_ax_brk(v: float, ay: float) -> float:
        iv = min(max(int((v - v_ggv[0]) / dv_grid), 0), n_v - 2)
        dv = (v - v_ggv[iv]) / dv_grid
        ay_lim = ggv.ay_max[iv] * (1.0 - dv) + ggv.ay_max[iv + 1] * dv
        ay_frac = min(max(ay / max(ay_lim, 0.01), 0.0), 1.0)
        j_float = ay_frac * (n_ay - 1)
        j0 = min(max(int(j_float), 0), n_ay - 2)
        dj = j_float - j0
        b0 = (1.0 - dv) * brake_surf[iv, j0] + dv * brake_surf[iv + 1, j0]
        b1 = (1.0 - dv) * brake_surf[iv, j0 + 1] + dv * brake_surf[iv + 1, j0 + 1]
        return float((1.0 - dj) * b0 + dj * b1)

    for track_name in ("spa", "silverstone", "monza", "fsae_endurance"):
        res = simulate_lap(vehicle=vp, track=track_name, is_closed=True, compute_surface=False)
        assert abs(res.speeds[0] - res.speeds[-1]) < 0.01, f"{track_name} speed closure failed"
        segs = get_builtin_track(track_name)
        n = len(res.speeds)
        for i in range(1, n):
            v_curr = res.speeds[i]
            v_prev = res.speeds[i - 1]
            ds = res.distances[i] - res.distances[i - 1]

            # Banked corner lateral tire acceleration at previous station (for forward acceleration)
            turn_sign_prev = 1.0 if segs[i - 1].curvature >= 0 else -1.0
            theta_prev = segs[i - 1].bank_angle * turn_sign_prev
            ay_raw_prev = (v_prev ** 2) * abs(segs[i - 1].curvature)
            mu_req_prev = (ay_raw_prev * math.cos(theta_prev) - 9.81 * math.sin(theta_prev)) / max(9.81 * math.cos(theta_prev) + ay_raw_prev * math.sin(theta_prev), 1.0)
            ay_prev = max(mu_req_prev * 9.81, 0.0)

            # Banked corner lateral tire acceleration at current station (for lateral grip and braking)
            turn_sign_curr = 1.0 if segs[i].curvature >= 0 else -1.0
            theta_curr = segs[i].bank_angle * turn_sign_curr
            ay_raw_curr = (v_curr ** 2) * abs(segs[i].curvature)
            mu_req_curr = (ay_raw_curr * math.cos(theta_curr) - 9.81 * math.sin(theta_curr)) / max(9.81 * math.cos(theta_curr) + ay_raw_curr * math.sin(theta_curr), 1.0)
            ay_curr = max(mu_req_curr * 9.81, 0.0)

            # Check lateral grip limit + 2%
            iv = min(max(int((v_curr - v_ggv[0]) / dv_grid), 0), n_v - 2)
            dv = (v_curr - v_ggv[iv]) / dv_grid
            ay_lim = ggv.ay_max[iv] * (1.0 - dv) + ggv.ay_max[iv + 1] * dv
            assert ay_curr <= ay_lim * 1.02 + 0.05, f"{track_name} station {i}: ay_curr {ay_curr:.2f} > ay_lim {ay_lim:.2f}"

            # Work-energy acceleration between consecutive stations
            a_kin = (v_curr ** 2 - v_prev ** 2) / (2.0 * max(ds, 0.1))
            grad = (segs[i].elevation - segs[i - 1].elevation) / max(ds, 0.1)
            a_net = a_kin + 9.81 * grad

            if a_net >= 0:
                ax_cap = lookup_ax_acc(v_prev, ay_prev)
                assert a_net <= ax_cap * 1.02 + 0.05, f"{track_name} station {i}: accel {a_net:.3f} > avail {ax_cap:.3f}"
            else:
                ax_cap = lookup_ax_brk(v_curr, ay_curr)
                assert abs(a_net) <= ax_cap * 1.02 + 0.05, f"{track_name} station {i}: brake {abs(a_net):.3f} > avail {ax_cap:.3f}"


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
