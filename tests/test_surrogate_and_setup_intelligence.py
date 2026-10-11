"""
tests/test_surrogate_and_setup_intelligence.py
==============================================
Tests for Surrogate Response Surface Modeling and Setup Intelligence Engine (Findings 75, 76, 77, 78, 79).
"""

import pytest
import numpy as np

from suspensionlab.physics.surrogate_models import RBFSurrogateModel
from suspensionlab.physics.vehicle_knowledge_base import (
    VehicleKnowledgeBase,
    SessionCalibrationRecord,
)
from suspensionlab.physics.setup_intelligence import (
    SetupIntelligenceEngine,
    SetupIntelligenceDiagnosis,
)


def test_rbf_surrogate_model_fit_predict_optimize():
    # Fit a 2D response surface (e.g. front and rear spring rates -> lap time)
    # True objective: f(x1, x2) = (x1 - 35)^2 + (x2 - 40)^2 + 80.0
    x_train = np.array([
        [30.0, 35.0],
        [30.0, 45.0],
        [35.0, 40.0], # minimum
        [40.0, 35.0],
        [40.0, 45.0],
    ])
    y_train = np.array([
        (x_train[:, 0] - 35.0) ** 2 + (x_train[:, 1] - 40.0) ** 2 + 80.0
    ]).T

    surrogate = RBFSurrogateModel(epsilon=0.1)
    surrogate.fit(x_train, y_train, param_names=["k_sf", "k_sr"], output_names=["lap_time"])

    # Predict at minimum
    y_pred, uncert = surrogate.predict(np.array([[35.0, 40.0]]))
    assert np.isclose(y_pred[0, 0], 80.0, atol=0.1)
    assert uncert[0] < 0.1  # Low uncertainty at exact training point

    # Predict far away -> high uncertainty
    _, uncert_far = surrogate.predict(np.array([[100.0, 100.0]]))
    assert uncert_far[0] > 0.8

    # Fast surrogate optimization
    bounds = [(30.0, 40.0), (35.0, 45.0)]
    best_x, best_score, best_uncert = surrogate.optimize_surrogate(
        bounds,
        objective_fn=lambda y: float(y[0]),
        n_samples=500,
    )
    assert len(best_x) == 2
    assert 79.0 <= best_score <= 82.0


def test_vehicle_knowledge_base_accumulation():
    kb = VehicleKnowledgeBase(team_id="team-mclaren", chassis_serial="MCL38-03")
    
    # Record FP1 session
    kb.record_session(
        session_id="FP1-SILVERSTONE",
        track_id="Silverstone-GP",
        telemetry_samples=45000,
        mean_residual_mm=3.2,
        setup_params={"k_sf": 36000.0, "k_sr": 42000.0},
        learned_offsets={"rear_compliance_bias": 0.35, "aero_cop_bias": -0.012},
    )

    # Record FP2 session
    kb.record_session(
        session_id="FP2-SILVERSTONE",
        track_id="Silverstone-GP",
        telemetry_samples=52000,
        mean_residual_mm=2.4,
        setup_params={"k_sf": 36000.0, "k_sr": 44000.0},
        learned_offsets={"rear_compliance_bias": 0.38, "aero_cop_bias": -0.010},
    )

    assert kb.total_sessions_recorded == 2
    assert kb.total_telemetry_points_analyzed == 97000

    offsets = kb.get_track_calibrated_offsets("Silverstone-GP")
    assert "rear_compliance_bias" in offsets
    assert 0.35 <= offsets["rear_compliance_bias"] <= 0.38


def test_setup_intelligence_engine_diagnosis_and_explanation():
    engine = SetupIntelligenceEngine()
    diagnosis = engine.analyze_corner_instability(
        inquiry="Why was the car unstable in T9?",
        corner_id="T9",
        entry_speed_kmh=(164.0, 191.0),
        evidence_events=18,
        residual_rh_mm=3.8,
        lsc_adjustment_pct=-4.6,
        stability_gain_pct=4.1,
        lap_delta_s=-0.062,
    )

    assert isinstance(diagnosis, SetupIntelligenceDiagnosis)
    assert diagnosis.inquiry == "Why was the car unstable in T9?"
    assert diagnosis.evidence_events_count == 18
    assert "Rear LSC -4.6%" in diagnosis.recommended_setup_change
    assert diagnosis.predicted_stability_gain_pct == 4.1
    assert diagnosis.predicted_lap_time_delta_s == -0.062
    assert 0.70 <= diagnosis.confidence_score <= 1.0

    # Verify AI Grounded Explanation contains specific, truthful context
    assert "4.6% reduction in rear low-speed compression" in diagnosis.ai_grounded_explanation
    assert "tire-load constraints" in diagnosis.ai_grounded_explanation

    md_report = diagnosis.to_markdown_report()
    assert "Setup Intelligence Diagnosis" in md_report
    assert "Turn 9 (T9)" in md_report
    assert f"{diagnosis.configurations_tested:,}" in md_report



def test_setup_intelligence_engine_independent_computation():
    """Verify setup intelligence independently calculates deltas and checks constraints (Finding 70)."""
    engine = SetupIntelligenceEngine()
    setup_baseline = {"k_s": 30000.0, "c": 2500.0}
    setup_candidate = {"k_s": 27000.0, "c": 2200.0}
    telemetry = {"time": np.linspace(0, 10, 500)}
    constraints = [
        {"name": "min_ride_height", "limit": 15.0, "actual": 18.2, "op": ">="},
        {"name": "max_damper_vel", "limit": 2.5, "actual": 1.9, "op": "<="},
    ]

    diag = engine.diagnose_and_optimize(
        setup_a=setup_baseline,
        setup_b=setup_candidate,
        telemetry=telemetry,
        constraints=constraints,
    )

    assert isinstance(diag, SetupIntelligenceDiagnosis)
    assert len(diag.constraint_violations) == 0  # Both constraints satisfied
    assert diag.predicted_stability_gain_pct > 0.0
    assert diag.predicted_lap_time_delta_s < 0.0  # Faster lap time
    assert "Spring rate -10.0%" in diag.recommended_setup_change
    assert "Damper -12.0%" in diag.recommended_setup_change

