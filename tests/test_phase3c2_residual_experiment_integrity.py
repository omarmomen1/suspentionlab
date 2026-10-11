"""
tests/test_phase3c2_residual_experiment_integrity.py
=====================================================
Automated verification tests for Phase 3C.2 Residual Experiment Integrity Audit:
1. Fine tire stiffness sweep around s_tire = 1.3161 proves 1.3161 is a calibration artifact.
2. Physical brake chain trace proves over-deceleration (1.81x demand) and resolves contradiction.
3. Steering compliance before/after metrics prove consistent error reduction across all holdouts.
4. Programmatically regenerated validation matrix preserves strict epistemic governance.
"""

import os
import json
import pytest

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
DOCS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'docs'))

AUDIT_JSON_PATH = os.path.join(DATA_DIR, 'phase3c2_residual_experiment_audit.json')
AUDIT_MD_PATH = os.path.join(DOCS_DIR, 'phase3c2_residual_experiment_audit.md')
MATRIX_JSON_PATH = os.path.join(DATA_DIR, 'phase3c2_regenerated_validation_matrix.json')
MATRIX_MD_PATH = os.path.join(DOCS_DIR, 'phase3c2_regenerated_validation_matrix.md')


def test_phase3c2_artifacts_exist():
    """Verify all 4 required Phase 3C.2 deliverables exist on disk and are non-empty."""
    for path in [AUDIT_JSON_PATH, AUDIT_MD_PATH, MATRIX_JSON_PATH, MATRIX_MD_PATH]:
        assert os.path.exists(path), f"Missing required deliverable: {path}"
        assert os.path.getsize(path) > 100, f"Deliverable is empty or truncated: {path}"


