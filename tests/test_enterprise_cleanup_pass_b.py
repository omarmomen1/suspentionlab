"""
tests/test_enterprise_cleanup_pass_b.py
========================================
Pass B: backend Security, Auth, Billing, SSRF, and Metering P1 fixes.
Covers items 1-7 of the Pass B spec (docs/enterprise_deep_audit.md).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from suspensionlab.backend.config import settings
from suspensionlab.backend.database.models.billing import StripeEvent
from suspensionlab.backend.database.models.usage_counter import UsageCounter
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.user_session import UserSession
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password
from suspensionlab.shared.models import PlanTier


# ─────────────────────────── helpers ─────────────────────────────────────────

class FakeObject:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    def get(self, key, default=None):
        return self.__dict__.get(key, default)


async def _mk_user(db, **kw):
    u = User(
        email=kw.pop("email", f"passb_{uuid.uuid4().hex[:8]}@test.com"),
        password_hash=hash_password("PassBTest123!"),
        name=kw.pop("name", "Pass B Tester"),
        **kw,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


# ─────────────────── Item 1: Gumroad billing ─────────────────────────────────

@pytest.mark.asyncio
async def test_gumroad_ping_refund_downgrades_plan(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "gumroad_seller_id", "seller_abc")
    user = await _mk_user(
        db_session, plan=PlanTier.PRO.value, plan_source="gumroad",
        gumroad_license_key="GUMROAD-KEY-1",
    )
    resp = await client.post("/api/v1/billing/gumroad/ping", data={
        "seller_id": "seller_abc",
        "license_key": "GUMROAD-KEY-1",
        "refunded": "true",
    })
    assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.plan == PlanTier.FREE.value
    assert user.plan_source is None


@pytest.mark.asyncio
async def test_gumroad_ping_rejects_wrong_seller(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "gumroad_seller_id", "seller_abc")
    user = await _mk_user(
        db_session, plan=PlanTier.PRO.value, plan_source="gumroad",
        gumroad_license_key="GUMROAD-KEY-2",
    )
    resp = await client.post("/api/v1/billing/gumroad/ping", data={
        "seller_id": "attacker",
        "license_key": "GUMROAD-KEY-2",
        "refunded": "true",
    })
    assert resp.status_code == 403
    await db_session.refresh(user)
    assert user.plan == PlanTier.PRO.value


@pytest.mark.asyncio
async def test_license_redeem_conflict_returns_409(client, db_session, app_instance):
    from suspensionlab.backend.security.license_keys import generate_license_key
    from suspensionlab.backend.security.auth import verify_api_key, UserContext

    key = generate_license_key("PRO")
    u1 = await _mk_user(db_session)
    u2 = await _mk_user(db_session)

    def _ctx_for(u):
        return UserContext(user_id=str(u.id), plan="FREE", email=u.email, name=u.name)

    app_instance.dependency_overrides[verify_api_key] = lambda: _ctx_for(u1)
    r1 = await client.post("/api/v1/billing/verify-license", json={"license_key": key})
    assert r1.status_code == 200, r1.text

    app_instance.dependency_overrides[verify_api_key] = lambda: _ctx_for(u2)
    r2 = await client.post("/api/v1/billing/verify-license", json={"license_key": key})
    assert r2.status_code == 409
    assert r2.json()["detail"] == "License key already redeemed."


# ─────────────────── Item 2: Stripe webhook hardening ────────────────────────

@pytest.mark.asyncio
async def test_stripe_signature_failure_is_generic_400(client, db_session):
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
    with patch("stripe.Webhook.construct_event", side_effect=ValueError("No signatures found matching the expected signature for payload")):
        resp = await client.post(
            "/api/v1/billing/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "bad"},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid webhook signature."


@pytest.mark.asyncio
async def test_stripe_unknown_user_returns_500_for_retry(client, db_session):
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
    event = {
        "id": "evt_unknown_user_1",
        "type": "customer.subscription.created",
        "created": 1700000100,
        "data": {"object": FakeObject(customer="cus_ghost", items=FakeObject(data=[{"price": {"id": "price_pro_test"}}]), status="active", id="sub_ghost")},
    }
    with patch("stripe.Webhook.construct_event", return_value=event):
        resp = await client.post(
            "/api/v1/billing/webhooks/stripe",
            json={"id": "evt_unknown_user_1"},
            headers={"stripe-signature": "sig"},
        )
    assert resp.status_code == 500
    # Event must NOT be recorded as processed, so Stripe's retry is handled fresh.
    res = await db_session.execute(select(StripeEvent).where(StripeEvent.event_id == "evt_unknown_user_1"))
    assert res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_stripe_stale_event_cannot_resurrect_plan(client, db_session):
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
    os.environ["STRIPE_PRO_PRICE_ID"] = "price_pro_test"
    user = await _mk_user(
        db_session, plan=PlanTier.FREE.value, plan_source=None,
        billing_customer_id="cus_stale_1", billing_last_event_created=2000,
    )
    stale = {
        "id": "evt_stale_1", "type": "customer.subscription.updated", "created": 1000,
        "data": {"object": FakeObject(customer="cus_stale_1", items=FakeObject(data=[{"price": {"id": "price_pro_test"}}]), status="active", id="sub_stale")},
    }
    with patch("stripe.Webhook.construct_event", return_value=stale):
        resp = await client.post("/api/v1/billing/webhooks/stripe", json={}, headers={"stripe-signature": "s"})
    assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.plan == PlanTier.FREE.value  # stale updated did not resurrect

    fresh = {
        "id": "evt_fresh_1", "type": "customer.subscription.updated", "created": 3000,
        "data": {"object": FakeObject(customer="cus_stale_1", items=FakeObject(data=[{"price": {"id": "price_pro_test"}}]), status="active", id="sub_stale")},
    }
    with patch("stripe.Webhook.construct_event", return_value=fresh):
        resp = await client.post("/api/v1/billing/webhooks/stripe", json={}, headers={"stripe-signature": "s"})
    assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.plan == PlanTier.PRO
    assert user.plan_source == "stripe"
    assert user.billing_last_event_created == 3000


@pytest.mark.asyncio
async def test_stripe_deleted_never_overwrites_gumroad_entitlement(client, db_session):
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
    gum = await _mk_user(
        db_session, plan=PlanTier.PRO.value, plan_source="gumroad",
        gumroad_license_key="GUMROAD-KEY-3", billing_customer_id="cus_gum_1",
    )
    stripe_user = await _mk_user(
        db_session, plan=PlanTier.PRO.value, plan_source="stripe",
        billing_customer_id="cus_str_1", billing_subscription_id="sub_1",
    )
    for cid in ("cus_gum_1", "cus_str_1"):
        event = {
            "id": f"evt_del_{cid}", "type": "customer.subscription.deleted", "created": 1700000200,
            "data": {"object": FakeObject(customer=cid, id="sub_1")},
        }
        with patch("stripe.Webhook.construct_event", return_value=event):
            resp = await client.post("/api/v1/billing/webhooks/stripe", json={}, headers={"stripe-signature": "s"})
        assert resp.status_code == 200

    await db_session.refresh(gum)
    await db_session.refresh(stripe_user)
    assert gum.plan == PlanTier.PRO.value           # Gumroad entitlement survives
    assert stripe_user.plan == PlanTier.FREE.value  # Stripe entitlement downgraded
    assert stripe_user.billing_subscription_id is None


@pytest.mark.asyncio
async def test_stripe_new_event_handlers(client, db_session):
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
    user = await _mk_user(
        db_session, plan=PlanTier.PRO.value, plan_source="stripe",
        billing_customer_id="cus_misc_1", billing_subscription_id="sub_m",
    )
    # invoice.payment_failed: recorded, plan unchanged
    evt = {
        "id": "evt_inv_fail_1", "type": "invoice.payment_failed", "created": 1700000300,
        "data": {"object": FakeObject(customer="cus_misc_1", id="in_1")},
    }
    with patch("stripe.Webhook.construct_event", return_value=evt):
        resp = await client.post("/api/v1/billing/webhooks/stripe", json={}, headers={"stripe-signature": "s"})
    assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.plan == PlanTier.PRO.value

    # charge.dispute.created: recorded, plan unchanged
    evt = {
        "id": "evt_dispute_1", "type": "charge.dispute.created", "created": 1700000400,
        "data": {"object": FakeObject(customer="cus_misc_1", id="dp_1")},
    }
    with patch("stripe.Webhook.construct_event", return_value=evt):
        resp = await client.post("/api/v1/billing/webhooks/stripe", json={}, headers={"stripe-signature": "s"})
    assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.plan == PlanTier.PRO.value

    # charge.refunded: Stripe-sourced plan downgraded
    evt = {
        "id": "evt_refund_1", "type": "charge.refunded", "created": 1700000500,
        "data": {"object": FakeObject(customer="cus_misc_1", id="ch_1")},
    }
    with patch("stripe.Webhook.construct_event", return_value=evt):
        resp = await client.post("/api/v1/billing/webhooks/stripe", json={}, headers={"stripe-signature": "s"})
    assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.plan == PlanTier.FREE.value
    assert user.billing_subscription_id is None

    # All four events recorded
    res = await db_session.execute(select(StripeEvent))
    ids = {e.event_id for e in res.scalars().all()}
    assert {"evt_inv_fail_1", "evt_dispute_1", "evt_refund_1"} <= ids


# ─────────────── Item 3: Approvals & cryptographic integrity ─────────────────

@pytest.mark.asyncio
async def test_approval_identity_and_content_bound_signature(client, db_session, app_instance):
    from suspensionlab.backend.security.auth import verify_api_key, UserContext
    from suspensionlab.backend.services.timeline_decision_service import TimelineDecisionService
    from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision

    user = await _mk_user(db_session, name="Server Side Engineer", is_admin=True)

    dec = await TimelineDecisionService.create_decision(
        db=db_session,
        user_id=str(user.id),
        team_id=None,
        question="Which front spring rate for the street setup?",
        context={"vehicle": "CAR-1", "setup": "S1", "model_version": "v1"},
        candidates=[{"name": "soft"}, {"name": "stiff"}],
        selected_option={"name": "stiff", "parameter_changes": [{"k_s": 30000}]},
        reason="Body control",
        tradeoffs=[{"axis": "comfort", "effect": "worse"}],
        simulation_evidence={"primary_delta": "rms -5%"},
        telemetry_evidence={},
        validation_evidence={},
        risks=[],
        author="Server Side Engineer",
    )

    admin_ctx = UserContext(
        user_id=str(user.id), plan="ENTERPRISE", email=user.email,
        name="Server Side Engineer", is_admin=True,
    )
    app_instance.dependency_overrides[verify_api_key] = lambda: admin_ctx

    # Client attempts to spoof the approver name; server must ignore it.
    resp = await client.post(
        f"/api/v1/decisions/{dec['decision_id']}/approve",
        json={"approver_name": "Mallory Spoofer", "approver_role": "Chief Race Engineer"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Mallory Spoofer" not in (body.get("approver") or "")
    assert "Server Side Engineer" in (body.get("approver") or "")

    # Signature verifies against the current content...
    res = await db_session.execute(
        select(EngineeringDecision).where(EngineeringDecision.decision_id == dec["decision_id"])
    )
    record = res.scalar_one()
    assert TimelineDecisionService.verify_approval_signature(record) is True

    # ...and fails after tampering with the approved payload.
    record.selected_option = {"name": "soft", "parameter_changes": [{"k_s": 10000}]}
    assert TimelineDecisionService.verify_approval_signature(record) is False


# ─────────────────── Item 4: Auth, secrets & sessions ────────────────────────

def test_license_secret_required_in_prod(monkeypatch):
    from suspensionlab.backend.security import license_keys
    monkeypatch.setattr(settings, "environment", "PROD")
    monkeypatch.setattr(settings, "license_signing_secret", None)
    monkeypatch.delenv("LICENSE_SIGNING_SECRET", raising=False)
    with pytest.raises(license_keys.LicenseConfigError):
        license_keys.get_license_signing_secret()
    monkeypatch.setattr(settings, "license_signing_secret", "lic_" + "x" * 40)
    assert license_keys.get_license_signing_secret() == "lic_" + "x" * 40


def test_saml_relay_state_secret_separation(monkeypatch):
    from suspensionlab.backend.security import saml
    monkeypatch.setattr(settings, "environment", "PROD")
    monkeypatch.setattr(settings, "saml_relay_state_secret", None)
    monkeypatch.delenv("SAML_RELAY_STATE_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        saml.get_saml_relay_state_secret()
    monkeypatch.setattr(settings, "saml_relay_state_secret", "saml_" + "y" * 40)
    token = saml.generate_relay_state("org-1", "/dashboard")
    org_id, return_to = saml.validate_relay_state(token)
    assert org_id == "org-1" and return_to == "/dashboard"


@pytest.mark.asyncio
async def test_legacy_plaintext_api_key_rejected(client, db_session):
    import hashlib
    raw_key = "sk_plaintext_legacy_key"
    # Plaintext-stored key must no longer authenticate.
    await _mk_user(db_session, api_key=raw_key)
    resp = await client.get("/api/v1/usage", headers={"X-API-Key": raw_key})
    assert resp.status_code == 401
    # Hashed storage still authenticates.
    await _mk_user(db_session, api_key=hashlib.sha256(raw_key.encode()).hexdigest())
    resp = await client.get("/api/v1/usage", headers={"X-API-Key": raw_key})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_vnv_run_requires_authentication(client, db_session):
    resp = await client.get("/api/v1/vnv/run")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_register_does_not_confirm_existing_email(client, db_session):
    payload = {"email": "dup@test.com", "password": "Str0ng!Passw0rdXY", "name": "Dup"}
    r1 = await client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201, r1.text
    r2 = await client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409
    assert "already exists" not in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_expired_sessions_not_listed(client, db_session):
    user = await _mk_user(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(UserSession(
        user_id=user.id, jti="expired-jti", expires_at=(now - timedelta(hours=1)).replace(tzinfo=None),
    ))
    db_session.add(UserSession(
        user_id=user.id, jti="active-jti", expires_at=(now + timedelta(days=1)).replace(tzinfo=None),
    ))
    await db_session.commit()
    token = create_access_token({"sub": str(user.id), "email": user.email, "plan": "FREE"})
    resp = await client.get("/api/v1/auth/sessions", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    jtis = [s["jti"] for s in resp.json()["sessions"]]
    assert "active-jti" in jtis
    assert "expired-jti" not in jtis


@pytest.mark.asyncio
async def test_jti_revocation_db_fallback():
    from suspensionlab.backend.security.jwt_utils import record_revoked_jti, is_jti_revoked
    from suspensionlab.backend.database.core import engine
    from suspensionlab.backend.database.core import Base
    import suspensionlab.backend.database.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    jti = f"jti-{uuid.uuid4().hex}"
    with patch("suspensionlab.backend.core.redis_client.get_async_redis_conn", return_value=None):
        assert await is_jti_revoked(jti) is False
        await record_revoked_jti(jti, datetime.now(timezone.utc).timestamp() + 3600, "logout")
        assert await is_jti_revoked(jti) is True


# ─────────────────── Item 5: CORS & exception sanitization ───────────────────

@pytest.mark.asyncio
async def test_cors_rejects_arbitrary_vercel_projects(client):
    resp = await client.options(
        "/api/v1/usage",
        headers={
            "Origin": "https://suspensionlab-attacker.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in {k.lower(): v for k, v in resp.headers.items()}

    resp_ok = await client.options(
        "/api/v1/usage",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp_ok.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_validation_error_does_not_echo_input(client):
    resp = await client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "x"})
    assert resp.status_code == 422
    for err in resp.json().get("errors", []):
        assert "input" not in err


# ─────────────────── Item 6: Webhook SSRF & error handling ───────────────────

def test_ssrf_bypass_refused_in_production(monkeypatch):
    from suspensionlab.backend.services.webhooks import validate_webhook_url
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "true")
    monkeypatch.setenv("ENVIRONMENT", "PROD")
    with pytest.raises(ValueError):
        validate_webhook_url("http://169.254.169.254/latest/meta-data")


def test_validate_webhook_url_pins_resolved_ip(monkeypatch):
    from suspensionlab.backend.services.webhooks import validate_webhook_url
    monkeypatch.delenv("ALLOW_PRIVATE_WEBHOOKS", raising=False)
    ip = validate_webhook_url("https://example.com/hook")
    assert ip and isinstance(ip, str)


@pytest.mark.asyncio
async def test_webhook_malformed_and_unknown_ids(client, db_session, app_instance):
    from suspensionlab.backend.security.auth import verify_api_key, UserContext
    user = await _mk_user(db_session)
    ctx = UserContext(user_id=str(user.id), plan="PRO", email=user.email, name=user.name)
    app_instance.dependency_overrides[verify_api_key] = lambda: ctx

    resp = await client.delete("/api/v1/webhooks/not-a-uuid")
    assert resp.status_code == 400
    resp = await client.delete(f"/api/v1/webhooks/{uuid.uuid4()}")
    assert resp.status_code == 404
    resp = await client.post("/api/v1/webhooks/not-a-uuid/test")
    assert resp.status_code == 400


# ─────────────────── Item 7: Usage metering consistency ──────────────────────

@pytest.mark.asyncio
async def test_metering_db_fallback_records_and_reads_usage(db_session):
    from suspensionlab.backend.core.compute_governance import meter_simulation, get_monthly_usage
    uid = str(uuid.uuid4())
    with patch("suspensionlab.backend.core.redis_client.get_async_redis_conn", return_value=None):
        await meter_simulation(db_session, uid, "PRO")
        await meter_simulation(db_session, uid, "PRO")
        assert await get_monthly_usage(uid, db=db_session) == 2


@pytest.mark.asyncio
async def test_metering_db_fallback_enforces_quota(db_session):
    from fastapi import HTTPException
    from suspensionlab.backend.core.compute_governance import meter_simulation, SIM_QUOTAS, _month_key
    uid = uuid.uuid4()
    db_session.add(UsageCounter(user_id=uid, month=_month_key(), count=SIM_QUOTAS["FREE"]))
    await db_session.commit()
    with patch("suspensionlab.backend.core.redis_client.get_async_redis_conn", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await meter_simulation(db_session, str(uid), "FREE")
    assert exc_info.value.status_code == 402
