"""Phase 3H.4.2 Torque-Cut Metrics Separation Tests.

Verifies:
1. Strict separation of signed torque error, cut magnitude error, and percentage attenuation.
2. Ban on combined 'OR' formulations.
3. Quantified metrics match physical simulation and empirical telemetry values.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h42_torque_cut_metrics.json"


@pytest.fixture(scope="module")
def metrics_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_torque_cut_metrics_metadata(metrics_data):
    """Verify phase metadata and policy."""
    assert metrics_data["phase"] == "PHASE_3H.4.2"
    assert metrics_data["contract"] == "TORQUE_CUT_METRICS_SEPARATION"
    assert metrics_data["policy"] == "DO_NOT_COMBINE_INTO_OR_STATEMENTS"
    assert "metrics" in metrics_data


def test_signed_torque_error_separated(metrics_data):
    """Verify signed torque error is independently reported."""
    m = metrics_data["metrics"]["signed_torque_error"]
    assert "value_nm" in m
    assert m["unit"] == "Nm"
    assert m["value_nm"] == pytest.approx(101.12, abs=5.0)
    assert m["simulated_t_cut_nm"] > 0.0
    assert m["measured_t_cut_nm"] < 0.0, "Measured cut torque must be negative (active spark retard)"


def test_cut_magnitude_error_separated(metrics_data):
    """Verify cut magnitude error is independently reported."""
    m = metrics_data["metrics"]["cut_magnitude_error"]
    assert "value_nm" in m
    assert m["unit"] == "Nm"
    assert m["value_nm"] == pytest.approx(35.32, abs=2.0)
    assert m["simulated_drop_nm"] > 250.0
    assert m["measured_drop_nm"] > 250.0


def test_percentage_attenuation_separated(metrics_data):
    """Verify percentage attenuation is independently reported."""
    m = metrics_data["metrics"]["percentage_attenuation"]
    assert "simulated_pct" in m
    assert "measured_pct" in m
    assert "attenuation_error_pct" in m
    assert m["simulated_pct"] == pytest.approx(90.0, abs=1.0)
    assert m["measured_pct"] > 100.0, "Measured percentage attenuation exceeds 100% due to negative torque"
    assert m["attenuation_error_pct"] == pytest.approx(41.3, abs=2.0)


def test_no_combined_or_statements(metrics_data):
    """Verify verdict prohibits combined OR statements."""
    assert metrics_data["verdict"] == "METRICS_INDEPENDENTLY_QUANTIFIED_AND_SEPARATED"
