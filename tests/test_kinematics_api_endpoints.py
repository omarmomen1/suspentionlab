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
    Wave 8: /solve reports requested_backend, active_backend, fallback_reason,
    solver_version and geometry_hash.
    Never shows C++ branding when the fallback answered.
    """
    payload = {
        "hardpoints": DEFAULT_HARDPOINTS,
        "z_min_mm": -25.0,
        "z_max_mm": 25.0,
        "n_steps": 11,
        "backend": "auto",
    }
    resp = await authenticated_client.post("/api/v1/kinematics/solve", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "requested_backend" in data
    assert "active_backend" in data
    assert "fallback_reason" in data
    assert "solver_version" in data
    assert "geometry_hash" in data
    assert len(data["geometry_hash"]) > 0

    from suspensionlab.physics import kinematics as py_kin
    if not py_kin._HAVE_CPP:
        assert data["active_backend"] == "python_reference"
        assert data["fallback_reason"] == "cpp_extension_not_loaded"
        assert "c++" not in data["active_backend"].lower()
    else:
        assert data["active_backend"] == "cpp"
        assert data["fallback_reason"] is None

    # Test explicit C++ request in non-strict mode
    payload_cpp = dict(payload, backend="cpp", strict_mode=False)
    resp_cpp = await authenticated_client.post("/api/v1/kinematics/solve", json=payload_cpp)
    assert resp_cpp.status_code == 200, resp_cpp.text
    data_cpp = resp_cpp.json()
    assert data_cpp["requested_backend"] == "cpp"
    if not py_kin._HAVE_CPP:
        assert data_cpp["active_backend"] == "python_reference"
        assert data_cpp["fallback_reason"] == "cpp_extension_not_loaded"
    else:
        assert data_cpp["active_backend"] == "cpp"
        assert data_cpp["fallback_reason"] is None


@pytest.mark.asyncio
async def test_nonconverged_sweep_steps_are_counted_not_hidden(authenticated_client):
    """
    Wave 8: Non-converged sweep steps must be counted and not hidden from the API response.
    The response maintains the full n_steps length, marks failed steps as False in `converged`,
    sets `all_converged` to False, and counts the non-converged steps in `nonconverged_steps`
    and `convergence_summary`.
    """
    import copy
    divergent_hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    # Modify upper wishbone outer balljoint so linkage locks before +/-150mm
    divergent_hp["UWO"] = [-19.0, 450.0, 360.0]

    payload = {
        "hardpoints": divergent_hp,
        "z_min_mm": -150.0,
        "z_max_mm": 150.0,
        "n_steps": 15,
        "backend": "python",
    }
    resp = await authenticated_client.post("/api/v1/kinematics/solve", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Steps must not be dropped/hidden: arrays preserve full step count
    assert len(data["wheel_travel_mm"]) == 15
    assert len(data["camber_deg"]) == 15
    assert len(data["converged"]) == 15

    # Some steps failed to converge
    n_failed = sum(1 for c in data["converged"] if not c)
    assert n_failed > 0, "Expected at least one nonconverged step for extreme geometry"
    assert data["all_converged"] is False
    assert data["nonconverged_steps"] == n_failed
    assert data["nonconverged_count"] == n_failed
    assert str(n_failed) in data["convergence_summary"]
    assert "failed" in data["convergence_summary"].lower()


@pytest.mark.asyncio
async def test_kinematics_scope_notes_in_solve_and_export(authenticated_client):
    """
    Wave 8: Rigid-body and Corner-model scope notes in solve and CSV/JSON exports.
    """
    payload = {
        "hardpoints": DEFAULT_HARDPOINTS,
        "z_min_mm": -20.0,
        "z_max_mm": 20.0,
        "n_steps": 5,
    }
    # Solve response
    resp = await authenticated_client.post("/api/v1/kinematics/solve", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "rigid_body_scope_note" in data
    assert "Rigid-body kinematics. Bushing compliance" in data["rigid_body_scope_note"]
    assert "corner_model_scope_note" in data
    assert "Single-corner sweep; roll centre from a 2-D front-view" in data["corner_model_scope_note"]

    # CSV Export
    csv_resp = await authenticated_client.post(
        "/api/v1/kinematics/export/csv",
        json={"hardpoints": DEFAULT_HARDPOINTS, "format": "csv"},
    )
    assert csv_resp.status_code == 200
    csv_text = csv_resp.text
    assert "Single-corner sweep; roll centre from a 2-D front-view construction" in csv_text
    assert "Left/right interaction and steering-rack compliance are not modeled" in csv_text

    # JSON Export
    json_resp = await authenticated_client.post(
        "/api/v1/kinematics/export/json",
        json={"hardpoints": DEFAULT_HARDPOINTS, "format": "json"},
    )
    assert json_resp.status_code == 200
    json_data = json_resp.json()
    scope_note_found = (
        "Single-corner sweep; roll centre from a 2-D front-view construction" in json_data.get("scope_note", "")
        or "Single-corner sweep; roll centre from a 2-D front-view construction" in json_data.get("metadata", {}).get("scope_note", "")
    )
    assert scope_note_found
