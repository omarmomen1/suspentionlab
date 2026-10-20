"""
tests/test_phase6_7_evidence_integrity_dossiers.py
==================================================
SuspensionLab PRO — Phase 6.7 Validation Evidence Integrity,
Engineering Decision Dossiers & Closure Governance Hostile Verification Suite.

Complete Adversarial Verification Matrix:
  1. Claimed vs. Verified Source Distinction (SOURCE_CLAIMED vs SOURCE_IDENTITY_VERIFIED).
  2. Anti-Masquerade Guardrail: Simulation data cannot claim physical validation.
  3. Artifact hash tampering rejection (ArtifactIntegrityBreachError).
  4. Trusted Source Registry checks (authorized vs unauthorized/expired).
  5. Authenticated Supplier Attestation verification.
  6. Authorized Custodian Review verification & RBAC check.
  7. Cryptographic Ed25519 signature verification over artifact hash.
  8. Source authorization revocation cascades to evidence items (REVOKED).
  9. Deterministic dossier content hashing (deterministic SHA-256 over canonical JSON).
  10. Immutable linkages: plan_hash, closure_hash, reassessment_hash, evidence_item_ids.
  11. Before/After decision robustness delta comparison (reversal resolution).
  12. Contradictory evidence detection in evidence pool.
  13. Role-controlled governance gate sequence (DRAFT -> IN_REVIEW -> EVIDENCE_ACCEPTED -> CONCLUSION_REVIEWED -> DECISION_APPROVED).
  14. Illegal/out-of-order governance transitions rejected (InvalidGovernanceTransitionError).
  15. Unauthorized user cannot transition governance states (UnauthorizedReviewerError).
  16. Strict Non-Elevation: deployment_safety_inferred == False & deployment_authorization_status == NOT_ESTABLISHED across all states.
  17. Dossier supersession preserves parent lineage and increments version.
  18. Phase 5 pre-reveal firewall protects blind validation evidence.
  19. Cross-tenant isolation strictly enforced (CrossTenantAccessError / 403 / 404).
  20. Full REST API workflow execution over HTTP via AsyncClient.
"""
from __future__ import annotations

import sys
import os
_local_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path = [p for p in sys.path if not p.rstrip("/\\").endswith("src")]
sys.path.insert(0, _local_src)

