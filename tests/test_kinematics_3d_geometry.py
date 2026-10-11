"""
tests/test_kinematics_3d_geometry.py
====================================
Rigorous verification of:
1. Complete 3D nodal coordinate generation for suspension members.
2. Rigid link distance conservation across full wheel travel sweep.
3. Analytical Instant Center and Roll Center intersection geometry.
4. Ground piercing steering axis and scrub radius geometric accuracy.
5. Admissibility validator with diagnostic remediation guidance.
6. Industry benchmark presets (Formula SAE, GT3, LMP Prototype).
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    compute_corner_geometry,
    compute_sweep_geometry,
    validate_hardpoints_py,
    solve_kinematics,
    solve_single_point,
)
from suspensionlab.backend.api.routes.kinematics_routes import BENCHMARK_PRESETS


def test_3d_nodal_points_exist_and_finite():
    geom = compute_corner_geometry(DEFAULT_HARDPOINTS, dz_mm=0.0)
    expected_keys = [
        "uwo", "lwo", "tro", "pro", "wc", "cp",
        "ic_fv", "rc", "ic_sv", "steering_axis_ground",
        "uwi_mid", "lwi_mid", "uwi_fwd", "uwi_aft", "lwi_fwd", "lwi_aft", "tri", "pri",
    ]
    for k in expected_keys:
        assert k in geom, f"Missing key '{k}' in computed corner geometry"
        coords = geom[k]
        assert len(coords) == 3, f"Node '{k}' must be a 3D coordinate [x, y, z]"
        assert all(isinstance(c, (float, int)) and not math.isnan(c) and not math.isinf(c) for c in coords)


def test_rigid_link_conservation_across_travel():
    z_sweep = [-40.0, -20.0, -10.0, 0.0, 10.0, 20.0, 40.0]
    geoms = compute_sweep_geometry(DEFAULT_HARDPOINTS, z_sweep)
    assert len(geoms) == len(z_sweep)

    neutral_idx = z_sweep.index(0.0)
    g0 = geoms[neutral_idx]

    l_uca_fwd_0 = np.linalg.norm(np.array(g0["uwo"]) - np.array(g0["uwi_fwd"]))
    l_uca_aft_0 = np.linalg.norm(np.array(g0["uwo"]) - np.array(g0["uwi_aft"]))
    l_lca_fwd_0 = np.linalg.norm(np.array(g0["lwo"]) - np.array(g0["lwi_fwd"]))
    l_lca_aft_0 = np.linalg.norm(np.array(g0["lwo"]) - np.array(g0["lwi_aft"]))
    l_tierod_0  = np.linalg.norm(np.array(g0["tro"]) - np.array(g0["tri"]))
    l_kingpin_0 = np.linalg.norm(np.array(g0["uwo"]) - np.array(g0["lwo"]))

    for idx, z in enumerate(z_sweep):
        g = geoms[idx]
        l_uca_fwd = np.linalg.norm(np.array(g["uwo"]) - np.array(g["uwi_fwd"]))
        l_uca_aft = np.linalg.norm(np.array(g["uwo"]) - np.array(g["uwi_aft"]))
        l_lca_fwd = np.linalg.norm(np.array(g["lwo"]) - np.array(g["lwi_fwd"]))
        l_lca_aft = np.linalg.norm(np.array(g["lwo"]) - np.array(g["lwi_aft"]))
        l_tierod  = np.linalg.norm(np.array(g["tro"]) - np.array(g["tri"]))
        l_kingpin = np.linalg.norm(np.array(g["uwo"]) - np.array(g["lwo"]))

        assert abs(l_uca_fwd - l_uca_fwd_0) < 0.05, f"UCA front leg stretched at z={z}"
        assert abs(l_uca_aft - l_uca_aft_0) < 0.05, f"UCA rear leg stretched at z={z}"
        assert abs(l_lca_fwd - l_lca_fwd_0) < 0.05, f"LCA front leg stretched at z={z}"
        assert abs(l_lca_aft - l_lca_aft_0) < 0.05, f"LCA rear leg stretched at z={z}"
        assert abs(l_tierod  - l_tierod_0)  < 0.05, f"Tie rod stretched at z={z}"
        assert abs(l_kingpin - l_kingpin_0) < 0.05, f"Kingpin upright stretched at z={z}"


def test_analytical_instant_center_and_roll_center():
    geom = compute_corner_geometry(DEFAULT_HARDPOINTS, dz_mm=0.0)

    uwi_mid = np.array(geom["uwi_mid"])
    uwo = np.array(geom["uwo"])
    lwi_mid = np.array(geom["lwi_mid"])
    lwo = np.array(geom["lwo"])
    ic_fv = np.array(geom["ic_fv"])
    rc = np.array(geom["rc"])
    cp = np.array(geom["cp"])

    assert abs(rc[0]) < 1e-6
    assert abs(rc[1]) < 1e-6

    v_u_arm = np.array([uwo[1] - uwi_mid[1], uwo[2] - uwi_mid[2]])
    v_u_ic  = np.array([ic_fv[1] - uwi_mid[1], ic_fv[2] - uwi_mid[2]])
    cross_u = v_u_arm[0] * v_u_ic[1] - v_u_arm[1] * v_u_ic[0]
    assert abs(cross_u) < 1.0, f"IC does not lie on upper arm line: cross={cross_u}"

    v_l_arm = np.array([lwo[1] - lwi_mid[1], lwo[2] - lwi_mid[2]])
    v_l_ic  = np.array([ic_fv[1] - lwi_mid[1], ic_fv[2] - lwi_mid[2]])
    cross_l = v_l_arm[0] * v_l_ic[1] - v_l_arm[1] * v_l_ic[0]
    assert abs(cross_l) < 1.0, f"IC does not lie on lower arm line: cross={cross_l}"

    v_cp_ic = np.array([ic_fv[1] - cp[1], ic_fv[2] - cp[2]])
    v_cp_rc = np.array([rc[1] - cp[1], rc[2] - cp[2]])
    cross_rc = v_cp_ic[0] * v_cp_rc[1] - v_cp_ic[1] * v_cp_rc[0]
    assert abs(cross_rc) < 1.0, f"RC does not lie on CP-to-IC line: cross={cross_rc}"


def test_steering_axis_ground_piercing_point():
    geom = compute_corner_geometry(DEFAULT_HARDPOINTS, dz_mm=0.0)
    uwo = np.array(geom["uwo"])
    lwo = np.array(geom["lwo"])
    sa_ground = np.array(geom["steering_axis_ground"])

    assert abs(sa_ground[2]) < 1e-6, "Ground piercing point must be on ground plane Z=0"

    v_kp = uwo - lwo
    v_g  = lwo - sa_ground
    cross = np.cross(v_kp, v_g)
    assert np.linalg.norm(cross) < 1e-4, f"Steering axis ground point not collinear: {np.linalg.norm(cross)}"


def test_validation_diagnostics_and_remediation():
    val_ok = validate_hardpoints_py("double_wishbone", DEFAULT_HARDPOINTS)
    assert val_ok["is_valid"] is True
    assert val_ok["status"] == "VALID"
    assert len(val_ok["errors"]) == 0

    bad_hp = dict(DEFAULT_HARDPOINTS)
    bad_hp["UWI_aft"] = list(bad_hp["UWI_fwd"])
    val_bad = validate_hardpoints_py("double_wishbone", bad_hp)

    assert val_bad["is_valid"] is False
    assert val_bad["status"] == "OUT_OF_BOUNDS"
    assert len(val_bad["errors"]) > 0
    assert len(val_bad["remediation"]) > 0

    rem = val_bad["remediation"][0]
    for field in ["issue", "reason", "affected_parameter", "safe_range", "what_engineer_should_change", "severity"]:
        assert field in rem, f"Remediation missing field '{field}': {rem}"
        assert len(str(rem[field])) > 0


def test_benchmark_presets_valid_and_solvable():
    for bench_id, bench in BENCHMARK_PRESETS.items():
        hps = bench["hardpoints"]
        t_rad = bench["tire_radius_m"]
        val = validate_hardpoints_py("double_wishbone", hps, tire_radius_m=t_rad)
        assert val["is_valid"] is True, f"Benchmark '{bench_id}' failed validation: {val['errors']}"

        z_min, z_max = bench["wheel_travel_range"]
        curves = solve_kinematics(
            hardpoints=hps,
            z_min_mm=z_min,
            z_max_mm=z_max,
            n_steps=17,
            tire_radius=t_rad,
        )
        d = curves.to_dict()
        assert len(d["wheel_travel_mm"]) == 17
        assert all(d["converged"]), f"Benchmark '{bench_id}' had unconverged steps"
        assert len(d["geometry_steps"]) == 17