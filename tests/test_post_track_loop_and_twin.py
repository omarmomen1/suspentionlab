"""
tests/test_post_track_loop_and_twin.py
======================================
Tests for Step 11 & Step 12:
- DigitalTwinVersion & CalibrationResult construction with empirical uncertainty & lineage
- Closed-loop post-track SetupProposal delta analysis (predicted vs actual measured performance)
"""

import pytest
import numpy as np

from suspensionlab.physics.telemetry_dataset import TelemetryDataset
from suspensionlab.physics.digital_twin import (
    DigitalTwin,
    CalibrationResult,
    OperatingRange,
    create_digital_twin_from_calibration,
    create_reference_digital_twin,
)
from suspensionlab.physics.parameter_identification import (
    identify_suspension_parameters,
)
from suspensionlab.physics.post_track_loop import (
    evaluate_post_track_proposal,
    PostTrackAnalysisReport,
    MetricDeltaComparison,
)


def test_digital_twin_from_calibration_with_lineage_and_operating_range():
    """Verify create_digital_twin_from_calibration produces full lineage, uncertainty, and operating envelope."""
    t = np.linspace(0.0, 5.0, 200)
    telem = {"vert_g": 1.1 * np.sin(2 * np.pi * 1.6 * t), "time": t}
    nominal = {"k_s": 32000.0, "c": 2300.0, "MR": 0.85, "k_t": 210000.0}

    cal_report = identify_suspension_parameters(telem, nominal_params=nominal)
    twin = create_digital_twin_from_calibration(
        calibration_report=cal_report,
        twin_id="TWIN-GT3-CAL-01",
        chassis_name="Porsche-992-GT3R",
        session_ids=["FP1", "FP2"],
        nominal_setup=nominal,
        dataset_ids=["silverstone-fp2-004"],
    )

    assert isinstance(twin, DigitalTwin)
    assert twin.twin_id == "TWIN-GT3-CAL-01"
    assert twin.chassis_name == "Porsche-992-GT3R"
    assert twin.calibration_result is not None
    assert twin.calibration_result.train_rmse > 0.0
    assert len(twin.calibration_result.dataset_ids) == 1

    # Check operating range
    assert isinstance(twin.operating_range, OperatingRange)
    assert twin.operating_range.is_within_bounds(speed_ms=50.0, lat_g=2.5, vert_g=1.2)
    assert not twin.operating_range.is_within_bounds(speed_ms=120.0, lat_g=2.5, vert_g=1.2) # Overspeed

    # Check cryptographic fingerprint
    fp = twin.compute_fingerprint()
    assert len(fp) == 64
    assert twin.fingerprint_hash == fp

    # Check dictionary serialization
    d = twin.to_dict()
    assert "operating_range" in d
    assert "calibration_result" in d
    assert d["calibration_result"]["train_rmse"] > 0.0


def test_post_track_proposal_closed_loop_analysis():
    """Verify evaluate_post_track_proposal computes predicted vs measured deltas and effectiveness score."""
    from suspensionlab.physics.parameter_identification import simulate_quarter_car_response
    t = np.linspace(0.0, 6.0, 300)
    road = 0.015 * np.sin(2 * np.pi * 1.5 * t)
    # Measured on-track telemetry with setup installed (k_s=34000, c=2500)
    y_vert, susp_d = simulate_quarter_car_response(
        m_s=300.0, k_s=34000.0, c=2500.0, k_t=200000.0, MR=0.85, t_eval=t, road_input=road
    )
    telem = TelemetryDataset(
        timestamps=t,
        sampling_rate=50.0,
        vehicle="CAR-2026-07",
        session="FP3-Validated",
    )
    telem.add_channel("vert_g", y_vert)
    telem.add_channel("lat_g", 2.65 * np.cos(2 * np.pi * 0.2 * t))
    telem.add_channel("rh_fl", 32.0 + susp_d * 1000.0, unit="mm")
    telem.add_channel("damper_fl", susp_d * 1000.0, unit="mm")

    proposal_payload = {
        "id": "PROP-2026-SILV-09",
        "baseline_params": {"k_s": 30000.0, "c": 2200.0, "m_s": 300.0, "MR": 0.85},
        "recommended_params": {"k_s": 34000.0, "c": 2500.0},
        "predicted_effects": [
            {"metric": "Peak Lateral Grip", "unit": "G", "baseline": 2.40, "predicted": 2.65},
            {"metric": "Heave Body Acceleration", "unit": "m/s²", "baseline": 1.20, "predicted": 1.05},
        ],
    }

    report = evaluate_post_track_proposal(
        proposal_data=proposal_payload,
        telemetry_dataset=telem,
    )

    assert isinstance(report, PostTrackAnalysisReport)
    assert report.proposal_id == "PROP-2026-SILV-09"
    assert report.setup_validated == True
    assert report.overall_effectiveness_pct > 50.0
    assert len(report.metric_comparisons) >= 3

    # Check spring stiffness comparison
    ks_comp = next(m for m in report.metric_comparisons if "Spring Stiffness" in m.metric_name)
    assert ks_comp.predicted_delta == 4000.0 # 34000 - 30000
    assert ks_comp.actual_measured_delta > 0.0
    assert ks_comp.status in ("verified", "partial", "diverged")

    # Check learning observation payload
    assert "learning_observation_payload" in report.to_dict()
    assert report.learning_observation_payload["proposal_id"] == "PROP-2026-SILV-09"
    assert len(report.provenance_hash) == 64
