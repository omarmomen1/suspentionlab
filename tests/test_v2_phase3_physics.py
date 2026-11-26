"""V2 Phase 3 behavioral physics tests: rack sweep, vertical curvature, Why Chain.

Every assertion reads numbers produced by the real solvers. No source-string greps.
"""
from __future__ import annotations

import asyncio
import dataclasses
import math

import numpy as np
import pytest

from suspensionlab.physics import kinematics as K
from suspensionlab.physics import lap_sim as L
from suspensionlab.physics import track_geometry as TG
from suspensionlab.physics.why_chain import NOT_MODELED, compute_why_chain

HP = K.DEFAULT_HARDPOINTS


# ── (a) steering rack ────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def grid():
    return K.solve_steer_grid(HP, wheelbase_mm=2650.0)


def test_zero_rack_matches_1d_bump_sweep_identically(grid):
    ref = K.solve_kinematics(HP, z_min_mm=-50.0, z_max_mm=50.0, n_steps=11, mode="python")
    i0 = grid["rack_travel_mm"].index(0.0)
    mr = grid["motion_ratio"][i0]
    cam = grid["camber_deg"][i0]
    assert len(mr) == len(ref.points) == 11
    for j, p in enumerate(ref.points):
        assert grid["bump_mm"][j] == pytest.approx(p.wheel_travel_mm, abs=1e-9)
        assert mr[j] == pytest.approx(p.motion_ratio, abs=1e-6)
        assert cam[j] == pytest.approx(p.camber_deg, abs=1e-6)
        assert grid["steer_angle_deg"][i0][j] == pytest.approx(0.0, abs=1e-9)


def test_rack_travel_gives_physical_signed_steer_angle(grid):
    racks = grid["rack_travel_mm"]
    j0 = grid["bump_mm"].index(0.0)
    steer = [grid["steer_angle_deg"][i][j0] for i in range(len(racks))]
    # +5 mm is past the reachable range for the default geometry at this bump: solver reports
    # non-convergence and the cell is None (never a made-up number).
    assert steer[-1] is None and not grid["converged"][-1][j0]
    steer = steer[:-1]
    assert all(math.isfinite(s) for s in steer)
    assert all(b > a for a, b in zip(steer, steer[1:]))   # monotonic in rack travel
    assert steer[0] < 0 < steer[-1]                       # signed about zero
    assert abs(steer[0] + steer[-1]) < 0.6 * abs(steer[0])  # roughly odd about zero rack
    # steering sets camber change at the same time (kingpin inclination + caster), so it is non-zero
    dcam = [grid["d_camber_deg"][i][j0] for i in range(len(racks))]
    assert max(abs(c) for c in dcam if c is not None) > 1e-3


def test_mr_surface_is_non_trivial_in_both_axes(grid):
    mr = np.array([[np.nan if v is None else v for v in row] for row in grid["motion_ratio"]])
    assert mr.shape == (len(grid["rack_travel_mm"]), len(grid["bump_mm"]))
    assert np.isfinite(mr).sum() > 0.8 * mr.size
    along_bump = np.nanmax(np.nanmax(mr, axis=1) - np.nanmin(mr, axis=1))
    along_steer = np.nanmax(np.nanmax(mr, axis=0) - np.nanmin(mr, axis=0))
    assert along_bump > 1e-3
    assert along_steer > 1e-4  # MR genuinely depends on steer, not a flat copy of the 1D curve


def test_clearances_not_modeled_and_ackermann_gate(grid):
    assert grid["clearances"]["status"] == "NOT_MODELED"
    assert grid["ackermann"]["status"] == "COMPUTED" and grid["ackermann"]["wheelbase_mm"] == 2650.0
    no_wb = K.solve_steer_grid(HP, n_bump=3, n_steer=3)
    assert no_wb["ackermann"]["status"] == "NOT_MODELED"


def test_unreachable_rack_cells_are_none_not_invented():
    g = K.solve_steer_grid(HP, n_bump=3, rack_min_mm=-15.0, rack_max_mm=15.0, n_steer=3)
    flat = [v for row in g["motion_ratio"] for v in row]
    conv = [c for row in g["converged"] for c in row]
    assert any(not c for c in conv)  # the +15 mm cells really are unreachable
    for row_v, row_c in zip(g["motion_ratio"], g["converged"]):
        for v, c in zip(row_v, row_c):
            if not c:
                assert v is None


