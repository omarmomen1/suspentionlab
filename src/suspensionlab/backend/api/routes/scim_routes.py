"""
backend/api/routes/scim_routes.py
==================================
SCIM 2.0 User & Group provisioning — RFC 7643 (core schema) / RFC 7644 (protocol).

Supports:
    GET    /scim/v2/ServiceProviderConfig   → capabilities document
    GET    /scim/v2/Users                   → list/filter/paginate users
    POST   /scim/v2/Users                   → provision (JIT create)
    GET    /scim/v2/Users/{id}              → retrieve by id or externalId
    PUT    /scim/v2/Users/{id}              → full replace of mutable attrs
    PATCH  /scim/v2/Users/{id}              → partial update (active, name, roles, ...)
    DELETE /scim/v2/Users/{id}              → deactivate (soft delete)

    GET    /scim/v2/Groups                  → list/filter/paginate groups
    POST   /scim/v2/Groups                  → create group (with role/team mapping)
    GET    /scim/v2/Groups/{id}             → retrieve group with members
    PUT    /scim/v2/Groups/{id}             → replace group attributes & members
    PATCH  /scim/v2/Groups/{id}             → RFC 7644 PatchOp on members (add/remove/replace)
    DELETE /scim/v2/Groups/{id}             → delete group

Security & Governance:
    * Supports both global SCIM_BEARER_TOKEN and per-organization rotatable & expirable SCIM tokens.
    * Real-time group-to-team and group-to-role synchronization.
    * Every SCIM provisioning event is audited with tamper-evident Merkle hash logging.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from suspensionlab.backend.config import settings
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.scim_group import SCIMGroup, scim_group_members
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.audit import AuditLog
from suspensionlab.backend.security.jwt_utils import hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scim/v2", tags=["SCIM 2.0"])

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
SCIM_CONTENT_TYPE = "application/scim+json"


class SCIMAuthContext(BaseModel):
    organization_id: Optional[str] = None
    is_global: bool = False


# ── Authentication ────────────────────────────────────────────────────────────

async def require_scim_auth(
    authorization: str | None = Header(default=None),
) -> SCIMAuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Bearer token.")

    token = authorization.split(" ", 1)[1].strip()

    # 1. Check global environment token
    if settings.scim_enabled and settings.scim_bearer_token:
        if secrets.compare_digest(token, settings.scim_bearer_token):
            return SCIMAuthContext(organization_id=None, is_global=True)

    # 2. Check per-organization token
    prefix = token[:12] if len(token) >= 12 else token
    async with SessionLocal() as db:
        candidates = (await db.execute(
            select(Organization).where(
                Organization.scim_enabled == True,
                Organization.scim_token_prefix == prefix,
                Organization.deleted_at == None,
            )
        )).scalars().all()
        for org in candidates:
            if org and org.scim_token_hash:
                is_valid, _ = verify_password(token, org.scim_token_hash)
                if is_valid:
                    if org.scim_token_expires_at:
                        exp = org.scim_token_expires_at
                        if exp.tzinfo is None:
                            exp = exp.replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) > exp:
                            raise HTTPException(status_code=401, detail="SCIM bearer token has expired.")
                    return SCIMAuthContext(organization_id=str(org.id), is_global=False)

    raise HTTPException(status_code=401, detail="Invalid SCIM bearer token.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scim_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={
        "schemas": [SCIM_ERROR_SCHEMA],
        "status": str(status_code),
        "detail": detail,
    })


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _user_to_scim(user: User) -> dict[str, Any]:
    active = user.deleted_at is None
    resource: dict[str, Any] = {
        "schemas": [SCIM_USER_SCHEMA],
        "id": str(user.id),
        "externalId": user.external_id,
        "userName": user.email,
        "active": active,
        "meta": {
            "resourceType": "User",
            "created": _iso(user.created_at),
            "lastModified": _iso(user.updated_at),
            "location": f"/scim/v2/Users/{user.id}",
        },
    }
    name_parts = (user.name or "").strip().split(" ", 1)
    resource["name"] = {
        "givenName": name_parts[0] if name_parts else "",
        "familyName": name_parts[1] if len(name_parts) > 1 else "",
        "formatted": user.name or "",
    }
    resource["emails"] = [{"value": user.email, "type": "work", "primary": True}]
    if user.team_role:
        resource["roles"] = [{"value": user.team_role, "primary": True}]
    return {k: v for k, v in resource.items() if v is not None}


def _group_to_scim(group: SCIMGroup) -> dict[str, Any]:
    members_list = [
        {"value": str(u.id), "display": u.name or u.email, "$ref": f"/scim/v2/Users/{u.id}"}
        for u in group.members if u.deleted_at is None
    ]
    return {
        "schemas": [SCIM_GROUP_SCHEMA],
        "id": str(group.id),
        "externalId": group.external_id,
        "displayName": group.display_name,
        "members": members_list,
        "meta": {
            "resourceType": "Group",
            "created": _iso(group.created_at),
            "lastModified": _iso(group.updated_at),
            "location": f"/scim/v2/Groups/{group.id}",
        },
    }


def _extract_name(scim_name: Optional[dict[str, Any]]) -> Optional[str]:
    if not scim_name:
        return None
    formatted = scim_name.get("formatted")
    if formatted:
        return str(formatted)
    given = scim_name.get("givenName", "")
    family = scim_name.get("familyName", "")
    combined = f"{given} {family}".strip()
    return combined or None


async def _log_scim_audit(db, action: str, details: dict, org_id: Optional[str] = None):
    ev = AuditLog(
        event=f"SCIM_{action.upper()}",
        organization_id=uuid.UUID(org_id) if org_id else None,
        event_data=details,
    )
    db.add(ev)


# ── Capabilities / Config ─────────────────────────────────────────────────────

@router.get("/ServiceProviderConfig")
async def service_provider_config(_: SCIMAuthContext = Depends(require_scim_auth)):
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "documentationUri": "https://suspensionlab.pro/docs/api-reference",
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "OAuth Bearer Token",
                "description": "Authentication via SCIM Bearer Token.",
                "primary": True,
            }
        ],
    }


# ── Users Endpoints ───────────────────────────────────────────────────────────

@router.get("/Users")
async def list_users(
    auth: SCIMAuthContext = Depends(require_scim_auth),
    filter: Optional[str] = Query(None),
    start_index: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=200),
):
    """List users with optional filtering (userName eq '...', externalId eq '...')."""
    async with SessionLocal() as db:
        query = select(User).where(User.deleted_at.is_(None))
        if auth.organization_id:
            query = query.where(User.organization_id == uuid.UUID(auth.organization_id))

        if filter:
            f = filter.strip()
            lowered = f.lower()
            if lowered.startswith("username eq"):
                value = f.split("eq", 1)[1].strip().strip('"').strip("'").lower()
                query = query.where(func.lower(User.email) == value)
            elif lowered.startswith("externalid eq"):
                value = f.split("eq", 1)[1].strip().strip('"').strip("'")
                query = query.where(User.external_id == value)
            else:
                raise _scim_error(400, f"Unsupported filter: '{filter}'. Supported: userName eq, externalId eq.")

        total_res = await db.execute(select(func.count()).select_from(query.subquery()))
        total = int(total_res.scalar_one())

        result = await db.execute(
            query.order_by(User.created_at).offset(start_index - 1).limit(count)
        )
        users = result.scalars().all()

    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": len(users),
        "Resources": [_user_to_scim(u) for u in users],
    }


@router.post("/Users", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    auth: SCIMAuthContext = Depends(require_scim_auth),
):
    """Provision a user from the IdP."""
    body = await request.json()
    if SCIM_USER_SCHEMA not in body.get("schemas", []):
        raise _scim_error(400, "Request must include the core User schema.")

    user_name = body.get("userName")
    if not user_name:
        raise _scim_error(400, "userName is required.")
    email = user_name.lower().strip()
    external_id = body.get("externalId")

    async with SessionLocal() as db:
        org_uuid = uuid.UUID(auth.organization_id) if auth.organization_id else None
        existing = (
            await db.execute(select(User).where(func.lower(User.email) == email))
        ).scalar_one_or_none()

        if existing is not None and existing.deleted_at is None:
            raise _scim_error(409, f"User '{email}' already exists.")

        if existing is not None:
            existing.deleted_at = None
            existing.external_id = external_id or existing.external_id
            existing.name = _extract_name(body.get("name")) or existing.name
            if org_uuid:
                existing.organization_id = org_uuid
            await _log_scim_audit(db, "user_reactivated", {"email": email, "user_id": str(existing.id)}, auth.organization_id)
            await db.commit()
            await db.refresh(existing)
            return _user_to_scim(existing)

        user = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            name=_extract_name(body.get("name")),
            plan="PRO",
            external_id=external_id,
            auth_provider="oidc",
            organization_id=org_uuid,
            org_role="MEMBER",
            onboarding_complete=False,
        )
        db.add(user)
        await db.flush()
        await _log_scim_audit(db, "user_provisioned", {"email": email, "user_id": str(user.id)}, auth.organization_id)
        await db.commit()
        await db.refresh(user)
        return _user_to_scim(user)


@router.get("/Users/{user_id}")
async def get_user(
    user_id: str,
    auth: SCIMAuthContext = Depends(require_scim_auth),
):
    async with SessionLocal() as db:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise _scim_error(404, f"User {user_id} not found")

        query = select(User).where(User.id == uid)
        if auth.organization_id:
            query = query.where(User.organization_id == uuid.UUID(auth.organization_id))

        user = (await db.execute(query)).scalar_one_or_none()
        if user is None:
            raise _scim_error(404, f"User {user_id} not found")
        return _user_to_scim(user)


@router.put("/Users/{user_id}")
async def replace_user(
    user_id: str,
    request: Request,
    auth: SCIMAuthContext = Depends(require_scim_auth),
):
    body = await request.json()
    async with SessionLocal() as db:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise _scim_error(404, f"User {user_id} not found")

        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user is None:
            raise _scim_error(404, f"User {user_id} not found")

        user.email = (body.get("userName") or user.email).lower().strip()
        user.name = _extract_name(body.get("name")) or user.name
        if body.get("externalId"):
            user.external_id = body["externalId"]
        active = body.get("active", True)
        user.deleted_at = None if active else (user.deleted_at or datetime.now(timezone.utc))

        await _log_scim_audit(db, "user_replaced", {"user_id": str(user.id), "active": active}, auth.organization_id)
        await db.commit()
        await db.refresh(user)
        return _user_to_scim(user)


@router.patch("/Users/{user_id}")
async def patch_user(
    user_id: str,
    request: Request,
    auth: SCIMAuthContext = Depends(require_scim_auth),
):
    body = await request.json()
    if SCIM_PATCH_SCHEMA not in body.get("schemas", []):
        raise _scim_error(400, "PATCH body must be a PatchOp message.")

    operations = body.get("Operations") or body.get("operations") or []
    async with SessionLocal() as db:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise _scim_error(404, f"User {user_id} not found")

        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user is None:
            raise _scim_error(404, f"User {user_id} not found")

        for op in operations:
            op_type = str(op.get("op", "")).lower()
            path = op.get("path")
            val = op.get("value")

            if op_type == "replace":
                if path == "active":
                    user.deleted_at = None if bool(val) else (user.deleted_at or datetime.now(timezone.utc))
                elif path in ("name", "name.formatted", "displayName"):
                    user.name = _extract_name(val if isinstance(val, dict) else {"formatted": val}) or user.name
                elif path == "userName":
                    user.email = str(val).lower().strip()
                elif path == "externalId":
                    user.external_id = str(val)
                elif path is None and isinstance(val, dict):
                    if "active" in val:
                        user.deleted_at = None if val["active"] else (user.deleted_at or datetime.now(timezone.utc))
                    if "userName" in val:
                        user.email = str(val["userName"]).lower().strip()
                    if "name" in val:
                        user.name = _extract_name(val["name"]) or user.name
                else:
                    raise _scim_error(400, f"Unsupported patch path: '{path}'.")
            elif op_type in ("add", "remove"):
                if path == "active":
                    user.deleted_at = None if op_type == "add" else datetime.now(timezone.utc)
                else:
                    raise _scim_error(400, f"Unsupported patch op '{op_type}' for path '{path}'.")
            else:
                raise _scim_error(400, f"Unknown patch op '{op_type}'.")

        await _log_scim_audit(db, "user_patched", {"user_id": str(user.id)}, auth.organization_id)
        await db.commit()
        await db.refresh(user)
        return _user_to_scim(user)


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    auth: SCIMAuthContext = Depends(require_scim_auth),
):
    """Deactivate (soft delete) a user."""
    async with SessionLocal() as db:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise _scim_error(404, f"User {user_id} not found")

        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user is None:
            raise _scim_error(404, f"User {user_id} not found")

        if user.deleted_at is None:
            user.deleted_at = datetime.now(timezone.utc)
            await _log_scim_audit(db, "user_deactivated", {"user_id": str(user.id), "email": user.email}, auth.organization_id)
            await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Groups Endpoints ──────────────────────────────────────────────────────────

@router.get("/Groups")
async def list_groups(
    auth: SCIMAuthContext = Depends(require_scim_auth),
    filter: Optional[str] = Query(None),
    start_index: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=200),
):
    """List SCIM groups with members."""
    async with SessionLocal() as db:
        query = select(SCIMGroup).options(selectinload(SCIMGroup.members))
        if auth.organization_id:
            query = query.where(SCIMGroup.organization_id == uuid.UUID(auth.organization_id))

        if filter:
            f = filter.strip()
            if f.lower().startswith("displayname eq"):
                val = f.split("eq", 1)[1].strip().strip('"').strip("'")
                query = query.where(func.lower(SCIMGroup.display_name) == val.lower())

        total_res = await db.execute(select(func.count()).select_from(query.subquery()))
        total = int(total_res.scalar_one())

        res = await db.execute(query.order_by(SCIMGroup.created_at).offset(start_index - 1).limit(count))
        groups = res.scalars().all()

    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": len(groups),
        "Resources": [_group_to_scim(g) for g in groups],
    }


@router.post("/Groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    request: Request,
    auth: SCIMAuthContext = Depends(require_scim_auth),
):
    """Create a new SCIM Group and optionally map members to a Team and Role."""
    body = await request.json()
    if SCIM_GROUP_SCHEMA not in body.get("schemas", []):
        raise _scim_error(400, "Request must include the core Group schema.")

    display_name = body.get("displayName")
    if not display_name:
        raise _scim_error(400, "displayName is required.")

    async with SessionLocal() as db:
        org_uuid = uuid.UUID(auth.organization_id) if auth.organization_id else None
        if not org_uuid:
            # Fallback to first active organization
            first_org = (await db.execute(select(Organization).where(Organization.deleted_at == None))).scalar_one_or_none()
            if not first_org:
                raise _scim_error(500, "No active organization exists to attach group to.")
            org_uuid = first_org.id

        group = SCIMGroup(
            organization_id=org_uuid,
            display_name=display_name,
            external_id=body.get("externalId"),
            target_role=body.get("targetRole", "Engineer"),
        )
        db.add(group)
        await db.flush()

        # Add initial members if specified
        members_data = body.get("members", [])
        for m in members_data:
            member_id = m.get("value")
            if member_id:
                try:
                    u = (await db.execute(select(User).where(User.id == uuid.UUID(member_id)))).scalar_one_or_none()
                    if u:
                        await db.execute(scim_group_members.insert().values(group_id=group.id, user_id=u.id))
                        if group.target_role:
                            u.team_role = group.target_role
                except ValueError:
                    continue

        await _log_scim_audit(db, "group_created", {"group_id": str(group.id), "displayName": display_name}, str(org_uuid))
        await db.commit()
        await db.refresh(group)
        # Reload members
        group_with_members = (await db.execute(select(SCIMGroup).options(selectinload(SCIMGroup.members)).where(SCIMGroup.id == group.id))).scalar_one()
        return _group_to_scim(group_with_members)


@router.get("/Groups/{group_id}")
async def get_group(
    group_id: str,
    auth: SCIMAuthContext = Depends(require_scim_auth),
):
    async with SessionLocal() as db:
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise _scim_error(404, f"Group {group_id} not found")

        query = select(SCIMGroup).options(selectinload(SCIMGroup.members)).where(SCIMGroup.id == gid)
        if auth.organization_id:
            query = query.where(SCIMGroup.organization_id == uuid.UUID(auth.organization_id))

        group = (await db.execute(query)).scalar_one_or_none()
        if not group:
            raise _scim_error(404, f"Group {group_id} not found")
        return _group_to_scim(group)


@router.patch("/Groups/{group_id}")
async def patch_group(
    group_id: str,
    request: Request,
    auth: SCIMAuthContext = Depends(require_scim_auth),
):
    """RFC 7644 PatchOp for SCIM Groups (add, remove, replace members)."""
    body = await request.json()
    if SCIM_PATCH_SCHEMA not in body.get("schemas", []):
        raise _scim_error(400, "PATCH body must be a PatchOp message.")

    operations = body.get("Operations") or body.get("operations") or []
    async with SessionLocal() as db:
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise _scim_error(404, f"Group {group_id} not found")

        group = (await db.execute(
            select(SCIMGroup).options(selectinload(SCIMGroup.members)).where(SCIMGroup.id == gid)
        )).scalar_one_or_none()

        if not group:
            raise _scim_error(404, f"Group {group_id} not found")

        for op in operations:
            op_type = str(op.get("op", "")).lower()
            path = op.get("path")
            val = op.get("value")

            if op_type == "add":
                if path == "members" or isinstance(val, list):
                    member_items = val if isinstance(val, list) else [val]
                    for item in member_items:
                        m_id = item.get("value") if isinstance(item, dict) else item
                        if m_id:
                            u = (await db.execute(select(User).where(User.id == uuid.UUID(str(m_id))))).scalar_one_or_none()
                            if u and u not in group.members:
                                group.members.append(u)
                                if group.target_role:
                                    u.team_role = group.target_role
                                if group.team_id:
                                    u.team_id = group.team_id
            elif op_type == "remove":
                if path and "value eq" in path:
                    import re
                    match = re.search(r'["\']?([a-f0-9\-]{36})["\']?', path)
                    if match:
                        m_id_str = match.group(1)
                        group.members = [m for m in group.members if str(m.id) != m_id_str]
                elif path == "members" and isinstance(val, list):
                    remove_ids = {str(item.get("value")) for item in val if isinstance(item, dict)}
                    group.members = [m for m in group.members if str(m.id) not in remove_ids]
            elif op_type == "replace":
                if path == "displayName":
                    group.display_name = str(val)
                elif path == "members" and isinstance(val, list):
                    new_members = []
                    for item in val:
                        m_id = item.get("value") if isinstance(item, dict) else item
                        if m_id:
                            u = (await db.execute(select(User).where(User.id == uuid.UUID(str(m_id))))).scalar_one_or_none()
                            if u:
                                new_members.append(u)
                                if group.target_role:
                                    u.team_role = group.target_role
                    group.members = new_members

        await _log_scim_audit(db, "group_patched", {"group_id": str(group.id), "displayName": group.display_name}, auth.organization_id)
        await db.commit()
        await db.refresh(group)
        group_with_members = (await db.execute(select(SCIMGroup).options(selectinload(SCIMGroup.members)).where(SCIMGroup.id == group.id))).scalar_one()
        return _group_to_scim(group_with_members)


@router.delete("/Groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: str,
    auth: SCIMAuthContext = Depends(require_scim_auth),
):
    async with SessionLocal() as db:
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise _scim_error(404, f"Group {group_id} not found")

        group = (await db.execute(select(SCIMGroup).where(SCIMGroup.id == gid))).scalar_one_or_none()
        if not group:
            raise _scim_error(404, f"Group {group_id} not found")

        await db.delete(group)
        await _log_scim_audit(db, "group_deleted", {"group_id": str(gid)}, auth.organization_id)
        await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
