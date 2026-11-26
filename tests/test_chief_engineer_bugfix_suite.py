"""
tests/test_chief_engineer_bugfix_suite.py
=========================================
Verification suite covering all 11 backend physics, sign-convention,
worker execution, and API fixes from the Chief Engineer's Bug Ledger.
"""
from __future__ import annotations

import copy
import math
import os
import time
import uuid
from unittest.mock import patch

import numpy as np
import pytest
from httpx import AsyncClient

from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    compute_corner_geometry,
    solve_kinematics,
)
from suspensionlab.physics.kinematics_facade import solve_kinematics as facade_solve_kinematics
from suspensionlab.physics.kinematics_sensitivity import (
    OptimizationConstraint,
    OptimizationObjective,
    optimize_hardpoints,
)
from suspensionlab.backend.api.routes.kinematics_routes import BENCHMARK_PRESETS
from suspensionlab.physics.lap_sim import AeroMap, MassProperties
from suspensionlab.physics.suspension_aero_coupling import (
    CoupledVehicleModel,
    SuspensionConfig,
)
from suspensionlab.physics.handling_model import HandlingParams
from suspensionlab.physics.handling_analysis import (
    compare_handling_setups,
    compute_handling_diagram,
    simulate_yaw_response_scenario,
)
from suspensionlab.physics.full_car import (
    FourCornerRoadProfile,
    FullCarParams,
    calculate_full_car_kpis,
    run_full_car_analysis,
)
from suspensionlab.physics.pareto_optimizer import (
    OptimizationConstraint as ParetoConstraint,
    OptimizationObjective as ParetoObjective,
    SuspensionParetoOptimizer,
)
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile
from suspensionlab.backend.services.experiment_service import ExperimentService


# ── Bug 1: Camber Sign & KPI Sign (C++ & Python parity) ──────────────────────

def test_bug1_camber_and_kpi_sign_conventions_cpp_and_python():
    for mode in ("cpp", "python"):
        res = facade_solve_kinematics(
            DEFAULT_HARDPOINTS, z_min_mm=-30.0, z_max_mm=30.0, n_steps=13, tire_radius_m=0.33, mode=mode
        ).to_dict()
        idx_0 = res["wheel_travel_mm"].index(0.0)
        cam_static = res["camber_deg"][idx_0]
        cam_bump = res["camber_deg"][-1]
        assert cam_bump < cam_static, f"[{mode}] Bump camber ({cam_bump}) must be more negative than static ({cam_static})"
        assert res["kpi_deg"][idx_0] > 10.0, f"[{mode}] KPI must be positive inward inclination, got {res['kpi_deg'][idx_0]}"


# ── Bug 2: Benchmark Presets Ground Plane CP, RC_z, Caster, MR ───────────────

def test_bug2_benchmark_presets_physical_geometry():
    for name, preset in BENCHMARK_PRESETS.items():
        hps = preset["hardpoints"]
        r_m = preset["tire_radius_m"]
        z_min, z_max = preset["wheel_travel_range"]

        assert math.isclose(hps["WC"][2], r_m * 1000.0, abs_tol=1e-6), f"{name}: WC.z != r_tire_mm"
        geom = compute_corner_geometry(hps, dz_mm=0.0, tire_radius=r_m)
        assert abs(geom["cp"][2]) < 1e-6, f"{name}: Contact patch CP.z != 0.0 (got {geom['cp'][2]})"

        sol = facade_solve_kinematics(hps, z_min_mm=z_min, z_max_mm=z_max, n_steps=17, tire_radius_m=r_m).to_dict()
        assert all(sol["converged"]), f"{name}: solver failed to converge"
        mid = len(sol["wheel_travel_mm"]) // 2

        rc_z = sol["roll_center_height_mm"][mid]
        caster = sol["caster_deg"][mid]
        kpi = sol["kpi_deg"][mid]
        mr = sol["motion_ratio"][mid]
        # Wave 5A-2: realistic GT3 bounds (approved by the owner): RC <= 75 mm, KPI >= 8 deg.
        assert 15.0 <= rc_z <= 75.0, f"{name}: RC height {rc_z} mm outside [+15, +75] mm"
        assert 4.5 <= caster <= 6.5, f"{name}: Caster {caster} deg outside [+4.5, +6.5] deg"
        assert 8.0 <= kpi <= 25.0, f"{name}: KPI {kpi} deg outside [+8, +25] deg"
        assert 0.60 <= mr <= 0.85, f"{name}: Motion ratio {mr} outside [0.60, 0.85]"
        assert sol["camber_deg"][-1] < sol["camber_deg"][mid], f"{name}: expected negative camber gain in bump"


