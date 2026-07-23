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
        
        # But if we decode old_token with a strictly different secret using PyJWT manually to check:
        from jose import jwt
        unverified = jwt.get_unverified_headers(old_token)
        assert unverified.get("kid") == "v1"
        
        unverified_new = jwt.get_unverified_headers(new_token)
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
