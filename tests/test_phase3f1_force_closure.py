"""
tests/test_phase3f1_force_closure.py
====================================
Test Suite 2 for Phase 3F.1: Non-Tautological Independent Force & Torque Closure.
"""

import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def force_closure_data():
    path = PROJECT_ROOT / "data" / "phase3f1_force_closure.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_independent_force_closure_bounds(force_closure_data):
    """Verify independent finite-difference chassis force closure is strictly bounded (< 0.5% RMS)."""
    chassis = force_closure_data["chassis_force_closure"]
    assert chassis["closure_valid"] is True
    assert chassis["rms_residual_n"] < 10.0, f"RMS force residual {chassis['rms_residual_n']} N exceeded 10.0 N"
    assert chassis["relative_residual_pct"] < 0.5, f"Relative residual {chassis['relative_residual_pct']}% exceeded 0.5%"


def test_independent_wheel_torque_balance_all_corners(force_closure_data):
    """Verify per-wheel torque balance is computed and reported for all 4 corners."""
    wheels = force_closure_data["wheel_torque_closure"]
    for corner in ("FL", "FR", "RL", "RR"):
        assert corner in wheels
        assert "rms_residual_nm" in wheels[corner]
        assert "relative_residual_pct" in wheels[corner]
        assert wheels[corner]["rms_residual_nm"] < 5.0, f"{corner} RMS torque residual too high"


def test_tautology_explanation_recorded(force_closure_data):
    """Verify that the Phase 3F internal derivative tautology is explicitly explained."""
    taut = force_closure_data["tautology_explanation"]
    assert "tautology_nature" in taut
    assert "phase3f1_independent_method" in taut
    assert "finding" in taut


def test_force_closure_documentation_exists():
    """Verify docs/phase3f1_force_closure.md exists and is populated."""
    path = PROJECT_ROOT / "docs" / "phase3f1_force_closure.md"
    assert path.exists(), f"Missing {path}"
    assert path.stat().st_size > 500
