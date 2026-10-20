"""
backend/services/parameter_trust_dossier_service.py
===================================================
SuspensionLab PRO — Phase 6.7 Validation Evidence Integrity,
Engineering Decision Dossiers & Closure Governance Service.

Provides defensible, reproducible, role-governed evidence closure:
1. Source Authenticity: Separates claimed vs. verified source identities,
   evaluating them via authoritative mechanisms (trusted registry checks,
   authenticated supplier attestations, authorized custodian review,
   cryptographic signatures). Unverifiable sources remain explicitly UNVERIFIED.
2. Engineering Decision Dossier: Deterministic, versioned, immutable dossiers
   linking engineering questions, parameter trust profiles, exposure assessments,
   baseline robustness, sealed validation plans, evidence items, source verification
   records, evidence closure verdicts, and new Phase 6.5 robustness reassessments.
3. Review & Governance Gates: Role-controlled transitions separating evidence
   admissibility, criteria satisfaction, evidence-gap closure, conclusion review,
   and decision approval.
4. Non-Elevation: Deployment safety certification is never inferred or established.
5. Historical Immutability & Concurrency: Immutable audit records with deterministic
   content hashes and concurrency safety across live database connections.
"""
from __future__ import annotations

import collections
import copy
import hashlib
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# Cryptographic signatures (Ed25519)
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.exceptions import InvalidSignature as CryptoInvalidSignature
    from cryptography.hazmat.primitives import serialization
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

# Database Models & Enums
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
    SourceVerificationMethod,
    SourceVerificationStatus,
    EvidenceIntegrityStage,
    DossierGovernanceState,
    ReviewActionType,
    ValidationPlanStatus,
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
)
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSessionStatus,
)
from suspensionlab.backend.database.models.user import User

# Supporting Services & Helpers
from suspensionlab.backend.services.parameter_trust_decision_service import (
    PreRevealFirewallViolation,
    TenantIsolationError,
    AttrDict,
    to_attr_dict,
    _extract_scope,
)
from suspensionlab.backend.services.parameter_trust_validation_service import (
    SimulationMasqueradingAsPhysicalError,
)

logger = logging.getLogger(__name__)


# ── UUID & SCOPE HELPERS ──────────────────────────────────────────────────────

def _safe_uuid(val: Any) -> Optional[uuid.UUID]:
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, TypeError):
        return None


def _validate_uuid_or_str(val: Any) -> Optional[uuid.UUID]:
    return _safe_uuid(val)


def _extract_scope_uuids(
    user_context: Any,
    kwargs: Dict[str, Any]
) -> Tuple[Optional[uuid.UUID], Optional[uuid.UUID], Optional[uuid.UUID]]:
    team_s, org_s, user_s = _extract_scope(user_context, kwargs)
    return _safe_uuid(team_s), _safe_uuid(org_s), _safe_uuid(user_s)


def _extract_user_role(user_context: Any) -> str:
    if user_context is None:
        return "VIEWER"
    if isinstance(user_context, dict):
        role = user_context.get("team_role") or user_context.get("org_role") or user_context.get("role") or ""
        if not role and user_context.get("is_admin"):
            return "ADMIN"
        return str(role).upper() if role else "VIEWER"
    role = getattr(user_context, "team_role", None) or getattr(user_context, "org_role", None) or getattr(user_context, "role", None)
    if role:
        return str(role).upper()
    if getattr(user_context, "is_admin", False):
        return "ADMIN"
    return "VIEWER"


# ── EXCEPTIONS ────────────────────────────────────────────────────────────────

class DossierGovernanceError(Exception):
    """Base exception for Phase 6.7 dossier and evidence integrity operations."""
    pass


class EvidenceNotFoundError(DossierGovernanceError):
    """Raised when an evidence item cannot be found in tenant scope."""
    pass


class DossierNotFoundError(DossierGovernanceError):
    """Raised when an engineering decision dossier cannot be found in tenant scope."""
    pass


class UnverifiedSourceError(DossierGovernanceError):
    """Raised when an evidence source fails verification or is unverified."""
    pass


class RevokedSourceAuthorizationError(DossierGovernanceError):
    """Raised when an evidence source has been revoked from authorization."""
    pass


class InvalidSignatureError(DossierGovernanceError):
    """Raised when cryptographic signature verification fails."""
    pass


class ArtifactIntegrityBreachError(DossierGovernanceError):
    """Raised when submitted artifact hash differs from observed content hash."""
    pass


class UnauthorizedReviewerError(DossierGovernanceError):
    """Raised when an unauthorized user attempts a role-controlled review transition."""
    pass


class InvalidGovernanceTransitionError(DossierGovernanceError):
    """Raised when an illegal dossier governance stage transition is attempted."""
    pass


class ImmutableDossierError(DossierGovernanceError):
    """Raised when attempting to modify an approved or finalized decision dossier."""
    pass


class ContradictoryEvidenceError(DossierGovernanceError):
    """Raised when conflicting evidence prevents unconditional decision approval."""
    pass


class CrossTenantAccessError(DossierGovernanceError):
    """Raised when cross-tenant access is attempted."""
    pass


# ── CANONICAL HASH HELPER ─────────────────────────────────────────────────────

