import pytest
import time
from datetime import timedelta
import os

from suspensionlab.backend.security.jwt_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    JWT_ACTIVE_KEY,
    get_jwt_keys
)

def test_hash_password():
    """Test Argon2 password hashing and verification."""
    password = "supersecretpassword123!"
    hashed = hash_password(password)
    
    # Must not match plaintext
    assert hashed != password
    
    # Argon2 hashes usually start with $argon2
    assert hashed.startswith("$argon2")
    
    # Verification should succeed
    is_valid, needs_rehash = verify_password(password, hashed)
    assert is_valid is True
    # A fresh Argon2 hash should not need rehashing
    assert needs_rehash is False

def test_verify_password_bcrypt_legacy():
    """Test that legacy bcrypt hashes still verify but flag needs_rehash."""
    password = "legacy_password"
    # An example bcrypt hash for "legacy_password" (cost 12)
    # Generated via python -c "import bcrypt; print(bcrypt.hashpw(b'legacy_password', bcrypt.gensalt(12)).decode('utf-8'))"
    bcrypt_hash = "$2b$12$9FkE0h4Kx6a1l1M3Z1C.v.8Z6D9J2C4h7k8L3M9N1B5V4C2X7Z1K"
    
    import bcrypt
    real_bcrypt = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(10)).decode('utf-8')
    
    is_valid, needs_rehash = verify_password(password, real_bcrypt)
    assert is_valid is True
    # Passlib deprecated="auto" deprecates any scheme that is not the default (argon2)
    assert needs_rehash is True

def test_verify_password_invalid():
    """Test password verification fails properly."""
    password = "password"
    hashed = hash_password(password)
    
    is_valid, needs_rehash = verify_password("wrong_password", hashed)
    assert is_valid is False
    assert needs_rehash is False

def test_jwt_creation_contains_jti():
    """Test that JWT tokens contain a JTI claim for revocation tracking."""
    data = {"sub": "user-123", "email": "test@example.com"}
    token = create_access_token(data)
    
    payload = decode_access_token(token)
    assert payload is not None
    assert "jti" in payload
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"

def test_refresh_token_creation_contains_jti():
    """Test that Refresh tokens contain a JTI claim."""
    data = {"sub": "user-123"}
    token = create_refresh_token(data)
    
    payload = decode_refresh_token(token)
    assert payload is not None
    assert "jti" in payload
    assert payload["type"] == "refresh"

def test_jwt_key_rotation(monkeypatch):
    """Test that old keys can still decode, but new keys are used for signing."""
    # Temporarily modify keys for testing
    import suspensionlab.backend.security.jwt_utils as jwt_utils
    orig_active = jwt_utils.JWT_ACTIVE_KEY
    
    def mock_get_jwt_keys():
        return {"v1": "old_secret_key_123", "v2": "new_secret_key_456"}
        
    monkeypatch.setattr(jwt_utils, "get_jwt_keys", mock_get_jwt_keys)
    
    try:
        # Test old key
        jwt_utils.JWT_ACTIVE_KEY = "v1"
        old_token = create_access_token({"sub": "user-123"})
        
        # Now rotate to new key
        jwt_utils.JWT_ACTIVE_KEY = "v2"
        new_token = create_access_token({"sub": "user-123"})
        
        # Both should decode successfully
        assert decode_access_token(old_token) is not None
        assert decode_access_token(new_token) is not None
        
        # But if we inspect old_token headers directly with PyJWT:
        import jwt
        unverified = jwt.get_unverified_header(old_token)
        assert unverified.get("kid") == "v1"
        
        unverified_new = jwt.get_unverified_header(new_token)
        assert unverified_new.get("kid") == "v2"
        
    finally:
        # Restore
        jwt_utils.JWT_ACTIVE_KEY = orig_active

def test_jwt_invalid_token_type():
    """Test that access/refresh tokens cannot be swapped."""
    data = {"sub": "user-123"}
    access_token = create_access_token(data)
    refresh_token = create_refresh_token(data)
    
    # decode_refresh_token on an access token should fail
    assert decode_refresh_token(access_token) is None
    
    # decode_access_token on a refresh token should fail
    assert decode_access_token(refresh_token) is None


def test_jwt_malformed_and_nonstring_kid_fail_closed():
    """Malformed tokens and non-string kid headers must fail closed and return None."""
    import base64
    import json

    assert decode_access_token("") is None
    assert decode_access_token("not.a.jwt") is None
    assert decode_access_token(None) is None  # type: ignore[arg-type]

    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT", "kid": ["v1"]}).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps({"sub": "user-123", "type": "access", "exp": time.time() + 300}).encode()).decode().rstrip("=")
    bad_kid_token = f"{header_b64}.{payload_b64}.fakesig"
    assert decode_access_token(bad_kid_token) is None


@pytest.mark.asyncio
async def test_sso_state_and_id_token_validation_pyjwt(monkeypatch):
    """Verify OIDC state tokens and RS256/HS256 ID token validation via PyJWT."""
    from unittest.mock import AsyncMock
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import HTTPException
    from jwt.utils import to_base64url_uint
    from suspensionlab.backend.api.routes import sso_routes

    state = sso_routes._issue_state("nonce-abc", "verifier-xyz")
    parsed = sso_routes._read_state(state)
    assert parsed["nonce"] == "nonce-abc"
    assert parsed["verifier"] == "verifier-xyz"

    keys = get_jwt_keys()
    no_exp_state = jwt.encode(
        {"nonce": "n", "verifier": "v", "type": "sso_state"},
        keys[JWT_ACTIVE_KEY],
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc_info:
        sso_routes._read_state(no_exp_state)
    assert exc_info.value.status_code == 400

    monkeypatch.setattr(sso_routes.settings, "oidc_client_id", "test-client")
    monkeypatch.setattr(sso_routes.settings, "oidc_issuer", "https://idp.example.com")
    monkeypatch.setattr(sso_routes.settings, "oidc_client_secret", "s" * 64)

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "idp-key-1",
                "n": to_base64url_uint(pub.n).decode(),
                "e": to_base64url_uint(pub.e).decode(),
            }
        ]
    }
    rs256_token = jwt.encode(
        {
            "sub": "user-rs",
            "aud": "test-client",
            "iss": "https://idp.example.com",
            "nonce": "nonce-rs",
            "exp": int(time.time()) + 120,
        },
        priv,
        algorithm="RS256",
        headers={"kid": "idp-key-1"},
    )
    monkeypatch.setattr(sso_routes, "_get_jwks", AsyncMock(return_value=jwks))

    claims_rs = await sso_routes._validate_id_token(
        rs256_token, {"jwks_uri": "https://idp.example.com/jwks"}, "nonce-rs"
    )
    assert claims_rs["sub"] == "user-rs"

    with pytest.raises(HTTPException) as nonce_exc:
        await sso_routes._validate_id_token(
            rs256_token, {"jwks_uri": "https://idp.example.com/jwks"}, "wrong-nonce"
        )
    assert nonce_exc.value.status_code == 401

    hs256_token = jwt.encode(
        {
            "sub": "user-hs",
            "aud": "test-client",
            "iss": "https://idp.example.com",
            "nonce": "nonce-hs",
            "exp": int(time.time()) + 120,
        },
        "s" * 64,
        algorithm="HS256",
    )
    claims_hs = await sso_routes._validate_id_token(
        hs256_token, {"jwks_uri": "https://idp.example.com/jwks"}, "nonce-hs"
    )
    assert claims_hs["sub"] == "user-hs"
