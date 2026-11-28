"""Targeted regression tests for Sprint 2 P0 & P1 security/credibility fixes."""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
import uuid

import pytest

from suspensionlab.backend.api.routes import billing_routes
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.user_session import UserSession
from suspensionlab.backend.security.jwt_utils import (
    create_password_reset_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
)
from suspensionlab.backend.services.experiment_service import compare_metrics
from suspensionlab.backend.workers import unified_worker
from suspensionlab.shared.models import PlanTier


@pytest.mark.asyncio
async def test_p0_login_backdoor_removed_and_soft_deleted_rejected(client, db_session):
    """Hardcoded testuser backdoor is gone and soft-deleted users cannot log in."""
    for pwd in ("SuspensionLab2026!#", "TestPass123!", "password123", "anything-at-all"):
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "testuser@suspensionlab.com", "password": pwd},
        )
        assert res.status_code == 401

    # Soft-deleted user with valid password must still be rejected
    email = f"deleted_{uuid.uuid4().hex[:8]}@example.com"
    u = User(
        email=email,
        password_hash=hash_password("ValidStrongPass123!"),
        name="Deleted User",
        plan=PlanTier.FREE,
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(u)
    await db_session.commit()

    res_del = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "ValidStrongPass123!"},
    )
    assert res_del.status_code == 401


@pytest.mark.asyncio
async def test_p0_reset_password_min_length_single_use_and_revokes_sessions(client, db_session):
    """Password reset enforces 12+ chars, rejects replay, and invalidates UserSessions."""
    email = f"reset_{uuid.uuid4().hex[:8]}@example.com"
    u = User(
        email=email,
        password_hash=hash_password("InitialPass12345!"),
        name="Reset User",
        plan=PlanTier.FREE,
    )
    db_session.add(u)
    await db_session.flush()
    sess = UserSession(
        user_id=u.id,
        jti=f"jti-{uuid.uuid4().hex}",
        device_type="Desktop",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
    )
    db_session.add(sess)
    await db_session.commit()

    reset_tok = create_password_reset_token(str(u.id))

    # Short password (< 12) rejected with 422
    res_short = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_tok, "new_password": "short"},
    )
    assert res_short.status_code == 422

    # Valid password succeeds and clears sessions
    res_ok = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_tok, "new_password": "NewStrongPassword2026!"},
    )
    assert res_ok.status_code == 200

    # Replay must fail cleanly
    res_replay = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_tok, "new_password": "AnotherStrongPass2026!"},
    )
    assert res_replay.status_code == 400

    from sqlalchemy import select
    rem = (await db_session.execute(select(UserSession).where(UserSession.user_id == u.id))).scalars().all()
    assert rem == []


@pytest.mark.asyncio
async def test_p0_refresh_uses_live_db_plan_and_rejects_deleted_user(client, db_session):
    """Token refresh queries live User row instead of trusting stale JWT plan claim."""
    email = f"refresh_{uuid.uuid4().hex[:8]}@example.com"
    u = User(
        email=email,
        password_hash=hash_password("RefreshPass12345!"),
        name="Refresh User",
        plan=PlanTier.FREE,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)

    # Refresh token claims PRO, but live DB has FREE
    stale_refresh = create_refresh_token({"sub": str(u.id), "email": email, "plan": "PRO"})
    res = await client.post("/api/v1/auth/refresh", json={"refresh_token": stale_refresh})
    assert res.status_code == 200
    claims = decode_access_token(res.json()["token"])
    assert claims is not None
    assert claims["plan"] == "FREE"

    # Soft-delete user -> new refresh must fail with 401
    u.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    res_del = await client.post("/api/v1/auth/refresh", json={"refresh_token": res.json()["refresh_token"]})
    assert res_del.status_code == 401


@pytest.mark.asyncio
async def test_p0_saml_disabled_by_default_returns_503(client):
    """SAML login and ACS callback return HTTP 503 when ENABLE_SAML_SSO is disabled."""
    r1 = await client.get("/api/v1/auth/saml/login?org_slug=acme")
    assert r1.status_code == 503
    assert "disabled" in r1.json()["detail"].lower()

    r2 = await client.post("/api/v1/auth/saml/acs", data={"SAMLResponse": "dummy"})
    assert r2.status_code == 503
    assert "disabled" in r2.json()["detail"].lower()


