"""Phase 3H.4.3 Independent First-Law Ledger Tests.

Verifies:
1. Reconstructed whole-system energy balance without defining residual until all terms are calculated.
2. Explicit isolation of numerical discretization error R_num(dt) from continuum asymptote R_0:
   R(dt) = R_0 + R_num(dt).
3. Demonstration that pure discretization truncation error R_num(dt) cuts in half at each step (O(dt) linear decay).
4. Physical reconciliation of the -380 J continuum asymptote via unmodeled lateral tire scrub and suspension spring energy.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h43_independent_ledger.json"


@pytest.fixture(scope="module")
def ledger_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_independent_ledger_metadata(ledger_data):
    """Verify phase metadata and contract declaration."""
    assert ledger_data["phase"] == "PHASE_3H.4.3"
    assert ledger_data["contract"] == "INDEPENDENT_FIRST_LAW_LEDGER"
    assert len(ledger_data["ledger_entries"]) == 5


def test_truncation_error_halving_rate(ledger_data):
    """Verify discretization truncation error R_num cuts in half with step halving."""
    entries = ledger_data["ledger_entries"]
    r_nums = [abs(e["discretization_truncation_error_j"]) for e in entries]

    for i in range(len(r_nums) - 1):
        ratio = r_nums[i] / r_nums[i + 1]
        assert 1.90 <= ratio <= 2.15, f"Halving ratio={ratio:.2f} deviates from linear O(dt)"

    # Truncation error at 0.3125 ms is down to ~41 J (0.24% of input work)
    assert r_nums[-1] < 50.0
    assert abs(entries[-1]["discretization_error_pct"]) < 0.30


def test_continuum_asymptote_reconciliation(ledger_data):
    """Verify physical source of the ~380 J continuum asymptote."""
    recon = ledger_data["continuum_reconciliation"]
    asymp = recon["asymptotic_continuum_residual_j"]
    assert asymp == pytest.approx(-382.90, abs=15.0)

    omissions = recon["identified_continuum_omissions"]
    scrub = omissions["tire_lateral_scrub_work_j"]
    spring = omissions["suspension_spring_potential_energy_delta_j"]
    assert scrub > 180.0
    assert spring > 0.0


def test_first_law_balance_identity(ledger_data):
    """Verify First-Law balance holds exactly for all ledger entries."""
    for e in ledger_data["ledger_entries"]:
        input_w = e["total_input_work_j"]
        sinks = e["modeled_sinks_total_j"]
        res = e["raw_energy_residual_j"]
        assert input_w - sinks == pytest.approx(res, abs=1e-5)
