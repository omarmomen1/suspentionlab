"""Wave 6 final items: single 80 mm travel limit, audit-write failure returns 503."""
import pytest
from suspensionlab.physics import pareto_optimizer as po


def test_travel_limit_is_80mm_everywhere():
    assert po.DEFAULT_MAX_SUSP_TRAVEL_MM == 80.0
    from suspensionlab.backend.services import setup_proposal
    from suspensionlab.backend.api.routes import ai_engineer_routes
    from suspensionlab.backend.services.experiment_service import check_engineering_constraints
    assert setup_proposal.CONSTRAINTS["peak_susp_travel_max"] == pytest.approx(0.080)
    assert ai_engineer_routes.CONSTRAINTS["peak_susp_travel_max"] == pytest.approx(0.080)
    ok, rows = check_engineering_constraints({}, {"peak_susp_travel_mm": 79.0})
    assert rows[0]["limit"] == "≤ 80.0 mm" and rows[0]["passed"]
    ok, rows = check_engineering_constraints({}, {"peak_susp_travel_mm": 81.0})
    assert not rows[0]["passed"]
    # caller override stays intact
    ok, rows = check_engineering_constraints({}, {"peak_susp_travel_mm": 100.0}, travel_limit_mm=120.0)
    assert rows[0]["passed"]
    cons = po.quarter_car_feasibility_constraints()
    assert any(getattr(c, "upper", None) == 80.0 for c in cons) or "80" in repr(cons)
    cons2 = po.quarter_car_feasibility_constraints(max_travel_mm=120.0)
    assert any(getattr(c, "upper", None) == 120.0 for c in cons2) or "120" in repr(cons2)


def test_ai_approve_audit_write_failure_returns_503(monkeypatch):
    """Audit write fails -> approval fails closed with 503 (not 400)."""
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.routes import ai_engineer_routes as aer
    from suspensionlab.backend.security.auth import verify_api_key
    from suspensionlab.backend.database.core import get_db_dependency
    import suspensionlab.backend.security.audit as audit_mod
    from tests.test_wave5a2_remediation import _route_app, _session_user

    async def boom(db, event_type, **kw):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(audit_mod, "record_audit_event", boom)
    monkeypatch.setenv("DECISION_HMAC_SECRET", "x" * 48)
    eng = _session_user("ENGINEER")

    async def fake_db():
        yield object()

    client = TestClient(_route_app(aer.router, overrides={
        verify_api_key: lambda: eng, get_db_dependency: fake_db}))
    r = client.post("/api/v1/ai/approve", json={
        "decision_id": "dec-audit-fail", "approver_name": "x",
        "approver_role": "VIEWER", "autonomous_request": False})
    assert r.status_code == 503, r.text
