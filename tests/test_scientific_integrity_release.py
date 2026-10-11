import pytest
import numpy as np

from suspensionlab.physics.constrained_optimization import (
    optimize_setup_constrained,
    _compute_non_dominated_front,
    ConstrainedOptimizationReport,
)
from suspensionlab.physics.telemetry_analysis import (
    evaluate_model_vs_car_session,
    ModelVsCarReport,
)
from suspensionlab.physics.setup_intelligence import (
    EngineeringDecisionRecord,
)


def test_pareto_frontier_non_domination_math():
    candidates = [
        {'setup_id': 'A', 'lap_time_s': 84.10, 'tire_wear_index': 0.90, 'vibration_rms': 1.20},
        {'setup_id': 'B', 'lap_time_s': 84.30, 'tire_wear_index': 0.80, 'vibration_rms': 1.10},
        {'setup_id': 'C', 'lap_time_s': 84.50, 'tire_wear_index': 0.95, 'vibration_rms': 1.30},
        {'setup_id': 'D', 'lap_time_s': 84.05, 'tire_wear_index': 1.10, 'vibration_rms': 1.40},
    ]

    pareto = _compute_non_dominated_front(candidates)
    pareto_ids = {p['setup_id'] for p in pareto}

    assert 'A' in pareto_ids
    assert 'B' in pareto_ids
    assert 'D' in pareto_ids
    assert 'C' not in pareto_ids


def test_constrained_optimization_computes_real_pareto_and_sensitivity():
    initial_p = {'k_sf': 35000.0, 'k_sr': 38000.0, 'c_f': 2200.0, 'c_r': 2400.0}
    report = optimize_setup_constrained(initial_p, stochastic_robustness=True)

    assert isinstance(report, ConstrainedOptimizationReport)
    assert report.is_feasible
    assert report.optimized_lap_time_s <= report.baseline_lap_time_s
    assert len(report.pareto_frontier) >= 2

    sens_vals = [s.normalized_sensitivity for s in report.sensitivity_rankings]
    assert all(sens_vals[i] >= sens_vals[i+1] for i in range(len(sens_vals)-1))
    assert sum(s.variance_explained_pct for s in report.sensitivity_rankings) == pytest.approx(100.0, abs=1.0)


def test_model_vs_car_spatial_residuals():
    t = np.linspace(0, 10, 500)
    fake_telem = {
        'rh_fl': (35.0 + 4.0 * np.sin(2 * np.pi * 1.2 * t)).tolist(),
        'speed': (60.0 + 5.0 * np.cos(t)).tolist(),
    }
    model_params = {'k_s': 32000.0, 'c': 2400.0}

    report = evaluate_model_vs_car_session(fake_telem, model_params, session_id='FP2-Silverstone')
    assert isinstance(report, ModelVsCarReport)
    assert report.overall_correlation_pct > 60.0
    assert "ride_height" in report.channel_correlations

    assert len(report.spatial_residuals) >= 2
    
    # Check all spatial residual segments have valid bounds and metrics
    for seg in report.spatial_residuals:
        assert seg.end_distance_m > seg.start_distance_m
        assert isinstance(seg.residual_rh_mm, float)
        assert len(seg.suggested_investigation_params) > 0



def test_engineering_decision_record_lineage():
    edr = EngineeringDecisionRecord(
        record_id='EDR-2026-T9-0418',
        vehicle_id='CAR-07',
        track_id='SILVERSTONE-GP',
        session_id='FP2',
        problem_statement='Rear entry instability on trail braking into Turn 9 (Copse)',
        evidence_summary='18 corner events, 4,281 samples, delta RH = +3.3 mm',
        model_lineage={'vehicle_model': 'v12', 'tire_model': 'v5', 'aero_model': 'v9', 'solver': 'RK45'},
        candidate_setup='Rear LSC -4.6% (-1 click / -150 Ns/m)',
        predicted_outcomes={'lap_time_delta_s': -0.062, 'stability_gain_pct': 4.1, 'residual_reduction_pct': 18.2},
        validation_status='PASS',
        risk_assessment='Aero model operates within verified 0-4 deg yaw boundary',
        decision='APPROVED',
        approver_name='Dr. Mark Weber',
        approver_role='Senior Vehicle Dynamics Lead',
        timestamp='2026-08-31T01:45:00Z',
    )
    h1 = edr.compute_hash()
    h2 = edr.compute_hash()
    assert h1 == h2
    assert len(h1) == 64
    d = edr.to_dict()
    assert d['payload_hash'] == h1
    assert d['decision'] == 'APPROVED'