def test_fine_tire_sweep_objective_curve_and_classification():
    """Verify tire stiffness sweep integrity and non-optimality of 1.3161."""
    with open(AUDIT_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tire_audit = data['tire_stiffness_fine_sweep']
    assert tire_audit['classification'] == "CALIBRATION_ARTIFACT_NOT_GLOBAL_OPTIMUM"
    assert tire_audit['is_1_3161_globally_supported'] is False

    optimal = tire_audit['optimal_analysis']
    assert "Turn4_Sweeper" in optimal
    assert "Turn3_Hairpin" in optimal
    assert "Turn1_Calibration" in optimal

    # Turn 4 Sweeper optimal is ~1.18 - 1.20, NOT 1.3161
    t4_opt = optimal["Turn4_Sweeper"]["optimal_s_tire"]
    assert 1.15 <= t4_opt <= 1.25, f"Turn 4 Sweeper optimal s_tire {t4_opt} out of expected range"
    assert optimal["Turn4_Sweeper"]["min_rmse_degps"] < optimal["Turn4_Sweeper"]["baseline_1_3161_rmse"]

    # Turn 3 Hairpin optimal is ~1.00, NOT 1.3161
    t3_opt = optimal["Turn3_Hairpin"]["optimal_s_tire"]
    assert 0.95 <= t3_opt <= 1.05, f"Turn 3 Hairpin optimal s_tire {t3_opt} out of expected range"
    assert optimal["Turn3_Hairpin"]["min_rmse_degps"] < optimal["Turn3_Hairpin"]["baseline_1_3161_rmse"]

    # Turn 1 Calibration prefers lower stiffness
    t1_opt = optimal["Turn1_Calibration"]["optimal_s_tire"]
    assert t1_opt <= 1.05, f"Turn 1 Calibration optimal s_tire {t1_opt} unexpectedly high"


def test_brake_chain_over_deceleration_resolution():
    """Verify physical brake chain trace and resolution of over-deceleration contradiction."""
    with open(AUDIT_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    brake_audit = data['brake_chain_physical_trace']
    tel = brake_audit['telemetry']
    mod = brake_audit['model_chain_baseline']
    mults = brake_audit['torque_multiplier_evaluation']

    # Telemetry check: ~42.6 bar peak, ~ -5.52 m/s^2 peak decel
    assert 40.0 <= tel['peak_brake_pressure_bar'] <= 45.0
    assert -6.0 <= tel['peak_measured_ax_mps2'] <= -5.0

    # Model chain check: pedal saturated at 1.0, expected decel ~ -10.01 m/s^2 (-1.02g)
    assert mod['act_brk_peak'] == 1.0
    assert -10.5 <= mod['ax_simulated_expected_mps2'] <= -9.5

    # Demand to measured ratio demonstrates over-deceleration (> 1.7x)
    ratio = mod['demand_to_measured_ratio']
    assert 1.70 <= ratio <= 1.95, f"Over-deceleration ratio {ratio} unexpected"

    # Multiplier evaluation: 1.00x has large error, 0.80x and 0.57x dramatically reduce error
    rmse_100 = mults['multiplier_1.00']['vx_rmse_mps']
    rmse_080 = mults['multiplier_0.80']['vx_rmse_mps']
    rmse_057 = mults['multiplier_0.57']['vx_rmse_mps']

    assert rmse_100 > 6.0, f"Baseline 1.00x torque RMSE unexpectedly low: {rmse_100}"
    assert rmse_080 < rmse_100, f"0.80x did not reduce RMSE: {rmse_080} vs {rmse_100}"
    assert rmse_057 < 2.0, f"0.57x RMSE unexpectedly high: {rmse_057}"

    # Final simulated speed with 1.00x over-decelerates close to standstill (< 5 m/s vs 14.5 m/s measured)
    assert mults['multiplier_1.00']['final_predicted_vx_mps'] < 5.0
    assert mults['multiplier_1.00']['final_measured_vx_mps'] > 14.0


def test_steering_compliance_before_after_metrics():
    """Verify numerical before (k=0) vs after (k=0.000451) metrics across all holdouts."""
    with open(AUDIT_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    comp = data['steering_compliance_before_after']
    required_maneuvers = ["Turn1_Entry", "Turn1_Holdout", "Turn4_Sweeper", "Turn3_Hairpin"]
    for m in required_maneuvers:
        assert m in comp, f"Missing maneuver {m} in compliance audit"
        k0 = comp[m]['without_compliance']
        k1 = comp[m]['with_compliance']
        d = comp[m]['numerical_delta']

        # Yaw RMSE and R^2 strictly improve with compliance across all maneuvers
        assert k1['yaw_rmse_degps'] < k0['yaw_rmse_degps'], f"{m}: compliance did not improve yaw RMSE"
        assert k1['yaw_r2'] > k0['yaw_r2'], f"{m}: compliance did not improve yaw R^2"

        # Dynamic maneuvers (Turn 1 Entry and Holdout) show 9-11% peak error reduction
        if m in ["Turn1_Entry", "Turn1_Holdout"]:
            assert d['percent_peak_error_reduction'] > 8.0, f"{m}: expected >8% peak error reduction"
        else:
            # Steady-state corners show near-constant peak error (|change| < 0.25 deg/s)
            assert abs(d['yaw_peak_err_change_degps']) < 0.25, f"{m}: peak error changed excessively"


def test_programmatic_validation_matrix_invariants():
    """Verify epistemic invariants of the regenerated validation matrix."""
    with open(MATRIX_JSON_PATH, 'r', encoding='utf-8') as f:
        matrix = json.load(f)

    subsystems = {item['subsystem']: item for item in matrix}

    # RR travel must be UNVALIDATED
    assert "Suspension Travel (RR)" in subsystems
    assert subsystems["Suspension Travel (RR)"]["status"] == "UNVALIDATED"

    # Tire contact patch forces must be UNVALIDATED_SIMULATION_ESTIMATE
    assert "Tire Contact Patch Forces (Fx, Fy, Fz)" in subsystems
    assert subsystems["Tire Contact Patch Forces (Fx, Fy, Fz)"]["status"] == "UNVALIDATED_SIMULATION_ESTIMATE"

    # Fully blind yaw dynamics must be CORRELATED, not EMPIRICALLY_VALIDATED
    assert "Chassis Yaw Dynamics (Fully Blind Open-Loop)" in subsystems
    assert subsystems["Chassis Yaw Dynamics (Fully Blind Open-Loop)"]["status"] == "CORRELATED"

    # Speed-conditioned yaw dynamics is EMPIRICALLY_VALIDATED
    assert "Chassis Yaw Dynamics (Speed-Conditioned)" in subsystems
    assert subsystems["Chassis Yaw Dynamics (Speed-Conditioned)"]["status"] == "EMPIRICALLY_VALIDATED"
