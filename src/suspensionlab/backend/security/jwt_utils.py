"""
backend/security/jwt_utils.py
JWT token creation and verification for SuspensionLab auth.
"""
from __future__ import annotations

import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Tuple

import jwt
from jwt.exceptions import PyJWTError
import bcrypt
from passlib.context import CryptContext

# ─── Config ──────────────────────────────────────────────────────────────────

JWT_ACTIVE_KEY = os.getenv("JWT_ACTIVE_KEY", "v1")

def get_jwt_keys() -> dict[str, str]:
    jwt_keys_env = os.getenv("JWT_KEYS")
    keys = {}
    
    if jwt_keys_env:
        try:
            keys = json.loads(jwt_keys_env)
        except Exception:
            raise RuntimeError("CRITICAL: JWT_KEYS environment variable is not valid JSON!")
    
    if JWT_ACTIVE_KEY not in keys:
        legacy_key = os.getenv("JWT_SECRET_KEY")
        if legacy_key:
            keys[JWT_ACTIVE_KEY] = legacy_key
            
    if not keys:
        raise RuntimeError("CRITICAL: JWT_KEYS or JWT_SECRET_KEY environment variable is missing! Refusing to start with hardcoded secrets.")
        
    if JWT_ACTIVE_KEY not in keys:
        raise RuntimeError(f"CRITICAL: JWT_ACTIVE_KEY ({JWT_ACTIVE_KEY}) not found in available keys!")
        
    return keys


ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # Default 24 hours (1440 min)
REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Argon2 is preferred, bcrypt supported for legacy hashes via raw bcrypt
pwd_context = CryptContext(schemes=["argon2"])

def hash_password(plain: str) -> str:
    """Hash a password using Argon2id."""
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> Tuple[bool, bool]:
    """
    Verify password and check if it needs to be re-hashed (e.g. from bcrypt to argon2).
    Returns (is_valid, needs_rehash).
    """
    if hashed.startswith("$2b$") or hashed.startswith("$2a$") or hashed.startswith("$2y$"):
        # Legacy bcrypt hash
        try:
            import bcrypt
            is_valid = bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
            return is_valid, is_valid  # if valid, it needs rehash to Argon2
        except ValueError:
            return False, False

    try:
        is_valid = pwd_context.verify(plain, hashed)
        needs_rehash = pwd_context.needs_update(hashed)
        return is_valid, needs_rehash
    except ValueError:
        return False, False

# ─── JWT helpers ──────────────────────────────────────────────────────────────

def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    # Inject jti (JWT ID) for revocation tracking
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "type": "access", "jti": jti})
    
    # Use kid header for key rotation
    headers = {"kid": JWT_ACTIVE_KEY}
    keys = get_jwt_keys()
    return jwt.encode(to_encode, keys[JWT_ACTIVE_KEY], algorithm=ALGORITHM, headers=headers)

def create_refresh_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "type": "refresh", "jti": jti})
    
    headers = {"kid": JWT_ACTIVE_KEY}
    keys = get_jwt_keys()
    return jwt.encode(to_encode, keys[JWT_ACTIVE_KEY], algorithm=ALGORITHM, headers=headers)

def _decode_token_with_rotation(token: str) -> dict[str, Any] | None:
    """Decodes token dynamically handling the `kid` header for rotation."""
    try:
        unverified_headers = jwt.get_unverified_header(token)
        kid = unverified_headers.get("kid", "v1")
        
        keys = get_jwt_keys()
        # SECURITY: Reject tokens with unknown kid outright — do NOT fall back to
        # the active key, as that would allow a forged token with an arbitrary kid
        # header to potentially match the active key's signature.
        if not isinstance(kid, str) or kid not in keys:
            return None
        secret_key = keys[kid]
        
        return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except PyJWTError:
        return None

