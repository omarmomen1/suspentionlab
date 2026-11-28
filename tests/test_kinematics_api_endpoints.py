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


@pytest.mark.asyncio
async def test_solve_response_reports_active_backend_and_fallback_reason(authenticated_client):
    """
    Wave 8: /solve must always report requested_backend, active_backend,
    fallback_reason, solver_version, and geometry_hash.
    When C++ is requested but not deployed on the host, active_backend must report
    'python' (or reference) with an explicit fallback_reason, and never claim C++.
    Scope notes must be included in the response.
    """
    payload = {
        "hardpoints": DEFAULT_HARDPOINTS,
        "z_min_mm": -30.0,
        "z_max_mm": 30.0,
        "n_steps": 15,
        "backend": "cpp",
        "strict_mode": False,
    }
    response = await authenticated_client.post("/api/v1/kinematics/solve", json=payload)
    assert response.status_code == 200, f"Solve failed: {response.text}"
    data = response.json()

    # Requested C++, but on this host C++ module is unavailable -> fallback to python
    assert data["requested_backend"] == "cpp"
    assert data["active_backend"] in ["python", "python_reference"]
    assert data["fallback_reason"] is not None
    assert len(data["fallback_reason"]) > 0
    assert "cpp" not in data["active_backend"].lower()

    # Provenance fields
    assert "solver_version" in data and len(data["solver_version"]) > 0
    assert "geometry_hash" in data and len(data["geometry_hash"]) > 0

    # Scope notes
    assert data["rigid_body_scope_note"] == (
        "Rigid-body kinematics. Bushing compliance (elastokinematics) is not included in these curves."
    )
    assert data["corner_model_scope_note"] == (
        "Single-corner sweep; roll centre from a 2-D front-view construction. Left/right interaction and steering-rack compliance are not modeled."
    )
    assert data["scope_note"] == data["corner_model_scope_note"]


@pytest.mark.asyncio
async def test_nonconverged_sweep_steps_are_counted_not_hidden(authenticated_client):
    """
    Wave 8: When geometry causes continuation solver steps to diverge,
    non-converged steps must be counted (nonconverged_steps, nonconverged_count)
    and preserved in the arrays with converged=False, rather than silently dropped.
    """
    bad_hp = dict(DEFAULT_HARDPOINTS)
    # Move UWO inboard and down to stress the linkage into non-convergence at travel extremes
    bad_hp["UWO"] = [-19.0, 450.0, 360.0]

    payload = {
        "hardpoints": bad_hp,
        "z_min_mm": -150.0,
        "z_max_mm": 150.0,
        "n_steps": 15,
        "backend": "python",
        "strict_mode": False,
    }
    response = await authenticated_client.post("/api/v1/kinematics/solve", json=payload)
    assert response.status_code == 200, f"Solve failed: {response.text}"
    data = response.json()

    # Non-converged steps must be counted
    assert "nonconverged_steps" in data
    assert "nonconverged_count" in data
    assert data["nonconverged_steps"] > 0
    assert data["nonconverged_count"] == data["nonconverged_steps"]
    assert data["all_converged"] is False

    # Steps are not hidden or dropped
    assert len(data["wheel_travel_mm"]) == 15
    assert len(data["converged"]) == 15
    n_false = sum(1 for c in data["converged"] if not c)
    assert n_false == data["nonconverged_steps"]


@pytest.mark.asyncio
async def test_kinematics_scope_notes_in_solve_and_export(authenticated_client):
    """
    Wave 8: Model scope notes must be present in both CSV and JSON export headers.
    """
    # 1. Export CSV via /export
    export_csv_payload = {
        "hardpoints": DEFAULT_HARDPOINTS,
        "format": "csv",
        "z_min_mm": -30.0,
        "z_max_mm": 30.0,
        "n_steps": 11,
    }
    res_csv = await authenticated_client.post("/api/v1/kinematics/export", json=export_csv_payload)
    assert res_csv.status_code == 200
    csv_text = res_csv.text
    assert "Single-corner sweep; roll centre from a 2-D front-view construction. Left/right interaction and steering-rack compliance are not modeled." in csv_text
    assert "Rigid-body kinematics. Bushing compliance (elastokinematics) is not included in these curves." in csv_text

    # 2. Export CSV via /export/csv
    res_csv2 = await authenticated_client.post("/api/v1/kinematics/export/csv", json=export_csv_payload)
    assert res_csv2.status_code == 200
    assert "Single-corner sweep; roll centre from a 2-D front-view construction. Left/right interaction and steering-rack compliance are not modeled." in res_csv2.text

    # 3. Export JSON via /export/json
    export_json_payload = {
        "hardpoints": DEFAULT_HARDPOINTS,
        "format": "json",
        "z_min_mm": -30.0,
        "z_max_mm": 30.0,
        "n_steps": 11,
    }
    res_json = await authenticated_client.post("/api/v1/kinematics/export/json", json=export_json_payload)
    assert res_json.status_code == 200
    json_data = res_json.json()
    assert "Single-corner sweep; roll centre from a 2-D front-view construction. Left/right interaction and steering-rack compliance are not modeled." in (
        json_data.get("scope_note") or json_data.get("metadata", {}).get("scope_note", "")
    )

