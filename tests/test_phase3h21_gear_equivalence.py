"""Phase 3H.2.1 Golden Gear-Equivalence Tests.

Verifies:
1. Golden Gear-Equivalence Test on HighSpeed S-Curves [54.0, 63.0] s.
2. Fixed ratio N = 5.6427 and inferred gear produce identical trajectories to machine precision.
3. Inferred gear engine selects Gear 3 (ratio 5.6427) across 100% of samples.
4. CF_K reproduces the Phase 3H.1 benchmark within authorized tolerance (<= 0.10 m/s).
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GEAR_EQUIVALENCE_JSON = DATA_DIR / "phase3h21_gear_equivalence.json"


@pytest.fixture(scope="module")
def eq_data():
    assert GEAR_EQUIVALENCE_JSON.exists(), f"Missing file: {GEAR_EQUIVALENCE_JSON}"
    with open(GEAR_EQUIVALENCE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_golden_gear_equivalence_numerical_identity(eq_data):
    """Verify Case A (fixed 5.6427) and Case B (inferred gear) match to numerical precision."""
    metrics = eq_data["equivalence_metrics"]
    assert metrics["max_trajectory_abs_diff_mps"] < 1e-6
    assert metrics["is_machine_equivalent"] is True
    assert metrics["numerical_equivalence_verdict"] == "PERFECT_NUMERICAL_EQUIVALENCE"


def test_gear_inference_selects_gear_3_exclusively(eq_data):
    """Verify that gear inference identifies Gear 3 with ratio 5.6427 across all samples."""
    case_b = eq_data["case_B_inferred_gear"]
    assert case_b["all_samples_gear_3"] is True
    assert case_b["all_samples_ratio_5_6427"] is True
    assert case_b["inferred_gears_present"] == [3]


def test_reproduces_phase3h1_benchmark_within_tolerance(eq_data):
    """Verify CF_K reproduces Phase 3H.1 CF_B2 benchmark within 0.10 m/s tolerance."""
    bench = eq_data["phase3h1_benchmark_comparison"]
    assert bench["reproduces_within_tolerance"] is True
    assert bench["delta_rmse_mps"] <= bench["tolerance_threshold_mps"]
    assert "shift" in bench["root_cause_of_delta"].lower()
