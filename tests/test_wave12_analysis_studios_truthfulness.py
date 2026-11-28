"""
tests/test_wave12_analysis_studios_truthfulness.py
==================================================
Wave 12 — Analysis studios: no fabricated sign-off, no hardcoded headline.

Pins:
1. No request model or query default carries an invented author or approver.
2. The workflow approver/author come from the authenticated user; a conflicting client identity is refused.
3. The Investigation Room has no invented question and handles a missing twin with an empty state + Create Twin.
4. /experiments/compare really simulates both setups and builds its causality chain from those results.
"""

import os

import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from suspensionlab.backend.api.routes import setup_engineering_routes as routes
from suspensionlab.backend.services.experiment_service import ExperimentService

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _user():
    return SimpleNamespace(
        user_id="11111111-1111-1111-1111-111111111111",
        email="chief.engineer@f1team.com",
        name="Pat Fry",
        team_role="Chief Race Engineer",
        team_id=None,
    )


def test_no_default_approver_anywhere():
    """No model, query default or payload may carry an invented identity."""
    source = open(os.path.join(ROOT, "src", "suspensionlab", "backend", "api", "routes", "setup_engineering_routes.py"), encoding="utf-8").read()
    assert "Elena Rostova" not in source
    assert "Chief Race Engineer & Technical Director" not in source

    assert routes.EngineeringDecisionRequest().author == ""
    assert routes.ApprovalRequest().approver_name == ""
    assert routes.ApprovalRequest().approver_role == ""


@pytest.mark.asyncio
async def test_workflow_approver_comes_from_authenticated_user(monkeypatch):
    """The server sets the approver from the session and refuses a conflicting client identity."""
    captured = {}

    async def fake_approval(**kwargs):
        captured.update(kwargs)
        return {"approval_code": kwargs.get("approval_code"), "approver_name": kwargs.get("approver_name")}

    monkeypatch.setattr(
        routes.Phase3LSetupEngineeringService, "request_human_approval", fake_approval, raising=False
    )

    user = _user()
    req = routes.ApprovalRequest(decision_code="DEC-1", approval_code="APPR-1")
    result = await routes.approve_decision_endpoint(req, user=user, db=None)
    assert captured["approver_name"] == "Pat Fry"
    assert captured["approver_role"] == "CHIEF RACE ENGINEER"
    assert result["approver_name"] == "Pat Fry"

    spoofed = routes.ApprovalRequest(approver_name="Elena Rostova")
    with pytest.raises(HTTPException) as excinfo:
        await routes.approve_decision_endpoint(spoofed, user=user, db=None)
    assert excinfo.value.status_code == 403
    assert "spoofing" in str(excinfo.value.detail).lower()

    # A client identity that matches the session is accepted, still with the server value.
    captured.clear()
    matching = routes.ApprovalRequest(approver_name="Pat Fry", approver_role="Chief Race Engineer")
    await routes.approve_decision_endpoint(matching, user=user, db=None)
    assert captured["approver_name"] == "Pat Fry"

    # /decision: the author is the session, never the payload.
    async def fake_decision(**kwargs):
        captured.clear()
        captured.update(kwargs)
        return {"decision_code": kwargs.get("decision_code")}

    monkeypatch.setattr(
        routes.Phase3LSetupEngineeringService, "create_engineering_decision", fake_decision, raising=False
    )
    await routes.create_decision_endpoint(routes.EngineeringDecisionRequest(decision_code="DEC-2"), user=user, db=None)
    assert captured["author"] == "Pat Fry"


def test_investigate_handles_twin_404_with_empty_state():
    """No invented headline; a missing twin renders an empty state with a Create Twin CTA."""
    page = open(os.path.join(ROOT, "frontend", "app", "investigate", "page.tsx"), encoding="utf-8").read()
    assert "Rear entry platform instability under trail braking" not in page
    assert "twinMissing" in page
    assert 'data-testid="twin-empty-state"' in page
    assert 'data-testid="create-twin-cta"' in page
    assert "DigitalTwinApi.createTwin(" in page
    # the empty state only creates the twin on the click, never on mount
    create_body = page[page.index("const createTwinFromEmptyState"):page.index("const handleGenerateProposal")]
    assert "await DigitalTwinApi.createTwin(" in create_body
    mount_effect = page[page.index("useEffect(() => {"):page.index("const createTwinFromEmptyState")]
    assert "createTwin(" not in mount_effect


def test_compare_simulates_both_setups():
    """The comparison runs both setups through the simulator and builds causality from the results."""
    setup_a = {"m_s": 320, "m_u": 45, "k_s": 20000, "c": 1200, "k_t": 220000, "MR": 0.85}
    setup_b = {"m_s": 320, "m_u": 45, "k_s": 45000, "c": 2500, "k_t": 220000, "MR": 0.85}
    result = ExperimentService.compare_setups(
        setup_a=setup_a,
        setup_b=setup_b,
        road_profile={"profile_type": "sine", "amplitude": 0.01, "frequency": 1.5, "duration": 2.0},
    )

    changed = {c["parameter"]: c for c in result["what_changed"]}
    assert changed["k_s"]["setup_a"] == 20000
    assert changed["k_s"]["setup_b"] == 45000
    assert changed["c"]["setup_a"] == 1200
    assert changed["c"]["setup_b"] == 2500

    # Real, distinct simulator output on both sides - not one run copied twice.
    improved_or_worse = result["what_improved"] + result["what_got_worse"]
    assert improved_or_worse, "comparison produced no metric deltas"
    for row in improved_or_worse:
        assert row["baseline"] != row["candidate"]

    assert result["engineering_causality"], "causality chain must be built from the two result sets"
    assert result["validation_state"] in ("UNVALIDATED", "VALIDATED", "NOT_EVALUATED", "DATA_MISSING", "PASS")
