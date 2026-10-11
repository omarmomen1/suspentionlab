"""
tests/test_lap_sim_routes_integration.py
========================================
Integration test suite for lap simulation API endpoints:
- POST /lapsim/run (telemetry, tire utilization, metadata)
- POST /lapsim/corners (corner detection and track zones)
- POST /lapsim/compare (setup delta causal attribution)
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from suspensionlab.backend.api.main import app
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.shared.models import PlanTier

client = TestClient(app)


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


def test_run_lap_sim_endpoint():
    """Verify POST /lapsim/run returns telemetry with tire utilization and metadata."""
    N = 100
    distances = np.linspace(0, 1000, N).tolist()
    curvatures = (0.01 * np.sin(np.linspace(0, np.pi, N))).tolist()
    
    payload = {
        "distances": distances,
        "curvatures": curvatures,
        "vehicle": {
            "mass": 780.0,
            "aero_cl": 2.0,
            "aero_cd": 0.9,
        },
    }
    
    response = client.post("/lapsim/run", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    
    assert "total_time_s" in data
    assert data["total_time_s"] > 0
    assert "telemetry" in data
    
    # Check tire utilization and available force telemetry
    telemetry = data["telemetry"]
    assert "tire_utilization_x" in telemetry
    assert "tire_utilization_y" in telemetry
    assert "tire_utilization_combined" in telemetry
    assert "ax_available_ms2" in telemetry
    assert "ay_available_ms2" in telemetry
    assert len(telemetry["tire_utilization_combined"]) == N
    
    # Check model transparency and reproducibility metadata
    assert "model_assumptions" in data
    assert "not_modeled" in data["model_assumptions"]
    assert "simulation_metadata" in data
    assert data["simulation_metadata"]["run_id"] != ""


def test_corners_endpoint():
    """Verify POST /lapsim/corners returns detected corners and zone classifications."""
    N = 200
    distances = np.linspace(0, 1500, N).tolist()
    curvatures = np.zeros(N)
    curvatures[60:120] = 0.02 * np.sin(np.pi * np.linspace(0, 1, 60))
    
    payload = {
        "distances": distances,
        "curvatures": curvatures.tolist(),
        "vehicle": {"mass": 800.0},
    }
    
    response = client.post("/lapsim/corners", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    
    assert "num_corners" in data
    assert data["num_corners"] >= 1
    assert "corners" in data
    assert len(data["corners"]) == data["num_corners"]
    assert "track_zones" in data
    assert len(data["track_zones"]) == N


def test_compare_endpoint():
    """Verify POST /lapsim/compare performs causal attribution between two setups."""
    N = 150
    distances = np.linspace(0, 1000, N).tolist()
    curvatures = (0.015 * np.sin(np.linspace(0, 2*np.pi, N))).tolist()
    
    payload = {
        "distances": distances,
        "curvatures": curvatures,
        "vehicle_a": {
            "mass": 800.0,
            "aero_cl": 1.5,
            "aero_cd": 1.0,
        },
        "vehicle_b": {
            "mass": 800.0,
            "aero_cl": 2.5,  # higher downforce
            "aero_cd": 1.0,
        },
    }
    
    response = client.post("/lapsim/compare", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    
    assert "setup_a" in data
    assert "setup_b" in data
    assert "delta_report" in data
    assert "total_delta_s" in data["delta_report"]
    # Higher downforce should yield a faster or different lap time
    assert "summary" in data["delta_report"]
    assert "model_assumptions_caveat" in data["delta_report"]


def test_run_lap_sim_high_fidelity_endpoint():
    """Verify POST /lapsim/run with HIGH_FIDELITY_LAP mode and differential configuration."""
    N = 80
    distances = np.linspace(0, 400, N).tolist()
    curvatures = np.zeros(N).tolist()

    payload = {
        "distances": distances,
        "curvatures": curvatures,
        "solver_mode": "HIGH_FIDELITY_LAP",
        "vehicle": {
            "mass": 780.0,
            "aero_cl": 2.0,
            "aero_cd": 0.9,
            "differential": {
                "diff_type": "LSD_TORQUE_BIASED",
                "bias_ratio": 3.2,
                "preload_nm": 70.0,
                "drivetrain_layout": "RWD",
            },
        },
    }

    response = client.post("/lapsim/run", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert "total_time_s" in data
    assert data["total_time_s"] > 0
    assert "telemetry" in data
    telemetry = data["telemetry"]
    assert "speeds_ms" in telemetry
    assert len(telemetry["speeds_ms"]) > 0
    assert "tire_utilization_combined" in telemetry
    assert "ax_available_ms2" in telemetry


def test_cross_validate_endpoint():
    """Verify POST /lapsim/cross_validate executes both QSS and 14-DOF passes and decomposes delta."""
    N = 60
    distances = np.linspace(0, 300, N).tolist()
    curvatures = np.zeros(N).tolist()

    payload = {
        "distances": distances,
        "curvatures": curvatures,
        "vehicle": {
            "mass": 750.0,
            "aero_cl": 2.2,
            "aero_cd": 0.85,
            "differential": {
                "diff_type": "CLUTCH_PACK",
                "preload_nm": 60.0,
            },
        },
    }

    response = client.post("/lapsim/cross_validate", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data.get("status") == "success"
    assert "qss" in data
    assert "dyn" in data
    assert "cross_validation" in data
    cv = data["cross_validation"]
    assert "lap_time_qss_s" in cv
    assert "lap_time_dyn_s" in cv
    assert "delta_s" in cv
    assert "attribution" in cv
    assert "gearshift_loss_s" in cv["attribution"]
    assert "transient_steer_yaw_lag_s" in cv["attribution"]
    assert "attribution_breakdown_pct" in cv
    assert "metrics" in cv
    assert "speed_rmse_kmh" in cv["metrics"]
    assert "validity_record" in cv


def test_maneuver_endpoints():
    """Verify POST /lapsim/maneuver handles STEP_STEER and THRESHOLD_BRAKING time-domain maneuvers."""
    # 1. Step Steer Maneuver
    payload_step = {
        "maneuver_type": "STEP_STEER",
        "initial_speed_mps": 35.0,
        "parameters": {
            "amplitude_deg": 3.0,
            "t_total": 1.5,
        },
        "vehicle": {
            "mass": 780.0,
            "differential": {
                "diff_type": "OPEN",
            },
        },
    }
    response = client.post("/lapsim/maneuver", json=payload_step)
    assert response.status_code == 200, response.text
    step_data = response.json()
    assert step_data["maneuver_type"] == "STEP_STEER"
    assert "metrics" in step_data
    assert "steady_state_yaw_rate_rads" in step_data["metrics"]
    assert "peak_yaw_rate_rads" in step_data["metrics"]
    assert "yaw_rate_overshoot_pct" in step_data["metrics"]
    assert "telemetry" in step_data
    assert len(step_data["telemetry"]["time_s"]) > 0

    # 2. Threshold Braking Maneuver
    payload_brake = {
        "maneuver_type": "THRESHOLD_BRAKING",
        "initial_speed_mps": 40.0,
        "parameters": {
            "brake_demand": 0.85,
            "t_total": 2.0,
        },
        "vehicle": {
            "mass": 780.0,
        },
    }
    response_brake = client.post("/lapsim/maneuver", json=payload_brake)
    assert response_brake.status_code == 200, response_brake.text
    brake_data = response_brake.json()
    assert brake_data["maneuver_type"] == "THRESHOLD_BRAKING"
    assert "stopping_distance_m" in brake_data["metrics"]
    assert "mean_decel_g" in brake_data["metrics"]
    assert brake_data["metrics"]["stopping_distance_m"] > 0

