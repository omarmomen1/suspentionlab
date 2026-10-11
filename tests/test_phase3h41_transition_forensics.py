"""Phase 3H.4.1 Shift-Dynamics Forensics Tests.

Verifies:
1. Window A (12.60 - 12.80 s) 2 -> 3 transition forensic metrics.
2. Shift trigger time error <= 50 ms.
3. Shift completion time error <= 50 ms.
4. Torque-cut start error <= 50 ms.
5. Post-shift RPM error characterization.
6. Vehicle longitudinal speed Vx RMSE <= 0.25 m/s across the transition.
7. Time-series alignment structure and integrity.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h41_transition_forensics.json"


@pytest.fixture(scope="module")
def forensics_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_transition_window_and_metadata(forensics_data):
    """Verify Window A boundaries and phase metadata."""
    assert forensics_data["phase"] == "PHASE_3H.4.1"
    assert forensics_data["window_a_time_range_s"] == [12.6, 12.8]
    assert "forensic_metrics" in forensics_data
    assert "time_series_alignment" in forensics_data


def test_trigger_time_forensics(forensics_data):
    """Verify shift trigger timing delta is within 50 ms."""
    m = forensics_data["forensic_metrics"]
    sim_trigger = m["trigger_time_sim_s"]
    meas_trigger = m["trigger_time_meas_s"]
    trigger_error = m["trigger_time_error_s"]
    assert abs(trigger_error) <= 0.050, f"Trigger error {trigger_error:.4f} s exceeds 50 ms"
    assert trigger_error == pytest.approx(-0.040, abs=0.005)
    assert sim_trigger == pytest.approx(12.60, abs=0.01)
    assert meas_trigger == pytest.approx(12.64, abs=0.01)


def test_torque_cut_timing(forensics_data):
    """Verify torque cut start and duration characterization."""
    m = forensics_data["forensic_metrics"]
    cut_start_error = m["torque_cut_start_error_s"]
    assert abs(cut_start_error) <= 0.050, f"Cut start error {cut_start_error:.4f} s exceeds 50 ms"
    assert m["torque_cut_duration_sim_s"] == pytest.approx(0.040, abs=0.005)
    assert m["torque_cut_duration_meas_s"] == pytest.approx(0.110, abs=0.005)


def test_shift_completion_accuracy(forensics_data):
    """Verify shift completion timing error is within 50 ms."""
    m = forensics_data["forensic_metrics"]
    completion_error = m["shift_completion_error_s"]
    assert abs(completion_error) <= 0.050, f"Shift completion error {completion_error:.4f} s exceeds 50 ms"
    assert m["shift_completion_time_sim_s"] == pytest.approx(12.75, abs=0.01)
    assert m["shift_completion_time_meas_s"] == pytest.approx(12.75, abs=0.01)


def test_post_shift_rpm_characterization(forensics_data):
    """Verify post-shift RPM matches within characterization threshold."""
    m = forensics_data["forensic_metrics"]
    post_rpm_sim = m["post_shift_rpm_sim"]
    post_rpm_meas = m["post_shift_rpm_meas"]
    rpm_error = abs(m["post_shift_rpm_error"])
    assert post_rpm_sim > 4000.0
    assert post_rpm_meas > 4000.0
    assert rpm_error < 300.0, f"Post-shift RPM error {rpm_error} exceeds 300 RPM"


def test_vx_trajectory_rmse(forensics_data):
    """Verify vehicle longitudinal speed RMSE <= 0.25 m/s across the transition."""
    m = forensics_data["forensic_metrics"]
    rmse = m["vx_rmse_mps"]
    assert rmse <= 0.250, f"Vx RMSE {rmse:.4f} exceeds 0.250 m/s preregistered threshold"
    assert rmse == pytest.approx(0.1535, abs=0.02)


def test_time_series_alignment_fidelity(forensics_data):
    """Verify time series alignment covers Window A with complete telemetry channels."""
    ts = forensics_data["time_series_alignment"]
    assert len(ts) >= 30, f"Expected >= 30 time steps, got {len(ts)}"
    first_pt = ts[0]
    last_pt = ts[-1]
    assert first_pt["t_s"] == pytest.approx(12.60, abs=0.01)
    assert last_pt["t_s"] == pytest.approx(12.80, abs=0.01)
    for pt in ts:
        assert "t_s" in pt
        assert "gear_sim" in pt
        assert "gear_meas" in pt
        assert "torque_engine_raw" in pt
        assert "torque_post_cut" in pt
        assert "clutch1_torque" in pt
        assert "clutch2_torque" in pt
        assert "shift_state" in pt
        assert "clutch_state" in pt
        assert "vx_sim" in pt
        assert "vx_meas" in pt
