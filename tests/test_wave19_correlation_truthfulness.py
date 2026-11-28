"""
tests/test_wave19_correlation_truthfulness.py
=============================================
Wave 19 — Correlation: no verdict against synthetic data.

Pins:
1. The comparison response declares reference_source and whether a verdict is allowed.
2. A synthetic reference can never carry CORRELATED: the page gate requires uploaded telemetry.
3. The SAMPLE/UPLOADED legend follows the response, not the local sample flag.
"""

import os

import numpy as np

from suspensionlab.backend.services.telemetry_correlation_service import TelemetryCorrelationService

PAGE = os.path.join(os.path.dirname(__file__), "..", "frontend", "app", "correlation", "page.tsx")


def _page():
    return open(PAGE, encoding="utf-8").read()


def test_compare_without_upload_marks_reference_synthetic():
    """No telemetry supplied: the response says it correlated against the canned trace."""
    result = TelemetryCorrelationService.compare_measured_vs_model(
        model_type="QUARTER_CAR", telemetry_data=None
    )
    assert result["reference_source"] == "synthetic_canonical"
    assert result["verdict_allowed"] is False


def test_compare_with_upload_marks_reference_uploaded():
    """Real telemetry supplied: the response says uploaded and allows a verdict."""
    n = 400
    t = np.linspace(0.0, 4.0, n)
    telemetry = {
        "time": t.tolist(),
        "vert_g": (0.02 * np.sin(2 * np.pi * 1.5 * t)).tolist(),
    }
    result = TelemetryCorrelationService.compare_measured_vs_model(
        model_type="QUARTER_CAR", telemetry_data=telemetry
    )
    assert result["reference_source"] == "uploaded"
    assert result["verdict_allowed"] is True


def test_no_correlated_label_on_synthetic_reference():
    """The zero-lie gate refuses CORRELATED unless the reference is uploaded."""
    page = _page()
    assert "SAMPLE - NO VERDICT (upload telemetry to correlate)" in page
    assert "const verdictAllowed = r2Ok && !referenceIsSynthetic;" in page
    # the green badge must be gated on verdictAllowed, not on r2 alone
    assert 'activeChannelData.epistemic_label === "CORRELATED" && verdictAllowed' in page
    assert 'activeChannelData.epistemic_label === "CORRELATED" && r2Ok' not in page


def test_legend_follows_response_reference_source():
    """The legend is driven by the response, and the response wins over the local flag."""
    page = _page()
    assert "const referenceSource: string | undefined = (modelComparisonData as any)?.reference_source;" in page
    assert 'referenceSource !== undefined ? referenceSource !== "uploaded" : isSampleDataset' in page
    assert '{referenceIsSynthetic ? "SAMPLE (Demo CSV)" : "UPLOADED CSV"}' in page
    assert 'data-testid="correlation-upload-cta"' in page
    assert "Upload your CSV to run a real correlation" in page
