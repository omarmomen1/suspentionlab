"""Phase 3H.4.2 Clutch Interface Verification Tests.

Verifies:
1. Exact algebraic identity T_clutch_1 + T_clutch_2 == T_after_cut at all time steps (0.0 Nm discrepancy).
2. Clutch interface work balance closure within 2.0% relative error.
3. Separation and continuous reporting of T_raw, T_after_cut, T_clutch_1, T_clutch_2.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h42_clutch_interface.json"


@pytest.fixture(scope="module")
def clutch_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_clutch_interface_metadata(clutch_data):
    """Verify phase metadata and contract declaration."""
    assert clutch_data["phase"] == "PHASE_3H.4.2"
    assert clutch_data["contract"] == "CLUTCH_INTERFACE_VERIFICATION"


def test_algebraic_identity(clutch_data):
    """Verify T_clutch_1 + T_clutch_2 == T_after_cut identically."""
    ident = clutch_data["algebraic_identity"]
    assert ident["formula"] == "T_clutch_1 + T_clutch_2 == T_after_cut"
    assert ident["max_discrepancy_nm"] == pytest.approx(0.0, abs=1e-6)
    assert ident["closure_verdict"] == "EXACT_MACHINE_PRECISION_CLOSURE"


def test_clutch_interface_energy(clutch_data):
    """Verify clutch interface mechanical energy balance."""
    e = clutch_data["clutch_interface_energy"]
    w_in = e["W_engine_flywheel_in_j"]
    w_out = e["W_clutch_shafts_out_j"]
    e_diss = e["E_clutch_slip_dissipation_j"]
    res = e["clutch_interface_residual_j"]
    err_pct = abs(e["clutch_interface_relative_error_pct"])

    assert w_in > 10000.0
    assert w_out > 10000.0
    assert e_diss > 0.0
    assert res == pytest.approx(w_in - (w_out + e_diss), abs=1e-6)
    assert err_pct <= 2.0, f"Clutch interface error {err_pct:.3f}% exceeds 2.0%"


def test_observable_tracking(clutch_data):
    """Verify time series records separate T_raw, T_after_cut, T_clutch_1, and T_clutch_2."""
    samples = clutch_data["observable_time_series_sample"]
    assert len(samples) > 5
    for s in samples:
        assert "T_raw" in s
        assert "T_after_cut" in s
        assert "T_clutch_1" in s
        assert "T_clutch_2" in s
        assert "T_clutch_sum" in s
        assert s["T_clutch_sum"] == pytest.approx(s["T_after_cut"], abs=1e-6)
