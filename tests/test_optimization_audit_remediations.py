"""
tests/test_optimization_audit_remediations.py
=============================================
Validation tests for Engineering Optimization Audit remediations:
- P0: Front damping c_f sensitivity & coupled two-axle physics in constrained_optimization.py
- P1: Dynamic COBYLA parameter bounds in optimizer.py
- P1: Dynamic telemetry ride height constraint enforcement in constraint_optimizer.py
- P2: Stochastic uncertainty seed control in robust optimization
"""

import pytest
import numpy as np

from suspensionlab.physics.constrained_optimization import (
    _evaluate_candidate_physics,
    optimize_setup_constrained,
    ConstrainedOptimizationReport,
)
from suspensionlab.physics.optimizer import optimize_setup
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile
from suspensionlab.physics.lap_sim import LapSimVehicle, parse_track_from_curvature, solve_lap
from suspensionlab.physics.constraint_optimizer import ConstraintDrivenOptimizer, SetupConstraints


def test_front_damper_cf_has_real_physics_response():
    cand_low = {'k_sf': 35000.0, 'k_sr': 38000.0, 'c_f': 1500.0, 'c_r': 2400.0, 'k_arb_f': 15000.0, 'k_arb_r': 12000.0}
    cand_high = {'k_sf': 35000.0, 'k_sr': 38000.0, 'c_f': 4500.0, 'c_r': 2400.0, 'k_arb_f': 15000.0, 'k_arb_r': 12000.0}

    lap_low, wear_low, vib_low, cons_low = _evaluate_candidate_physics(cand_low)
    lap_high, wear_high, vib_high, cons_high = _evaluate_candidate_physics(cand_high)

    assert vib_low != vib_high, 'c_f had zero effect on vibration RMS!'
    assert lap_low != lap_high, 'c_f had zero effect on lap time!'
    assert wear_low != wear_high, 'c_f had zero effect on tire wear index!'


def test_cf_sensitivity_is_present_in_rankings():
    initial = {'k_sf': 35000.0, 'k_sr': 38000.0, 'c_f': 2200.0, 'c_r': 2400.0, 'k_arb_f': 15000.0, 'k_arb_r': 12000.0}
    report = optimize_setup_constrained(initial, stochastic_robustness=True, seed=42)

    assert isinstance(report, ConstrainedOptimizationReport)
    cf_item = next((s for s in report.sensitivity_rankings if s.parameter_name == 'c_f'), None)
    assert cf_item is not None, 'c_f was not included in sensitivity rankings!'
    assert cf_item.normalized_sensitivity > 0.0, 'c_f normalized sensitivity is zero!'


def test_cobyla_dynamic_bounds_for_stiff_racecar():
    p_race = QuarterCarParams(m_s=300.0, m_u=40.0, k_s=85000.0, c=4500.0, k_t=300000.0, MR=1.0)
    r = RoadProfile(profile_type='step', amplitude=0.03, duration=2.0)

    res = optimize_setup(p_race, r, objective_type='Ride Comfort', max_travel=0.08)
    assert res['success'], 'Optimization failed for high-stiffness setup'
    assert res['optimal_ks'] > 20000.0, 'Optimal spring rate collapsed to legacy bounds'

    custom_bounds = {'k_s': (70000.0, 110000.0), 'c': (3000.0, 7000.0)}
    res_custom = optimize_setup(p_race, r, objective_type='Ride Comfort', max_travel=0.08, bounds=custom_bounds)
    assert 69999.0 <= res_custom['optimal_ks'] <= 110001.0
    assert 2999.0 <= res_custom['optimal_c'] <= 7001.0


def test_dynamic_ride_height_constraint_check():
    v = LapSimVehicle()
    v.build_ggv(n_speeds=10)
    track_dist = np.linspace(0, 200, 6)
    track_curv = np.array([0.0, 0.0, 0.01, 0.01, 0.0, 0.0])
    segments = parse_track_from_curvature(track_dist, track_curv)

    res = solve_lap(v, segments)
    opt = ConstraintDrivenOptimizer()

    c_pass = SetupConstraints(
        ride_height_front_min_mm=5.0,
        ride_height_rear_min_mm=None,
        aero_balance_min=None,
        aero_balance_max=None,
        tire_load_variation_max_n=None,
    )
    check_pass = opt.check_constraints(v, {}, c_pass, lap_result=res)
    assert check_pass['all_hard_satisfied']

    min_dyn_f = float(np.min(res.ride_height_front))
    c_fail = SetupConstraints(
        ride_height_front_min_mm=min_dyn_f + 5.0,
        ride_height_rear_min_mm=None,
        aero_balance_min=None,
        aero_balance_max=None,
        tire_load_variation_max_n=None,
    )
    check_fail = opt.check_constraints(v, {}, c_fail, lap_result=res)
    assert not check_fail['all_hard_satisfied']
    assert not check_fail['ride_height_front_min_dynamic_mm']['satisfied']



def test_stochastic_uncertainty_seed_reproducibility():
    initial = {'k_sf': 30000.0, 'k_sr': 35000.0, 'c_f': 2000.0, 'c_r': 2200.0, 'k_arb_f': 10000.0, 'k_arb_r': 8000.0}

    rep_a1 = optimize_setup_constrained(initial, stochastic_robustness=True, seed=123)
    rep_a2 = optimize_setup_constrained(initial, stochastic_robustness=True, seed=123)
    rep_b = optimize_setup_constrained(initial, stochastic_robustness=True, seed=456)

    assert rep_a1.optimized_lap_time_s == pytest.approx(rep_a2.optimized_lap_time_s, rel=1e-5)
    assert rep_a1.robustness_metric == pytest.approx(rep_a2.robustness_metric, rel=1e-5)
    assert rep_a1.robustness_metric != rep_b.robustness_metric
