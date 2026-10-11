"""Phase 3H.4.3 Rate Refinement Verification Tests.

Verifies:
1. Multi-rate evaluation of Window A (12.60–12.80 s) across 5 step sizes:
   - 5.000 ms, 2.500 ms, 1.250 ms, 0.625 ms, 0.3125 ms.
2. Monotonic decay of the numerical energy residual across all refinement steps:
   |R(5.0 ms)| > |R(2.5 ms)| > |R(1.25 ms)| > |R(0.625 ms)| > |R(0.3125 ms)|.
3. Anchor consistency at 1.25 ms with Phase 3H.4.2 (-556.18 J, -3.31%).
4. Physical positivity and sanity of all energy inputs, kinetic energy deltas, and sink dissipations.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h43_rate_refinement.json"


@pytest.fixture(scope="module")
def refinement_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_rate_refinement_metadata(refinement_data):
    """Verify phase metadata and contract declaration."""
    assert refinement_data["phase"] == "PHASE_3H.4.3"
    assert refinement_data["contract"] == "RATE_REFINEMENT_AUDIT"
    window = refinement_data["evaluation_window"]
    assert window["t_start_s"] == 12.60
    assert window["t_end_s"] == 12.80
    assert window["duration_s"] == pytest.approx(0.20, abs=1e-3)


def test_five_rates_evaluated(refinement_data):
    """Verify runs at exactly 5.0, 2.5, 1.25, 0.625, and 0.3125 ms."""
    rates = refinement_data["rates_evaluated"]
    assert len(rates) == 5
    dt_vals = [r["dt_ms"] for r in rates]
    assert dt_vals == [5.0, 2.5, 1.25, 0.625, 0.3125]
    step_counts = [r["n_steps"] for r in rates]
    assert step_counts == [39, 78, 156, 312, 624]


def test_strict_monotonic_residual_decay(refinement_data):
    """Verify numerical residual strictly contracts in magnitude with smaller dt."""
    assert refinement_data["monotonicity_verified"] is True
    rates = refinement_data["rates_evaluated"]
    res_mags = [abs(r["numerical_residual_j"]) for r in rates]

    for i in range(len(res_mags) - 1):
        assert res_mags[i] > res_mags[i + 1], f"Monotonicity failed at dt={rates[i]['dt_ms']}ms"

    assert res_mags[0] == pytest.approx(1080.18, abs=1.0)
    assert res_mags[1] == pytest.approx(727.70, abs=1.0)
    assert res_mags[2] == pytest.approx(556.18, abs=1.0)
    assert res_mags[3] == pytest.approx(468.00, abs=1.0)
    assert res_mags[4] == pytest.approx(424.06, abs=1.0)


def test_rate_refinement_1_25ms_golden_anchor(refinement_data):
    """Verify exact numerical consistency with Phase 3H.4.2 at dt = 1.25 ms."""
    rates = refinement_data["rates_evaluated"]
    r_125 = next(r for r in rates if r["dt_ms"] == 1.25)
    assert r_125["numerical_residual_j"] == pytest.approx(-556.18, abs=0.5)
    assert r_125["relative_residual_pct"] == pytest.approx(-3.31, abs=0.1)
    assert r_125["u_final_mps"] == pytest.approx(23.90857, abs=1e-3)


def test_energy_components_positivity_and_balance(refinement_data):
    """Verify energy terms are physically admissible and satisfy First Law."""
    for r in refinement_data["rates_evaluated"]:
        assert r["W_input_total_j"] > 0
        assert r["Delta_KE_trans_j"] > 0
        assert r["Delta_KE_wheels_j"] > 0
        assert r["E_clutch_diss_j"] > 0
        assert r["E_drivetrain_diss_j"] > 0
        assert r["E_tire_slip_j"] > 0
        assert r["E_damper_j"] > 0
        assert r["E_bearing_j"] > 0
        assert r["W_drag_j"] > 0

        # Input - Sinks == Residual
        expected_res = r["W_input_total_j"] - r["E_sinks_total_j"]
        assert r["numerical_residual_j"] == pytest.approx(expected_res, abs=1e-6)
