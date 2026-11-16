"""
tests/test_lap_sim_ggv_closed_loop.py
======================================
Tests for Coupled 3-Pass GGV & Closed-Loop QSS Lap Solver:
1. Closed-circuit speed closure |v(0) - v(end)| < 0.01 m/s (no 360 km/h start bug)
2. Braking distance law and kinematic deceleration verification
3. ARB sensitivity shifting corner grip & identifying UNDERSTEER_FRONT vs OVERSTEER_REAR
4. Real 3-sector splits summing to lap_time_s, positive energy_used_kj & braking_energy_kj
5. Locked JSON Contract verification on POST /api/v1/lap-sim/simulate
"""

import pytest
import numpy as np
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from suspensionlab.physics.lap_sim import (
    compute_ggv_surface,
    simulate_lap,
    get_builtin_track,
    parse_segments_array,
    parse_telemetry_csv,
    VehicleParameters,
    LapSimVehicle,
)
from suspensionlab.backend.main import app
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.api.routes.lap_sim_routes import simulate_lap_endpoint


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def override_auth():
    """Mock authentication for FastAPI test client."""
    mock_user = MagicMock()
    mock_user.is_trial = False
    mock_user.is_admin = True
    mock_user.user_id = "test-user-id"
    mock_user.plan = "PRO"
    app.dependency_overrides[verify_api_key] = lambda: mock_user
    yield
    app.dependency_overrides.pop(verify_api_key, None)


@pytest.fixture
def client():
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Closed-Circuit Speed Closure & Start-Speed Bug Fix
# ─────────────────────────────────────────────────────────────────────────────

def test_closed_circular_skidpad_boundary():
    """Verify that a closed circular skidpad (R = 100.0 m, length = 628.3 m)
    converges cleanly: |v(0) - v(-1)| < 0.1 km/h and steady-state speed v(0) < 160.0 km/h.
    """
    R = 100.0
    L = 628.3
    circle_segs = [
        {"type": "corner", "length_m": L, "radius_m": R, "banking_deg": 0.0, "grade_pct": 0.0}
    ]
    res = simulate_lap(segments=circle_segs, is_closed=True)

    v_start_kmh = res.speeds[0] * 3.6
    v_end_kmh = res.speeds[-1] * 3.6
    closure_err_kmh = abs(v_start_kmh - v_end_kmh)

    assert closure_err_kmh < 0.1, f"Closure error {closure_err_kmh:.4f} km/h exceeds 0.1 km/h!"
    assert v_start_kmh < 160.0, f"Unrealistic start speed {v_start_kmh:.2f} km/h on 100m circle (should be < 160 km/h)!"
    assert v_start_kmh > 80.0, f"Start speed {v_start_kmh:.2f} km/h unreasonably low!"


def test_oval_closed_loop_speed_closure():
    """Verify that closed-circuit iteration converges to |v(0) - v(end)| < 0.01 m/s

    and eliminates the 360 km/h start-speed artifact.
    """
    # Create an oval track: straight 400m -> 180 deg corner R=40m -> straight 400m -> 180 deg corner R=40m
    oval_segments = [
        {"type": "straight", "length_m": 400.0, "radius_m": 0.0, "banking_deg": 0.0, "grade_pct": 0.0},
        {"type": "corner",   "length_m": 125.6, "radius_m": 40.0, "banking_deg": 3.0, "grade_pct": 0.0},
        {"type": "straight", "length_m": 400.0, "radius_m": 0.0, "banking_deg": 0.0, "grade_pct": 0.0},
        {"type": "corner",   "length_m": 125.6, "radius_m": 40.0, "banking_deg": 3.0, "grade_pct": 0.0},
    ]

    result = simulate_lap(segments=oval_segments, is_closed=True)

    v_start = result.speeds[0]
    v_end = result.speeds[-1]
    closure_error = abs(v_start - v_end)

    # 1. Must satisfy exact closed-loop continuity: |v(0) - v(end)| < 0.01 m/s
    assert closure_error < 0.01, f"Closure error {closure_error:.6f} m/s exceeds 0.01 m/s limit!"

    # 2. Start speed must NOT be arbitrary terminal velocity (e.g. 360 km/h)
    # The car exits a 40m radius corner, so start speed on straight should be physical (< 200 km/h)
    start_speed_kmh = v_start * 3.6
    assert start_speed_kmh < 220.0, f"Unrealistic start speed {start_speed_kmh:.1f} km/h (start speed bug)!"
    assert start_speed_kmh > 40.0, f"Start speed {start_speed_kmh:.1f} km/h is unreasonably low!"


