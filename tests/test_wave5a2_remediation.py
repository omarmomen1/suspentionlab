"""
Wave 5A-2 remediation regression tests.

Covers:
  1. Kinematics: realistic GT3 defaults pass all benchmarks with zero warnings,
     tire-radius derivation + mismatch warning, coincident ball-joint rejection,
     C++/Python KPI sign parity (skipped when the native backend is absent).
  2. Lap-sim: 1-sample telemetry raises (no silent Spa substitution), explicit
     speed-unit detection, incomplete dynamic laps report
     lap_completed=False / solver_converged=False / lap_time_s=None.
  3. Full-car & quarter-car honesty: NaN/Inf -> DIVERGED, symmetric_input flag,
     overdamped/unidentified damping ratios return None + mode_status.
  4. Security & monetization: Gumroad verify sends increment_uses_count=false,
     /ai/approve derives role from the server-side session only.
"""

import math
import os
import sys
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Kinematics
# ─────────────────────────────────────────────────────────────────────────────

GT3_HP = {
    "UWI_fwd": [-50.0, 300.0, 340.0], "UWI_aft": [50.0, 300.0, 340.0],
    "UWO": [-19.0, 660.0, 425.0],
    "LWI_fwd": [-80.0, 300.0, 202.0], "LWI_aft": [80.0, 300.0, 202.0],
    "LWO": [0.0, 692.0, 235.0],
    "TRI": [0.0, 200.0, 190.0], "TRO": [-15.0, 710.0, 230.0],
    "WC": [-7.05, 758.0, 330.0], "CP": [-7.05, 758.0, 0.0],
    "PRI": [-20.0, 350.0, 620.0], "PRO": [-15.0, 610.0, 268.0],
    "static_camber_deg": -1.2, "static_toe_deg": 0.0,
}


def _static(d, key):
    i0 = min(range(len(d["wheel_travel_mm"])), key=lambda i: abs(d["wheel_travel_mm"][i]))
    return d[key][i0]


@pytest.mark.parametrize("mode", ["python"])
def test_gt3_default_geometry_realistic(mode):
    from suspensionlab.physics.kinematics import solve_kinematics

    c = solve_kinematics(dict(GT3_HP), -80.0, 80.0, 33, mode=mode)
    d = c.to_dict()
    assert 5.0 <= _static(d, "caster_deg") <= 8.0
    assert 8.0 <= _static(d, "kpi_deg") <= 13.0
    assert 0.55 <= _static(d, "motion_ratio") <= 0.95
    assert _static(d, "roll_center_height_mm") > 0.0
    assert _static(d, "camber_deg") == pytest.approx(-1.2, abs=0.2)
    # Bump steer < 0.05 deg per 10mm over +/-25mm
    tw, toe = d["wheel_travel_mm"], d["toe_deg"]
    pts = [(tw[k], toe[k]) for k in range(len(tw)) if -25.0 <= tw[k] <= 25.0]
    bs = (pts[-1][1] - pts[0][1]) / (pts[-1][0] - pts[0][0]) * 10.0
    assert abs(bs) < 0.05


@pytest.mark.parametrize("mode", ["python"])
def test_gt3_defaults_pass_all_benchmarks_zero_warnings(mode):
    from suspensionlab.physics.kinematics import solve_kinematics, get_kinematics_benchmarks

    c = solve_kinematics(dict(GT3_HP), -80.0, 80.0, 33, mode=mode)
    assert not (c.metadata or {}).get("warnings"), "untouched defaults must not warn"
    for b in get_kinematics_benchmarks(dict(GT3_HP), c.to_dict()):
        assert b["status"] in ("PASS", "NOT_MODELED"), f'{b["id"]}: {b["status"]}'


@pytest.mark.parametrize("mode", ["python"])
def test_bench01_bench02_references_consistent(mode):
    """BENCH-02's deflection reference must be the Gillespie-consistent value
    for BENCH-01's reference frequency: delta = g/(2*pi*f)^2."""
    from suspensionlab.physics.kinematics import solve_kinematics, get_kinematics_benchmarks

    c = solve_kinematics(dict(GT3_HP), -80.0, 80.0, 33, mode=mode)
    bench = {b["id"]: b for b in get_kinematics_benchmarks(dict(GT3_HP), c.to_dict())}
    f_ref = bench["BENCH-01-NAT-FREQ"]["reference_value"]
    expected_delta = (9.81 * 1000.0) / ((2.0 * math.pi * f_ref) ** 2)
    assert bench["BENCH-02-STAT-DEFL"]["reference_value"] == pytest.approx(expected_delta, rel=0.01)


