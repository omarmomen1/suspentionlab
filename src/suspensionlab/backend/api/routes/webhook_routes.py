"""
backend/api/routes/webhook_routes.py
=====================================
Webhook endpoint management (Tier C2).

GET    /api/v1/webhooks            → list endpoints (secrets masked)
POST   /api/v1/webhooks            → create endpoint (secret returned ONCE)
DELETE /api/v1/webhooks/{id}       → deactivate + delete
POST   /api/v1/webhooks/{id}/test  → send a signed ping event
"""
from __future__ import annotations

import secrets as _secrets
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.webhook import WebhookEndpoint
from suspensionlab.backend.services.webhooks import dispatch_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _parse_endpoint_id(endpoint_id: str) -> _uuid.UUID:
    """Pass B: malformed ids are a 400, never an unhandled 500."""
    try:
        return _uuid.UUID(endpoint_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Malformed webhook endpoint id.")

VALID_EVENTS = ("job.completed", "job.failed")
MAX_ENDPOINTS = 10


def _serialize(ep: WebhookEndpoint) -> dict:
    return {
        "id": str(ep.id),
        "url": ep.url,
        "events": [e for e in (ep.events or "").split(",") if e],
        "description": ep.description,
        "is_active": ep.is_active,
        "created_at": ep.created_at.isoformat() if ep.created_at else None,
        "secret_masked": f"whsec_…{ep.secret[-4:]}" if ep.secret else None,
    }


class CreateWebhookRequest(BaseModel):
    url: HttpUrl
    events: list[str] = Field(default=["job.completed", "job.failed"])
    description: str | None = Field(None, max_length=255)


@router.get("")
async def list_webhooks(user: UserContext = Depends(verify_api_key), db: AsyncSession = Depends(get_db_dependency)):
    result = await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.user_id == _uuid.UUID(str(user.user_id)))
    )
    return {"endpoints": [_serialize(ep) for ep in result.scalars().all()]}


@router.post("", status_code=201)
async def create_webhook(
    req: CreateWebhookRequest,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    events = [e for e in req.events if e in VALID_EVENTS]
    if not events:
        raise HTTPException(status_code=400, detail=f"events must include at least one of {VALID_EVENTS}.")

    from suspensionlab.backend.services.webhooks import validate_webhook_url
    try:
        validate_webhook_url(str(req.url))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid webhook URL (SSRF protection): {err}")

    count_result = await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.user_id == _uuid.UUID(str(user.user_id)))
    )

    if len(count_result.scalars().all()) >= MAX_ENDPOINTS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_ENDPOINTS} webhook endpoints per account.")

    secret = "whsec_" + _secrets.token_hex(24)
    ep = WebhookEndpoint(
        user_id=_uuid.UUID(str(user.user_id)),
        url=str(req.url),
        secret=secret,
        events=",".join(events),
        description=req.description,
    )
    db.add(ep)
    await db.commit()
    await db.refresh(ep)

    out = _serialize(ep)
    # The full secret is shown exactly once — at creation.
    out["secret"] = secret
    return out


@router.delete("/{endpoint_id}", status_code=204)
async def delete_webhook(
    endpoint_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == _parse_endpoint_id(endpoint_id),
            WebhookEndpoint.user_id == _uuid.UUID(user.user_id),
        )
    )
    ep = result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found.")
    await db.delete(ep)
    await db.commit()


@router.post("/{endpoint_id}/test")
async def test_webhook(
    endpoint_id: str,
    user: UserContext = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Send a signed webhook.ping event so customers can verify their receiver."""
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == _parse_endpoint_id(endpoint_id),
            WebhookEndpoint.user_id == _uuid.UUID(user.user_id),
        )
    )
    ep = result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found.")

    delivered = await dispatch_event(db, user.user_id, "webhook.ping", {
        "endpoint_id": str(ep.id),
        "message": "SuspensionLab webhook test — if you can read this, signature verification works.",
    })
    return {"delivered": bool(delivered), "event": "webhook.ping"}
