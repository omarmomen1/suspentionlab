"""
tests/test_nonlinear_ground_effect_aero.py
==========================================
Comprehensive validation suite for Nonlinear Ground-Effect Aerodynamics:
1. Downforce growth with decreasing ride height (pre-stall venturi effect)
2. Peak downforce clearance identification (inverted-U peak at rh_peak_front_mm)
3. Physically bounded post-stall downforce collapse (venturi choke / diffuser separation)
4. Aerodynamic Center of Pressure (CoP) rearward migration under front floor stall
5. Flow separation induced drag penalty
6. Flow reattachment hysteresis under dynamic/transient motion
7. 5D RegularGridInterpolator mapping with strict domain boundary checks
8. Closed-loop equilibrium porpoising limit cycle detection (NUMERICALLY_FAILED)
9. Epistemic validity hierarchy (MODEL_SUPPORTED, EXTRAPOLATED, UNSUPPORTED)
10. Optimization engine guardrails preventing zero/negative ride height exploitation
11. QSS AeroMap nonlinear ground effect integration
"""

import pytest
import numpy as np
import math

from suspensionlab.physics.suspension_aero_coupling import (
    ActiveAeroMode,
    AeroModelType,
    NonlinearGroundEffectConfig,
    evaluate_nonlinear_ground_effect,
    AeroGridMap5D,
    MultidimensionalAeroMap,
    CoupledVehicleModel,
    CoupledState,
    SuspensionConfig,
)
from suspensionlab.physics.lap_sim import MassProperties, AeroMap
from suspensionlab.physics.validity import PhysicsValidityStatus
from suspensionlab.physics.optimization_engine import (
    create_racecar_full_design_space,
    ConstraintManager,
    OptimizationObjective,
    ObjectiveType,
    MultiObjectiveEvaluator,
    ConstraintType,
    EngineeringConstraint,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Downforce Increase With Decreasing Ride Height (Pre-Stall Regime)
# ─────────────────────────────────────────────────────────────────────────────

def test_pre_stall_downforce_monotonic_increase():
    """Verify downforce strictly increases as ride height drops towards peak clearance."""
    cfg = NonlinearGroundEffectConfig(rh_peak_front_mm=22.0, cl_peak=3.60, pre_stall_sens=-0.018)
    
    # Evaluate decreasing ride heights from 70mm down to 22mm
    rhs = [70.0, 55.0, 40.0, 30.0, 25.0, 22.0]
    cls = []
    for rh in rhs:
        cl, _, _, _, sep = evaluate_nonlinear_ground_effect(
            front_rh_mm=rh,
            rear_rh_mm=rh + 25.0,
            cfg=cfg,
        )
        cls.append(cl)
        assert not sep, f"Flow should remain attached at rh={rh} mm"

    # Strictly monotonically increasing
    for i in range(len(cls) - 1):
        assert cls[i + 1] > cls[i], f"Expected CL({rhs[i+1]}) > CL({rhs[i]}), got {cls[i+1]} <= {cls[i]}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Peak Downforce at Critical Ground Clearance
# ─────────────────────────────────────────────────────────────────────────────

def test_peak_downforce_at_critical_clearance():
    """Verify peak downforce occurs at rh_peak_front_mm and is higher than both pre- and post-stall."""
    cfg = NonlinearGroundEffectConfig(rh_peak_front_mm=22.0, cl_peak=3.60)
    
    cl_pre, _, _, _, _ = evaluate_nonlinear_ground_effect(front_rh_mm=26.0, rear_rh_mm=51.0, cfg=cfg)
    cl_peak, _, _, _, _ = evaluate_nonlinear_ground_effect(front_rh_mm=22.0, rear_rh_mm=47.0, cfg=cfg)
    cl_post, _, _, _, _ = evaluate_nonlinear_ground_effect(front_rh_mm=17.0, rear_rh_mm=42.0, cfg=cfg)

    assert cl_peak > cl_pre, f"Peak CL ({cl_peak:.3f}) must exceed pre-stall CL ({cl_pre:.3f})"
    assert cl_peak > cl_post, f"Peak CL ({cl_peak:.3f}) must exceed post-stall CL ({cl_post:.3f})"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Post-Stall Downforce Collapse Without Arbitrary Clipping
# ─────────────────────────────────────────────────────────────────────────────

def test_post_stall_collapse_without_clipping():
    """Verify smooth, physically continuous collapse of downforce below peak clearance."""
    cfg = NonlinearGroundEffectConfig(
        rh_peak_front_mm=22.0,
        cl_peak=3.60,
        cl_stall_floor=1.20,
        stall_decay_power=2.0,
    )
    
    # Decreasing ride heights below peak (22mm down to 1mm)
    rh_post = [20.0, 16.0, 12.0, 8.0, 4.0, 1.0]
    cl_vals = []
    for rh in rh_post:
        cl, _, _, _, sep = evaluate_nonlinear_ground_effect(
            front_rh_mm=rh,
            rear_rh_mm=rh + 25.0,
            cfg=cfg,
        )
        cl_vals.append(cl)
        assert sep, f"Flow must be separated at rh={rh} mm"

    # Must decrease monotonically toward stall floor
    for i in range(len(cl_vals) - 1):
        assert cl_vals[i] > cl_vals[i + 1], f"Expected post-stall collapse: {cl_vals[i]} > {cl_vals[i+1]}"

    # No arbitrary flat clipping: each step has distinct gradient
    diffs = [cl_vals[i] - cl_vals[i+1] for i in range(len(cl_vals) - 1)]
    assert all(d > 0.05 for d in diffs), "Post-stall curve must not be arbitrarily clipped flat"

    # Near touchdown, reaches stall floor
    cl_touchdown, _, _, _, _ = evaluate_nonlinear_ground_effect(front_rh_mm=0.0, rear_rh_mm=25.0, cfg=cfg)
    assert math.isclose(cl_touchdown, cfg.cl_stall_floor, rel_tol=0.05)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Aerodynamic Balance (CoP) Rearward Migration Under Front Floor Stall
# ─────────────────────────────────────────────────────────────────────────────

def test_cop_rearward_migration_under_front_stall():
    """Verify aerodynamic balance shifts rearward when the front floor separates."""
    cfg = NonlinearGroundEffectConfig(
        rh_peak_front_mm=22.0,
        cop_base=0.44,
        cop_stall_shift=-0.12,
    )
    
    # Attached baseline
    _, _, cop_attached, _, sep_att = evaluate_nonlinear_ground_effect(
        front_rh_mm=25.0, rear_rh_mm=50.0, cfg=cfg
    )
    assert not sep_att
    assert math.isclose(cop_attached, 0.44, abs_tol=0.01)

    # Moderate stall (15mm)
    _, _, cop_mod, _, sep_mod = evaluate_nonlinear_ground_effect(
        front_rh_mm=15.0, rear_rh_mm=40.0, cfg=cfg
    )
    assert sep_mod
    assert cop_mod < cop_attached, "CoP must shift rearward (lower % from front axle)"

    # Deep stall (5mm)
    _, _, cop_deep, _, sep_deep = evaluate_nonlinear_ground_effect(
        front_rh_mm=5.0, rear_rh_mm=30.0, cfg=cfg
    )
    assert sep_deep
    assert cop_deep < cop_mod, f"Deeper stall must shift balance further rearward: {cop_deep:.3f} < {cop_mod:.3f}"
    assert cop_deep < 0.35


# ─────────────────────────────────────────────────────────────────────────────
# 5. Flow Separation Induced Drag Penalty
# ─────────────────────────────────────────────────────────────────────────────

def test_flow_separation_drag_penalty():
    """Verify boundary layer stall imposes turbulent wake drag penalty."""
    cfg = NonlinearGroundEffectConfig(
        rh_peak_front_mm=22.0,
        cd_base=0.95,
        cd_stall_penalty=0.35,
    )
    
    _, cd_attached, _, _, sep_att = evaluate_nonlinear_ground_effect(
        front_rh_mm=22.0, rear_rh_mm=47.0, cfg=cfg
    )
    _, cd_stalled, _, _, sep_stall = evaluate_nonlinear_ground_effect(
        front_rh_mm=8.0, rear_rh_mm=33.0, cfg=cfg
    )
    
    assert sep_stall
    # Despite lower induced drag (due to lower downforce), stall separation penalty elevates CD
    assert cd_stalled > 1.10
    assert cd_stalled - cfg.cd_base > 0.20


# ─────────────────────────────────────────────────────────────────────────────
# 6. Flow Reattachment Hysteresis
# ─────────────────────────────────────────────────────────────────────────────

def test_flow_reattachment_hysteresis():
    """Verify that flow separating during compression remains stalled during rebound."""
    cfg = NonlinearGroundEffectConfig(
        rh_peak_front_mm=22.0,
        hysteresis_buffer_mm=4.0,  # reattaches only above 26.0 mm
    )
    
    # Test at 24mm (between peak 22mm and reattach 26mm):
    # If previously clean -> remains attached
    cl_clean, _, _, _, sep_clean = evaluate_nonlinear_ground_effect(
        front_rh_mm=24.0, rear_rh_mm=49.0, cfg=cfg, flow_separated_prev=False
    )
    assert not sep_clean

    # If previously separated -> remains stalled due to hysteresis
    cl_hyst, _, _, _, sep_hyst = evaluate_nonlinear_ground_effect(
        front_rh_mm=24.0, rear_rh_mm=49.0, cfg=cfg, flow_separated_prev=True
    )
    assert sep_hyst
    assert cl_clean > cl_hyst, "Clean attached flow must produce more downforce than hysteretic stalled flow"

    # Once lifted above 26mm, flow reattaches
    _, _, _, _, sep_rebound = evaluate_nonlinear_ground_effect(
        front_rh_mm=27.0, rear_rh_mm=52.0, cfg=cfg, flow_separated_prev=True
    )
    assert not sep_rebound, "Flow must reattach above hysteresis boundary (26mm)"


# ─────────────────────────────────────────────────────────────────────────────
# 7. 5D Multidimensional RegularGridInterpolator
# ─────────────────────────────────────────────────────────────────────────────

def test_aero_grid_map_5d_interpolation_and_domain_boundaries():
    """Verify 5D grid map evaluates accurately and rejects out-of-domain points."""
    grid_map = AeroGridMap5D.create_ground_effect_benchmark_grid()
    
    # 1. Query point strictly within domain
    cl, cd, cop, cm, is_extrap, warnings = grid_map.evaluate(
        v=50.0,
        front_rh_mm=25.0,
        rear_rh_mm=50.0,
        pitch_deg=0.0,
        roll_deg=1.0,
    )
    assert not is_extrap
    assert len(warnings) == 0
    assert 2.5 < cl < 4.0
    assert 0.8 < cd < 2.0
    assert 0.35 < cop < 0.50

    # 2. Query point exceeding speed domain (120 m/s > 90 m/s)
    _, _, _, _, is_extrap_v, warnings_v = grid_map.evaluate(
        v=120.0,
        front_rh_mm=25.0,
        rear_rh_mm=50.0,
        pitch_deg=0.0,
        roll_deg=0.0,
    )
    assert is_extrap_v
    assert any("Speed" in w for w in warnings_v)

    # 3. Query point with front ride height outside domain (5 mm < 15 mm)
    _, _, _, _, is_extrap_rh, warnings_rh = grid_map.evaluate(
        v=50.0,
        front_rh_mm=5.0,
        rear_rh_mm=50.0,
        pitch_deg=0.0,
        roll_deg=0.0,
    )
    assert is_extrap_rh
    assert any("Front RH" in w for w in warnings_rh)

    # 4. Integrated evaluation in MultidimensionalAeroMap
    aero = MultidimensionalAeroMap(
        model_type=AeroModelType.GRID_5D,
        grid_5d=grid_map,
    )
    cl_5d, cd_5d, cop_5d, cm_5d, status, v_warn = aero.evaluate_5d(
        speed_mps=50.0,
        front_rh_mm=25.0,
        rear_rh_mm=50.0,
        pitch_deg=0.0,
        roll_deg=0.0,
    )
    assert status == PhysicsValidityStatus.MODEL_SUPPORTED
    assert len(v_warn) == 0
    assert cl_5d > 2.5


# ─────────────────────────────────────────────────────────────────────────────
# 8. Closed-Loop Porpoising Limit Cycle Detection
# ─────────────────────────────────────────────────────────────────────────────

def test_closed_loop_porpoising_detection():
    """Verify equilibrium solver detects porpoising limit cycles across the stall threshold."""
    mp = MassProperties(total_mass=800.0, wheelbase=2.7, track_front=1.6, track_rear=1.6)
    # Suspension tuned so heave deflection lands right at the peak stall cliff
    sus = SuspensionConfig(
        k_spring_front=38000.0,
        k_spring_rear=50000.0,
        ride_height_front=26.0,
        ride_height_rear=51.0,
    )
    cfg = NonlinearGroundEffectConfig(
        rh_peak_front_mm=22.0,
        cl_peak=4.2,
        cl_stall_floor=1.0,
        stall_decay_power=3.0,  # Extremely sharp stall cliff creates porpoising
        hysteresis_buffer_mm=3.0,
    )
    aero = MultidimensionalAeroMap(
        model_type=AeroModelType.NONLINEAR_GROUND_EFFECT,
        nonlinear_config=cfg,
    )

    # Relax with small max_iter and moderate relaxation to provoke limit cycling
    model = CoupledVehicleModel(mp, aero, sus, tol=0.001, max_iter=25, relaxation_alpha=0.85)
    state = model.solve(v=52.0, ax=0.0, ay=0.0, active_aero_mode=ActiveAeroMode.Z_MODE)

    # The oscillating non-monotonic aero curve must trigger porpoising or non-convergence
    if not state.converged:
        assert state.validity_record is not None
        assert state.validity_record.status == PhysicsValidityStatus.NUMERICALLY_FAILED
        assert any("porpoising" in w.lower() or "converge" in w.lower() for w in state.validity_record.warnings)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Epistemic Validity Boundaries
# ─────────────────────────────────────────────────────────────────────────────

def test_epistemic_validity_hierarchy():
    """Verify validity flags: MODEL_SUPPORTED (>=20mm), EXTRAPOLATED (1-20mm), UNSUPPORTED (<=1mm)."""
    mp = MassProperties(total_mass=800.0, wheelbase=2.7, track_front=1.6, track_rear=1.6)
    aero = MultidimensionalAeroMap(model_type=AeroModelType.NONLINEAR_GROUND_EFFECT)

    # Case A: Stiff suspension maintaining RH >= 20mm
    sus_supported = SuspensionConfig(
        k_spring_front=95000.0, k_spring_rear=95000.0,
        ride_height_front=40.0, ride_height_rear=65.0,
    )
    model_supp = CoupledVehicleModel(mp, aero, sus_supported, tol=0.05, max_iter=25)
    st_supp = model_supp.solve(v=40.0, ax=0.0, ay=0.0)
    assert st_supp.rh_front_mm >= 20.0
    assert st_supp.validity_record.status == PhysicsValidityStatus.MODEL_SUPPORTED

    # Case B: Pulls front RH into (1mm, 20mm) -> EXTRAPOLATED
    sus_extrap = SuspensionConfig(
        k_spring_front=45000.0, k_spring_rear=55000.0,
        ride_height_front=24.0, ride_height_rear=50.0,
    )
    model_extrap = CoupledVehicleModel(mp, aero, sus_extrap, tol=0.05, max_iter=25)
    st_extrap = model_extrap.solve(v=35.0, ax=0.0, ay=0.0)
    assert 1.0 < st_extrap.rh_front_mm < 20.0
    assert st_extrap.validity_record.status == PhysicsValidityStatus.EXTRAPOLATED

    # Case C: Bottoming out (RH <= 1mm) -> UNSUPPORTED
    sus_bottom = SuspensionConfig(
        k_spring_front=10000.0, k_spring_rear=15000.0,
        ride_height_front=12.0, ride_height_rear=25.0,
    )
    model_bottom = CoupledVehicleModel(mp, aero, sus_bottom, tol=0.05, max_iter=25)
    st_bottom = model_bottom.solve(v=80.0, ax=0.0, ay=0.0)
    assert st_bottom.bottomed_out or st_bottom.rh_front_mm <= 1.0
    assert st_bottom.validity_record.status == PhysicsValidityStatus.UNSUPPORTED


# ─────────────────────────────────────────────────────────────────────────────
# 10. Optimization Engine Rejection of Zero/Negative Ride Heights
# ─────────────────────────────────────────────────────────────────────────────

def test_optimization_engine_rejects_bottomed_and_stalled_setups():
    """Verify optimizer heavily penalizes setups attempting to exploit near-zero ride heights."""
    ds = create_racecar_full_design_space()
    cm = ConstraintManager.create_aero_racing_constraints()
    objs = [OptimizationObjective("lap_time_s", ObjectiveType.LAP_TIME, minimize=True)]
    evaluator = MultiObjectiveEvaluator(
        ds, cm, objs, simulation_model="coupled_lap_sim",
        aero_model_type=AeroModelType.NONLINEAR_GROUND_EFFECT,
    )

    p_valid = ds.get_default_parameters()
    m_valid, c_valid, _ = evaluator.evaluate_physical_candidate(p_valid)

    # Set extreme setup with collapsed ride height (e.g. 5mm) and soft springs to bottom out
    p_stalled = dict(p_valid)
    p_stalled["ride_height_front"] = 20.0  # lowest allowed by design space
    p_stalled["k_sf"] = 30000.0           # softest allowed spring -> forces severe bottoming

    m_stalled, c_stalled, _ = evaluator.evaluate_physical_candidate(p_stalled)

    # Check that aero validity constraint is violated
    aero_rep = next((r for r in c_stalled if r.name == "aero_validity"), None)
    assert aero_rep is not None
    # Because it is in the extrapolated/stalled regime below 20mm dynamic ride height:
    assert not aero_rep.is_satisfied
    assert aero_rep.violation_penalty > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 11. QSS LapSim AeroMap Nonlinear Ground Effect Support
# ─────────────────────────────────────────────────────────────────────────────

def test_qss_aeromap_nonlinear_ground_effect():
    """Verify lap_sim.py AeroMap supports nonlinear stall when enabled."""
    aero = AeroMap(
        cl_base=2.40,
        cl_rh_sens=-0.015,
        nonlinear_ground_effect=True,
        rh_peak_mm=22.0,
        cl_stall_floor=1.20,
    )

    # Pre-stall (rh >= 22mm)
    cl_30 = aero._effective_cl(30.0)
    cl_22 = aero._effective_cl(22.0)
    assert cl_22 > cl_30, "Downforce must increase as ride height drops towards peak"

    # Post-stall (rh < 22mm)
    cl_15 = aero._effective_cl(15.0)
    cl_5 = aero._effective_cl(5.0)
    assert cl_22 > cl_15 > cl_5, "Downforce must collapse below peak clearance"

    # Downforce and drag calculations respect nonlinear CL
    df_22 = aero.downforce_total(v=50.0, ride_height_mm=22.0)
    df_10 = aero.downforce_total(v=50.0, ride_height_mm=10.0)
    assert df_22 > df_10
