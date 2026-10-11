"""
tests/test_kinematics_api_endpoints.py
======================================
Integration tests for FastAPI Kinematics REST API endpoints:
- POST /api/v1/kinematics/solve
- POST /api/v1/kinematics/solve-point
- POST /api/v1/kinematics/validate
- GET  /api/v1/kinematics/benchmarks
- GET  /api/v1/kinematics/default
- GET  /api/v1/kinematics/info
"""

import pytest
from suspensionlab.physics.kinematics import DEFAULT_HARDPOINTS


@pytest.mark.asyncio
async def test_kinematics_solve_endpoint(authenticated_client):
    payload = {
        "hardpoints": DEFAULT_HARDPOINTS,
        "z_min_mm": -40.0,
        "z_max_mm": 40.0,
        "n_steps": 17,
    }
    response = await authenticated_client.post("/api/v1/kinematics/solve", json=payload)
    assert response.status_code == 200, f"Error {response.status_code}: {response.text}"
    data = response.json()

    # Verify all 9 KPI arrays are present and matched in length
    kpi_fields = [
        "camber_deg", "toe_deg", "caster_deg", "kpi_deg",
        "track_change_mm", "wheelbase_change_mm", "roll_center_height_mm",
        "motion_ratio", "scrub_radius_mm"
    ]
    for field in kpi_fields:
        assert field in data, f"Missing KPI field: {field}"
        assert len(data[field]) == 17

    # Verify Instant Center channels
    for ic_field in ["ic_y_mm", "ic_z_mm", "ic_sv_x_mm", "ic_sv_z_mm"]:
        assert ic_field in data, f"Missing IC field: {ic_field}"
        assert len(data[ic_field]) == 17

    # Verify 3D geometry steps
    assert "geometry_steps" in data
    assert len(data["geometry_steps"]) == 17
    step0 = data["geometry_steps"][0]
    for node in ["uwo", "lwo", "tro", "wc", "cp", "ic_fv", "rc", "steering_axis_ground"]:
        assert node in step0, f"Missing node '{node}' in geometry step 0"
        assert len(step0[node]) == 3

    # Verify validation report & solver provenance
    assert "validation_report" in data
    assert data["validation_report"]["is_valid"] is True
    assert "backend" in data
    assert "solver_version" in data


@pytest.mark.asyncio
async def test_kinematics_solve_point_endpoint(authenticated_client):
    payload = {
        "hardpoints": DEFAULT_HARDPOINTS,
        "dz_mm": 15.0,
        "roll_deg": 0.5,
        "steer_deg": 2.0,
    }
    response = await authenticated_client.post("/api/v1/kinematics/solve-point", json=payload)
    assert response.status_code == 200, f"Error {response.status_code}: {response.text}"
    data = response.json()

    assert abs(data["wheel_travel_mm"] - 15.0) < 1e-3
    assert "camber_deg" in data
    assert "toe_deg" in data
    assert "roll_center_height_mm" in data
    assert "scrub_radius_mm" in data

    # Verify 3D nodal geometry
    assert "geometry" in data
    geom = data["geometry"]
    assert "uwo" in geom
    assert "lwo" in geom
    assert "wc" in geom
    assert "cp" in geom
    assert "ic_fv" in geom
    assert "rc" in geom


@pytest.mark.asyncio
async def test_kinematics_validate_endpoint_valid(authenticated_client):
    payload = {
        "topology": "double_wishbone",
        "hardpoints": DEFAULT_HARDPOINTS,
        "tire_radius_m": 0.33,
    }
    response = await authenticated_client.post("/api/v1/kinematics/validate", json=payload)
    assert response.status_code == 200, f"Error {response.status_code}: {response.text}"
    data = response.json()

    assert data["is_valid"] is True
    assert data["status"] == "VALID"
    assert len(data["errors"]) == 0


@pytest.mark.asyncio
async def test_kinematics_validate_endpoint_inadmissible(authenticated_client):
    bad_hp = dict(DEFAULT_HARDPOINTS)
    # Force singular/inadmissible condition: upper ball joint lower than lower ball joint
    bad_hp["UWO"] = [0.0, 650.0, 100.0]
    bad_hp["LWO"] = [0.0, 720.0, 200.0]

    payload = {
        "topology": "double_wishbone",
        "hardpoints": bad_hp,
        "tire_radius_m": 0.33,
    }
    response = await authenticated_client.post("/api/v1/kinematics/validate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["is_valid"] is False
    assert data["status"] == "OUT_OF_BOUNDS"
    assert len(data["remediation"]) > 0

    first_rem = data["remediation"][0]
    for required_field in [
        "issue", "reason", "affected_parameter", "safe_range",
        "what_engineer_should_change", "severity"
    ]:
        assert required_field in first_rem


@pytest.mark.asyncio
async def test_kinematics_benchmarks_endpoint(authenticated_client):
    response = await authenticated_client.get("/api/v1/kinematics/benchmarks")
    assert response.status_code == 200
    data = response.json()

    for preset_id in ["formula_sae", "gt3_touring", "lmp_prototype"]:
        assert preset_id in data
        assert "hardpoints" in data[preset_id]
        assert "wheel_travel_range" in data[preset_id]


@pytest.mark.asyncio
async def test_kinematics_defaults_and_info_endpoints(authenticated_client):
    res_def = await authenticated_client.get("/api/v1/kinematics/default")
    assert res_def.status_code == 200
    def_data = res_def.json()
    assert "hardpoints" in def_data
    assert "coordinate_system" in def_data

    res_info = await authenticated_client.get("/api/v1/kinematics/info")
    assert res_info.status_code == 200
    info_data = res_info.json()
    assert "backend" in info_data
    assert "cpp_loaded" in info_data
