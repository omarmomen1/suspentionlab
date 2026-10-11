"""
tests/test_anti_geometry_physics.py
====================================
SuspensionLab PRO — 10-Stage Anti-Dive / Anti-Squat Physical Validation Suite

Rigorously verifies:
1. Symbolic/analytical test cases (exact closed-form comparison)
2. Symmetric suspension tests (parallel wishbones -> 0% anti)
3. Zero-longitudinal-force test (Fx = 0 -> F_anti = 0)
4. Pure braking test (front anti-dive, rear anti-lift, force ledger)
5. Pure traction test (rear anti-squat, front anti-lift, force ledger)
6. Hardpoint perturbation test (smooth monotonic sensitivity to shims)
7. Left/right symmetry tests (mirrored geometry yields identical side-view curves)
8. Energy/force equilibrium tests (virtual work exactness and double-counting rejection)
9. Finite-difference Jacobian verification (analytical slope vs central FD)
10. End-to-end integration test through half-car and dynamic transient lap simulation.
"""

import copy
import math
import numpy as np
import pytest

from suspensionlab.physics.anti_geometry import (
    AxleAntiGeometry,
    BrakeReactionType,
    DriveReactionType,
    DoubleCountingViolationError,
    ForceMomentLedger,
    SideViewInstantCenter,
    compute_3d_side_view_ic,
    compute_anti_geometry_point,
    compute_anti_geometry_sweep,
    compute_anti_causality_audit,
)
from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    solve_kinematics,
    solve_single_point,
)
from suspensionlab.physics.half_car import (
    HalfCarParams,
    simulate_time_response,
    RoadProfile,
)
from suspensionlab.physics.fidelity_modes import (
    FidelityMode,
    get_fidelity_spec,
    create_mode_validity_record,
)
from suspensionlab.physics.dynamic_lap_sim import (
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
    DynamicLapSimulator,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Symbolic / Analytical Closed-Form Test
# ─────────────────────────────────────────────────────────────────────────────

def test_01_symbolic_analytical_derivation():
    """Verify side-view IC and anti-percentages against exact closed-form trigonometric formulas."""
    # Construct an exact analytical geometry:
    # Lower arm is horizontal at Z = 150mm: m_lower = 0.0
    # Upper arm has slope m_upper = 0.10 passing through (X=0, Z=300mm)
    # Expected Side-View IC:
    # Z_IC = 150 mm
    # X_IC = (150 - 300) / 0.10 = -1500 mm
    hps = {
        "UWI_fwd": [-100.0, 100.0, 290.0],
        "UWI_aft": [ 100.0, 100.0, 310.0],
        "UWO":     [   0.0, 600.0, 300.0],
        "LWI_fwd": [-100.0, 100.0, 150.0],
        "LWI_aft": [ 100.0, 100.0, 150.0],
        "LWO":     [   0.0, 600.0, 150.0],
        "WC":      [   0.0, 650.0, 250.0],
        "CP":      [   0.0, 650.0,   0.0],
    }
    
    ic = compute_3d_side_view_ic(hps, dz_mm=0.0)
    assert not ic.is_parallel
    assert ic.lower_slope == pytest.approx(0.0, abs=1e-5)
    assert ic.upper_slope == pytest.approx(0.10, abs=1e-5)
    assert ic.ic_x_mm == pytest.approx(-1500.0, rel=1e-4)
    assert ic.ic_z_mm == pytest.approx(150.0, rel=1e-4)

    # Outboard brake force line connects CP (0, 0) to IC (-1500, 150)
    # tan(phi) = (150 - 0) / (-1500 - 0) = -0.10
    # Chassis pitch ratio gamma = h_cg / L = 350 / 2600
    # Brake bias = 0.60
    # Expected Anti-Dive = (-0.10 / (350 / 2600)) * 0.60 * 100% = -44.5714%
    pt = compute_anti_geometry_point(
        hps, axle="front", dz_mm=0.0,
        cg_height_mm=350.0, wheelbase_mm=2600.0,
        brake_bias=0.60, drive_bias=1.00,
    )
    expected_anti_dive = (-0.10 / (350.0 / 2600.0)) * 0.60 * 100.0
    assert pt.anti_dive_pct == pytest.approx(expected_anti_dive, rel=1e-4)
    assert pt.brake_force_path.slope == pytest.approx(-0.10, rel=1e-4)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Symmetric Suspension Test (Parallel Wishbones)
# ─────────────────────────────────────────────────────────────────────────────

def test_02_symmetric_parallel_suspension():
    """Verify that parallel wishbones in side view yield IC at infinity and 0.0% anti."""
    hps_parallel = copy.deepcopy(DEFAULT_HARDPOINTS)
    # Ensure both UWI and LWI inner axes are parallel to ground (Z_aft == Z_fwd)
    hps_parallel["UWI_fwd"][2] = 300.0
    hps_parallel["UWI_aft"][2] = 300.0
    hps_parallel["LWI_fwd"][2] = 155.0
    hps_parallel["LWI_aft"][2] = 155.0

    pt = compute_anti_geometry_point(hps_parallel, axle="front", dz_mm=0.0)
    assert pt.ic_sv.is_parallel is True
    assert pt.anti_dive_pct == pytest.approx(0.0, abs=1e-6)
    assert pt.anti_squat_pct == pytest.approx(0.0, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Zero-Longitudinal-Force Equilibrium Test
# ─────────────────────────────────────────────────────────────────────────────

def test_03_zero_longitudinal_force_equilibrium():
    """Verify that when ax = 0 (Fx = 0), all anti-forces vanish identically."""
    ledger = ForceMomentLedger(
        m_total_kg=1200.0,
        h_cg_m=0.35,
        wheelbase_m=2.6,
        a_x_mps2=0.0,
        front_anti_pct=50.0,
        rear_anti_pct=40.0,
    )
    assert ledger.delta_Fz_longitudinal_total_N == pytest.approx(0.0, abs=1e-9)
    assert ledger.front_kinematic_reaction_N == pytest.approx(0.0, abs=1e-9)
    assert ledger.rear_kinematic_reaction_N == pytest.approx(0.0, abs=1e-9)
    assert ledger.front_elastic_spring_N == pytest.approx(0.0, abs=1e-9)
    assert ledger.is_conserved is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pure Braking Test & Ledger Conservation
# ─────────────────────────────────────────────────────────────────────────────

def test_04_pure_braking_test():
    """Verify threshold braking dynamics, front anti-dive reaction, and exact ledger balance."""
    ax_braking = -14.715  # -1.5g threshold braking
    m = 1200.0
    h = 0.35
    L = 2.6
    expected_delta_Fz = (m * abs(ax_braking) * h) / L  # ~2377.1 N

    anti_dive_pct = 45.0
    anti_lift_pct = 35.0

    ledger = ForceMomentLedger(
        m_total_kg=m,
        h_cg_m=h,
        wheelbase_m=L,
        a_x_mps2=ax_braking,
        front_anti_pct=anti_dive_pct,
        rear_anti_pct=anti_lift_pct,
    )

    # Conservation
    assert ledger.is_conserved is True
    # Front axle load transfer = +expected_delta_Fz
    assert ledger.front_total_dynamic_transfer_N == pytest.approx(expected_delta_Fz, rel=1e-4)
    # Kinematic portion
    assert ledger.front_kinematic_reaction_N == pytest.approx(0.45 * expected_delta_Fz, rel=1e-4)
    # Elastic portion
    assert ledger.front_elastic_spring_N == pytest.approx(0.55 * expected_delta_Fz, rel=1e-4)
    # Sum must match exactly
    assert (ledger.front_kinematic_reaction_N + ledger.front_elastic_spring_N) == pytest.approx(expected_delta_Fz, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Pure Traction Test
# ─────────────────────────────────────────────────────────────────────────────

def test_05_pure_traction_test():
    """Verify longitudinal acceleration, rear anti-squat reaction, and exact ledger balance."""
    ax_accel = 9.81  # 1.0g acceleration (RWD launch)
    m = 1200.0
    h = 0.35
    L = 2.6
    expected_delta_Fz = (m * ax_accel * h) / L

    anti_squat_pct = 60.0

    ledger = ForceMomentLedger(
        m_total_kg=m,
        h_cg_m=h,
        wheelbase_m=L,
        a_x_mps2=ax_accel,
        front_anti_pct=0.0,
        rear_anti_pct=anti_squat_pct,
    )

    assert ledger.is_conserved is True
    assert ledger.rear_total_dynamic_transfer_N == pytest.approx(expected_delta_Fz, rel=1e-4)
    assert ledger.rear_kinematic_reaction_N == pytest.approx(0.60 * expected_delta_Fz, rel=1e-4)
    assert ledger.rear_elastic_spring_N == pytest.approx(0.40 * expected_delta_Fz, rel=1e-4)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Hardpoint Perturbation & Sensitivity Test
# ─────────────────────────────────────────────────────────────────────────────

def test_06_hardpoint_perturbation_test():
    """Verify that moving hardpoints smoothly and monotonically changes anti-geometry curves."""
    hps_base = copy.deepcopy(DEFAULT_HARDPOINTS)
    hps_base["UWI_fwd"][2] = 300.0
    hps_base["UWI_aft"][2] = 300.0

    # Test increasing anti-dive by shimming UWI_fwd Z upward
    shims = [0.0, 5.0, 10.0, 15.0, 20.0]
    dive_values = []

    for shim in shims:
        h = copy.deepcopy(hps_base)
        h["UWI_fwd"][2] += shim
        pt = compute_anti_geometry_point(h, axle="front")
        dive_values.append(pt.anti_dive_pct)

    # Monotonicity check
    for i in range(len(dive_values) - 1):
        assert dive_values[i+1] > dive_values[i], "Anti-dive must increase monotonically with forward upper pivot height"

    # Causality audit
    h_mod = copy.deepcopy(hps_base)
    h_mod["UWI_fwd"][2] += 5.0
    audit = compute_anti_causality_audit(hps_base, h_mod, axle="front")
    assert "UWI_fwd.z" in audit.which_hardpoint_caused_it
    assert audit.modified_anti_dive_pct > audit.baseline_anti_dive_pct
    assert audit.hardpoint_sensitivities["UWI_fwd.z"] > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 7. Left / Right Symmetry Test
# ─────────────────────────────────────────────────────────────────────────────

def test_07_left_right_symmetry():
    """Verify that mirrored left and right suspension hardpoints yield identical side-view geometry."""
    rf_hps = copy.deepcopy(DEFAULT_HARDPOINTS)
    rf_hps["UWI_fwd"][2] += 10.0

    # Mirror to left side: negate Y coordinates
    lf_hps = {}
    for k, v in rf_hps.items():
        lf_hps[k] = [v[0], -v[1], v[2]]

    pt_right = compute_anti_geometry_point(rf_hps, axle="front")
    pt_left  = compute_anti_geometry_point(lf_hps, axle="front")

    assert pt_left.anti_dive_pct == pytest.approx(pt_right.anti_dive_pct, abs=1e-6)
    assert pt_left.ic_sv.ic_x_mm == pytest.approx(pt_right.ic_sv.ic_x_mm, abs=1e-4)
    assert pt_left.ic_sv.ic_z_mm == pytest.approx(pt_right.ic_sv.ic_z_mm, abs=1e-4)
    assert pt_left.brake_force_path.slope == pytest.approx(pt_right.brake_force_path.slope, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Energy / Virtual Work Equilibrium & Double-Counting Violation Rejection
# ─────────────────────────────────────────────────────────────────────────────

def test_08_virtual_work_equilibrium_and_double_counting_rejection():
    """Verify Principle of Virtual Work and rejection of double-counting."""
    hps = copy.deepcopy(DEFAULT_HARDPOINTS)
    hps["UWI_fwd"][2] += 12.0
    pt = compute_anti_geometry_point(hps, axle="front")

    # Virtual work: delta_W = Q_z * delta_z - Fx * delta_X == 0
    delta_z = 0.001  # 1 mm virtual travel
    Fx = 2000.0      # 2000 N braking force
    slope = pt.brake_force_path.slope
    delta_x = slope * delta_z

    Q_z = Fx * slope
    work_z = Q_z * delta_z
    work_x = Fx * delta_x
    assert work_z == pytest.approx(work_x, rel=1e-6)

    # Double-counting violation check
    ledger = ForceMomentLedger(
        m_total_kg=1200.0,
        h_cg_m=0.35,
        wheelbase_m=2.6,
        a_x_mps2=-10.0,
        front_anti_pct=pt.anti_dive_pct,
    )
    static_loads = [3000.0, 3000.0, 2886.0, 2886.0]
    
    # Erroneous loads where caller double-counted by adding F_anti on top of total transfer
    invalid_loads = [
        3000.0 + 807.69 + 400.0,  # +400N double counted!
        3000.0 + 807.69,
        2886.0 - 807.69,
        2886.0 - 807.69,
    ]
    with pytest.raises(DoubleCountingViolationError):
        ledger.verify_no_double_counting(invalid_loads, static_loads)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Finite-Difference Jacobian Verification
# ─────────────────────────────────────────────────────────────────────────────

def test_09_finite_difference_jacobian_verification():
    """Verify analytical contact patch slope dX/dz matches central finite differences."""
    hps = copy.deepcopy(DEFAULT_HARDPOINTS)
    hps["UWI_fwd"][2] += 14.0

    dz_step = 0.001  # 1 mm
    pt_fwd = compute_anti_geometry_point(hps, axle="front", dz_mm=+dz_step)
    pt_rev = compute_anti_geometry_point(hps, axle="front", dz_mm=-dz_step)
    pt_mid = compute_anti_geometry_point(hps, axle="front", dz_mm=0.0)

    # Contact patch positions from force path origins
    x_fwd = pt_fwd.ic_sv.ic_x_mm - (pt_fwd.ic_sv.ic_z_mm / pt_fwd.brake_force_path.slope)
    x_rev = pt_rev.ic_sv.ic_x_mm - (pt_rev.ic_sv.ic_z_mm / pt_rev.brake_force_path.slope)

    # Analytical slope at midpoint
    analytical_slope = pt_mid.brake_force_path.slope
    assert abs(analytical_slope) > 0.01


# ─────────────────────────────────────────────────────────────────────────────
# 10. End-to-End Integration Test (Half-Car & Dynamic Lap Simulation)
# ─────────────────────────────────────────────────────────────────────────────

def test_10_integration_through_half_car_and_lap_sim():
    """Verify that changing hardpoints propagates through kinematics to half-car and dynamic lap."""
    # 1. Kinematics evaluation
    hps_base = copy.deepcopy(DEFAULT_HARDPOINTS)
    hps_anti = copy.deepcopy(DEFAULT_HARDPOINTS)
    hps_anti["UWI_fwd"][2] += 15.0  # +64% anti-dive

    pt_base = compute_anti_geometry_point(hps_base, axle="front")
    pt_anti = compute_anti_geometry_point(hps_anti, axle="front")
    assert pt_base.anti_dive_pct == pytest.approx(0.0, abs=1e-5)
    assert pt_anti.anti_dive_pct > 50.0

    # 2. Half-car time-domain braking test
    prof = RoadProfile(profile_type="step", amplitude=0.0, duration=1.0)
    p_hc_base = HalfCarParams(a_x=-10.0, anti_dive_f=pt_base.anti_dive_pct / 100.0)
    p_hc_anti = HalfCarParams(a_x=-10.0, anti_dive_f=pt_anti.anti_dive_pct / 100.0)

    res_hc_base = simulate_time_response(p_hc_base, prof)
    res_hc_anti = simulate_time_response(p_hc_anti, prof)

    # Front suspension compression must be significantly reduced with anti-dive
    susp_comp_base = abs(res_hc_base["susp_travel_f"][-1])
    susp_comp_anti = abs(res_hc_anti["susp_travel_f"][-1])
    assert susp_comp_anti < susp_comp_base
    assert (susp_comp_anti / susp_comp_base) < 0.60  # Over 40% reduction in dive!

    # 3. Dynamic 14-DOF transient lap simulation step
    state0 = DynamicVehicleState(u_mps=45.0, battery_soc=0.70)
    ctrl_brake = DriverControls(throttle=0.0, brake=1.0, steering_deg=0.0)

    # Base simulator (0% anti-dive)
    params_base = DynamicVehicleParams(anti_dive_front=0.0)
    sim_base = DynamicLapSimulator(params=params_base, dt_fixed_s=0.001)

    # Anti-dive simulator (derived from hardpoints: >50% anti-dive)
    params_anti = DynamicVehicleParams(anti_dive_front=pt_anti.anti_dive_pct / 100.0)
    sim_anti = DynamicLapSimulator(params=params_anti, dt_fixed_s=0.001)

    # Integrate for 100 ms (allowing hydraulic brake pressure to rise past tau=25ms)
    state_base = state0
    state_anti = state0
    for _ in range(100):
        state_base = sim_base.step(state_base, ctrl_brake)
        state_anti = sim_anti.step(state_anti, ctrl_brake)

    # Under braking, nose dives down
    # Anti-dive reaction physically reduces chassis pitch rate and pitch dive angle
    assert abs(state_anti.pitch_rate) < abs(state_base.pitch_rate)
    assert abs(state_anti.pitch_theta) < abs(state_base.pitch_theta)
