"""
tests/test_adams_exporter.py
============================
Tests for MSC ADAMS CAE Interoperability Export Pipelines.
Validates syntax, parameter propagation, and endpoint integrity for:
- MSC ADAMS Solver Datasets (.adm)
- MSC ADAMS View Command Files (.cmd)
- MSC ADAMS View Python Automation Scripts (.py)
"""

import pytest
from fastapi.testclient import TestClient

from suspensionlab.physics.quarter_car import QuarterCarParams
from suspensionlab.physics.full_car import FullCarParams
from suspensionlab.backend.services.cae_exporter import (
    export_quarter_car_to_adams,
    export_quarter_car_to_adams_view_cmd,
    export_quarter_car_to_adams_view_python,
    export_full_car_to_adams,
    export_quarter_car_to_matlab,
)
from suspensionlab.backend.api.main import app


def test_adams_solver_dataset_syntax_and_parameters():
    p = QuarterCarParams(m_s=320.0, m_u=38.0, k_s=28000.0, c=2200.0, k_t=210000.0, MR=0.9)
    adm = export_quarter_car_to_adams(p)

    # Verify standard ADAMS dataset sections
    assert "UNITS/ FORCE = NEWTON, MASS = KILOGRAM, LENGTH = METER, TIME = SECOND" in adm
    assert "PART/1, GROUND" in adm
    assert f"PART/2, MASS = {p.m_s:.3f}" in adm
    assert f"PART/3, MASS = {p.m_u:.3f}" in adm

    # Markers & Joints
    assert "MARKER/201, PART = 2" in adm
    assert "MARKER/301, PART = 3" in adm
    assert "JOINT/1, TRANSLATIONAL" in adm
    assert "JOINT/2, TRANSLATIONAL" in adm

    # Forces with pre-calculated wheel rates
    assert f"STIFFNESS_COEFFICIENT = {p.k_w:.2f}" in adm
    assert f"DAMPING_COEFFICIENT = {p.c_w:.2f}" in adm
    assert f"STIFFNESS_COEFFICIENT = {p.k_t:.2f}" in adm

    # Requests
    assert "REQUEST/1, DISPLACEMENT" in adm
    assert "REQUEST/3, ACCELERATION" in adm
    assert "REQUEST/5, FORCE" in adm
    assert "OUTPUT/ REQSAVE, GRF" in adm
    assert "END" in adm


def test_adams_view_command_deck():
    p = QuarterCarParams(m_s=300.0, m_u=35.0, k_s=25000.0, c=2050.0, k_t=200000.0, MR=0.85)
    cmd = export_quarter_car_to_adams_view_cmd(p)

    assert "model create model_name = Quarter_Car_Rig" in cmd
    assert "defaults units" in cmd
    assert f"part create rigid_body name_and_position_spec = .Quarter_Car_Rig.sprung_mass &" in cmd
    assert f"mass = {p.m_s:.3f}" in cmd
    assert f"part create rigid_body name_and_position_spec = .Quarter_Car_Rig.unsprung_mass &" in cmd
    assert "constraint create joint translational" in cmd
    assert "force create element spring_damper" in cmd
    assert f"stiffness = {p.k_w:.2f}" in cmd
    assert f"damping = {p.c_w:.2f}" in cmd
    assert "measure create function" in cmd
    assert "simulation single_run transient" in cmd


def test_adams_view_python_script():
    p = QuarterCarParams(m_s=300.0, m_u=35.0, k_s=25000.0, c=2050.0, k_t=200000.0)
    py_script = export_quarter_car_to_adams_view_python(p)

    assert "import adams" in py_script
    assert "models.create(name=\"Quarter_Car_Rig\")" in py_script
    assert f"mass={p.m_s:.3f}" in py_script
    assert "parts.create_rigid_body" in py_script
    assert "joints.create_translational" in py_script
    assert "forces.create_spring_damper" in py_script

    # Validate Python script compiles with compile()
    compile(py_script, "<adams_script>", "exec")