def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decodes and validates an access token. Returns None if invalid or wrong type."""
    payload = _decode_token_with_rotation(token)
    if not payload or payload.get("type") != "access":
        return None
    return payload

def decode_refresh_token(token: str) -> dict[str, Any] | None:
    """Decodes and validates a refresh token."""
    payload = _decode_token_with_rotation(token)
    if not payload or payload.get("type") != "refresh":
        return None
    return payload


def create_password_reset_token(user_id: str, expires_delta: timedelta | None = None) -> str:
    """Create a dedicated single-purpose password reset JWT (cannot be used as an access token)."""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=1))
    jti = str(uuid.uuid4())
    to_encode = {"sub": user_id, "exp": expire, "type": "password_reset", "jti": jti}
    headers = {"kid": JWT_ACTIVE_KEY}
    keys = get_jwt_keys()
    return jwt.encode(to_encode, keys[JWT_ACTIVE_KEY], algorithm=ALGORITHM, headers=headers)


def decode_password_reset_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a password_reset token strictly."""
    payload = _decode_token_with_rotation(token)
    if not payload or payload.get("type") != "password_reset":
        return None
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Session Revocation & JWKS Key Management (Finding 50)
# ─────────────────────────────────────────────────────────────────────────────

class TokenRevocationRegistry:
    """In-memory and Redis-compatible revocation & reuse detection registry."""
    _revoked_jtis: set[str] = set()
    _used_refresh_jtis: set[str] = set()

    @classmethod
    def revoke_jti(cls, jti: str) -> None:
        cls._revoked_jtis.add(jti)

    @classmethod
    def is_revoked(cls, jti: str) -> bool:
        return jti in cls._revoked_jtis

    @classmethod
    def register_refresh_use(cls, jti: str) -> bool:
        """
        Record refresh token use. Returns True if this is the first use.
        Returns False if REUSE is detected (triggers family revocation).
        """
        if jti in cls._used_refresh_jtis:
            # Token reuse detected! Invalidate all related sessions.
            return False
        cls._used_refresh_jtis.add(jti)
        return True


async def is_jti_revoked(jti: str | None) -> bool:
    """
    Check if JTI is revoked. Lookup order: in-memory registry, Redis, then the
    durable revoked_tokens table so revocation does not fail open when Redis
    is unavailable (Pass B).
    """
    if not jti:
        return False
    if TokenRevocationRegistry.is_revoked(jti):
        return True
    try:
        from suspensionlab.backend.core.redis_client import get_async_redis_conn
        async_redis = get_async_redis_conn()
        if async_redis:
            val = await async_redis.get(f"revoked:{jti}")
            return val is not None
    except Exception:
        pass  # fall through to the durable DB fallback
    try:
        from sqlalchemy import select
        from suspensionlab.backend.database.core import SessionLocal
        from suspensionlab.backend.database.models.revoked_token import RevokedToken
        async with SessionLocal() as session:
            res = await session.execute(
                select(RevokedToken.jti).where(RevokedToken.jti == jti)
            )
            return res.scalar_one_or_none() is not None
    except Exception:
        # DB fallback unavailable; nothing more we can verify against.
        return False


async def record_revoked_jti(jti: str, exp: float | int | None, reason: str) -> None:
    """
    Persist a revoked JTI to the durable revoked_tokens table (best effort).
    This is the fallback `is_jti_revoked` consults when Redis is down.
    """
    if not jti:
        return
    try:
        from sqlalchemy import select
        from suspensionlab.backend.database.core import SessionLocal
        from suspensionlab.backend.database.models.revoked_token import RevokedToken
        expires_at = None
        if exp:
            expires_at = datetime.fromtimestamp(float(exp), tz=timezone.utc).replace(tzinfo=None)
        async with SessionLocal() as session:
            existing = await session.execute(
                select(RevokedToken.jti).where(RevokedToken.jti == jti)
            )
            if existing.scalar_one_or_none() is None:
                session.add(RevokedToken(jti=jti, reason=reason, expires_at=expires_at))
                await session.commit()
    except Exception:
        pass  # durable persistence is best effort; Redis/memory already hold it


def get_public_jwks() -> dict[str, Any]:
    """Export public JWKS (JSON Web Key Set) metadata for internal verification."""
    keys = get_jwt_keys()
    jwks = []
    for kid in keys.keys():
        jwks.append({
            "kty": "oct",
            "kid": kid,
            "alg": ALGORITHM,
            "use": "sig",
            "status": "active" if kid == JWT_ACTIVE_KEY else "rotation_fallback",
        })
    return {"keys": jwks}


