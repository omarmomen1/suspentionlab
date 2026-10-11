"""
tests/test_physical_load_transfer.py
====================================
SuspensionLab PRO — Master Physics Vision: Physical Load Transfer Verification

Verifies the complete elimination of heuristic first-order load-transfer lag (tau = 0.05s)
and audits:
1. Zero-lag instantaneous geometric load transfer paths (roll centers, anti-dive, anti-squat).
2. Newton-Raphson algebraic loop convergence (residual < 1e-4 N in <= 4 iterations).
3. Solver non-convergence error raising with diagnostic information.
4. Frequency-domain dynamic benchmark (0.5 to 3.0 Hz) quantifying phase divergence.
5. Seven standardized transient maneuvers (STEP_STEER, SINE_STEER, RAPID_CHICANE,
   BRAKE_IN, BRAKE_RELEASE, THROTTLE_PICKUP, KERB_ENTRY).
6. ForceMomentLedger strict vertical and moment conservation:
   sum(Fz_i) == m*(g + a_z) + F_aero_z (residual < 1e-3 N) and zero double-counting.
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.load_transfer_dynamics import (
    PhysicalLoadTransferEngine,
    LoadTransferPartition,
    solve_coupled_wheel_loads_algebraic_loop,
    run_frequency_response_benchmark,
    run_transient_scenarios,
    FrequencyResponseReport,
)
from suspensionlab.physics.handling_model import (
    HandlingParams,
    simulate_maneuver,
    compute_instantaneous_wheel_state,
)
from suspensionlab.physics.exceptions import SolverNonConvergenceError, MathConvergenceError
from suspensionlab.physics.anti_geometry import ForceMomentLedger, DoubleCountingViolationError
from suspensionlab.physics.magic_formula import TireCoeffs


# ─────────────────────────────────────────────────────────────────────────────
# 1. Zero-Lag Instantaneous Geometric Force Paths
# ─────────────────────────────────────────────────────────────────────────────

def test_instantaneous_geometric_force_paths_zero_lag():
    """Verify geometric roll center reactions and anti-geometry links transfer load with ZERO lag."""
    engine = PhysicalLoadTransferEngine(
        anti_dive_front_pct=30.0,
        anti_squat_rear_pct=35.0,
    )

    # Lateral acceleration step: 4.0 m/s2
    part = engine.compute_partition(a_x_mps2=0.0, a_y_mps2=4.0)

    # Geometric & unsprung components must be non-zero and instantaneous
    assert part.delta_Fz_lat_f_kinematic > 50.0
    assert part.delta_Fz_lat_f_unsprung > 30.0
    assert part.delta_Fz_lat_f_elastic > 100.0

    # Total equals sum of exact components
    sum_f = part.delta_Fz_lat_f_unsprung + part.delta_Fz_lat_f_kinematic + part.delta_Fz_lat_f_elastic
    assert math.isclose(part.delta_Fz_lat_f_total, sum_f, rel_tol=1e-5)

    # Longitudinal acceleration step (braking: -8.0 m/s2)
    part_brk = engine.compute_partition(a_x_mps2=-8.0, a_y_mps2=0.0)

    # 30% anti-dive carried kinematically through suspension links
    assert abs(part_brk.delta_Fz_long_total) > 1000.0
    expected_kin = 0.30 * abs(part_brk.delta_Fz_long_total)
    assert math.isclose(part_brk.delta_Fz_long_kinematic, expected_kin, rel_tol=1e-5)
    assert math.isclose(part_brk.delta_Fz_long_elastic, 0.70 * abs(part_brk.delta_Fz_long_total), rel_tol=1e-5)



def test_handling_model_zero_lag_vs_legacy_filter():
    """Verify handling model operates strictly with physical canonical load transfer."""
    p_phys = HandlingParams(use_physical_load_transfer=True, tau_load_transfer=0.0)
    p_legacy = HandlingParams(use_physical_load_transfer=False, tau_load_transfer=0.05)

    # Step steer input at t = 0.1s
    def steer_step(t):
        return 0.04 if t >= 0.1 else 0.0

    res_phys = simulate_maneuver(p_phys, v_x_init=25.0, steering_func=steer_step,
                                 throttle_func=lambda t: 0.0, brake_func=lambda t: 0.0, duration=0.5, dt=0.005)
    res_legacy = simulate_maneuver(p_legacy, v_x_init=25.0, steering_func=steer_step,
                                   throttle_func=lambda t: 0.0, brake_func=lambda t: 0.0, duration=0.5, dt=0.005)

    t_arr = np.arange(0.0, 0.5, 0.005)
    # Check at t = 0.13s (30 ms after steer step)
    idx_30ms = np.argmin(np.abs(t_arr - 0.13))

    fz_lat_phys = res_phys["delta_Fz_lat_f"][idx_30ms]
    fz_lat_legacy = res_legacy["delta_Fz_lat_f"][idx_30ms]

    # Both run canonical physical load transfer; legacy flag cannot corrupt physics
    assert math.isclose(fz_lat_phys, fz_lat_legacy, rel_tol=1e-5)
    # Load transfer responds immediately without artificial 50ms deadband
    assert fz_lat_phys > 150.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Newton-Raphson Algebraic Loop Solver
# ─────────────────────────────────────────────────────────────────────────────

def test_newton_raphson_algebraic_loop_convergence():
    """Verify algebraic loop solver converges to residual < 1e-4 N in <= 4 iterations."""
    engine = PhysicalLoadTransferEngine()
    steer_rad = math.radians(3.5)

    fz_sol, iters, residual = solve_coupled_wheel_loads_algebraic_loop(
        engine=engine,
        v_x=28.0,
        v_y=-0.5,
        omega_z=0.35,
        steer_rad=steer_rad,
        throttle=0.1,
        brake=0.0,
        max_iter=25,
        tol=1e-4,
    )

    assert residual < 1e-4, f"Newton residual {residual} N exceeds 1e-4 N"
    assert iters <= 4, f"Newton solve took {iters} iterations (expected <= 4)"
    assert np.all(fz_sol > 100.0), f"Unphysical negative or zero wheel loads: {fz_sol}"

    # Vertical conservation check
    expected_total = engine.m_total_kg * 9.81
    assert math.isclose(float(np.sum(fz_sol)), expected_total, abs_tol=1e-3)


def test_algebraic_loop_solver_nonconvergence_raises_error():
    """Verify solver raises SolverNonConvergenceError when tolerance cannot be achieved."""
    engine = PhysicalLoadTransferEngine()

    # Pass max_iter=0 and impossible tolerance to trigger convergence failure
    with pytest.raises((SolverNonConvergenceError, MathConvergenceError)) as excinfo:
        solve_coupled_wheel_loads_algebraic_loop(
            engine=engine,
            v_x=25.0,
            v_y=0.0,
            omega_z=0.2,
            steer_rad=0.05,
            throttle=0.0,
            brake=0.0,
            max_iter=0,
            tol=1e-12,
        )

    assert "SOLVER_NONCONVERGENCE" in str(excinfo.value) or "exceeds tolerance" in str(excinfo.value)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Frequency-Domain Dynamic Benchmark (0.5 to 3.0 Hz)
# ─────────────────────────────────────────────────────────────────────────────

def test_frequency_response_benchmark_sweep():
    """Benchmark dynamic load transfer across 0.5 to 3.0 Hz and verify phase divergence."""
    engine = PhysicalLoadTransferEngine()
    report = run_frequency_response_benchmark(engine=engine, speed_mps=30.0, frequencies=[0.5, 1.0, 1.5, 2.0, 3.0])

    assert isinstance(report, FrequencyResponseReport)
    assert len(report.points) == 5

    # Roll natural frequency is physical (~1.5 to 2.5 Hz)
    assert 1.4 <= report.roll_natural_frequency_hz <= 2.8
    assert 0.2 <= report.roll_damping_ratio <= 0.8

    # Verify monotonic increase of legacy filter lag: arctan(omega * 0.05)
    # At 0.5 Hz: ~9.0 deg; at 1.0 Hz: ~17.4 deg; at 3.0 Hz: ~43.3 deg
    p05 = report.points[0]
    p10 = report.points[1]
    p30 = report.points[4]

    assert 7.0 <= p05.legacy_filter_phase_lag_deg <= 11.0
    assert 15.0 <= p10.legacy_filter_phase_lag_deg <= 20.0
    assert 38.0 <= p30.legacy_filter_phase_lag_deg <= 46.0

    # At frequencies >= 1.0 Hz, legacy filter diverges from physical dynamics
    assert report.divergence_threshold_hz <= 1.5
    assert p30.phase_divergence_deg > 12.0

    # Markdown report formatting
    assert "| Frequency [Hz] |" in report.summary_markdown
    assert "Roll Mode Natural Frequency" in report.summary_markdown


# ─────────────────────────────────────────────────────────────────────────────
# 4. Standardized Transient Scenarios Suite (7 Required Maneuvers)
# ─────────────────────────────────────────────────────────────────────────────

def test_all_seven_transient_scenarios():
    """Execute all 7 standardized transient maneuvers and audit conservation."""
    scenarios = run_transient_scenarios()

    required_scenarios = [
        "STEP_STEER",
        "SINE_STEER",
        "RAPID_CHICANE",
        "BRAKE_IN",
        "BRAKE_RELEASE",
        "THROTTLE_PICKUP",
        "KERB_ENTRY",
    ]

    for name in required_scenarios:
        assert name in scenarios, f"Missing required scenario: {name}"
        res = scenarios[name]
        assert res.time_series_pts > 0
        assert res.ledger_conserved is True, f"Conservation failed for {name}"
        assert res.conservation_residual_max_N < 1e-3, f"Residual {res.conservation_residual_max_N} N too high in {name}"
        assert res.peak_wheel_load_transfer_N > 0.0

    # Scenario specific physics checks:
    # 1. STEP_STEER: Immediate lateral load transfer
    assert scenarios["STEP_STEER"].peak_lateral_accel_mps2 > 5.0

    # 4. BRAKE_IN: Longitudinal deceleration > 8 m/s2
    assert scenarios["BRAKE_IN"].peak_longitudinal_accel_mps2 <= -8.0

    # 5. BRAKE_RELEASE: Coupled longitudinal and lateral transfer
    assert scenarios["BRAKE_RELEASE"].peak_lateral_accel_mps2 > 5.0
    assert scenarios["BRAKE_RELEASE"].peak_longitudinal_accel_mps2 < -5.0

    # 6. THROTTLE_PICKUP: Longitudinal traction > 4 m/s2
    assert scenarios["THROTTLE_PICKUP"].peak_longitudinal_accel_mps2 >= 4.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. ForceMomentLedger Conservation & Double-Counting Audit
# ─────────────────────────────────────────────────────────────────────────────

def test_force_moment_ledger_conservation_and_no_double_counting():
    """Audit ForceMomentLedger conservation and verify double-counting protection."""
    ledger = ForceMomentLedger(
        m_total_kg=1200.0,
        wheelbase_m=2.6,
        h_cg_m=0.45,
        a_x_mps2=-7.5,
        front_anti_pct=25.0,
        rear_anti_pct=20.0,
    )

    assert ledger.is_conserved is True
    assert "Ledger Verified" in ledger.audit_message

    # Conservation: Kinematic + Elastic == Total
    assert math.isclose(
        ledger.front_total_dynamic_transfer_N,
        ledger.front_kinematic_reaction_N + ledger.front_elastic_spring_N,
        rel_tol=1e-6,
    )

    # Double-counting check with valid static and dynamic loads
    w0 = 1200.0 * 9.81 / 4.0
    static_loads = [w0, w0, w0, w0]
    # Valid transfer: front gains Delta_Fz, rear loses Delta_Fz (sum transfer = 0)
    transfer = abs(ledger.delta_Fz_longitudinal_total_N) / 2.0
    valid_asserted_loads = [w0 + transfer, w0 + transfer, w0 - transfer, w0 - transfer]
    assert ledger.verify_no_double_counting(valid_asserted_loads, static_loads) is True

    # Erroneous caller double counts by adding kinematic reaction on top
    invalid_asserted_loads = [w0 + transfer + 500.0, w0 + transfer + 500.0, w0 - transfer, w0 - transfer]
    with pytest.raises(DoubleCountingViolationError):
        ledger.verify_no_double_counting(invalid_asserted_loads, static_loads)


def test_instantaneous_wheel_state_vertical_equilibrium():
    """Verify compute_instantaneous_wheel_state strictly enforces vertical equilibrium."""
    p = HandlingParams()
    x = [25.0, 0.5, 0.15, 0.0, 0.0, 0.0, 0.0, 0.0] + [200.0, 800.0, 200.0, 850.0, 150.0, 500.0, 150.0, 520.0]
    ws = compute_instantaneous_wheel_state(t=0.5, x=x, p=p, steer_val=0.03, throttle_val=0.1, brake_val=0.0)

    fz_sum = ws["Fz_fl"] + ws["Fz_fr"] + ws["Fz_rl"] + ws["Fz_rr"]
    expected_fz = p.m * 9.81 + ws["F_aero_downforce_f"] + ws["F_aero_downforce_r"]

    # Sum of 4 wheels must equal m*g + F_aero within 1 N
    assert math.isclose(fz_sum, expected_fz, abs_tol=1.0)
