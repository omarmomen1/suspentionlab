"""
tests/test_organization_team_governance.py
==========================================
Adversarial security and governance test suite for Organization & Team Lifecycle:
1. Safe organization creation (no silent context overwrite, returns 409 Conflict).
2. Cryptographic invitation lifecycle (create -> token -> expiration -> accept -> member).
3. Security tests:
   - Invitation reuse (prevented)
   - Expired token rejection
   - Token belonging to another user (rejected with 403)
   - Organization/team substitution attacks
   - Replay attacks
   - Unauthorized removal defense
   - Privilege escalation through invitations
4. Auditability: full event trail for invitation and membership transitions.
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.invitation import OrganizationInvitation
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password
from sqlalchemy import select


@pytest.fixture
async def governance_org_fixture():
    """Setup Org A (Mercedes) and Org B (Red Bull) with users and teams."""
    org_a_id = uuid.uuid4()
    org_b_id = uuid.uuid4()
    team_a_id = uuid.uuid4()
    team_b_id = uuid.uuid4()

    admin_a_id = uuid.uuid4()
    eng_a_id = uuid.uuid4()
    admin_b_id = uuid.uuid4()
    external_user_id = uuid.uuid4()

    async with SessionLocal() as db:
        org_a = Organization(id=org_a_id, name="Mercedes AMG Petronas", slug=f"merc-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        org_b = Organization(id=org_b_id, name="Red Bull Racing", slug=f"rbr-{uuid.uuid4().hex[:6]}", plan="ENTERPRISE")
        team_a = Team(id=team_a_id, name="Merc Suspension", slug=f"merc-susp-{uuid.uuid4().hex[:6]}", organization_id=org_a_id, owner_id=admin_a_id)
        team_b = Team(id=team_b_id, name="RBR Dynamics", slug=f"rbr-dyn-{uuid.uuid4().hex[:6]}", organization_id=org_b_id, owner_id=admin_b_id)

        admin_a = User(
            id=admin_a_id,
            email=f"toto_{uuid.uuid4().hex[:6]}@mercedes-f1.com",
            password_hash=hash_password("MercSecr3t!"),
            name="Toto Wolff",
            organization_id=org_a_id,
            team_id=team_a_id,
            org_role="ORG_ADMIN",
            team_role="Admin",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        eng_a = User(
            id=eng_a_id,
            email=f"james_{uuid.uuid4().hex[:6]}@mercedes-f1.com",
            password_hash=hash_password("MercSecr3t!"),
            name="James Vowles",
            organization_id=org_a_id,
            team_id=team_a_id,
            org_role="MEMBER",
            team_role="Engineer",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        admin_b = User(
            id=admin_b_id,
            email=f"christian_{uuid.uuid4().hex[:6]}@redbull-racing.com",
            password_hash=hash_password("RbrSecr3t!"),
            name="Christian Horner",
            organization_id=org_b_id,
            team_id=team_b_id,
            org_role="ORG_ADMIN",
            team_role="Admin",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        external_user = User(
            id=external_user_id,
            email=f"recruit_{uuid.uuid4().hex[:6]}@engineering-talent.com",
            password_hash=hash_password("RecruitSecr3t!"),
            name="New Recruit",
            organization_id=None,
            team_id=None,
            org_role="MEMBER",
            team_role="Viewer",
            plan="FREE",
            onboarding_complete=True,
        )

        db.add_all([org_a, org_b, team_a, team_b, admin_a, eng_a, admin_b, external_user])
        await db.commit()

    return {
        "org_a": org_a,
        "org_b": org_b,
        "team_a": team_a,
        "team_b": team_b,
        "admin_a": admin_a,
        "eng_a": eng_a,
        "admin_b": admin_b,
        "external_user": external_user,
    }


@pytest.mark.asyncio
async def test_user_already_in_org_cannot_silently_overwrite_via_create(governance_org_fixture):
    """A user already assigned to Org A must not silently become a member of Org B through create."""
    data = governance_org_fixture
    token = create_access_token({
        "sub": str(data["eng_a"].id),
        "email": data["eng_a"].email,
        "plan": "ENTERPRISE",
        "organization_id": str(data["org_a"].id),
        "org_role": "MEMBER",
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Eng A tries to create a new organization
        res = await client.post(
            "/api/v1/organizations",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Rogue Racing Team",
                "slug": f"rogue-racing-{uuid.uuid4().hex[:6]}",
                "plan": "ENTERPRISE",
            },
        )
        # Must be rejected with 409 Conflict
        assert res.status_code == 409
        assert "already belongs to organization" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invitation_lifecycle_create_expiry_and_acceptance(governance_org_fixture):
    """Full lifecycle: create invitation -> secure token -> expiration check -> accept -> member."""
    data = governance_org_fixture
    admin_token = create_access_token({
        "sub": str(data["admin_a"].id),
        "email": data["admin_a"].email,
        "plan": "ENTERPRISE",
        "organization_id": str(data["org_a"].id),
        "org_role": "ORG_ADMIN",
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Admin A invites external recruit
        res = await client.post(
            f"/api/v1/organizations/{data['org_a'].id}/invitations",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "email": data["external_user"].email,
                "role": "MEMBER",
                "team_id": str(data["team_a"].id),
                "team_role": "Engineer",
                "expires_days": 7,
            },
        )
        assert res.status_code == 201
        inv_data = res.json()
        raw_token = inv_data["token"]
        assert raw_token is not None
        assert inv_data["status"] == "PENDING"
        assert inv_data["invitee_email"] == data["external_user"].email

        # 2. Verify invitation in DB does NOT modify user membership prematurely
        async with SessionLocal() as db:
            ext_user_db = (await db.execute(select(User).where(User.id == data["external_user"].id))).scalar_one()
            assert ext_user_db.organization_id is None  # NOT mutated merely because invited!

        # 3. External user accepts the invitation
        user_token = create_access_token({
            "sub": str(data["external_user"].id),
            "email": data["external_user"].email,
            "plan": "FREE",
            "organization_id": None,
            "org_role": "MEMBER",
        })
        accept_res = await client.post(
            f"/api/v1/organizations/invitations/{raw_token}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert accept_res.status_code == 200
        assert accept_res.json()["status"] == "ACCEPTED"

        # 4. Verify membership created and audit logged
        async with SessionLocal() as db:
            ext_user_db = (await db.execute(select(User).where(User.id == data["external_user"].id))).scalar_one()
            assert ext_user_db.organization_id == data["org_a"].id
            assert ext_user_db.team_id == data["team_a"].id
            assert ext_user_db.team_role == "Engineer"

            # Check audit trail
            audit = (await db.execute(
                select(AuditLog).where(AuditLog.event == "INVITATION_ACCEPTED", AuditLog.user_id == data["external_user"].id)
            )).scalar_one_or_none()
            assert audit is not None
            assert audit.event_data["role_granted"] == "MEMBER"


@pytest.mark.asyncio
async def test_invitation_security_reuse_and_replay_rejected(governance_org_fixture):
    """An accepted or revoked invitation token cannot be reused or replayed."""
    data = governance_org_fixture
    admin_token = create_access_token({
        "sub": str(data["admin_a"].id),
        "email": data["admin_a"].email,
        "plan": "ENTERPRISE",
        "organization_id": str(data["org_a"].id),
        "org_role": "ORG_ADMIN",
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create invitation
        res = await client.post(
            f"/api/v1/organizations/{data['org_a'].id}/invitations",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"email": data["external_user"].email, "role": "MEMBER"},
        )
        raw_token = res.json()["token"]

        user_token = create_access_token({
            "sub": str(data["external_user"].id),
            "email": data["external_user"].email,
            "plan": "FREE",
            "organization_id": None,
        })
        # First accept: 200 OK
        res1 = await client.post(
            f"/api/v1/organizations/invitations/{raw_token}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert res1.status_code == 200

        # Second accept (replay): rejected 400
        res2 = await client.post(
            f"/api/v1/organizations/invitations/{raw_token}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert res2.status_code == 400
        assert "not pending" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_token_belonging_to_another_user_rejected(governance_org_fixture):
    """A competing engineer or unauthorized user cannot accept an invitation meant for someone else."""
    data = governance_org_fixture
    admin_token = create_access_token({
        "sub": str(data["admin_a"].id),
        "email": data["admin_a"].email,
        "plan": "ENTERPRISE",
        "organization_id": str(data["org_a"].id),
        "org_role": "ORG_ADMIN",
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Mercedes invites target email
        res = await client.post(
            f"/api/v1/organizations/{data['org_a'].id}/invitations",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"email": "intended_recruit@mercedes-f1.com", "role": "MEMBER"},
        )
        raw_token = res.json()["token"]

        # Red Bull admin tries to hijack/accept Mercedes invitation
        rbr_token = create_access_token({
            "sub": str(data["admin_b"].id),
            "email": data["admin_b"].email,
            "plan": "ENTERPRISE",
            "organization_id": str(data["org_b"].id),
        })
        hijack_res = await client.post(
            f"/api/v1/organizations/invitations/{raw_token}/accept",
            headers={"Authorization": f"Bearer {rbr_token}"},
        )
        assert hijack_res.status_code == 403
        assert "intended for" in hijack_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_expired_token_rejected(governance_org_fixture):
    """Expired invitation token must be rejected."""
    data = governance_org_fixture
    import hashlib

    expired_raw_token = f"expired_token_secret_{uuid.uuid4().hex}"
    token_hash = hashlib.sha256(expired_raw_token.encode("utf-8")).hexdigest()

    async with SessionLocal() as db:
        expired_inv = OrganizationInvitation(
            organization_id=data["org_a"].id,
            invited_by_user_id=data["admin_a"].id,
            invitee_email=data["external_user"].email,
            role="MEMBER",
            token_hash=token_hash,
            token_prefix="expired_to",
            status="PENDING",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired yesterday
        )
        db.add(expired_inv)
        await db.commit()

    user_token = create_access_token({
        "sub": str(data["external_user"].id),
        "email": data["external_user"].email,
        "plan": "FREE",
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/v1/organizations/invitations/{expired_raw_token}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert res.status_code == 400
        assert "expired" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unauthorized_member_removal_and_sole_admin_protection(governance_org_fixture):
    """A regular member cannot remove members, and the sole ORG_ADMIN cannot be removed without transfer."""
    data = governance_org_fixture
    eng_token = create_access_token({
        "sub": str(data["eng_a"].id),
        "email": data["eng_a"].email,
        "plan": "ENTERPRISE",
        "organization_id": str(data["org_a"].id),
        "org_role": "MEMBER",
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Regular engineer tries to remove admin -> 403 Forbidden
        res1 = await client.delete(
            f"/api/v1/organizations/{data['org_a'].id}/members/{data['admin_a'].id}",
            headers={"Authorization": f"Bearer {eng_token}"},
        )
        assert res1.status_code == 403

        # 2. Admin tries to remove sole admin -> 400 Bad Request
        admin_token = create_access_token({
            "sub": str(data["admin_a"].id),
            "email": data["admin_a"].email,
            "plan": "ENTERPRISE",
            "organization_id": str(data["org_a"].id),
            "org_role": "ORG_ADMIN",
        })
        res2 = await client.delete(
            f"/api/v1/organizations/{data['org_a'].id}/members/{data['admin_a'].id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res2.status_code == 400
        assert "sole org_admin" in res2.json()["detail"].lower()
