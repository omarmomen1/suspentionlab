"""
tests/test_extreme_engineer_edge_cases.py
==========================================
Hostile stress test suite hammering physics solvers with extreme real-world engineering inputs:
a) Kinematics: Extreme travel (±80 mm) and impossible geometric lockup (zero 500s, zero NaN/Inf, converged=False tracking).
b) Handling & Sensitivity: Zero/low speed (v = 0 km/h, 1 km/h), ultra-soft springs (5,000 N/m), extreme ARBs (K_arb_f = 0, K_arb_r = 100,000), critical oversteer speed warning (v > v_crit).
c) Quarter-Car & Full-Car: Zero damping (c = 0.0) and extreme damping (c = 50,000 Ns/m) with zero NaNs/Infs in eigenvalues and BDF time traces.
d) Telemetry CSV: UTF-8 BOM, aliased case-insensitive headers, non-numeric values, and trailing empty lines.
"""

import copy
import math
import numpy as np
import pytest
from httpx import AsyncClient

from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    solve_kinematics,
    solve_single_point,
    compute_corner_geometry,
)
from suspensionlab.physics.kinematics_facade import solve_kinematics as facade_solve_kinematics
from suspensionlab.backend.api.routes.kinematics_routes import BENCHMARK_PRESETS
from suspensionlab.physics.handling_model import HandlingParams
from suspensionlab.physics.handling_analysis import (
    compute_handling_diagram,
    simulate_yaw_response_scenario,
    effective_roll_dist,
)
from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    simulate_time_response,
    compute_modal_properties,
)
from suspensionlab.physics.full_car import (
    FullCarParams,
    FourCornerRoadProfile,
    run_full_car_analysis,
)
from suspensionlab.physics.lap_sim import MassProperties, AeroMap, SuspensionConfig
from suspensionlab.physics.suspension_aero_coupling import CoupledVehicleModel
from suspensionlab.physics.telemetry_parser import parse_telemetry_csv


# ── Edge Case A: Kinematics Extreme Bounds & Geometric Lockup ────────────────

def test_kinematics_extreme_travel_range():
    """Verify solver handles ±80 mm extreme travel without NaN/Inf."""
    hps = BENCHMARK_PRESETS["gt3_touring"]["hardpoints"]
    res = facade_solve_kinematics(hps, z_min_mm=-80.0, z_max_mm=80.0, n_steps=33, tire_radius_m=0.33).to_dict()

    assert len(res["wheel_travel_mm"]) == 33
    assert all(res["converged"]), "GT3 geometry should converge across ±80 mm travel"

    # Verify every scalar array has zero NaN and zero Infinity
    for key, arr in res.items():
        if isinstance(arr, list) and arr and isinstance(arr[0], (int, float)):
            for val in arr:
                assert not math.isnan(val), f"NaN detected in {key}"
                assert not math.isinf(val), f"Infinity detected in {key}"


def test_kinematics_impossible_geometric_lockup():
    """Construct physically impossible geometry (short link lockup) and verify graceful divergence handling."""
    locked_hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    # Extremely short wishbone (10 mm) that cannot physically travel ±80 mm
    locked_hp["UWO"] = [0.0, 110.0, 370.0]
    locked_hp["LWO"] = [0.0, 110.0, 215.0]
    locked_hp["WC"]  = [0.0, 120.0, 330.0]
    locked_hp["CP"]  = [0.0, 120.0, 0.0]

    # Python and Facade solvers must NOT raise unhandled exceptions
    sol = solve_kinematics(locked_hp, z_min_mm=-80.0, z_max_mm=80.0, n_steps=33, tire_radius=0.33)
    sol_dict = sol.to_dict()

    # Divergence must be explicitly tracked (converged list contains False)
    assert not all(sol_dict["converged"]), "Impossible geometry must flag non-converged points"
    assert sol_dict["model_validity"]["numerical_status"] == "FAIL"

    # Must contain zero NaN or Infinity values in JSON-serializable output
    for key, arr in sol_dict.items():
        if isinstance(arr, list) and arr and isinstance(arr[0], (int, float)):
            for val in arr:
                assert not math.isnan(val), f"NaN in {key} for impossible geometry"
                assert not math.isinf(val), f"Inf in {key} for impossible geometry"


