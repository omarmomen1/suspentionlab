from __future__ import annotations

import os
import logging
from typing import Any
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

from suspensionlab.backend.config import settings


def _stripe_webhook_secret() -> str | None:
    """Lazy read (Pass B): never bind secrets/price IDs at import time."""
    return os.getenv("STRIPE_WEBHOOK_SECRET") or settings.stripe_webhook_secret


def _stripe_pro_price_id() -> str | None:
    return os.getenv("STRIPE_PRO_PRICE_ID") or settings.stripe_pro_price_id


def _stripe_enterprise_price_id() -> str | None:
    return os.getenv("STRIPE_ENTERPRISE_PRICE_ID") or settings.stripe_enterprise_price_id

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
    user: Any = Depends(verify_api_key),
):
    if req.plan not in ["pro", "enterprise"]:
        raise HTTPException(status_code=400, detail="Unknown plan")

    user_id = getattr(user, "user_id", None) or (user.get("user_id") if isinstance(user, dict) else None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    price_id = _stripe_enterprise_price_id() if req.plan == "enterprise" else _stripe_pro_price_id()
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
            client_reference_id=str(user_id),
            metadata={"user_id": str(user_id)},
            subscription_data={"metadata": {"user_id": str(user_id)}},
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
    webhook_secret = _stripe_webhook_secret()
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
        # Pass B: never leak the verifier's error text to the caller.
        logger.warning("Stripe webhook signature verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    def _get(container, key, default=None):
        if isinstance(container, dict):
            return container.get(key, default)
        val = getattr(container, key, None)
        if val is None and hasattr(container, "get"):
            try:
                val = container.get(key, default)
            except Exception:
                val = default
        return val if val is not None else default

    event_id = _get(event, "id")
    event_type = _get(event, "type")
    event_created = _get(event, "created")  # epoch seconds, for stale-event ordering
    try:
        event_created = int(event_created) if event_created is not None else None
    except (TypeError, ValueError):
        event_created = None
    event_data = _get(event, "data", {}) or {}
    obj = _get(event_data, "object", {}) or {}

    customer_id = _get(obj, "customer")
    sub_id = _get(obj, "id")
    items_obj = _get(obj, "items")

    meta = _get(obj, "metadata")
    meta_user_id = _get(meta, "user_id") if meta else None
    client_ref_id = _get(obj, "client_reference_id")
    target_user_id = client_ref_id or meta_user_id

    from suspensionlab.backend.database.models.billing import StripeEvent
    if event_id:
        res = await db.execute(select(StripeEvent).where(StripeEvent.event_id == str(event_id)))
        if res.scalar_one_or_none():
            return {"received": True, "message": "Duplicate event ignored"}

    async def _find_user():
        found = None
        if customer_id:
            res = await db.execute(select(User).where(User.billing_customer_id == str(customer_id)))
            found = res.scalar_one_or_none()
        if not found and target_user_id:
            import uuid
            try:
                uid = uuid.UUID(str(target_user_id))
                res = await db.execute(select(User).where(User.id == uid))
                found = res.scalar_one_or_none()
            except (ValueError, TypeError):
                res = await db.execute(select(User).where(User.id == str(target_user_id)))
                found = res.scalar_one_or_none()
        return found

    def _is_stale(user) -> bool:
        """Ordering guard (Pass B): a stale event must never override a newer one."""
        last = getattr(user, "billing_last_event_created", None)
        return bool(event_created is not None and last is not None and event_created < last)

    def _mark_applied(user) -> None:
        if event_created is not None:
            last = getattr(user, "billing_last_event_created", None) or 0
            if event_created > last:
                user.billing_last_event_created = event_created

    GRANT_EVENTS = {
        "customer.subscription.created",
        "customer.subscription.updated",
        "checkout.session.completed",
    }

    if event_type in GRANT_EVENTS:
        user = await _find_user()
        if not user:
            # Pass B: do NOT mark the event processed — roll back and 500 so
            # Stripe retries instead of silently losing a paid upgrade.
            await db.rollback()
            logger.error(
                "Stripe webhook %s: no user for customer=%s target=%s — returning 500 for retry.",
                event_id, customer_id, target_user_id,
            )
            raise HTTPException(status_code=500, detail="Billing event could not be applied yet; please retry.")

        if _is_stale(user):
            logger.warning(
                "Stripe webhook %s: stale %s (created=%s < last=%s) for user %s — skipped.",
                event_id, event_type, event_created, user.billing_last_event_created, user.id,
            )
        else:
            obj_status = str(_get(obj, "status", "") or "")
            payment_status = str(_get(obj, "payment_status", "") or "")
            sub_ref = _get(obj, "subscription") if event_type == "checkout.session.completed" else sub_id

            if event_type == "checkout.session.completed":
                is_entitled = payment_status.lower() in ("paid", "no_payment_required")
            else:
                is_entitled = obj_status.lower() in ("active", "trialing")

            # Persist billing_customer_id on first subscription event
            if customer_id and not user.billing_customer_id:
                user.billing_customer_id = str(customer_id)

            if not is_entitled:
                logger.warning(
                    "Stripe webhook: skipping plan grant for user %s due to status='%s' payment_status='%s'",
                    user.id, obj_status, payment_status,
                )
            else:
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
                    price_val = _get(first_item, "price")
                    price_id = _get(price_val, "id") if price_val else None

                if sub_ref:
                    user.billing_subscription_id = str(sub_ref)

                if price_id == _stripe_enterprise_price_id():
                    user.plan = PlanTier.ENTERPRISE
                    user.plan_source = "stripe"
                elif price_id == _stripe_pro_price_id():
                    user.plan = PlanTier.PRO
                    user.plan_source = "stripe"
                else:
                    logger.warning(
                        "Stripe webhook: unknown price_id '%s' for customer %s — plan unchanged.",
                        price_id, customer_id
                    )
            _mark_applied(user)

    elif event_type == "customer.subscription.deleted":
        user = await _find_user()
        if user:
            if _is_stale(user):
                logger.warning(
                    "Stripe webhook %s: stale subscription.deleted for user %s — skipped.",
                    event_id, user.id,
                )
            else:
                # Pass B: only downgrade Stripe-sourced entitlements. A Gumroad
                # or SLPRO license entitlement must survive a Stripe cancel.
                source = getattr(user, "plan_source", None)
                stripe_sourced = source == "stripe" or (source is None and not user.gumroad_license_key)
                if stripe_sourced:
                    user.plan = PlanTier.FREE
                    user.billing_subscription_id = None
                    user.plan_source = None
                else:
                    logger.warning(
                        "Stripe webhook: subscription.deleted for user %s with plan_source='%s' — plan untouched.",
                        user.id, source,
                    )
                _mark_applied(user)

    elif event_type == "invoice.payment_failed":
        user = await _find_user()
        logger.warning(
            "Stripe invoice.payment_failed for customer=%s user=%s invoice=%s — dunning left to Stripe; plan unchanged.",
            customer_id, getattr(user, "id", None), sub_id,
        )
        if user:
            _mark_applied(user)

    elif event_type == "charge.refunded":
        user = await _find_user()
        if user:
            source = getattr(user, "plan_source", None)
            stripe_sourced = source == "stripe" or (source is None and not user.gumroad_license_key)
            plan_val = user.plan.value if isinstance(user.plan, PlanTier) else str(user.plan)
            if stripe_sourced and plan_val in (PlanTier.PRO.value, PlanTier.ENTERPRISE.value):
                user.plan = PlanTier.FREE
                user.billing_subscription_id = None
                user.plan_source = None
                logger.warning("Stripe charge.refunded: downgraded user %s to FREE.", user.id)
            _mark_applied(user)
        else:
            logger.warning("Stripe charge.refunded for unknown customer=%s — recorded only.", customer_id)

    elif event_type == "charge.dispute.created":
        user = await _find_user()
        logger.warning(
            "Stripe charge.dispute.created for customer=%s user=%s — recorded; awaiting dispute outcome before plan action.",
            customer_id, getattr(user, "id", None),
        )
        if user:
            _mark_applied(user)

    # Record the event in the SAME transaction as the plan mutation (Pass B):
    # if anything above failed we already rolled back and returned 500.
    if event_id:
        db.add(StripeEvent(
            event_id=str(event_id),
            payload={
                "type": event_type,
                "created": event_created,
                "customer": str(customer_id) if customer_id else None,
            },
        ))

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("Stripe webhook DB commit failed: %s", exc)
        raise HTTPException(status_code=500, detail="Webhook persistence failed; please retry.")

    return {"received": True}
