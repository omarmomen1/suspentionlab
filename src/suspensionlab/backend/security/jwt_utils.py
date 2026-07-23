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

from jose import JWTError, jwt
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
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # 15 minutes
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
        unverified_headers = jwt.get_unverified_headers(token)
        kid = unverified_headers.get("kid", "v1")
        
        keys = get_jwt_keys()
        # SECURITY: Reject tokens with unknown kid outright — do NOT fall back to
        # the active key, as that would allow a forged token with an arbitrary kid
        # header to potentially match the active key's signature.
        if kid not in keys:
            return None
        secret_key = keys[kid]
        
        return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except JWTError:
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
