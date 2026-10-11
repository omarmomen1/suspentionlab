"""
backend/api/routes/vehicle_intelligence_routes.py
===================================================
SuspensionLab PRO — Vehicle Dynamics Intelligence Platform Routes

Endpoints
---------
POST /intelligence/yaw          Yaw moment diagram (MMM) + stability metrics
POST /intelligence/tire_warmup  Tire warm-up simulation
POST /intelligence/ers          ERS lap analysis (2026 regulations)
POST /intelligence/pareto       Multi-objective Pareto frontier optimization
POST /intelligence/constrained  Constraint-driven lap time optimization
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from suspensionlab.backend.security.auth import verify_api_key

router = APIRouter(prefix="/intelligence", tags=["Vehicle Intelligence"])


# ─────────────────────────────────────────────────────────────────────────────
# POST /intelligence/yaw
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/yaw", summary="Yaw moment diagram (MMM) + stability metrics")
async def yaw_analysis(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
):
    """Compute the Milliken Moment Method diagram and stability metrics.

    Request body
    ------------
    params : dict (optional)
        mass, Iz, wheelbase, cog_dist_front, C_alpha_front, C_alpha_rear
    v_ms : float  Speed [m/s] (default 50)
    beta_range  : [min, max] sideslip [deg] (default [-10, 10])
    delta_range : [min, max] steer [deg]    (default [-5, 5])
    n_beta  : int  (default 21)
    n_delta : int  (default 11)

    Response
    --------
    stability_metrics, mmm_diagram (Fy and Mz matrices)
    """
    from suspensionlab.physics.yaw_dynamics import (
        BicycleModelParams, YawMomentAnalyzer, TransientYawSolver,
        compute_stability_metrics,
    )

    raw = request_data.get("params", {})
    a = float(raw.get("a", raw.get("cog_dist_front", 1.35)))
    b = float(raw.get("b", 1.35))
    wheelbase = float(raw.get("wheelbase", a + b))
    p = BicycleModelParams(
        mass=float(raw.get("m", raw.get("mass", 800.0))),
        Iz=float(raw.get("I_z", raw.get("Iz", 1200.0))),
        wheelbase=wheelbase,
        cog_dist_front=a,
        C_alpha_front=float(raw.get("C_f", raw.get("C_alpha_front", 120_000.0))),
        C_alpha_rear=float(raw.get("C_r", raw.get("C_alpha_rear", 140_000.0))),
    )

    v          = float(request_data.get("v_ms", 50.0))
    beta_range = tuple(request_data.get("beta_range",  [-10.0, 10.0]))
    delta_range = tuple(request_data.get("delta_range", [-5.0, 5.0]))
    n_beta     = int(request_data.get("n_beta",  21))
    n_delta    = int(request_data.get("n_delta", 11))

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        analyzer = YawMomentAnalyzer(p)
        metrics  = await loop.run_in_executor(
            None, compute_stability_metrics, p, v
        )
        mmm = await loop.run_in_executor(
            None, lambda: analyzer.compute_mmm(v, beta_range, delta_range, n_beta, n_delta)
        )
    except Exception as e:
        raise HTTPException(500, f"Yaw analysis failed: {e}")

    return {
        "stability_metrics": metrics,
        "mmm": {
            "beta_deg":   mmm.beta_deg.tolist(),
            "delta_deg":  mmm.delta_deg.tolist(),
            "Fy_total_n": mmm.Fy_total.tolist(),   # shape (n_beta, n_delta)
            "Mz_total_nm": mmm.Mz_total.tolist(),
            "understeer_gradient_deg_per_g": mmm.understeer_gradient,
            "neutral_steer_speed_ms":        mmm.neutral_steer_speed,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /intelligence/yaw/transient
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/yaw/transient", summary="Transient yaw simulation (step steer)")
async def yaw_transient(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
):
    """Simulate transient yaw response to a step steer input.

    Request body
    ------------
    params    : dict  vehicle parameters (same as /yaw)
    v_ms      : float  speed [m/s]
    radius_m  : float  corner radius [m]
    t_total_s : float  simulation duration [s] (default 3.0)
    dt_s      : float  time step [s] (default 0.005)
    """
    from suspensionlab.physics.yaw_dynamics import BicycleModelParams, TransientYawSolver

    raw = request_data.get("params", {})
    a = float(raw.get("a", raw.get("cog_dist_front", 1.35)))
    b = float(raw.get("b", 1.35))
    wheelbase = float(raw.get("wheelbase", a + b))
    p = BicycleModelParams(
        mass=float(raw.get("m", raw.get("mass", 800.0))),
        Iz=float(raw.get("I_z", raw.get("Iz", 1200.0))),
        wheelbase=wheelbase,
        cog_dist_front=a,
        C_alpha_front=float(raw.get("C_f", raw.get("C_alpha_front", 120_000.0))),
        C_alpha_rear=float(raw.get("C_r", raw.get("C_alpha_rear", 140_000.0))),
    )

    v        = float(request_data.get("v_ms",      50.0))
    radius   = float(request_data.get("radius_m",  50.0))
    t_total  = float(request_data.get("t_total_s",  3.0))
    dt       = float(request_data.get("dt_s",      0.005))

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        solver = TransientYawSolver(p)
        result = await loop.run_in_executor(
            None, lambda: solver.simulate_corner(v, radius, t_total, dt)
        )
    except Exception as e:
        raise HTTPException(500, f"Transient yaw simulation failed: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# POST /intelligence/tire_warmup
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/tire_warmup", summary="Tire warm-up simulation over N laps")
async def tire_warmup(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
):
    """Simulate tire temperature evolution over multiple laps.

    Request body
    ------------
    n_laps          : int   (default 5)
    track_length_m  : float (default 5000)
    avg_speed_ms    : float (default 50)
    avg_lat_g       : float (default 1.5)
    avg_long_g      : float (default 0.5)
    avg_fz_n        : float (default 3000)  N per tire
    thermal_config  : dict  optional override of TireThermalConfig defaults
        T_opt, sigma_T, mu_cold, T_ambient, T_road, T_initial
    """
    from suspensionlab.physics.tire_thermal import TireThermalConfig, TireWarmupSimulator

    tc_raw = request_data.get("thermal_config", {})
    config = TireThermalConfig(
        T_opt=float(tc_raw.get("T_opt",      85.0)),
        sigma_T=float(tc_raw.get("sigma_T",  30.0)),
        mu_cold=float(tc_raw.get("mu_cold",  0.65)),
        T_ambient=float(tc_raw.get("T_ambient", 25.0)),
        T_road=float(tc_raw.get("T_road",    35.0)),
        T_initial=float(tc_raw.get("T_initial", 25.0)),
    )

    n_laps        = int(request_data.get("n_laps",         5))
    track_length  = float(request_data.get("track_length_m", 5_000.0))
    avg_speed     = float(request_data.get("avg_speed_ms",   50.0))
    avg_lat_g     = float(request_data.get("avg_lat_g",       1.5))
    avg_long_g    = float(request_data.get("avg_long_g",      0.5))
    avg_fz        = float(request_data.get("avg_fz_n",     3_000.0))

    n_laps = min(max(n_laps, 1), 20)

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        sim = TireWarmupSimulator(config)
        result = await loop.run_in_executor(
            None,
            lambda: sim.simulate_warmup(
                n_laps=n_laps,
                track_length_m=track_length,
                avg_speed_ms=avg_speed,
                avg_lat_g=avg_lat_g,
                avg_long_g=avg_long_g,
                avg_fz_n=avg_fz,
            ),
        )
    except Exception as e:
        raise HTTPException(500, f"Tire warmup simulation failed: {e}")

    # Remove final_state object (not JSON serializable)
    result.pop("final_state", None)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# POST /intelligence/ers
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/ers", summary="2026 ERS deployment lap analysis")
async def ers_analysis(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
):
    """Analyze ERS deployment over a lap using a speed profile.

    Provide the output from /lapsim/run (distances, speeds, longitudinal_g,
    curvatures) plus optional ERS config.

    Request body
    ------------
    telemetry       : dict  from /lapsim/run response
        distances, speeds_ms, longitudinal_g, curvatures
    ers_config      : dict  optional override of ERSConfig defaults
        mgu_k_max_power_w, mgu_k_max_regen_w, battery_capacity_j,
        battery_soc_initial, regen_efficiency, deploy_efficiency
    strategy        : str  'aggressive' | 'conservative' | 'optimal' (default)
    vehicle_mass_kg : float  (default 800)
    """
    from suspensionlab.physics.ers_model import ERSConfig, ERSLapAnalyzer
    import numpy as np

    telem = request_data.get("telemetry", {})
    if not telem:
        raise HTTPException(400, "Provide 'telemetry' from a /lapsim/run result.")

    try:
        distances  = np.array(telem["distances"],      dtype=float)
        speeds_ms  = np.array(telem.get("speeds_ms",
                              [s/3.6 for s in telem.get("speeds_kmh", [])]), dtype=float)
        ax_arr     = np.array(telem.get("longitudinal_g", [0.0]*len(distances)), dtype=float) * 9.81
        curvatures = np.array(telem.get("curvatures",  [0.0]*len(distances)), dtype=float)
    except Exception as e:
        raise HTTPException(422, f"Invalid telemetry arrays: {e}")

    ec_raw = request_data.get("ers_config", {})
    config = ERSConfig(
        mgu_k_max_power_w=float(ec_raw.get("mgu_k_max_power_w",   350_000.0)),
        mgu_k_max_regen_w=float(ec_raw.get("mgu_k_max_regen_w",   200_000.0)),
        battery_capacity_j=float(ec_raw.get("battery_capacity_j", 4_000_000.0)),
        battery_soc_initial=float(ec_raw.get("battery_soc_initial", 0.50)),
        regen_efficiency=float(ec_raw.get("regen_efficiency", 0.85)),
        deploy_efficiency=float(ec_raw.get("deploy_efficiency", 0.92)),
    )

    strategy = str(request_data.get("strategy", "optimal"))
    mass     = float(request_data.get("vehicle_mass_kg", 800.0))

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        analyzer = ERSLapAnalyzer(config=config, strategy=strategy, vehicle_mass_kg=mass)
        result   = await loop.run_in_executor(
            None, lambda: analyzer.analyze(distances, speeds_ms, ax_arr, curvatures)
        )
    except Exception as e:
        raise HTTPException(500, f"ERS analysis failed: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# POST /intelligence/pareto
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/pareto", summary="Multi-objective Pareto frontier optimization")
async def pareto_optimization(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
):
    """Compute Pareto frontier for suspension spring + damping optimization.

    Request body
    ------------
    vehicle_params : dict  QuarterCarParams overrides
        m_s, m_u, k_s, c, k_t, MR
    road_profile   : dict  RoadProfile overrides
        v_ms, psd_type ('iso_b', 'iso_c', 'iso_d'), length_m
    objectives     : str or list  'comfort_vs_grip' | 'grip_vs_travel' | list of objective dicts
    param_ranges   : dict  {'k_s': [min, max, n], 'c': [min, max, n]}
    constraints    : list  optional [{name, lower, upper}]

    Response
    --------
    frontier (Pareto-optimal points), all_feasible, best_compromise
    """
    from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile
    from suspensionlab.physics.pareto_optimizer import (
        SuspensionParetoOptimizer,
        OptimizationObjective,
        OptimizationConstraint,
    )

    # Vehicle params
    vp = request_data.get("vehicle_params", {})
    try:
        base_params = QuarterCarParams(
            m_s=float(vp.get("m_s", 350.0)),
            m_u=float(vp.get("m_u",  40.0)),
            k_s=float(vp.get("k_s", 25_000.0)),
            c=float(vp.get("c",   2_500.0)),
            k_t=float(vp.get("k_t", 200_000.0)),
            MR=float(vp.get("MR",  0.85)),
        )
    except Exception as e:
        raise HTTPException(422, f"Invalid vehicle_params: {e}")

    # Road profile
    rp = request_data.get("road_profile", {})
    # Map psd_type shorthand (e.g. "iso_c") to RoadProfile fields
    psd_raw = str(rp.get("psd_type", "iso_c")).lower()
    iso_class_map = {"iso_a": "A", "iso_b": "B", "iso_c": "C", "iso_d": "D",
                     "iso_e": "E", "iso_f": "F", "iso_g": "G", "iso_h": "H"}
    iso_class = iso_class_map.get(psd_raw, psd_raw.upper() if len(psd_raw) == 1 else "C")
    try:
        profile = RoadProfile(
            profile_type="iso8608",
            iso_class=iso_class,
            speed_mps=float(rp.get("speed_mps", rp.get("v_ms", 30.0))),
            duration=float(rp.get("duration", 5.0)),
        )
    except Exception as e:
        raise HTTPException(422, f"Invalid road_profile: {e}")

    # Objectives
    opt = SuspensionParetoOptimizer()
    obj_raw = request_data.get("objectives", "comfort_vs_grip")
    if isinstance(obj_raw, str):
        objectives = opt.PRESET_OBJECTIVES.get(obj_raw)
        if objectives is None:
            raise HTTPException(422, f"Unknown preset '{obj_raw}'. Use: {list(opt.PRESET_OBJECTIVES)}")
    elif isinstance(obj_raw, list):
        objectives = [
            OptimizationObjective(
                name=o["name"],
                minimize=bool(o.get("minimize", True)),
                unit=str(o.get("unit", "")),
            )
            for o in obj_raw
        ]
    else:
        raise HTTPException(422, "objectives must be a preset string or list of dicts")

    # Constraints
    constraints = []
    for c in request_data.get("constraints", []):
        constraints.append(OptimizationConstraint(
            name=str(c["name"]),
            lower=float(c.get("lower", -1e30)),
            upper=float(c.get("upper",  1e30)),
            unit=str(c.get("unit", "")),
            hard=bool(c.get("hard", True)),
        ))

    # Parameter ranges
    pr_raw = request_data.get("param_ranges", {
        "k_s": [10_000, 80_000, 12],
        "c":   [1_000,   6_000, 10],
    })
    param_ranges = {k: (float(v[0]), float(v[1]), int(v[2])) for k, v in pr_raw.items()}

    # Cap grid size
    total = 1
    for _, _, n in param_ranges.values():
        total *= n
    if total > 2000:
        raise HTTPException(422, f"Grid too large: {total} points. Reduce n_steps per parameter.")

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        frontier = await loop.run_in_executor(
            None, lambda: opt.optimize(base_params, profile, objectives, constraints, param_ranges)
        )
    except Exception as e:
        raise HTTPException(500, f"Pareto optimization failed: {e}")

    return frontier.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# POST /intelligence/constrained
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/constrained", summary="Constraint-driven lap time optimization")
async def constrained_optimization(
    request_data: Dict[str, Any],
    user=Depends(verify_api_key),
):
    """Minimize lap time subject to engineering constraints.

    Request body
    ------------
    vehicle       : dict  vehicle config (same schema as /lapsim/run)
    track         : dict  'distances' + 'curvatures' arrays  (same as /lapsim/run)
    constraints   : dict  override SetupConstraints defaults
    param_ranges  : dict  {'k_spring_front': [min,max,n], 'k_spring_rear': [...], ...}
    strategy      : str   'grid' | 'random' (default 'grid')
    n_samples     : int   max evaluations for random strategy (default 100)

    Response
    --------
    best_solution, feasible_solutions, baseline, n_feasible, n_total, engineer_report
    """
    from suspensionlab.physics.lap_sim import (
        LapSimVehicle, MassProperties, AeroMap, PowertrainModel,
        parse_track_from_curvature,
    )
    from suspensionlab.physics.suspension_aero_coupling import SuspensionConfig
    from suspensionlab.physics.magic_formula import TireCoeffs
    from suspensionlab.physics.constraint_optimizer import (
        ConstraintDrivenOptimizer, SetupConstraints,
    )
    from suspensionlab.backend.api.routes.lap_sim_routes import _build_vehicle, VehicleInput

    # Build vehicle
    v_raw = request_data.get("vehicle")
    try:
        v_input = VehicleInput(**v_raw) if v_raw else None
    except Exception as e:
        raise HTTPException(422, f"Invalid vehicle: {e}")

    # Import helper
    vehicle = _build_vehicle(v_input)

    # Build track
    track_raw = request_data.get("track", {})
    distances  = track_raw.get("distances")
    curvatures = track_raw.get("curvatures")
    if not distances or not curvatures:
        raise HTTPException(400, "Provide track.distances and track.curvatures arrays.")
    try:
        segments = parse_track_from_curvature(distances, curvatures)
    except Exception as e:
        raise HTTPException(422, f"Invalid track data: {e}")

    # Build constraints
    c_raw = request_data.get("constraints", {})
    constraints = SetupConstraints(**{k: v for k, v in c_raw.items()
                                      if hasattr(SetupConstraints, k)})

    # Parameter ranges
    pr_raw = request_data.get("param_ranges", {
        "k_spring_front": [25_000, 55_000, 5],
        "k_spring_rear":  [30_000, 65_000, 5],
    })
    param_ranges = {k: (float(v[0]), float(v[1]), int(v[2])) for k, v in pr_raw.items()}

    strategy  = str(request_data.get("strategy",  "grid"))
    n_samples = int(request_data.get("n_samples", 100))

    # Cap total evaluations
    total = 1
    for _, _, n in param_ranges.values():
        total *= n
    if total > 500:
        raise HTTPException(422, f"Grid too large: {total} evals. Reduce n_steps or use strategy='random'.")

    import asyncio
    loop = asyncio.get_running_loop()

    try:
        optimizer = ConstraintDrivenOptimizer()
        result    = await loop.run_in_executor(
            None,
            lambda: optimizer.optimize(vehicle, segments, constraints, param_ranges, n_samples, strategy),
        )
    except Exception as e:
        raise HTTPException(500, f"Constrained optimization failed: {e}")

    # Generate engineer report
    if result["best_solution"]:
        best_v = __import__("copy").deepcopy(vehicle)
        for k, val in result["best_solution"]["params"].items():
            if hasattr(best_v.suspension, k):
                setattr(best_v.suspension, k, float(val))
        cc = optimizer.check_constraints(best_v, result["best_solution"]["params"], constraints)
        report = optimizer.format_engineer_report(
            result["best_solution"],
            result["baseline"],
            cc,
        )
        result["engineer_report"] = report
    else:
        result["engineer_report"] = {"recommendation": "No feasible solution found."}

    return result
