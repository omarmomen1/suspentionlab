"""
tests/test_lap_sim_phase2.py
============================
Phase 2 Comprehensive Test Suite for SuspensionLab PRO Lap Sim:
1. 3D GGV Surface Tensor Generation & Transparent Labeling
2. Parameter Sensitivity Sweep Engine (setup_sweep.py)
3. Telemetry Correlation & Residual Analysis (telemetry_analysis.py)
4. Optimizer Integration & Physical Evaluation (optimization_engine.py)
5. Backend API Endpoints: /lapsim/ggv, /lapsim/sweep, /lapsim/correlate
"""

import math
import numpy as np
import pytest
from fastapi.testclient import TestClient

from suspensionlab.physics.lap_sim import (
    LapSimVehicle,
    MassProperties,
    AeroMap,
    PowertrainModel,
    solve_lap,
    parse_track_from_curvature,
)
from suspensionlab.physics.magic_formula import TireCoeffs
from suspensionlab.physics.suspension_aero_coupling import SuspensionConfig
from suspensionlab.physics.setup_sweep import (
    SweepParameter,
    run_parameter_sweep,
    SweepResult,
)
from suspensionlab.physics.telemetry_analysis import (
    compare_sim_vs_measured,
    SimVsMeasuredReport,
)
from suspensionlab.physics.optimization_engine import (
    LapTimeObjective,
    DesignSpace,
    DesignVariable,
    VariableCategory,
    MultiObjectiveEvaluator,
    OptimizationObjective,
    ObjectiveType,
    ConstraintManager,
)
from suspensionlab.backend.api.main import app
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.shared.models import PlanTier

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_auth():
    """Bypass auth for FastAPI endpoints in this test module."""
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


def _make_vehicle():
    return LapSimVehicle(
        mass_props=MassProperties(total_mass=780.0, wheelbase=2.7, h_cog=0.32),
        aero=AeroMap(cl_base=2.0, cd_base=0.9),
        powertrain=PowertrainModel(),
        tire_coeffs=TireCoeffs(),
        suspension=SuspensionConfig(),
    )


def _make_track(n_points=120, length_m=1200.0):
    distances = np.linspace(0, length_m, n_points).tolist()
    curvatures = (0.015 * np.sin(np.linspace(0, 2 * np.pi, n_points))).tolist()
    return parse_track_from_curvature(distances, curvatures)


# =============================================================================
# 1. 3D GGV Surface Tensor Generation & Transparent Labeling
# =============================================================================

def test_ggv_3d_surface_generation():
    """Verify 3D GGV surface tensor structure, shape, and transparent labeling."""
    veh = _make_vehicle()
    n_speeds = 15
    n_ay = 11
    veh.build_ggv(n_speeds=n_speeds, n_ay=n_ay)

    assert veh._ggv_speeds is not None
    assert len(veh._ggv_speeds) == n_speeds
    assert len(veh._ggv_ay_frac) == n_ay
    assert veh._ggv_ax_accel.shape == (n_speeds, n_ay)
    assert veh._ggv_ax_brake.shape == (n_speeds, n_ay)

    # Solve lap and verify LapSimResult populates 3D GGV fields
    track = _make_track()
    res = solve_lap(veh, track, build_ggv=False)

    assert hasattr(res, "ggv_ay_frac")
    assert hasattr(res, "ggv_ax_accel_surface")
    assert hasattr(res, "ggv_ax_brake_surface")
    assert hasattr(res, "ggv_type")
    assert res.ggv_type == "INTERPOLATED_PRE_COMPUTED"
    assert len(res.ggv_ay_frac) == n_ay
    assert res.ggv_ax_accel_surface.shape == (n_speeds, n_ay)
    assert res.ggv_ax_brake_surface.shape == (n_speeds, n_ay)

    # Physical check: at pure straight (ay_frac=0, col 0), ax_accel should be greater than
    # at peak lateral cornering (ay_frac=1, col -1) due to tire combined slip and power limits
    for i in range(1, n_speeds - 1):
        assert res.ggv_ax_accel_surface[i, 0] >= res.ggv_ax_accel_surface[i, -1]


# =============================================================================
# 2. Parameter Sensitivity Sweep Engine (setup_sweep.py)
# =============================================================================

def test_parameter_sweep_mass_monotonicity():
    """Verify that sweeping mass produces strictly positive sensitivity (heavier car is slower)."""
    veh = _make_vehicle()
    track = _make_track()

    masses = [740.0, 780.0, 820.0]
    sweep = run_parameter_sweep(
        baseline_vehicle=veh,
        track=track,
        parameter=SweepParameter.MASS,
        values=masses,
        baseline_val=780.0,
        ggv_resolution=(12, 7),
    )

    assert isinstance(sweep, SweepResult)
    assert len(sweep.lap_times_s) == 3
    assert all(sweep.convergence_flags)

    # Mass monotonicity: lap_time increases with mass
    assert sweep.lap_times_s[0] < sweep.lap_times_s[1] < sweep.lap_times_s[2]

    # Gradient dT/dm must be strictly positive
    for sens in sweep.sensitivities_s_per_unit:
        assert not math.isnan(sens)
        assert sens > 0.0

    # Test JSON-safe conversion
    d = sweep.to_dict()
    assert d["parameter"] == "mass"
    assert d["unit"] == "kg"
    assert len(d["lap_times_s"]) == 3
    assert d["deltas_s"][1] == 0.0  # baseline delta is 0