def test_route_model_defaults_solve():
    from suspensionlab.backend.api.routes import kinematics_routes as kr
    out = asyncio.run(kr.steer_grid(kr.SteerGridRequest(n_bump=3, n_steer=3), user=None))
    assert out["clearances"]["status"] == "NOT_MODELED"
    i0 = out["rack_travel_mm"].index(0.0)
    assert out["motion_ratio"][i0][1] is not None and math.isfinite(out["motion_ratio"][i0][1])


# ── (b) vertical curvature ───────────────────────────────────────────────────
def _track_with_kappa(kz: float):
    segs = L._get_builtin_track_flat("fsae_endurance")
    return [dataclasses.replace(s, kappa_z=kz, dz_ds=0.0) for s in segs]


@pytest.fixture(scope="module")
def runs():
    out = {}
    for name, kz in (("flat", 0.0), ("valley", 1.0e-3), ("crest", -1.0e-3)):
        out[name] = L.simulate_lap({}, track=_track_with_kappa(kz))
    return out


def test_valley_load_is_exactly_m_v2_kappa(runs):
    m = L.LapSimVehicleParams().mass_kg
    for name, kz in (("valley", 1.0e-3), ("crest", -1.0e-3)):
        tr = runs[name].trace
        v = np.array(tr["speed_kmh"]) / 3.6
        dfz = np.array(tr["vertical_load_delta_n"])
        np.testing.assert_allclose(dfz, m * v ** 2 * kz, rtol=2e-3, atol=0.2)
        np.testing.assert_allclose(np.array(tr["vertical_g"]), dfz / (m * 9.81), rtol=2e-3, atol=1e-4)
    assert np.all(np.array(runs["flat"].trace["vertical_load_delta_n"]) == 0.0)


def test_valley_compresses_more_and_crest_unloads(runs):
    cf = np.array(runs["flat"].trace["compression_mm"])
    cv = np.array(runs["valley"].trace["compression_mm"])
    cc = np.array(runs["crest"].trace["compression_mm"])
    assert cv.mean() > cf.mean() and cv.max() > cf.max()
    assert cc.mean() < cf.mean()
    assert np.array(runs["valley"].trace["vertical_g"]).min() > 0
    assert np.array(runs["crest"].trace["vertical_g"]).max() < 0


def test_trace_exposes_z_vertical_g_and_compression(runs):
    for k in ("z_m", "vertical_g", "compression_mm"):
        assert k in runs["flat"].trace and len(runs["flat"].trace[k]) == len(runs["flat"].trace["s_m"])


def test_spa_elevation_is_opt_in_documented_and_finite():
    flat = L.get_builtin_track("spa")
    assert all(s.elevation == 0.0 and s.kappa_z == 0.0 and s.elevation_source == "none" for s in flat)
    spa = L.get_builtin_track("spa", with_elevation=True)
    z = np.array([s.z_m for s in spa])
    assert np.isfinite(z).all() and np.isfinite([s.kappa_z for s in spa]).all()
    assert 90.0 < z.max() - z.min() < 110.0  # range of the stations themselves (373..470 m)
    assert min(s for _, s in TG.SPA_ELEVATION_STATIONS_M) == z.min() or abs(z.min() - 373.0) < 3.0
    assert "racspa.be" in TG.SPA_ELEVATION_SOURCE
    assert all(s.elevation_source != "none" for s in spa)
    # profile is closed: end matches start
    assert abs(z[0] - z[-1]) < 1.0
    for name in ("monza", "silverstone"):
        assert all(s.elevation == 0.0 and s.elevation_source == "none" for s in L.get_builtin_track(name, with_elevation=True))


def test_elevation_profile_curvature_matches_finite_difference():
    s_st = np.array([p[0] for p in TG.SPA_ELEVATION_STATIONS_M])
    z_st = np.array([p[1] for p in TG.SPA_ELEVATION_STATIONS_M])
    se = np.arange(100.0, 6900.0, 1.0)
    z, d1, kz = TG.elevation_profile_from_stations(se, s_st, z_st)
    fd_slope = np.gradient(z, se)
    np.testing.assert_allclose(d1[2:-2], fd_slope[2:-2], atol=2e-4)
    fd_k = np.gradient(fd_slope, se) / (1 + fd_slope ** 2) ** 1.5
    np.testing.assert_allclose(kz[5:-5], fd_k[5:-5], atol=2e-5)


# ── (c) Why Chain ────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def chain_arb():
    return compute_why_chain({"k_arb_front_n_m": 45000.0}, {"k_arb_front_n_m": 60000.0}, track="fsae_endurance")


def _by(chain, name):
    return next(l for l in chain["chain"] if l["link"] == name)


