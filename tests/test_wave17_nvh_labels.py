"""
tests/test_wave17_nvh_labels.py
===============================
Wave 17 — NVH: stop quoting dBA that isn't sound pressure.

Static guards: /nvh is a client component with a local compute helper and no JSX test
runner is wired in this repository (npm build is skipped for these waves).
"""

import os

PAGE = os.path.join(os.path.dirname(__file__), "..", "frontend", "app", "nvh", "page.tsx")


def _source():
    return open(PAGE, encoding="utf-8").read()


def test_no_absolute_dba_claims_rendered():
    """No unit, label, chart title or axis may claim dBA sound pressure."""
    source = _source()
    assert "dBA" not in source
    assert "Peak Cabin Boom" not in source
    assert "Peak Cavity Roar" not in source
    assert "Acoustic Noise" not in source
    assert "Boom-region response" in source
    assert "Roar-region response" in source
    assert "dB (A-wtd, rel.)" in source
    assert "not SPL" in source
    # the preview label stays
    assert "Client-Side Interactive Solver (Preview)" in source


def test_scope_note_visible():
    """The scope note is rendered under the KPI row."""
    source = _source()
    assert 'data-testid="nvh-scope-note"' in source
    assert (
        "Relative trend from a 2-DOF transmissibility model with A-weighting. Not an absolute"
        in source
    )
    assert "no cavity or panel model" in source
    assert "Use for setup-to-setup comparison only." in source
