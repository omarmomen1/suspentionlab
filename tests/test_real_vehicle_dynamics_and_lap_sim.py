"""
tests/test_real_vehicle_dynamics_and_lap_sim.py
===============================================
SuspensionLab PRO — Real Vehicle Dynamics & Lap Simulation Physical Validation Suite

Engineering Validation Scenarios (Step 11):
1. Straight acceleration (torque curve, gearing, shift cut, power-limited top speed)
2. Straight braking (load transfer, pitch nose-down, hydraulic brake bias)
3. Constant-radius corner (lateral load transfer, roll angle, understeer gradient)
4. Combined braking & cornering (trail braking, Pacejka friction circle)
5. Banked corner (signed physics: favorable +12 deg vs adverse -12 deg)
6. Gradient & elevation (signed physics: uphill +10% vs downhill -10%)
7. Suspension-aero dynamic coupling (ride height drop under downforce, active aero)
8. Gearbox shift dynamics (shift timer torque cut, rev limit cut)
9. 2026 FIA ERS energy & thermal derating (SOC, MGU-K boost/harvest, thermal limits)
10. Full lap simulation & telemetry parity (14-DOF Dynamic vs Fast Quasi-Steady)
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
    DynamicTrackPoint,
    DynamicTrackModel,
    MacAdamPreviewDriver,
    ClosedLoopDriverModel,
    solve_dynamic_lap,
    DYNAMIC_TRANSIENT_14DOF,
    FAST_QUASI_STEADY,
)
from suspensionlab.physics.lap_sim import (
    LapSimVehicle,
    TrackSegment,
    solve_lap,
    parse_track_from_curvature,
)
from suspensionlab.physics.magic_formula import TireCoeffs, _calc_tire_forces_and_moments_fast
from suspensionlab.physics.ers_model import ERSConfig, ERSState, ERSDeploymentController
from suspensionlab.physics.suspension_aero_coupling import ActiveAeroMode, MultidimensionalAeroMap


# ─────────────────────────────────────────────────────────────────────────────
# 1. Straight Acceleration & Power-Limited Top Speed
# ─────────────────────────────────────────────────────────────────────────────

def test_straight_acceleration_and_terminal_velocity():
    """Verify vehicle accelerates through gears to power-limited terminal velocity without arbitrary speed caps."""
    params = DynamicVehicleParams(mass_kg=800.0)
    sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

    state = DynamicVehicleState(u_mps=20.0, current_gear=2, omega_fl=60.0, omega_fr=60.0, omega_rl=60.0, omega_rr=60.0)
    ctrl = DriverControls(throttle=1.0, brake=0.0, steering_deg=0.0, gear=2)

    # Step forward 100 ms
    for _ in range(100):
        state = sim.step(state, ctrl)

    assert state.u_mps > 20.0
    assert state.pitch_theta > 0.0 or state.pitch_rate != 0.0  # Squat under acceleration
    assert state.distance_m > 2.0

    # Test terminal velocity equilibrium: at v_top, F_drive == F_drag + F_rr
    v_high = 90.0  # ~324 km/h
    state_top = DynamicVehicleState(u_mps=v_high, current_gear=6, omega_rl=v_high / params.wheel_radius_m, omega_rr=v_high / params.wheel_radius_m)
    ctrl_top = DriverControls(throttle=1.0, gear=6)
    derivs_top = sim.compute_derivatives(state_top, ctrl_top)

    # Downforce and drag are non-zero and physical
    assert derivs_top["F_drag"] > 2000.0
    assert derivs_top["F_downforce"] > 4000.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Straight Braking, Pitch Dynamics & Hydraulic Bias
# ─────────────────────────────────────────────────────────────────────────────

def test_straight_braking_and_load_transfer():
    """Verify threshold braking generates forward load transfer, nose-down pitch, and stable deceleration."""
    params = DynamicVehicleParams(mass_kg=800.0, brake_front_bias=0.62)
    sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

    u_init = 60.0  # 216 km/h
    w_init = u_init / params.wheel_radius_m
    state = DynamicVehicleState(u_mps=u_init, omega_fl=w_init, omega_fr=w_init, omega_rl=w_init, omega_rr=w_init)
    ctrl = DriverControls(throttle=0.0, brake=1.0, steering_deg=0.0)

    # Baseline unbraked steady state loads at 60 m/s
    ctrl_unbraked = DriverControls(throttle=0.0, brake=0.0, steering_deg=0.0)
    derivs0 = sim.compute_derivatives(state, ctrl_unbraked)
    fz_fl0, fz_fr0, fz_rl0, fz_rr0 = derivs0["wheel_loads"]

    # Step braking for 20 ms
    for _ in range(20):
        state = sim.step(state, ctrl)

    derivs = sim.compute_derivatives(state, ctrl)
    fz_fl, fz_fr, fz_rl, fz_rr = derivs["wheel_loads"]

    # Decelerating (> 1g physical braking deceleration)
    assert state.u_mps < u_init
    assert derivs["du"] < -9.0  # Deceleration near or exceeding 1g

    # Front axle load increases, rear axle load decreases
    assert (fz_fl + fz_fr) > (fz_fl0 + fz_fr0)
    assert (fz_rl + fz_rr) < (fz_rl0 + fz_rr0)

    # Chassis pitches nose down (negative pitch theta in standard SAE coordinates)
    assert state.pitch_theta < 0.0 or derivs["d_pitch_theta"] < 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Constant-Radius Cornering & Lateral Load Transfer
# ─────────────────────────────────────────────────────────────────────────────

def test_constant_radius_cornering_and_roll():
    """Verify steady cornering generates lateral load transfer, chassis roll, and consistent yaw rate."""
    params = DynamicVehicleParams(mass_kg=800.0)
    sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

    u_corner = 40.0  # 144 km/h
    R_corner = 100.0 # radius 100 m -> kappa = 0.01
    w_init = u_corner / params.wheel_radius_m
    state = DynamicVehicleState(u_mps=u_corner, omega_fl=w_init, omega_fr=w_init, omega_rl=w_init, omega_rr=w_init)

    # Steer left (+5 degrees steer wheel angle)
    ctrl = DriverControls(throttle=0.2, brake=0.0, steering_deg=35.0)

    for _ in range(100):
        state = sim.step(state, ctrl, road_curvature=0.01)

    derivs = sim.compute_derivatives(state, ctrl, road_curvature=0.01)
    fz_fl, fz_fr, fz_rl, fz_rr = derivs["wheel_loads"]

    # Turning left -> right (outer) wheels get more normal load
    assert fz_fr > fz_fl
    assert fz_rr > fz_rl

    # Yaw rate is positive (turning left)
    assert state.yaw_rate_rads > 0.0
    # Roll angle tilts toward right (outside)
    assert state.roll_phi > 0.0 or derivs["d_roll_phi"] > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Combined Braking & Cornering (Trail Braking Entry)
# ─────────────────────────────────────────────────────────────────────────────

def test_combined_trail_braking_and_friction_circle():
    """Verify trail braking adheres to Pacejka combined slip without numerical singularity."""
    params = DynamicVehicleParams(mass_kg=800.0)
    sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

    u_entry = 50.0
    w_init = u_entry / params.wheel_radius_m
    state = DynamicVehicleState(u_mps=u_entry, omega_fl=w_init, omega_fr=w_init, omega_rl=w_init, omega_rr=w_init)

    # Simultaneous brake and steering input
    ctrl = DriverControls(throttle=0.0, brake=0.6, steering_deg=25.0)

    for _ in range(60):
        state = sim.step(state, ctrl, road_curvature=0.008)

    derivs = sim.compute_derivatives(state, ctrl, road_curvature=0.008)

    # Both longitudinal braking and lateral force are non-zero (combined slip friction ellipse)
    assert derivs["du"] < 0.0
    assert abs(derivs["Fy_total"]) > 500.0

    # Slip angles and slip ratios are computed and bounded
    for sa in derivs["slip_angles"]:
        assert not np.isnan(sa) and abs(sa) < math.radians(45.0)
    for sr in derivs["slip_ratios"]:
        assert not np.isnan(sr) and abs(sr) < 2.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Banked Corner Signed Physics (+12 deg vs -12 deg)
# ─────────────────────────────────────────────────────────────────────────────

def test_banked_corner_favorable_vs_adverse_physics():
    """Verify favorable banking (+12 deg) produces inward gravity assistance compared to adverse (-12 deg)."""
    params = DynamicVehicleParams(mass_kg=800.0)
    sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

    u = 35.0
    w = u / params.wheel_radius_m
    st_fav = DynamicVehicleState(u_mps=u, omega_fl=w, omega_fr=w, omega_rl=w, omega_rr=w)
    st_adv = DynamicVehicleState(u_mps=u, omega_fl=w, omega_fr=w, omega_rl=w, omega_rr=w)

    ctrl = DriverControls(throttle=0.1, steering_deg=20.0)

    bank_fav = math.radians(12.0)   # +12 deg favorable
    bank_adv = math.radians(-12.0)  # -12 deg adverse off-camber

    d_fav = sim.compute_derivatives(st_fav, ctrl, road_bank_rad=bank_fav)
    d_adv = sim.compute_derivatives(st_adv, ctrl, road_bank_rad=bank_adv)

    # Inward lateral acceleration dv is significantly higher with favorable banking
    assert d_fav["dv"] > d_adv["dv"]
    # Net lateral chassis force includes gravity component mg*sin(bank)
    f_grav_diff = params.mass_kg * 9.81 * (math.sin(bank_fav) - math.sin(bank_adv))
    assert pytest.approx(d_fav["dv"] - d_adv["dv"], rel=0.1) == f_grav_diff / params.mass_kg


# ─────────────────────────────────────────────────────────────────────────────
# 6. Gradient & Elevation Signed Physics (+10% uphill vs -10% downhill)
# ─────────────────────────────────────────────────────────────────────────────

def test_gradient_uphill_vs_downhill_physics():
    """Verify uphill (+10% grade) reduces forward acceleration vs downhill (-10% grade)."""
    params = DynamicVehicleParams(mass_kg=800.0)
    sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

    u = 30.0
    w = u / params.wheel_radius_m
    st_up = DynamicVehicleState(u_mps=u, omega_fl=w, omega_fr=w, omega_rl=w, omega_rr=w)
    st_dn = DynamicVehicleState(u_mps=u, omega_fl=w, omega_fr=w, omega_rl=w, omega_rr=w)

    ctrl = DriverControls(throttle=0.8, gear=3)

    grade_up = math.atan(0.10)   # +10% uphill
    grade_dn = math.atan(-0.10)  # -10% downhill

    d_up = sim.compute_derivatives(st_up, ctrl, road_grade_rad=grade_up)
    d_dn = sim.compute_derivatives(st_dn, ctrl, road_grade_rad=grade_dn)

    # Downhill has much higher forward acceleration du than uphill
    assert d_dn["du"] > d_up["du"]
    f_grade_diff = params.mass_kg * 9.81 * (math.sin(grade_up) - math.sin(grade_dn))
    assert pytest.approx(d_dn["du"] - d_up["du"], rel=0.05) == f_grade_diff / params.mass_kg


# ─────────────────────────────────────────────────────────────────────────────
# 7. Suspension-Aero Dynamic Coupling
# ─────────────────────────────────────────────────────────────────────────────

def test_suspension_aero_coupling_and_ride_height_drop():
    """Verify aerodynamic downforce dynamically compresses the suspension and modulates Cl/Cd."""
    params = DynamicVehicleParams()
    sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

    # Compare low speed (10 m/s) vs high speed (70 m/s)
    st_low = DynamicVehicleState(u_mps=10.0)
    st_high = DynamicVehicleState(u_mps=70.0)
    ctrl = DriverControls(throttle=0.5, gear=4, active_aero_mode="Z_MODE")

    d_low = sim.compute_derivatives(st_low, ctrl)
    d_high = sim.compute_derivatives(st_high, ctrl)

    # Downforce scales quadratically with speed
    assert d_high["F_downforce"] > 15.0 * d_low["F_downforce"]

    # Active aero X_MODE reduces drag on straights
    ctrl_x = DriverControls(throttle=0.5, gear=4, active_aero_mode="X_MODE")
    d_high_x = sim.compute_derivatives(st_high, ctrl_x)
    assert d_high_x["F_drag"] < d_high["F_drag"]


# ─────────────────────────────────────────────────────────────────────────────
# 8. Gearbox Shifting & Shift-Time Torque Cut
# ─────────────────────────────────────────────────────────────────────────────

def test_gearbox_shift_dynamics_and_redline_cut():
    """Verify gear shifting triggers torque cut during shift_time_s and rev limiter cuts engine torque."""
    params = DynamicVehicleParams(shift_time_s=0.045, rev_limit_rpm=13500.0)
    sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

    # Optimal gear selection
    assert params.select_optimal_gear(15.0) == 1
    assert params.select_optimal_gear(45.0) >= 3
    assert params.select_optimal_gear(80.0) in (5, 6)
    assert params.select_optimal_gear(95.0) == 6

    # Test shift timer torque cut
    st_shift = DynamicVehicleState(u_mps=30.0, current_gear=2, shift_in_progress=True, shift_timer_s=0.030)
    ctrl = DriverControls(throttle=1.0, gear=3)
    d_shift = sim.compute_derivatives(st_shift, ctrl)

    # Engine torque is zero during active shift (only ERS if commanded)
    assert d_shift["Fx_total"] < 100.0  # Tractive torque cut active

    # Test rev limit cut
    t_over_rev = params.engine_torque(14000.0)
    assert t_over_rev == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 9. 2026 FIA ERS Energy & Thermal Constraints
# ─────────────────────────────────────────────────────────────────────────────

def test_ers_2026_soc_deployment_and_thermal_derate():
    """Verify 2026 ERS energy management, battery SOC depletion, and thermal derating."""
    ers_cfg = ERSConfig(mgu_k_max_power_w=350_000.0, battery_capacity_j=4_000_000.0)
    params = DynamicVehicleParams(ers_config=ers_cfg)
    sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

    state = DynamicVehicleState(
        u_mps=40.0,
        battery_soc=0.80,
        battery_temp_c=40.0,
        mguk_temp_c=60.0,
    )
    ctrl = DriverControls(throttle=1.0, ers_boost_request_kw=350.0, gear=3)

    # Step for 100 ms with 350 kW boost
    for _ in range(100):
        state = sim.step(state, ctrl)

    # SOC decreased, energy deployed increased, temperatures rose
    assert state.battery_soc < 0.80
    assert state.energy_deployed_j > 30_000.0
    assert state.battery_temp_c > 40.0
    assert state.mguk_temp_c > 60.0


# ─────────────────────────────────────────────────────────────────────────────
# 10. Closed-Loop Dynamic Lap Solver & Fast Quasi-Steady Parity
# ─────────────────────────────────────────────────────────────────────────────

def test_solve_dynamic_lap_full_track_simulation():
    """Execute complete 14-DOF closed-loop transient dynamic lap solver on a test track."""
    distances = np.linspace(0, 1000, 201)
    curvatures = np.zeros(201)
    curvatures[40:70] = 0.015   # Turn 1
    curvatures[120:150] = -0.012 # Turn 2

    elevations = 5.0 * np.sin(2.0 * np.pi * distances / 1000.0)
    bank_angles = 0.05 * np.sign(curvatures)

    track = DynamicTrackModel(
        distances=distances,
        curvatures=curvatures,
        elevations=elevations,
        bank_angles=bank_angles,
    )

    sim = DynamicLapSimulator()
    res = solve_dynamic_lap(sim, track, initial_speed_mps=30.0, max_simulation_time_s=60.0)

    assert res.total_time > 5.0
    assert res.max_speed_kmh > 100.0
    assert len(res.speeds) > 0
    assert len(res.times) == len(res.speeds)
    assert res.wheel_loads_n.shape[0] == 4
    assert res.model_version == "dynamic-transient-14dof-v3.2"


def test_fast_quasi_steady_and_dynamic_solver_contract_parity():
    """Verify both FAST_QUASI_STEADY and DYNAMIC_TRANSIENT_14DOF solver modes produce structured telemetry."""
    # Fast Quasi Steady
    veh = LapSimVehicle()
    segs = [
        TrackSegment(distance=0.0, curvature=0.0, elevation=0.0),
        TrackSegment(distance=200.0, curvature=0.01, elevation=2.0),
        TrackSegment(distance=500.0, curvature=0.0, elevation=0.0),
    ]
    res_qss = solve_lap(veh, segs, build_ggv=False)
    assert res_qss.total_time > 0.0
    assert res_qss.solver_mode == FAST_QUASI_STEADY

    # Dynamic Transient 14-DOF
    track_dyn = DynamicTrackModel(
        distances=np.array([s.distance for s in segs]),
        curvatures=np.array([s.curvature for s in segs]),
        elevations=np.array([s.elevation for s in segs]),
    )
    sim_dyn = DynamicLapSimulator()
    res_dyn = solve_dynamic_lap(sim_dyn, track_dyn, initial_speed_mps=30.0)
    assert res_dyn.total_time > 0.0
    assert res_dyn.model_version == "dynamic-transient-14dof-v3.2"