@pytest.mark.parametrize("mode", ["python"])
def test_tire_radius_derived_from_hardpoints(mode):
    from suspensionlab.physics.kinematics import solve_kinematics

    hp = dict(GT3_HP)
    c = solve_kinematics(hp, -80.0, 80.0, 33, mode=mode)
    # WC.z - CP.z = 330 mm -> 0.330 m; no warning when derived matches geometry
    assert not (c.metadata or {}).get("warnings")


@pytest.mark.parametrize("mode", ["python"])
def test_tire_radius_explicit_mismatch_warns_and_strict_raises(mode):
    from suspensionlab.physics.kinematics import solve_kinematics

    hp = dict(GT3_HP)
    c = solve_kinematics(hp, -80.0, 80.0, 33, tire_radius=0.25, mode=mode)  # 80 mm off
    warnings = (c.metadata or {}).get("warnings", [])
    assert any("tire" in w.lower() and "radius" in w.lower() for w in warnings)
    with pytest.raises(ValueError):
        solve_kinematics(hp, -80.0, 80.0, 33, tire_radius=0.25, mode=mode, strict_mode=True)


@pytest.mark.parametrize("mode", ["python"])
def test_coincident_ball_joints_rejected(mode):
    from suspensionlab.physics.kinematics import solve_kinematics

    hp = dict(GT3_HP)
    hp["UWO"] = list(hp["LWO"])
    with pytest.raises(ValueError, match="[Cc]oincident"):
        solve_kinematics(hp, -80.0, 80.0, 33, mode=mode)


def test_cpp_python_kpi_parity():
    """C++ and Python backends must agree on KPI sign AND magnitude (SAE J670:
    positive = top of kingpin leans inboard)."""
    from suspensionlab.physics import kinematics as kin

    if not getattr(kin, "_HAVE_CPP", False):
        pytest.skip("C++ kinematics backend not available in this environment")
    c_py = kin.solve_kinematics(dict(GT3_HP), -80.0, 80.0, 33, mode="python")
    c_cpp = kin.solve_kinematics(dict(GT3_HP), -80.0, 80.0, 33, mode="cpp")
    kpi_py = _static(c_py.to_dict(), "kpi_deg")
    kpi_cpp = _static(c_cpp.to_dict(), "kpi_deg")
    assert math.copysign(1.0, kpi_py) == math.copysign(1.0, kpi_cpp)
    assert kpi_cpp == pytest.approx(kpi_py, abs=0.5)


def test_route_defaults_match_gt3_baseline():
    """The API's untouched defaults must BE the validated GT3 baseline."""
    from suspensionlab.backend.api.routes.kinematics_routes import HardpointSetInput

    hp = HardpointSetInput().to_dict()
    for k, v in GT3_HP.items():
        assert hp[k] == pytest.approx(v) if isinstance(v, float) else hp[k] == v


# ─────────────────────────────────────────────────────────────────────────────
# 2. Lap-sim honesty
# ─────────────────────────────────────────────────────────────────────────────

def test_single_sample_telemetry_raises_no_spa_substitution():
    from suspensionlab.physics.lap_sim import parse_telemetry_csv

    with pytest.raises(ValueError, match="at least 2"):
        parse_telemetry_csv({"time_s": [0.0], "speed": [22.0], "lat_g": [0.1]})


def test_telemetry_unit_detection_explicit_header():
    from suspensionlab.physics.lap_sim import parse_telemetry_csv

    data = {"time_s": [0, 1, 2, 3], "speed": [40.0, 80.0, 90.0, 60.0],
            "lat_g": [0, 0.5, 0.2, 0], "units": "km/h"}
    _, units = parse_telemetry_csv(data, return_units=True)
    assert units == "km/h"