def test_parameter_sweep_aero_downforce():
    """Verify downforce sweep on a twisty track shows performance gain with higher CL."""
    veh = _make_vehicle()
    track = _make_track()

    cls = [1.5, 2.0, 2.5]
    sweep = run_parameter_sweep(
        baseline_vehicle=veh,
        track=track,
        parameter=SweepParameter.AERO_CL,
        values=cls,
        baseline_val=2.0,
        ggv_resolution=(12, 7),
    )

    assert all(sweep.convergence_flags)
    # Higher downforce should lower lap time on this track
    assert sweep.lap_times_s[2] < sweep.lap_times_s[0]
    # Gradient dT/dCL should be negative (more downforce = faster lap)
    mean_sens = np.mean([s for s in sweep.sensitivities_s_per_unit if not math.isnan(s)])
    assert mean_sens < 0.0


# =============================================================================
# 3. Telemetry Correlation & Residual Analysis (telemetry_analysis.py)
# =============================================================================

def test_telemetry_correlation_perfect_match():
    """Verify that correlating a simulation trace with itself yields RMSE=0 and R^2=1.0."""
    veh = _make_vehicle()
    track = _make_track()
    res = solve_lap(veh, track)

    # Create telemetry from simulation result
    meas_data = {
        "distance": res.distances.tolist(),
        "speed": res.speeds.tolist(),
        "lateral_g": res.lateral_g.tolist(),
        "longitudinal_g": res.longitudinal_g.tolist(),
    }

    report = compare_sim_vs_measured(res, meas_data, distance_step_m=5.0)

    assert isinstance(report, SimVsMeasuredReport)
    assert report.num_aligned_points > 10
    assert "speed" in report.channels

    speed_m = report.channels["speed"]
    assert speed_m.rmse == pytest.approx(0.0, abs=1e-3)
    assert speed_m.r_squared == pytest.approx(1.0, abs=1e-3)
    assert speed_m.phase_lag_m == pytest.approx(0.0, abs=1e-1)
    assert report.overall_fit_pct >= 99.0

    # Model disclaimer is required
    assert "Quasi-steady simulation neglects transient yaw" in report.model_disclaimer

    # Test serialization
    rep_dict = report.to_dict()
    assert "channels" in rep_dict
    assert "residuals" in rep_dict


def test_telemetry_correlation_with_shift():
    """Verify that spatial phase lag detection identifies a shifted signal."""
    veh = _make_vehicle()
    track = _make_track()
    res = solve_lap(veh, track)

    shift_m = 10.0
    meas_dist = (res.distances + shift_m).tolist()
    meas_data = {
        "distance": meas_dist,
        "speed": res.speeds.tolist(),
        "lateral_g": res.lateral_g.tolist(),
    }

    report = compare_sim_vs_measured(res, meas_data, distance_step_m=2.0)
    assert "speed" in report.channels
    # Phase lag should be detected within reasonable tolerance of shift_m
    assert abs(report.channels["speed"].phase_lag_m - shift_m) <= 4.0


# =============================================================================
# 4. Optimizer Integration & Physical Evaluation (optimization_engine.py)
# =============================================================================

def test_lap_time_objective_evaluation():
    """Verify LapTimeObjective directly executes physical solve_lap and evaluates constraints."""
    veh = _make_vehicle()
    track = _make_track(n_points=60, length_m=600.0)

    ds = DesignSpace("TestSpace", "Test design space for LapTimeObjective")
    ds.add_variable(DesignVariable(
        name="k_sf", category=VariableCategory.SPRING,
        minimum=40000.0, maximum=120000.0, default_value=75000.0, step=5000.0,
        unit="N/m", source="Test", physical_justification="Front spring rate",
    ))
    ds.add_variable(DesignVariable(
        name="k_sr", category=VariableCategory.SPRING,
        minimum=40000.0, maximum=120000.0, default_value=85000.0, step=5000.0,
        unit="N/m", source="Test", physical_justification="Rear spring rate",
    ))
    ds.add_variable(DesignVariable(
        name="k_arb_f", category=VariableCategory.ARB,
        minimum=10000.0, maximum=40000.0, default_value=22000.0, step=2000.0,
        unit="N/m", source="Test", physical_justification="Front ARB rate",
    ))
    ds.add_variable(DesignVariable(
        name="k_arb_r", category=VariableCategory.ARB,
        minimum=5000.0, maximum=30000.0, default_value=14000.0, step=2000.0,
        unit="N/m", source="Test", physical_justification="Rear ARB rate",
    ))

    obj = LapTimeObjective(
        track=track,
        baseline_vehicle=veh,
        design_space=ds,
        ggv_resolution=(10, 5),
    )

    cost, metrics, reports = obj.evaluate({"k_sf": 80000.0, "k_sr": 90000.0})
    assert cost > 0.0
    total_penalty = sum(r.violation_penalty for r in reports if not r.is_satisfied)
    assert cost == pytest.approx(metrics["lap_time_s"] + total_penalty)
    assert "solver_converged" in metrics
    assert metrics["solver_converged"] == 1.0

    # Check constraints: max_tire_utilization, min_dynamic_ride_height_mm, solver_converged
    report_map = {r.name: r for r in reports}
    assert "solver_converged" in report_map
    assert report_map["solver_converged"].is_satisfied