def test_p0_unified_worker_numpy_toplevel_and_sanitized_errors():
    """unified_worker imports numpy at module level and never shadows np locally in _run_job_async."""
    assert hasattr(unified_worker, "np")
    src = inspect.getsource(unified_worker._run_job_async)
    assert "import numpy" not in src
    worker_file = Path(inspect.getfile(unified_worker)).read_text(encoding="utf-8")
    assert 'f"Transient Error: {str(e)}"' not in worker_file
    assert "Simulation execution failed" in worker_file


def test_p0_experiment_service_no_fabricated_regressions():
    """compare_metrics does not invent +7.4% / +8.2% secondary tradeoffs when none exist."""
    base = {
        "k_s": 25000.0,
        "rms_body_accel": 2.0,
        "peak_susp_travel_mm": 30.0,
        "tire_load_variation_n": 400.0,
        "settling_time_s": 0.5,
        "peak_body_accel": 4.0,
        "peak_transmissibility": 1.6,
    }
    cand = {
        "k_s": 30000.0,  # delta k_s > 500
        "rms_body_accel": 1.8,
        "peak_susp_travel_mm": 27.0,
        "tire_load_variation_n": 360.0,
        "settling_time_s": 0.45,
        "peak_body_accel": 3.7,
        "peak_transmissibility": 1.45,
    }
    improvements, regressions = compare_metrics(base, cand)
    assert len(improvements) == 6
    assert regressions == []


@pytest.mark.asyncio
async def test_p0_client_asserted_share_not_signed_and_email_redacted(authenticated_client):
    """Client-asserted share links must never get signature_valid=True or leak approver email."""
    res = await authenticated_client.post(
        "/api/v1/reports/share",
        json={
            "simulation_type": "quarter_car",
            "params": {"m_s": 300, "k_s": 35000, "c": 2200},
            "result": {"rms_body_accel": 1.1},
            "title": "Client Supplied",
        },
    )
    assert res.status_code == 200, res.text[:200]
    token = res.json()["token"]
    assert res.json()["provenance"] == "client-asserted"

    pub = await authenticated_client.get(f"/api/v1/reports/{token}")
    assert pub.status_code == 200, pub.text[:200]
    prov = pub.json()["provenance"]
    assert prov["status"] == "client-asserted"
    assert prov["signature_valid"] is None
    assert prov["approved_by_email"] is None


@pytest.mark.asyncio
async def test_p1_stripe_webhook_status_gate_and_500_on_commit_fail(client, db_session):
    """Stripe webhook rejects past_due/unpaid status grants and returns 500 on DB commit error."""
    billing_routes.STRIPE_WEBHOOK_SECRET = "whsec_test"
    billing_routes.STRIPE_PRO_PRICE_ID = "price_pro_test"

    u = User(
        email=f"bill_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        plan=PlanTier.FREE,
        billing_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)

    past_due_event = {
        "id": f"evt_past_due_{uuid.uuid4().hex[:8]}",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": u.billing_customer_id,
                "status": "past_due",
                "id": "sub_pd_1",
                "items": {"data": [{"price": {"id": "price_pro_test"}}]},
            }
        },
    }
    with patch("stripe.Webhook.construct_event", return_value=past_due_event):
        r = await client.post(
            "/api/v1/billing/webhooks/stripe",
            json=past_due_event,
            headers={"stripe-signature": "sig"},
        )
    assert r.status_code == 200
    await db_session.refresh(u)
    assert u.plan == PlanTier.FREE

    # Final commit failure must return HTTP 500 so Stripe retries
    active_event = {
        "id": f"evt_fail_{uuid.uuid4().hex[:8]}",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "customer": u.billing_customer_id,
                "status": "active",
                "id": "sub_active_1",
                "items": {"data": [{"price": {"id": "price_pro_test"}}]},
            }
        },
    }
    with patch("stripe.Webhook.construct_event", return_value=active_event), patch.object(
        db_session, "commit", new=AsyncMock(side_effect=RuntimeError("DB down"))
    ):
        r_err = await client.post(
            "/api/v1/billing/webhooks/stripe",
            json=active_event,
            headers={"stripe-signature": "sig"},
        )
    assert r_err.status_code == 500
