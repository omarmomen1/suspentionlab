"""
backend/api/routes/lemon_squeezy_routes.py
Lemon Squeezy checkout, billing portal, and webhook handler.
"""
from __future__ import annotations

import os
import json
import hmac
import hashlib
import uuid as _uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.billing import LemonEvent
from suspensionlab.backend.security.jwt_utils import decode_access_token
from suspensionlab.shared.models import PlanTier

router = APIRouter(prefix="/billing", tags=["billing"])

LEMON_SQUEEZY_API_KEY      = os.getenv("LEMON_SQUEEZY_API_KEY", "")
LEMON_SQUEEZY_STORE_ID     = os.getenv("LEMON_SQUEEZY_STORE_ID", "")
LEMON_SQUEEZY_WEBHOOK_SECRET = os.getenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "")
LEMON_PRO_VARIANT_ID       = os.getenv("LEMON_PRO_VARIANT_ID", "")
LEMON_ENTERPRISE_VARIANT_ID= os.getenv("LEMON_ENTERPRISE_VARIANT_ID", "")
FRONTEND_URL               = os.getenv("FRONTEND_URL", "http://localhost:3000")

PLAN_VARIANT_MAP = {
    "pro":        LEMON_PRO_VARIANT_ID,
    "enterprise": LEMON_ENTERPRISE_VARIANT_ID,
}

# ─── Schemas ──────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str  # "pro" | "enterprise"

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_user_id_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = decode_access_token(auth.removeprefix("Bearer ").strip())
        if payload:
            return payload.get("sub")
    return None

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/checkout")
async def create_checkout_session(
    req: CheckoutRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_dependency),
):
    """Create a Lemon Squeezy Checkout Session and return the URL."""
    if not LEMON_SQUEEZY_API_KEY or not LEMON_SQUEEZY_STORE_ID:
        raise HTTPException(status_code=503, detail="Lemon Squeezy is not configured. Set API_KEY and STORE_ID.")

    user_id = _get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required to checkout.")

    variant_id = PLAN_VARIANT_MAP.get(req.plan.lower())
    if not variant_id:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {req.plan}")

    try:
        user_uuid = _uuid.UUID(str(user_id))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid user ID format.")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user: User | None = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": user.email,
                    "name": user.name or "",
                    "custom": {
                        "user_id": str(user_id),
                        "plan": req.plan
                    }
                },
                "product_options": {
                    "redirect_url": f"{FRONTEND_URL}/settings?success=1"
                }
            },
            "relationships": {
                "store": {
                    "data": {
                        "type": "stores",
                        "id": str(LEMON_SQUEEZY_STORE_ID)
                    }
                },
                "variant": {
                    "data": {
                        "type": "variants",
                        "id": str(variant_id)
                    }
                }
            }
        }
    }

    headers = {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {LEMON_SQUEEZY_API_KEY}"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post("https://api.lemonsqueezy.com/v1/checkouts", json=payload, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"Lemon Squeezy API error: {resp.text}")
        data = resp.json()
        checkout_url = data["data"]["attributes"]["url"]

    return {"checkout_url": checkout_url}


@router.post("/portal")
async def create_billing_portal(
    request: Request,
    db: AsyncSession = Depends(get_db_dependency),
):
    """Create a Lemon Squeezy Customer Portal session for managing subscriptions."""
    if not LEMON_SQUEEZY_API_KEY:
        raise HTTPException(status_code=503, detail="Lemon Squeezy is not configured.")

    user_id = _get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        user_uuid = _uuid.UUID(str(user_id))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid user token.")
        
    result = await db.execute(select(User).where(User.id == user_uuid))
    user: User | None = result.scalar_one_or_none()
    if not user or not user.lemon_subscription_id:
        raise HTTPException(status_code=404, detail="No billing account found. Subscribe first.")

    # Fetch the subscription from Lemon Squeezy to get the customer portal update URL
    headers = {
        "Accept": "application/vnd.api+json",
        "Authorization": f"Bearer {LEMON_SQUEEZY_API_KEY}"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.lemonsqueezy.com/v1/subscriptions/{user.lemon_subscription_id}", headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=500, detail="Could not fetch customer portal.")
        data = resp.json()
        portal_url = data["data"]["attributes"]["urls"]["customer_portal"]

    return {"portal_url": portal_url}


@router.post("/webhooks/lemonsqueezy")
async def lemon_squeezy_webhook(request: Request, db: AsyncSession = Depends(get_db_dependency)):
    """Handle Lemon Squeezy webhooks — update user plan on subscription events."""
    if not LEMON_SQUEEZY_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured.")

    payload = await request.body()
    signature = request.headers.get("X-Signature", "")

    # Verify HMAC-SHA256 signature
    digest = hmac.new(
        LEMON_SQUEEZY_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(digest, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload_dict = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_name = payload_dict.get("meta", {}).get("event_name")
    event_id = payload_dict.get("meta", {}).get("webhook_id", str(_uuid.uuid4()))
    custom_data = payload_dict.get("meta", {}).get("custom_data", {})
    
    from sqlalchemy.exc import IntegrityError
    try:
        new_event = LemonEvent(event_id=event_id, payload=payload_dict)
        db.add(new_event)
        
        data_attr = payload_dict.get("data", {}).get("attributes", {})
        customer_id = str(data_attr.get("customer_id"))
        subscription_id = str(payload_dict.get("data", {}).get("id"))
        variant_id = str(data_attr.get("variant_id"))
        
        PLAN_FROM_VARIANT: dict[str, str] = {
            LEMON_PRO_VARIANT_ID:        PlanTier.PRO,
            LEMON_ENTERPRISE_VARIANT_ID: PlanTier.ENTERPRISE,
        }

        user_id = custom_data.get("user_id")
        
        if event_name in ("subscription_created", "subscription_updated"):
            new_plan = PLAN_FROM_VARIANT.get(variant_id, PlanTier.PRO)
            status = data_attr.get("status", "")

            # Look up by custom user_id or lemon_customer_id
            user = None
            if user_id:
                try:
                    user_uuid = _uuid.UUID(str(user_id))
                    user_res = await db.execute(select(User).where(User.id == user_uuid))
                    user = user_res.scalars().first()
                except ValueError:
                    pass
            
            if not user and customer_id:
                user_res = await db.execute(select(User).where(User.lemon_customer_id == customer_id))
                user = user_res.scalars().first()

            if user:
                user.plan = new_plan if status in ("active", "on_trial", "past_due") else PlanTier.FREE
                user.lemon_subscription_id = subscription_id
                user.lemon_customer_id = customer_id

        elif event_name == "subscription_expired":
            user_res = await db.execute(select(User).where(User.lemon_subscription_id == subscription_id))
            user = user_res.scalars().first()
            if user:
                user.plan = PlanTier.FREE
                
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"received": True, "message": "Duplicate event ignored"}

    return {"received": True}