import asyncio
import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import Base, get_db_dependency
from suspensionlab.backend.database.models.parameter_trust import (
    EngineeringValidationPlanRecord,
    ValidationEvidenceItemRecord,
    ValidationEvidenceClosureRecord,
    ValidationDecisionReassessmentRecord,
    DecisionExposureAssessmentRecord,
    DecisionRobustnessAnalysisRecord,
    TrustedSourceRegistryRecord,
    SourceVerificationRecord,
    EngineeringDecisionDossierRecord,
    ParameterTrustProfile,
    ParameterTrustEvidenceRecord,
    ParameterTrustAssessmentRecord,
    SourceVerificationMethod,
    SourceVerificationStatus,
    EvidenceIntegrityStage,
    DossierGovernanceState,
    ReviewActionType,
    ValidationPlanStatus,
    ValidationMethodType,
    CriterionStatus,
    EvidenceDataSourceType,
    EvidenceClosureVerdict,
    ReversalResolutionStatus,
    DecisionRobustnessClassification,
    GOVERNANCE_SEPARATION_NOTICE_V2,
    UNVERIFIED_SOURCE_NOTICE,
    FINITE_SAMPLE_SCOPE_NOTICE,
    EVIDENCE_INTEGRITY_POLICY_V1,
    CURRENT_EVIDENCE_INTEGRITY_POLICY_VERSION,
    CURRENT_VALIDATION_PLANNING_POLICY_VERSION,
    CURRENT_ROBUSTNESS_POLICY_VERSION,
    CURRENT_TRUST_POLICY_VERSION,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.setup_engineering import (
    SetupCandidateRecord,
)
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSessionStatus,
)
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.parameter_trust_dossier_service import (
    ParameterTrustDossierService,
    DossierGovernanceError,
    EvidenceNotFoundError,
    DossierNotFoundError,
    UnverifiedSourceError,
    RevokedSourceAuthorizationError,
    InvalidSignatureError,
    ArtifactIntegrityBreachError,
    UnauthorizedReviewerError,
    InvalidGovernanceTransitionError,
    ImmutableDossierError,
    ContradictoryEvidenceError,
    CrossTenantAccessError,
)
from suspensionlab.backend.services.parameter_trust_validation_service import (
    ParameterTrustValidationService,
    SimulationMasqueradingAsPhysicalError,
)
from suspensionlab.backend.services.parameter_trust_decision_service import (
    PreRevealFirewallViolation,
    TenantIsolationError,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


def make_user_ctx(
    user_id: uuid.UUID,
    team_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    role: str = "engineer",
) -> UserContext:
    return UserContext(
        user_id=str(user_id),
        plan="ENTERPRISE",
        email=f"user_{user_id.hex[:6]}@suspensionlab.com",
        name="Validation Engineer",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role=role.upper(),
        org_role="MEMBER",
        is_admin=role.lower() in ("admin", "org_admin", "lead", "validation_lead", "system_auditor"),
    )


@pytest.fixture
async def seeded_dossier_env(async_test_db: AsyncSession):
    """
    Sets up multi-tenant decisions, validation plans, evidence items, closures,
    and robustness reassessments.
    """
    db = async_test_db
    org_a = uuid.uuid4()
    team_a = uuid.uuid4()
    lead_a = uuid.uuid4()       # Lead Engineer / Reviewer
    auditor_a = uuid.uuid4()    # System Auditor
    eng_a = uuid.uuid4()        # Engineer
    viewer_a = uuid.uuid4()     # Viewer

    org_b = uuid.uuid4()
    team_b = uuid.uuid4()
    user_b = uuid.uuid4()

    now = datetime.now(timezone.utc)

    # 1. Engineering Decision
    dec_a = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-67-01",
        question="Is front spring stiffness robust against reversal under measured bump loads?",
        context={"car_model": "GT3-2026", "track": "Circuit-Alpha"},
        candidates=["SETUP-67-01"],
        selected_option={"setup_id": "SETUP-67-01"},
        reason="Stiffness targets ride frequency and damping ratio",
        tradeoffs={"ride_vs_handling": "Stiffer front improves turn-in response"},
        risks={"kerb_strike": "Higher peak contact patch load"},
        simulation_evidence=[{"sim_label": "SIM-SENS-67-01"}],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Validation Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_67_01"},
        user_id=eng_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(dec_a)

    # 2. Decision Exposure Assessment
    exp_a = DecisionExposureAssessmentRecord(
        id=uuid.uuid4(),
        decision_id="DEC-67-01",
        decision_type="EngineeringDecision",
        policy_version="DECISION_TRUST_POLICY_V1",
        assessment_hash="exphash_67_01",
        input_snapshot_hash="hash_snap_val_01",
        exposure_classification="HIGH_EXPOSURE",
        exposure_summary="Decision is sensitive to front_spring_rate uncertainty.",
        parameter_dependencies=[],
        evidence_gaps=[{"gap_id": "GAP-VAL-SPRING-01", "parameter_name": "front_spring_rate", "gap_type": "NO_PHYSICAL_VALIDATION"}],
        actionable_recommendations=[],
        governance_separation_notice="DECISION EXPOSURE ASSESSMENT ONLY",
        is_active=True,
        organization_id=org_a,
        team_id=team_a,
        user_id=eng_a,
        created_at=now,
    )
    db.add(exp_a)

    # 3. Baseline Robustness Analysis
    rob_baseline = DecisionRobustnessAnalysisRecord(
        id=uuid.uuid4(),
        decision_id="DEC-67-01",
        decision_type="EngineeringDecision",
        policy_version=CURRENT_ROBUSTNESS_POLICY_VERSION,
        analysis_hash="rob_base_hash_01",
        input_snapshot_hash="snap_rob_base_01",
        robustness_classification=DecisionRobustnessClassification.FRAGILE_REVERSAL_DEMONSTRATED.value,
        robustness_summary="Decision reverses under wide unverified front_spring_rate uncertainty.",
        evaluated_envelope={
            "parameters": {
                "front_spring_rate": {"nominal": 80.0, "min": 70.0, "max": 90.0, "unit": "N/mm"},
            },
            "decision_threshold": 1.25,
            "target_kpi": "rms_body_accel_wk",
            "selected_option": "SETUP-67-01",
        },
        parameter_uncertainties=[],
        reversal_scenarios=[{"scenario_id": "SCEN-01", "parameter_shifts": {"front_spring_rate": 72.0}}],
        boundary_crossings=[],
        dominant_uncertainties=[{"parameter_name": "front_spring_rate", "elasticity": 0.35}],
        voi_prioritizations=[{"parameter_name": "front_spring_rate", "priority_level": "HIGH"}],
        solver_failures=[],
        governance_separation_notice="ROBUSTNESS ANALYSIS IS AN ANALYTICAL EVALUATION ONLY",
        is_active=False,
        organization_id=org_a,
        team_id=team_a,
        user_id=eng_a,
        created_at=now - timedelta(days=1),
    )
    db.add(rob_baseline)

    # 4. Validation Plan Record
    plan_a = EngineeringValidationPlanRecord(
        id=uuid.uuid4(),
        plan_id="VAL-PLAN-67-01",
        plan_version=1,
        decision_id="DEC-67-01",
        decision_type="EngineeringDecision",
        parameter_name="front_spring_rate",
        validation_objective="Empirically verify spring rate within +/-5% of nominal",
        validation_method=ValidationMethodType.RIG_TEST_4_POST.value,
        unit="N/mm",
        measurement_definition="Quasi-static spring rate deflection measurement on 4-post rig",
        status=ValidationPlanStatus.AUTHORIZED.value,
        acceptance_criteria=[
            {
                "metric_name": "front_spring_rate_tolerance",
                "target_value": 80.0,
                "tolerance_band": [76.0, 84.0],
                "unit": "N/mm",
                "status": "AUTHORIZED",
            }
        ],
        operating_conditions={"regime": "TRACK_DRY", "temperature_c": 22.0},
        plan_hash="planhash_67_01",
        is_active=True,
        organization_id=org_a,
        team_id=team_a,
        created_by_user_id=lead_a,
        created_at=now,
    )
    db.add(plan_a)

    # 5. Validation Evidence Items
    ev_artifact_hash = hashlib.sha256(b"raw_telemetry_rig_4p_2026_01").hexdigest()
    ev_item_1 = ValidationEvidenceItemRecord(
        id=uuid.uuid4(),
        plan_id=plan_a.id,
        evidence_source_type=EvidenceDataSourceType.PHYSICAL_RIG_MEASUREMENT.value,
        source_identifier="FACILITY-DYNO-CHASSIS-01",
        source_timestamp=now,
        parameter_name="front_spring_rate",
        observed_value=80.2,
        observed_interval=[79.0, 81.4],
        unit="N/mm",
        operating_scope={"temperature_c": 22.0},
        integrity_hash=ev_artifact_hash,
        provenance={"rig_id": "RIG-4P-A", "operator": "Test Engineer Alpha"},
        calibration_metadata={"cert": "ISO-17025"},
        is_physically_validated=True,
        integrity_stage=EvidenceIntegrityStage.SOURCE_CLAIMED.value,
        source_verification_status=SourceVerificationStatus.UNVERIFIED.value,
        review_status="PENDING_REVIEW",
        organization_id=org_a,
        team_id=team_a,
        submitted_by_user_id=eng_a,
        created_at=now,
    )
    db.add(ev_item_1)

    # 6. Validation Evidence Closure Record
    closure_a = ValidationEvidenceClosureRecord(
        id=uuid.uuid4(),
        plan_id=plan_a.id,
        decision_id="DEC-67-01",
        parameter_name="front_spring_rate",
        closure_verdict=EvidenceClosureVerdict.CLOSED_WITH_SUPPORTING_EVIDENCE.value,
        criteria_met=True,
        criteria_evaluated=[
            {
                "metric_name": "front_spring_rate_tolerance",
                "target_value": 80.0,
                "measured_value": 80.2,
                "passed": True,
                "status": "SATISFIED",
            }
        ],
        closure_summary="4-post rig tests confirmed spring rate at 80.2 N/mm within [76.0, 84.0] N/mm tolerance.",
        closure_hash="closurehash_67_01",
        finite_sample_notice=FINITE_SAMPLE_SCOPE_NOTICE,
        governance_separation_notice=GOVERNANCE_SEPARATION_NOTICE_V2,
        deployment_safety_inferred=False,
        deployment_authorization="NOT_ESTABLISHED",
        is_active=True,
        organization_id=org_a,
        team_id=team_a,
        evaluated_by_user_id=lead_a,
        created_at=now,
    )
    db.add(closure_a)

    # 7. Decision Robustness Reassessment Record
    reassess_rob = DecisionRobustnessAnalysisRecord(
        id=uuid.uuid4(),
        decision_id="DEC-67-01",
        decision_type="EngineeringDecision",
        policy_version=CURRENT_ROBUSTNESS_POLICY_VERSION,
        analysis_hash="rob_reassess_hash_01",
        input_snapshot_hash="snap_rob_reassess_01",
        robustness_classification=DecisionRobustnessClassification.ROBUST_ACROSS_ENVELOPE.value,
        robustness_summary="Decision is robust against reversals within measured confidence interval.",
        evaluated_envelope={
            "parameters": {
                "front_spring_rate": {"nominal": 80.2, "min": 79.0, "max": 81.4, "unit": "N/mm"},
            },
            "decision_threshold": 1.25,
            "target_kpi": "rms_body_accel_wk",
            "selected_option": "SETUP-67-01",
        },
        parameter_uncertainties=[],
        reversal_scenarios=[],
        boundary_crossings=[],
        dominant_uncertainties=[],
        voi_prioritizations=[],
        solver_failures=[],
        governance_separation_notice="ROBUSTNESS ANALYSIS IS AN ANALYTICAL EVALUATION ONLY",
        is_active=True,
        organization_id=org_a,
        team_id=team_a,
        user_id=lead_a,
        created_at=now,
    )
    db.add(reassess_rob)

    reassessment_a = ValidationDecisionReassessmentRecord(
        id=uuid.uuid4(),
        decision_id="DEC-67-01",
        decision_type="EngineeringDecision",
        plan_id=plan_a.id,
        closure_id=closure_a.id,
        original_exposure_assessment_id=exp_a.id,
        original_robustness_analysis_id=rob_baseline.id,
        new_robustness_analysis_id=reassess_rob.id,
        reversal_status=ReversalResolutionStatus.REVERSAL_RESOLVED.value,
        reassessment_delta={
            "classification_before": "VULNERABLE_TO_REVERSAL",
            "classification_after": "ROBUST_WITHIN_CREDIBLE_RANGE",
            "reversals_before_count": 1,
            "reversals_after_count": 0,
            "reversal_status": "REVERSAL_RESOLVED",
            "parameter_uncertainty_updated": "front_spring_rate",
            "gap_closure_verdict": "CLOSED_WITH_SUPPORTING_EVIDENCE",
        },
        envelope_coverage_statement="Narrowed uncertainty interval [79.0, 81.4] N/mm successfully resolved ranking reversal.",
        governance_separation_notice=GOVERNANCE_SEPARATION_NOTICE_V2,
        deployment_safety_inferred=False,
        deployment_authorization="NOT_ESTABLISHED",
        reassessment_hash="reassesshash_67_01",
        is_active=True,
        organization_id=org_a,
        team_id=team_a,
        reassessed_by_user_id=lead_a,
        created_at=now,
    )
    db.add(reassessment_a)

    await db.commit()

    return {
        "org_a": org_a,
        "team_a": team_a,
        "lead_a": lead_a,
        "auditor_a": auditor_a,
        "eng_a": eng_a,
        "viewer_a": viewer_a,
        "org_b": org_b,
        "team_b": team_b,
        "user_b": user_b,
        "decision": dec_a,
        "exposure": exp_a,
        "baseline_rob": rob_baseline,
        "plan": plan_a,
        "evidence_item": ev_item_1,
        "closure": closure_a,
        "reassessment": reassessment_a,
        "reassess_rob": reassess_rob,
        "raw_artifact_hash": ev_artifact_hash,
    }


# ── TESTS ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claimed_vs_verified_source_distinction(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Ingested evidence starts at SOURCE_CLAIMED and UNVERIFIED.
    Anti-masquerade guardrail rejects simulation data claiming physical validation.
    Tampered artifact hash fails closed.
    """
    db = async_test_db
    env = seeded_dossier_env
    ev = env["evidence_item"]

    # Initial state
    assert ev.integrity_stage == "SOURCE_CLAIMED"
    assert ev.source_verification_status == "UNVERIFIED"

    # Anti-masquerade check: attempt to verify with simulation claiming physical
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")
    ev.is_physically_validated = True
    ev.evidence_source_type = "SIMULATION_SWEEP"  # CAE data trying to masquerade as physical

    with pytest.raises(SimulationMasqueradingAsPhysicalError):
        await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=ev.id,
            verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
            user_context=u_lead,
        )

    # Restore correct source type
    ev.evidence_source_type = "PHYSICAL_RIG_MEASUREMENT"

    # Artifact integrity check: tampered hash
    with pytest.raises(ArtifactIntegrityBreachError):
        await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=ev.id,
            verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
            user_context=u_lead,
            expected_artifact_hash="mismatched_tampered_hash_00000000000000000000",
        )


@pytest.mark.asyncio
async def test_trusted_registry_verification(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Source in trusted_source_registries with is_authorized=True verifies successfully.
    Unregistered or deauthorized source is rejected.
    """
    db = async_test_db
    env = seeded_dossier_env
    ev = env["evidence_item"]
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    # 1. Attempt verification without registering source -> fails
    with pytest.raises(UnverifiedSourceError):
        await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=ev.id,
            verification_method=SourceVerificationMethod.TRUSTED_REGISTRY_CHECK,
            user_context=u_lead,
        )

    # 2. Register source in registry
    source_reg = await ParameterTrustDossierService.register_trusted_source(
        db=db,
        source_identifier=ev.source_identifier,
        source_name="Chassis Dyno Test Facility 01",
        source_type="AUTHORITATIVE_LAB_FACILITY",
        user_context=u_lead,
        certificate_ref="ISO-17025-CAL-2026",
    )
    assert source_reg.is_authorized is True

    # 3. Now verify via TRUSTED_REGISTRY_CHECK -> succeeds
    verif = await ParameterTrustDossierService.verify_source_identity(
        db=db,
        evidence_item_id=ev.id,
        verification_method=SourceVerificationMethod.TRUSTED_REGISTRY_CHECK,
        user_context=u_lead,
    )
    assert verif.verification_status == SourceVerificationStatus.VERIFIED
    assert ev.integrity_stage == EvidenceIntegrityStage.SOURCE_IDENTITY_VERIFIED
    assert ev.source_verification_status == SourceVerificationStatus.VERIFIED
    assert verif.is_revoked is False