@pytest.mark.anyio
async def test_kinematics_api_impossible_geometry_returns_200(authenticated_client: AsyncClient):
    """Ensure POST /api/v1/kinematics/solve returns HTTP 200 with all_converged=False instead of 500."""
    locked_hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    locked_hp["UWO"] = [0.0, 110.0, 370.0]
    locked_hp["LWO"] = [0.0, 110.0, 215.0]
    locked_hp["WC"]  = [0.0, 120.0, 330.0]
    locked_hp["CP"]  = [0.0, 120.0, 0.0]

    req = {"hardpoints": locked_hp, "z_min_mm": -80.0, "z_max_mm": 80.0, "n_steps": 17}
    resp = await authenticated_client.post("/api/v1/kinematics/solve", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["all_converged"] is False
    assert sum(data["converged"]) < len(data["converged"])
    assert data.get("overall_model_status") == "FAIL" or data.get("numerical_status") == "FAIL"


# ── Edge Case B: Handling Zero/Low Speed & Extreme Oversteer Critical Speed ────

def test_handling_zero_and_low_speed():
    """Guard against division-by-zero (1/v^2, radius=inf, delta_ack) at v = 0 and 1 km/h."""
    p = HandlingParams()

    for speed in [0.0, 1.0]:
        res = compute_handling_diagram(p, speed_kph=speed, max_ay_g=1.0, n_points=15)
        assert res["speed_kph"] == speed
        assert res["speed_ms"] >= 1.0  # Safe internal clamp
        assert not math.isnan(res["kus_linear_deg_per_g"])
        assert not math.isnan(res["ay_peak_g"])

        for pt in res["points"]:
            assert not math.isnan(pt["radius_m"])
            assert not math.isnan(pt["delta_steer_deg"])
            assert not math.isnan(pt["delta_ack_deg"])
            assert not math.isnan(pt["yaw_rate_deg_s"])


def test_handling_extreme_oversteer_and_critical_speed():
    """Verify v_crit calculation and instability warning with K_arb_f = 0, K_arb_r = 100,000, and soft springs."""
    p = HandlingParams(
        a=1.6,
        b=1.1,
        K_spring_f=5000.0,
        K_spring_r=5000.0,
        K_arb_f=0.0,
        K_arb_r=100000.0,
    )

    r_dist = effective_roll_dist(p)
    assert r_dist < 0.15, f"Front roll stiffness distribution ({r_dist*100:.1f}%) should be heavily rear-biased"

    # At 120 km/h, vehicle is in extreme oversteer
    res = compute_handling_diagram(p, speed_kph=120.0, max_ay_g=0.8, n_points=20)
    assert res["kus_linear_deg_per_g"] < 0.0, "Should exhibit negative understeer gradient (oversteer)"
    assert res["critical_speed_kph"] is not None
    assert res["critical_speed_kph"] > 0.0

    # Operating speed (120 km/h) exceeds critical speed -> instability warning triggered
    if 120.0 > res["critical_speed_kph"]:
        assert res["is_unstable_oversteer"] is True
        assert res["stability_warning"] is not None
        assert "dynamically unstable" in res["stability_warning"]


def test_setup_sensitivity_extreme_soft_and_stiff_arbs():
    """Verify CoupledVehicleModel handles zero speed and extreme ARB perturbation."""
    mp = MassProperties(total_mass=800.0, h_cog=0.30, wheelbase=2.70, cog_dist_front=1.35, track_front=1.55, track_rear=1.52)
    aero = AeroMap(cl_base=1.8, cd_base=0.95, frontal_area=1.70, cop_fraction=0.45, cl_rh_sens=0.02)
    sus = SuspensionConfig(k_spring_front=5000.0, k_spring_rear=5000.0, k_arb_front=0.0, k_arb_rear=100000.0)

    model = CoupledVehicleModel(mass_props=mp, aero=aero, suspension=sus)

    # Test v = 0 m/s
    sens_v0 = model.sensitivity_to_arb(v=0.0, ay=10.0, delta_arb_front=5000.0)
    assert sens_v0["delta_lat_transfer_front_n"] > 0.0
    assert sens_v0["understeer_tendency"] == "more"

    # Test extreme front ARB perturbation (+100,000 N/m)
    sens_extreme = model.sensitivity_to_arb(v=50.0, ay=20.0, delta_arb_front=100000.0)
    assert sens_extreme["delta_lat_transfer_front_n"] > 50.0
    assert sens_extreme["understeer_tendency"] == "more"


# ── Edge Case C: Quarter-Car & Full-Car Zero and Extreme Damping ─────────────

def test_quarter_car_zero_and_extreme_damping():
    """Verify 2-DOF Quarter-Car solver produces zero NaN/Inf for c = 0.0 and c = 50,000 Ns/m."""
    for c_val in [0.0, 50000.0]:
        p = QuarterCarParams(c=c_val)
        modal = compute_modal_properties(p)

        assert modal["f_n_s"] > 0.5
        assert modal["f_n_u"] > 5.0
        assert modal["zeta_s"] >= 0.0
        assert not math.isnan(modal["zeta_s"])
        assert not math.isinf(modal["zeta_s"])

        prof = RoadProfile(profile_type="step", amplitude=0.02, duration=1.0)
        sim = simulate_time_response(p, prof)

        assert len(sim["time"]) > 100
        for key in ["z_s", "z_u", "ddz_s", "susp_travel"]:
            arr = np.array(sim[key])
            assert not np.isnan(arr).any(), f"NaN in {key} with c={c_val}"
            assert not np.isinf(arr).any(), f"Inf in {key} with c={c_val}"


def test_full_car_zero_and_extreme_damping():
    """Verify 7-DOF Full-Car solver produces zero NaN/Inf for c_f = c_r = 0.0 and 50,000 Ns/m."""
    for c_val in [0.0, 50000.0]:
        p = FullCarParams(
            m_s=1200.0, I_x=600.0, I_y=1800.0, m_uf=40.0, m_ur=40.0,
            k_sf=35000.0, k_sr=35000.0, c_f=c_val, c_r=c_val,
            k_arb_f=10000.0, k_arb_r=8000.0, k_tf=250000.0, k_tr=250000.0,
            L=2.7, a=1.2, b=1.5, tw_f=1.6, tw_r=1.6, speed_mps=20.0,
            MR_f=1.0, MR_r=1.0, enable_contact_loss=False
        )
        t = np.linspace(0, 0.4, 200)
        z_in = np.where(t < 0.04, 0.005 * np.sin(np.pi * t / 0.04), 0.0)
        profile = FourCornerRoadProfile(time=t, z_rfl=z_in, z_rfr=z_in, z_rrl=z_in, z_rrr=z_in)

        res = run_full_car_analysis(p, profile)
        assert res.f_n_heave > 0.5
        assert res.f_n_pitch > 0.5
        assert not np.isnan(res.z_s).any(), f"NaN in z_s with c={c_val}"
        assert not np.isinf(res.z_s).any(), f"Inf in z_s with c={c_val}"
        assert not np.isnan(res.ddz_s).any(), f"NaN in ddz_s with c={c_val}"


# ── Edge Case D: Messy Real-World CSV Parsing ────────────────────────────────

def test_telemetry_csv_parsing_bom_aliased_headers_and_trailing_blanks():
    """Test telemetry parsing with UTF-8 BOM, aliases (v_kph, Ground_Speed, ay, time_s), and trailing NaNs."""
    # CSV content with UTF-8 BOM, mixed case, aliases, empty rows, and NaN cells
    csv_raw = (
        "\ufeffTime_s,Ground_Speed,LatAccel,Ax_g,Damper_FL\n"
        "0.00,120.5,0.02,0.15,12.4\n"
        "0.01,121.0,0.05,0.12,12.8\n"
        "0.02,121.5,0.10,NaN,13.1\n"
        "0.03,122.0,0.18,-0.05,null\n"
        "0.04,122.5,0.25,-0.10,13.9\n"
        "0.05,123.0,0.30,-0.12,14.2\n"
        "0.06,123.5,0.35,-0.15,14.5\n"
        "0.07,124.0,0.40,-0.18,14.8\n"
        "0.08,124.5,0.42,-0.20,15.1\n"
        "0.09,125.0,0.45,-0.22,15.4\n"
        "0.10,125.5,0.48,-0.25,15.7\n"
        "\n"
        "   \n"
    )

    parsed = parse_telemetry_csv(csv_raw)
    assert "time" in parsed
    assert "speed" in parsed
    assert "lat_g" in parsed
    assert len(parsed["time"]) == 11
    assert math.isclose(parsed["time"][0], 0.00)
    assert math.isclose(parsed["time"][-1], 0.10)
    assert parsed["_audit_trail"]["duplicate_timestamps_count"] == 0