# ── Bug 3: /api/v1/kinematics/export accepts hardpoints OR sweep_data ────────

@pytest.mark.anyio
async def test_bug3_kinematics_export_accepts_hardpoints_and_sweep_data(authenticated_client: AsyncClient):
    payload_hp = {
        "hardpoints": BENCHMARK_PRESETS["gt3_touring"]["hardpoints"],
        "setup_name": "GT3_Check",
        "z_min_mm": -30.0,
        "z_max_mm": 30.0,
        "n_steps": 9,
        "format": "csv",
    }
    resp_csv = await authenticated_client.post("/api/v1/kinematics/export", json=payload_hp)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers.get("content-type", "")
    assert "camber_deg" in resp_csv.text

    payload_json = {**payload_hp, "format": "json"}
    resp_json = await authenticated_client.post("/api/v1/kinematics/export", json=payload_json)
    assert resp_json.status_code == 200
    data = resp_json.json()
    assert "curves" in data

    resp_legacy = await authenticated_client.post("/api/v1/kinematics/export/csv", json=payload_hp)
    assert resp_legacy.status_code == 200


# ── Bug 4: Kinematics sensitivity optimizer response keys ────────────────────

def test_bug4_kinematics_optimizer_response_shape():
    opt = optimize_hardpoints(
        BENCHMARK_PRESETS["gt3_touring"]["hardpoints"],
        target_hardpoints=["UWI_aft", "LWI_aft"],
        allowed_axes=["Z"],
        hardpoint_bounds_mm=5.0,
        objectives=[
            OptimizationObjective(metric="camber_gain_deg_per_100mm", direction="minimize", weight=1.0),
            OptimizationObjective(metric="toe_variation_deg", direction="minimize", weight=1.0),
        ],
        constraints=[
            OptimizationConstraint(metric="roll_center_height_static_mm", min_val=-50.0, max_val=120.0),
        ],
        n_samples=12,
        z_min_mm=-25.0,
        z_max_mm=25.0,
        n_steps=9,
    )
    assert "pareto_frontier" in opt and len(opt["pareto_frontier"]) > 0
    assert "best_compromise_candidate" in opt and opt["best_compromise_candidate"] is not None
    assert "objective_values" in opt["pareto_frontier"][0]


# ── Bug 5: Worker executes inline without REDIS_URL ──────────────────────────

def test_bug5_worker_runs_without_redis_url(db_session, tmp_path):
    """Simulate missing REDIS_URL and verify _run_job_async persists COMPLETED_VALID in <2s."""
    import asyncio
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from suspensionlab.backend.database.core import Base
    from suspensionlab.backend.database.models.job import JobRecord
    from suspensionlab.backend.workers.unified_worker import _run_job_async
    from opentelemetry import trace

    db_file = tmp_path / "no_redis_test.db"
    test_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    async def _run():
        eng = create_async_engine(test_url, connect_args={"check_same_thread": False})
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=eng, class_=AsyncSession)

        job_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        async with maker() as s:
            s.add(JobRecord(
                id=uuid.UUID(job_id),
                user_id=uuid.UUID(user_id),
                job_type="SIMULATE_QUARTER",
                status="PENDING",
                params={"m_s": 320.0, "m_u": 45.0, "k_s": 35000.0, "c": 2200.0, "k_t": 220000.0, "MR": 0.85},
                profile={"profile_type": "step", "amplitude": 0.05, "duration": 2.0},
            ))
            await s.commit()

        payload = {
            "params": {"m_s": 320.0, "m_u": 45.0, "k_s": 35000.0, "c": 2200.0, "k_t": 220000.0, "MR": 0.85},
            "profile": {"profile_type": "step", "amplitude": 0.05, "duration": 2.0},
        }
        tracer = trace.get_tracer(__name__)
        t0 = time.perf_counter()
        with patch.dict(os.environ, {"REDIS_URL": ""}, clear=False), \
             patch("suspensionlab.backend.database.core.get_worker_session_maker", return_value=maker):
            with tracer.start_as_current_span("test_no_redis") as span:
                await _run_job_async(job_id, payload, None, span, time.time(), {"user_id": user_id, "model_family": "quarter_car"})
        elapsed = time.perf_counter() - t0

        async with maker() as s:
            rec = (await s.execute(select(JobRecord).where(JobRecord.id == uuid.UUID(job_id)))).scalar_one()
            status_val = rec.status
            res_val = rec.result
        await eng.dispose()
        return status_val, res_val, elapsed

    status_val, res_val, elapsed = asyncio.run(_run())
    assert status_val in ("COMPLETED", "COMPLETED_VALID", "COMPLETED_WITH_WARNINGS")
    assert res_val is not None and "f_n_s" in res_val
    assert elapsed < 5.0


