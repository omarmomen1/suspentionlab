"""
tests/test_wave5a_remediation.py
================================
Remediation Wave 5A regression tests.

Covers:
  1. Damper LUT linearisation energy-equivalence fix (closed-loop integral bug)
  2. Pacejka MF 5.2 PKY1 sign handling for standard .tir uploads
  3. Yaw dynamics oversteer JSON serialization & speed terminology
  4. Active (Skyhook) vs Passive time-axis alignment
  5. Half-Car "bump" single-bump road profile acceptance
  6. /simulate/sweep vectorized performance & fidelity
  7. /evidence-graph/traverse empty-graph 200 on missing root
  8. CAE compare_external_vs_native numeric contract fields
  9. /telemetry/events honest detection & G-G point cloud
 10. /scim/v2/status honest configuration status
 11. /setup-engineering/manifest structured empty baseline
 12. /parameter-trust structured UNASSESSED baseline (no raw 404)
 13. /ai/chat deterministic fallback (never unhandled 500)
"""

import json
import math
import os
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Damper LUT linearisation
# ─────────────────────────────────────────────────────────────────────────────

def _linear_damper(c: float):
    from suspensionlab.physics.damper_model import BiDirectionalDamper, DamperCurve
    vc = np.linspace(0.01, 0.5, 32)
    vr = np.linspace(-0.5, -0.01, 32)
    return BiDirectionalDamper(
        compression=DamperCurve(vc, c * vc, direction="compression"),
        rebound=DamperCurve(vr, c * vr, direction="rebound"),
        name="linear",
    )


def test_damper_linearise_linear_damper_returns_exact_c():
    """(a) Linear damper F = c*v must return c_eff == c (was collapsing to ~0
    because trapezoid(F, v) over a closed loop is identically zero)."""
    c = 2000.0
    damper = _linear_damper(c)
    c_eff, _ = damper.linearise(v_rms=0.05)
    assert c_eff == pytest.approx(c, rel=0.01)
    assert c_eff > 100.0  # the bug produced ~0


def test_damper_linearise_bilinear_asymmetric_returns_mean():
    """(b) Bilinear asymmetric damper (c_c, c_r) returns (c_c + c_r) / 2."""
    c_c, c_r = 1500.0, 3500.0
    from suspensionlab.physics.damper_model import BiDirectionalDamper, DamperCurve
    vc = np.linspace(0.01, 0.5, 32)
    vr = np.linspace(-0.5, -0.01, 32)
    damper = BiDirectionalDamper(
        compression=DamperCurve(vc, c_c * vc, direction="compression"),
        rebound=DamperCurve(vr, c_r * vr, direction="rebound"),
        name="bilinear",
    )
    c_eff, _ = damper.linearise(v_rms=0.05)
    assert c_eff == pytest.approx((c_c + c_r) / 2.0, rel=0.01)


def test_quarter_car_asymmetric_lut_finite_bode_peak_tx():
    """(c) Quarter-Car with an asymmetric damper LUT produces a finite,
    realistic Bode Peak TX (production measured the buggy 687.24).

    Bode Peak TX is a frequency-domain quantity, so this exercises
    compute_frequency_response + linearise_damper_from_params directly.
    (The time-domain LUT path is covered by a separate performance note.)"""
    from suspensionlab.physics.quarter_car import QuarterCarParams, compute_frequency_response
    from suspensionlab.physics.damper_model import linearise_damper_from_params

    vc = np.linspace(0.01, 1.0, 20)
    vr = np.linspace(-1.0, -0.01, 20)
    p = QuarterCarParams(
        damper_curve_v_comp=vc.tolist(),
        damper_curve_f_comp=(1500.0 * vc).tolist(),
        damper_curve_v_reb=vr.tolist(),
        damper_curve_f_reb=(3500.0 * vr).tolist(),
    )
    c_eff, _ = linearise_damper_from_params(p, v_rms=0.05)
    assert c_eff > 100.0  # the bug collapsed this to ~0

    freq = compute_frequency_response(p)
    peak = freq["peak_transmissibility"]
    assert math.isfinite(peak)
    assert 1.0 <= peak < 100.0  # measured 1.87 after the fix; was 687.24


# ─────────────────────────────────────────────────────────────────────────────
# 2. Pacejka PKY1 sign handling
# ─────────────────────────────────────────────────────────────────────────────

