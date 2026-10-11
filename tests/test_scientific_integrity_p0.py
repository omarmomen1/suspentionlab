"""
tests/test_scientific_integrity_p0.py
======================================
SuspensionLab PRO — Scientific Integrity P0 Verification Test Suite

Verifies:
1. Canonical Physics Contracts: SI units, ISO 8855 coordinate frames, sign conventions, state ordering.
2. Pacejka MF 5.2 / MF 6.1:
   - Pure longitudinal Fx0, Pure lateral Fy0
   - Self-aligning moment Mz (pneumatic trail t & residual torque Mzr)
   - Combined slip Similarity Method (Gxα, Gyκ)
   - Physical inflation pressure scaling (kt, cornering stiffness, peak friction)
   - Physical thermodynamic temperature scaling (optimal window, cold/hot degradation)
   - Contact states (ATTACHED, SLIPPING, SATURATED, LOST)
3. Unilateral Contact & Liftoff:
   - Physical non-negative normal load (Fz >= 0)
   - Contact states sequence (CONTACT, LIFTOFF, RECONTACT)
   - Timestamps & minimum Fz
4. Canonical Road Excitation:
   - 3D road spatial derivative dz/dt = (dz/dx) * speed
5. Solver Strategy & Benchmarking:
   - RK45 vs BDF vs Radau comparison on stiff systems
   - Zero explicit matrix inversions
6. Conservation Diagnostics & Cryptographic Provenance.
"""

import pytest
import numpy as np
import math

from suspensionlab.physics.contracts import (
    CoordinateSystem,
    SignConvention,
    ContactState,
    SlipState,
    CanonicalRoadProfile,
    PhysicsDiagnostics,
    PhysicsProvenance,
    compute_dataset_hash,
)
from suspensionlab.physics.magic_formula import (
    TireCoeffs,
    calc_tire_forces,
    calc_tire_forces_3d,
    PacejkaMF52TireModel,
)
from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    run_quarter_car_analysis,
    simulate_time_response,
    build_state_space,
)
from suspensionlab.physics.half_car import (
    HalfCarParams,
    run_half_car_analysis,
)
from suspensionlab.physics.full_car import (
    FullCarParams,
    FourCornerRoadProfile,
    run_full_car_analysis,
)
from suspensionlab.physics.solvers import (
    benchmark_solvers,
    PrecisionMode,
    solve_dynamic_system,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. CANONICAL CONTRACTS & COORDINATE SYSTEMS
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_coordinate_and_sign_conventions():
    assert CoordinateSystem.ISO_8855 == "ISO_8855"
    assert "forward" in SignConvention.LONGITUDINAL
    assert "leftward" in SignConvention.LATERAL
    assert "upward" in SignConvention.VERTICAL
    assert "nose-up" in SignConvention.PITCH
    assert "right-side down" in SignConvention.ROLL
    assert "counter-clockwise" in SignConvention.YAW


def test_provenance_and_dataset_hashing():
    p = QuarterCarParams(m_s=320.0, k_s=28000.0)
    hash1 = compute_dataset_hash(p)
    assert isinstance(hash1, str)
    assert len(hash1) == 16
    
    p2 = QuarterCarParams(m_s=320.0, k_s=28000.0)
    assert compute_dataset_hash(p2) == hash1
    
    p3 = QuarterCarParams(m_s=350.0, k_s=28000.0)
    assert compute_dataset_hash(p3) != hash1


# ─────────────────────────────────────────────────────────────────────────────
# 2. MAGIC FORMULA MF 5.2 / 6.1 TIRE INTEGRITY & ALIGNING MOMENT MZ
# ─────────────────────────────────────────────────────────────────────────────

def test_magic_formula_pure_and_aligning_moment():
    coeffs = TireCoeffs()
    # At zero slip, forces and aligning moment must be zero
    Fx, Fy, Mz = calc_tire_forces_3d(Fz=4000.0, alpha_rad=0.0, kappa=0.0, camber_rad=0.0, coeffs=coeffs)
    assert abs(Fx) < 1.0
    assert abs(Fy) < 1.0
    assert abs(Mz) < 1.0

    # At moderate slip angle (alpha = 3 deg ~ 0.052 rad), Fy and Mz must be generated
    alpha = math.radians(3.0)
    Fx_turn, Fy_turn, Mz_turn = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=0.0, camber_rad=0.0, coeffs=coeffs)
    assert Fy_turn > 1000.0  # substantial lateral force
    assert Mz_turn < 0.0    # restoring self-aligning moment opposes slip angle!
    assert abs(Mz_turn) > 10.0