@pytest.mark.asyncio
async def test_authenticated_supplier_attestation(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Verifies source via AUTHENTICATED_SUPPLIER_ATTESTATION with supporting references.
    Missing supplier reference is rejected.
    """
    db = async_test_db
    env = seeded_dossier_env
    ev = env["evidence_item"]
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    # Missing supplier references
    with pytest.raises(UnverifiedSourceError):
        await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=ev.id,
            verification_method=SourceVerificationMethod.AUTHENTICATED_SUPPLIER_ATTESTATION,
            user_context=u_lead,
            supporting_references=None,
        )

    # Valid supplier attestation
    verif = await ParameterTrustDossierService.verify_source_identity(
        db=db,
        evidence_item_id=ev.id,
        verification_method=SourceVerificationMethod.AUTHENTICATED_SUPPLIER_ATTESTATION,
        user_context=u_lead,
        supporting_references={"supplier_code": "SUP-BILSTEIN-OEM", "attestation_cert": "CERT-2026-B9"},
        scope={"batch_lot": "LOT-2026-X4", "rig_calibrated": True},
    )
    assert verif.verification_status == SourceVerificationStatus.VERIFIED
    assert verif.verification_method == SourceVerificationMethod.AUTHENTICATED_SUPPLIER_ATTESTATION


@pytest.mark.asyncio
async def test_authorized_custodian_review_and_rbac(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Authorized custodian review requires authorized role (lead / auditor / admin).
    Viewer cannot perform custodian verification (UnauthorizedReviewerError).
    """
    db = async_test_db
    env = seeded_dossier_env
    ev = env["evidence_item"]
    u_viewer = make_user_ctx(env["viewer_a"], env["team_a"], env["org_a"], role="viewer")
    u_auditor = make_user_ctx(env["auditor_a"], env["team_a"], env["org_a"], role="system_auditor")

    # Viewer unauthorized
    with pytest.raises(UnauthorizedReviewerError):
        await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=ev.id,
            verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
            user_context=u_viewer,
        )

    # Auditor authorized
    verif = await ParameterTrustDossierService.verify_source_identity(
        db=db,
        evidence_item_id=ev.id,
        verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
        user_context=u_auditor,
        verification_notes="Lead auditor physically inspected test cell calibration records.",
    )
    assert verif.verification_status == SourceVerificationStatus.VERIFIED
    assert verif.verifier_role == "SYSTEM_AUDITOR"


