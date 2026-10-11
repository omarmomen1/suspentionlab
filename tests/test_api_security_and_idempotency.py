"""
tests/test_api_security_and_idempotency.py
==========================================
SuspensionLab PRO — Enterprise API Security, Idempotency, Payload Bounds, and Route Protection Matrix.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password


@pytest.mark.asyncio
async def test_security_headers_middleware():
    """Verify strict enterprise security headers on all API responses."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        headers = res.headers

        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert "Strict-Transport-Security" in headers
        assert "Content-Security-Policy" in headers
        assert "Permissions-Policy" in headers


@pytest.mark.asyncio
async def test_payload_size_limit_rejection():
    """Verify oversized payloads exceeding 10MB are rejected with HTTP 413."""
    oversized_headers = {
        "Content-Length": str(15 * 1024 * 1024),  # 15MB
        "Content-Type": "application/json",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/health", headers=oversized_headers)
        assert res.status_code == 413
        assert "payload_too_large" in res.json()["error"]


@pytest.mark.asyncio
async def test_idempotency_caching_and_conflict_detection():
    """Verify Idempotency-Key caching, replay headers, and payload conflict detection."""
    user_id = uuid.uuid4()
    user_email = f"idemp_{uuid.uuid4().hex[:6]}@motorsport.com"

    async with SessionLocal() as db:
        user = User(
            id=user_id,
            email=user_email,
            password_hash=hash_password("Pass123!"),
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add(user)
        await db.commit()

    token = create_access_token({"sub": str(user_id), "email": user_email, "plan": "ENTERPRISE"})
    idempotency_key = f"idemp-key-{uuid.uuid4().hex}"
    req_body = {
        "name": f"Idempotent Org {uuid.uuid4().hex[:6]}",
        "slug": f"idemp-org-{uuid.uuid4().hex[:6]}",
        "plan": "ENTERPRISE",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        }

        # 1. First execution
        res1 = await client.post("/api/v1/organizations", json=req_body, headers=headers)
        assert res1.status_code == 201
        data1 = res1.json()

        # 2. Replay with exact same Idempotency-Key & body
        res2 = await client.post("/api/v1/organizations", json=req_body, headers=headers)
        assert res2.status_code == 201
        data2 = res2.json()
        assert data1["id"] == data2["id"]
        assert res2.headers.get("X-Idempotent-Replay") == "true"

        # 3. Replay with SAME Idempotency-Key but DIFFERENT body -> 409 Conflict
        conflicting_body = dict(req_body)
        conflicting_body["name"] = "Different Name Payload"
        res_conflict = await client.post("/api/v1/organizations", json=conflicting_body, headers=headers)
        assert res_conflict.status_code == 409
        assert "conflict" in res_conflict.json()["error"]


@pytest.mark.asyncio
async def test_route_security_matrix():
    """
    Test 4-point security matrix on sensitive endpoints:
      1. Authorized request -> 200/201
      2. Unauthorized request (no credentials) -> 401
      3. Wrong role (insufficient permissions) -> 403
      4. Wrong tenant (cross-tenant access) -> 403/404
    """
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()
    admin_user_id = uuid.uuid4()
    admin_email = f"admin_{uuid.uuid4().hex[:6]}@ferrari.com"
    viewer_user_id = uuid.uuid4()
    viewer_email = f"viewer_{uuid.uuid4().hex[:6]}@ferrari.com"
    other_tenant_admin_id = uuid.uuid4()
    other_email = f"admin_{uuid.uuid4().hex[:6]}@mercedes.com"

    async with SessionLocal() as db:
        org1 = Organization(id=org1_id, name="Scuderia Ferrari", slug=f"ferrari-{uuid.uuid4().hex[:6]}")
        org2 = Organization(id=org2_id, name="Mercedes F1", slug=f"mercedes-{uuid.uuid4().hex[:6]}")
        db.add_all([org1, org2])

        # Admin user in Org 1
        admin_user = User(
            id=admin_user_id,
            email=admin_email,
            password_hash=hash_password("Pass123!"),
            organization_id=org1_id,
            org_role="ORG_ADMIN",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        # Member user in Org 1 (lacks ORG_ADMIN permission)
        viewer_user = User(
            id=viewer_user_id,
            email=viewer_email,
            password_hash=hash_password("Pass123!"),
            organization_id=org1_id,
            org_role="MEMBER",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        # Admin in Org 2
        other_tenant_admin = User(
            id=other_tenant_admin_id,
            email=other_email,
            password_hash=hash_password("Pass123!"),
            organization_id=org2_id,
            org_role="ORG_ADMIN",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add_all([admin_user, viewer_user, other_tenant_admin])
        await db.commit()

    token_admin = create_access_token({"sub": str(admin_user_id), "email": admin_email, "organization_id": str(org1_id)})
    token_viewer = create_access_token({"sub": str(viewer_user_id), "email": viewer_email, "organization_id": str(org1_id)})
    token_other_tenant = create_access_token({"sub": str(other_tenant_admin_id), "email": other_email, "organization_id": str(org2_id)})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        endpoint = f"/api/v1/organizations/{org1_id}/scim/rotate-token"

        # 1. Authorized request (Org 1 Admin) -> 200
        res_auth = await client.post(endpoint, headers={"Authorization": f"Bearer {token_admin}"})
        assert res_auth.status_code == 200

        # 2. Unauthorized request (No auth header) -> 401
        res_unauth = await client.post(endpoint)
        assert res_unauth.status_code == 401

        # 3. Wrong role (Viewer/Member in Org 1 without ORG_ADMIN) -> 403
        res_wrong_role = await client.post(endpoint, headers={"Authorization": f"Bearer {token_viewer}"})
        assert res_wrong_role.status_code == 403

        # 4. Wrong tenant (Admin from Org 2 attempting access on Org 1) -> 403
        res_wrong_tenant = await client.post(endpoint, headers={"Authorization": f"Bearer {token_other_tenant}"})
        assert res_wrong_tenant.status_code == 403