def test_adams_full_car_7dof_dataset():
    fc = FullCarParams(
        m_s=1200.0,
        I_x=350.0,
        I_y=1200.0,
        m_uf=45.0,
        m_ur=40.0,
        k_sf=35000.0,
        k_sr=40000.0,
        c_f=2200.0,
        c_r=2500.0,
        k_arb_f=1200.0,
        k_arb_r=900.0,
        k_tf=220000.0,
        k_tr=220000.0,
        L=2.7,
        a=1.2,
        b=1.5,
        tw_f=1.6,
        tw_r=1.55,
        speed_mps=20.0,
    )
    adm = export_full_car_to_adams(fc)

    assert "Full_Car_7DOF_Rig" in adm
    assert "PART/1, GROUND" in adm
    assert f"PART/2, MASS = {fc.m_s:.2f}" in adm
    assert f"PART/3, MASS = {fc.m_uf:.2f}" in adm
    assert f"PART/4, MASS = {fc.m_uf:.2f}" in adm
    assert f"PART/5, MASS = {fc.m_ur:.2f}" in adm
    assert f"PART/6, MASS = {fc.m_ur:.2f}" in adm
    assert f"STIFFNESS_COEFFICIENT = {fc.k_sf:.2f}" in adm
    assert f"STIFFNESS_COEFFICIENT = {fc.k_sr:.2f}" in adm
    assert "REQUEST/1, DISPLACEMENT" in adm
    assert "REQUEST/6, FORCE" in adm


from suspensionlab.backend.security.auth import require_plan, UserContext, verify_api_key
from suspensionlab.shared.models import PlanTier


def test_export_api_endpoints_enterprise_access():
    client = TestClient(app)
    # Use FastAPI dependency override for enterprise tier requirement and api key
    enterprise_user = UserContext(
        user_id="test-enterprise-eng",
        plan=PlanTier.ENTERPRISE,
        email="engineer@enterprise-oem.com",
        name="Lead CAE Engineer",
        onboarding_complete=True,
        is_admin=True,
        permissions=["export:cae", "simulation:run"],
    )
    app.dependency_overrides[verify_api_key] = lambda: enterprise_user
    try:
        payload = {
            "m_s": 1200.0, "m_uf": 45.0, "m_ur": 40.0,
            "I_x": 350.0, "I_y": 1200.0,
            "L": 2.7,
            "a": 1.2, "b": 1.5, "tw_f": 1.6, "tw_r": 1.55,
            "k_sf": 35000.0, "k_sr": 40000.0,
            "c_f": 2200.0, "c_r": 2500.0,
            "k_arb_f": 1200.0, "k_arb_r": 900.0,
            "k_tf": 220000.0, "k_tr": 220000.0,
        }

        # 1. Test /export/adams (adm format)
        resp_adm = client.post("/export/adams?export_format=adm", json=payload)
        assert resp_adm.status_code == 200
        assert "Full_Car_7DOF_Rig" in resp_adm.text

        # 2. Test /export/adams (cmd format)
        resp_cmd = client.post("/export/adams?export_format=cmd", json=payload)
        assert resp_cmd.status_code == 200
        assert "model create model_name = Quarter_Car_Rig" in resp_cmd.text

        # 3. Test /export/adams (py format)
        resp_py = client.post("/export/adams?export_format=py", json=payload)
        assert resp_py.status_code == 200
        assert "import adams" in resp_py.text

        # 4. Test /export/simulink
        resp_sim = client.post("/export/simulink", json=payload)
        assert resp_sim.status_code == 200
        assert "sys = ss(A, B, C, D);" in resp_sim.text

        # 5. Test /export/fmu
        resp_fmu = client.post("/export/fmu")
        assert resp_fmu.status_code == 200
        assert len(resp_fmu.content) > 10000  # Valid ZIP archive
        assert resp_fmu.content[:4] == b"PK\x03\x04"  # ZIP magic header
    finally:
        app.dependency_overrides.pop(verify_api_key, None)


def test_export_adams_geometric_inconsistency_handled_with_422():
    client = TestClient(app)
    enterprise_user = UserContext(
        user_id="test-enterprise-eng",
        plan=PlanTier.ENTERPRISE,
        email="engineer@enterprise-oem.com",
        name="Lead CAE Engineer",
        onboarding_complete=True,
        is_admin=True,
        permissions=["export:cae", "simulation:run"],
    )
    app.dependency_overrides[verify_api_key] = lambda: enterprise_user
    try:
        # L=2.6 != a + b (1.2 + 1.5 = 2.7)
        bad_geometry_payload = {
            "m_s": 1200.0, "m_uf": 45.0, "m_ur": 40.0,
            "I_x": 350.0, "I_y": 1200.0,
            "L": 2.6,
            "a": 1.2, "b": 1.5, "tw_f": 1.6, "tw_r": 1.55,
            "k_sf": 35000.0, "k_sr": 40000.0,
            "c_f": 2200.0, "c_r": 2500.0,
            "k_arb_f": 1200.0, "k_arb_r": 900.0,
            "k_tf": 220000.0, "k_tr": 220000.0,
        }
        resp = client.post("/export/adams?export_format=adm", json=bad_geometry_payload)
        assert resp.status_code == 422
        assert "geometrically inconsistent" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(verify_api_key, None)