_STANDARD_TIR = """
[MDI_HEADER]
FILE_TYPE = 'tir'
[VERTICAL]
FNOMIN = 4000.0
[LATERAL_COEFFICIENTS]
PCY1 = 1.3
PDY1 = 1.0
PDY2 = -0.1
PKY1 = -15.0
PKY2 = 1.5
PKY3 = 0.0
"""


def test_pky1_negative_tir_produces_positive_cornering_stiffness():
    """Standard PAC2002 .tir with PKY1 = -15.0 must yield positive cornering
    stiffness (Fy same sign as alpha), not flipped-sign grip collapse."""
    from suspensionlab.physics.tir_parser import parse_tir_file
    from suspensionlab.physics.magic_formula import calc_tire_forces

    coeffs = parse_tir_file(_STANDARD_TIR)
    assert coeffs.pKy1 == pytest.approx(-15.0)

    _, fy_pos = calc_tire_forces(4000.0, 0.02, 0.0, 0.0, coeffs)
    _, fy_neg = calc_tire_forces(4000.0, -0.02, 0.0, 0.0, coeffs)
    assert fy_pos > 0.0
    assert fy_neg < 0.0

    alphas = np.linspace(0.0, 0.3, 60)
    peak_fy = max(calc_tire_forces(4000.0, float(a), 0.0, 0.0, coeffs)[1] for a in alphas)
    peak_g = peak_fy / 4000.0
    assert peak_g > 0.9  # ~1.10 G class grip, not the 0.033 G collapse


# ─────────────────────────────────────────────────────────────────────────────
# 3. Yaw oversteer JSON safety
# ─────────────────────────────────────────────────────────────────────────────

def test_yaw_oversteer_metrics_are_json_safe():
    """Oversteer (C_af=160k, C_ar=100k): characteristic speed null, critical
    speed finite, neutral_steer_speed sanitized, json.dumps never fails."""
    from suspensionlab.physics.yaw_dynamics import BicycleModelParams, compute_stability_metrics

    p = BicycleModelParams(C_alpha_front=160_000.0, C_alpha_rear=100_000.0)
    metrics = compute_stability_metrics(p, 30.0)

    assert metrics["handling_class"] == "oversteer"
    assert metrics["characteristic_speed_kmh"] is None
    assert metrics["neutral_steer_speed_kmh"] is None
    assert metrics["critical_speed_kmh"] is not None
    assert math.isfinite(metrics["critical_speed_kmh"])
    json.dumps(metrics)  # must not raise (strict JSON)


def _make_app_with_router(router, dependency_overrides=None):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    for dep, override in (dependency_overrides or {}).items():
        app.dependency_overrides[dep] = override
    return app


def _fake_user():
    user = SimpleNamespace(
        user_id="wave5a-test",
        team_id=None,
        organization_id=None,
        plan="PRO",
        team_role="engineer",
    )
    user.can = lambda perm: True
    return user


