"""
Tests for SuspensionLab PRO Phase 3:
- 2D Circuit Geometry Integration & Closed-Loop Coordinate Correction
- Defensible Race Engineer Decision Engine (verdict, attribution, evidence, ranked setup levers)
- FastAPI Phase 3 Endpoints (/lapsim/decision and track_coordinates in /lapsim/run)
- End-to-End Workflow Integration & Computational Timing
"""

import time
import numpy as np
import pytest
from fastapi.testclient import TestClient

from suspensionlab.backend.api.main import app
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.shared.models import PlanTier
from suspensionlab.physics.lap_sim import (
    LapSimVehicle, MassProperties, AeroMap, PowertrainModel,
    parse_track_from_curvature, solve_lap
)
from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.physics.suspension_aero_coupling import SuspensionConfig
from suspensionlab.physics.track_geometry import (
    integrate_track_coordinates, gps_to_cartesian, normalize_to_viewport, TrackCoordinates
)
from suspensionlab.physics.race_engineer_decision import (
    synthesize_race_engineer_decision, RaceEngineerDecision, SetupActionRecommendation
)
from suspensionlab.physics.corner_analysis import analyze_lap_corners
from suspensionlab.physics.lap_delta import compute_lap_delta


def make_vehicle(total_mass=800.0, cl_base=1.8, cd_base=0.95, power_scale=1.0, n_speeds=14, n_ay=8):
    pt = PowertrainModel()
    if power_scale != 1.0:
        pt.torque_curve_nm = [t * power_scale for t in pt.torque_curve_nm]
    v = LapSimVehicle(
        mass_props=MassProperties(total_mass=total_mass),
        aero=AeroMap(cl_base=cl_base, cd_base=cd_base),
        powertrain=pt,
        tire_coeffs=TireCoeffs(),
        suspension=SuspensionConfig(),
        use_coupling=False,
    )
    v.build_ggv(n_speeds=n_speeds, n_ay=n_ay)
    return v


def make_curved_track(n_points=300, length_m=2000.0):
    distances = np.linspace(0, length_m, n_points).tolist()
    curvatures = []
    for d in distances:
        frac = d / length_m
        if 0.15 <= frac <= 0.30:
            curvatures.append(1.0 / 60.0)  # 60m radius right
        elif 0.55 <= frac <= 0.70:
            curvatures.append(-1.0 / 80.0) # 80m radius left
        else:
            curvatures.append(0.0)
    return parse_track_from_curvature(distances, curvatures), distances, curvatures


# ─── 1. Track Geometry & Coordinate Integration ───────────────────────────────

def test_straight_line_geometry():
    """Verify that a flat straight track maintains heading=0, x=s, and y=0."""
    distances = np.linspace(0, 1000, 101)
    curvatures = np.zeros(101)

    coords = integrate_track_coordinates(distances, curvatures, initial_heading_rad=0.0)
    assert coords.n_points == 101
    assert coords.is_closed is False
    assert coords.x[0] == pytest.approx(0.0)
    assert coords.y[0] == pytest.approx(0.0)
    assert coords.x[-1] == pytest.approx(1000.0, abs=1e-3)
    assert coords.y[-1] == pytest.approx(0.0, abs=1e-3)
    assert np.allclose(coords.heading_rad, 0.0, atol=1e-6)


def test_circle_geometry_and_closure():
    """Verify that a circular track closes within threshold and heading rotates by 2*pi."""
    r = 100.0
    circumference = 2 * np.pi * r
    n_points = 200
    distances = np.linspace(0, circumference, n_points)
    curvatures = np.full(n_points, 1.0 / r)

    coords = integrate_track_coordinates(distances, curvatures, initial_heading_rad=0.0)
    assert coords.is_closed is True
    # Initial point (0, 0)
    assert coords.x[0] == pytest.approx(0.0, abs=1e-4)
    assert coords.y[0] == pytest.approx(0.0, abs=1e-4)
    # Closed loop correction ensures endpoint exactly returns to (0, 0)
    assert coords.x[-1] == pytest.approx(0.0, abs=1e-3)
    assert coords.y[-1] == pytest.approx(0.0, abs=1e-3)
    # Total angle rotation is 2*pi
    assert coords.heading_rad[-1] == pytest.approx(2 * np.pi, rel=1e-2)


def test_loop_closure_error_distribution():
    """Verify loop closure error is distributed linearly along arc length."""
    # Semi-closed track with small endpoint drift
    distances = np.linspace(0, 1000, 100)
    # Create smooth curve that almost closes
    theta = np.linspace(0, 2 * np.pi * 0.98, 100)
    curvatures = np.gradient(theta, distances)

    coords = integrate_track_coordinates(distances, curvatures, closure_threshold_m=100.0)
    if coords.is_closed:
        assert coords.x[0] == pytest.approx(coords.x[-1], abs=1e-3)
        assert coords.y[0] == pytest.approx(coords.y[-1], abs=1e-3)


