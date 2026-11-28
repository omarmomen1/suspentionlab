"""
backend/security/saml.py
========================
SuspensionLab PRO — Enterprise SAML 2.0 Service Provider Engine.

Implements:
1. SP Metadata XML generation (RFC / OASIS SAML 2.0 Core & Metadata profile).
2. SP-Initiated Login AuthnRequest generation (with Deflate + Base64 encoding for HTTP-Redirect).
3. Signed & Tamper-Evident RelayState generation and validation (HMAC-SHA256).
4. Assertion Consumer Service (ACS) SAMLResponse decoding, decompression, and parsing.
5. Strict SAML 2.0 Assertion Validation:
   - Issuer check
   - AudienceRestriction validation against SP Entity ID
   - SubjectConfirmationData recipient and time boundary (NotBefore / NotOnOrAfter with clock skew)
   - Status code verification (urn:oasis:names:tc:SAML:2.0:status:Success)
   - X.509 Certificate and Signature verification
   - Replay attack protection (tracking Assertion IDs)
6. Attribute extraction (NameID / Email, Name, Role, Groups).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
import urllib.parse
import uuid
import zlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
try:
    from defusedxml.ElementTree import fromstring as safe_xml_fromstring
except ImportError as exc:
    raise RuntimeError(
        "CRITICAL: 'defusedxml' is required for secure SAML 2.0 XML parsing to prevent "
        "XML External Entity (XXE) attacks. Refusing insecure fallback to standard library XML parser."
    ) from exc

from suspensionlab.backend.config import settings

logger = logging.getLogger(__name__)

SAML_BINDING_HTTP_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
SAML_BINDING_HTTP_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
SAML_NAMEID_FORMAT_EMAIL = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
SAML_STATUS_SUCCESS = "urn:oasis:names:tc:SAML:2.0:status:Success"

# Namespace mappings for SAML XML
NAMESPACES = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "md": "urn:oasis:names:tc:SAML:2.0:metadata",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}

# Cache for replay attack prevention: records assertion IDs and expiration timestamps.
# Wave 6: primary store is a DISTRIBUTED Redis cache (SET NX PX, atomic check-and-set)
# so multi-worker / serverless deployments reject replayed assertions consistently.
# The in-process dict remains as a graceful fallback when Redis is unavailable
# (single-worker correctness preserved; a warning is logged once).
_seen_assertion_ids: Dict[str, float] = {}

_REPLAY_KEY_PREFIX = "saml:replay:"
_sync_redis_client = None
_sync_redis_unavailable = False


def _get_replay_redis():
    """Lazily connect a synchronous Redis client for the replay cache."""
    global _sync_redis_client, _sync_redis_unavailable
    if _sync_redis_client is not None or _sync_redis_unavailable:
        return _sync_redis_client
    import os
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        _sync_redis_unavailable = True
        return None
    try:
        import redis as sync_redis
        client = sync_redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)
        client.ping()
        _sync_redis_client = client
    except Exception as exc:
        logger.warning(
            "SAML replay cache: Redis unavailable (%s); falling back to in-process cache "
            "(replay protection is per-worker only until Redis recovers).", exc,
        )
        _sync_redis_unavailable = True
        _sync_redis_client = None
    return _sync_redis_client


def _cleanup_seen_assertions():
    now = time.time()
    expired = [k for k, exp in _seen_assertion_ids.items() if exp < now]
    for k in expired:
        _seen_assertion_ids.pop(k, None)


def _replay_lookup(assertion_id: str) -> bool:
    """Return True if this assertion ID was already consumed (read-only check)."""
    client = _get_replay_redis()
    if client is not None:
        try:
            return bool(client.exists(_REPLAY_KEY_PREFIX + assertion_id))
        except Exception as exc:
            logger.warning("SAML replay cache Redis read error (%s); in-process fallback", exc)
    _cleanup_seen_assertions()
    return assertion_id in _seen_assertion_ids


def _replay_mark(assertion_id: str, expires_at_epoch: float) -> None:
    """Atomically mark an assertion ID as consumed until its expiry.

    Raises ValueError on a replay race (another worker consumed it between the
    lookup and the mark). TTL is the assertion's own expiry (plus skew), so
    entries expire gracefully instead of growing unboundedly.
    """
    ttl_ms = max(int((expires_at_epoch - time.time()) * 1000), 60_000)
    client = _get_replay_redis()
    if client is not None:
        try:
            was_set = client.set(_REPLAY_KEY_PREFIX + assertion_id, "1", nx=True, px=ttl_ms)
            if not was_set:
                raise ValueError(f"SAML Assertion replay detected (ID: {assertion_id})")
            return
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("SAML replay cache Redis write error (%s); in-process fallback", exc)
    _cleanup_seen_assertions()
    if assertion_id in _seen_assertion_ids:
        raise ValueError(f"SAML Assertion replay detected (ID: {assertion_id})")
    _seen_assertion_ids[assertion_id] = expires_at_epoch


def generate_sp_metadata_xml(
    sp_entity_id: str,
    acs_url: str,
    org_name: str = "SuspensionLab PRO Enterprise",
) -> str:
    """Generate OASIS SAML 2.0 compliant SP EntityDescriptor metadata XML."""
    root = ET.Element(
        "{urn:oasis:names:tc:SAML:2.0:metadata}EntityDescriptor",
        {
            "xmlns:md": "urn:oasis:names:tc:SAML:2.0:metadata",
            "xmlns:saml": "urn:oasis:names:tc:SAML:2.0:assertion",
            "xmlns:ds": "http://www.w3.org/2000/09/xmldsig#",
            "entityID": sp_entity_id,
        },
    )

    spsso = ET.SubElement(
        root,
        "{urn:oasis:names:tc:SAML:2.0:metadata}SPSSODescriptor",
        {
            "AuthnRequestsSigned": "false",
            "WantAssertionsSigned": "true",
            "protocolSupportEnumeration": "urn:oasis:names:tc:SAML:2.0:protocol",
        },
    )

    name_id_format = ET.SubElement(
        spsso,
        "{urn:oasis:names:tc:SAML:2.0:metadata}NameIDFormat",
    )
    name_id_format.text = SAML_NAMEID_FORMAT_EMAIL

    acs = ET.SubElement(
        spsso,
        "{urn:oasis:names:tc:SAML:2.0:metadata}AssertionConsumerService",
        {
            "Binding": SAML_BINDING_HTTP_POST,
            "Location": acs_url,
            "index": "1",
            "isDefault": "true",
        },
    )

    org = ET.SubElement(root, "{urn:oasis:names:tc:SAML:2.0:metadata}Organization")
    org_name_elem = ET.SubElement(org, "{urn:oasis:names:tc:SAML:2.0:metadata}OrganizationName", {"xml:lang": "en"})
    org_name_elem.text = org_name
    org_display = ET.SubElement(org, "{urn:oasis:names:tc:SAML:2.0:metadata}OrganizationDisplayName", {"xml:lang": "en"})
    org_display.text = org_name
    org_url = ET.SubElement(org, "{urn:oasis:names:tc:SAML:2.0:metadata}OrganizationURL", {"xml:lang": "en"})
    org_url.text = "https://suspensionlab.pro"

    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def get_saml_relay_state_secret() -> bytes:
    """
    HMAC secret for RelayState signing (Pass B: separated from JWT).

    Uses SAML_RELAY_STATE_SECRET (settings/env). In PROD a missing dedicated
    secret is a hard error; non-prod falls back to the JWT key material so
    existing dev flows keep working.
    """
    from suspensionlab.backend.config import settings
    secret = settings.saml_relay_state_secret or os.getenv("SAML_RELAY_STATE_SECRET")
    if secret and str(secret).strip():
        return str(secret).encode()
    env = (settings.environment or os.getenv("ENVIRONMENT", "DEV")).upper()
    if env == "PROD":
        raise RuntimeError(
            "CRITICAL: SAML_RELAY_STATE_SECRET is not configured. "
            "Refusing to sign RelayState with the JWT secret in PROD."
        )
    from suspensionlab.backend.security.jwt_utils import get_jwt_keys, JWT_ACTIVE_KEY
    return get_jwt_keys()[JWT_ACTIVE_KEY].encode()


def generate_relay_state(org_id: str, return_to: str = "/dashboard") -> str:
    """Create a signed, tamper-evident RelayState token."""
    signing_key = get_saml_relay_state_secret()
    nonce = secrets.token_hex(8)
    expiry = int(time.time()) + 900  # 15 minutes
    payload = f"{org_id}|{return_to}|{expiry}|{nonce}"
    sig = hmac.new(signing_key, payload.encode(), hashlib.sha256).hexdigest()
    raw_token = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(raw_token.encode()).decode()


def validate_relay_state(relay_state_b64: str) -> Tuple[str, str]:
    """Validate RelayState signature and expiry. Returns (org_id, return_to)."""
    try:
        raw = base64.urlsafe_b64decode(relay_state_b64.encode()).decode()
        parts = raw.split("|")
        if len(parts) != 5:
            raise ValueError("Invalid RelayState format")
        org_id, return_to, expiry_str, nonce, sig = parts
        expiry = int(expiry_str)
        if time.time() > expiry:
            raise ValueError("RelayState expired")

        signing_key = get_saml_relay_state_secret()
        payload = f"{org_id}|{return_to}|{expiry_str}|{nonce}"
        expected_sig = hmac.new(signing_key, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("RelayState signature mismatch")
        return org_id, return_to
    except Exception as e:
        logger.warning("RelayState validation failed: %s", e)
        raise ValueError(f"Invalid or tampered RelayState: {e}")


def create_authn_request(
    idp_sso_url: str,
    sp_entity_id: str,
    acs_url: str,
    relay_state: str,
) -> Tuple[str, str]:
    """
    Generate SAML 2.0 AuthnRequest XML and encode it for HTTP-Redirect binding.
    Returns (redirect_url, request_id).
    """
    request_id = f"ID_{uuid.uuid4()}"
    issue_instant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    authn_request = (
        f'<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        f'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{request_id}" Version="2.0" IssueInstant="{issue_instant}" '
        f'Destination="{idp_sso_url}" AssertionConsumerServiceURL="{acs_url}" '
        f'ProtocolBinding="{SAML_BINDING_HTTP_POST}">'
        f'<saml:Issuer>{sp_entity_id}</saml:Issuer>'
        f'<samlp:NameIDPolicy Format="{SAML_NAMEID_FORMAT_EMAIL}" AllowCreate="true"/>'
        f'</samlp:AuthnRequest>'
    )

    # Deflate (without headers) + Base64 + URL encode per SAML HTTP-Redirect binding spec
    compressed = zlib.compress(authn_request.encode("utf-8"))[2:-4]
    saml_request_b64 = base64.b64encode(compressed).decode("utf-8")

    params = {
        "SAMLRequest": saml_request_b64,
        "RelayState": relay_state,
    }
    separator = "&" if "?" in idp_sso_url else "?"
    redirect_url = f"{idp_sso_url}{separator}{urllib.parse.urlencode(params)}"
    return redirect_url, request_id


def verify_saml_xml_signature(xml_bytes: bytes, idp_x509_cert_pem: Optional[str]) -> bool:
    """
    Cryptographically verifies the XMLDSig signature on a SAML 2.0 Response or Assertion
    against the provided IdP X.509 certificate. Strictly fails closed if missing or invalid.
    """
    if not idp_x509_cert_pem or not idp_x509_cert_pem.strip():
        raise ValueError("Missing IdP X.509 certificate for SAML signature verification")

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        import lxml.etree as etree
    except ImportError as exc:
        raise RuntimeError("Required cryptographic or XML libraries missing for SAML signature verification") from exc

    cert_clean = idp_x509_cert_pem.strip()
    if not cert_clean.startswith("-----BEGIN"):
        cert_clean = f"-----BEGIN CERTIFICATE-----\n{cert_clean}\n-----END CERTIFICATE-----\n"

    try:
        cert = x509.load_pem_x509_certificate(cert_clean.encode("utf-8"))
        pub_key = cert.public_key()
    except Exception as exc:
        raise ValueError(f"Invalid IdP X.509 certificate: {exc}")

    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(xml_bytes, parser=parser)
    except Exception as exc:
        raise ValueError(f"Invalid SAML XML for signature verification: {exc}")

    sig_elem = root.find(".//{http://www.w3.org/2000/09/xmldsig#}Signature")
    if sig_elem is None:
        raise ValueError("SAML response/assertion lacks required XMLDSig cryptographic signature")

    signed_info = sig_elem.find("{http://www.w3.org/2000/09/xmldsig#}SignedInfo")
    if signed_info is None:
        raise ValueError("Missing SignedInfo in XML signature")

    sig_val = sig_elem.find("{http://www.w3.org/2000/09/xmldsig#}SignatureValue")
    if sig_val is None or not sig_val.text:
        raise ValueError("Missing SignatureValue in XML signature")

    try:
        raw_sig = base64.b64decode(sig_val.text.strip())
    except Exception as exc:
        raise ValueError(f"Invalid base64 in SignatureValue: {exc}")

    signed_info_c14n = etree.tostring(signed_info, method="c14n", exclusive=True)

    sig_method = signed_info.find("{http://www.w3.org/2000/09/xmldsig#}SignatureMethod")
    sig_alg = sig_method.attrib.get("Algorithm", "").lower() if sig_method is not None else ""
    hash_algo = hashes.SHA1() if "rsa-sha1" in sig_alg else hashes.SHA256()

    try:
        pub_key.verify(raw_sig, signed_info_c14n, padding.PKCS1v15(), hash_algo)
    except Exception as exc:
        raise ValueError(f"SAML XML signature cryptographic verification failed: {exc}")

    ref_elem = signed_info.find("{http://www.w3.org/2000/09/xmldsig#}Reference")
    if ref_elem is not None:
        digest_val_elem = ref_elem.find("{http://www.w3.org/2000/09/xmldsig#}DigestValue")
        if digest_val_elem is not None and digest_val_elem.text:
            expected_digest = base64.b64decode(digest_val_elem.text.strip())
            uri = ref_elem.attrib.get("URI", "")
            target_id = uri.lstrip("#")

            target = None
            if target_id:
                target = root.find(f".//*[@ID='{target_id}']")
            if target is None:
                target = root.find(".//{urn:oasis:names:tc:SAML:2.0:assertion}Assertion") or root

            target_copy = etree.fromstring(etree.tostring(target))
            for s in target_copy.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
                s.getparent().remove(s)
            target_c14n = etree.tostring(target_copy, method="c14n", exclusive=True)

            digest_method = ref_elem.find("{http://www.w3.org/2000/09/xmldsig#}DigestMethod")
            d_alg = digest_method.attrib.get("Algorithm", "").lower() if digest_method is not None else ""
            actual_digest = hashlib.sha1(target_c14n).digest() if "sha1" in d_alg else hashlib.sha256(target_c14n).digest()
            if not hmac.compare_digest(actual_digest, expected_digest):
                raise ValueError("SAML XML signature digest mismatch (tampered content)")

    return True


def sign_saml_response_xml(xml_str: str, private_key, cert_der_b64: str) -> str:
    """Helper to sign a SAML 2.0 XML assertion with RSA-SHA256 XMLDSig."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    import lxml.etree as etree

    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(xml_str.encode("utf-8"), parser=parser)
    assertion = root.find(".//{urn:oasis:names:tc:SAML:2.0:assertion}Assertion")
    target = assertion if assertion is not None else root
    target_id = target.attrib.get("ID", "")

    target_c14n = etree.tostring(target, method="c14n", exclusive=True)
    digest = hashlib.sha256(target_c14n).digest()
    digest_b64 = base64.b64encode(digest).decode("utf-8")

    signed_info_xml = f"""<ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
<ds:Reference URI="#{target_id}">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
<ds:Transform Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{digest_b64}</ds:DigestValue>
</ds:Reference>
</ds:SignedInfo>"""
    signed_info_elem = etree.fromstring(signed_info_xml.encode("utf-8"))
    signed_info_c14n = etree.tostring(signed_info_elem, method="c14n", exclusive=True)

    sig_bytes = private_key.sign(signed_info_c14n, padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")

    sig_xml = f"""<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
{signed_info_xml}
<ds:SignatureValue>{sig_b64}</ds:SignatureValue>
<ds:KeyInfo>
<ds:X509Data>
<ds:X509Certificate>{cert_der_b64}</ds:X509Certificate>
</ds:X509Data>
</ds:KeyInfo>
</ds:Signature>"""
    sig_elem = etree.fromstring(sig_xml.encode("utf-8"))

    issuer_elem = target.find("{urn:oasis:names:tc:SAML:2.0:assertion}Issuer")
    if issuer_elem is not None:
        idx = target.index(issuer_elem) + 1
        target.insert(idx, sig_elem)
    else:
        target.insert(0, sig_elem)

    return etree.tostring(root, encoding="utf-8").decode("utf-8")


def parse_and_validate_saml_response(
    saml_response_b64: str,
    expected_audience: str,
    expected_recipient: str,
    expected_idp_entity_id: Optional[str] = None,
    idp_x509_cert_pem: Optional[str] = None,
    clock_skew_seconds: int = 300,
) -> Dict[str, Any]:
    """
    Decodes, parses, and rigorously validates a SAMLResponse assertion.
    Extracts Subject NameID, Email, Name, and Role attributes.
    Strictly validates XMLDSig signature against idp_x509_cert_pem (fail-closed).
    """
    _cleanup_seen_assertions()

    # 1. Base64 decode
    try:
        xml_bytes = base64.b64decode(saml_response_b64)
    except Exception as e:
        raise ValueError(f"SAMLResponse is not valid base64: {e}")

    # 2. Cryptographic XMLDSig signature verification (fail-closed)
    verify_saml_xml_signature(xml_bytes, idp_x509_cert_pem)

    # 3. Parse XML (defused against XXE and entity expansion)
    try:
        root = safe_xml_fromstring(xml_bytes)
    except Exception as e:
        raise ValueError(f"Invalid SAMLResponse XML structure: {e}")

    # 3. Validate Status Code
    status_elem = root.find(".//{urn:oasis:names:tc:SAML:2.0:protocol}StatusCode")
    if status_elem is None:
        raise ValueError("Missing StatusCode in SAMLResponse")
    status_val = status_elem.attrib.get("Value")
    if status_val != SAML_STATUS_SUCCESS:
        msg_elem = root.find(".//{urn:oasis:names:tc:SAML:2.0:protocol}StatusMessage")
        msg = msg_elem.text if msg_elem is not None else status_val
        raise ValueError(f"SAML authentication failed with status: {msg}")

    # 4. Locate Assertion
    assertion = root.find(".//{urn:oasis:names:tc:SAML:2.0:assertion}Assertion")
    if assertion is None:
        raise ValueError("Missing Assertion element in SAMLResponse")

    assertion_id = assertion.attrib.get("ID")
    if not assertion_id:
        raise ValueError("Assertion is missing ID attribute")

    # 5. Replay Attack Prevention (distributed Redis cache + in-process fallback)
    if _replay_lookup(assertion_id):
        raise ValueError(f"SAML Assertion replay detected (ID: {assertion_id})")

    # 6. Validate Issuer
    issuer_elem = assertion.find("{urn:oasis:names:tc:SAML:2.0:assertion}Issuer")
    if issuer_elem is None or not issuer_elem.text:
        raise ValueError("Missing Issuer in SAML Assertion")
    issuer = issuer_elem.text.strip()
    if expected_idp_entity_id and issuer != expected_idp_entity_id.strip():
        raise ValueError(f"SAML Issuer mismatch. Expected '{expected_idp_entity_id}', got '{issuer}'")

    # 7. Validate Conditions (NotBefore, NotOnOrAfter, AudienceRestriction)
    conditions = assertion.find("{urn:oasis:names:tc:SAML:2.0:assertion}Conditions")
    now = datetime.now(timezone.utc)
    skew = timedelta(seconds=clock_skew_seconds)

    if conditions is not None:
        not_before_str = conditions.attrib.get("NotBefore")
        not_on_or_after_str = conditions.attrib.get("NotOnOrAfter")

        if not_before_str:
            not_before = datetime.fromisoformat(not_before_str.replace("Z", "+00:00"))
            if now + skew < not_before:
                raise ValueError("SAML Assertion is not yet valid (NotBefore violation)")

        if not_on_or_after_str:
            not_on_or_after = datetime.fromisoformat(not_on_or_after_str.replace("Z", "+00:00"))
            if now - skew >= not_on_or_after:
                raise ValueError("SAML Assertion has expired (NotOnOrAfter violation)")
            # Record assertion ID expiry for replay prevention (atomic check-and-set)
            _replay_mark(assertion_id, not_on_or_after.timestamp() + clock_skew_seconds)
        else:
            _replay_mark(assertion_id, time.time() + 3600)

        # Audience check
        audience_elems = conditions.findall(".//{urn:oasis:names:tc:SAML:2.0:assertion}Audience")
        audiences = [a.text.strip() for a in audience_elems if a.text]
        if expected_audience and audiences and expected_audience.strip() not in audiences:
            raise ValueError(f"SAML Audience mismatch. Expected '{expected_audience}', found {audiences}")

    # 8. Validate SubjectConfirmationData (Recipient)
    subj_data = assertion.find(".//{urn:oasis:names:tc:SAML:2.0:assertion}SubjectConfirmationData")
    if subj_data is not None:
        recipient = subj_data.attrib.get("Recipient")
        if recipient and expected_recipient:
            allowed = [expected_recipient] if isinstance(expected_recipient, str) else list(expected_recipient)
            if not any(recipient.rstrip("/").lower() == r.rstrip("/").lower() for r in allowed):
                raise ValueError(f"SAML Recipient mismatch. Expected one of '{allowed}', got '{recipient}'")

    # 9. Extract NameID (Primary Identity / Email)
    name_id_elem = assertion.find(".//{urn:oasis:names:tc:SAML:2.0:assertion}NameID")
    if name_id_elem is None or not name_id_elem.text:
        raise ValueError("Missing NameID in SAML Assertion Subject")
    name_id = name_id_elem.text.strip()

    # 10. Extract Attributes
    attributes: Dict[str, List[str]] = {}
    attr_statement = assertion.find("{urn:oasis:names:tc:SAML:2.0:assertion}AttributeStatement")
    if attr_statement is not None:
        for attr in attr_statement.findall("{urn:oasis:names:tc:SAML:2.0:assertion}Attribute"):
            attr_name = attr.attrib.get("Name") or attr.attrib.get("FriendlyName")
            if not attr_name:
                continue
            values = [v.text.strip() for v in attr.findall("{urn:oasis:names:tc:SAML:2.0:assertion}AttributeValue") if v.text]
            attributes[attr_name.lower()] = values

    # Resolve email, name, role
    email = attributes.get("email", [name_id])[0] if attributes.get("email") else name_id
    first_name = attributes.get("firstname", [""])[0] or attributes.get("givenname", [""])[0]
    last_name = attributes.get("lastname", [""])[0] or attributes.get("surname", [""])[0]
    display_name = attributes.get("displayname", [""])[0] or attributes.get("name", [""])[0]
    if not display_name and (first_name or last_name):
        display_name = f"{first_name} {last_name}".strip()

    role = attributes.get("role", [""])[0] or attributes.get("groups", [""])[0] or "Engineer"

    return {
        "assertion_id": assertion_id,
        "issuer": issuer,
        "name_id": name_id,
        "email": email.lower(),
        "name": display_name or email.split("@")[0],
        "role": role,
        "attributes": attributes,
    }
