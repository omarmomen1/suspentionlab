"""
Self-issued HMAC-SHA256 signed license keys (SLPRO-PRO-... and SLPRO-ENT-...).

Token format:
    SLPRO-<TIER_TAG>-<payload_b64url>.<sig_b64url>

Where:
    - TIER_TAG is "PRO" (PlanTier.PRO) or "ENT" (PlanTier.ENTERPRISE)
    - payload JSON encodes {"plan": "PRO" | "ENTERPRISE", "max_uses": int, "exp": int, "jti": str}
    - sig_b64url is HMAC-SHA256 over f"SLPRO-{TIER_TAG}-{payload_b64url}"
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from suspensionlab.backend.config import settings
from suspensionlab.backend.security.jwt_utils import JWT_ACTIVE_KEY, get_jwt_keys
from suspensionlab.shared.models import PlanTier


class LicenseKeyError(ValueError):
    """Base error for self-issued license key failures."""


class LicenseConfigError(LicenseKeyError):
    """Raised when the signing/verification secret is missing."""


class LicenseInvalidError(LicenseKeyError):
    """Raised when a token is malformed, tampered, or fails validation."""


class LicenseExpiredError(LicenseKeyError):
    """Raised when a valid signed license key is past its expiration time."""


@dataclass(frozen=True)
class VerifiedLicense:
    plan: PlanTier
    max_uses: int
    exp: int
    jti: Optional[str] = None


_PLAN_TO_TAG = {
    PlanTier.PRO: "PRO",
    PlanTier.ENTERPRISE: "ENT",
}
_TAG_TO_PLAN = {
    "PRO": PlanTier.PRO,
    "ENT": PlanTier.ENTERPRISE,
}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    if not segment or not isinstance(segment, str):
        raise LicenseInvalidError("Empty license token segment.")
    padding = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode((segment + padding).encode("ascii"))
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise LicenseInvalidError("Malformed base64 encoding in license key.") from exc


def normalize_license_plan(plan: str | PlanTier) -> PlanTier:
    raw = plan.value if isinstance(plan, PlanTier) else str(plan or "")
    upper = raw.strip().upper()
    if upper == "PRO":
        return PlanTier.PRO
    if upper in ("ENT", "ENTERPRISE"):
        return PlanTier.ENTERPRISE
    raise LicenseInvalidError(f"Unsupported license plan: {plan!r}. Expected PRO or ENTERPRISE.")


def get_license_signing_secret(override: Optional[str] = None) -> str:
    """
    Resolve the license HMAC signing secret (Pass B: separated from JWT).

    Order of precedence:
      1. explicit override (tests / tooling)
      2. LICENSE_SIGNING_SECRET (settings / env) — required in PROD
      3. non-prod only: legacy fallback to the JWT secret so pre-Pass-B keys
         still verify in DEV/TRIAL. In PROD a missing dedicated secret is a
         hard configuration error, never a JWT reuse.
    """
    signing_material: Optional[str] = override
    if not signing_material:
        signing_material = settings.license_signing_secret or os.getenv("LICENSE_SIGNING_SECRET")
    if not signing_material:
        env = (settings.environment or os.getenv("ENVIRONMENT", "DEV")).upper()
        if env == "PROD":
            raise LicenseConfigError(
                "LICENSE_SIGNING_SECRET is not configured. Refusing to fall back to the JWT secret in PROD."
            )
        signing_material = settings.jwt_secret_key or os.getenv("JWT_SECRET_KEY")
        if not signing_material:
            try:
                keys = get_jwt_keys()
                signing_material = keys.get(JWT_ACTIVE_KEY)
            except RuntimeError:
                signing_material = None
    if not signing_material or not str(signing_material).strip():
        raise LicenseConfigError("License signing secret is not configured for license verification.")
    return str(signing_material)


def generate_license_key(
    plan: str | PlanTier,
    *,
    max_uses: int = 1,
    exp: Optional[int] = None,
    days: int = 365,
    secret_override: Optional[str] = None,
    jti: Optional[str] = None,
) -> str:
    """Create an HMAC-SHA256 signed SLPRO-PRO-... or SLPRO-ENT-... license key."""
    target_plan = normalize_license_plan(plan)
    if isinstance(max_uses, bool) or not isinstance(max_uses, int) or max_uses < 1:
        raise ValueError("max_uses must be an integer >= 1.")
    if exp is None:
        if days < 1:
            raise ValueError("days must be >= 1 when exp is not provided.")
        exp_ts = int(time.time()) + days * 86400
    else:
        if isinstance(exp, bool) or not isinstance(exp, (int, float)):
            raise ValueError("exp must be a Unix timestamp.")
        exp_ts = int(exp)

    signing_key = get_license_signing_secret(secret_override)
    tier_tag = _PLAN_TO_TAG[target_plan]
    payload = {
        "plan": target_plan.value,
        "max_uses": max_uses,
        "exp": exp_ts,
        "jti": jti or secrets.token_hex(6),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)
    signing_input = f"SLPRO-{tier_tag}-{payload_b64}".encode("utf-8")
    sig_bytes = hmac.new(signing_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig_bytes)
    return f"SLPRO-{tier_tag}-{payload_b64}.{sig_b64}"


def verify_license_key(
    token: str,
    *,
    secret_override: Optional[str] = None,
    now: Optional[float] = None,
) -> VerifiedLicense:
    """Verify an SLPRO- signed license token and return its validated claims."""
    if not token or not isinstance(token, str) or not token.startswith("SLPRO-"):
        raise LicenseInvalidError("Invalid license key prefix.")

    remainder = token[len("SLPRO-"):]
    if "-" not in remainder:
        raise LicenseInvalidError("Invalid license key structure.")
    tier_tag, signed_body = remainder.split("-", 1)
    if tier_tag not in _TAG_TO_PLAN:
        raise LicenseInvalidError("Unsupported license tier tag.")
    if "." not in signed_body:
        raise LicenseInvalidError("Missing license key signature.")
    payload_b64, sig_b64 = signed_body.split(".", 1)
    if not payload_b64 or not sig_b64:
        raise LicenseInvalidError("Incomplete license key.")

    signing_key = get_license_signing_secret(secret_override)
    signing_input = f"SLPRO-{tier_tag}-{payload_b64}".encode("utf-8")
    expected_sig = _b64url_encode(
        hmac.new(signing_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected_sig, sig_b64):
        raise LicenseInvalidError("Invalid license key signature.")

    try:
        payload_raw = _b64url_decode(payload_b64)
        payload = json.loads(payload_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseInvalidError("Corrupt license key payload.") from exc

    if not isinstance(payload, dict):
        raise LicenseInvalidError("Invalid license key payload structure.")

    claimed_plan = payload.get("plan")
    try:
        plan_tier = normalize_license_plan(claimed_plan)
    except LicenseInvalidError as exc:
        raise LicenseInvalidError("Invalid plan in license key.") from exc

    if _TAG_TO_PLAN[tier_tag] != plan_tier:
        raise LicenseInvalidError("License tier tag does not match payload plan.")

    max_uses = payload.get("max_uses")
    if isinstance(max_uses, bool) or not isinstance(max_uses, int) or max_uses < 1:
        raise LicenseInvalidError("Invalid max_uses in license key.")

    exp = payload.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        raise LicenseInvalidError("Missing or invalid expiration in license key.")

    current_ts = time.time() if now is None else now
    if float(exp) <= current_ts:
        raise LicenseExpiredError("This license key has expired.")

    jti_val = payload.get("jti")
    return VerifiedLicense(
        plan=plan_tier,
        max_uses=max_uses,
        exp=int(exp),
        jti=str(jti_val) if jti_val is not None else None,
    )
