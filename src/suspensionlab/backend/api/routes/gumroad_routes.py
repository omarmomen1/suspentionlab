from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.database.models import User
from suspensionlab.backend.auth import verify_api_key, PlanTier
from suspensionlab.backend.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

class LicenseVerificationRequest(BaseModel):
    license_key: str

class LicenseVerificationResponse(BaseModel):
    success: bool
    plan: PlanTier
    message: str

@router.post("/verify-license", response_model=LicenseVerificationResponse)
async def verify_gumroad_license(
    req: LicenseVerificationRequest,
    user_data: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Verifies a Gumroad License Key.
    If valid, upgrades the user to PRO.
    """
    if not req.license_key:
        raise HTTPException(status_code=400, detail="License key is required.")

    permalink = settings.gumroad_product_permalink
    if not permalink:
        raise HTTPException(status_code=500, detail="Gumroad configuration is missing.")

    # Call Gumroad API
    url = "https://api.gumroad.com/v2/licenses/verify"
    payload = {
        "product_permalink": permalink,
        "license_key": req.license_key
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, data=payload, timeout=10.0)
            data = resp.json()
        except Exception as e:
            logger.error("Failed to reach Gumroad API: %s", e)
            raise HTTPException(status_code=502, detail="Failed to verify license with Gumroad.")

    if not data.get("success"):
        raise HTTPException(status_code=400, detail="Invalid or deactivated license key.")

    # Check if the license is refunded or cancelled
    purchase = data.get("purchase", {})
    if purchase.get("refunded") or purchase.get("chargebacked"):
        raise HTTPException(status_code=400, detail="This license key has been refunded and is no longer active.")
    
    # Optional: If it's a subscription, check if it's cancelled/failed
    # Gumroad uses 'subscription_cancelled_at' and 'subscription_failed_at'
    if purchase.get("subscription_failed_at"):
        raise HTTPException(status_code=400, detail="The subscription for this license has failed.")

    # License is valid! Upgrade the user.
    user_id = user_data["user_id"]
    result = await db.execute(select(User).where(User.id == user_id))
    user_model = result.scalar_one_or_none()

    if not user_model:
        raise HTTPException(status_code=404, detail="User not found.")

    # Upgrade to PRO
    user_model.plan = PlanTier.PRO
    # Save the license key to the user model so we can re-verify it later if needed
    # We will just dump it into metadata for now to avoid schema changes
    if not user_model.metadata_:
        user_model.metadata_ = {}
    user_model.metadata_["gumroad_license_key"] = req.license_key

    await db.commit()

    return LicenseVerificationResponse(
        success=True,
        plan=PlanTier.PRO,
        message="License verified successfully! Your account has been upgraded to PRO."
    )