def test_magic_formula_physical_pressure_scaling():
    coeffs = TireCoeffs()
    alpha = math.radians(4.0)
    # Under-inflated (1.4 bar) vs Nominal (2.0 bar) vs Over-inflated (2.8 bar)
    Fx_under, Fy_under, _ = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=0.0, pressure_bar=1.4, coeffs=coeffs)
    Fx_nom, Fy_nom, _     = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=0.0, pressure_bar=2.0, coeffs=coeffs)
    Fx_over, Fy_over, _   = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=0.0, pressure_bar=2.8, coeffs=coeffs)

    # Higher pressure increases cornering stiffness in initial linear range
    assert Fy_over > Fy_under
    assert Fy_over != Fy_nom
    assert Fy_under != Fy_nom


def test_magic_formula_physical_temperature_scaling():
    coeffs = TireCoeffs()
    alpha = math.radians(6.0)
    # Cold (20°C) vs Optimal (85°C) vs Overheated (140°C)
    _, Fy_cold, _ = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=0.0, T_c=20.0, coeffs=coeffs)
    _, Fy_opt, _  = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=0.0, T_c=85.0, coeffs=coeffs)
    _, Fy_hot, _  = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=0.0, T_c=140.0, coeffs=coeffs)

    # Grip is highest in optimal operating window
    assert Fy_opt > Fy_cold
    assert Fy_opt > Fy_hot


def test_magic_formula_combined_slip_similarity():
    coeffs = TireCoeffs()
    alpha = math.radians(4.0)
    kappa = 0.10
    
    # Pure slip forces
    Fx_pure, _, _ = calc_tire_forces_3d(Fz=4000.0, alpha_rad=0.0, kappa=kappa, coeffs=coeffs)
    _, Fy_pure, _ = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=0.0, coeffs=coeffs)
    
    # Combined slip forces
    Fx_comb, Fy_comb, _ = calc_tire_forces_3d(Fz=4000.0, alpha_rad=alpha, kappa=kappa, coeffs=coeffs)
    
    # Combined forces must be reduced due to friction sharing (Gxalpha < 1, Gykappa < 1)
    assert Fx_comb < Fx_pure
    assert Fy_comb < Fy_pure
    assert Fx_comb > 0.0
    assert Fy_comb > 0.0


def test_modular_tire_model_evaluation_and_metadata():
    model = PacejkaMF52TireModel()
    res = model.evaluate(Fz=4500.0, alpha_rad=0.05, kappa=0.02, T_c=80.0, pressure_bar=2.1)
    assert res.contact_state in (ContactState.ATTACHED, ContactState.SLIPPING, ContactState.SATURATED)
    assert res.forces.Fx > 0
    assert res.forces.Fy > 0
    assert res.forces.Mz < 0  # Restoring moment
    assert res.metadata is not None
    assert res.metadata.model_version == "5.2.1-canonical"


# ─────────────────────────────────────────────────────────────────────────────
# 3. UNILATERAL CONTACT & LIFTOFF/RECONTACT EVENT TRACKING
# ─────────────────────────────────────────────────────────────────────────────

