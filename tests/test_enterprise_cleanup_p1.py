from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from suspensionlab.backend.api.main import app
from suspensionlab.backend.api.routes.decision_loop_routes import (
    ApproveLoopDecisionRequest,
    CreateLoopQuestionRequest,
)
from suspensionlab.backend.api.routes.setup_engineering_routes import (
    ApprovalRequest,
    EngineeringDecisionRequest,
)
from suspensionlab.backend.services.cae_exporter import (
    QuarterCarParams,
    export_quarter_car_to_matlab,
)
from suspensionlab.backend.services.experiment_service import ExperimentService, compare_metrics

ROOT = Path(__file__).resolve().parents[1]


def test_compare_setups_identical_returns_no_change():
    params = {"m_s": 300.0, "m_u": 40.0, "k_s": 25000.0, "c": 1800.0, "k_t": 180000.0}
    res = ExperimentService.compare_setups(params, params)
    assert res["verdict"] == "NO_CHANGE"
    assert res["confidence"] == 0.0
    assert res["what_improved"] == []
    assert res["what_got_worse"] == []
    assert "identical" in res["verdict_summary"].lower()


def test_compare_metrics_degraded_does_not_emit_positive_reason():
    baseline = {
        "rms_body_accel": 0.40,
        "peak_susp_travel_mm": 30.0,
        "tire_load_variation_n": 500.0,
        "settling_time_s": 1.2,
    }
    candidate = {
        "rms_body_accel": 0.65,
        "peak_susp_travel_mm": 45.0,
        "tire_load_variation_n": 700.0,
        "settling_time_s": 2.0,
    }
    improved, worse = compare_metrics(baseline, candidate)
    assert improved == []
    accel_delta = next(d for d in worse if d["key"] == "rms_body_accel")
    assert "reduced" not in accel_delta["reason"].lower()


def test_matlab_export_notes_coupled_eigenvalues():
    script = export_quarter_car_to_matlab(
        QuarterCarParams(m_s=300.0, m_u=40.0, k_s=25000.0, c=1800.0, k_t=180000.0)
    )
    assert "coupled 4-state modal frequency f_n_s" in script


def test_schema_defaults_do_not_expose_fabricated_identities():
    assert ApproveLoopDecisionRequest().approver_name == ""
    assert CreateLoopQuestionRequest().question_text == ""
    assert EngineeringDecisionRequest().author == ""
    assert ApprovalRequest().approver_name == ""


def test_studio_p1_experiment_durability_nvh_contracts():
    exp_src = (ROOT / "frontend" / "app" / "experiment" / "page.tsx").read_text(encoding="utf-8")
    assert "What happens if I increase front spring rate (k_s) by 10%?" in exp_src

    dur_src = (ROOT / "frontend" / "app" / "durability" / "page.tsx").read_text(encoding="utf-8")
    assert "SCHEMATIC / PLACEHOLDER CONSTANTS" in dur_src
    assert "Schematic Proxy D" in dur_src

    nvh_src = (ROOT / "frontend" / "app" / "nvh" / "page.tsx").read_text(encoding="utf-8")
    assert "A-Weighted Transfer Gain (dB)" in nvh_src
    assert "Acoustic Noise (dBA)" not in nvh_src


@pytest.mark.asyncio
async def test_yaw_transient_infeasible_warning_and_handling_assumptions_warning():
    from suspensionlab.backend.security.auth import verify_api_key
    from tests.test_wave5a2_remediation import _session_user

    eng = _session_user("ENGINEER")
    app.dependency_overrides[verify_api_key] = lambda: eng
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yaw_resp = await client.post(
                "/api/v1/intelligence/yaw/transient",
                json={"params": {"mass": 1200.0}, "v_ms": 60.0, "radius_m": 60.0, "t_total_s": 1.0},
            )
            assert yaw_resp.status_code == 200
            yaw_data = yaw_resp.json()
            assert yaw_data["infeasible"] is True
            assert yaw_data["ay_required_g"] > yaw_data["mu_limit_g"]
            assert "INFEASIBLE" in yaw_data["feasibility_warning"]

            yaw_ok = await client.post(
                "/api/v1/intelligence/yaw/transient",
                json={"params": {"mass": 1200.0}},
            )
            assert yaw_ok.status_code == 200
            assert yaw_ok.json()["infeasible"] is False

            hand_resp = await client.post(
                "/api/v1/handling/diagram",
                json={
                    "params": {
                        "m": 1200.0,
                        "h_cg": 0.4,
                        "roll_dist": 0.55,
                        "K_spring_f": 30000.0,
                        "K_spring_r": 30000.0,
                        "K_arb_f": 20000.0,
                        "K_arb_r": 10000.0,
                        "tw_f": 1.6,
                        "tw_r": 1.6,
                    }
                },
            )
            assert hand_resp.status_code == 200
            warnings = hand_resp.json().get("assumptions_warnings", [])
            assert len(warnings) >= 1
            assert any("roll center" in w.lower() for w in warnings)
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
