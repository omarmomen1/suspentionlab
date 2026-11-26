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

from fastapi import APIRouter, HTTPException, Depends
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
        raise HTTPException(status_code=400, detail="This license key is already in use by another account.")

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
            raise HTTPException(status_code=400, detail="This license key has already been redeemed.")

        return await _apply_license_upgrade(db, user_data, verified.plan, license_key)

    data, target_plan = await _verify_with_gumroad(license_key)

    # Check if the license is refunded or cancelled
    purchase = data.get("purchase", {})
    if purchase.get("refunded") or purchase.get("chargebacked"):
        raise HTTPException(status_code=400, detail="This license key has been refunded and is no longer active.")

    if purchase.get("subscription_failed_at"):
        raise HTTPException(status_code=400, detail="The subscription for this license has failed.")

    # Prevent someone from adding the same key multiple times
    if data.get("uses", 0) > 1:
        raise HTTPException(status_code=400, detail="This license key has already been used on another account.")

    return await _apply_license_upgrade(db, user_data, target_plan, license_key)
