"""
tests/test_saml_service_provider.py
===================================
SuspensionLab PRO — Enterprise SAML 2.0 Service Provider Test Matrix.
"""
import base64
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.saml import (
    generate_sp_metadata_xml,
    generate_relay_state,
    validate_relay_state,
    create_authn_request,
    parse_and_validate_saml_response,
    sign_saml_response_xml,
)

_test_rsa_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend(),
)
_test_cert = (
    x509.CertificateBuilder()
    .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "Test Enterprise IdP")]))
    .issuer_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "Test Enterprise IdP")]))
    .public_key(_test_rsa_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
    .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
    .sign(_test_rsa_key, hashes.SHA256(), default_backend())
)
TEST_IDP_CERT_PEM = _test_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
_TEST_CERT_DER_B64 = base64.b64encode(_test_cert.public_bytes(serialization.Encoding.DER)).decode("utf-8")


def _build_test_saml_response_xml(
    assertion_id: str,
    issuer: str,
    audience: str,
    recipient: str,
    name_id: str,
    email: str,
    name: str = "Test SAML User",
    status_code: str = "urn:oasis:names:tc:SAML:2.0:status:Success",
    not_before_offset_sec: int = -60,
    not_on_or_after_offset_sec: int = 300,
    sign: bool = True,
) -> str:
    now = datetime.now(timezone.utc)
    issue_instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    not_before = (now + timedelta(seconds=not_before_offset_sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
    not_on_or_after = (now + timedelta(seconds=not_on_or_after_offset_sec)).strftime("%Y-%m-%dT%H:%M:%SZ")

    xml = f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
        xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
        ID="RESP_{uuid.uuid4().hex}"
        Version="2.0"
        IssueInstant="{issue_instant}"
        Destination="{recipient}">
        <saml:Issuer>{issuer}</saml:Issuer>
        <samlp:Status>
            <samlp:StatusCode Value="{status_code}"/>
        </samlp:Status>
        <saml:Assertion ID="{assertion_id}" Version="2.0" IssueInstant="{issue_instant}">
            <saml:Issuer>{issuer}</saml:Issuer>
            <saml:Subject>
                <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{name_id}</saml:NameID>
                <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
                    <saml:SubjectConfirmationData Recipient="{recipient}" NotOnOrAfter="{not_on_or_after}"/>
                </saml:SubjectConfirmation>
            </saml:Subject>
            <saml:Conditions NotBefore="{not_before}" NotOnOrAfter="{not_on_or_after}">
                <saml:AudienceRestriction>
                    <saml:Audience>{audience}</saml:Audience>
                </saml:AudienceRestriction>
            </saml:Conditions>
            <saml:AttributeStatement>
                <saml:Attribute Name="email">
                    <saml:AttributeValue>{email}</saml:AttributeValue>
                </saml:Attribute>
                <saml:Attribute Name="name">
                    <saml:AttributeValue>{name}</saml:AttributeValue>
                </saml:Attribute>
                <saml:Attribute Name="role">
                    <saml:AttributeValue>Engineer</saml:AttributeValue>
                </saml:Attribute>
            </saml:AttributeStatement>
        </saml:Assertion>
    </samlp:Response>"""
    if sign:
        xml = sign_saml_response_xml(xml, _test_rsa_key, _TEST_CERT_DER_B64)
    return xml


def test_sp_metadata_xml_generation():
    """Verify SP EntityDescriptor XML conforms to SAML 2.0 specifications."""
    sp_entity = "https://suspensionlab.pro/saml/sp/metadata"
    acs_url = "https://suspensionlab.pro/saml/acs"
    xml = generate_sp_metadata_xml(sp_entity, acs_url, "Test OEM")

    assert 'entityID="https://suspensionlab.pro/saml/sp/metadata"' in xml
    assert 'AssertionConsumerService' in xml
    assert 'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"' in xml
    assert 'Location="https://suspensionlab.pro/saml/acs"' in xml
    assert 'NameIDFormat' in xml


def test_relay_state_signed_token_and_tamper_detection():
    """Verify HMAC-SHA256 signature and anti-tamper validation on RelayState."""
    org_id = str(uuid.uuid4())
    relay_state = generate_relay_state(org_id=org_id, return_to="/simulations/runs")

    valid_org, valid_dest = validate_relay_state(relay_state)
    assert valid_org == org_id
    assert valid_dest == "/simulations/runs"

    # Tamper with token
    tampered = relay_state[:-4] + "AAAA"
    with pytest.raises(ValueError, match="Invalid or tampered"):
        validate_relay_state(tampered)


def test_authn_request_generation():
    """Verify AuthnRequest generation with deflated URL encoding."""
    redirect_url, req_id = create_authn_request(
        idp_sso_url="https://idp.example.com/sso",
        sp_entity_id="https://suspensionlab.pro/saml/metadata",
        acs_url="https://suspensionlab.pro/saml/acs",
        relay_state="state123",
    )
    assert "https://idp.example.com/sso?" in redirect_url
    assert "SAMLRequest=" in redirect_url
    assert "RelayState=state123" in redirect_url
    assert req_id.startswith("ID_")


def test_saml_assertion_validation_rules():
    """Test assertion validation: issuer, audience, timestamp, and replay."""
    assertion_id = f"ASSERT_{uuid.uuid4().hex}"
    issuer = "https://idp.example.com"
    audience = "https://suspensionlab.pro/saml/metadata"
    recipient = "https://suspensionlab.pro/saml/acs"
    email = "engineer@motorsport.com"

    xml = _build_test_saml_response_xml(
        assertion_id=assertion_id,
        issuer=issuer,
        audience=audience,
        recipient=recipient,
        name_id=email,
        email=email,
    )
    b64_resp = base64.b64encode(xml.encode()).decode()

    # Valid assertion succeeds
    parsed = parse_and_validate_saml_response(
        saml_response_b64=b64_resp,
        expected_audience=audience,
        expected_recipient=recipient,
        expected_idp_entity_id=issuer,
        idp_x509_cert_pem=TEST_IDP_CERT_PEM,
    )
    assert parsed["email"] == email
    assert parsed["name_id"] == email
    assert parsed["assertion_id"] == assertion_id

    # Replay attack: submitting same assertion ID again must fail
    with pytest.raises(ValueError, match="replay detected"):
        parse_and_validate_saml_response(
            saml_response_b64=b64_resp,
            expected_audience=audience,
            expected_recipient=recipient,
            expected_idp_entity_id=issuer,
            idp_x509_cert_pem=TEST_IDP_CERT_PEM,
        )


def test_saml_assertion_expiration_rejection():
    """Assertions past NotOnOrAfter timestamp must be rejected."""
    assertion_id = f"ASSERT_{uuid.uuid4().hex}"
    xml_expired = _build_test_saml_response_xml(
        assertion_id=assertion_id,
        issuer="https://idp.example.com",
        audience="https://suspensionlab.pro/saml/metadata",
        recipient="https://suspensionlab.pro/saml/acs",
        name_id="user@example.com",
        email="user@example.com",
        not_before_offset_sec=-1000,
        not_on_or_after_offset_sec=-500,  # Expired in past
    )
    b64_expired = base64.b64encode(xml_expired.encode()).decode()

    with pytest.raises(ValueError, match="NotOnOrAfter"):
        parse_and_validate_saml_response(
            saml_response_b64=b64_expired,
            expected_audience="https://suspensionlab.pro/saml/metadata",
            expected_recipient="https://suspensionlab.pro/saml/acs",
            expected_idp_entity_id="https://idp.example.com",
            idp_x509_cert_pem=TEST_IDP_CERT_PEM,
        )


def test_saml_assertion_audience_mismatch():
    """Assertions targeted for a different SP entity ID must be rejected."""
    assertion_id = f"ASSERT_{uuid.uuid4().hex}"
    xml = _build_test_saml_response_xml(
        assertion_id=assertion_id,
        issuer="https://idp.example.com",
        audience="https://different-sp.com/metadata",
        recipient="https://suspensionlab.pro/saml/acs",
        name_id="user@example.com",
        email="user@example.com",
    )
    b64_resp = base64.b64encode(xml.encode()).decode()

    with pytest.raises(ValueError, match="Audience mismatch"):
        parse_and_validate_saml_response(
            saml_response_b64=b64_resp,
            expected_audience="https://suspensionlab.pro/saml/metadata",
            expected_recipient="https://suspensionlab.pro/saml/acs",
            idp_x509_cert_pem=TEST_IDP_CERT_PEM,
        )


@pytest.mark.asyncio
async def test_saml_acs_endpoint_flow_and_jit_provisioning():
    """End-to-end test of POST /api/v1/auth/saml/acs with JIT user provisioning."""
    async with SessionLocal() as db:
        org_id = uuid.uuid4()
        org_slug = f"saml-oem-{uuid.uuid4().hex[:6]}"
        sp_entity = f"https://suspensionlab.pro/saml/sp/{org_slug}"
        acs_url = "http://test/api/v1/auth/saml/acs"
        idp_entity = "https://idp.enterprise-oem.com"

        org = Organization(
            id=org_id,
            name="Enterprise OEM",
            slug=org_slug,
            plan="ENTERPRISE",
            saml_enabled=True,
            saml_idp_entity_id=idp_entity,
            saml_idp_sso_url="https://idp.enterprise-oem.com/sso",
            saml_sp_entity_id=sp_entity,
            saml_idp_x509_cert=TEST_IDP_CERT_PEM,
        )
        db.add(org)
        await db.commit()

    relay_state = generate_relay_state(org_id=str(org_id), return_to="/dashboard")

    assertion_id = f"ASSERT_{uuid.uuid4().hex}"
    test_email = f"saml_user_{uuid.uuid4().hex[:6]}@enterprise-oem.com"
    saml_xml = _build_test_saml_response_xml(
        assertion_id=assertion_id,
        issuer=idp_entity,
        audience=sp_entity,
        recipient=acs_url,
        name_id=test_email,
        email=test_email,
        name="Elena Rossi",
    )
    saml_b64 = base64.b64encode(saml_xml.encode()).decode()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Submit SAMLResponse to ACS
        res = await client.post(
            "/api/v1/auth/saml/acs",
            data={
                "SAMLResponse": saml_b64,
                "RelayState": relay_state,
            },
            follow_redirects=False,
        )

        assert res.status_code == 302
        assert "/dashboard" in res.headers.get("location", "")
        assert "sl_token=" in res.headers.get("set-cookie", "")

    # Verify user was provisioned JIT in database
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == test_email))).scalar_one_or_none()
        assert user is not None
        assert user.name == "Elena Rossi"
        assert user.organization_id == org_id
        assert user.auth_provider == "saml"


def test_defusedxml_hard_dependency_fail_closed(monkeypatch):
    """Verify SAML fails closed with RuntimeError if defusedxml is missing (preventing XXE downgrade)."""
    import sys
    import importlib

    # Mock defusedxml as unimportable
    monkeypatch.setitem(sys.modules, "defusedxml", None)
    monkeypatch.setitem(sys.modules, "defusedxml.ElementTree", None)

    # Reloading saml module must raise RuntimeError rather than falling back to unsafe xml.etree
    with pytest.raises(RuntimeError, match="CRITICAL: 'defusedxml' is required"):
        import suspensionlab.backend.security.saml as saml_mod
        importlib.reload(saml_mod)

    # Clean up and reload properly
    monkeypatch.undo()
    import suspensionlab.backend.security.saml as saml_mod
    importlib.reload(saml_mod)


def test_saml_unsigned_assertion_rejected():
    """Unsigned assertions must strictly fail closed."""
    xml = _build_test_saml_response_xml(
        assertion_id=f"ASSERT_{uuid.uuid4().hex}",
        issuer="https://idp.example.com",
        audience="https://suspensionlab.pro/saml/metadata",
        recipient="https://suspensionlab.pro/saml/acs",
        name_id="user@example.com",
        email="user@example.com",
        sign=False,
    )
    b64_resp = base64.b64encode(xml.encode()).decode()
    with pytest.raises(ValueError, match="lacks required XMLDSig cryptographic signature"):
        parse_and_validate_saml_response(
            saml_response_b64=b64_resp,
            expected_audience="https://suspensionlab.pro/saml/metadata",
            expected_recipient="https://suspensionlab.pro/saml/acs",
            idp_x509_cert_pem=TEST_IDP_CERT_PEM,
        )


def test_saml_missing_idp_cert_rejected():
    """Omitting IdP X.509 certificate must strictly fail closed."""
    xml = _build_test_saml_response_xml(
        assertion_id=f"ASSERT_{uuid.uuid4().hex}",
        issuer="https://idp.example.com",
        audience="https://suspensionlab.pro/saml/metadata",
        recipient="https://suspensionlab.pro/saml/acs",
        name_id="user@example.com",
        email="user@example.com",
    )
    b64_resp = base64.b64encode(xml.encode()).decode()
    with pytest.raises(ValueError, match="Missing IdP X.509 certificate"):
        parse_and_validate_saml_response(
            saml_response_b64=b64_resp,
            expected_audience="https://suspensionlab.pro/saml/metadata",
            expected_recipient="https://suspensionlab.pro/saml/acs",
            idp_x509_cert_pem=None,
        )

