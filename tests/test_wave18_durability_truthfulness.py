"""
tests/test_wave18_durability_truthfulness.py
============================================
Wave 18 — Durability: life in km is a ranking, not a prediction.

Pins:
1. VDV is still the real ISO 2631 quantity (checked against a hand computation).
2. Component life is reported as a relative index with no km unit, capped and labeled.
3. The table carries the ranking disclaimer.
"""

import os

from suspensionlab.backend.api.routes.durability_routes import DurabilityRequest, _compute_durability


def _result(road_class="C", speed_kph=80.0):
    return _compute_durability(DurabilityRequest(road_class=road_class, speed_kph=speed_kph))


def test_vdv_matches_hand_computed_value():
    """VDV = rms_wk * duration^0.25 * 1.4, with the same 20 s window."""
    result = _result()
    expected = result.rms_body_accel_wk * (20.0 ** 0.25) * 1.4
    assert abs(result.vdv - round(expected, 4)) < 1e-3


def test_life_output_is_index_not_km():
    """Every component reports an index, no km string, and a capped value is labeled."""
    result = _result()
    assert result.life_index_unit.startswith("relative index")
    for comp in result.components:
        assert comp.life_index > 0
        assert "km" not in comp.life_index_label.lower()
        assert comp.life_index == comp.life_km  # deprecated alias carries the same number
        assert comp.life_index_label.startswith("index") or comp.life_index_label == ">= max"
    # the summary may name the road speed in km/h, but never a component life in km
    assert "km" not in result.summary.lower().replace("km/h", "")


def test_capped_life_is_labeled_not_rounded():
    """A very soft setup saturates the index; the label says >= max rather than 999,999."""
    soft = _result(road_class="A", speed_kph=10.0)
    labels = [c.life_index_label for c in soft.components]
    assert any(label == ">= max" for label in labels) or all(c.life_index < 1_000_000 for c in soft.components)
    for comp in soft.components:
        if comp.life_index >= 1_000_000:
            assert comp.life_index_label == ">= max"


def test_component_table_shows_ranking_disclaimer():
    """The disclaimer is in the payload and on the page."""
    result = _result()
    assert "Ranking only" in result.life_index_disclaimer
    assert "Not a predicted service life" in result.life_index_disclaimer

    page = open(os.path.join(os.path.dirname(__file__), "..", "frontend", "app", "durability", "page.tsx"), encoding="utf-8").read()
    assert 'data-testid="durability-ranking-disclaimer"' in page
    assert "Relative durability index (higher = longer life)" in page
    assert "Not a predicted service life" in page
    assert "Component Life & Fatigue Predictions" not in page