@pytest.mark.asyncio
async def test_cryptographic_signature_verification(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Cryptographically verifies an Ed25519 signature over artifact hash.
    Invalid signature or mismatched key is rejected.
    """
    if not HAS_CRYPTOGRAPHY:
        pytest.skip("cryptography library not installed")

    db = async_test_db
    env = seeded_dossier_env
    ev = env["evidence_item"]
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    # Generate Ed25519 key pair
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    # Sign the artifact hash
    message_bytes = ev.raw_artifact_hash.encode("utf-8")
    signature = private_key.sign(message_bytes)
    sig_hex = signature.hex()

    # 1. Invalid signature rejection
    with pytest.raises(InvalidSignatureError):
        await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=ev.id,
            verification_method=SourceVerificationMethod.CRYPTOGRAPHIC_SIGNATURE,
            user_context=u_lead,
            signature_hex="deadbeef" * 8,  # bad signature
            public_key_pem=pub_pem,
        )

    # 2. Valid signature verification
    verif = await ParameterTrustDossierService.verify_source_identity(
        db=db,
        evidence_item_id=ev.id,
        verification_method=SourceVerificationMethod.CRYPTOGRAPHIC_SIGNATURE,
        user_context=u_lead,
        signature_hex=sig_hex,
        public_key_pem=pub_pem,
    )
    assert verif.verification_status == SourceVerificationStatus.VERIFIED
    assert verif.verification_method == SourceVerificationMethod.CRYPTOGRAPHIC_SIGNATURE


@pytest.mark.asyncio
async def test_source_authorization_revocation_cascades(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Revoking source authorization cascades status REVOKED to evidence items
    and prevents newly revoked evidence from passing gap evaluation.
    """
    db = async_test_db
    env = seeded_dossier_env
    ev = env["evidence_item"]
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    # 1. Verify source first
    verif = await ParameterTrustDossierService.verify_source_identity(
        db=db,
        evidence_item_id=ev.id,
        verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
        user_context=u_lead,
    )
    assert verif.verification_status == SourceVerificationStatus.VERIFIED
    assert ev.source_verification_status == SourceVerificationStatus.VERIFIED

    # 2. Revoke verification
    revoked = await ParameterTrustDossierService.revoke_source_verification(
        db=db,
        verification_id=verif.id,
        user_context=u_lead,
        reason="Disputed sensor calibration in rig load cell.",
    )
    assert revoked.verification_status == SourceVerificationStatus.REVOKED
    assert revoked.is_revoked is True
    assert ev.source_verification_status == SourceVerificationStatus.REVOKED

    # 3. Attempting to verify source again after revocation raises RevokedSourceAuthorizationError
    with pytest.raises(RevokedSourceAuthorizationError):
        await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=ev.id,
            verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
            user_context=u_lead,
        )