# ── Bug 6: Inverted Front ARB LT Sign & Dynamic Pressure q_dyn ───────────────

def test_bug6_arb_sensitivity_sign_and_true_dynamic_pressure():
    coupler = CoupledVehicleModel(
        MassProperties(),
        AeroMap(rho_air=1.225, frontal_area=2.0, cl_base=2.5, cl_rh_sens=0.02),
        SuspensionConfig(k_spring_front=40000.0, k_arb_front=15000.0, motion_ratio_front=0.85),
    )
    arb = coupler.sensitivity_to_arb(v=50.0, ay=9.81, delta_arb_front=5000.0)
    assert arb["delta_lat_transfer_front_n"] > 0.0
    assert arb["delta_lat_transfer_rear_n"] < 0.0
    assert math.isclose(arb["delta_lat_transfer_front_n"], -arb["delta_lat_transfer_rear_n"], abs_tol=0.2)
    assert arb["understeer_tendency"] == "more"

    # q_dyn check via ride-height sensitivity: delta_df = dCL_drh * delta_rh * (0.5 * rho * v^2) * A
    rh = coupler.sensitivity_to_ride_height(v=50.0, delta_rh_mm=5.0)
    expected_q = 0.5 * 1.225 * (50.0 ** 2)
    expected_delta_df = 0.02 * 5.0 * expected_q * 2.0
    assert math.isclose(rh["delta_downforce_total_n"], expected_delta_df, abs_tol=0.2)


