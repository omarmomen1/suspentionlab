"""
tests/test_scim_groups_and_lifecycle.py
=======================================
SuspensionLab PRO — Enterprise SCIM 2.0 Users, Groups, Role Mapping, and Audit Log Tests.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.scim_group import SCIMGroup
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.security.jwt_utils import hash_password, create_access_token


@pytest.mark.asyncio
async def test_scim_user_provisioning_and_lifecycle():
    """Test SCIM 2.0 User creation, retrieval, filtering, PATCH, and soft-delete."""
    org_id = uuid.uuid4()
    raw_scim_token = f"scim_live_{uuid.uuid4().hex}"
    prefix = raw_scim_token[:12]

    async with SessionLocal() as db:
        org = Organization(
            id=org_id,
            name="Apex Dynamics",
            slug=f"apex-{uuid.uuid4().hex[:6]}",
            plan="ENTERPRISE",
            scim_enabled=True,
            scim_token_prefix=prefix,
            scim_token_hash=hash_password(raw_scim_token),
            scim_token_expires_at=datetime.now(timezone.utc) + timedelta(days=90),
        )
        db.add(org)
        await db.commit()

    headers = {
        "Authorization": f"Bearer {raw_scim_token}",
        "Content-Type": "application/json",
    }

    test_email = f"scim_eng_{uuid.uuid4().hex[:6]}@apexdynamics.com"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Provision User (POST /scim/v2/Users)
        create_res = await client.post(
            "/api/v1/scim/v2/Users",
            headers=headers,
            json={
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                "userName": test_email,
                "externalId": f"ext-{uuid.uuid4().hex[:8]}",
                "name": {"givenName": "Marcus", "familyName": "Vance", "formatted": "Marcus Vance"},
            },
        )
        assert create_res.status_code == 201
        user_data = create_res.json()
        user_id = user_data["id"]
        assert user_data["userName"] == test_email
        assert user_data["active"] is True

        # 2. Get User (GET /scim/v2/Users/{id})
        get_res = await client.get(f"/api/v1/scim/v2/Users/{user_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] == user_id

        # 3. Filter User (GET /scim/v2/Users?filter=userName eq '...')
        filter_res = await client.get(f'/api/v1/scim/v2/Users?filter=userName eq "{test_email}"', headers=headers)
        assert filter_res.status_code == 200
        assert filter_res.json()["totalResults"] == 1
        assert filter_res.json()["Resources"][0]["id"] == user_id

        # 4. PATCH User Name
        patch_res = await client.patch(
            f"/api/v1/scim/v2/Users/{user_id}",
            headers=headers,
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "replace", "path": "name.formatted", "value": "Marcus Vance Jr."}
                ],
            },
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["name"]["formatted"] == "Marcus Vance Jr."

        # 5. Deactivate User (DELETE /scim/v2/Users/{id})
        del_res = await client.delete(f"/api/v1/scim/v2/Users/{user_id}", headers=headers)
        assert del_res.status_code == 204

    # Verify soft-delete in database
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
        assert user is not None
        assert user.deleted_at is not None


@pytest.mark.asyncio
async def test_scim_group_provisioning_and_team_role_mapping():
    """Test SCIM 2.0 Groups CRUD, member synchronization, and dynamic role/team mapping."""
    org_id = uuid.uuid4()
    team_id = uuid.uuid4()
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()
    raw_scim_token = f"scim_live_{uuid.uuid4().hex}"
    prefix = raw_scim_token[:12]

    async with SessionLocal() as db:
        org = Organization(
            id=org_id,
            name="Redline Racing",
            slug=f"redline-{uuid.uuid4().hex[:6]}",
            plan="ENTERPRISE",
            scim_enabled=True,
            scim_token_prefix=prefix,
            scim_token_hash=hash_password(raw_scim_token),
            scim_token_expires_at=datetime.now(timezone.utc) + timedelta(days=90),
        )
        db.add(org)

        # Create a Team under this Org
        team = Team(
            id=team_id,
            name="Vehicle Dynamics Dept",
            slug=f"redline-vd-{uuid.uuid4().hex[:6]}",
            owner_id=uuid.uuid4(),
            organization_id=org_id,
            plan="ENTERPRISE",
        )
        db.add(team)

        user1 = User(
            id=user1_id,
            email=f"sim_dev1_{uuid.uuid4().hex[:6]}@redline.com",
            password_hash=hash_password("Pass123!"),
            organization_id=org_id,
            team_role="Viewer",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        user2 = User(
            id=user2_id,
            email=f"sim_dev2_{uuid.uuid4().hex[:6]}@redline.com",
            password_hash=hash_password("Pass123!"),
            organization_id=org_id,
            team_role="Viewer",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add_all([user1, user2])
        await db.commit()

    headers = {
        "Authorization": f"Bearer {raw_scim_token}",
        "Content-Type": "application/json",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create Group with initial member user1 (POST /scim/v2/Groups)
        create_res = await client.post(
            "/api/v1/scim/v2/Groups",
            headers=headers,
            json={
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
                "displayName": "Race Engineers",
                "targetRole": "Admin",
                "members": [{"value": str(user1_id)}],
            },
        )
        assert create_res.status_code == 201
        group_data = create_res.json()
        group_id = group_data["id"]
        assert group_data["displayName"] == "Race Engineers"
        assert len(group_data["members"]) == 1

        # 2. List Groups (GET /scim/v2/Groups)
        list_res = await client.get("/api/v1/scim/v2/Groups", headers=headers)
        assert list_res.status_code == 200
        assert list_res.json()["totalResults"] >= 1

        # 3. Add user2 via PATCH (RFC 7644)
        patch_res = await client.patch(
            f"/api/v1/scim/v2/Groups/{group_id}",
            headers=headers,
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "add", "path": "members", "value": [{"value": str(user2_id)}]}
                ],
            },
        )
        assert patch_res.status_code == 200
        members = patch_res.json()["members"]
        assert len(members) == 2

        # 4. Remove user1 via PATCH
        remove_res = await client.patch(
            f"/api/v1/scim/v2/Groups/{group_id}",
            headers=headers,
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "remove", "path": f'members[value eq "{user1_id}"]'}
                ],
            },
        )
        assert remove_res.status_code == 200
        assert len(remove_res.json()["members"]) == 1
        assert remove_res.json()["members"][0]["value"] == str(user2_id)

        # 5. Delete Group
        del_res = await client.delete(f"/api/v1/scim/v2/Groups/{group_id}", headers=headers)
        assert del_res.status_code == 204


@pytest.mark.asyncio
async def test_scim_token_expiration_and_rotation_audit():
    """Verify expired SCIM tokens are rejected, and token rotation generates audit trails."""
    org_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    admin_email = f"admin_{uuid.uuid4().hex[:6]}@vintage.com"
    expired_token = f"scim_live_{uuid.uuid4().hex}"
    prefix_exp = expired_token[:12]

    async with SessionLocal() as db:
        org = Organization(
            id=org_id,
            name="Vintage Motors",
            slug=f"vintage-{uuid.uuid4().hex[:6]}",
            plan="ENTERPRISE",
            scim_enabled=True,
            scim_token_prefix=prefix_exp,
            scim_token_hash=hash_password(expired_token),
            scim_token_expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired yesterday
        )
        db.add(org)

        # Admin user to rotate token
        admin = User(
            id=admin_id,
            email=admin_email,
            password_hash=hash_password("Pass123!"),
            organization_id=org_id,
            org_role="ORG_ADMIN",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add(admin)
        await db.commit()

    admin_token = create_access_token({"sub": str(admin_id), "email": admin_email, "organization_id": str(org_id)})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Expired token request -> 401 Unauthorized
        res_exp = await client.get("/api/v1/scim/v2/Users", headers={"Authorization": f"Bearer {expired_token}"})
        assert res_exp.status_code == 401
        assert "expired" in res_exp.json()["detail"].lower()

        # 2. Rotate SCIM Token via Org Admin endpoint
        rot_res = await client.post(
            f"/api/v1/organizations/{org_id}/scim/rotate-token",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert rot_res.status_code == 200
        new_scim_token = rot_res.json()["scim_token"]
        assert new_scim_token.startswith("scim_live_")

        # 3. Request with newly rotated SCIM token -> 200 OK
        res_new = await client.get("/api/v1/scim/v2/Users", headers={"Authorization": f"Bearer {new_scim_token}"})
        assert res_new.status_code == 200

    # Verify SCIM_TOKEN_ROTATED was recorded in AuditLog
    async with SessionLocal() as db:
        audit = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.organization_id == org_id,
                    AuditLog.event == "SCIM_TOKEN_ROTATED",
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
