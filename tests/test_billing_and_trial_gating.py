"""
Unit and integration tests for:
1. Expired trial leak fix in PLAN_LEVELS and require_plan (auth.py)
2. Self-issued HMAC-SHA256 signed license keys (SLPRO-PRO-..., SLPRO-ENT-...)
   alongside existing Gumroad verification (gumroad_routes.py + license_keys.py)
3. CLI key generator script (scripts/generate_license_key.py)
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import generate_license_key as cli_gen
from suspensionlab.backend.api.main import app
from suspensionlab.backend.api.routes import gumroad_routes
from suspensionlab.backend.config import settings
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.trial import Trial
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.auth import (
    PLAN_LEVELS,
    UserContext,
    require_plan,
    verify_api_key,
)
from suspensionlab.backend.security.jwt_utils import hash_password
from suspensionlab.backend.security.license_keys import (
    LicenseExpiredError,
    LicenseInvalidError,
    generate_license_key,
    verify_license_key,
)
from suspensionlab.shared.models import PlanTier


# ─── 1. PLAN_LEVELS & require_plan Trial Enforcement ──────────────────────────


def test_plan_levels_maps_trial_to_pro_level():
    assert PLAN_LEVELS[PlanTier.FREE] == 0
    assert PLAN_LEVELS[PlanTier.PRO] == 1
    assert PLAN_LEVELS[PlanTier.TRIAL] == 1
    assert PLAN_LEVELS[PlanTier.ENTERPRISE] == 2


def _make_mini_gated_app() -> FastAPI:
    mini = FastAPI()

    @mini.get("/pro-only")
    async def pro_only(user: UserContext = Depends(require_plan(PlanTier.PRO))):
        return {"ok": True, "plan": user.plan}

    @mini.get("/enterprise-only")
    async def enterprise_only(user: UserContext = Depends(require_plan(PlanTier.ENTERPRISE))):
        return {"ok": True, "plan": user.plan}

    @mini.get("/free-ok")
    async def free_ok(user: UserContext = Depends(require_plan(PlanTier.FREE))):
        return {"ok": True, "plan": user.plan}

    return mini


def test_require_plan_trial_tiers_and_expiration():
    mini = _make_mini_gated_app()
    future_iso = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    # Active trial -> allowed on PRO, rejected on ENTERPRISE
    active_trial_user = UserContext(
        user_id=str(uuid.uuid4()),
        plan="TRIAL",
        email="active@trial.dev",
        name="Active Trial",
        onboarding_complete=True,
        is_trial=True,
        trial_status="ACTIVE",
        trial_expires_at=future_iso,
    )
    mini.dependency_overrides[verify_api_key] = lambda: active_trial_user
    c = TestClient(mini)
    assert c.get("/pro-only").status_code == 200
    assert c.get("/enterprise-only").status_code == 403

    # Trial expired via trial_status == "EXPIRED" (even if expires_at not set) -> rejected on PRO & ENTERPRISE
    expired_status_user = UserContext(
        user_id=str(uuid.uuid4()),
        plan="TRIAL",
        email="expired1@trial.dev",
        name="Expired Status",
        onboarding_complete=True,
        is_trial=True,
        trial_status="EXPIRED",
        trial_expires_at=future_iso,
    )
    mini.dependency_overrides[verify_api_key] = lambda: expired_status_user
    assert c.get("/free-ok").status_code == 200
    assert c.get("/pro-only").status_code == 403
    assert c.get("/enterprise-only").status_code == 403

    # Trial expired via past trial_expires_at (even if trial_status says ACTIVE) -> rejected on PRO
    expired_date_user = UserContext(
        user_id=str(uuid.uuid4()),
        plan="FREE",
        email="expired2@trial.dev",
        name="Expired Date",
        onboarding_complete=True,
        is_trial=True,
        trial_status="ACTIVE",
        trial_expires_at=past_iso,
    )
    mini.dependency_overrides[verify_api_key] = lambda: expired_date_user
    assert c.get("/pro-only").status_code == 403
    assert c.get("/enterprise-only").status_code == 403

    # Paid PRO -> allowed on PRO, blocked on ENTERPRISE
    pro_user = UserContext(
        user_id=str(uuid.uuid4()),
        plan="PRO",
        email="pro@user.dev",
        name="Pro User",
        onboarding_complete=True,
    )
    mini.dependency_overrides[verify_api_key] = lambda: pro_user
    assert c.get("/pro-only").status_code == 200
    assert c.get("/enterprise-only").status_code == 403

    # Paid ENTERPRISE -> allowed on both
    ent_user = UserContext(
        user_id=str(uuid.uuid4()),
        plan="ENTERPRISE",
        email="ent@user.dev",
        name="Ent User",
        onboarding_complete=True,
    )
    mini.dependency_overrides[verify_api_key] = lambda: ent_user
    assert c.get("/pro-only").status_code == 200
    assert c.get("/enterprise-only").status_code == 200


@pytest.mark.asyncio
async def test_active_trial_blocked_from_enterprise_session_endpoint(
    client: AsyncClient,
):
    reg = await client.post(
        "/api/v1/trials/register",
        json={
            "email": "trial_ent_block@example.com",
            "password": "Password123!",
            "name": "Trial Eng",
            "organization_name": "Trial Team",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["token"]
    resp = await client.post(
        "/api/v1/sessions/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ─── 2. Signed SLPRO- License Key Helpers & CLI ───────────────────────────────


def test_signed_license_key_generation_verification_and_cli(capsys):
    secret = "test_signing_secret_with_sufficient_length_1234567890"
    with patch.object(settings, "jwt_secret_key", secret):
        pro_key = generate_license_key("PRO", max_uses=1, days=30)
        ent_key = generate_license_key("ENTERPRISE", max_uses=10, days=365)

        assert pro_key.startswith("SLPRO-PRO-")
        assert ent_key.startswith("SLPRO-ENT-")

        v_pro = verify_license_key(pro_key)
        assert v_pro.plan == PlanTier.PRO
        assert v_pro.max_uses == 1
        assert v_pro.exp > int(time.time())

        v_ent = verify_license_key(ent_key)
        assert v_ent.plan == PlanTier.ENTERPRISE
        assert v_ent.max_uses == 10

        # Tampering fails verification
        tampered = pro_key[:-1] + ("A" if pro_key[-1] != "A" else "B")
        with pytest.raises(LicenseInvalidError):
            verify_license_key(tampered)

        # Tier prefix swap fails verification
        swapped = "SLPRO-ENT-" + pro_key[len("SLPRO-PRO-"):]
        with pytest.raises(LicenseInvalidError):
            verify_license_key(swapped)

        # Expired token fails with LicenseExpiredError
        expired_key = generate_license_key("PRO", max_uses=1, exp=int(time.time()) - 10)
        with pytest.raises(LicenseExpiredError):
            verify_license_key(expired_key)

        # CLI generates valid verifiable keys
        rc = cli_gen.main(["--plan", "PRO", "--days", "90", "--max-uses", "1", "--raw"])
        assert rc == 0
        cli_pro = capsys.readouterr().out.strip()
        assert cli_pro.startswith("SLPRO-PRO-")
        assert verify_license_key(cli_pro).plan == PlanTier.PRO

        rc2 = cli_gen.main(["--plan", "ENT", "--days", "365", "--max-uses", "10", "--raw"])
        assert rc2 == 0
        cli_ent = capsys.readouterr().out.strip()
        assert cli_ent.startswith("SLPRO-ENT-")
        verified_cli_ent = verify_license_key(cli_ent)
        assert verified_cli_ent.plan == PlanTier.ENTERPRISE
        assert verified_cli_ent.max_uses == 10


# ─── 3. /api/v1/billing/verify-license Endpoint ───────────────────────────────


async def _create_db_user(
    db_session: AsyncSession, email: str, plan: str = "FREE"
) -> User:
    u = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("StrongPass123!"),
        name="License Tester",
        plan=plan,
        onboarding_complete=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_verify_license_self_issued_pro_and_ent_without_gumroad_call(
    client: AsyncClient, db_session: AsyncSession
):
    secret = "prod_like_jwt_secret_key_for_license_verification_987654321"
    user1 = await _create_db_user(db_session, "slpro_user1@example.com", plan="FREE")
    user2 = await _create_db_user(db_session, "slpro_user2@example.com", plan="FREE")

    with patch.object(settings, "jwt_secret_key", secret):
        pro_key = generate_license_key("PRO", max_uses=1, days=30)
        ent_key = generate_license_key("ENTERPRISE", max_uses=10, days=365)

        app.dependency_overrides[verify_api_key] = lambda: UserContext(
            user_id=str(user1.id),
            plan=user1.plan,
            email=user1.email,
            name=user1.name or "",
            onboarding_complete=True,
        )
        mock_gumroad_client = MagicMock()
        mock_gumroad_client.__aenter__ = AsyncMock(return_value=mock_gumroad_client)
        mock_gumroad_client.__aexit__ = AsyncMock(return_value=False)
        mock_gumroad_client.post = AsyncMock()
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_gumroad_client

        with patch.object(gumroad_routes, "httpx", mock_httpx):
            resp = await client.post(
                "/api/v1/billing/verify-license",
                json={"license_key": pro_key},
            )
            mock_gumroad_client.post.assert_not_called()

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["plan"] == "PRO"

        await db_session.refresh(user1)
        assert user1.plan == "PRO"
        assert user1.gumroad_license_key == pro_key

        # Re-using an already redeemed SLPRO key on another account must fail
        app.dependency_overrides[verify_api_key] = lambda: UserContext(
            user_id=str(user2.id),
            plan=user2.plan,
            email=user2.email,
            name=user2.name or "",
            onboarding_complete=True,
        )
        replay_resp = await client.post(
            "/api/v1/billing/verify-license",
            json={"license_key": pro_key},
        )
        assert replay_resp.status_code == 400
        assert "already been redeemed" in replay_resp.json()["detail"].lower()

        # Valid SLPRO-ENT key upgrades user2 to ENTERPRISE
        with patch.object(gumroad_routes, "httpx", mock_httpx):
            ent_resp = await client.post(
                "/api/v1/billing/verify-license",
                json={"license_key": ent_key},
            )
            mock_gumroad_client.post.assert_not_called()

        assert ent_resp.status_code == 200
        assert ent_resp.json()["plan"] == "ENTERPRISE"
        await db_session.refresh(user2)
        assert user2.plan == "ENTERPRISE"
        assert user2.gumroad_license_key == ent_key


@pytest.mark.asyncio
async def test_verify_license_rejects_expired_and_tampered_slpro_keys(
    client: AsyncClient, db_session: AsyncSession
):
    secret = "prod_like_jwt_secret_key_for_license_verification_987654321"
    user = await _create_db_user(db_session, "slpro_bad@example.com", plan="FREE")

    app.dependency_overrides[verify_api_key] = lambda: UserContext(
        user_id=str(user.id),
        plan="FREE",
        email=user.email,
        name="Bad Key User",
        onboarding_complete=True,
    )

    with patch.object(settings, "jwt_secret_key", secret):
        expired_key = generate_license_key("PRO", exp=int(time.time()) - 60)
        tampered_key = generate_license_key("PRO", days=30)[:-2] + "ZZ"

        r_exp = await client.post(
            "/api/v1/billing/verify-license",
            json={"license_key": expired_key},
        )
        assert r_exp.status_code == 400
        assert "expired" in r_exp.json()["detail"].lower()

        r_tamper = await client.post(
            "/api/v1/billing/verify-license",
            json={"license_key": tampered_key},
        )
        assert r_tamper.status_code == 400

    await db_session.refresh(user)
    assert user.plan == "FREE"


@pytest.mark.asyncio
async def test_verify_license_keeps_gumroad_flow_for_non_slpro_keys(
    client: AsyncClient, db_session: AsyncSession
):
    user = await _create_db_user(db_session, "gumroad_user@example.com", plan="FREE")
    app.dependency_overrides[verify_api_key] = lambda: UserContext(
        user_id=str(user.id),
        plan="FREE",
        email=user.email,
        name="Gumroad User",
        onboarding_complete=True,
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "success": True,
        "uses": 1,
        "purchase": {"refunded": False, "chargebacked": False},
    }
    mock_gumroad_client = MagicMock()
    mock_gumroad_client.__aenter__ = AsyncMock(return_value=mock_gumroad_client)
    mock_gumroad_client.__aexit__ = AsyncMock(return_value=False)
    mock_gumroad_client.post = AsyncMock(return_value=mock_resp)
    mock_httpx = MagicMock()
    mock_httpx.AsyncClient.return_value = mock_gumroad_client

    with patch.object(gumroad_routes, "httpx", mock_httpx):
        resp = await client.post(
            "/api/v1/billing/verify-license",
            json={"license_key": "ABCD1234-EFGH5678-IJKL9012-MNOP3456"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"] == "PRO"
    mock_gumroad_client.post.assert_called_once()
    call_args = mock_gumroad_client.post.call_args
    assert call_args.args[0] == "https://api.gumroad.com/v2/licenses/verify"
    assert call_args.kwargs["data"] == {
        "product_permalink": settings.gumroad_product_permalink,
        "license_key": "ABCD1234-EFGH5678-IJKL9012-MNOP3456",
    }
    await db_session.refresh(user)
    assert user.plan == "PRO"
    assert user.gumroad_license_key == "ABCD1234-EFGH5678-IJKL9012-MNOP3456"


@pytest.mark.asyncio
async def test_verify_license_uses_gumroad_product_id_and_team_product_id(
    client: AsyncClient, db_session: AsyncSession
):
    pro_user = await _create_db_user(db_session, "gumroad_prod_id@example.com", plan="FREE")
    team_user = await _create_db_user(db_session, "gumroad_team_id@example.com", plan="FREE")

    # 1. When gumroad_product_id is configured, payload sends product_id (not product_permalink)
    pro_resp_mock = MagicMock()
    pro_resp_mock.json.return_value = {
        "success": True,
        "uses": 1,
        "purchase": {"product_id": "prod_pro_123", "refunded": False, "chargebacked": False},
    }
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=pro_resp_mock)
    mock_httpx = MagicMock()
    mock_httpx.AsyncClient.return_value = mock_client

    app.dependency_overrides[verify_api_key] = lambda: UserContext(
        user_id=str(pro_user.id),
        plan="FREE",
        email=pro_user.email,
        name="Pro Buyer",
        onboarding_complete=True,
    )
    with patch.object(settings, "gumroad_product_id", "prod_pro_123"), \
         patch.object(settings, "gumroad_team_product_id", "prod_team_999"), \
         patch.object(gumroad_routes, "httpx", mock_httpx):
        resp = await client.post(
            "/api/v1/billing/verify-license",
            json={"license_key": "PROKEY-1111-2222-3333"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"] == "PRO"
    mock_client.post.assert_called_once()
    assert mock_client.post.call_args.kwargs["data"] == {
        "product_id": "prod_pro_123",
        "license_key": "PROKEY-1111-2222-3333",
    }
    await db_session.refresh(pro_user)
    assert pro_user.plan == "PRO"

    # 2. Team Pass buyer: PRO product_id returns success=False, then team product_id succeeds -> ENTERPRISE
    fail_resp = MagicMock()
    fail_resp.json.return_value = {"success": False}
    team_resp = MagicMock()
    team_resp.json.return_value = {
        "success": True,
        "uses": 1,
        "purchase": {"product_id": "prod_team_999", "refunded": False, "chargebacked": False},
    }
    mock_client_team = MagicMock()
    mock_client_team.__aenter__ = AsyncMock(return_value=mock_client_team)
    mock_client_team.__aexit__ = AsyncMock(return_value=False)
    mock_client_team.post = AsyncMock(side_effect=[fail_resp, team_resp])
    mock_httpx_team = MagicMock()
    mock_httpx_team.AsyncClient.return_value = mock_client_team

    app.dependency_overrides[verify_api_key] = lambda: UserContext(
        user_id=str(team_user.id),
        plan="FREE",
        email=team_user.email,
        name="Team Buyer",
        onboarding_complete=True,
    )
    with patch.object(settings, "gumroad_product_id", "prod_pro_123"), \
         patch.object(settings, "gumroad_team_product_id", "prod_team_999"), \
         patch.object(gumroad_routes, "httpx", mock_httpx_team):
        resp_team = await client.post(
            "/api/v1/billing/verify-license",
            json={"license_key": "TEAMKEY-4444-5555-6666"},
        )

    assert resp_team.status_code == 200, resp_team.text
    assert resp_team.json()["plan"] == "ENTERPRISE"
    assert mock_client_team.post.call_count == 2
    assert mock_client_team.post.call_args_list[0].kwargs["data"] == {
        "product_id": "prod_pro_123",
        "license_key": "TEAMKEY-4444-5555-6666",
    }
    assert mock_client_team.post.call_args_list[1].kwargs["data"] == {
        "product_id": "prod_team_999",
        "license_key": "TEAMKEY-4444-5555-6666",
    }
    await db_session.refresh(team_user)
    assert team_user.plan == "ENTERPRISE"


@pytest.mark.asyncio
async def test_expired_trial_user_upgrades_cleanly_with_slpro_key(
    client: AsyncClient, db_session: AsyncSession
):
    reg = await client.post(
        "/api/v1/trials/register",
        json={
            "email": "trial_upgrade@example.com",
            "password": "Password123!",
            "name": "Upgrade Eng",
            "organization_name": "Upgrade Racing",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["token"]
    user_uuid = uuid.UUID(str(reg.json()["user_id"]))

    # Expire the trial
    trial = (await db_session.execute(select(Trial).where(Trial.user_id == user_uuid))).scalar_one()
    trial.status = "EXPIRED"
    trial.expires_at = datetime.now(timezone.utc) - timedelta(hours=3)
    await db_session.commit()

    secret = "prod_like_jwt_secret_key_for_license_verification_987654321"
    with patch.object(settings, "jwt_secret_key", secret):
        ent_key = generate_license_key("ENTERPRISE", max_uses=10, days=365)
        resp = await client.post(
            "/api/v1/billing/verify-license",
            headers={"Authorization": f"Bearer {token}"},
            json={"license_key": ent_key},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"] == "ENTERPRISE"

    # Now user is no longer treated as an expired trial and can access Enterprise endpoints
    me_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["plan"] == "ENTERPRISE"
    assert me_resp.json()["is_trial"] is False

    sess_resp = await client.post("/api/v1/sessions/", headers={"Authorization": f"Bearer {token}"})
    assert sess_resp.status_code == 201