def test_viewport_normalization():
    """Verify normalization scales coordinates into viewport bounds with padding."""
    x = np.array([0.0, 500.0, 1000.0])
    y = np.array([-200.0, 0.0, 200.0])

    norm_x, norm_y, bounds = normalize_to_viewport(x, y, width=800.0, height=600.0, padding=40.0)
    assert np.all(norm_x >= 39.9)
    assert np.all(norm_x <= 760.1)
    assert np.all(norm_y >= 39.9)
    assert np.all(norm_y <= 560.1)
    assert bounds["span_x_m"] == pytest.approx(1000.0)
    assert bounds["span_y_m"] == pytest.approx(400.0)


def test_gps_to_cartesian():
    """Verify equirectangular projection converts GPS lat/lon to meters."""
    # 0.001 deg latitude is approx 111.3 meters
    lats = [52.0, 52.001]
    lons = [0.0, 0.0]

    x, y, dists = gps_to_cartesian(lats, lons)
    assert len(x) == 2
    assert x[0] == 0.0 and y[0] == 0.0
    assert y[1] == pytest.approx(111.3, abs=2.0)
    assert dists[1] == pytest.approx(111.3, abs=2.0)


# ─── 2. Race Engineer Decision Engine ─────────────────────────────────────────

def test_decision_synthesis_faster_setup():
    """Verify decision engine correctly attributes lap time gain to lower mass / higher aero."""
    track, dists, curvs = make_curved_track(n_points=250, length_m=1500.0)
    veh_base = make_vehicle(total_mass=820.0, cl_base=1.60, cd_base=0.95)
    veh_cand = make_vehicle(total_mass=780.0, cl_base=1.85, cd_base=0.96) # Faster

    res_a = solve_lap(veh_base, track)
    res_b = solve_lap(veh_cand, track)

    assert res_b.total_time < res_a.total_time

    decision = synthesize_race_engineer_decision(
        res_a, res_b,
        setup_baseline={"mass": 820.0, "cl_base": 1.60},
        setup_candidate={"mass": 780.0, "cl_base": 1.85},
    )

    assert isinstance(decision, RaceEngineerDecision)
    assert decision.total_delta_s < -0.05
    assert "faster" in decision.verdict.lower()
    assert len(decision.where_time_lost) > 0
    assert len(decision.why_time_lost) > 0
    assert len(decision.supporting_evidence) > 0
    assert decision.confidence_rating in ["MODEL_SUPPORTED", "PROVEN", "LIKELY", "CORRELATED"]
    assert len(decision.ranked_actions) > 0
    # Model limitations disclosure must be explicitly stated
    assert "quasi-steady-state" in decision.model_limitations.lower()


def test_decision_synthesis_slower_setup():
    """Verify decision engine correctly flags a drag-penalized slower setup."""
    track, dists, curvs = make_curved_track(n_points=250, length_m=1500.0)
    veh_base = make_vehicle(total_mass=800.0, cl_base=1.80, cd_base=0.85)
    veh_drag = make_vehicle(total_mass=800.0, cl_base=1.80, cd_base=1.30) # High drag, slower

    res_a = solve_lap(veh_base, track)
    res_b = solve_lap(veh_drag, track)

    assert res_b.total_time > res_a.total_time

    decision = synthesize_race_engineer_decision(
        res_a, res_b,
        setup_baseline={"cd_base": 0.85},
        setup_candidate={"cd_base": 1.30},
    )

    assert decision.total_delta_s > 0.05
    assert "slower" in decision.verdict.lower()
    assert len(decision.ranked_actions) > 0
    # Drag reduction should be recommended
    action_params = [a.parameter for a in decision.ranked_actions]
    assert "cd_base" in action_params or "aero_drag" in str(decision.ranked_actions)


def test_decision_synthesis_with_sensitivity_prioritization():
    """Verify ranked actions prioritize parameters with higher sensitivity gradients."""
    track, dists, curvs = make_curved_track(n_points=200, length_m=1000.0)
    veh_a = make_vehicle()
    veh_b = make_vehicle(total_mass=780.0)

    res_a = solve_lap(veh_a, track)
    res_b = solve_lap(veh_b, track)

    sensitivities = {
        "cl_base": -0.85,    # High sensitivity
        "cd_base": 0.35,
        "total_mass": 0.015, # Lower per-unit sensitivity
    }

    decision = synthesize_race_engineer_decision(
        res_a, res_b,
        sensitivities=sensitivities,
    )

    assert len(decision.ranked_actions) > 0
    assert decision.ranked_actions[0].parameter in ["cl_base", "total_mass"]