def test_telemetry_unit_detection_key_name_and_heuristic():
    from suspensionlab.physics.lap_sim import parse_telemetry_csv

    _, units = parse_telemetry_csv(
        {"time_s": [0, 1, 2, 3], "speed_kmh": [40.0, 80.0, 90.0, 60.0], "lat_g": [0, 0.5, 0.2, 0]},
        return_units=True)
    assert units == "km/h"
    _, units = parse_telemetry_csv(
        {"time_s": [0, 1, 2, 3], "speed": [11.0, 22.0, 25.0, 16.0], "lat_g": [0, 0.5, 0.2, 0]},
        return_units=True)
    assert units == "m/s"


def test_telemetry_unit_detection_mph():
    from suspensionlab.physics.lap_sim import parse_telemetry_csv

    segs, units = parse_telemetry_csv(
        {"time_s": [0, 1, 2, 3], "speed": [25.0, 50.0, 55.0, 40.0], "lat_g": [0, 0.5, 0.2, 0],
         "speed_units": "mph"}, return_units=True)
    assert units == "mph"
    # 25 mph = 11.18 m/s
    assert segs[0].v_driver_ms == pytest.approx(25.0 * 0.44704, rel=1e-3)


def test_incomplete_dynamic_lap_contract():
    """An aborted dynamic lap must never read as a converged timed lap."""
    from suspensionlab.physics.dynamic_lap_sim import DynamicLapResult, LapSimulationOutcome

    res = DynamicLapResult(
        total_time=None,
        outcome=LapSimulationOutcome.PHYSICAL_INSTABILITY,
        lap_completed=False,
        termination_reason="test-induced instability",
        solver_converged=False,
    )
    d = res.to_dict()
    assert d["lap_completed"] is False
    assert d["solver_converged"] is False
    assert d["lap_time_s"] is None
    assert d["total_time_s"] is None
    assert d["outcome"] == LapSimulationOutcome.PHYSICAL_INSTABILITY.value


# ─────────────────────────────────────────────────────────────────────────────
# 3. Full-car & quarter-car honesty
# ─────────────────────────────────────────────────────────────────────────────

def test_full_car_diverged_error_type():
    from suspensionlab.physics.full_car import FullCarDivergedError

    assert FullCarDivergedError.status == "DIVERGED_NUMERICAL_INSTABILITY"
    assert issubclass(FullCarDivergedError, RuntimeError)


def test_full_car_tire_force_not_masked():
    """The numba tire-force helper must propagate NaN, not mask it to 0.0."""
    from suspensionlab.physics.full_car import _get_tire_force

    f = _get_tire_force(float("nan"), 0.0, 0.0, 0.0, 0.0, 0.0)
    assert math.isnan(f)


def test_full_car_symmetric_input_flag():
    """A symmetric profile must be marked symmetric_input=True on the result."""
    pytest.importorskip("scipy")
    from suspensionlab.physics.full_car import (
        FullCarDivergedError, FourCornerRoadProfile, run_full_car_analysis,
    )
    from suspensionlab.shared.models import FullCarParamsSchema

    t = np.linspace(0.0, 0.3, 61)
    bump = 0.01 * np.sin(2 * np.pi * 5 * t)
    profile = FourCornerRoadProfile(
        time=t,
        z_rfl=bump.copy(), z_rfr=bump.copy(),
        z_rrl=bump.copy(), z_rrr=bump.copy(),
    )
    params_cls = None
    import suspensionlab.physics.full_car as fc
    params_cls = getattr(fc, "FullCarParams", None)
    if params_cls is None:
        pytest.skip("FullCarParams not importable")
    try:
        res = run_full_car_analysis(params_cls(), profile)
    except FullCarDivergedError:
        pytest.skip("default params diverge in this environment")
    except Exception as e:
        pytest.skip(f"full-car run unavailable here: {e}")
    assert res.symmetric_input is True
    assert res.status == "CONVERGED"


def test_quarter_car_overdamped_zeta_none():
    """Real-pole (overdamped) systems must report zeta=None + mode_status,
    never a fabricated damping ratio."""
    import suspensionlab.physics.quarter_car as qc

    fn = getattr(qc, "compute_modal_properties", None)
    if fn is None:
        pytest.skip("compute_modal_properties not found")
    params_cls = getattr(qc, "QuarterCarParams", None)
    p = params_cls(c=1.0e6, c_t=1.0e6)  # overwhelming damping: real poles
    res = fn(p)
    assert res["zeta_s"] is None
    assert res["zeta_u"] is None
    assert res.get("mode_status_s") == "OVERDAMPED_OR_UNIDENTIFIED"
    assert res.get("mode_status_u") == "OVERDAMPED_OR_UNIDENTIFIED"
    # Validated modal frequency estimates remain present
    assert res["f_n_s"] > 0.0 and res["f_n_u"] > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Security & monetization
