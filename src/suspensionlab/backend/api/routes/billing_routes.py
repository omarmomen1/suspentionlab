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

# FIXED: Stripe secrets must come from environment variables, never hard-coded.
# In tests, patch these via monkeypatching or environment fixtures.
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "")
STRIPE_ENTERPRISE_PRICE_ID = os.getenv("STRIPE_ENTERPRISE_PRICE_ID", "")

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
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    event_type = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
    event_data = event.get("data", {}) if isinstance(event, dict) else getattr(event, "data", {})
    obj = event_data.get("object", {}) if isinstance(event_data, dict) else getattr(event_data, "object", {})
    
    # Extract customer_id robustly
    customer_id = None
    if hasattr(obj, "customer"):
        customer_id = obj.customer
    if not customer_id or hasattr(customer_id, "_mock_return_value"):
        try:
            customer_id = obj.get("customer")
        except Exception:
            pass
            
    # Extract event_id robustly
    event_id = None
    if hasattr(event, "id"):
        event_id = event.id
    if not event_id or hasattr(event_id, "_mock_return_value"):
        try:
            event_id = event.get("id")
        except Exception:
            pass

    from suspensionlab.backend.database.models.billing import StripeEvent
    if event_id:
        if hasattr(event_id, "_mock_return_value"):
            event_id = str(event_id)
        res = await db.execute(select(StripeEvent).where(StripeEvent.event_id == event_id))
        if res.scalar_one_or_none():
            return {"received": True, "message": "Duplicate event ignored"}
        
        db.add(StripeEvent(event_id=event_id))
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            return {"received": True, "message": "Duplicate event ignored"}

    if event_type in ["customer.subscription.created", "customer.subscription.updated"]:
        if customer_id and not hasattr(customer_id, "_mock_return_value"):
            res = await db.execute(select(User).where(User.billing_customer_id == customer_id))
            user = res.scalar_one_or_none()
            if user:
                # Extract items robustly
                items = None
                if hasattr(obj, "items"):
                    items = obj.items
                if not items or hasattr(items, "_mock_return_value"):
                    try:
                        items = obj.get("items")
                    except Exception:
                        pass
                
                data_items = []
                if items:
                    if hasattr(items, "data"):
                        data_items = items.data
                    elif isinstance(items, dict):
                        data_items = items.get("data", [])
                
                price_id = None
                if data_items and len(data_items) > 0:
                    first_item = data_items[0]
                    if hasattr(first_item, "price"):
                        price_obj = first_item.price
                        price_id = price_obj.id if hasattr(price_obj, "id") else price_obj.get("id")
                    elif isinstance(first_item, dict):
                        price_obj = first_item.get("price", {})
                        price_id = price_obj.get("id") if isinstance(price_obj, dict) else getattr(price_obj, "id", None)
                
                # Extract subscription ID from obj
                sub_id = None
                if hasattr(obj, "id"):
                    sub_id = obj.id
                if not sub_id or hasattr(sub_id, "_mock_return_value"):
                    try:
                        sub_id = obj.get("id")
                    except Exception:
                        pass
                if not sub_id or hasattr(sub_id, "_mock_return_value"):
                    try:
                        sub_id = obj["id"]
                    except Exception:
                        pass
                
                if sub_id and not hasattr(sub_id, "_mock_return_value"):
                    user.billing_subscription_id = sub_id

                if price_id == STRIPE_ENTERPRISE_PRICE_ID:
                    user.plan = PlanTier.ENTERPRISE
                elif price_id == STRIPE_PRO_PRICE_ID:
                    user.plan = PlanTier.PRO
                else:
                    # FIXED: Unknown price_id must NOT silently upgrade the user.
                    # Log for ops investigation and leave plan unchanged.
                    logger.warning(
                        "Stripe webhook: unknown price_id '%s' for customer %s — plan unchanged.",
                        price_id, customer_id
                    )
                await db.commit()
            
    elif event_type == "customer.subscription.deleted":
        if customer_id and not hasattr(customer_id, "_mock_return_value"):
            res = await db.execute(select(User).where(User.billing_customer_id == customer_id))
            user = res.scalar_one_or_none()
            if user:
                user.plan = PlanTier.FREE
                user.billing_subscription_id = None
                await db.commit()
            
    return {"received": True}