def test_yaw_route_oversteer_returns_200_valid_json():
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.routes.vehicle_intelligence_routes import router
    from suspensionlab.backend.security.auth import verify_api_key

    app = _make_app_with_router(router, {verify_api_key: lambda: _fake_user()})
    client = TestClient(app)
    r = client.post("/api/v1/intelligence/yaw", json={
        "params": {"C_alpha_front": 160000.0, "C_alpha_rear": 100000.0},
        "v_ms": 30.0,
    })
    assert r.status_code == 200, r.text
    payload = r.json()  # raises if body contained inf/NaN literals
    assert payload["mmm"]["neutral_steer_speed_ms"] is None
    assert payload["mmm"]["critical_speed_ms"] is not None
    assert math.isfinite(payload["mmm"]["critical_speed_ms"])
    assert payload["mmm"]["characteristic_speed_ms"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Active vs passive time-axis alignment
# ─────────────────────────────────────────────────────────────────────────────

def test_active_passive_identical_time_grid():
    """Skyhook active and passive baseline must share the identical t_eval grid
    and both sample the step bump onset at t = 0.5 s at the same index."""
    from suspensionlab.physics.active_quarter_car import ActiveQuarterCarParams, simulate_active_time_response
    from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, simulate_time_response

    shared_dt = 0.002
    profile = RoadProfile(profile_type="step", amplitude=0.1, duration=3.0)
    p_active = ActiveQuarterCarParams()
    p_passive = QuarterCarParams(
        m_s=p_active.m_s, m_u=p_active.m_u, k_s=p_active.k_s,
        c=1500.0, k_t=p_active.k_t, MR=p_active.MR,
    )

    active_res = simulate_active_time_response(p_active, profile, shared_dt)
    passive_res = simulate_time_response(p_passive, profile, shared_dt)

    t_a = np.asarray(active_res.time, dtype=float)
    t_p = np.asarray(passive_res["time"], dtype=float)
    assert len(t_a) == len(t_p)
    assert np.allclose(t_a, t_p, rtol=0.0, atol=1e-12)

    onset_idx = int(round(0.5 / shared_dt))
    assert abs(t_a[onset_idx] - 0.5) < 1e-9
    assert abs(t_p[onset_idx] - 0.5) < 1e-9
    # both responses carry data at the onset sample
    assert np.isfinite(active_res.susp_travel[onset_idx])
    assert np.isfinite(passive_res["susp_travel"][onset_idx])


# ─────────────────────────────────────────────────────────────────────────────
# 5. Half-car "bump" acceptance
# ─────────────────────────────────────────────────────────────────────────────

def test_road_profile_schema_accepts_bump_alias():
    from suspensionlab.shared.models import RoadProfileSchema
    assert RoadProfileSchema(profile_type="bump").profile_type == "bump"
    assert RoadProfileSchema(profile_type="single_bump").profile_type == "bump"


def test_half_car_single_bump_runs():
    """The /half-car Single Bump request path must succeed (was HTTP 422)."""
    from suspensionlab.physics.half_car import HalfCarParams, RoadProfile, run_half_car_analysis

    res = run_half_car_analysis(
        HalfCarParams(),
        RoadProfile(profile_type="bump", amplitude=0.05, duration=2.0),
    )
    time_arr = np.asarray(res.time, dtype=float)
    assert len(time_arr) > 100
    assert np.all(np.isfinite(time_arr))


# ─────────────────────────────────────────────────────────────────────────────
# 6. Sweep vectorization
# ─────────────────────────────────────────────────────────────────────────────

def test_sweep_10x10_under_5_seconds_and_accurate():
    """Vectorized 10x10 sweep: < 5 s and within 2% of per-point reference."""
    from suspensionlab.backend.api.routes.simulate.sweep import (
        perform_sweep_sync, _sweep_metrics_vectorized,
    )
    from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis

    t0 = time.monotonic()
    out = perform_sweep_sync({
        "grid_res": 10,
        "var_x": "Spring Rate (ks)",
        "var_y": "Damping (c)",
        "objective": "Balanced",
    })
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0, f"10x10 sweep took {elapsed:.1f}s (must be < 5 s)"
    Z = np.asarray(out["Z"], dtype=float)
    assert Z.shape == (10, 10)
    assert np.all(np.isfinite(Z))

    # Fidelity: compare vectorized metrics against the reference per-point solver
    for ks, c in [(15000.0, 1000.0), (45000.0, 4000.0), (30000.0, 2500.0)]:
        p = QuarterCarParams()
        p.k_s = ks
        p.c = c
        profile = RoadProfile(profile_type="step", amplitude=0.05)
        ref = run_quarter_car_analysis(p, profile)
        vec = _sweep_metrics_vectorized([p], profile)[0]
        for ref_val, vec_val in [
            (ref.rms_body_accel_wk, vec["rms_body_accel_wk"]),
            (ref.rms_tire_load, vec["rms_tire_load"]),
            (ref.rms_susp_travel, vec["rms_susp_travel"]),
        ]:
            assert vec_val == pytest.approx(ref_val, rel=0.02)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Evidence graph traverse: empty graph 200
# ─────────────────────────────────────────────────────────────────────────────

def test_evidence_graph_traverse_missing_root_returns_empty_200():
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.routes import evidence_graph_routes as egr
    from suspensionlab.backend.security.auth import verify_api_key
    from suspensionlab.backend.database.core import get_db_dependency
    from suspensionlab.backend.services.evidence_graph_service import EntityNotFoundError

    async def _raise_not_found(**kwargs):
        raise EntityNotFoundError("root not found")

    async def _fake_db():
        yield None

    app = _make_app_with_router(egr.router, {
        verify_api_key: lambda: _fake_user(),
        get_db_dependency: _fake_db,
    })
    client = TestClient(app)

    original = egr.EvidenceGraphService.get_subgraph
    egr.EvidenceGraphService.get_subgraph = staticmethod(_raise_not_found)
    orig_empty = egr._caller_graph_is_empty
    async def _empty(*a, **k):
        return True
    egr._caller_graph_is_empty = _empty
    try:
        r = client.get("/api/v1/evidence-graph/traverse",
                       params={"root_type": "RUN", "root_id": "RUN-BASELINE"})
    finally:
        egr.EvidenceGraphService.get_subgraph = original
        egr._caller_graph_is_empty = orig_empty

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["root"]["entity_id"] == "RUN-BASELINE"
    assert body["traversal"]["nodes_returned"] == 0


def test_evidence_graph_traverse_missing_root_nonempty_graph_returns_404():
    """Option (b): missing/cross-tenant root is 404 unless caller graph is empty."""
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.routes import evidence_graph_routes as egr
    from suspensionlab.backend.security.auth import verify_api_key
    from suspensionlab.backend.database.core import get_db_dependency
    from suspensionlab.backend.services.evidence_graph_service import EntityNotFoundError

    async def _raise_not_found(**kwargs):
        raise EntityNotFoundError("root not found")

    async def _fake_db():
        yield None

    async def _nonempty(*a, **k):
        return False

    app = _make_app_with_router(egr.router, {
        verify_api_key: lambda: _fake_user(),
        get_db_dependency: _fake_db,
    })
    client = TestClient(app)
    orig_sg, orig_e = egr.EvidenceGraphService.get_subgraph, egr._caller_graph_is_empty
    egr.EvidenceGraphService.get_subgraph = staticmethod(_raise_not_found)
    egr._caller_graph_is_empty = _nonempty
    try:
        for rid in ("RUN-BASELINE", "DEC-12"):
            r = client.get("/api/v1/evidence-graph/traverse",
                           params={"root_type": "RUN", "root_id": rid})
            assert r.status_code == 404, r.text
        # non-placeholder root is 404 even when the caller graph is empty
        async def _empty(*a, **k):
            return True
        egr._caller_graph_is_empty = _empty
        r = client.get("/api/v1/evidence-graph/traverse",
                       params={"root_type": "RUN", "root_id": "DEC-12"})
        assert r.status_code == 404, r.text
    finally:
        egr.EvidenceGraphService.get_subgraph = orig_sg
        egr._caller_graph_is_empty = orig_e


# ─────────────────────────────────────────────────────────────────────────────
# 8. CAE numeric contract
# ─────────────────────────────────────────────────────────────────────────────

def test_cae_compare_populates_numeric_contract_fields():
    from suspensionlab.backend.services.cae_integration_service import (
        CaeIntegrationService, NormalizedCaeDataset, ExternalModelIdentity,
    )

    t = np.linspace(0.0, 5.0, 501)
    ddz = 0.5 * np.sin(2 * np.pi * 1.8 * t)
    identity = ExternalModelIdentity(
        source_tool="MSC Adams",
        version="2024.1",
        solver="WSTIFF",
        artifact_hash="0" * 64,
        parameters={"m_s": 320.0, "m_u": 45.0, "k_s": 35000.0, "c": 2200.0, "k_t": 220000.0, "MR": 0.85},
        inputs={"road_profile": "sine 0.015 m @ 1.8 Hz"},
        execution_environment="External CAE Host (Linux)",
        timestamp_iso="2026-11-26T00:00:00Z",
    )
    dataset = NormalizedCaeDataset(
        identity=identity,
        time_s=t.tolist(),
        ddz_s=ddz.tolist(),
        susp_travel_mm=(10.0 * np.sin(2 * np.pi * 1.8 * t)).tolist(),
        tire_load_N=(4000.0 + 500.0 * np.sin(2 * np.pi * 1.8 * t)).tolist(),
        kpis={"duration_s": 5.0, "rms_body_accel_mps2": 0.35},
    )
    res = CaeIntegrationService.compare_external_vs_native(dataset)

    assert "time_start" in res and "time_end" in res and "dt_mean" in res
    assert res["time_start"] == pytest.approx(0.0)
    assert res["time_end"] == pytest.approx(5.0)
    assert res["dt_mean"] == pytest.approx(0.01, rel=1e-3)
    ch = res["channel_metrics"]["ddz_s"]
    assert "max_absolute_error" in ch and math.isfinite(ch["max_absolute_error"])
    assert "mean_percentage_error" in ch and math.isfinite(ch["mean_percentage_error"])


# ─────────────────────────────────────────────────────────────────────────────
# 9. Correlation events: honest detection + G-G cloud
# ─────────────────────────────────────────────────────────────────────────────

def test_correlation_events_real_detection_and_gg_points():
    """An 80-bar CSV must never produce a hardcoded 140-bar event; the G-G
    diagram receives full sampled (ay, ax) points."""
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.routes import correlation_routes as cr
    from suspensionlab.backend.security.auth import verify_api_key

    n = 2000
    t = np.linspace(0.0, 20.0, n)
    rng = np.random.default_rng(7)
    lat_g = 0.9 * np.sin(2 * np.pi * 0.2 * t) + 0.05 * rng.standard_normal(n)
    long_g = np.zeros(n)
    long_g[500:600] = -1.2  # one braking event
    brake_bar = np.zeros(n)
    brake_bar[500:600] = 80.0  # 80-bar peak, NOT 140
    speed = np.full(n, 40.0)

    telemetry = {
        "time": t.tolist(),
        "lat_g": lat_g.tolist(),
        "long_g": long_g.tolist(),
        "brake_bar": brake_bar.tolist(),
        "speed": speed.tolist(),
    }

    app = _make_app_with_router(cr.router, {verify_api_key: lambda: _fake_user()})
    client = TestClient(app)
    r = client.post("/api/v1/telemetry/events", json={"telemetry_data": telemetry})
    assert r.status_code == 200, r.text
    body = r.json()

    # Honest brake events: no pressure above the 80-bar data maximum
    for ev in body["events"]:
        peak = (ev.get("source_data") or {}).get("peak_brake_press_bar")
        if peak is not None:
            assert peak <= 80.0 + 1e-6

    # G-G cloud present and sampled from the real channels
    assert len(body["gg_points"]["lat_g"]) > 100
    assert len(body["gg_points"]["lat_g"]) == len(body["gg_points"]["long_g"])
    assert body["gg_stats"]["sample_count"] == n
    assert body["gg_stats"]["max_resultant_g"] > 0.5


# ─────────────────────────────────────────────────────────────────────────────
# 10. SCIM status
# ─────────────────────────────────────────────────────────────────────────────

def test_scim_status_returns_200_honest_disabled():
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.routes import scim_routes as sr
    from suspensionlab.backend.security.auth import verify_api_key

    app = _make_app_with_router(sr.router, {verify_api_key: lambda: _fake_user()})
    client = TestClient(app)
    r = client.get("/api/v1/scim/v2/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "enabled" in body
    assert body["enabled"] is False  # unconfigured in test environment
    assert body["user_count"] == 0 and body["group_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 11. Setup-engineering manifest baseline
# ─────────────────────────────────────────────────────────────────────────────

def test_setup_engineering_manifest_returns_structured_empty_state():
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.routes import setup_engineering_routes as ser
    from suspensionlab.backend.security.auth import verify_api_key

    app = _make_app_with_router(ser.router, {verify_api_key: lambda: _fake_user()})
    client = TestClient(app)
    r = client.get("/api/v1/setup-engineering/manifest")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "EMPTY"
    for section in ("problem", "hypothesis", "simulation", "comparison",
                    "validation", "decision", "approval", "parameter_gate"):
        assert section in body


# ─────────────────────────────────────────────────────────────────────────────
# 12. Parameter-trust UNASSESSED baseline
# ─────────────────────────────────────────────────────────────────────────────

def test_parameter_trust_missing_parameter_returns_unassessted_baseline():
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.routes import parameter_trust_routes as ptr
    from suspensionlab.backend.security.auth import verify_api_key
    from suspensionlab.backend.database.core import get_db_dependency
    from suspensionlab.backend.services.parameter_trust_service import ParameterNotFoundError

    async def _fake_db():
        yield None

    async def _raise_not_found(**kwargs):
        raise ParameterNotFoundError("no such parameter")

    app = _make_app_with_router(ptr.router, {
        verify_api_key: lambda: _fake_user(),
        get_db_dependency: _fake_db,
    })
    client = TestClient(app)

    original = ptr.ParameterTrustService.get_or_assess_parameter_trust
    ptr.ParameterTrustService.get_or_assess_parameter_trust = staticmethod(_raise_not_found)
    try:
        r = client.get("/api/v1/parameter-trust/SetupCandidate/SETUP-P3L-CAND-01/front_spring_rate")
    finally:
        ptr.ParameterTrustService.get_or_assess_parameter_trust = original

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current_trust_state"] == "UNASSESSED"
    assert body["validation_coverage"] == "NO_VALIDATION"
    assert body["supporting_evidence"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 13. AI chat deterministic fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_chat_never_unhandled_500_on_service_failure():
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.routes import ai_engineer_routes as air
    from suspensionlab.backend.security.auth import verify_api_key

    app = _make_app_with_router(air.router, {verify_api_key: lambda: _fake_user()})
    client = TestClient(app)

    class _Boom:
        @staticmethod
        def calculate_physics_diagnosis_and_setup(**kwargs):
            raise RuntimeError("simulated provider failure")

    import suspensionlab.backend.services.ai_race_engineer_service as svc_mod
    original = svc_mod.AIRaceEngineerService.calculate_physics_diagnosis_and_setup
    svc_mod.AIRaceEngineerService.calculate_physics_diagnosis_and_setup = staticmethod(
        _Boom.calculate_physics_diagnosis_and_setup
    )
    try:
        r = client.post("/api/v1/ai/chat", json={
            "problem": "a completely custom free-form prompt that breaks the pipeline",
            "params": {},
        })
    finally:
        svc_mod.AIRaceEngineerService.calculate_physics_diagnosis_and_setup = original

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulated"] is False
    assert body["confidence"] == 0.0
    assert "could not complete" in body["diagnosis"]


# ── Omar review round (2026-11-26): sweep sign fix, ai/chat root cause, CAE ingest ──

def test_sweep_tire_load_uses_rhs_sign_convention():
    """tire_load_var post-processing must use F_t = k_t*(z_r - z_u) (rhs sign),
    so the contact-loss clamp limits lift-off tension, not compression."""
    import inspect
    from suspensionlab.backend.api.routes.simulate import sweep as sweep_mod
    src = inspect.getsource(sweep_mod._sweep_metrics_vectorized)
    assert "k_t * (z_r_arr - Z_U) + c_t * (dz_r_arr - DZ_U)" in src
    assert "k_t * (Z_U - z_r_arr)" not in src


def test_reference_solver_clamps_tension_side_in_reported_metric():
    """quarter_car.py reported tire_load_var uses the -F_t convention, so the
    contact-loss clamp must be np.minimum(..., +static), not np.maximum(..., -static)."""
    import inspect
    from suspensionlab.physics import quarter_car as qc_mod
    src = inspect.getsource(qc_mod)
    assert "tire_load_var = np.minimum(tire_load_var, static_tire_load)" in src
    assert "tire_load_var = np.maximum(tire_load_var, -static_tire_load)" not in src


def test_ai_race_engineer_custom_prompts_all_intents_no_crash():
    """Root cause of live /ai/chat 500s: target_zeta was only bound in two of
    four intent branches. Every intent class must produce a real answer."""
    from suspensionlab.backend.services.ai_race_engineer_service import AIRaceEngineerService
    for prob in [
        "my car feels nervous on corner entry at spa, what should I change?",
        "the rear is loose and snaps on exit",
        "completely unrelated custom question about setup balance",
        "ride is harsh over kerbs",
    ]:
        r = AIRaceEngineerService.calculate_physics_diagnosis_and_setup(problem=prob, params={})
        assert r["diagnosis"], prob
        assert r["recommendations"] or r["best_feasible"] is not None


def test_cae_normalize_ingest_populates_time_grid_fields():
    """Normalize & Ingest must populate time_start/time_end/dt_mean like the
    compare path does."""
    from suspensionlab.backend.services.cae_integration_service import CaeIntegrationService
    csv = "time,body_accel_g,susp_travel_mm,tire_load\n0.0,0.1,1.0,3500\n0.1,0.2,1.1,3510\n0.2,0.15,1.05,3505"
    ds = CaeIntegrationService.import_and_normalize_external_run("Adams", "2024.1", "solver", {"m_s": 320.0}, csv)
    assert ds.kpis["time_start"] == 0.0
    assert ds.kpis["time_end"] == 0.2
    assert abs(ds.kpis["dt_mean"] - 0.1) < 1e-9