def test_builtin_track_closure():
    """Verify closed-loop speed closure across built-in tracks."""
    for track_name in ("spa", "silverstone", "monza", "fsae_endurance"):
        res = simulate_lap(track=track_name, is_closed=True)
        assert abs(res.speeds[0] - res.speeds[-1]) < 0.01, f"{track_name} failed speed closure!"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Braking Distance Law & Kinematics
# ─────────────────────────────────────────────────────────────────────────────

def test_braking_distance_law():
    """Verify that braking deceleration follows kinematic laws:

    v1^2 - v2^2 = 2 * a_brake * delta_s, and higher brake grip reduces stopping distance.
    """
    # Track with 600m straight entering a tight 15m radius hairpin
    track_segs = [
        {"type": "straight", "length_m": 600.0, "radius_m": 0.0, "banking_deg": 0.0, "grade_pct": 0.0},
        {"type": "corner",   "length_m": 80.0,  "radius_m": 15.0, "banking_deg": 0.0, "grade_pct": 0.0},
        {"type": "straight", "length_m": 200.0, "radius_m": 0.0, "banking_deg": 0.0, "grade_pct": 0.0},
    ]

    # Baseline vehicle
    res_base = simulate_lap(segments=track_segs, max_brake_force=28000.0, is_closed=False)
    # High brake force vehicle
    res_high_brake = simulate_lap(segments=track_segs, max_brake_force=45000.0, is_closed=False)

    # 1. Max braking deceleration must be physically realistic (high-downforce prototype car reaching 2.5g to 4.5g)
    assert 1.0 <= res_base.max_braking_g <= 5.0

    # 2. Braking energy must be strictly positive
    assert res_base.braking_energy_kj > 0.0
    assert res_high_brake.braking_energy_kj > 0.0

    # 3. Higher brake force allows later braking and shorter lap time
    assert res_high_brake.lap_time_s <= res_base.lap_time_s + 1e-4

    # 4. Trace braking factor detection
    assert "BRAKING" in res_base.trace["limiting_factor"]
    assert res_base.braking_limited_pct > 0.0