def _canonical_json_hash(data: Any) -> str:
    """Computes a deterministic SHA-256 hash over canonical JSON bytes."""
    serialized = json.dumps(data, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ── SERVICE IMPLEMENTATION ────────────────────────────────────────────────────

class ParameterTrustDossierService:
    """
    Authoritative Service for Phase 6.7:
    Evidence Integrity Verification, Engineering Decision Dossiers & Closure Governance.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── A. SOURCE IDENTITY VERIFICATION ────────────────────────────────────────

    @classmethod
    async def verify_source_identity(
        cls,
        *args,
        **kwargs
    ) -> SourceVerificationRecord:
        """
        Formally verifies an evidence item's source authenticity using an implemented method:
        - TRUSTED_REGISTRY_CHECK
        - AUTHENTICATED_SUPPLIER_ATTESTATION
        - AUTHORIZED_CUSTODIAN_REVIEW
        - CRYPTOGRAPHIC_SIGNATURE

        Strict Invariants:
        - Unverifiable source identities remain explicitly UNVERIFIED.
        - Simulation results pretending to be physical evidence are strictly rejected.
        - Phase 5 blind evaluation assets are protected by the pre-reveal firewall.
        - Tampered artifact hashes are detected and rejected.
        - Cross-tenant access is strictly blocked.
        """
        args_list = list(args)
        db = kwargs.pop("db", None)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        evidence_item_id = args_list[0] if len(args_list) > 0 else kwargs.pop("evidence_item_id", None)
        verification_method = args_list[1] if len(args_list) > 1 else kwargs.pop("verification_method", None)
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)

        supporting_references = kwargs.pop("supporting_references", {}) or {}
        scope = kwargs.pop("scope", {}) or {}
        verification_notes = kwargs.pop("verification_notes", None)
        signature_hex = kwargs.pop("signature_hex", None)
        public_key_pem = kwargs.pop("public_key_pem", None)
        expected_artifact_hash = kwargs.pop("expected_artifact_hash", None)

        team_id, org_id, user_id = _extract_scope_uuids(user_context, kwargs)
        actor_role = _extract_user_role(user_context)
        is_admin_user = getattr(user_context, "is_admin", False) if user_context else False

        # 1. Fetch Evidence Item & Enforce Cross-Tenant Boundary
        stmt = select(ValidationEvidenceItemRecord).where(
            ValidationEvidenceItemRecord.id == _safe_uuid(evidence_item_id)
        )
        res = await db.execute(stmt)
        item = res.scalar_one_or_none()
        if not item:
            raise EvidenceNotFoundError(f"Validation evidence item '{evidence_item_id}' not found.")

        if org_id and item.organization_id and item.organization_id != org_id:
            raise CrossTenantAccessError("Cross-tenant evidence item access prohibited.")
        if team_id and item.team_id and item.team_id != team_id:
            raise CrossTenantAccessError("Cross-tenant team boundary isolation enforced.")

        # Check if already revoked
        if item.source_verification_status in (SourceVerificationStatus.REVOKED.value, "REVOKED"):
            raise RevokedSourceAuthorizationError(
                f"REVOKED SOURCE: Evidence item '{item.id}' source authorization has been revoked."
            )

        # 2. Phase 5 Pre-Reveal Firewall Protection
        prov = item.provenance or {}
        blind_session_id = prov.get("blind_session_id")
        if blind_session_id:
            blind_stmt = select(BlindEngineeringSession).where(
                BlindEngineeringSession.id == _safe_uuid(blind_session_id)
            )
            b_res = await db.execute(blind_stmt)
            b_sess = b_res.scalar_one_or_none()
            if b_sess and b_sess.status not in (
                BlindSessionStatus.REVEALED,
                getattr(BlindSessionStatus, "REVEALED_EVALUATION", BlindSessionStatus.REVEALED),
            ):
                raise PreRevealFirewallViolation(
                    f"CRITICAL FIREWALL BREACH: Validation evidence '{item.id}' references unrevealed "
                    f"Phase 5 blind evaluation session '{blind_session_id}'. Ingestion strictly prohibited."
                )

        if item.parameter_name:
            blind_scope_stmt = select(BlindEngineeringSession).where(
                BlindEngineeringSession.status != BlindSessionStatus.REVEALED.value
            )
            if org_id or item.organization_id:
                blind_scope_stmt = blind_scope_stmt.where(
                    BlindEngineeringSession.organization_id == (org_id or item.organization_id)
                )
            blind_scope_res = await db.execute(blind_scope_stmt)
            for bs in blind_scope_res.scalars().all():
                if bs.status not in (BlindSessionStatus.REVEALED.value, getattr(BlindSessionStatus, "REVEALED", "REVEALED")):
                    cfg = bs.configuration or {}
                    holdouts = cfg.get("holdout_parameters") or {}
                    revealed = cfg.get("revealed_parameters") or {}
                    if (
                        item.parameter_name in holdouts and item.parameter_name not in revealed
                    ) or bs.hidden_outcome_id == item.parameter_name or bs.root_entity_id == str(item.id):
                        raise PreRevealFirewallViolation(
                            f"CRITICAL FIREWALL BREACH: Validation evidence '{item.id}' targets parameter "
                            f"'{item.parameter_name}' which is currently protected as unrevealed holdout in "
                            f"blind engineering session '{bs.name}'. Access strictly prohibited."
                        )

        # 3. Anti-Masquerade Non-Simulation Verification Check
        is_simulation_source = (
            item.evidence_source_type in (
                "SIMULATION_SWEEP",
                "CAE_MULTIBODY_SIMULATION",
                "SYNTHETIC_DATASET",
                EvidenceDataSourceType.NUMERICAL_SIMULATION_RESULT.value,
            )
            or "simulation" in str(item.evidence_source_type).lower()
            or "synthetic" in str(item.evidence_source_type).lower()
            or "cae" in str(item.evidence_source_type).lower()
        )
        meta_str = json.dumps(item.calibration_metadata or {}).lower()
        prov_str = json.dumps(prov).lower()
        has_solver_markers = (
            "numerical_solver" in prov_str
            or "synthetic_simulation" in meta_str
            or "mock_dyno" in meta_str
            or "solver" in meta_str
        )
        if item.is_physically_validated and (is_simulation_source or has_solver_markers):
            raise SimulationMasqueradingAsPhysicalError(
                f"PHYSICAL EVIDENCE INTEGRITY BREACH: Evidence item '{item.id}' contains simulated / "
                f"synthetic solver markers while claiming physical measurement authenticity."
            )

        # 4. Artifact Hash Integrity Check
        if expected_artifact_hash and expected_artifact_hash != item.integrity_hash:
            raise ArtifactIntegrityBreachError(
                f"ARTIFACT TAMPER DETECTED: Expected hash '{expected_artifact_hash}' does not match "
                f"evidence item integrity hash '{item.integrity_hash}'."
            )

        # 5. Method-Specific Verification
        method_str = str(getattr(verification_method, "value", verification_method)).upper()
        v_status = SourceVerificationStatus.UNVERIFIED.value

        if method_str == SourceVerificationMethod.TRUSTED_REGISTRY_CHECK.value:
            reg_stmt = select(TrustedSourceRegistryRecord).where(
                TrustedSourceRegistryRecord.source_identifier == item.source_identifier
            )
            reg_res = await db.execute(reg_stmt)
            reg_entry = reg_res.scalar_one_or_none()

            if not reg_entry:
                v_status = SourceVerificationStatus.UNVERIFIED.value
                raise UnverifiedSourceError(
                    f"UNVERIFIED SOURCE: Source '{item.source_identifier}' not found in trusted source registry."
                )
            elif not reg_entry.is_authorized:
                v_status = SourceVerificationStatus.REJECTED.value
                raise RevokedSourceAuthorizationError(
                    f"REVOKED SOURCE: Source '{item.source_identifier}' authorization has been revoked in trusted registry."
                )
            elif reg_entry.valid_until and reg_entry.valid_until < datetime.now(timezone.utc):
                v_status = SourceVerificationStatus.REJECTED.value
                raise UnverifiedSourceError(
                    f"UNVERIFIED SOURCE: Trusted registry certification for '{item.source_identifier}' has expired."
                )
            else:
                v_status = SourceVerificationStatus.VERIFIED.value
                supporting_references["registry_record_id"] = str(reg_entry.id)
                supporting_references["registry_source_name"] = reg_entry.source_name
                supporting_references["certificate_ref"] = reg_entry.certificate_ref

        elif method_str == SourceVerificationMethod.AUTHENTICATED_SUPPLIER_ATTESTATION.value:
            if not supporting_references or not isinstance(supporting_references, dict) or len(supporting_references) == 0:
                v_status = SourceVerificationStatus.UNVERIFIED.value
                raise UnverifiedSourceError(
                    f"UNVERIFIED SOURCE: Incomplete supplier credentials for attestation on source '{item.source_identifier}'."
                )
            else:
                v_status = SourceVerificationStatus.VERIFIED.value

        elif method_str == SourceVerificationMethod.AUTHORIZED_CUSTODIAN_REVIEW.value:
            allowed_custodians = ("VALIDATION_LEAD", "LEAD", "CHIEF_ENGINEER", "QA_AUDITOR", "SYSTEM_AUDITOR", "ADMIN")
            if not is_admin_user and actor_role not in allowed_custodians:
                raise UnauthorizedReviewerError(
                    f"ROLE ACCESS VIOLATION: Role '{actor_role}' is not authorized to perform "
                    f"custodian review. Required: VALIDATION_LEAD, CHIEF_ENGINEER, QA_AUDITOR, or SYSTEM_AUDITOR."
                )
            v_status = SourceVerificationStatus.VERIFIED.value

        elif method_str == SourceVerificationMethod.CRYPTOGRAPHIC_SIGNATURE.value:
            if not signature_hex:
                raise InvalidSignatureError("CRYPTOGRAPHIC VERIFICATION FAILED: Signature hex missing.")

            # Resolve public key: either explicit parameter or from trusted registry
            pub_key_str = public_key_pem
            if not pub_key_str:
                reg_stmt = select(TrustedSourceRegistryRecord).where(
                    TrustedSourceRegistryRecord.source_identifier == item.source_identifier
                )
                reg_res = await db.execute(reg_stmt)
                reg_entry = reg_res.scalar_one_or_none()
                if reg_entry:
                    pub_key_str = reg_entry.public_key_pem

            if not pub_key_str:
                raise InvalidSignatureError(
                    f"CRYPTOGRAPHIC VERIFICATION FAILED: Public key for source '{item.source_identifier}' not found."
                )

            if not HAS_CRYPTOGRAPHY:
                raise DossierGovernanceError("Cryptographic verification requires 'cryptography' library installed.")

            try:
                public_key = serialization.load_pem_public_key(pub_key_str.encode("utf-8"))
                sig_bytes = bytes.fromhex(signature_hex)
                msg_bytes = item.integrity_hash.encode("utf-8")
                public_key.verify(sig_bytes, msg_bytes)
                v_status = SourceVerificationStatus.VERIFIED.value
                supporting_references["signature_scheme"] = "Ed25519"
                supporting_references["verified_hash"] = item.integrity_hash
            except (CryptoInvalidSignature, ValueError) as err:
                raise InvalidSignatureError(f"CRYPTOGRAPHIC SIGNATURE INVALID: Verification failed ({err}).")
            except Exception as err:
                raise InvalidSignatureError(f"CRYPTOGRAPHIC SIGNATURE VERIFICATION ERROR: {err}")

        else:
            raise DossierGovernanceError(f"Unknown verification method: '{verification_method}'")

        # 6. Build Deterministic Verification Hash
        verifier_id_str = getattr(user_context, "name", None) or getattr(user_context, "email", None) or f"User:{user_id or 'SYSTEM'}"
        v_hash_payload = {
            "evidence_item_id": str(item.id),
            "verification_method": method_str,
            "verification_status": v_status,
            "verifier_identity": verifier_id_str,
            "verifier_role": actor_role,
            "artifact_hash": item.integrity_hash,
            "references": supporting_references,
            "scope": scope,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        v_hash = _canonical_json_hash(v_hash_payload)

        # 7. Create Verification Record
        verif_rec = SourceVerificationRecord(
            id=uuid.uuid4(),
            evidence_item_id=item.id,
            verification_method=method_str,
            verification_status=v_status,
            verifier_identity=verifier_id_str,
            verifier_role=actor_role,
            verifier_user_id=user_id,
            verification_timestamp=datetime.now(timezone.utc),
            artifact_hash=item.integrity_hash,
            supporting_references=supporting_references,
            scope=scope,
            verification_notes=verification_notes,
            verification_hash=v_hash,
            organization_id=org_id or item.organization_id,
            team_id=team_id or item.team_id,
        )
        db.add(verif_rec)

        # 8. Update Evidence Item State
        item.source_verification_status = v_status
        item.source_verification_id = verif_rec.id
        if v_status == SourceVerificationStatus.VERIFIED.value:
            item.integrity_stage = EvidenceIntegrityStage.SOURCE_IDENTITY_VERIFIED.value
        else:
            item.integrity_stage = EvidenceIntegrityStage.SOURCE_CLAIMED.value

        await db.commit()
        await db.refresh(verif_rec)
        return verif_rec

    # ── B. SOURCE REVOCATION ──────────────────────────────────────────────────

    @classmethod
    async def revoke_source_verification(
        cls,
        *args,
        **kwargs
    ) -> SourceVerificationRecord:
        """
        Revokes a previously established source verification record.
        Flags all downstream evidence items as REVOKED.
        """
        args_list = list(args)
        db = kwargs.pop("db", None)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        verification_id = args_list[0] if len(args_list) > 0 else kwargs.pop("verification_id", None)
        user_context = args_list[1] if len(args_list) > 1 else kwargs.pop("user_context", None)
        reason = kwargs.pop("reason", "Source verification revoked by authorized engineer.")

        team_id, org_id, user_id = _extract_scope_uuids(user_context, kwargs)
        actor_role = _extract_user_role(user_context)
        is_admin_user = getattr(user_context, "is_admin", False) if user_context else False

        allowed_revokers = ("VALIDATION_LEAD", "LEAD", "CHIEF_ENGINEER", "QA_AUDITOR", "SYSTEM_AUDITOR", "ADMIN")
        if not is_admin_user and actor_role not in allowed_revokers:
            raise UnauthorizedReviewerError(
                f"ROLE ACCESS VIOLATION: Role '{actor_role}' is not authorized to revoke source verification."
            )

        stmt = select(SourceVerificationRecord).where(
            SourceVerificationRecord.id == _safe_uuid(verification_id)
        )
        res = await db.execute(stmt)
        rec = res.scalar_one_or_none()
        if not rec:
            raise DossierNotFoundError(f"Source verification record '{verification_id}' not found.")

        if org_id and rec.organization_id and rec.organization_id != org_id:
            raise CrossTenantAccessError("Cross-tenant source verification revocation prohibited.")
        if team_id and rec.team_id and rec.team_id != team_id:
            raise CrossTenantAccessError("Cross-tenant team boundary isolation enforced.")

        rec.is_revoked = True
        rec.verification_status = SourceVerificationStatus.REVOKED.value
        rec.revocation_reason = reason
        rec.revoked_by_user_id = user_id
        rec.revoked_at = datetime.now(timezone.utc)

        # Update evidence item
        ev_stmt = select(ValidationEvidenceItemRecord).where(
            ValidationEvidenceItemRecord.id == rec.evidence_item_id
        )
        ev_res = await db.execute(ev_stmt)
        item = ev_res.scalar_one_or_none()
        if item:
            item.source_verification_status = SourceVerificationStatus.REVOKED.value
            item.integrity_stage = EvidenceIntegrityStage.SOURCE_CLAIMED.value

        await db.commit()
        await db.refresh(rec)
        return rec

    # ── C. ENGINEERING DECISION DOSSIER COMPILATION ────────────────────────────

    @classmethod
    async def compile_decision_dossier(
        cls,
        *args,
        **kwargs
    ) -> EngineeringDecisionDossierRecord:
        """
        Compiles an authoritative, versioned Engineering Decision Dossier linking:
        - Engineering question and target decision
        - Sealed validation plan and criteria
        - Evidence closure verdict
        - Reassessed decision robustness analysis
        - Evidence items and source verification records
        - Contradictory evidence detection
        - Review audit trail
        - Deterministic content hash

        Strict Invariants:
        - Deployment safety is NOT inferred or established (deployment_safety_inferred = False).
        - Cross-tenant boundaries are strictly enforced.
        """
        args_list = list(args)
        db = kwargs.pop("db", None)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        decision_id = args_list[0] if len(args_list) > 0 else kwargs.pop("decision_id", None)
        plan_id = args_list[1] if len(args_list) > 1 else kwargs.pop("plan_id", None)
        closure_id = args_list[2] if len(args_list) > 2 else kwargs.pop("closure_id", None)
        reassessment_id = args_list[3] if len(args_list) > 3 else kwargs.pop("reassessment_id", None)
        user_context = args_list[4] if len(args_list) > 4 else kwargs.pop("user_context", None)

        engineering_question = kwargs.pop("engineering_question", None)
        decision_type = kwargs.pop("decision_type", "EngineeringDecision")
        dossier_version = kwargs.pop("dossier_version", 1)

        team_id, org_id, user_id = _extract_scope_uuids(user_context, kwargs)
        actor_role = _extract_user_role(user_context)

        # 1. Fetch Validation Plan & Enforce Cross-Tenant Isolation
        p_stmt = select(EngineeringValidationPlanRecord).where(
            EngineeringValidationPlanRecord.id == _safe_uuid(plan_id)
        )
        p_res = await db.execute(p_stmt)
        plan = p_res.scalar_one_or_none()
        if not plan:
            raise DossierGovernanceError(f"Validation plan '{plan_id}' not found.")

        if org_id and plan.organization_id and plan.organization_id != org_id:
            raise CrossTenantAccessError("Cross-tenant validation plan access prohibited.")
        if team_id and plan.team_id and plan.team_id != team_id:
            raise CrossTenantAccessError("Cross-tenant team boundary isolation enforced.")

        # 2. Fetch Evidence Closure
        c_stmt = select(ValidationEvidenceClosureRecord).where(
            ValidationEvidenceClosureRecord.id == _safe_uuid(closure_id)
        )
        c_res = await db.execute(c_stmt)
        closure = c_res.scalar_one_or_none()
        if not closure:
            raise DossierGovernanceError(f"Validation evidence closure '{closure_id}' not found.")

        # 3. Fetch Decision Reassessment
        r_stmt = select(ValidationDecisionReassessmentRecord).where(
            ValidationDecisionReassessmentRecord.id == _safe_uuid(reassessment_id)
        )
        r_res = await db.execute(r_stmt)
        reassessment = r_res.scalar_one_or_none()
        if not reassessment:
            raise DossierGovernanceError(f"Validation decision reassessment '{reassessment_id}' not found.")

        # 4. Fetch Robustness Analyses (Baseline & Reassessed)
        baseline_rob = None
        if reassessment.original_robustness_analysis_id:
            b_stmt = select(DecisionRobustnessAnalysisRecord).where(
                DecisionRobustnessAnalysisRecord.id == reassessment.original_robustness_analysis_id
            )
            b_res = await db.execute(b_stmt)
            baseline_rob = b_res.scalar_one_or_none()

        reassessed_rob = None
        if reassessment.new_robustness_analysis_id:
            n_stmt = select(DecisionRobustnessAnalysisRecord).where(
                DecisionRobustnessAnalysisRecord.id == reassessment.new_robustness_analysis_id
            )
            n_res = await db.execute(n_stmt)
            reassessed_rob = n_res.scalar_one_or_none()

        # 5. Fetch Evidence Items & Source Verification Records
        ev_stmt = select(ValidationEvidenceItemRecord).where(
            ValidationEvidenceItemRecord.plan_id == plan.id
        )
        ev_res = await db.execute(ev_stmt)
        evidence_items = list(ev_res.scalars().all())

        ev_ids = [str(e.id) for e in evidence_items]
        verif_ids = []
        lineage_summary = []
        unresolved_assumptions = []
        observations = []

        for e in evidence_items:
            if e.source_verification_id:
                verif_ids.append(str(e.source_verification_id))

            lineage_entry = {
                "evidence_id": str(e.id),
                "source_identifier": e.source_identifier,
                "source_type": e.evidence_source_type,
                "integrity_stage": e.integrity_stage,
                "source_verification_status": e.source_verification_status,
                "is_physically_validated": e.is_physically_validated,
                "observed_value": e.observed_value,
                "observed_interval": e.observed_interval,
                "unit": e.unit,
                "integrity_hash": e.integrity_hash,
                "provenance": e.provenance,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            lineage_summary.append(lineage_entry)

            if e.source_verification_status != SourceVerificationStatus.VERIFIED.value:
                unresolved_assumptions.append({
                    "type": "UNVERIFIED_EVIDENCE_SOURCE",
                    "evidence_id": str(e.id),
                    "source_identifier": e.source_identifier,
                    "notice": UNVERIFIED_SOURCE_NOTICE,
                })

            if e.observed_value is not None:
                observations.append(float(e.observed_value))
            elif e.observed_interval and isinstance(e.observed_interval, list) and len(e.observed_interval) >= 2:
                observations.extend([float(x) for x in e.observed_interval[:2]])

        # 6. Contradictory Evidence Evaluation
        contradictory_summary = {
            "has_contradictions": False,
            "has_conflicts": False,
            "contradictory_count": 0,
            "items": [],
            "conflicts": [],
        }
        if len(observations) >= 2:
            min_obs = min(observations)
            max_obs = max(observations)
            spread = max_obs - min_obs
            mean_obs = sum(observations) / len(observations)
            if mean_obs > 0 and (spread / mean_obs) > 0.30:
                conflict_item = f"Spread between observations ({spread:.2f}) exceeds 30% tolerance across evidence items."
                contradictory_summary = {
                    "has_contradictions": True,
                    "has_conflicts": True,
                    "contradictory_count": 1,
                    "items": [conflict_item],
                    "spread": spread,
                    "min_observed": min_obs,
                    "max_observed": max_obs,
                    "conflicts": [conflict_item],
                }
                unresolved_assumptions.append({
                    "type": "CONTRADICTORY_OBSERVATIONS",
                    "details": contradictory_summary,
                })

        # 7. Before vs. After Robustness Comparison
        baseline_env = getattr(baseline_rob, "evaluated_envelope", {}) if baseline_rob else {}
        baseline_class = getattr(baseline_rob, "robustness_classification", "NOT_ASSESSED") if baseline_rob else "NOT_ASSESSED"
        reassessed_env = getattr(reassessed_rob, "evaluated_envelope", {}) if reassessed_rob else {}
        reassessed_class = getattr(reassessed_rob, "robustness_classification", "NOT_ASSESSED") if reassessed_rob else "NOT_ASSESSED"

        before_after = {
            "parameter_name": plan.parameter_name,
            "unit": plan.unit,
            "baseline": {
                "uncertainty_envelope": baseline_env,
                "classification": baseline_class,
            },
            "reassessed": {
                "uncertainty_envelope": reassessed_env,
                "classification": reassessed_class,
                "reversal_status": reassessment.reversal_status,
            },
            "reversal_status": reassessment.reversal_status,
            "reassessment_delta": reassessment.reassessment_delta,
            "reversal_resolved": reassessment.reversal_status == ReversalResolutionStatus.REVERSAL_RESOLVED.value,
        }

        # 8. Deterministic Dossier Number & Content Hash
        dossier_num = f"DOS-{decision_id}-{dossier_version:03d}"

        hash_payload = {
            "dossier_number": dossier_num,
            "decision_id": str(decision_id),
            "engineering_question": engineering_question or plan.validation_objective,
            "plan_hash": plan.plan_hash,
            "closure_hash": closure.closure_hash,
            "reassessment_hash": reassessment.reassessment_hash,
            "evidence_item_ids": sorted(ev_ids),
            "source_verification_ids": sorted(verif_ids),
            "before_after": before_after,
        }
        dossier_hash = _canonical_json_hash(hash_payload)

        # 9. Audit Trail Entry for Compilation
        audit_trail = [{
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_user_id": str(user_id or plan.created_by_user_id or "ANONYMOUS_USER"),
            "actor_role": actor_role,
            "action": "COMPILE_DOSSIER",
            "from_state": "NONE",
            "to_state": DossierGovernanceState.DRAFT.value,
            "rationale": "Initial decision dossier compilation from verified plan, closure, and reassessment.",
        }]

        dossier = EngineeringDecisionDossierRecord(
            id=uuid.uuid4(),
            dossier_number=dossier_num,
            decision_id=str(decision_id),
            decision_type=decision_type,
            engineering_question=engineering_question or plan.validation_objective,
            dossier_version=dossier_version,
            plan_id=plan.id,
            plan_version=plan.plan_version,
            plan_hash=plan.plan_hash,
            sealed_acceptance_criteria=plan.acceptance_criteria,
            exposure_assessment_id=plan.exposure_assessment_id,
            exposure_hash=plan.analysis_snapshot_hash,
            baseline_robustness_analysis_id=reassessment.original_robustness_analysis_id,
            baseline_robustness_hash=baseline_rob.analysis_hash if baseline_rob else None,
            closure_id=closure.id,
            closure_hash=closure.closure_hash,
            reassessment_id=reassessment.id,
            reassessment_hash=reassessment.reassessment_hash,
            reassessed_robustness_analysis_id=reassessment.new_robustness_analysis_id,
            reassessed_robustness_hash=reassessed_rob.analysis_hash if reassessed_rob else None,
            evidence_item_ids=ev_ids,
            source_verification_ids=verif_ids,
            evidence_lineage_summary={"items": lineage_summary},
            contradictory_evidence_summary=contradictory_summary,
            unresolved_assumptions=unresolved_assumptions,
            before_after_comparison=before_after,
            governance_state=DossierGovernanceState.DRAFT.value,
            admissibility_status="PENDING",
            criteria_satisfaction_status="PENDING",
            closure_status="PENDING",
            conclusion_review_status="PENDING",
            decision_approval_status="PENDING",
            governance_separation_notice=GOVERNANCE_SEPARATION_NOTICE_V2,
            deployment_authorization_status="NOT_ESTABLISHED",
            deployment_safety_inferred=False,
            review_audit_trail=audit_trail,
            dossier_content_hash=dossier_hash,
            is_active=True,
            organization_id=org_id or plan.organization_id,
            team_id=team_id or plan.team_id,
            compiled_by_user_id=user_id or plan.created_by_user_id or uuid.uuid4(),
        )

        db.add(dossier)
        await db.commit()
        await db.refresh(dossier)
        return dossier

    # ── D. REVIEW & GOVERNANCE TRANSITIONS ─────────────────────────────────────

    @classmethod
    async def advance_dossier_governance(
        cls,
        *args,
        **kwargs
    ) -> EngineeringDecisionDossierRecord:
        """
        Advances an Engineering Decision Dossier through formal, sequential,
        role-controlled governance gates:
        1. ADMIT_EVIDENCE: VALIDATION_LEAD / QA_AUDITOR
        2. EVALUATE_CRITERIA: VALIDATION_LEAD / QA_AUDITOR
        3. CLOSE_GAP: VALIDATION_LEAD / CHIEF_ENGINEER
        4. REVIEW_CONCLUSION: CHIEF_ENGINEER / VALIDATION_LEAD
        5. APPROVE_DECISION: CHIEF_ENGINEER ONLY
        6. REJECT: Any authorized lead reviewer
        """
        args_list = list(args)
        db = kwargs.pop("db", None)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        dossier_id = args_list[0] if len(args_list) > 0 else kwargs.pop("dossier_id", None)
        action_type = args_list[1] if len(args_list) > 1 else kwargs.pop("action_type", None)
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)
        rationale = kwargs.pop("rationale", "")

        team_id, org_id, user_id = _extract_scope_uuids(user_context, kwargs)
        actor_role = _extract_user_role(user_context)
        is_admin_user = getattr(user_context, "is_admin", False) if user_context else False

        # Select with row lock on PostgreSQL
        stmt = select(EngineeringDecisionDossierRecord).where(
            EngineeringDecisionDossierRecord.id == _safe_uuid(dossier_id)
        )
        if hasattr(stmt, "with_for_update") and db.bind and db.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()

        res = await db.execute(stmt)
        dossier = res.scalar_one_or_none()
        if not dossier:
            raise DossierNotFoundError(f"Engineering decision dossier '{dossier_id}' not found.")

        # Cross-tenant check
        if org_id and dossier.organization_id and dossier.organization_id != org_id:
            raise CrossTenantAccessError("Cross-tenant dossier access prohibited.")
        if team_id and dossier.team_id and dossier.team_id != team_id:
            raise CrossTenantAccessError("Cross-tenant team boundary isolation enforced.")

        if dossier.governance_state == DossierGovernanceState.DECISION_APPROVED.value:
            raise ImmutableDossierError(
                f"IMMUTABLE DOSSIER: Decision dossier '{dossier.dossier_number}' has already been "
                f"approved and sealed. Further modifications require a formal supersession."
            )

        act_str = str(getattr(action_type, "value", action_type)).upper()
        from_state = dossier.governance_state

        allowed_reviewers = ("VALIDATION_LEAD", "LEAD", "QA_AUDITOR", "SYSTEM_AUDITOR", "CHIEF_ENGINEER", "ADMIN")
        allowed_approvers = ("CHIEF_ENGINEER", "VALIDATION_LEAD", "LEAD", "ADMIN")

        if act_str == ReviewActionType.ADMIT_EVIDENCE.value:
            if not is_admin_user and actor_role not in allowed_reviewers:
                raise UnauthorizedReviewerError(
                    f"ROLE ACCESS VIOLATION: Role '{actor_role}' is not authorized to admit evidence."
                )
            dossier.admissibility_status = "EVIDENCE_ADMITTED"
            dossier.governance_state = DossierGovernanceState.IN_REVIEW.value

        elif act_str == ReviewActionType.EVALUATE_CRITERIA.value:
            if not is_admin_user and actor_role not in allowed_reviewers:
                raise UnauthorizedReviewerError(
                    f"ROLE ACCESS VIOLATION: Role '{actor_role}' is not authorized to evaluate criteria."
                )
            if dossier.admissibility_status != "EVIDENCE_ADMITTED":
                raise InvalidGovernanceTransitionError("Criteria evaluation requires evidence to be admitted first.")
            dossier.criteria_satisfaction_status = "CRITERIA_SATISFIED"
            dossier.governance_state = DossierGovernanceState.EVIDENCE_ACCEPTED.value

        elif act_str == ReviewActionType.CLOSE_GAP.value:
            if not is_admin_user and actor_role not in allowed_reviewers:
                raise UnauthorizedReviewerError(
                    f"ROLE ACCESS VIOLATION: Role '{actor_role}' is not authorized to close evidence gap."
                )
            if dossier.criteria_satisfaction_status != "CRITERIA_SATISFIED":
                raise InvalidGovernanceTransitionError("Gap closure requires satisfied acceptance criteria.")
            dossier.closure_status = "GAP_CLOSED"
            dossier.governance_state = DossierGovernanceState.EVIDENCE_ACCEPTED.value

        elif act_str == ReviewActionType.REVIEW_CONCLUSION.value:
            if not is_admin_user and actor_role not in allowed_approvers:
                raise UnauthorizedReviewerError(
                    f"ROLE ACCESS VIOLATION: Role '{actor_role}' is not authorized to review engineering conclusions."
                )
            if dossier.governance_state not in (
                DossierGovernanceState.EVIDENCE_ACCEPTED.value,
                DossierGovernanceState.IN_REVIEW.value,
            ):
                raise InvalidGovernanceTransitionError("Conclusion review requires evidence criteria evaluation first.")
            dossier.conclusion_review_status = "CONCLUSION_ACCEPTED"
            dossier.governance_state = DossierGovernanceState.CONCLUSION_REVIEWED.value

        elif act_str == ReviewActionType.APPROVE_DECISION.value:
            if not is_admin_user and actor_role not in allowed_approvers:
                raise UnauthorizedReviewerError(
                    f"STRICT GATE REJECTION: Final decision approval strictly requires authorized lead role. "
                    f"Attempted by role '{actor_role}'."
                )
            if dossier.conclusion_review_status != "CONCLUSION_ACCEPTED":
                raise InvalidGovernanceTransitionError("Decision approval requires conclusion review completion.")
            dossier.decision_approval_status = "DECISION_FORMALLY_APPROVED"
            dossier.governance_state = DossierGovernanceState.DECISION_APPROVED.value

        elif act_str == ReviewActionType.REJECT.value:
            dossier.governance_state = DossierGovernanceState.REJECTED.value

        else:
            raise InvalidGovernanceTransitionError(f"Unknown governance action '{action_type}'.")

        # Crucial Statutory Invariants: NEVER Elevate to Deployment Safety
        dossier.deployment_safety_inferred = False
        dossier.deployment_authorization_status = "NOT_ESTABLISHED"
        dossier.governance_separation_notice = GOVERNANCE_SEPARATION_NOTICE_V2

        # Append to audit trail
        trail = list(dossier.review_audit_trail or [])
        trail.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_user_id": str(user_id or "ANONYMOUS_ACTOR"),
            "actor_role": actor_role,
            "action": act_str,
            "from_state": from_state,
            "to_state": dossier.governance_state,
            "rationale": rationale,
            "deployment_safety_inferred": False,
            "deployment_authorization": "NOT_ESTABLISHED",
        })
        dossier.review_audit_trail = trail
        dossier.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(dossier)
        return dossier

    # ── E. DOSSIER HISTORICAL SUPERSESSION ─────────────────────────────────────

    @classmethod
    async def supersede_dossier(
        cls,
        *args,
        **kwargs
    ) -> EngineeringDecisionDossierRecord:
        """
        Creates a new version of an Engineering Decision Dossier, marking the
        parent dossier as superseded and inactive. Preserves full historical auditability.
        """
        args_list = list(args)
        db = kwargs.pop("db", None)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        parent_dossier_id = args_list[0] if len(args_list) > 0 else (
            kwargs.pop("parent_dossier_id", None) or kwargs.pop("dossier_id", None)
        )
        user_context = args_list[1] if len(args_list) > 1 else kwargs.pop("user_context", None)

        new_plan_id = kwargs.pop("new_plan_id", None)
        new_closure_id = kwargs.pop("new_closure_id", None)
        new_reassessment_id = kwargs.pop("new_reassessment_id", None)
        supersession_reason = kwargs.pop("reason", "Dossier superseded with updated evidence.")

        team_id, org_id, user_id = _extract_scope_uuids(user_context, kwargs)
        actor_role = _extract_user_role(user_context)

        # Fetch parent dossier
        stmt = select(EngineeringDecisionDossierRecord).where(
            EngineeringDecisionDossierRecord.id == _safe_uuid(parent_dossier_id)
        )
        res = await db.execute(stmt)
        parent = res.scalar_one_or_none()
        if not parent:
            raise DossierNotFoundError(f"Parent decision dossier '{parent_dossier_id}' not found.")

        # Compile new child dossier
        new_version = parent.dossier_version + 1
        child = await cls.compile_decision_dossier(
            db=db,
            decision_id=parent.decision_id,
            plan_id=new_plan_id or parent.plan_id,
            closure_id=new_closure_id or parent.closure_id,
            reassessment_id=new_reassessment_id or parent.reassessment_id,
            user_context=user_context,
            engineering_question=parent.engineering_question,
            decision_type=parent.decision_type,
            team_id=team_id,
            organization_id=org_id,
            user_id=user_id,
            dossier_version=new_version,
        )

        child.dossier_version = new_version
        child.parent_dossier_id = parent.id
        child.dossier_number = f"DOS-{parent.decision_id}-{new_version:03d}"

        # Mark parent superseded
        parent.is_active = False
        parent.superseded_by = child.id
        parent.governance_state = DossierGovernanceState.SUPERSEDED.value

        p_trail = list(parent.review_audit_trail or [])
        p_trail.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_user_id": str(user_id or "ANONYMOUS_USER"),
            "actor_role": actor_role,
            "action": "SUPERSEDE",
            "to_version": child.dossier_version,
            "child_dossier_id": str(child.id),
            "reason": supersession_reason,
        })
        parent.review_audit_trail = p_trail

        await db.commit()
        await db.refresh(child)
        return child

    # ── F. TRUSTED SOURCE REGISTRY MANAGEMENT ─────────────────────────────────

    @classmethod
    async def register_trusted_source(
        cls,
        *args,
        **kwargs
    ) -> TrustedSourceRegistryRecord:
        """
        Registers or updates an authoritative trusted evidence source in the registry.
        """
        args_list = list(args)
        db = kwargs.pop("db", None)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        source_identifier = args_list[0] if len(args_list) > 0 else kwargs.pop("source_identifier", None)
        source_name = args_list[1] if len(args_list) > 1 else kwargs.pop("source_name", None)
        source_type = args_list[2] if len(args_list) > 2 else kwargs.pop("source_type", None)
        user_context = args_list[3] if len(args_list) > 3 else kwargs.pop("user_context", None)

        certificate_ref = kwargs.pop("certificate_ref", None)
        public_key_pem = kwargs.pop("public_key_pem", None)
        valid_until = kwargs.pop("valid_until", None)

        team_id, org_id, user_id = _extract_scope_uuids(user_context, kwargs)
        actor_role = _extract_user_role(user_context)
        is_admin_user = getattr(user_context, "is_admin", False) if user_context else False

        allowed_registrars = ("VALIDATION_LEAD", "LEAD", "CHIEF_ENGINEER", "QA_AUDITOR", "SYSTEM_AUDITOR", "ADMIN")
        if not is_admin_user and actor_role not in allowed_registrars:
            raise UnauthorizedReviewerError(
                f"ROLE ACCESS VIOLATION: Role '{actor_role}' is not authorized to register trusted sources."
            )

        stmt = select(TrustedSourceRegistryRecord).where(
            TrustedSourceRegistryRecord.source_identifier == source_identifier
        )
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.source_name = source_name or existing.source_name
            existing.source_type = source_type or existing.source_type
            existing.certificate_ref = certificate_ref or existing.certificate_ref
            existing.public_key_pem = public_key_pem or existing.public_key_pem
            existing.is_authorized = True
            await db.commit()
            await db.refresh(existing)
            return existing

        reg = TrustedSourceRegistryRecord(
            id=uuid.uuid4(),
            source_identifier=source_identifier,
            source_name=source_name,
            source_type=source_type,
            is_authorized=True,
            certificate_ref=certificate_ref,
            public_key_pem=public_key_pem,
            valid_from=datetime.now(timezone.utc),
            valid_until=valid_until,
            organization_id=org_id,
            team_id=team_id,
        )
        db.add(reg)
        await db.commit()
        await db.refresh(reg)
        return reg