def test_multi_objective_evaluator_with_lap_sim():
    """Verify MultiObjectiveEvaluator runs full_lap_sim mode without error."""
    veh = _make_vehicle()
    track = _make_track(n_points=50, length_m=500.0)

    ds = DesignSpace("TestSpace2", "Test design space for MultiObjectiveEvaluator")
    ds.add_variable(DesignVariable(
        name="k_sf", category=VariableCategory.SPRING,
        minimum=50000.0, maximum=100000.0, default_value=75000.0, step=5000.0,
        unit="N/m", source="Test", physical_justification="Front spring rate",
    ))

    evaluator = MultiObjectiveEvaluator(
        design_space=ds,
        constraint_manager=ConstraintManager(),
        objectives=[OptimizationObjective("lap_time", ObjectiveType.LAP_TIME)],
        simulation_model="full_lap_sim",
        track=track,
        baseline_vehicle=veh,
    )

    metrics, constraints, payload = evaluator.evaluate_physical_candidate({"k_sf": 75000.0})
    assert "lap_time_s" in metrics
    assert metrics["lap_time_s"] > 0
    assert "lap_sim_result" in payload
    assert payload["lap_sim_result"].total_time == metrics["lap_time_s"]


# =============================================================================
# 5. Backend API Endpoints: /lapsim/ggv, /lapsim/sweep, /lapsim/correlate
# =============================================================================

def test_api_ggv_surface_endpoint():
    """Verify GET /lapsim/ggv returns 3D surface matrices and ay_frac."""
    response = client.get("/lapsim/ggv?mass=800.0&aero_cl=2.0&aero_cd=0.9&n_speeds=15")
    assert response.status_code == 200, response.text
    data = response.json()

    assert "speeds_ms" in data
    assert "ay_frac" in data
    assert "ax_accel_surface" in data
    assert "ax_brake_surface" in data
    assert data["ggv_type"] == "INTERPOLATED_PRE_COMPUTED"
    assert len(data["speeds_ms"]) == 15
    assert len(data["ax_accel_surface"]) == 15


def test_api_sweep_endpoint():
    """Verify POST /lapsim/sweep returns full sweep analysis with gradients."""
    N = 80
    distances = np.linspace(0, 800, N).tolist()
    curvatures = (0.01 * np.sin(np.linspace(0, np.pi, N))).tolist()

    payload = {
        "distances": distances,
        "curvatures": curvatures,
        "parameter": "mass",
        "values": [750.0, 790.0, 830.0],
        "baseline_value": 790.0,
        "vehicle": {"mass": 790.0, "aero_cl": 1.8},
        "ggv_resolution": [10, 7],
    }

    response = client.post("/lapsim/sweep", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["parameter"] == "mass"
    assert "lap_times_s" in data
    assert len(data["lap_times_s"]) == 3
    assert "sensitivities_s_per_unit" in data
    assert len(data["sensitivities_s_per_unit"]) == 3
    assert data["deltas_s"][1] == 0.0


def test_api_correlate_endpoint():
    """Verify POST /lapsim/correlate accepts telemetry and returns validation report."""
    N = 60
    distances = np.linspace(0, 600, N).tolist()
    speeds = (40.0 + 10.0 * np.sin(np.linspace(0, 2 * np.pi, N))).tolist()
    lat_g = (1.5 * np.cos(np.linspace(0, 2 * np.pi, N))).tolist()

    payload = {
        "sim_result": {
            "distances": distances,
            "speeds": speeds,
            "lateral_g": lat_g,
            "longitudinal_g": [0.0] * N,
        },
        "telemetry": {
            "distance": distances,
            "speed": speeds,
            "lateral_g": lat_g,
        },
        "distance_step_m": 10.0,
        "session_id": "test_correlate_01",
    }

    response = client.post("/lapsim/correlate", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["session_id"] == "test_correlate_01"
    assert "channels" in data
    assert "speed" in data["channels"]
    assert data["channels"]["speed"]["rmse"] == pytest.approx(0.0, abs=1e-3)
    assert data["overall_fit_pct"] >= 99.0
    assert "model_disclaimer" in data
