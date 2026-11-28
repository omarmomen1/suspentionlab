"""
tests/test_wave11_ride_studios_truthfulness.py
==============================================
Wave 11 — Ride studios: no silent assumptions in full-car, honest AI tune.

Pins:
1. A default full-car run is symmetric (road_asymmetry 1.0 everywhere).
2. The response echoes the asymmetry actually used, with a human-readable note.
3. The lateral-g provenance note is stated in the payload and on the page.
4. AI Tune proposes a diff and waits for a click; it never writes parameters itself.
"""

import os
import re
from types import SimpleNamespace

import pytest

from suspensionlab.backend.api.routes.simulate import full_car as fc
from suspensionlab.shared.models import FullCarParamsSchema, FullCarSimulateRequest, RoadProfileSchema


def test_full_car_default_road_is_symmetric():
    """No default may run the right road at 30% of the left."""
    assert FullCarParamsSchema().road_asymmetry == 1.0
    # The frozen physics dataclass is not touched (guardrail); the API schema is the
    # default that reaches every run, and the route/worker fallbacks agree with it.
    worker = open(os.path.join(os.path.dirname(__file__), "..", "src", "suspensionlab", "backend", "workers", "unified_worker.py"), encoding="utf-8").read()
    assert 'pdump.pop("road_asymmetry", 1.0)' in worker
    assert 'pdump.pop("road_asymmetry", 0.3)' not in worker
    source = open(os.path.join(os.path.dirname(__file__), "..", "src", "suspensionlab", "backend", "api", "routes", "simulate", "full_car.py"), encoding="utf-8").read()
    assert 'pdump.pop("road_asymmetry", 1.0)' in source
    assert 'pdump.pop("road_asymmetry", 0.3)' not in source


@pytest.mark.asyncio
async def test_full_car_response_echoes_asymmetry(monkeypatch):
    """The response carries the asymmetry used and the lateral-g provenance note."""

    async def fake_bounded(*args, **kwargs):
        return {"rms_heave_accel": 0.1}

    async def fake_concurrency(*args, **kwargs):
        return None

    monkeypatch.setattr(fc, "bounded_run", fake_bounded)
    monkeypatch.setattr(fc, "assert_user_concurrency", fake_concurrency)

    user = SimpleNamespace(user_id="u-1", plan="PRO")
    profile = RoadProfileSchema(duration=0.02)

    explicit = FullCarSimulateRequest(params=FullCarParamsSchema(road_asymmetry=0.5), profile=profile)
    res = await fc.simulate_full_car(explicit, user=user, db=None)
    assert res["road_asymmetry"] == 0.5
    assert res["metadata"]["road_asymmetry"] == 0.5
    assert res["metadata"]["road_asymmetry_note"] == "Road asymmetry: 0.50 (right = 50% of left)"
    assert res["metadata"]["lateral_g_source"] == "input"
    assert "not solved" in res["metadata"]["lateral_g_model_note"]

    default = FullCarSimulateRequest(params=FullCarParamsSchema(), profile=profile)
    res2 = await fc.simulate_full_car(default, user=user, db=None)
    assert res2["road_asymmetry"] == 1.0
    assert res2["metadata"]["road_asymmetry_note"] == "Road asymmetry: 1.00 (right = 100% of left)"

    page = open(os.path.join(os.path.dirname(__file__), "..", "frontend", "app", "full-car", "page.tsx"), encoding="utf-8").read()
    assert "Ride-and-attitude model: roll and load transfer are computed from the lateral g you enter" in page


def test_ai_tune_requires_confirmation_before_apply():
    """AI Tune may only propose; parameters change on the engineer's click.

    Static guard: this is a React client component with no JSX test runner wired in
    this repository (npm build is skipped for these waves), so the handler bodies are
    asserted from source.
    """
    page = open(os.path.join(os.path.dirname(__file__), "..", "frontend", "app", "quarter-car", "page.tsx"), encoding="utf-8").read()

    start = page.index("const autoTune = async () => {")
    end = page.index("// ————————————————— Derived", start)
    auto_tune_body = page[start:end]

    assert "setAiProposal(" in auto_tune_body
    assert "setParams(" not in auto_tune_body, "autoTune must not write parameters itself"
    assert "AI suggestion - unverified" in auto_tune_body
    assert "AI suggestion - backed by a tool run" in auto_tune_body

    # the apply path exists and is the only place params change from an AI answer
    assert "const applyAiProposal = () => {" in page
    apply_body = page[page.index("const applyAiProposal = () => {"):page.index("const autoTune = async () => {")]
    assert "setParams(" in apply_body
    assert 'data-testid="ai-proposal-apply"' in page
    assert 'data-testid="ai-proposal-panel"' in page