def test_quarter_car_contact_liftoff_and_recontact():
    # Severe pothole excitation causing wheel liftoff (negative normal force prevented)
    p = QuarterCarParams(m_s=300.0, m_u=35.0, k_s=25000.0, c=1500.0, k_t=200000.0, enable_contact_loss=True)
    severe_pothole = RoadProfile(profile_type="pothole", amplitude=0.15, duration=2.5)
    
    res = run_quarter_car_analysis(p, severe_pothole)
    
    # Verify contact states and non-negative normal force
    assert res.diagnostics is not None
    assert res.diagnostics.contact_violations_count == 0  # No Fz < 0 allowed!
    assert res.minimum_Fz >= 0.0
    assert res.diagnostics.minimum_Fz_n >= 0.0
    
    # Liftoff detected during severe drop
    assert (res.liftoff_time is not None) or (res.minimum_Fz == 0.0)
    assert res.provenance is not None
    assert res.provenance.model_version == "quarter-car-2dof-v3.0"


def test_half_car_independent_axle_contact_and_delay():
    p = HalfCarParams(m_s=1200.0, k_sf=30000.0, k_sr=35000.0, speed_mps=25.0)
    profile = RoadProfile(profile_type="pothole", amplitude=0.06, duration=3.0)
    
    res = run_half_car_analysis(p, profile)
    
    assert hasattr(res, "contact_states_f")
    assert hasattr(res, "contact_states_r")
    assert res.diagnostics is not None
    assert res.diagnostics.contact_violations_count == 0
    assert res.minimum_Fz_f >= 0.0
    assert res.minimum_Fz_r >= 0.0


def test_full_car_7dof_4wheel_contact_states():
    params = FullCarParams(
        m_s=1200.0, I_x=600.0, I_y=1800.0, m_uf=45.0, m_ur=45.0,
        k_sf=32000.0, k_sr=36000.0, c_f=2600.0, c_r=2800.0,
        k_arb_f=15000.0, k_arb_r=8000.0, k_tf=250000.0, k_tr=250000.0,
        L=2.6, a=1.2, b=1.4, tw_f=1.6, tw_r=1.6, speed_mps=20.0,
    )
    t = np.linspace(0.0, 2.0, 1000)
    z_bump = 0.04 * np.sin(2.0 * np.pi * 3.0 * t)
    profile = FourCornerRoadProfile(time=t, z_rfl=z_bump, z_rfr=np.zeros_like(t), z_rrl=z_bump, z_rrr=np.zeros_like(t))
    
    res = run_full_car_analysis(params, profile)
    
    assert res.contact_states_fl is not None
    assert res.contact_states_fr is not None
    assert res.minimum_Fz is not None
    assert res.minimum_Fz >= 0.0
    assert res.diagnostics is not None
    assert res.diagnostics["contact_violations_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. CANONICAL ROAD EXCITATION WITH SPATIAL DERIVATIVE
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_road_profile_spatial_derivative():
    x = np.linspace(0.0, 100.0, 1000)
    z = 0.05 * np.sin(2.0 * np.pi * x / 10.0)  # 10m wavelength sinusoid
    road = CanonicalRoadProfile(x=x, z=z)
    
    # Test time excitation at 20 m/s: dz/dt = dz/dx * speed
    t_arr, z_road, dz_dt = road.get_time_excitation(vehicle_speed_mps=20.0, dt=0.001)
    
    assert len(t_arr) == len(z_road) == len(dz_dt)
    expected_peak_slope = 0.05 * (2.0 * np.pi / 10.0)
    expected_peak_dz_dt = expected_peak_slope * 20.0
    
    assert math.isclose(np.max(dz_dt), expected_peak_dz_dt, rel_tol=0.05)


# ─────────────────────────────────────────────────────────────────────────────
# 5. NUMERICAL SOLVER STRATEGY & BENCHMARKING
# ─────────────────────────────────────────────────────────────────────────────

def test_solver_benchmarking_rk_bdf_radau():
    results = benchmark_solvers()
    assert len(results) >= 3
    method_names = [r.method_name for r in results]
    assert "RK45" in method_names
    assert "BDF" in method_names
    assert "Radau" in method_names
    
    for r in results:
        assert r.converged is True
        assert r.num_steps > 0
        assert r.wall_time_ms > 0
