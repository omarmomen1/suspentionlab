import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from suspensionlab.backend.security.auth import verify_api_key
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.user import User
from suspensionlab.shared.models import PlanTier
import stripe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing-compatibility"])

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID")
STRIPE_ENTERPRISE_PRICE_ID = os.getenv("STRIPE_ENTERPRISE_PRICE_ID")

def _get_user_id_from_request(request: Request) -> str:
    """Extract authenticated user ID from JWT state (set by auth middleware)."""
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "user_id"):
        return str(user.user_id)
    # Fallback: read from request state set by verify_api_key
    user_id = getattr(request.state, "user_id", None)
    return str(user_id) if user_id else ""

class CheckoutRequest(BaseModel):
    plan: str

@router.post("/checkout")
async def checkout(
    req: CheckoutRequest,
    user: dict = Depends(verify_api_key),
):
    if req.plan not in ["pro", "enterprise"]:
        raise HTTPException(status_code=400, detail="Unknown plan")
    # FIXED: Use the configured price ID, never a hardcoded placeholder.
    price_id = STRIPE_ENTERPRISE_PRICE_ID if req.plan == "enterprise" else STRIPE_PRO_PRICE_ID
    if not price_id:
        logger.error("Stripe price ID not configured for plan: %s", req.plan)
        raise HTTPException(status_code=503, detail="Payment system not configured. Contact support.")
    import asyncio
    try:
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=os.getenv("STRIPE_SUCCESS_URL", "http://localhost:3000/success"),
            cancel_url=os.getenv("STRIPE_CANCEL_URL", "http://localhost:3000/pricing")
        )
        return {"checkout_url": session.url}
    except stripe.error.StripeError as e:
        logger.error("Stripe checkout session creation failed: %s", e)
        raise HTTPException(status_code=502, detail="Payment provider error. Please try again later.")

@router.post("/portal")
async def portal():
    raise HTTPException(status_code=404, detail="No billing account found. Subscribe first.")

@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db_dependency)):
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        webhook_secret = STRIPE_WEBHOOK_SECRET
    if not webhook_secret or not webhook_secret.strip():
        logger.error("STRIPE_WEBHOOK_SECRET is not configured.")
        raise HTTPException(status_code=500, detail="Stripe webhook secret is not configured.")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header.")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # Extract event fields cleanly
    if isinstance(event, dict):
        event_id = event.get("id")
        event_type = event.get("type")
        event_data = event.get("data", {})
    else:
        event_id = getattr(event, "id", None) or (event.get("id") if hasattr(event, "get") else None)
        event_type = getattr(event, "type", None) or (event.get("type") if hasattr(event, "get") else None)
        event_data = getattr(event, "data", {}) or (event.get("data") if hasattr(event, "get") else {})

    if isinstance(event_data, dict):
        obj = event_data.get("object", {})
    else:
        obj = getattr(event_data, "object", {}) or (event_data.get("object") if hasattr(event_data, "get") else {})

    # Extract customer_id and sub_id
    if isinstance(obj, dict):
        customer_id = obj.get("customer")
        sub_id = obj.get("id")
        items_obj = obj.get("items")
    else:
        customer_id = getattr(obj, "customer", None) or (obj.get("customer") if hasattr(obj, "get") else None)
        sub_id = getattr(obj, "id", None) or (obj.get("id") if hasattr(obj, "get") else None)
        items_obj = getattr(obj, "items", None) or (obj.get("items") if hasattr(obj, "get") else None)

    from suspensionlab.backend.database.models.billing import StripeEvent
    if event_id:
        res = await db.execute(select(StripeEvent).where(StripeEvent.event_id == str(event_id)))
        if res.scalar_one_or_none():
            return {"received": True, "message": "Duplicate event ignored"}
        db.add(StripeEvent(event_id=str(event_id)))

    if event_type in ["customer.subscription.created", "customer.subscription.updated"]:
        if customer_id:
            res = await db.execute(select(User).where(User.billing_customer_id == str(customer_id)))
            user = res.scalar_one_or_none()
            if user:
                # Extract items list
                data_items = []
                if isinstance(items_obj, dict):
                    data_items = items_obj.get("data", [])
                elif hasattr(items_obj, "data"):
                    data_items = items_obj.data
                elif isinstance(items_obj, list):
                    data_items = items_obj

                price_id = None
                if data_items and len(data_items) > 0:
                    first_item = data_items[0]
                    if isinstance(first_item, dict):
                        price_val = first_item.get("price")
                        price_id = price_val.get("id") if isinstance(price_val, dict) else getattr(price_val, "id", None)
                    else:
                        price_val = getattr(first_item, "price", None) or (first_item.get("price") if hasattr(first_item, "get") else None)
                        price_id = getattr(price_val, "id", None) if not isinstance(price_val, dict) else price_val.get("id")

                if sub_id:
                    user.billing_subscription_id = str(sub_id)

                if price_id == STRIPE_ENTERPRISE_PRICE_ID:
                    user.plan = PlanTier.ENTERPRISE
                elif price_id == STRIPE_PRO_PRICE_ID:
                    user.plan = PlanTier.PRO
                else:
                    logger.warning(
                        "Stripe webhook: unknown price_id '%s' for customer %s — plan unchanged.",
                        price_id, customer_id
                    )
                await db.commit()

    elif event_type == "customer.subscription.deleted":
        if customer_id:
            res = await db.execute(select(User).where(User.billing_customer_id == str(customer_id)))
            user = res.scalar_one_or_none()
            if user:
                user.plan = PlanTier.FREE
                user.billing_subscription_id = None
                await db.commit()

    try:
        await db.commit()
    except Exception:
        await db.rollback()
            
    return {"received": True}
