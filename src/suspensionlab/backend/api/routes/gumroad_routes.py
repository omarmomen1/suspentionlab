"""
Gumroad & Self-Issued License Verification Route
================================================
Handles license key verification for:
  1. Self-issued HMAC-SHA256 signed tokens (`SLPRO-...`)
  2. External Gumroad purchases (`/v2/licenses/verify`)
"""
from __future__ import annotations

import logging
import uuid as _uuid

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import httpx
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.trial import Trial
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.auth import verify_api_key, PlanTier
from suspensionlab.backend.security.license_keys import (
    LicenseConfigError,
    LicenseExpiredError,
    LicenseInvalidError,
    verify_license_key,
)
from suspensionlab.backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing-gumroad"])


class LicenseVerificationRequest(BaseModel):
    license_key: str


class LicenseVerificationResponse(BaseModel):
    success: bool
    plan: PlanTier
    message: str


async def _apply_license_upgrade(
    db: AsyncSession,
    user_data: dict | object,
    target_plan: PlanTier,
    license_key: str,
) -> LicenseVerificationResponse:
    """Persist plan upgrade, license key binding, and convert any active/expired trial."""
    raw_uid = user_data.get("user_id") if isinstance(user_data, dict) else getattr(user_data, "user_id", None)
    user_id = _uuid.UUID(str(raw_uid))
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user_model = result.scalar_one_or_none()

    if not user_model:
        raise HTTPException(status_code=404, detail="User not found.")

    user_model.plan = target_plan.value
    user_model.gumroad_license_key = license_key
    # Pass B: record entitlement provenance so a later Stripe subscription.deleted
    # can never downgrade a Gumroad/SLPRO entitlement.
    user_model.plan_source = "gumroad" if not license_key.startswith("SLPRO-") else "license_key"

    if user_model.organization_id:
        org_res = await db.execute(
            select(Organization).where(Organization.id == user_model.organization_id)
        )
        org = org_res.scalar_one_or_none()
        if org and org.plan in (PlanTier.TRIAL.value, PlanTier.FREE.value, PlanTier.PRO.value):
            if org.plan != PlanTier.ENTERPRISE.value or target_plan == PlanTier.ENTERPRISE:
                org.plan = target_plan.value
                org.subscription_status = "active"

    trial_cond = Trial.user_id == user_model.id
    if user_model.organization_id:
        trial_cond = or_(trial_cond, Trial.organization_id == user_model.organization_id)
    trials_res = await db.execute(
        select(Trial).where(trial_cond, Trial.deleted_at.is_(None))
    )
    for trial in trials_res.scalars().all():
        trial.status = "CONVERTED"

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="License key already redeemed.")

    return LicenseVerificationResponse(
        success=True,
        plan=target_plan,
        message=f"License verified successfully! Your account has been upgraded to {target_plan.value}.",
    )


def _build_gumroad_verify_candidates(license_key: str) -> list[tuple[PlanTier, dict[str, str]]]:
    """Build ordered (target_plan, payload) candidates for Gumroad license verification."""
    pro_id = (settings.gumroad_product_id or "").strip()
    team_id = (settings.gumroad_team_product_id or "").strip()
    permalink = (settings.gumroad_product_permalink or "").strip()

    candidates: list[tuple[PlanTier, dict[str, str]]] = []
    if pro_id:
        candidates.append((PlanTier.PRO, {"product_id": pro_id, "license_key": license_key, "increment_uses_count": "false"}))
    elif permalink:
        candidates.append((PlanTier.PRO, {"product_permalink": permalink, "license_key": license_key, "increment_uses_count": "false"}))

    if team_id and team_id != pro_id:
        candidates.append((PlanTier.ENTERPRISE, {"product_id": team_id, "license_key": license_key, "increment_uses_count": "false"}))

    return candidates


async def _verify_with_gumroad(license_key: str) -> tuple[dict, PlanTier]:
    """Verify a Gumroad license against configured product_id / product_permalink and team product_id."""
    candidates = _build_gumroad_verify_candidates(license_key)
    if not candidates:
        raise HTTPException(status_code=500, detail="Gumroad configuration is missing.")

    url = "https://api.gumroad.com/v2/licenses/verify"
    team_id = (settings.gumroad_team_product_id or "").strip()

    async with httpx.AsyncClient() as client:
        for candidate_plan, payload in candidates:
            try:
                resp = await client.post(url, data=payload, timeout=10.0)
                data = resp.json()
            except Exception as e:
                logger.error("Failed to reach Gumroad API: %s", e)
                raise HTTPException(status_code=502, detail="Failed to verify license with Gumroad.")

            if data.get("success"):
                purchase = data.get("purchase", {})
                if team_id and purchase.get("product_id") == team_id:
                    return data, PlanTier.ENTERPRISE
                return data, candidate_plan

    raise HTTPException(status_code=400, detail="Invalid or deactivated license key.")


