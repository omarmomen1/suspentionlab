"""
tests/test_retention_and_pii_anonymization.py
=============================================
SuspensionLab PRO — Retention Policy Purge & GDPR PII Anonymization vs Engineering Preservation Tests.
"""
import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.organization import Organization
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.user_api_key import UserApiKey
from suspensionlab.backend.database.models.user_session import UserSession
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.session import SimSession
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.audit import AuditLog, EngineeringAuditLog
from suspensionlab.backend.services.retention_service import (
    anonymize_user_pii,
    execute_retention_purge,
)
from suspensionlab.backend.security.jwt_utils import create_access_token, hash_password


@pytest.mark.asyncio
async def test_pii_anonymization_preserves_engineering_provenance():
    """
    CRITICAL COMPLIANCE TEST:
    Verify that GDPR/CCPA user erasure completely anonymizes personal identity and revokes credentials,
    WHILE PRESERVING engineering simulation records, physics provenance, and kinematics calculations.
    """
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    user_email = f"lead_aerodynamicist_{uuid.uuid4().hex[:6]}@f1-team.com"
    prof_id = uuid.uuid4()
    sim_session_id = uuid.uuid4()
    eng_audit_id = uuid.uuid4()

    async with SessionLocal() as db:
        org = Organization(id=org_id, name="F1 Scuderia", slug=f"f1-{uuid.uuid4().hex[:6]}")
        db.add(org)

        user = User(
            id=user_id,
            email=user_email,
            name="Jean Alesi",
            password_hash=hash_password("SuperSecret123!"),
            organization_id=org_id,
            org_role="ORG_ADMIN",
            external_id="okta-sub-12345",
            billing_customer_id="cus_stripe_98765",
            onboarding_complete=True,
        )
        db.add(user)

        # Add User API Key & User Session (personal credentials)
        api_key = UserApiKey(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Personal CLI Key",
            key_prefix="slk_personal",
            key_hash=hash_password("slk_personal_12345678"),
        )
        user_session = UserSession(
            id=uuid.uuid4(),
            user_id=user_id,
            jti=f"jti_{uuid.uuid4().hex}",
            user_agent="Mozilla/5.0 Ubuntu Workstation",
            device_type="Desktop",
            ip_address="192.168.1.50",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add_all([api_key, user_session])

        # Add Engineering Records created by this user
        profile = VehicleProfile(
            id=prof_id,
            user_id=user_id,
            name="F1 2026 High Downforce Aero Setup",
            vehicle_type="FULL_CAR",
            params={"mass_kg": 798.0, "k_spring": 45000.0, "c_damper": 2200.0},
        )
        sim_session = SimSession(
            id=sim_session_id,
            owner_id=user_id,
            name="Monza Low Downforce Baseline",
        )
        eng_audit = EngineeringAuditLog(
            id=eng_audit_id,
            user_id=user_id,
            organization_id=org_id,
            simulation_type="full_car_7dof",
            vehicle_ref="F1 2026 High Downforce Aero Setup",
            setup_version="v2.4.1",
            software_version="2.0.0",
            physics_version="full-car-rk4-v3",
            simulation_version="1.0.0",
            params_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            result_hash="ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
        )
        db.add_all([profile, sim_session, eng_audit])
        await db.commit()

    # Perform PII Anonymization in a fresh session
    async with SessionLocal() as db:
        result = await anonymize_user_pii(db, user_id=user_id, reason="GDPR Right to Erasure")
        assert result["status"] == "success"
        assert result["pii_erased"] is True
        assert result["engineering_records_preserved"] is True

    # Verification phase: Inspect database state
    async with SessionLocal() as db:
        # 1. User PII is completely erased and replaced with non-identifying pseudonym
        updated_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        assert updated_user.email != user_email
        assert updated_user.email.startswith("anonymized-")
        assert updated_user.email.endswith("@redacted.internal")
        assert updated_user.name == "Anonymized Engineer"
        assert updated_user.external_id is None
        assert updated_user.billing_customer_id is None
        assert updated_user.deleted_at is not None

        # 2. Personal API keys and sessions are purged
        keys = (await db.execute(select(UserApiKey).where(UserApiKey.user_id == user_id))).scalars().all()
        assert len(keys) == 0

        sessions = (await db.execute(select(UserSession).where(UserSession.user_id == user_id))).scalars().all()
        assert len(sessions) == 0

        # 3. CRITICAL: Engineering records and physics audit calculations are 100% PRESERVED!
        saved_profile = (await db.execute(select(VehicleProfile).where(VehicleProfile.id == prof_id))).scalar_one_or_none()
        assert saved_profile is not None
        assert saved_profile.name == "F1 2026 High Downforce Aero Setup"
        assert saved_profile.params["mass_kg"] == 798.0

        saved_sim_session = (await db.execute(select(SimSession).where(SimSession.id == sim_session_id))).scalar_one_or_none()
        assert saved_sim_session is not None
        assert saved_sim_session.name == "Monza Low Downforce Baseline"

        saved_eng_audit = (await db.execute(select(EngineeringAuditLog).where(EngineeringAuditLog.id == eng_audit_id))).scalar_one_or_none()
        assert saved_eng_audit is not None
        assert saved_eng_audit.physics_version == "full-car-rk4-v3"
        assert saved_eng_audit.params_hash == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        # 4. Audit trail confirms PII erasure completed
        audit = (await db.execute(select(AuditLog).where(AuditLog.event == "PII_ERASURE_COMPLETED", AuditLog.user_id == user_id))).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_retention_purge_workflow_and_api_endpoint():
    """Verify retention purge identifies expired records and executes cleanup."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    admin_email = f"admin_{uuid.uuid4().hex[:6]}@hypercar.com"
    expired_prof_id = uuid.uuid4()

    async with SessionLocal() as db:
        org = Organization(
            id=org_id,
            name="Hypercar Lab",
            slug=f"hypercar-{uuid.uuid4().hex[:6]}",
            data_retention_days=30,
            telemetry_retention_days=7,
        )
        user = User(
            id=user_id,
            email=admin_email,
            password_hash=hash_password("Pass123!"),
            organization_id=org_id,
            org_role="ORG_ADMIN",
            plan="ENTERPRISE",
            onboarding_complete=True,
        )
        db.add_all([org, user])

        # Soft-deleted profile expired 60 days ago (> 30 days retention policy)
        expired_prof = VehicleProfile(
            id=expired_prof_id,
            user_id=user_id,
            name="Deprecated Concept v1",
            params={"m_s": 250.0},
            deleted_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        db.add(expired_prof)
        await db.commit()

    token = create_access_token({"sub": str(user_id), "email": admin_email, "organization_id": str(org_id)})

    # Call purge endpoint via API
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/compliance/retention/purge",
            json={"organization_id": str(org_id), "dry_run": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["summary"]["purged_vehicle_profiles"] >= 1

    # Confirm expired profile was purged
    async with SessionLocal() as db:
        check = (await db.execute(select(VehicleProfile).where(VehicleProfile.id == expired_prof_id))).scalar_one_or_none()
        assert check is None