def test_chain_links_have_value_unit_and_source(chain_arb):
    assert chain_arb["chain_complete"] is True
    names = [l["link"] for l in chain_arb["chain"]]
    assert names == ["input_delta", "roll_gradient_lltd", "camber_in_roll", "pacejka_peak_grip",
                     "qss_apex_speed", "corner_time"]
    def nums(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from nums(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            yield o
    for l in chain_arb["chain"]:
        assert l["status"] == "OK" and l["unit"] and l["solver_source"]
        assert all(math.isfinite(x) for x in nums(l["value"]))
        assert "prose" not in l and "explanation" not in l


def test_chain_is_directionally_consistent(chain_arb):
    rg = _by(chain_arb, "roll_gradient_lltd")["value"]
    assert rg["roll_gradient_deg_per_g"]["delta"] < 0          # stiffer front ARB, less roll
    assert rg["lltd_front"]["delta"] > 0                      # more front load transfer share
    cam = _by(chain_arb, "camber_in_roll")["value"]["ground_camber_deg"]
    assert cam["delta"] != 0 and (cam["b"] - cam["a"]) * rg["roll_gradient_deg_per_g"]["delta"] > 0  # less roll, less roll-camber
    # roll gradient and LLTD deltas reproduce lap_sim's own numbers
    va, vb = L.LapSimVehicleParams(k_arb_front_n_m=45000.0), L.LapSimVehicleParams(k_arb_front_n_m=60000.0)
    assert rg["lltd_front"]["a"] == pytest.approx(va.lltd()) and rg["lltd_front"]["b"] == pytest.approx(vb.lltd())
    ct = _by(chain_arb, "corner_time")["value"]
    assert ct["corner_time_s"]["delta"] == pytest.approx(
        ct["corner_time_s"]["b"] - ct["corner_time_s"]["a"])
    ap = _by(chain_arb, "qss_apex_speed")["value"]["apex_speed_ms"]
    # apex speed and corner time move in opposite directions
    assert ap["delta"] * ct["corner_time_s"]["delta"] <= 0


def test_unmodeled_levers_stop_chain_cleanly():
    for lever, code in (("static_rh_front_mm", "LEVER_HAS_NO_PATH_TO_ROLL_STIFFNESS"),
                        ("damper_clicks_front", "LEVER_NOT_IN_QSS_MODEL"),
                        ("tire_pressure_bar", "LEVER_NOT_IN_QSS_MODEL")):
        r = compute_why_chain({lever: 1.0}, {lever: 2.0}, track="fsae_endurance")
        assert r["chain_complete"] is False
        assert r["chain"][0]["status"] == "OK"
        for l in r["chain"][1:]:
            assert l["status"] == NOT_MODELED and l["value"] is None and l["reason_code"] == code
        assert len(r["chain"]) == 6


def test_chain_rejects_identical_or_non_finite_setups():
    with pytest.raises(ValueError):
        compute_why_chain({"k_arb_front_n_m": 1.0}, {"k_arb_front_n_m": 1.0})
    with pytest.raises(ValueError):
        compute_why_chain({"k_arb_front_n_m": 1.0}, {"k_arb_front_n_m": float("nan")})


# ── API boundaries ───────────────────────────────────────────────────────────
def test_lap_sim_route_returns_vertical_channels():
    from suspensionlab.backend.api.routes import lap_sim_routes as lr
    out = asyncio.run(lr.simulate_lap_endpoint({"track": "fsae_endurance"}, user=None, _limiter=None))
    trace = out.get("trace", out)
    flat = {}
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                flat[k] = v
                walk(v)
    walk(out)
    for k in ("z_m", "vertical_g", "compression_mm"):
        assert k in flat and len(flat[k]) == len(flat["distances"]) and len(flat[k]) > 100


def test_why_chain_route_maps_bad_input_to_422():
    from fastapi import HTTPException
    from suspensionlab.backend.api.routes import lap_sim_routes as lr
    body = lr.WhyChainRequest(setup_a={"k_arb_front_n_m": 1.0}, setup_b={"k_arb_front_n_m": 1.0})
    with pytest.raises(HTTPException) as ei:
        asyncio.run(lr.why_chain_endpoint(body, user=None, _limiter=None))
    assert ei.value.status_code == 422
    body = lr.WhyChainRequest(setup_a={"damper_clicks_front": 3.0}, setup_b={"damper_clicks_front": 5.0}, track="fsae_endurance")
    out = asyncio.run(lr.why_chain_endpoint(body, user=None, _limiter=None))
    assert out["chain_complete"] is False
