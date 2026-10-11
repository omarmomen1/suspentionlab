"""
tests/test_phase3f1_low_pressure_audit.py
=========================================
Test Suite 3 for Phase 3F.1: Low-Pressure Brake Map Audit and Provenance Verification.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def low_pressure_data():
    path = PROJECT_ROOT / "data" / "phase3f1_low_pressure_audit.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def generalization_data():
    path = PROJECT_ROOT / "data" / "phase3f1_generalization.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_turn5_final_speed_bias_identified(low_pressure_data):
    """Verify audit identifies that CF_D increases Turn 5 exit speed bias compared to CF_C."""
    m_t5 = low_pressure_data["cross_maneuver_comparison"]["Turn5_Tight_Complex"]
    err_c = abs(m_t5["cf_c"]["final_error"])
    err_d = abs(m_t5["cf_d"]["final_error"])

    # CF_C final error is essentially zero (0.066 m/s) while CF_D introduces > 1.0 m/s error
    assert err_c < 0.10
    assert err_d > 1.00
    assert err_c < err_d


def test_cross_sector_cf_d_degradation(low_pressure_data):
    """Verify that CF_D degrades Turn 9-10 Complex RMSE compared to production CF_C."""
    m_t9 = low_pressure_data["cross_maneuver_comparison"]["Turn9_10_Final_Complex"]
    assert m_t9["delta_rmse_pct"] > 10.0, f"Expected >10% degradation on Turn 9-10, got {m_t9['delta_rmse_pct']:.1f}%"


def test_low_pressure_production_decision_and_classification(low_pressure_data, generalization_data):
    """Verify CF_C is retained and CF_D is classified as NOT_GENERALIZED."""
    assert low_pressure_data["recommendation"] == "PRESERVE_CF_C_AS_PRODUCTION_BASELINE"
    gen_matrix = generalization_data["component_generalization_matrix"]
    assert "NOT_GENERALIZED" in gen_matrix["low_pressure_actuator_map"]["final_classification"]


def test_evaluation_contamination_honestly_flagged(generalization_data):
    """Verify provenance audit flags evaluation contamination where Turn 5 samples were inspected."""
    prov = generalization_data["provenance_findings"]
    assert "EVALUATION_CONTAMINATION" in prov["engine_overrun_map"]["evaluation_contamination_status"]
    assert "EVALUATION_CONTAMINATION" in prov["low_pressure_map"]["evaluation_contamination_status"]


def test_phase3f1_documentation_artifacts_exist():
    """Verify all required documentation reports exist."""
    for doc in ("phase3f1_actuator_provenance.md", "phase3f1_force_closure.md",
                "phase3f1_low_pressure_audit.md", "phase3f1_validation_status.md"):
        path = PROJECT_ROOT / "docs" / doc
        assert path.exists(), f"Missing docs/{doc}"
        assert path.stat().st_size > 400, f"docs/{doc} appears empty"