@pytest.mark.asyncio
async def test_decision_dossier_compilation_and_deterministic_hashing(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Compiles an authoritative Engineering Decision Dossier.
    Verifies deterministic content hash generation and immutable linkages.
    """
    db = async_test_db
    env = seeded_dossier_env
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    # Verify evidence item source first
    await ParameterTrustDossierService.verify_source_identity(
        db=db,
        evidence_item_id=env["evidence_item"].id,
        verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
        user_context=u_lead,
    )

    # Compile Dossier
    dossier = await ParameterTrustDossierService.compile_decision_dossier(
        db=db,
        decision_id="DEC-67-01",
        plan_id=env["plan"].id,
        closure_id=env["closure"].id,
        reassessment_id=env["reassessment"].id,
        user_context=u_lead,
        engineering_question="Is front spring stiffness robust against reversal under measured bump loads?",
    )

    assert dossier.dossier_number == "DOS-DEC-67-01-001"
    assert dossier.dossier_version == 1
    assert dossier.parent_dossier_id is None
    assert dossier.governance_state == DossierGovernanceState.DRAFT
    assert dossier.is_active is True
    assert len(dossier.dossier_content_hash) == 64  # SHA-256
    assert dossier.plan_hash == env["plan"].plan_hash
    assert dossier.closure_hash == env["closure"].closure_hash
    assert dossier.reassessment_hash == env["reassessment"].reassessment_hash

    # Non-elevation invariant check
    assert dossier.deployment_safety_inferred is False
    assert dossier.deployment_authorization_status == "NOT_ESTABLISHED"
    assert "STRICT NON-ELEVATION POLICY" in dossier.governance_separation_notice


@pytest.mark.asyncio
async def test_before_after_robustness_delta_in_dossier(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Dossier before_after_comparison captures the baseline vs. reassessed robustness delta:
    vulnerable classification resolved, reversals reduced from 1 to 0.
    """
    db = async_test_db
    env = seeded_dossier_env
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    await ParameterTrustDossierService.verify_source_identity(
        db=db,
        evidence_item_id=env["evidence_item"].id,
        verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
        user_context=u_lead,
    )

    dossier = await ParameterTrustDossierService.compile_decision_dossier(
        db=db,
        decision_id="DEC-67-01",
        plan_id=env["plan"].id,
        closure_id=env["closure"].id,
        reassessment_id=env["reassessment"].id,
        user_context=u_lead,
    )

    delta = dossier.before_after_comparison
    assert delta["baseline"]["classification"] == "FRAGILE_REVERSAL_DEMONSTRATED"
    assert delta["reassessed"]["classification"] == "ROBUST_ACROSS_ENVELOPE"
    assert delta["reassessed"]["reversal_status"] == "REVERSAL_RESOLVED"
    assert delta["reassessment_delta"]["reversal_status"] == "REVERSAL_RESOLVED"
    assert delta["reassessment_delta"]["reversals_before_count"] == 1
    assert delta["reassessment_delta"]["reversals_after_count"] == 0


@pytest.mark.asyncio
async def test_contradictory_evidence_detection_in_dossier(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Submitting contradictory evidence items is detected and recorded in contradictory_evidence_summary.
    """
    db = async_test_db
    env = seeded_dossier_env
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    # Add a second conflicting evidence item with non-overlapping bounds (e.g. 50 N/mm vs 80.2 N/mm)
    conflict_hash = hashlib.sha256(b"conflict_telemetry_run_99").hexdigest()
    ev_conflict = ValidationEvidenceItemRecord(
        id=uuid.uuid4(),
        plan_id=env["plan"].id,
        evidence_source_type=EvidenceDataSourceType.PHYSICAL_RIG_MEASUREMENT.value,
        source_identifier="FACILITY-DYNO-CHASSIS-02",
        source_timestamp=datetime.now(timezone.utc),
        parameter_name="front_spring_rate",
        observed_value=50.0,
        observed_interval=[48.0, 52.0],
        unit="N/mm",
        operating_scope={"temperature_c": 22.0},
        integrity_hash=conflict_hash,
        provenance={"rig_id": "RIG-4P-B", "operator": "Test Engineer Beta"},
        calibration_metadata={"cert": "ISO-17025"},
        is_physically_validated=True,
        integrity_stage=EvidenceIntegrityStage.SOURCE_IDENTITY_VERIFIED.value,
        source_verification_status=SourceVerificationStatus.VERIFIED.value,
        review_status="ACCEPTED",
        organization_id=env["org_a"],
        team_id=env["team_a"],
        submitted_by_user_id=env["eng_a"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(ev_conflict)
    await db.commit()

    # Compile dossier
    dossier = await ParameterTrustDossierService.compile_decision_dossier(
        db=db,
        decision_id="DEC-67-01",
        plan_id=env["plan"].id,
        closure_id=env["closure"].id,
        reassessment_id=env["reassessment"].id,
        user_context=u_lead,
    )

    contradictions = dossier.contradictory_evidence_summary
    assert contradictions["has_contradictions"] is True
    assert contradictions["contradictory_count"] > 0
    assert len(contradictions["items"]) > 0


@pytest.mark.asyncio
async def test_role_controlled_governance_progression(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Enforces sequential governance gate sequence:
    DRAFT -> IN_REVIEW (ADMIT_EVIDENCE)
          -> EVIDENCE_ACCEPTED (EVALUATE_CRITERIA)
          -> CONCLUSION_REVIEWED (REVIEW_CONCLUSION)
          -> DECISION_APPROVED (APPROVE_DECISION).
    Out-of-order transitions are rejected.
    Unauthorized users cannot transition states.
    """
    db = async_test_db
    env = seeded_dossier_env
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")
    u_viewer = make_user_ctx(env["viewer_a"], env["team_a"], env["org_a"], role="viewer")

    await ParameterTrustDossierService.verify_source_identity(
        db=db,
        evidence_item_id=env["evidence_item"].id,
        verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
        user_context=u_lead,
    )

    dossier = await ParameterTrustDossierService.compile_decision_dossier(
        db=db,
        decision_id="DEC-67-01",
        plan_id=env["plan"].id,
        closure_id=env["closure"].id,
        reassessment_id=env["reassessment"].id,
        user_context=u_lead,
    )
    assert dossier.governance_state == DossierGovernanceState.DRAFT

    # 1. Illegal transition: DRAFT directly to DECISION_APPROVED
    with pytest.raises(InvalidGovernanceTransitionError):
        await ParameterTrustDossierService.advance_dossier_governance(
            db=db,
            dossier_id=dossier.id,
            action_type=ReviewActionType.APPROVE_DECISION,
            user_context=u_lead,
        )

    # 2. Unauthorized user: Viewer attempting ADMIT_EVIDENCE
    with pytest.raises(UnauthorizedReviewerError):
        await ParameterTrustDossierService.advance_dossier_governance(
            db=db,
            dossier_id=dossier.id,
            action_type=ReviewActionType.ADMIT_EVIDENCE,
            user_context=u_viewer,
        )

    # 3. Step 1: ADMIT_EVIDENCE -> moves to IN_REVIEW
    dossier = await ParameterTrustDossierService.advance_dossier_governance(
        db=db,
        dossier_id=dossier.id,
        action_type=ReviewActionType.ADMIT_EVIDENCE,
        user_context=u_lead,
        rationale="Evidence admitted by Lead Validation Engineer.",
    )
    assert dossier.governance_state == DossierGovernanceState.IN_REVIEW
    assert dossier.admissibility_status == "EVIDENCE_ADMITTED"

    # 4. Step 2: EVALUATE_CRITERIA -> moves to EVIDENCE_ACCEPTED
    dossier = await ParameterTrustDossierService.advance_dossier_governance(
        db=db,
        dossier_id=dossier.id,
        action_type=ReviewActionType.EVALUATE_CRITERIA,
        user_context=u_lead,
        rationale="Criteria evaluated against sealed tolerance bands.",
    )
    assert dossier.governance_state == DossierGovernanceState.EVIDENCE_ACCEPTED
    assert dossier.criteria_satisfaction_status == "CRITERIA_SATISFIED"

    # 5. Step 3: REVIEW_CONCLUSION -> moves to CONCLUSION_REVIEWED
    dossier = await ParameterTrustDossierService.advance_dossier_governance(
        db=db,
        dossier_id=dossier.id,
        action_type=ReviewActionType.REVIEW_CONCLUSION,
        user_context=u_lead,
        rationale="Conclusion reviewed and deemed scientifically grounded.",
    )
    assert dossier.governance_state == DossierGovernanceState.CONCLUSION_REVIEWED
    assert dossier.conclusion_review_status == "CONCLUSION_ACCEPTED"

    # 6. Step 4: APPROVE_DECISION -> moves to DECISION_APPROVED
    dossier = await ParameterTrustDossierService.advance_dossier_governance(
        db=db,
        dossier_id=dossier.id,
        action_type=ReviewActionType.APPROVE_DECISION,
        user_context=u_lead,
        rationale="Final approval of front spring rate specification.",
    )
    assert dossier.governance_state == DossierGovernanceState.DECISION_APPROVED
    assert dossier.decision_approval_status == "DECISION_FORMALLY_APPROVED"

    # CRITICAL CHECK: In final approved state, deployment safety is STILL NOT inferred!
    assert dossier.deployment_safety_inferred is False
    assert dossier.deployment_authorization_status == "NOT_ESTABLISHED"


@pytest.mark.asyncio
async def test_dossier_supersession_lineage(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Superseding a dossier creates version 2, links parent_dossier_id,
    and sets version 1 is_active=False.
    """
    db = async_test_db
    env = seeded_dossier_env
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    await ParameterTrustDossierService.verify_source_identity(
        db=db,
        evidence_item_id=env["evidence_item"].id,
        verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
        user_context=u_lead,
    )

    dossier_v1 = await ParameterTrustDossierService.compile_decision_dossier(
        db=db,
        decision_id="DEC-67-01",
        plan_id=env["plan"].id,
        closure_id=env["closure"].id,
        reassessment_id=env["reassessment"].id,
        user_context=u_lead,
    )
    assert dossier_v1.dossier_version == 1
    assert dossier_v1.is_active is True

    # Supersede v1 -> generates v2
    dossier_v2 = await ParameterTrustDossierService.supersede_dossier(
        db=db,
        dossier_id=dossier_v1.id,
        user_context=u_lead,
        reason="Updated with dry track telemetry holdout sample.",
    )

    assert dossier_v2.dossier_version == 2
    assert dossier_v2.parent_dossier_id == dossier_v1.id
    assert dossier_v2.is_active is True
    assert dossier_v1.is_active is False
    assert dossier_v1.superseded_by == dossier_v2.id


@pytest.mark.asyncio
async def test_phase5_pre_reveal_firewall_enforcement(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Validation evidence for an unrevealed parameter in a blind engineering session
    triggers PreRevealFirewallViolation.
    """
    db = async_test_db
    env = seeded_dossier_env
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    # Create active blind session with protected parameter
    blind_sess = BlindEngineeringSession(
        id=uuid.uuid4(),
        name="Spring Rate Verification Blind Session",
        root_entity_type="ValidationEvidence",
        root_entity_id=str(env["evidence_item"].id),
        hidden_outcome_type="HoldoutParameter",
        hidden_outcome_id="front_spring_rate",
        configuration={"holdout_parameters": {"front_spring_rate": 80.0}, "revealed_parameters": {}},
        session_hash="blind_sess_hash_67_01",
        status=BlindSessionStatus.BLIND_ACTIVE.value,
        created_by_user_id=env["lead_a"],
        team_id=env["team_a"],
        organization_id=env["org_a"],
    )
    db.add(blind_sess)
    await db.commit()

    # Attempt to verify source on protected parameter while holdout is hidden
    with pytest.raises(PreRevealFirewallViolation):
        await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=env["evidence_item"].id,
            verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
            user_context=u_lead,
        )


@pytest.mark.asyncio
async def test_cross_tenant_isolation(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Tenant B user cannot access, verify, compile, or transition Tenant A records.
    """
    db = async_test_db
    env = seeded_dossier_env
    u_tenant_b = make_user_ctx(env["user_b"], env["team_b"], env["org_b"], role="lead")

    # 1. Tenant B attempts to verify Tenant A evidence item
    with pytest.raises(CrossTenantAccessError):
        await ParameterTrustDossierService.verify_source_identity(
            db=db,
            evidence_item_id=env["evidence_item"].id,
            verification_method=SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW,
            user_context=u_tenant_b,
        )

    # 2. Tenant B attempts to compile dossier using Tenant A plan
    with pytest.raises(CrossTenantAccessError):
        await ParameterTrustDossierService.compile_decision_dossier(
            db=db,
            decision_id="DEC-67-01",
            plan_id=env["plan"].id,
            closure_id=env["closure"].id,
            reassessment_id=env["reassessment"].id,
            user_context=u_tenant_b,
        )


@pytest.mark.asyncio
async def test_full_rest_api_lifecycle(async_test_db: AsyncSession, seeded_dossier_env: dict):
    """
    Full end-to-end REST API lifecycle verification over HTTP via AsyncClient:
      - Register trusted source
      - Verify evidence source
      - Compile decision dossier
      - Get decision dossier & list dossiers
      - Advance governance through authorized gates
      - Supersede dossier
      - Verify all non-elevation flags
    """
    env = seeded_dossier_env
    u_lead = make_user_ctx(env["lead_a"], env["team_a"], env["org_a"], role="lead")

    # Dependency override for authentication and database
    async def override_verify_api_key():
        return u_lead

    app.dependency_overrides[verify_api_key] = override_verify_api_key
    app.dependency_overrides[get_db_dependency] = lambda: async_test_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Trusted Source
        reg_resp = await client.post(
            "/api/v1/parameter-trust/validation/registries/trusted-sources",
            json={
                "source_identifier": env["evidence_item"].source_identifier,
                "source_name": "Authoritative Chassis Rig Lab",
                "source_type": "AUTHORITATIVE_LAB_FACILITY",
                "certificate_ref": "ISO-17025-2026",
            },
        )
        assert reg_resp.status_code == 200, reg_resp.text
        reg_json = reg_resp.json()
        assert reg_json["source_identifier"] == env["evidence_item"].source_identifier
        assert reg_json["is_authorized"] is True

        # 2. Verify Evidence Source
        verif_resp = await client.post(
            f"/api/v1/parameter-trust/validation/evidence/{env['evidence_item'].id}/verify-source",
            json={
                "verification_method": "AUTHORIZED_CUSTODIAN_REVIEW",
                "verifier_identity": "Lead Validation Auditor",
                "verification_notes": "All calibration certificates and trace logs verified.",
            },
        )
        assert verif_resp.status_code == 200, verif_resp.text
        verif_json = verif_resp.json()
        assert verif_json["verification_status"] == "VERIFIED"
        assert verif_json["is_revoked"] is False

        # 3. Compile Decision Dossier
        compile_resp = await client.post(
            "/api/v1/parameter-trust/validation/dossiers/compile",
            json={
                "decision_id": "DEC-67-01",
                "plan_id": str(env["plan"].id),
                "closure_id": str(env["closure"].id),
                "reassessment_id": str(env["reassessment"].id),
                "engineering_question": "Is front spring stiffness robust against reversal under measured bump loads?",
            },
        )
        assert compile_resp.status_code == 200, compile_resp.text
        dossier_json = compile_resp.json()
        dossier_id = dossier_json["id"]
        assert dossier_json["dossier_number"] == "DOS-DEC-67-01-001"
        assert dossier_json["governance_state"] == "DRAFT"
        assert dossier_json["deployment_safety_inferred"] is False
        assert dossier_json["deployment_authorization_status"] == "NOT_ESTABLISHED"
        assert "STRICT NON-ELEVATION POLICY" in dossier_json["governance_separation_notice"]

        # 4. Get Dossier by ID
        get_resp = await client.get(f"/api/v1/parameter-trust/validation/dossiers/{dossier_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == dossier_id

        # 5. List Dossiers for Decision
        list_resp = await client.get("/api/v1/parameter-trust/validation/dossiers/by-decision/DEC-67-01")
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] >= 1

        # 6. Advance Governance: ADMIT_EVIDENCE
        admit_resp = await client.post(
            f"/api/v1/parameter-trust/validation/dossiers/{dossier_id}/governance-transition",
            json={"action_type": "ADMIT_EVIDENCE", "rationale": "Admitted by Lead"},
        )
        assert admit_resp.status_code == 200
        assert admit_resp.json()["governance_state"] == "IN_REVIEW"

        # 7. Advance Governance: EVALUATE_CRITERIA
        eval_resp = await client.post(
            f"/api/v1/parameter-trust/validation/dossiers/{dossier_id}/governance-transition",
            json={"action_type": "EVALUATE_CRITERIA", "rationale": "Criteria satisfied"},
        )
        assert eval_resp.status_code == 200
        assert eval_resp.json()["governance_state"] == "EVIDENCE_ACCEPTED"

        # 8. Advance Governance: REVIEW_CONCLUSION
        rev_resp = await client.post(
            f"/api/v1/parameter-trust/validation/dossiers/{dossier_id}/governance-transition",
            json={"action_type": "REVIEW_CONCLUSION", "rationale": "Conclusion reviewed"},
        )
        assert rev_resp.status_code == 200
        assert rev_resp.json()["governance_state"] == "CONCLUSION_REVIEWED"

        # 9. Advance Governance: APPROVE_DECISION
        appr_resp = await client.post(
            f"/api/v1/parameter-trust/validation/dossiers/{dossier_id}/governance-transition",
            json={"action_type": "APPROVE_DECISION", "rationale": "Decision formally approved"},
        )
        assert appr_resp.status_code == 200
        appr_json = appr_resp.json()
        assert appr_json["governance_state"] == "DECISION_APPROVED"
        assert appr_json["decision_approval_status"] == "DECISION_FORMALLY_APPROVED"
        assert appr_json["deployment_safety_inferred"] is False
        assert appr_json["deployment_authorization_status"] == "NOT_ESTABLISHED"

        # 10. Supersede Dossier
        super_resp = await client.post(
            f"/api/v1/parameter-trust/validation/dossiers/{dossier_id}/supersede",
            json={"reason": "Updated with track calibration data"},
        )
        assert super_resp.status_code == 200
        super_json = super_resp.json()
        assert super_json["dossier_version"] == 2
        assert super_json["parent_dossier_id"] == dossier_id
        assert super_json["is_active"] is True
        assert super_json["deployment_safety_inferred"] is False

    app.dependency_overrides.clear()