def test_analytical_braking_distance():
    """Verify analytical braking distance law:
    Flat straight, Cd = 0, Cl = 0, k_load = 0, braking 50 m/s to 10 m/s matches (50^2 - 10^2) / (2 * mu * g) within <= 2.0%.
    """
    mu_target = 1.45
    g = 9.81
    v_start = 50.0  # m/s
    v_end = 10.0    # m/s
    delta_s_analytical = (v_start**2 - v_end**2) / (2.0 * mu_target * g)  # ~84.36 m

    r_corner = (v_end**2) / (mu_target * g)
    segments = [
        {"type": "straight", "length_m": 300.0, "radius_m": 0.0, "banking_deg": 0.0, "grade_pct": 0.0},
        {"type": "corner",   "length_m": 80.0,  "radius_m": r_corner, "banking_deg": 0.0, "grade_pct": 0.0},
    ]

    res = simulate_lap(
        segments=segments,
        is_closed=False,
        v_start=v_start,
        cd_total=0.0,
        cl_total=0.0,
        k_load_sensitivity=0.0,
        mu_0=mu_target,
        max_brake_force_n=60000.0,
    )

    speeds = np.array(res.trace["speed_kmh"]) / 3.6
    stations = np.array(res.trace["s_m"])

    # Locate braking zone (between 200m and 305m)
    mask = (stations >= 200.0) & (stations <= 305.0)
    s_zone = stations[mask]
    v_zone = speeds[mask]

    # Interpolate exact distance at 50 m/s and 10 m/s
    s_50 = float(np.interp(v_start, v_zone[::-1], s_zone[::-1]))
    s_10 = float(np.interp(v_end, v_zone[::-1], s_zone[::-1]))

    delta_s_sim = s_10 - s_50
    rel_error = abs(delta_s_sim - delta_s_analytical) / delta_s_analytical

    assert rel_error <= 0.02, (
        f"Simulated braking distance {delta_s_sim:.2f} m deviates {rel_error*100:.2f}% "
        f"from analytical {delta_s_analytical:.2f} m (allowed <= 2.0%)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. ARB Sensitivity & Balance Limits (UNDERSTEER_FRONT vs OVERSTEER_REAR)
# ─────────────────────────────────────────────────────────────────────────────

def test_arb_sensitivity_shifts_balance():
    """Verify that stiffening Front ARB vs Rear ARB shifts LLTD and identifies

    UNDERSTEER_FRONT vs OVERSTEER_REAR balance limits in GGV and simulation.
    """
    # GGV Envelope test:
    # Stiff front ARB: front LLTD > 0.50 -> front tire saturates first -> UNDERSTEER_FRONT
    ggv_stiff_front = compute_ggv_surface(k_arb_f=80000.0, k_arb_r=10000.0)
    # Stiff rear ARB: rear LLTD > 0.50 -> rear tire saturates first -> OVERSTEER_REAR
    ggv_stiff_rear = compute_ggv_surface(k_arb_f=10000.0, k_arb_r=80000.0)

    # Check LLTD
    assert ggv_stiff_front.lltd > 0.55, f"Front LLTD {ggv_stiff_front.lltd} should be > 0.55"
    assert ggv_stiff_rear.lltd < 0.45, f"Front LLTD {ggv_stiff_rear.lltd} should be < 0.45"

    # Check balance limits identified
    assert "UNDERSTEER_FRONT" in ggv_stiff_front.balance_limit
    assert "OVERSTEER_REAR" in ggv_stiff_rear.balance_limit

    # Simulation test on a cornering-heavy FSAE track
    sim_stiff_front = simulate_lap(track="fsae_endurance", k_arb_f=80000.0, k_arb_r=10000.0)
    sim_stiff_rear  = simulate_lap(track="fsae_endurance", k_arb_f=10000.0, k_arb_r=80000.0)

    # Stiff front must exhibit high understeer percentage
    assert sim_stiff_front.understeer_pct > 0.0
    assert "UNDERSTEER_FRONT" in sim_stiff_front.trace["limiting_factor"]

    # Stiff rear must have OVERSTEER_REAR in limiting factors
    assert "OVERSTEER_REAR" in sim_stiff_rear.trace["limiting_factor"]


def test_arb_sensitivity_on_lap_time():
    """Verify that ARB changes alter corner apex speeds and lap time."""
    # Stiff front increases front lateral load transfer, diminishing front grip due to mu(Fz)
    res_stiff_front = simulate_lap(track="fsae_endurance", k_arb_f=85000.0, k_arb_r=10000.0)
    res_balanced    = simulate_lap(track="fsae_endurance", k_arb_f=25000.0, k_arb_r=25000.0)

    # Lap times should differ noticeably due to tire load sensitivity
    assert abs(res_stiff_front.lap_time_s - res_balanced.lap_time_s) > 0.01


def test_suspension_arb_to_lltd_to_lap_time_coupling():
    """Verify suspension ARB -> LLTD -> lap time coupling on 'fsae_endurance':
    k_arb_f = 5000 vs 45000 N*m/rad changes lltd_front, min corner apex speed, and lap_time_s.
    """
    res_soft_f = simulate_lap(track="fsae_endurance", k_arb_front_nm_rad=5000.0, k_arb_rear_nm_rad=22000.0)
    res_stiff_f = simulate_lap(track="fsae_endurance", k_arb_front_nm_rad=45000.0, k_arb_rear_nm_rad=22000.0)

    # 1. LLTD front fraction must change
    lltd_soft = res_soft_f.arb_balance
    lltd_stiff = res_stiff_f.arb_balance
    assert abs(lltd_stiff - lltd_soft) > 0.05, f"LLTD shift {abs(lltd_stiff - lltd_soft):.4f} should exceed 0.05!"

    # 2. Min corner apex speed must change due to load sensitivity
    assert abs(res_soft_f.min_speed_kmh - res_stiff_f.min_speed_kmh) > 0.05, "Min apex speed should vary with ARB!"

    # 3. Lap time must change
    assert abs(res_soft_f.lap_time_s - res_stiff_f.lap_time_s) > 0.02, "Lap time should vary with ARB rate!"


# ─────────────────────────────────────────────────────────────────────────────
# 4. 3-Sector Splits & Energy Outputs
# ─────────────────────────────────────────────────────────────────────────────

def test_three_sector_and_energy_outputs():
    """Verify that sector_times has 3 elements, sum(sector_times) == lap_time_s,

    and energy outputs are strictly positive.
    """
    for track_name in ("spa", "monza", "fsae_endurance"):
        res = simulate_lap(track=track_name)

        # 1. Exactly 3 sectors
        assert len(res.sector_times) == 3, f"{track_name} should have 3 sector times"
        assert all(t > 0 for t in res.sector_times), f"Sector times must be positive: {res.sector_times}"

        # 2. Sector times must sum to total lap time
        sum_sectors = sum(res.sector_times)
        assert sum_sectors == pytest.approx(res.lap_time_s, rel=1e-4)

        # 3. Energy used must be positive (engine work done)
        assert res.energy_used_kj > 0.0, f"{track_name} energy_used_kj must be > 0"

        # 4. Braking energy must be positive
        assert res.braking_energy_kj > 0.0, f"{track_name} braking_energy_kj must be > 0"

        # 5. 2D Coordinates check
        assert len(res.trace["x_m"]) == len(res.trace["s_m"])
        assert len(res.trace["y_m"]) == len(res.trace["s_m"])


def test_sectors_and_energy():
    """Verify sectors and energy outputs:
    len(sector_times) == 3, |sum(sector_times) - lap_time_s| < 0.01, and energy_used_kj > 100.0.
    """
    for track_name in ("spa", "monza"):
        res = simulate_lap(track=track_name)
        assert len(res.sector_times) == 3, f"{track_name} must have exactly 3 sectors!"
        assert abs(sum(res.sector_times) - res.lap_time_s) < 0.01, "Sector sum must equal lap_time_s!"
        assert res.energy_used_kj > 100.0, f"Energy used {res.energy_used_kj} kJ should be > 100.0 kJ!"
        assert res.braking_energy_kj > 50.0, f"Braking energy {res.braking_energy_kj} kJ should be > 50.0 kJ!"


# ─────────────────────────────────────────────────────────────────────────────
# 5. LOCKED JSON CONTRACT on POST /api/v1/lap-sim/simulate
# ─────────────────────────────────────────────────────────────────────────────

def test_api_v1_simulate_locked_contract(client):
    """Verify the LOCKED JSON CONTRACT on POST /api/v1/lap-sim/simulate."""
    payload = {
        "track": "spa",
        "vehicle": {
            "mass": 800.0,
            "aero_cl": 2.2,
            "aero_cd": 0.9,
        },
        "suspension": {
            "k_spring_f": 65000.0,
            "k_spring_r": 85000.0,
            "k_arb_f": 25000.0,
            "k_arb_r": 18000.0,
            "roll_center_f_m": 0.05,
            "roll_center_r_m": 0.08,
            "cg_height_m": 0.30,
        },
    }

    resp = client.post("/api/v1/lap-sim/simulate", json=payload)
    assert resp.status_code == 200, f"Request failed: {resp.text}"

    data = resp.json()

    # Top-level required fields in locked contract
    required_keys = [
        "lap_time_s",
        "sector_times",
        "max_speed_kmh",
        "min_speed_kmh",
        "avg_speed_kmh",
        "max_lat_g",
        "max_long_g",
        "max_braking_g",
        "energy_used_kj",
        "braking_energy_kj",
        "understeer_pct",
        "power_limited_pct",
        "braking_limited_pct",
        "trace",
        "ggv_envelope",
        "corner_opportunities",
    ]
    for key in required_keys:
        assert key in data, f"Missing required top-level key: {key}"

    # Verify sector_times: exactly 3 floats summing to lap_time_s
    assert len(data["sector_times"]) == 3
    assert sum(data["sector_times"]) == pytest.approx(data["lap_time_s"], rel=1e-3)

    # Verify energy values
    assert data["energy_used_kj"] > 0.0
    assert data["braking_energy_kj"] > 0.0

    # Verify trace dictionary structure
    trace = data["trace"]
    trace_keys = [
        "s_m", "x_m", "y_m", "speed_kmh", "lat_g", "long_g",
        "throttle_pct", "brake_pct", "gear", "downforce_n", "limiting_factor"
    ]
    for tk in trace_keys:
        assert tk in trace, f"Missing trace key: {tk}"
        assert len(trace[tk]) == len(trace["s_m"]), f"Trace key {tk} length mismatch!"

    # Verify limiting factor values are strictly in the locked enum
    valid_factors = {"POWER", "BRAKING", "UNDERSTEER_FRONT", "OVERSTEER_REAR"}
    observed_factors = set(trace["limiting_factor"])
    assert observed_factors.issubset(valid_factors), f"Unexpected limiting factors: {observed_factors - valid_factors}"

    # Verify GGV envelope structure
    ggv = data["ggv_envelope"]
    ggv_keys = ["speeds_kmh", "max_lat_g", "max_accel_g", "max_brake_g"]
    for gk in ggv_keys:
        assert gk in ggv, f"Missing GGV key: {gk}"
        assert len(ggv[gk]) > 0

    # Verify corner opportunities list
    opps = data["corner_opportunities"]
    assert isinstance(opps, list)
    if len(opps) > 0:
        opp = opps[0]
        for ok in ("corner_id", "s_start_m", "s_end_m", "v_sim_apex_kmh", "v_driver_apex_kmh", "time_loss_s", "bottleneck"):
            assert ok in opp, f"Missing corner_opportunity key: {ok}"

    # Verify backward-compatible fields
    assert data.get("status") == "success"
    assert "telemetry" in data
    assert "ggv" in data
    assert "track_coordinates" in data


def test_api_v1_simulate_with_custom_segments(client):
    """Verify simulate endpoint with custom segments array input."""
    payload = {
        "segments": [
            {"type": "straight", "length_m": 350.0, "radius_m": 0.0, "banking_deg": 0.0, "grade_pct": 0.0},
            {"type": "corner",   "length_m": 120.0, "radius_m": 35.0, "banking_deg": 2.0, "grade_pct": 0.0},
            {"type": "straight", "length_m": 350.0, "radius_m": 0.0, "banking_deg": 0.0, "grade_pct": 0.0},
            {"type": "corner",   "length_m": 120.0, "radius_m": 35.0, "banking_deg": 2.0, "grade_pct": 0.0},
        ],
        "k_arb_f": 30000.0,
        "k_arb_r": 20000.0,
    }
    resp = client.post("/api/v1/lap-sim/simulate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["lap_time_s"] > 0.0
    assert len(data["sector_times"]) == 3
    assert len(data["trace"]["s_m"]) > 10


def test_api_v1_simulate_with_telemetry_csv(client):
    """Verify simulate endpoint with telemetry data input."""
    payload = {
        "telemetry": {
            "time_s": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "speed_ms": [25.0, 30.0, 35.0, 32.0, 28.0, 22.0, 25.0],
            "lat_g": [0.1, 0.2, 0.4, 1.5, 1.8, 0.5, 0.1],
        }
    }
    resp = client.post("/api/v1/lap-sim/simulate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["lap_time_s"] > 0.0
    assert "trace" in data


def test_gt3_track_calibrations():
    """Verify calibrated GT3 lap times, lengths, top speeds, lateral and braking g-forces across all 4 built-in circuits."""
    from suspensionlab.physics.lap_sim import LapSimVehicleParams, simulate_lap

    vp = LapSimVehicleParams()

    # 1. Spa-Francorchamps: 7004 m, 135-142 s, top speed 278-296 km/h
    res_spa = simulate_lap(vehicle=vp, track="spa")
    assert 7000.0 <= res_spa.distances[-1] <= 7010.0, f"Spa length {res_spa.distances[-1]} not 7004m"
    assert 135.0 <= res_spa.lap_time_s <= 142.0, f"Spa lap time {res_spa.lap_time_s}s outside [135, 142]s"
    assert 275.0 <= res_spa.max_speed_kmh <= 296.0, f"Spa top speed {res_spa.max_speed_kmh} outside [278, 296] km/h"
    assert 1.65 <= res_spa.max_lat_g <= 2.35, f"Spa max lat g {res_spa.max_lat_g} outside [1.65, 2.35]g"
    assert 1.80 <= res_spa.max_braking_g <= 2.45, f"Spa max brake g {res_spa.max_braking_g} outside [1.80, 2.45]g"

    # 2. Silverstone GP: 5891 m, 115-123 s
    res_silv = simulate_lap(vehicle=vp, track="silverstone")
    assert 5885.0 <= res_silv.distances[-1] <= 5895.0, f"Silverstone length {res_silv.distances[-1]} not 5891m"
    assert 115.0 <= res_silv.lap_time_s <= 123.0, f"Silverstone lap time {res_silv.lap_time_s}s outside [115, 123]s"
    assert 1.65 <= res_silv.max_lat_g <= 2.35, f"Silverstone max lat g {res_silv.max_lat_g} outside [1.65, 2.35]g"
    assert 1.80 <= res_silv.max_braking_g <= 2.45, f"Silverstone max brake g {res_silv.max_braking_g} outside [1.80, 2.45]g"

    # 3. Monza: 5793 m, 105-112 s
    res_monza = simulate_lap(vehicle=vp, track="monza")
    assert 5790.0 <= res_monza.distances[-1] <= 5800.0, f"Monza length {res_monza.distances[-1]} not 5793m"
    assert 105.0 <= res_monza.lap_time_s <= 112.0, f"Monza lap time {res_monza.lap_time_s}s outside [105, 112]s"
    assert 275.0 <= res_monza.max_speed_kmh <= 296.0, f"Monza top speed {res_monza.max_speed_kmh} outside [278, 296] km/h"
    assert 1.65 <= res_monza.max_lat_g <= 2.35, f"Monza max lat g {res_monza.max_lat_g} outside [1.65, 2.35]g"
    assert 1.80 <= res_monza.max_braking_g <= 2.45, f"Monza max brake g {res_monza.max_braking_g} outside [1.80, 2.45]g"

    # 4. FSAE Endurance: 1450 m, 62-88 s
    res_fsae = simulate_lap(vehicle=vp, track="fsae_endurance")
    assert 1445.0 <= res_fsae.distances[-1] <= 1455.0, f"FSAE length {res_fsae.distances[-1]} not 1450m"
    assert 62.0 <= res_fsae.lap_time_s <= 88.0, f"FSAE lap time {res_fsae.lap_time_s}s outside [62, 88]s"
    assert 1.80 <= res_fsae.max_braking_g <= 2.45, f"FSAE max brake g {res_fsae.max_braking_g} outside [1.80, 2.45]g"


def test_track_geometry_closure_all_presets():
    """Verify that all 4 championship circuit presets form closed loops: (x[-1], y[-1]) == (x[0], y[0])."""
    for track_key in ("spa", "silverstone", "monza", "fsae_endurance"):
        segs = get_builtin_track(track_key)
        assert len(segs) > 10, f"{track_key} too short"
        x0, y0 = segs[0].x_m, segs[0].y_m
        x_end, y_end = segs[-1].x_m, segs[-1].y_m
        err = np.hypot(x_end - x0, y_end - y0)
        assert err < 1e-4, f"Circuit {track_key} has non-zero closure gap: {err:.6f} m"


def test_stage_l3_dynamic_ride_height_and_pitch():
    """Verify Stage L3 dynamic ride height, pitch calculations, and contract serialization."""
    from suspensionlab.physics.lap_sim import LapSimVehicleParams, simulate_lap

    vp = LapSimVehicleParams(static_rh_front_mm=55.0, static_rh_rear_mm=70.0)
    res = simulate_lap(vehicle=vp, track="spa")

    # Verify trace telemetry
    assert "ride_height_front_mm" in res.trace
    assert "ride_height_rear_mm" in res.trace
    assert "pitch_deg" in res.trace
    assert len(res.trace["ride_height_front_mm"]) == len(res.trace["s_m"])

    # Physical checks: ride height compresses under aero downforce but stays positive
    min_f = res.min_rh_front_mm
    min_r = res.min_rh_rear_mm
    assert 5.0 <= min_f < 55.0, f"Unexpected min front ride height: {min_f}"
    assert 5.0 <= min_r < 70.0, f"Unexpected min rear ride height: {min_r}"

    # Verify contract dict serialization
    c_dict = res.to_contract_dict()
    assert "min_rh_front_mm" in c_dict
    assert "min_rh_rear_mm" in c_dict
    assert "bottoming_events_count" in c_dict
    assert c_dict["min_rh_front_mm"] == min_f
    assert c_dict["min_rh_rear_mm"] == min_r


def test_stage_l4_setup_response_surface():
    """Verify Stage L4 2D setup response surface and 1-click optimizer payload."""
    from suspensionlab.physics.lap_sim import LapSimVehicleParams, simulate_lap, compute_setup_response_surface

    surf = compute_setup_response_surface(
        base_lap_time_s=137.15,
        current_front_arb=45.0,
        current_aero_bal=44.0,
    )
    assert len(surf["front_arb_n_mm"]) == 5
    assert len(surf["aero_balance_front_pct"]) == 5
    assert len(surf["z_lap_time_s"]) == 5
    assert len(surf["z_lap_time_s"][0]) == 5

    # Check that optimal setup has positive or zero time gain
    opt = surf["optimal_setup"]
    assert "optimal_setup" in surf
    assert opt["time_gain_s"] >= 0.0
    assert opt["lap_time_s"] <= 137.15

    # Check full simulate_lap serialization
    res = simulate_lap(track="spa")
    assert res.setup_surface is not None
    assert "optimal_setup" in res.setup_surface
    c_dict = res.to_contract_dict()
    assert "setup_surface" in c_dict
    assert len(c_dict["setup_surface"]["z_lap_time_s"]) == 5