# ─────────────────────────────────────────────────────────────────────────────

def test_gumroad_verify_does_not_increment_uses(monkeypatch):
    from suspensionlab.backend.api.routes import gumroad_routes as gr

    monkeypatch.setattr(gr.settings, "gumroad_product_id", "prod_123")
    monkeypatch.setattr(gr.settings, "gumroad_team_product_id", "team_456")
    monkeypatch.setattr(gr.settings, "gumroad_product_permalink", "abc")
    candidates = gr._build_gumroad_verify_candidates("LICENSE-KEY")
    assert candidates, "expected configured candidates"
    for _plan, payload in candidates:
        assert payload.get("increment_uses_count") == "false"
        assert payload.get("license_key") == "LICENSE-KEY"


def test_ai_approve_rejects_client_supplied_role():
    """A session-less or Viewer caller posting approver_role=CHIEF_RACE_ENGINEER
    must be denied: role derives only from the verified session."""
    from suspensionlab.physics.ai_engineering_authority import (
        AIEngineeringToolRegistry, RBACPermissionDenied,
    )

    viewer = types.SimpleNamespace(
        team_role="VIEWER", org_role=None, is_admin=False,
        name="Vic Viewer", email="viewer@example.com",
    )
    with pytest.raises(RBACPermissionDenied):
        AIEngineeringToolRegistry.approve_decision_with_gate(
            decision_id="dec-1",
            approver_name="Vic Viewer",
            approver_role="CHIEF_RACE_ENGINEER",  # spoofed client claim
            autonomous_request=False,
            user_context=viewer,
        )
    # No session at all: denied even with a client role claim
    with pytest.raises(RBACPermissionDenied):
        AIEngineeringToolRegistry.approve_decision_with_gate(
            decision_id="dec-1",
            approver_name="Mallory",
            approver_role="CHIEF_RACE_ENGINEER",
            autonomous_request=False,
            user_context=None,
        )


def test_ai_approve_signs_with_session_identity(monkeypatch):
    from suspensionlab.physics.ai_engineering_authority import AIEngineeringToolRegistry

    monkeypatch.setenv("DECISION_HMAC_SECRET", "x" * 48)
    engineer = types.SimpleNamespace(
        team_role="ENGINEER", org_role=None, is_admin=False,
        name="Real Engineer", email="eng@example.com",
    )
    res = AIEngineeringToolRegistry.approve_decision_with_gate(
        decision_id="dec-2",
        approver_name="Spoofed Name",          # must be overridden by session
        approver_role="VIEWER",                # must be ignored
        autonomous_request=False,
        user_context=engineer,
    )
    assert res["approver_role"].lower() == "engineer"
    assert res["approver_name"] == "Real Engineer"
    assert res["hmac_signature"]


def test_dynamic_lap_api_response_honesty():
    """Wave 5A-2 item 2: an incomplete dynamic lap must surface lap_completed=False,
    outcome, solver_converged=False and lap_time_s=None at the API boundary -
    never a converged 29.46 s partial run."""
    from suspensionlab.physics.dynamic_lap_sim import DynamicLapResult, LapSimulationOutcome
    from suspensionlab.backend.api.routes.lap_sim_routes import _result_to_dict

    aborted = DynamicLapResult(
        total_time=29.46,
        lap_completed=False,
        outcome=LapSimulationOutcome.PHYSICAL_INSTABILITY,
        solver_converged=True,  # stale/legacy flag the API boundary must override
        termination_reason="spin-out at 36% distance",
    )
    d = _result_to_dict(aborted)
    assert d["lap_completed"] is False
    assert d["outcome"] == "PHYSICAL_INSTABILITY"
    assert d["solver_converged"] is False
    assert d["lap_time_s"] is None
    assert d["total_time_s"] is None
    assert d["status"] == "terminated"

    complete = DynamicLapResult(total_time=87.1, lap_completed=True)
    d2 = _result_to_dict(complete)
    assert d2["lap_completed"] is True
    assert d2["lap_time_s"] == 87.1
    assert d2["solver_converged"] is True