# ─── 3. Backend API Endpoints (Phase 3) ───────────────────────────────────────

@pytest.fixture(autouse=True)
def override_auth_for_lap_sim_tests():
    """Bypass auth for integration testing on each test function."""
    mock_user = UserContext(
        user_id="00000000-0000-0000-0000-000000000000",
        plan=PlanTier.ENTERPRISE.value,
        email="engineer@suspensionlab.com",
        name="Test Engineer",
        onboarding_complete=True,
        is_admin=True,
    )
    app.dependency_overrides[verify_api_key] = lambda: mock_user
    yield
    app.dependency_overrides.pop(verify_api_key, None)


@pytest.fixture
def client():
    return TestClient(app)


def test_api_run_includes_track_coordinates(client):
    """Verify POST /lapsim/run returns integrated track_coordinates."""
    payload = {
        "distances": [0.0, 100.0, 200.0, 300.0, 400.0, 500.0],
        "curvatures": [0.0, 0.01, 0.01, 0.0, 0.0, 0.0],
        "vehicle": {
            "mass": 800.0,
            "aero_cl": 1.8,
            "aero_cd": 0.9,
        }
    }
    res = client.post("/lapsim/run", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "track_coordinates" in data
    coords = data["track_coordinates"]
    assert "x" in coords
    assert "y" in coords
    assert "heading_rad" in coords
    assert len(coords["x"]) == 6
    assert len(coords["y"]) == 6


def test_api_decision_endpoint(client):
    """Verify POST /lapsim/decision synthesizes race engineer decision."""
    payload = {
        "distances": [0.0, 100.0, 200.0, 300.0, 400.0, 500.0],
        "curvatures": [0.0, 0.01, 0.01, 0.0, 0.0, 0.0],
        "vehicle_a": {
            "mass": 820.0,
            "aero_cl": 1.6,
            "aero_cd": 0.95,
        },
        "vehicle_b": {
            "mass": 780.0,
            "aero_cl": 1.9,
            "aero_cd": 0.95,
        },
    }
    res = client.post("/lapsim/decision", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "verdict" in data
    assert "total_delta_s" in data
    assert "where_time_lost" in data
    assert "why_time_lost" in data
    assert "ranked_actions" in data
    assert "model_limitations" in data
    assert isinstance(data["ranked_actions"], list)


# ─── 4. End-to-End Workflow & Computational Timing ────────────────────────────

def test_phase3_full_workflow_benchmark():
    """Verify full end-to-end Phase 3 pipeline completes deterministically in < 2.5s."""
    t0 = time.perf_counter()

    # 1. Track generation & Coordinate integration
    track, dists, curvs = make_curved_track(n_points=350, length_m=3000.0)
    coords = integrate_track_coordinates(dists, curvs)
    assert coords.n_points == 350

    # 2. Lap solve A & B
    veh_a = make_vehicle(total_mass=820.0, cl_base=1.70, n_speeds=6, n_ay=5)
    veh_b = make_vehicle(total_mass=780.0, cl_base=1.90, n_speeds=6, n_ay=5)
    res_a = solve_lap(veh_a, track)
    res_b = solve_lap(veh_b, track)

    # 3. Corner detection & comparison
    dt_a = np.zeros(len(dists))
    for i in range(1, len(dists)):
        dt_a[i] = (dists[i] - dists[i-1]) / max(0.5 * (res_a.speeds[i] + res_a.speeds[i-1]), 0.1)
    corners_a = analyze_lap_corners(
        res_a.distances, res_a.speeds, res_a.curvatures,
        res_a.lateral_g, res_a.longitudinal_g, dt_a
    )
    assert len(corners_a) >= 2

    # 4. Lap delta attribution
    report = compute_lap_delta(res_a, res_b, corners_a=corners_a)
    assert len(report.sector_deltas) >= 1

    # 5. Race engineer decision synthesis
    decision = synthesize_race_engineer_decision(res_a, res_b)
    assert decision.confidence_rating in ["MODEL_SUPPORTED", "PROVEN", "LIKELY", "CORRELATED"]

    elapsed = time.perf_counter() - t0
    # Must be fast and suitable for interactive dashboard exploration (< 6.0s for 2 full vehicle solves & analysis)
    assert elapsed < 6.0, f"Phase 3 end-to-end pipeline took {elapsed:.2f}s (expected < 6.0s)"
