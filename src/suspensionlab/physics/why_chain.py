"""Deterministic coupled QSS "Why Chain" (V2 Phase 3).

Compares Setup A against Setup B on a track corner by calling the existing solvers and
returning one causal chain. Every link carries a computed value, a unit and its solver source.
There is no generated prose: only numbers, units, source identifiers and status codes.

Chain:
  1. input_delta            lever values A and B                       (caller input)
  2. roll_gradient_lltd     roll gradient [deg/g], LLTD [-]            (LapSimVehicleParams)
  3. camber_in_roll         front outer-wheel camber at apex roll [deg] (solve_kinematics + roll)
  4. pacejka_peak_grip      front outer-tire peak |Fy| at fixed Fz [N] (magic_formula)
  5. qss_apex_speed         minimum speed in the corner window [m/s]   (simulate_lap)
  6. corner_time            time over the corner window [s]            (simulate_lap)

A lever that has no physical path into the model stops the chain at the first link it cannot
reach. That link and every later link are returned with status NOT_MODELED and no value.

Coupling between link 4 and link 5 (stated, not hidden): the QSS tire model has one mu_0 for
the whole car and no camber input. For setup B the QSS mu_0 is multiplied by
    mu_scale = 1 + weight_dist_front * (Fy_peak_B / Fy_peak_A - 1)
which is the front-axle grip ratio weighted by the static front weight share. The rear axle has
no hardpoints in this API, so its camber effect is NOT_MODELED and contributes a ratio of 1.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional

import numpy as np

from suspensionlab.physics.kinematics import DEFAULT_HARDPOINTS, solve_kinematics
from suspensionlab.physics.lap_sim import LapSimVehicleParams, simulate_lap
from suspensionlab.physics.magic_formula import TireCoeffs, calc_tire_forces

NOT_MODELED = "NOT_MODELED"
OK = "OK"
G = 9.81

# Levers that enter roll stiffness in LapSimVehicleParams.roll_stiffness_front/rear().
ROLL_LEVERS = {
    "k_arb_front_n_m": "front ARB wheel rate [N/m]",
    "k_arb_rear_n_m": "rear ARB wheel rate [N/m]",
    "k_spring_front_n_m": "front spring rate [N/m]",
    "k_spring_rear_n_m": "rear spring rate [N/m]",
}
# Levers that exist in the lap-sim but do not enter roll stiffness, camber or grip.
# static ride height only sets the ride-height/bottoming channels in simulate_lap.
NO_GRIP_PATH_LEVERS = {
    "static_rh_front_mm": "static ride height only feeds ride-height and bottoming channels",
    "static_rh_rear_mm": "static ride height only feeds ride-height and bottoming channels",
}


def _link(name: str, status: str, **kw) -> Dict[str, Any]:
    d: Dict[str, Any] = {"link": name, "status": status}
    d.update(kw)
    return d


def _not_modeled(name: str, reason_code: str, detail_key: str = "") -> Dict[str, Any]:
    return _link(name, NOT_MODELED, value=None, unit=None, solver_source=None,
                 reason_code=reason_code, lever=detail_key or None)


def _peak_fy(fz: float, camber_deg: float, coeffs: TireCoeffs) -> float:
    alphas = np.radians(np.linspace(0.5, 14.0, 28))
    return float(max(abs(calc_tire_forces(fz, float(a), 0.0, math.radians(camber_deg), coeffs)[1])
                     for a in alphas))


def _roll_geometry(vp: LapSimVehicleParams, ay: float):
    k_f = vp.roll_stiffness_front()
    k_r = vp.roll_stiffness_rear()
    h_r = vp.roll_center_f_m + (vp.a_m / vp.wheelbase_m) * (vp.roll_center_r_m - vp.roll_center_f_m)
    delta_h = max(vp.cg_height_m - h_r, 0.02)
    theta = vp.mass_kg * ay * delta_h / max(k_f + k_r, 1.0)  # rad, same moment arm as the GGV solver
    return k_f, k_r, delta_h, theta


def _front_outer_fz(vp: LapSimVehicleParams, v: float, ay: float) -> float:
    k_f, k_r, delta_h, _ = _roll_geometry(vp, ay)
    f_down = 0.5 * vp.rho_air * vp.cl * vp.frontal_area_m2 * v ** 2
    fz_front_static = vp.mass_kg * G * vp.weight_dist_f + f_down * vp.cop_front
    d_geom = vp.mass_kg * ay * vp.weight_dist_f * (vp.roll_center_f_m / vp.track_f_m)
    d_elast = (k_f / max(k_f + k_r, 1.0)) * (vp.mass_kg * ay * delta_h / vp.track_f_m)
    return float(fz_front_static / 2.0 + d_geom + d_elast)


def _camber_at_travel(points, travel_mm: float) -> float:
    pts = [p for p in points if p.converged]
    x = np.array([p.wheel_travel_mm for p in pts], dtype=float)
    y = np.array([p.camber_deg for p in pts], dtype=float)
    return float(np.interp(travel_mm, x, y))


def _vehicle(base: Dict[str, Any], levers: Dict[str, float]) -> LapSimVehicleParams:
    kw = dict(base)
    kw.update(levers)
    return LapSimVehicleParams(**kw)


def compute_why_chain(
    setup_a: Dict[str, float],
    setup_b: Dict[str, float],
    track: str = "spa",
    corner: Optional[Dict[str, float]] = None,
    base_vehicle: Optional[Dict[str, Any]] = None,
    hardpoints: Optional[dict] = None,
) -> Dict[str, Any]:
    """Return the causal chain A -> B. Raises ValueError on malformed input.

    setup_a / setup_b: dicts of lever name -> value (the full set of levers being compared).
    corner: {"s_start_m", "s_end_m"}. Default: +/-150 m around the slowest point of setup A.
    """
    base_vehicle = dict(base_vehicle or {})
    levers = sorted(set(setup_a) | set(setup_b))
    if not levers:
        raise ValueError("setup_a and setup_b must name at least one lever")
    changed = [k for k in levers if setup_a.get(k) != setup_b.get(k)]
    if not changed:
        raise ValueError("setup_a and setup_b are identical")
    for k in changed:
        for s in (setup_a, setup_b):
            if k not in s or not isinstance(s[k], (int, float)) or not math.isfinite(float(s[k])):
                raise ValueError(f"lever {k!r} needs a finite number in both setups")

    chain: List[Dict[str, Any]] = []
    chain.append(_link(
        "input_delta", OK, solver_source="request",
        value={k: {"a": setup_a[k], "b": setup_b[k], "delta": float(setup_b[k]) - float(setup_a[k])}
               for k in changed},
        unit="lever units as supplied",
    ))

    def stop(reason: str, lever: str, from_link: str) -> Dict[str, Any]:
        order = ["roll_gradient_lltd", "camber_in_roll", "pacejka_peak_grip",
                 "qss_apex_speed", "corner_time"]
        for name in order[order.index(from_link):]:
            chain.append(_not_modeled(name, reason, lever))
        return {"track": track, "chain": chain, "chain_complete": False}

    # Link 2 reachability: every changed lever must reach roll stiffness.
    for k in changed:
        if k in NO_GRIP_PATH_LEVERS:
            return stop("LEVER_HAS_NO_PATH_TO_ROLL_STIFFNESS", k, "roll_gradient_lltd")
        if k not in ROLL_LEVERS:
            return stop("LEVER_NOT_IN_QSS_MODEL", k, "roll_gradient_lltd")

    la = {k: float(v) for k, v in setup_a.items()}
    lb = {k: float(v) for k, v in setup_b.items()}
    vp_a = _vehicle(base_vehicle, la)
    vp_b = _vehicle(base_vehicle, lb)

    # QSS run of A defines the corner and the apex state.
    res_a = simulate_lap(vp_a, track=track)
    dist = np.asarray(res_a.distances, dtype=float)
    spd_a = np.asarray(res_a.speeds, dtype=float)
    if corner and "s_start_m" in corner and "s_end_m" in corner:
        s0, s1 = float(corner["s_start_m"]), float(corner["s_end_m"])
        if not (s1 > s0):
            raise ValueError("corner.s_end_m must exceed corner.s_start_m")
    else:
        s_min = float(dist[int(np.argmin(spd_a))])
        s0, s1 = s_min - 150.0, s_min + 150.0
    mask = (dist >= s0) & (dist <= s1)
    if mask.sum() < 3:
        raise ValueError("corner window contains fewer than 3 track samples")
    idx_win = np.where(mask)[0]
    i_apex = int(idx_win[int(np.argmin(spd_a[idx_win]))])
    v_apex = float(spd_a[i_apex])
    ay_apex = float(abs(res_a.lateral_g[i_apex]) * G)

    # Link 2: roll gradient and LLTD.
    kfa, kra, _, th_a = _roll_geometry(vp_a, ay_apex)
    kfb, krb, _, th_b = _roll_geometry(vp_b, ay_apex)
    rg_a = math.degrees(th_a) / (ay_apex / G)
    rg_b = math.degrees(th_b) / (ay_apex / G)
    chain.append(_link(
        "roll_gradient_lltd", OK, solver_source="lap_sim.LapSimVehicleParams.roll_stiffness_front/rear/lltd",
        value={"roll_gradient_deg_per_g": {"a": rg_a, "b": rg_b, "delta": rg_b - rg_a},
               "lltd_front": {"a": vp_a.lltd(), "b": vp_b.lltd(), "delta": vp_b.lltd() - vp_a.lltd()},
               "evaluated_at_ay_ms2": ay_apex},
        unit="deg/g ; dimensionless",
    ))

    # Link 3: front outer-wheel camber from kinematics + body roll.
    hp = copy.deepcopy(hardpoints) if hardpoints else copy.deepcopy(DEFAULT_HARDPOINTS)
    kin = solve_kinematics(hp, mode="python")
    half_track_mm = 0.5 * vp_a.track_f_m * 1000.0
    cam = {}
    for tag, th in (("a", th_a), ("b", th_b)):
        travel_mm = half_track_mm * th  # outer wheel jounce, small-angle
        geo = _camber_at_travel(kin.points, travel_mm)
        # ground camber of the outer wheel: suspension camber + body roll (top moves outward = +)
        cam[tag] = {"travel_mm": travel_mm, "geometry_camber_deg": geo,
                    "ground_camber_deg": geo + math.degrees(th)}
    chain.append(_link(
        "camber_in_roll", OK, solver_source="kinematics.solve_kinematics(mode=python) + roll angle",
        value={"outer_wheel_travel_mm": {"a": cam["a"]["travel_mm"], "b": cam["b"]["travel_mm"]},
               "ground_camber_deg": {"a": cam["a"]["ground_camber_deg"], "b": cam["b"]["ground_camber_deg"],
                                     "delta": cam["b"]["ground_camber_deg"] - cam["a"]["ground_camber_deg"]},
               "axle": "front", "rear_axle": NOT_MODELED},
        unit="mm ; deg",
    ))

    # Link 4: Pacejka peak lateral grip at fixed Fz (isolates the camber effect).
    coeffs = TireCoeffs()
    fz = _front_outer_fz(vp_a, v_apex, ay_apex)
    fy_a = _peak_fy(fz, cam["a"]["ground_camber_deg"], coeffs)
    fy_b = _peak_fy(fz, cam["b"]["ground_camber_deg"], coeffs)
    ratio = fy_b / fy_a
    wdf = float(vp_a.weight_dist_f)
    mu_scale = 1.0 + wdf * (ratio - 1.0)
    chain.append(_link(
        "pacejka_peak_grip", OK, solver_source="magic_formula.calc_tire_forces (default TireCoeffs)",
        value={"front_outer_fz_n": fz,
               "peak_fy_n": {"a": fy_a, "b": fy_b, "delta": fy_b - fy_a},
               "front_grip_ratio_b_over_a": ratio,
               "mu_scale_applied_to_qss_b": mu_scale},
        unit="N ; dimensionless",
    ))

    # Link 5/6: QSS for B with LLTD change and the camber grip scale.
    vp_b.mu_0 = vp_b.mu_0 * mu_scale
    res_b = simulate_lap(vp_b, track=track)
    spd_b = np.asarray(res_b.speeds, dtype=float)
    if len(spd_b) != len(dist):
        raise ValueError("A and B QSS runs returned different sample counts")
    chain.append(_link(
        "qss_apex_speed", OK, solver_source="lap_sim.simulate_lap",
        value={"apex_speed_ms": {"a": float(spd_a[idx_win].min()), "b": float(spd_b[idx_win].min()),
                                 "delta": float(spd_b[idx_win].min() - spd_a[idx_win].min())},
               "corner_window_m": [s0, s1]},
        unit="m/s",
    ))

    def window_time(spd):
        ds = np.diff(dist[idx_win])
        v_mid = 0.5 * (spd[idx_win][:-1] + spd[idx_win][1:])
        return float(np.sum(ds / np.maximum(v_mid, 0.1)))

    t_a, t_b = window_time(spd_a), window_time(spd_b)
    chain.append(_link(
        "corner_time", OK, solver_source="lap_sim.simulate_lap (sum ds/v over corner window)",
        value={"corner_time_s": {"a": t_a, "b": t_b, "delta": t_b - t_a},
               "lap_time_s": {"a": float(res_a.lap_time_s), "b": float(res_b.lap_time_s),
                              "delta": float(res_b.lap_time_s - res_a.lap_time_s)}},
        unit="s",
    ))
    return {"track": track, "chain": chain, "chain_complete": True}