@router.post("/verify-license", response_model=LicenseVerificationResponse)
@router.post("/gumroad/verify-license", response_model=LicenseVerificationResponse)
async def verify_gumroad_license(
    req: LicenseVerificationRequest,
    user_data: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Verifies a self-issued `SLPRO-` signed license key or a Gumroad License Key.
    If valid, upgrades the user to the licensed plan (PRO or ENTERPRISE).
    """
    license_key = (req.license_key or "").strip()
    if not license_key:
        raise HTTPException(status_code=400, detail="License key is required.")

    # Self-issued signed license key path (SLPRO-PRO-... / SLPRO-ENT-...)
    if license_key.startswith("SLPRO-"):
        try:
            verified = verify_license_key(license_key)
        except LicenseConfigError as exc:
            logger.error("License signing key misconfigured: %s", exc)
            raise HTTPException(status_code=500, detail="License verification is not configured.")
        except LicenseExpiredError:
            raise HTTPException(status_code=400, detail="This license key has expired.")
        except LicenseInvalidError:
            raise HTTPException(status_code=400, detail="Invalid or tampered license key.")

        existing = await db.execute(
            select(User.id).where(User.gumroad_license_key == license_key)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="License key already redeemed.")

        return await _apply_license_upgrade(db, user_data, verified.plan, license_key)

    data, target_plan = await _verify_with_gumroad(license_key)

    # Check if the license is refunded or cancelled
    purchase = data.get("purchase", {})
    if purchase.get("refunded") or purchase.get("chargebacked"):
        raise HTTPException(status_code=400, detail="This license key has been refunded and is no longer active.")

    if purchase.get("subscription_failed_at"):
        raise HTTPException(status_code=400, detail="The subscription for this license has failed.")

    # Note: the old `uses > 1` reuse check was dead code (the verify call always
    # sends increment_uses_count=false). Reuse is enforced atomically by the
    # uq_users_gumroad_license_key constraint -> 409 above.

    return await _apply_license_upgrade(db, user_data, target_plan, license_key)


def _truthy(val) -> bool:
    return str(val).strip().lower() in ("1", "true", "yes")


@router.post("/gumroad/ping")
async def gumroad_ping(
    request: Request,
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Gumroad Ping webhook (Pass B): revokes the plan when a purchase is
    refunded or charged back. Authenticated by matching the ping's seller_id
    against the configured GUMROAD_SELLER_ID.
    """
    seller_id = (settings.gumroad_seller_id or "").strip()
    if not seller_id:
        logger.error("GUMROAD_SELLER_ID is not configured; refusing Gumroad ping.")
        raise HTTPException(status_code=500, detail="Gumroad ping is not configured.")

    form = await request.form()
    if str(form.get("seller_id", "")).strip() != seller_id:
        logger.warning("Gumroad ping rejected: seller_id mismatch.")
        raise HTTPException(status_code=403, detail="Invalid seller_id.")

    license_key = str(form.get("license_key", "") or "").strip()
    refunded = _truthy(form.get("refunded"))
    chargebacked = _truthy(form.get("chargebacked")) or _truthy(form.get("disputed"))

    if not (refunded or chargebacked):
        # Other ping types (sale, cancellation of a non-refunded sub) need no action.
        return {"received": True}

    if not license_key:
        logger.warning("Gumroad refund/chargeback ping without license_key; no action taken.")
        return {"received": True}

    result = await db.execute(
        select(User).where(User.gumroad_license_key == license_key).with_for_update()
    )
    user_model = result.scalar_one_or_none()
    if not user_model:
        # Unknown key: acknowledge so Gumroad stops retrying.
        logger.warning("Gumroad ping for unknown license key ending ...%s", license_key[-4:])
        return {"received": True}

    if user_model.plan_source in (None, "gumroad", "license_key"):
        user_model.plan = PlanTier.FREE.value
        user_model.plan_source = None
        if user_model.organization_id:
            org_res = await db.execute(
                select(Organization).where(Organization.id == user_model.organization_id)
            )
            org = org_res.scalar_one_or_none()
            if org and org.plan in (PlanTier.PRO.value, PlanTier.ENTERPRISE.value):
                org.plan = PlanTier.FREE.value
                org.subscription_status = "refunded" if refunded else "chargebacked"
        await db.commit()
        logger.info(
            "Gumroad ping: downgraded user %s to FREE (%s).",
            user_model.id, "refunded" if refunded else "chargebacked",
        )
    else:
        logger.warning(
            "Gumroad ping: user %s entitlement source is '%s'; leaving plan untouched.",
            user_model.id, user_model.plan_source,
        )

    return {"received": True}