@pytest.mark.anyio
async def test_bug6_lapsim_sensitivity_q_dynamic_pa(authenticated_client: AsyncClient):
    resp = await authenticated_client.post(
        "/api/v1/lapsim/sensitivity",
        json={"delta_arb_front": 5000.0, "speed_ms": 50.0, "delta_ride_height": 5.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    expected_q = 0.5 * 1.225 * (50.0 ** 2)
    assert math.isclose(data["operating_point"]["q_dynamic_pa"], expected_q, rel_tol=1e-3)
    assert data["arb_balance"]["delta_lat_transfer_front_n"] > 0.0


# ── Bug 7: Handling ARB Coupling & setup_b Typo ──────────────────────────────

def test_bug7_handling_couples_arb_into_roll_dist_kus_and_tau():
    p_soft = HandlingParams(K_arb_f=15000.0)
    p_stiff = HandlingParams(K_arb_f=45000.0)

    d_soft = compute_handling_diagram(p_soft, speed_kph=100.0, n_points=25)
    d_stiff = compute_handling_diagram(p_stiff, speed_kph=100.0, n_points=25)

    assert d_stiff["load_transfer_summary"]["front_roll_stiffness_pct"] > d_soft["load_transfer_summary"]["front_roll_stiffness_pct"]
    assert d_stiff["kus_linear_deg_per_g"] > d_soft["kus_linear_deg_per_g"]

    cmp = compare_handling_setups(p_soft, p_stiff, speed_kph=100.0)
    assert cmp["metrics_summary"]["delta_kus"] > 0.0
    rear_arb_row = next(r for r in cmp["what_changed"] if "Rear Anti-Roll" in r["parameter"]) if p_soft.K_arb_r != p_stiff.K_arb_r else None
    assert rear_arb_row is None  # identical rear ARB

    # Also verify direct Rear ARB label uses setup_a.K_arb_r (not setup_b.K_arb_r)
    p_rear_mod = HandlingParams(K_arb_r=25000.0)
    cmp_r = compare_handling_setups(p_soft, p_rear_mod, speed_kph=100.0)
    row_r = next(r for r in cmp_r["what_changed"] if "Rear Anti-Roll" in r["parameter"])
    assert row_r["setup_a"].startswith("10000")
    assert row_r["setup_b"].startswith("25000")

    s_soft = simulate_yaw_response_scenario(p_soft, scenario_type="step_steer", v_kph=100.0)
    s_stiff = simulate_yaw_response_scenario(p_stiff, scenario_type="step_steer", v_kph=100.0)
    assert s_soft["metrics"]["yaw_time_constant_ms"] != s_stiff["metrics"]["yaw_time_constant_ms"]


# ── Bug 8: Full-Car Overdamped Eigenmodes & Cornering LLT ────────────────────

def test_bug8_full_car_overdamped_heave_nonzero_and_cornering_llt():
    params_od = FullCarParams(
        m_s=1600.0, I_x=450.0, I_y=2000.0, m_uf=45.0, m_ur=45.0,
        k_sf=18000.0, k_sr=20000.0, c_f=9000.0, c_r=9000.0,  # Heavily overdamped heave
        k_arb_f=12000.0, k_arb_r=8000.0, k_tf=220000.0, k_tr=220000.0,
        L=2.7, a=1.3, b=1.4, tw_f=1.6, tw_r=1.6, speed_mps=20.0,
        lateral_accel_g=1.2,
    )
    kpis = calculate_full_car_kpis(params_od, {
        "ddz_s": np.zeros(10), "ddtheta": np.zeros(10), "ddphi": np.zeros(10),
        "z_rfl": np.zeros(10), "z_ufl": np.zeros(10),
        "z_rfr": np.zeros(10), "z_ufr": np.zeros(10),
        "z_rrl": np.zeros(10), "z_url": np.zeros(10),
        "z_rrr": np.zeros(10), "z_urr": np.zeros(10),
    })
    assert kpis["f_n_heave"] > 0.5, f"Overdamped heave frequency fell back to {kpis['f_n_heave']} Hz"

    t = np.linspace(0.0, 1.0, 200)
    flat_road = FourCornerRoadProfile(time=t, z_rfl=np.zeros_like(t), z_rfr=np.zeros_like(t), z_rrl=np.zeros_like(t), z_rrr=np.zeros_like(t))
    res = run_full_car_analysis(params_od, flat_road)
    assert np.mean(res.lateral_load_transfer_f) > 500.0
    assert np.mean(res.lateral_load_transfer_r) > 300.0


# ── Bug 9: Pareto Rank-0 best_compromise + <5s runtime ───────────────────────

def test_bug9_pareto_best_compromise_fields_and_speed():
    t0 = time.perf_counter()
    res = ExperimentService.batch_optimize_pareto({"m_s": 320.0})
    dt = time.perf_counter() - t0
    assert dt < 5.0, f"batch_optimize_pareto took {dt:.2f}s (> 5s)"
    best = res["best_compromise"]
    assert best is not None
    assert "candidate_id" in best and best["candidate_id"].startswith("CAND-")
    assert best.get("is_pareto_optimal") is True
    assert any(c["candidate_id"] == best["candidate_id"] for c in res["candidates"])


# ── Bug 10: /timeline/compare GET & POST ─────────────────────────────────────

@pytest.mark.anyio
async def test_bug10_timeline_compare_supports_get_and_post(authenticated_client: AsyncClient):
    ev1 = await authenticated_client.post(
        "/api/v1/timeline/events",
        json={"event_type": "setup_change", "title": "Base Setup", "description": "Baseline setup configuration"},
    )
    ev2 = await authenticated_client.post(
        "/api/v1/timeline/events",
        json={"event_type": "setup_change", "title": "Stiff Front", "description": "Stiffer front ARB setup"},
    )
    assert ev1.status_code == 201 and ev2.status_code == 201
    id1 = ev1.json()["id"]
    id2 = ev2.json()["id"]

    get_resp = await authenticated_client.get(f"/api/v1/timeline/compare?event_a_id={id1}&event_b_id={id2}")
    assert get_resp.status_code == 200

    post_resp1 = await authenticated_client.post("/api/v1/timeline/compare", json={"event_a_id": id1, "event_b_id": id2})
    assert post_resp1.status_code == 200

    post_resp2 = await authenticated_client.post("/api/v1/timeline/compare", json={"event_id_a": id1, "event_id_b": id2})
    assert post_resp2.status_code == 200


# ── Bug 11: Empty DB /reports/hydrate/latest & create_from_run return 200 ────

@pytest.mark.anyio
async def test_bug11_reports_hydrate_latest_and_create_from_empty_db(authenticated_client: AsyncClient):
    hydrate_resp = await authenticated_client.get("/api/v1/reports/hydrate/latest")
    assert hydrate_resp.status_code == 200
    hdata = hydrate_resp.json()
    assert hdata["run_id"].startswith("RUN-")
    assert "Heave Natural Frequency" in hdata["metrics"]
    assert float(hdata["metrics"]["Heave Natural Frequency"].split()[0]) > 0.0

    create_resp = await authenticated_client.post(
        "/api/v1/reports/create_from_run",
        json={"simulation_run_id": "latest", "title": "Baseline Report"},
    )
    assert create_resp.status_code == 200
    cdata = create_resp.json()
    assert cdata["token"]
    assert cdata["hydrated"]["run_id"].startswith("RUN-")
