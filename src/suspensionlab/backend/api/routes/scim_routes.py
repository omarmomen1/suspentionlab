"""
backend/api/routes/scim_routes.py
==================================
SCIM 2.0 user provisioning — RFC 7643 (core schema) / RFC 7644 (protocol).

Backed by the real `users` table so IdP-driven lifecycle changes
(Okta, Entra ID, JumpCloud, OneLogin…) take immediate effect:

    GET    /scim/v2/ServiceProviderConfig   → capabilities document
    GET    /scim/v2/Users                   → list/filter/paginate users
    POST   /scim/v2/Users                   → provision (JIT create)
    GET    /scim/v2/Users/{id}              → retrieve by id or externalId
    PUT    /scim/v2/Users/{id}              → full replace of mutable attrs
    PATCH  /scim/v2/Users/{id}              → partial update (active, name, …)
    DELETE /scim/v2/Users/{id}              → deactivate (soft delete)

Security:
    * Every request must present `Authorization: Bearer <SCIM_BEARER_TOKEN>`.
    * 503 when SCIM is disabled; 401 on bad/missing token — never fake data.
    * Deactivation maps to the existing soft-delete (`deleted_at`) so SSO/JWT
      sessions for de-provisioned staff stop working immediately.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, func

from suspensionlab.backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scim/v2", tags=["SCIM"])

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
SCIM_CONTENT_TYPE = "application/scim+json"


# ── Auth ──────────────────────────────────────────────────────────────────────

async def require_scim_auth(
    authorization: str | None = Header(default=None),
) -> None:
    if not settings.scim_enabled:
        raise HTTPException(
            status_code=503,
            detail="SCIM provisioning is not enabled on this deployment. Set SCIM_ENABLED=true "
                   "and configure SCIM_BEARER_TOKEN to activate it.",
        )
    token = settings.scim_bearer_token
    if not token:
        raise HTTPException(status_code=503, detail="SCIM is enabled but SCIM_BEARER_TOKEN is not configured.")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    presented = authorization.split(" ", 1)[1].strip()
    # Constant-time comparison to avoid timing side channels.
    if not secrets.compare_digest(presented, token):
        raise HTTPException(status_code=401, detail="Invalid bearer token.")


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


def _user_to_scim(user) -> dict[str, Any]:
    """Map a User ORM row to an RFC 7643 User resource."""
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
    return {k: v for k, v in resource.items() if v is not None}


async def _get_user_or_404(db, user_id: str):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise _scim_error(404, f"User {user_id} not found")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None:
        raise _scim_error(404, f"User {user_id} not found")
    return user


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


# Imported late so the module can be loaded before models register.
from suspensionlab.backend.database.core import SessionLocal  # noqa: E402
from suspensionlab.backend.database.models.user import User   # noqa: E402
from suspensionlab.backend.security.jwt_utils import hash_password  # noqa: E402


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/ServiceProviderConfig")
async def service_provider_config(_: None = Depends(require_scim_auth)):
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
                "description": "Authentication via SCIM_BEARER_TOKEN.",
                "primary": True,
            }
        ],
    }


@router.get("/Users")
async def list_users(
    _: None = Depends(require_scim_auth),
    filter: Optional[str] = Query(None),
    start_index: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=200),
):
    """List users with optional `filter=userName eq "..."` (RFC 7644 §3.4.2.2)."""
    async with SessionLocal() as db:
        query = select(User).where(User.deleted_at.is_(None))

        if filter:
            f = filter.strip()
            # Support the single most common IdP filter: userName eq "x@y.z"
            lowered = f.lower()
            if lowered.startswith("username eq"):
                value = f.split("eq", 1)[1].strip().strip('"').strip("'").lower()
                query = query.where(func.lower(User.email) == value)
            elif lowered.startswith("externalid eq"):
                value = f.split("eq", 1)[1].strip().strip('"').strip("'")
                query = query.where(User.external_id == value)
            else:
                raise _scim_error(400, f"Unsupported filter: '{filter}'. Supported: userName eq, externalId eq.")

        total_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = int(total_result.scalar_one())

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


@router.post("/Users", status_code=201)
async def create_user(request: Request, _: None = Depends(require_scim_auth)):
    """Provision a user from the IdP (RFC 7644 §3.3)."""
    body = await request.json()
    if SCIM_USER_SCHEMA not in body.get("schemas", []):
        raise _scim_error(400, "Request must include the core User schema.")

    user_name = body.get("userName")
    if not user_name:
        raise _scim_error(400, "userName is required.")
    email = user_name.lower()

    external_id = body.get("externalId")

    async with SessionLocal() as db:
        existing = (
            await db.execute(select(User).where(func.lower(User.email) == email))
        ).scalar_one_or_none()
        if existing is not None and existing.deleted_at is None:
            raise _scim_error(409, f"User '{email}' already exists.")

        if existing is not None:
            # Reactivate a previously soft-deleted account.
            existing.deleted_at = None
            existing.external_id = external_id or existing.external_id
            existing.name = _extract_name(body.get("name")) or existing.name
            await db.commit()
            await db.refresh(existing)
            return _user_to_scim(existing)

        user = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),  # unusable; auth via IdP
            name=_extract_name(body.get("name")),
            plan="PRO",
            external_id=external_id,
            auth_provider="oidc",
            onboarding_complete=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("SCIM provisioned user %s (externalId=%s)", email, external_id)
        return _user_to_scim(user)


@router.get("/Users/{user_id}")
async def get_user(user_id: str, _: None = Depends(require_scim_auth)):
    async with SessionLocal() as db:
        user = await _get_user_or_404(db, user_id)
        return _user_to_scim(user)


@router.put("/Users/{user_id}")
async def replace_user(user_id: str, request: Request, _: None = Depends(require_scim_auth)):
    """Full replace of mutable attributes (RFC 7644 §3.5.1)."""
    body = await request.json()
    async with SessionLocal() as db:
        user = await _get_user_or_404(db, user_id)
        new_email = (body.get("userName") or user.email).lower()
        user.email = new_email
        user.name = _extract_name(body.get("name")) or user.name
        if body.get("externalId"):
            user.external_id = body["externalId"]
        active = body.get("active", True)
        user.deleted_at = None if active else (user.deleted_at or datetime.now(timezone.utc))
        await db.commit()
        await db.refresh(user)
        return _user_to_scim(user)


@router.patch("/Users/{user_id}")
async def patch_user(user_id: str, request: Request, _: None = Depends(require_scim_auth)):
    """Partial update via PatchOp (RFC 7644 §3.5.2). Supports 'replace' operations."""
    body = await request.json()
    if SCIM_PATCH_SCHEMA not in body.get("schemas", []):
        raise _scim_error(400, "PATCH body must be a PatchOp message.")

    operations = body.get("Operations") or body.get("operations") or []
    async with SessionLocal() as db:
        user = await _get_user_or_404(db, user_id)

        for op in operations:
            op_type = str(op.get("op", "")).lower()
            path = op.get("path")
            value = op.get("value")

            if op_type == "replace":
                if path == "active":
                    if bool(value):
                        user.deleted_at = None
                    else:
                        user.deleted_at = user.deleted_at or datetime.now(timezone.utc)
                elif path in ("name", "name.formatted", "displayName"):
                    user.name = _extract_name(value if isinstance(value, dict) else {"formatted": value}) or user.name
                elif path == "userName":
                    user.email = str(value).lower()
                elif path == "externalId":
                    user.external_id = str(value)
                elif path is None and isinstance(value, dict):
                    # Okta-style whole-object replace
                    if "active" in value:
                        user.deleted_at = None if value["active"] else (
                            user.deleted_at or datetime.now(timezone.utc))
                    if "userName" in value:
                        user.email = str(value["userName"]).lower()
                    if "name" in value:
                        user.name = _extract_name(value["name"]) or user.name
                else:
                    raise _scim_error(400, f"Unsupported patch path: '{path}'.")
            elif op_type in ("add", "remove"):
                raise _scim_error(400, f"Unsupported patch op '{op_type}'. Supported: replace.")
            else:
                raise _scim_error(400, f"Unknown patch op '{op_type}'.")

        await db.commit()
        await db.refresh(user)
        logger.info("SCIM patched user %s", user.email)
        return _user_to_scim(user)


@router.delete("/Users/{user_id}", status_code=204)
async def delete_user(user_id: str, _: None = Depends(require_scim_auth)):
    """Deactivate (soft delete) a user — RFC 7644 recommends deactivation over hard delete."""
    async with SessionLocal() as db:
        user = await _get_user_or_404(db, user_id)
        if user.deleted_at is None:
            user.deleted_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("SCIM deactivated user %s", user.email)
    return Response(status_code=204)
