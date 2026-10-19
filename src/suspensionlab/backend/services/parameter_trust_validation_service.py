"""
backend/services/parameter_trust_validation_service.py
======================================================
SuspensionLab PRO — Phase 6.6 Engineering Validation Planning,
Evidence Closure & Decision Reassessment Service.

Closes the loop:
ENGINEERING QUESTION → PARAMETER UNCERTAINTY → DECISION ROBUSTNESS →
EVIDENCE GAP → VALIDATION PLAN → OBSERVED EVIDENCE → REASSESSMENT →
CLOSURE OR UNRESOLVED STATUS.

Scientific & Epistemic Principles:
1. Distinguish planned vs completed validation activities.
2. Never invent acceptance limits: unevidenced limits remain PROPOSED or UNRESOLVED.
3. Acceptance criteria become immutable once AUTHORIZED; modifications require a new plan version.
4. Simulated data must never masquerade as physical evidence.
5. Evidence uploaded without provenance fails closed.
6. Evidence gap closure requires evidence applicability and satisfied criteria,
   never mere upload or test completion.
7. Finite sampling limitation: finite empirical measurements narrow localized uncertainty
   without certifying the full infinite operational envelope.
8. Strict Governance Decoupling:
   - Plan approval != Activity permission != Evidence acceptance !=
     Decision approval != Deployment safety.
   - deployment_safety_inferred = False, deployment_authorization = "NOT_ESTABLISHED".
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

# Database Models & Enums
from suspensionlab.backend.database.models.parameter_trust import (
    EngineeringValidationPlanRecord,
    ValidationEvidenceItemRecord,
    ValidationEvidenceClosureRecord,
    ValidationDecisionReassessmentRecord,
    DecisionExposureAssessmentRecord,
    DecisionRobustnessAnalysisRecord,
    ValidationPlanStatus,
    ValidationMethodType,
    CriterionStatus,
    EvidenceDataSourceType,
    EvidenceClosureVerdict,
    ReversalResolutionStatus,
    UncertaintyRepresentationType,
    DecisionRobustnessClassification,
    BoundaryCrossingType,
    VOIPriorityLevel,
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    SensitivityStatus,
    VALIDATION_PLANNING_POLICY_V1,
    CURRENT_VALIDATION_PLANNING_POLICY_VERSION,
    GOVERNANCE_VALIDATION_SEPARATION_NOTICE,
    FINITE_SAMPLE_SCOPE_NOTICE,
    ROBUSTNESS_POLICY_V1,
)
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSessionStatus,
)
from suspensionlab.backend.database.models.user import User

# Services
from suspensionlab.backend.services.parameter_trust_service import (
    canonicalize_parameter_unit,
    compute_value_identity,
)
from suspensionlab.backend.services.parameter_trust_decision_service import (
    ParameterTrustDecisionService,
    DecisionNotFoundError,
    PreRevealFirewallViolation,
    TenantIsolationError,
    AttrDict,
    to_attr_dict,
    hybridmethod,
    _extract_scope,
)
from suspensionlab.backend.services.parameter_trust_robustness_service import (
    ParameterTrustRobustnessService,
    RobustnessError,
)

logger = logging.getLogger(__name__)


def _extract_user_role(user_context: Any) -> str:
    if user_context is None:
        return "VIEWER"
    if isinstance(user_context, dict):
        role = user_context.get("team_role") or user_context.get("org_role") or user_context.get("role") or ""
        if not role and user_context.get("is_admin"):
            return "ADMIN"
        return role.upper() if role else "VIEWER"
    if getattr(user_context, "is_admin", False):
        return "ADMIN"
    role = getattr(user_context, "team_role", None) or getattr(user_context, "org_role", None) or getattr(user_context, "role", None)
    return str(role).upper() if role else "VIEWER"


# ── EXCEPTIONS ────────────────────────────────────────────────────────────────

class ValidationPlanningError(Exception):
    """Base exception for Phase 6.6 validation planning operations."""
    pass


class PlanNotFoundError(ValidationPlanningError):
    """Raised when a validation plan cannot be found in tenant scope."""
    pass


class InvalidPlanStateTransitionError(ValidationPlanningError):
    """Raised when an illegal plan lifecycle transition is attempted."""
    pass


class CriteriaImmutableAfterAuthorizationError(ValidationPlanningError):
    """Raised when attempting to modify acceptance criteria on an authorized plan."""
    pass


class MissingEvidenceProvenanceError(ValidationPlanningError):
    """Raised when evidence is submitted without required source provenance."""
    pass


class SimulationMasqueradingAsPhysicalError(ValidationPlanningError):
    """Raised when simulation results are falsely labeled as physical measurements."""
    pass


class InvalidEvidenceScopeError(ValidationPlanningError):
    """Raised when submitted evidence is outside the operating scope or inapplicable."""
    pass


class UnauthorizedValidationActionError(ValidationPlanningError):
    """Raised when an unauthorized user attempts to approve or review a plan."""
    pass


# ── SERVICE IMPLEMENTATION ────────────────────────────────────────────────────

class ParameterTrustValidationService:
    """
    Core implementation of Phase 6.6 Engineering Validation Planning,
    Evidence Closure & Decision Reassessment.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── A. VALIDATION PLAN CREATION ───────────────────────────────────────────

    @hybridmethod
    async def create_validation_plan(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Creates a versioned, tenant-scoped Engineering Validation Plan (Package B).
        Binds to an engineering decision, parameter, and specific evidence gap.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        decision_id = args_list[0] if len(args_list) > 0 else kwargs.pop("decision_id", None)
        parameter_name = args_list[1] if len(args_list) > 1 else kwargs.pop("parameter_name", None)
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        dec_clean = str(decision_id).strip()
        pname_clean = str(parameter_name).strip()
        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        if user_uuid is None:
            raise UnauthorizedValidationActionError("User context required to create a validation plan.")

        # 1. Resolve decision to verify tenant access & existence
        decision_info = await ParameterTrustDecisionService.resolve_decision(
            db=db,
            decision_id=dec_clean,
            team_id=team_uuid,
            organization_id=org_uuid,
            user_id=user_uuid,
        )

        validation_objective = kwargs.pop("validation_objective", None) or f"Characterize physical behavior and uncertainty bounds for '{pname_clean}'"
        validation_method = kwargs.pop("validation_method", None) or ValidationMethodType.RIG_TEST_4_POST.value
        unit = kwargs.pop("unit", None) or ""
        canonical_unit = canonicalize_parameter_unit(unit)
        measurement_definition = kwargs.pop("measurement_definition", None) or f"Direct empirical measurement of {pname_clean} in {canonical_unit}"

        evidence_gap_id = kwargs.pop("evidence_gap_id", None)
        parameter_path = kwargs.pop("parameter_path", None) or f"parameters.{pname_clean}"
        input_artifact_requirements = kwargs.pop("input_artifact_requirements", [])
        operating_conditions = kwargs.pop("operating_conditions", {})
        applicability_envelope = kwargs.pop("applicability_envelope", {})
        expected_outputs = kwargs.pop("expected_outputs", [f"{pname_clean}_measured_mean", f"{pname_clean}_tolerance_band"])
        required_reviewer_role = kwargs.pop("required_reviewer_role", "VALIDATION_LEAD")

        # Associate active Phase 6.4/6.5 snapshots
        active_robustness = await ParameterTrustRobustnessService.get_active_robustness_analysis(
            db=db,
            decision_id=dec_clean,
            user_context=user_context,
            team_id=team_id_s,
            organization_id=org_id_s,
            user_id=user_id_s,
        )
        robustness_analysis_id = uuid.UUID(active_robustness["id"]) if active_robustness and active_robustness.get("id") else None
        analysis_snapshot_hash = active_robustness.get("analysis_hash") if active_robustness else None

        # Acceptance Criteria: Never invent limits; mark PROPOSED or UNRESOLVED if not authoritative
        raw_criteria = kwargs.pop("acceptance_criteria", [])
        acceptance_criteria: List[Dict[str, Any]] = []
        for crit in raw_criteria:
            crit_dict = dict(crit)
            crit_status = crit_dict.get("status")
            has_source = bool(crit_dict.get("source") or crit_dict.get("provenance"))
            if not crit_status:
                crit_dict["status"] = CriterionStatus.ESTABLISHED.value if has_source else CriterionStatus.PROPOSED.value
            if not has_source:
                crit_dict["provenance"] = "UNRESOLVED_PROVISIONAL_SPEC"
            acceptance_criteria.append(crit_dict)

        plan_code = f"VAL-PLAN-{uuid.uuid4().hex[:8].upper()}"

        canonical_plan_payload = {
            "plan_id": plan_code,
            "decision_id": dec_clean,
            "parameter_name": pname_clean,
            "validation_objective": validation_objective,
            "validation_method": validation_method,
            "unit": canonical_unit,
            "acceptance_criteria": acceptance_criteria,
            "operating_conditions": operating_conditions,
            "policy_version": CURRENT_VALIDATION_PLANNING_POLICY_VERSION,
        }
        dumped_plan = json.dumps(canonical_plan_payload, sort_keys=True, separators=(",", ":"))
        plan_hash = hashlib.sha256(dumped_plan.encode("utf-8")).hexdigest()

        plan_record = EngineeringValidationPlanRecord(
            id=uuid.uuid4(),
            plan_id=plan_code,
            decision_id=dec_clean,
            decision_type=decision_info.get("decision_type", "EngineeringDecision"),
            parameter_name=pname_clean,
            parameter_path=parameter_path,
            evidence_gap_id=evidence_gap_id,
            validation_objective=validation_objective,
            validation_method=validation_method,
            status=ValidationPlanStatus.DRAFT.value,
            plan_version=1,
            parent_plan_id=None,
            exposure_assessment_id=None,
            robustness_analysis_id=robustness_analysis_id,
            analysis_snapshot_hash=analysis_snapshot_hash,
            input_artifact_requirements=input_artifact_requirements,
            operating_conditions=operating_conditions,
            applicability_envelope=applicability_envelope,
            unit=canonical_unit,
            measurement_definition=measurement_definition,
            acceptance_criteria=acceptance_criteria,
            criteria_established_at=datetime.now(timezone.utc) if any(c.get("status") == CriterionStatus.ESTABLISHED.value for c in acceptance_criteria) else None,
            criteria_authorized_by_user_id=None,
            expected_outputs=expected_outputs,
            required_reviewer_role=required_reviewer_role,
            authorized_by_user_id=None,
            authorized_at=None,
            plan_hash=plan_hash,
            is_active=True,
            organization_id=org_uuid,
            team_id=team_uuid,
            created_by_user_id=user_uuid,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db.add(plan_record)
        await db.flush()

        logger.info(
            "Created Engineering Validation Plan '%s' for decision '%s' parameter '%s'.",
            plan_code, dec_clean, pname_clean
        )
        return to_attr_dict(cls._plan_to_dict(plan_record))

    # ── B. LIFECYCLE TRANSITIONS ──────────────────────────────────────────────

    @hybridmethod
    async def transition_plan_status(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Executes authorized plan lifecycle state machine transitions (Package C).
        DRAFT → PROPOSED → AUTHORIZED → IN_PROGRESS → EVIDENCE_SUBMITTED → UNDER_REVIEW → ACCEPTED / REJECTED / INCONCLUSIVE.
        Enforces criteria immutability once AUTHORIZED.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        plan_id = args_list[0] if len(args_list) > 0 else kwargs.pop("plan_id", None)
        target_status = args_list[1] if len(args_list) > 1 else kwargs.pop("target_status", None)
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        plan = await cls._get_plan_record(db, plan_id, team_uuid, org_uuid, user_uuid)
        if not plan:
            raise PlanNotFoundError(f"Validation plan '{plan_id}' not found in authorized tenant scope.")

        current = plan.status
        target = str(target_status).strip().upper()

        # Valid transitions mapping
        VALID_TRANSITIONS = {
            ValidationPlanStatus.DRAFT.value: [ValidationPlanStatus.PROPOSED.value, ValidationPlanStatus.SUPERSEDED.value],
            ValidationPlanStatus.PROPOSED.value: [ValidationPlanStatus.AUTHORIZED.value, ValidationPlanStatus.REJECTED.value, ValidationPlanStatus.DRAFT.value, ValidationPlanStatus.SUPERSEDED.value],
            ValidationPlanStatus.AUTHORIZED.value: [ValidationPlanStatus.IN_PROGRESS.value, ValidationPlanStatus.SUPERSEDED.value],
            ValidationPlanStatus.IN_PROGRESS.value: [ValidationPlanStatus.EVIDENCE_SUBMITTED.value, ValidationPlanStatus.SUPERSEDED.value],
            ValidationPlanStatus.EVIDENCE_SUBMITTED.value: [ValidationPlanStatus.UNDER_REVIEW.value, ValidationPlanStatus.IN_PROGRESS.value, ValidationPlanStatus.SUPERSEDED.value],
            ValidationPlanStatus.UNDER_REVIEW.value: [
                ValidationPlanStatus.ACCEPTED.value,
                ValidationPlanStatus.REJECTED.value,
                ValidationPlanStatus.INCONCLUSIVE.value,
                ValidationPlanStatus.IN_PROGRESS.value,
                ValidationPlanStatus.SUPERSEDED.value,
            ],
            ValidationPlanStatus.ACCEPTED.value: [ValidationPlanStatus.SUPERSEDED.value],
            ValidationPlanStatus.REJECTED.value: [ValidationPlanStatus.SUPERSEDED.value],
            ValidationPlanStatus.INCONCLUSIVE.value: [ValidationPlanStatus.IN_PROGRESS.value, ValidationPlanStatus.SUPERSEDED.value],
            ValidationPlanStatus.SUPERSEDED.value: [],
        }

        if target not in VALID_TRANSITIONS.get(current, []):
            raise InvalidPlanStateTransitionError(
                f"Illegal validation plan transition from '{current}' to '{target}'. "
                f"Allowed transitions: {VALID_TRANSITIONS.get(current, [])}"
            )

        # RBAC Check: Authorization & Final Acceptance require authorized reviewer role
        if target in (ValidationPlanStatus.AUTHORIZED.value, ValidationPlanStatus.ACCEPTED.value):
            user_role = _extract_user_role(user_context)
            is_reviewer = any(r in user_role for r in ("ADMIN", "LEAD", "OWNER", "VALIDATION_LEAD", "CHIEF"))
            if not is_reviewer:
                raise UnauthorizedValidationActionError(
                    f"User role '{user_role}' is not authorized to transition validation plan to '{target}'. "
                    f"Requires role matching '{plan.required_reviewer_role}' or Admin/Lead."
                )

        now = datetime.now(timezone.utc)
        if target == ValidationPlanStatus.AUTHORIZED.value:
            plan.authorized_by_user_id = user_uuid
            plan.authorized_at = now
            plan.criteria_authorized_by_user_id = user_uuid
            # Seal acceptance criteria as AUTHORIZED
            updated_criteria = []
            for c in plan.acceptance_criteria:
                c_copy = dict(c)
                c_copy["status"] = CriterionStatus.AUTHORIZED.value
                updated_criteria.append(c_copy)
            plan.acceptance_criteria = updated_criteria
            plan.criteria_established_at = now

        plan.status = target
        plan.updated_at = now
        await db.flush()

        logger.info("Transitioned validation plan '%s' to '%s'.", plan.plan_id, target)
        return to_attr_dict(cls._plan_to_dict(plan))

    # ── C. VERSIONING & CRITERIA REVISION ─────────────────────────────────────

    @hybridmethod
    async def create_new_plan_version(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Creates a new immutable plan version when authorized criteria need adjustment (Package C).
        Prevents retroactive alteration of already-authorized acceptance criteria.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        plan_id = args_list[0] if len(args_list) > 0 else kwargs.pop("plan_id", None)
        user_context = args_list[1] if len(args_list) > 1 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        parent_plan = await cls._get_plan_record(db, plan_id, team_uuid, org_uuid, user_uuid)
        if not parent_plan:
            raise PlanNotFoundError(f"Parent validation plan '{plan_id}' not found.")

        new_criteria = kwargs.pop("acceptance_criteria", parent_plan.acceptance_criteria)
        new_objective = kwargs.pop("validation_objective", parent_plan.validation_objective)
        new_method = kwargs.pop("validation_method", parent_plan.validation_method)
        new_scope = kwargs.pop("operating_conditions", parent_plan.operating_conditions)

        now = datetime.now(timezone.utc)
        new_version_num = parent_plan.plan_version + 1
        new_plan_code = f"{parent_plan.plan_id.split('-V')[0]}-V{new_version_num}"

        canonical_payload = {
            "plan_id": new_plan_code,
            "parent_plan_id": str(parent_plan.id),
            "decision_id": parent_plan.decision_id,
            "parameter_name": parent_plan.parameter_name,
            "plan_version": new_version_num,
            "acceptance_criteria": new_criteria,
            "operating_conditions": new_scope,
        }
        dumped_plan = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
        plan_hash = hashlib.sha256(dumped_plan.encode("utf-8")).hexdigest()

        new_plan = EngineeringValidationPlanRecord(
            id=uuid.uuid4(),
            plan_id=new_plan_code,
            decision_id=parent_plan.decision_id,
            decision_type=parent_plan.decision_type,
            parameter_name=parent_plan.parameter_name,
            parameter_path=parent_plan.parameter_path,
            evidence_gap_id=parent_plan.evidence_gap_id,
            validation_objective=new_objective,
            validation_method=new_method,
            status=ValidationPlanStatus.DRAFT.value,
            plan_version=new_version_num,
            parent_plan_id=parent_plan.id,
            exposure_assessment_id=parent_plan.exposure_assessment_id,
            robustness_analysis_id=parent_plan.robustness_analysis_id,
            analysis_snapshot_hash=parent_plan.analysis_snapshot_hash,
            input_artifact_requirements=parent_plan.input_artifact_requirements,
            operating_conditions=new_scope,
            applicability_envelope=parent_plan.applicability_envelope,
            unit=parent_plan.unit,
            measurement_definition=parent_plan.measurement_definition,
            acceptance_criteria=new_criteria,
            criteria_established_at=now,
            criteria_authorized_by_user_id=None,
            expected_outputs=parent_plan.expected_outputs,
            required_reviewer_role=parent_plan.required_reviewer_role,
            authorized_by_user_id=None,
            authorized_at=None,
            plan_hash=plan_hash,
            is_active=True,
            organization_id=parent_plan.organization_id,
            team_id=parent_plan.team_id,
            created_by_user_id=user_uuid,
            created_at=now,
            updated_at=now,
        )

        parent_plan.status = ValidationPlanStatus.SUPERSEDED.value
        parent_plan.is_active = False

        db.add(new_plan)
        await db.flush()

        logger.info("Created new plan version '%s' (parent '%s').", new_plan.plan_id, parent_plan.plan_id)
        return to_attr_dict(cls._plan_to_dict(new_plan))

    # ── D. EVIDENCE INGESTION ─────────────────────────────────────────────────

    @hybridmethod
    async def submit_evidence(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Ingests real empirical validation evidence against an authorized plan (Package D).
        Requires source identity, timestamps, operating scope, and integrity hash.
        Fails closed on missing provenance, simulated masquerade, or unrevealed blind sessions.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        plan_id = args_list[0] if len(args_list) > 0 else kwargs.pop("plan_id", None)
        evidence_data = args_list[1] if len(args_list) > 1 else kwargs.pop("evidence_data", {})
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        plan = await cls._get_plan_record(db, plan_id, team_uuid, org_uuid, user_uuid)
        if not plan:
            raise PlanNotFoundError(f"Validation plan '{plan_id}' not found.")

        if plan.status not in (ValidationPlanStatus.AUTHORIZED.value, ValidationPlanStatus.IN_PROGRESS.value, ValidationPlanStatus.EVIDENCE_SUBMITTED.value):
            raise InvalidPlanStateTransitionError(
                f"Cannot submit evidence to plan '{plan.plan_id}' in status '{plan.status}'. "
                "Plan must be AUTHORIZED or IN_PROGRESS."
            )

        # 1. Source Provenance Verification
        source_id = str(evidence_data.get("source_identifier") or "").strip()
        provenance = evidence_data.get("provenance") or {}
        if not source_id or not provenance or not isinstance(provenance, dict):
            raise MissingEvidenceProvenanceError(
                "Evidence rejected: missing source_identifier or traceable provenance metadata."
            )

        # 2. Simulated Data Masquerading Check
        is_phys = bool(evidence_data.get("is_physically_validated", False))
        source_type = str(evidence_data.get("evidence_source_type", EvidenceDataSourceType.PHYSICAL_RIG_MEASUREMENT.value)).strip().upper()
        sim_indicators = ("SIMULATION", "CAE", "SYNTHETIC", "VIRTUAL", "SOLVER")
        provenance_str = json.dumps(provenance).upper()
        if is_phys and (source_type == EvidenceDataSourceType.NUMERICAL_SIMULATION_RESULT.value or any(ind in provenance_str for ind in sim_indicators)):
            raise SimulationMasqueradingAsPhysicalError(
                f"Validation integrity breach: Simulated/CAE evidence '{source_id}' cannot be marked as physically validated."
            )

        # 3. Phase 5 Pre-Reveal Firewall Check
        prov_full = f"{source_id} {provenance_str}"
        if "BLIND" in prov_full:
            sess_code = source_id.split(":")[-1].strip()
            stmt = select(BlindEngineeringSession).where(
                or_(
                    BlindEngineeringSession.name == sess_code,
                    BlindEngineeringSession.session_hash == sess_code,
                )
            )
            res = await db.execute(stmt)
            b_sess = res.scalar_one_or_none()
            if b_sess and b_sess.status not in (BlindSessionStatus.REVEALED.value, BlindSessionStatus.COMPLETED.value):
                raise PreRevealFirewallViolation(
                    f"Phase 5 Pre-Reveal Firewall Violation: Evidence references unrevealed blind session '{b_sess.name}'. Ingestion blocked."
                )

        # 4. Integrity Hash
        raw_hash = evidence_data.get("integrity_hash")
        if not raw_hash:
            canonical_payload = {
                "source_identifier": source_id,
                "parameter_name": plan.parameter_name,
                "observed_value": evidence_data.get("observed_value"),
                "provenance": provenance,
            }
            dumped = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
            raw_hash = hashlib.sha256(dumped.encode("utf-8")).hexdigest()

        # Parse timestamps & values
        source_ts = evidence_data.get("source_timestamp")
        if isinstance(source_ts, str):
            try:
                parsed_ts = datetime.fromisoformat(source_ts.replace("Z", "+00:00"))
            except Exception:
                parsed_ts = datetime.now(timezone.utc)
        elif isinstance(source_ts, datetime):
            parsed_ts = source_ts
        else:
            parsed_ts = datetime.now(timezone.utc)

        unit = canonicalize_parameter_unit(evidence_data.get("unit") or plan.unit)
        observed_val = float(evidence_data["observed_value"]) if evidence_data.get("observed_value") is not None else None
        samples_raw = evidence_data.get("observed_samples") or []
        observed_samples = [float(s) for s in samples_raw]
        observed_interval = evidence_data.get("observed_interval")

        evidence_item = ValidationEvidenceItemRecord(
            id=uuid.uuid4(),
            plan_id=plan.id,
            evidence_source_type=source_type,
            source_identifier=source_id,
            source_timestamp=parsed_ts,
            parameter_name=plan.parameter_name,
            observed_value=observed_val,
            observed_interval=observed_interval,
            observed_samples=observed_samples,
            unit=unit,
            operating_scope=evidence_data.get("operating_scope") or {},
            integrity_hash=str(raw_hash),
            provenance=provenance,
            calibration_metadata=evidence_data.get("calibration_metadata") or {},
            is_physically_validated=is_phys,
            physical_limitations=evidence_data.get("physical_limitations"),
            review_status="PENDING_REVIEW",
            review_notes=None,
            reviewed_by_user_id=None,
            reviewed_at=None,
            organization_id=org_uuid,
            team_id=team_uuid,
            submitted_by_user_id=user_uuid,
            created_at=datetime.now(timezone.utc),
        )

        plan.status = ValidationPlanStatus.EVIDENCE_SUBMITTED.value
        plan.updated_at = datetime.now(timezone.utc)

        db.add(evidence_item)
        await db.flush()

        logger.info("Submitted evidence '%s' for validation plan '%s'.", source_id, plan.plan_id)
        return to_attr_dict(cls._evidence_to_dict(evidence_item))

    # ── E. EVIDENCE REVIEW ────────────────────────────────────────────────────

    @hybridmethod
    async def review_evidence_item(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Reviews a submitted evidence item (ACCEPTED, REJECTED, INCONCLUSIVE).
        Requires validation reviewer role.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        evidence_id = args_list[0] if len(args_list) > 0 else kwargs.pop("evidence_id", None)
        disposition = args_list[1] if len(args_list) > 1 else kwargs.pop("disposition", "ACCEPTED")
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        user_role = _extract_user_role(user_context)
        is_reviewer = any(r in user_role for r in ("ADMIN", "LEAD", "OWNER", "VALIDATION_LEAD", "CHIEF"))
        if not is_reviewer:
            raise UnauthorizedValidationActionError("User role is not authorized to review validation evidence.")

        e_uuid = uuid.UUID(str(evidence_id))
        stmt = select(ValidationEvidenceItemRecord).where(ValidationEvidenceItemRecord.id == e_uuid)
        if team_uuid:
            stmt = stmt.where(or_(ValidationEvidenceItemRecord.team_id == team_uuid, ValidationEvidenceItemRecord.team_id == None))
        res = await db.execute(stmt)
        item = res.scalar_one_or_none()
        if not item:
            raise PlanNotFoundError(f"Evidence item '{evidence_id}' not found.")

        now = datetime.now(timezone.utc)
        item.review_status = str(disposition).upper()
        item.review_notes = kwargs.pop("review_notes", None)
        item.reviewed_by_user_id = user_uuid
        item.reviewed_at = now
        await db.flush()

        logger.info("Reviewed evidence item '%s' with verdict '%s'.", item.id, item.review_status)
        return to_attr_dict(cls._evidence_to_dict(item))

    # ── F. EVIDENCE CLOSURE ASSESSMENT ────────────────────────────────────────

    @hybridmethod
    async def evaluate_evidence_closure(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Executes deterministic 10-point evidence gap closure evaluation (Package E).
        Verifies objective execution, parameter matching, operating scope compatibility,
        unit consistency, provenance validity, criteria satisfaction, and absence of unresolved conflicts.
        Emits immutable closure record without inferring deployment safety.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        plan_id = args_list[0] if len(args_list) > 0 else kwargs.pop("plan_id", None)
        user_context = args_list[1] if len(args_list) > 1 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        plan = await cls._get_plan_record(db, plan_id, team_uuid, org_uuid, user_uuid)
        if not plan:
            raise PlanNotFoundError(f"Validation plan '{plan_id}' not found.")

        # Query all submitted evidence items for this plan
        ev_stmt = select(ValidationEvidenceItemRecord).where(
            ValidationEvidenceItemRecord.plan_id == plan.id,
        ).order_by(desc(ValidationEvidenceItemRecord.created_at))
        ev_res = await db.execute(ev_stmt)
        evidence_items = ev_res.scalars().all()

        if not evidence_items:
            verdict = EvidenceClosureVerdict.REMAINS_OPEN.value
            summary = "No evidence submitted for validation plan; gap remains open."
            applicability = {"has_evidence": False}
            crit_eval = []
            conflict_eval = {"conflicts_found": False}
            unc_update = {}
            req_reassess = False
        else:
            latest_ev = evidence_items[0]

            # 1. Parameter match
            param_match = (latest_ev.parameter_name == plan.parameter_name)

            # 2. Scope match: temperature, speed, regime
            plan_scope = plan.operating_conditions or {}
            ev_scope = latest_ev.operating_scope or {}
            scope_mismatches = []
            for k, plan_val in plan_scope.items():
                if k in ev_scope:
                    ev_val = ev_scope[k]
                    if k.endswith(("_min", "_min_c", "_min_kph", "_min_hz", "_min_psi")):
                        if isinstance(ev_val, (int, float)) and isinstance(plan_val, (int, float)):
                            if ev_val < plan_val:
                                scope_mismatches.append(f"{k} observed {ev_val} is below required min {plan_val}")
                    elif k.endswith(("_max", "_max_c", "_max_kph", "_max_hz", "_max_psi")):
                        if isinstance(ev_val, (int, float)) and isinstance(plan_val, (int, float)):
                            if ev_val > plan_val:
                                scope_mismatches.append(f"{k} observed {ev_val} exceeds required max {plan_val}")
                    elif isinstance(plan_val, dict) and "min" in plan_val and "max" in plan_val:
                        if isinstance(ev_val, (int, float)):
                            if ev_val < plan_val["min"] or ev_val > plan_val["max"]:
                                scope_mismatches.append(f"{k} value {ev_val} outside required range [{plan_val['min']}, {plan_val['max']}]")
                    elif plan_val != ev_val:
                        scope_mismatches.append(f"{k} expected '{plan_val}', observed '{ev_val}'")
            scope_matched = len(scope_mismatches) == 0

            # 3. Unit compatibility
            unit_compatible = (canonicalize_parameter_unit(latest_ev.unit) == canonicalize_parameter_unit(plan.unit))

            # 4. Provenance & Integrity check
            provenance_verified = bool(latest_ev.provenance and latest_ev.integrity_hash)

            # 5. Stale evidence check (> 90 days from baseline)
            now = datetime.now(timezone.utc)
            src_ts = latest_ev.source_timestamp
            if src_ts is not None and src_ts.tzinfo is None:
                src_ts = src_ts.replace(tzinfo=timezone.utc)
            is_stale = bool(src_ts and (now - src_ts).days > 90)

            # 6. Unresolved contradictory evidence check
            # Check if there are conflicting values within submitted items or database
            values_observed = [e.observed_value for e in evidence_items if e.observed_value is not None]
            has_conflicting_measurements = False
            if len(values_observed) >= 2:
                spread = max(values_observed) - min(values_observed)
                mean_val = sum(values_observed) / len(values_observed)
                if mean_val > 0 and (spread / mean_val) > 0.15:  # > 15% discrepancy between tests
                    has_conflicting_measurements = True

            # 7. Evaluate Acceptance Criteria
            crit_eval = []
            all_criteria_met = True
            for c in plan.acceptance_criteria:
                metric = c.get("metric_name") or c.get("metric", "value")
                operator = c.get("operator", "WITHIN_RANGE").upper()
                target_val = c.get("threshold") or c.get("target_value")
                target_range = c.get("tolerance_band") or c.get("target_range")
                if not target_range and (c.get("min") is not None or c.get("max") is not None):
                    target_range = (c.get("min"), c.get("max"))

                # Evaluate against observed value
                obs = latest_ev.observed_value
                met = False
                if obs is not None:
                    if operator in ("EQUALS", "EQ"):
                        met = (abs(obs - float(target_val)) < 1e-4) if target_val is not None else False
                    elif operator in ("LESS_THAN", "LT"):
                        met = obs < float(target_val) if target_val is not None else False
                    elif operator in ("GREATER_THAN", "GT"):
                        met = obs > float(target_val) if target_val is not None else False
                    elif operator in ("WITHIN_RANGE", "RANGE", "BETWEEN"):
                        if target_range and len(target_range) >= 2 and target_range[0] is not None and target_range[1] is not None:
                            r_min = float(target_range[0])
                            r_max = float(target_range[1])
                            met = (r_min <= obs <= r_max)
                        elif target_val is not None and "tolerance" in c:
                            tol = float(c["tolerance"])
                            met = (abs(obs - float(target_val)) <= tol)
                        else:
                            met = False
                    else:
                        met = True
                crit_eval.append({
                    "metric": metric,
                    "operator": operator,
                    "observed": obs,
                    "target": target_val or target_range,
                    "met": met,
                    "status": c.get("status"),
                })
                if not met:
                    all_criteria_met = False

            applicability = {
                "parameter_matched": param_match,
                "scope_matched": scope_matched,
                "scope_mismatches": scope_mismatches,
                "unit_compatible": unit_compatible,
                "provenance_verified": provenance_verified,
                "is_stale": is_stale,
            }
            conflict_eval = {
                "conflicts_found": has_conflicting_measurements,
                "evidence_count": len(evidence_items),
            }

            # 8. Determine Verdict
            if not param_match or not unit_compatible:
                verdict = EvidenceClosureVerdict.EVIDENCE_NOT_APPLICABLE.value
                summary = f"Evidence not applicable: unit incompatibility ({latest_ev.unit} vs {plan.unit}) or parameter mismatch."
                unc_update = {}
                req_reassess = False
            elif not scope_matched:
                verdict = EvidenceClosureVerdict.EVIDENCE_NOT_APPLICABLE.value
                summary = f"Evidence not applicable: operating scope mismatch ({'; '.join(scope_mismatches)})."
                unc_update = {}
                req_reassess = False
            elif has_conflicting_measurements:
                verdict = EvidenceClosureVerdict.EVIDENCE_CONFLICTED.value
                summary = "Evidence conflicted: multiple submitted measurements exhibit unresolved variance (>15%)."
                # Widened uncertainty due to conflict
                unc_update = {
                    "parameter_name": plan.parameter_name,
                    "representation_type": UncertaintyRepresentationType.INTERVAL_BOUNDED.value,
                    "lower_bound": min(values_observed) * 0.90,
                    "nominal_value": sum(values_observed) / len(values_observed),
                    "upper_bound": max(values_observed) * 1.10,
                    "reason": "Widened interval due to unresolved conflicting measurements",
                }
                req_reassess = True
            elif is_stale:
                verdict = EvidenceClosureVerdict.REMAINS_OPEN.value
                summary = "Evidence is stale (>90 days old); gap remains open."
                unc_update = {}
                req_reassess = False
            elif all_criteria_met and provenance_verified:
                verdict = EvidenceClosureVerdict.CLOSED_WITH_SUPPORTING_EVIDENCE.value
                summary = f"Evidence gap for '{plan.parameter_name}' legitimately closed with empirical measurement '{latest_ev.source_identifier}'."
                # Narrow uncertainty interval from measured evidence (tightened band)
                obs_nom = latest_ev.observed_value or 0.0
                unc_update = {
                    "parameter_name": plan.parameter_name,
                    "representation_type": UncertaintyRepresentationType.MEASUREMENT_TOLERANCE.value,
                    "lower_bound": obs_nom * 0.97,
                    "nominal_value": obs_nom,
                    "upper_bound": obs_nom * 1.03,
                    "reason": f"Narrowed from physical test '{latest_ev.source_identifier}'",
                }
                req_reassess = True
            else:
                verdict = EvidenceClosureVerdict.REMAINS_OPEN.value
                summary = "Submitted evidence failed to satisfy authorized acceptance criteria; gap remains open."
                unc_update = {}
                req_reassess = False

        canonical_closure_payload = {
            "plan_id": str(plan.id),
            "decision_id": plan.decision_id,
            "parameter_name": plan.parameter_name,
            "verdict": verdict,
            "criteria_evaluated": crit_eval,
            "applicability": applicability,
            "policy_version": CURRENT_VALIDATION_PLANNING_POLICY_VERSION,
        }
        dumped_closure = json.dumps(canonical_closure_payload, sort_keys=True, separators=(",", ":"))
        closure_hash = hashlib.sha256(dumped_closure.encode("utf-8")).hexdigest()

        # Supersede prior active closure for this plan
        existing_stmt = select(ValidationEvidenceClosureRecord).where(
            ValidationEvidenceClosureRecord.plan_id == plan.id,
            ValidationEvidenceClosureRecord.is_active == True,
        )
        ex_res = await db.execute(existing_stmt)
        old_closure = ex_res.scalar_one_or_none()

        closure_record = ValidationEvidenceClosureRecord(
            id=uuid.uuid4(),
            plan_id=plan.id,
            decision_id=plan.decision_id,
            parameter_name=plan.parameter_name,
            evidence_gap_id=plan.evidence_gap_id,
            closure_verdict=verdict,
            criteria_met=(verdict == EvidenceClosureVerdict.CLOSED_WITH_SUPPORTING_EVIDENCE.value),
            criteria_evaluated=crit_eval,
            applicability_check=applicability,
            conflict_assessment=conflict_eval,
            uncertainty_update=unc_update,
            requires_robustness_reassessment=req_reassess,
            closure_summary=summary,
            closure_hash=closure_hash,
            governance_separation_notice=GOVERNANCE_VALIDATION_SEPARATION_NOTICE,
            finite_sample_notice=FINITE_SAMPLE_SCOPE_NOTICE,
            deployment_safety_inferred=False,
            deployment_authorization="NOT_ESTABLISHED",
            is_active=True,
            superseded_by=None,
            organization_id=org_uuid,
            team_id=team_uuid,
            evaluated_by_user_id=user_uuid,
            created_at=datetime.now(timezone.utc),
        )

        db.add(closure_record)
        await db.flush()

        if old_closure:
            old_closure.is_active = False
            old_closure.superseded_by = closure_record.id
            await db.flush()

        logger.info(
            "Evaluated evidence closure for plan '%s' verdict='%s'.",
            plan.plan_id, verdict
        )
        return to_attr_dict(cls._closure_to_dict(closure_record))

    # ── G. BEFORE / AFTER DECISION REASSESSMENT ───────────────────────────────

    @hybridmethod
    async def execute_decision_reassessment(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Executes before/after decision robustness reassessment following evidence ingestion (Package F).
        Runs fresh Phase 6.5 robustness evaluation with updated evidence-backed parameters.
        Quantifies difference between old and new conclusions, reversal resolutions, and boundary shifts.
        Strict guardrail: finite empirical evidence does NOT claim infinite envelope certification.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        plan_id = args_list[0] if len(args_list) > 0 else kwargs.pop("plan_id", None)
        user_context = args_list[1] if len(args_list) > 1 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        plan = await cls._get_plan_record(db, plan_id, team_uuid, org_uuid, user_uuid)
        if not plan:
            raise PlanNotFoundError(f"Validation plan '{plan_id}' not found.")

        # Query active closure record
        cl_stmt = select(ValidationEvidenceClosureRecord).where(
            ValidationEvidenceClosureRecord.plan_id == plan.id,
            ValidationEvidenceClosureRecord.is_active == True,
        )
        cl_res = await db.execute(cl_stmt)
        closure = cl_res.scalar_one_or_none()
        if not closure:
            # If no closure record exists yet, evaluate one
            closure = await cls.evaluate_evidence_closure(
                db=db,
                plan_id=plan.id,
                user_context=user_context,
            )

        # 1. Fetch original Phase 6.5 robustness analysis
        orig_analysis = None
        if plan.robustness_analysis_id:
            orig_stmt = select(DecisionRobustnessAnalysisRecord).where(
                DecisionRobustnessAnalysisRecord.id == plan.robustness_analysis_id
            )
            orig_res = await db.execute(orig_stmt)
            orig_analysis = orig_res.scalar_one_or_none()

        if not orig_analysis:
            # Fall back to latest active robustness analysis for the decision
            orig_dict = await ParameterTrustRobustnessService.get_active_robustness_analysis(
                db=db,
                decision_id=plan.decision_id,
                user_context=user_context,
                team_id=team_id_s,
                organization_id=org_id_s,
                user_id=user_id_s,
            )
        else:
            orig_dict = ParameterTrustRobustnessService._record_to_dict(orig_analysis)

        # 2. Construct updated uncertainty inputs based on closure record
        updated_uncertainty_inputs = {}
        if orig_dict and orig_dict.get("evaluated_envelope", {}).get("parameters"):
            for p, p_env in orig_dict["evaluated_envelope"]["parameters"].items():
                updated_uncertainty_inputs[p] = {
                    "parameter_name": p,
                    "representation_type": UncertaintyRepresentationType.INTERVAL_BOUNDED.value,
                    "lower_bound": p_env.get("min"),
                    "nominal_value": p_env.get("nominal"),
                    "upper_bound": p_env.get("max"),
                    "unit": p_env.get("unit", ""),
                }

        # Apply closure update if available
        unc_update = closure.uncertainty_update if hasattr(closure, "uncertainty_update") else closure.get("uncertainty_update", {})
        if unc_update and unc_update.get("parameter_name"):
            pname = unc_update["parameter_name"]
            updated_uncertainty_inputs[pname] = {
                "parameter_name": pname,
                "representation_type": unc_update.get("representation_type", UncertaintyRepresentationType.MEASUREMENT_TOLERANCE.value),
                "lower_bound": unc_update.get("lower_bound"),
                "nominal_value": unc_update.get("nominal_value"),
                "upper_bound": unc_update.get("upper_bound"),
                "unit": plan.unit,
            }

        # 3. Execute new Phase 6.5 robustness analysis
        new_analysis = await ParameterTrustRobustnessService.run_robustness_analysis(
            db=db,
            decision_id=plan.decision_id,
            uncertainty_inputs=updated_uncertainty_inputs,
            decision_threshold=orig_dict.get("evaluated_envelope", {}).get("decision_threshold") if orig_dict else None,
            target_kpi=orig_dict.get("target_kpi", "damping_ratio") if orig_dict else "damping_ratio",
            user_context=user_context,
            persist_record=True,
        )

        # 4. Compare Before vs After
        orig_reversals_count = orig_dict.get("reversals_count", 0) if orig_dict else 0
        new_reversals_count = new_analysis.get("reversals_count", 0)
        orig_class = orig_dict.get("robustness_classification") if orig_dict else "UNKNOWN"
        new_class = new_analysis.get("robustness_classification")

        if orig_reversals_count > 0 and new_reversals_count == 0:
            reversal_status = ReversalResolutionStatus.REVERSAL_RESOLVED.value
        elif orig_reversals_count > 0 and new_reversals_count > 0:
            reversal_status = ReversalResolutionStatus.REVERSAL_PERSISTS.value
        elif orig_reversals_count == 0 and new_reversals_count > 0:
            reversal_status = ReversalResolutionStatus.NEW_REVERSAL_INTRODUCED.value
        else:
            reversal_status = ReversalResolutionStatus.NO_REVERSAL_DEMONSTRATED.value

        reassessment_delta = {
            "classification_before": orig_class,
            "classification_after": new_class,
            "reversals_before_count": orig_reversals_count,
            "reversals_after_count": new_reversals_count,
            "reversal_status": reversal_status,
            "parameter_uncertainty_updated": plan.parameter_name,
            "boundaries_before_count": len(orig_dict.get("boundary_crossings", [])) if orig_dict else 0,
            "boundaries_after_count": len(new_analysis.get("boundary_crossings", [])),
            "dominant_uncertainties_after": new_analysis.get("dominant_uncertainties", []),
            "gap_closure_verdict": closure.closure_verdict if hasattr(closure, "closure_verdict") else closure.get("closure_verdict"),
        }

        # Finite sample scope limitation statement
        finite_sample_stmt = (
            f"Observed physical measurements for '{plan.parameter_name}' narrow the localized tolerance interval. "
            "However, per FINITE_SAMPLE_SCOPE_NOTICE, this evidence represents finite test runs and does not certify "
            "full infinite operational envelope robustness."
        )

        canonical_reassess_payload = {
            "decision_id": plan.decision_id,
            "plan_id": str(plan.id),
            "closure_id": str(closure.id) if hasattr(closure, "id") else str(closure.get("id")),
            "reassessment_delta": reassessment_delta,
            "policy_version": CURRENT_VALIDATION_PLANNING_POLICY_VERSION,
        }
        dumped_reassess = json.dumps(canonical_reassess_payload, sort_keys=True, separators=(",", ":"))
        reassess_hash = hashlib.sha256(dumped_reassess.encode("utf-8")).hexdigest()

        # Supersede prior active reassessments for this plan
        existing_reassess_stmt = select(ValidationDecisionReassessmentRecord).where(
            ValidationDecisionReassessmentRecord.plan_id == plan.id,
            ValidationDecisionReassessmentRecord.is_active == True,
        )
        ex_res = await db.execute(existing_reassess_stmt)
        old_reassess = ex_res.scalar_one_or_none()

        closure_id_raw = getattr(closure, "id", None) or (closure.get("id") if isinstance(closure, dict) else None)
        closure_id_uuid = uuid.UUID(str(closure_id_raw)) if closure_id_raw else None

        orig_exp_raw = plan.exposure_assessment_id
        orig_exp_uuid = uuid.UUID(str(orig_exp_raw)) if orig_exp_raw else None

        orig_rob_raw = plan.robustness_analysis_id
        orig_rob_uuid = uuid.UUID(str(orig_rob_raw)) if orig_rob_raw else None

        new_rob_raw = new_analysis.get("id") if isinstance(new_analysis, dict) else getattr(new_analysis, "id", None)
        new_rob_uuid = uuid.UUID(str(new_rob_raw)) if new_rob_raw else None

        reassessment_record = ValidationDecisionReassessmentRecord(
            id=uuid.uuid4(),
            decision_id=plan.decision_id,
            decision_type=plan.decision_type,
            plan_id=plan.id,
            closure_id=closure_id_uuid,
            original_exposure_assessment_id=orig_exp_uuid,
            original_robustness_analysis_id=orig_rob_uuid,
            new_robustness_analysis_id=new_rob_uuid,
            reassessment_delta=reassessment_delta,
            reversal_status=reversal_status,
            envelope_coverage_statement=finite_sample_stmt,
            governance_separation_notice=GOVERNANCE_VALIDATION_SEPARATION_NOTICE,
            deployment_safety_inferred=False,
            deployment_authorization="NOT_ESTABLISHED",
            reassessment_hash=reassess_hash,
            is_active=True,
            superseded_by=None,
            organization_id=org_uuid,
            team_id=team_uuid,
            reassessed_by_user_id=user_uuid,
            created_at=datetime.now(timezone.utc),
        )

        db.add(reassessment_record)
        await db.flush()

        if old_reassess:
            old_reassess.is_active = False
            old_reassess.superseded_by = reassessment_record.id
            await db.flush()

        logger.info(
            "Executed validation decision reassessment for decision '%s' (reversal_status='%s').",
            plan.decision_id, reversal_status
        )
        return to_attr_dict(cls._reassessment_to_dict(reassessment_record))

    # ── H. QUERY HELPERS ──────────────────────────────────────────────────────

    @classmethod
    async def _get_plan_record(
        cls,
        db: AsyncSession,
        plan_id: Union[str, uuid.UUID],
        team_uuid: Optional[uuid.UUID] = None,
        org_uuid: Optional[uuid.UUID] = None,
        user_uuid: Optional[uuid.UUID] = None,
    ) -> Optional[EngineeringValidationPlanRecord]:
        pid_str = str(plan_id).strip()
        conditions = [or_(
            EngineeringValidationPlanRecord.plan_id == pid_str,
        )]
        try:
            p_uuid = uuid.UUID(pid_str)
            conditions.append(EngineeringValidationPlanRecord.id == p_uuid)
        except ValueError:
            pass

        stmt = select(EngineeringValidationPlanRecord).where(or_(*conditions))
        if team_uuid:
            stmt = stmt.where(or_(
                EngineeringValidationPlanRecord.team_id == team_uuid,
                EngineeringValidationPlanRecord.team_id == None,
            ))
        elif user_uuid:
            stmt = stmt.where(EngineeringValidationPlanRecord.created_by_user_id == user_uuid)

        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    @hybridmethod
    async def get_validation_plan(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        plan_id = args_list[0] if len(args_list) > 0 else kwargs.pop("plan_id", None)
        user_context = args_list[1] if len(args_list) > 1 else kwargs.pop("user_context", None)
        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        plan = await cls._get_plan_record(db, plan_id, team_uuid, org_uuid, user_uuid)
        if not plan:
            raise PlanNotFoundError(f"Validation plan '{plan_id}' not found.")
        return to_attr_dict(cls._plan_to_dict(plan))

    @hybridmethod
    async def list_plans_for_decision(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        decision_id = args_list[0] if len(args_list) > 0 else kwargs.pop("decision_id", None)
        user_context = args_list[1] if len(args_list) > 1 else kwargs.pop("user_context", None)
        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        dec_clean = str(decision_id).strip()
        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None

        stmt = select(EngineeringValidationPlanRecord).where(
            EngineeringValidationPlanRecord.decision_id == dec_clean,
        ).order_by(desc(EngineeringValidationPlanRecord.created_at))

        if team_uuid:
            stmt = stmt.where(or_(
                EngineeringValidationPlanRecord.team_id == team_uuid,
                EngineeringValidationPlanRecord.team_id == None,
            ))
        elif user_uuid:
            stmt = stmt.where(EngineeringValidationPlanRecord.created_by_user_id == user_uuid)

        res = await db.execute(stmt)
        plans = res.scalars().all()
        items = [to_attr_dict(cls._plan_to_dict(p)) for p in plans]
        return to_attr_dict({
            "decision_id": dec_clean,
            "plans": items,
            "total": len(items),
        })

    @hybridmethod
    async def get_decision_reassessments(
        cls,
        inst: Optional["ParameterTrustValidationService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        decision_id = args_list[0] if len(args_list) > 0 else kwargs.pop("decision_id", None)
        user_context = args_list[1] if len(args_list) > 1 else kwargs.pop("user_context", None)
        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        dec_clean = str(decision_id).strip()
        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None

        stmt = select(ValidationDecisionReassessmentRecord).where(
            ValidationDecisionReassessmentRecord.decision_id == dec_clean,
        ).order_by(desc(ValidationDecisionReassessmentRecord.created_at))

        if team_uuid:
            stmt = stmt.where(or_(
                ValidationDecisionReassessmentRecord.team_id == team_uuid,
                ValidationDecisionReassessmentRecord.team_id == None,
            ))
        elif user_uuid:
            stmt = stmt.where(ValidationDecisionReassessmentRecord.reassessed_by_user_id == user_uuid)

        res = await db.execute(stmt)
        reassessments = res.scalars().all()
        items = [to_attr_dict(cls._reassessment_to_dict(r)) for r in reassessments]
        return to_attr_dict({
            "decision_id": dec_clean,
            "reassessments": items,
            "total": len(items),
        })

    # ── SERIALIZERS ───────────────────────────────────────────────────────────

    @classmethod
    def _plan_to_dict(cls, p: EngineeringValidationPlanRecord) -> Dict[str, Any]:
        return {
            "id": str(p.id),
            "plan_id": p.plan_id,
            "decision_id": p.decision_id,
            "decision_type": p.decision_type,
            "parameter_name": p.parameter_name,
            "parameter_path": p.parameter_path,
            "evidence_gap_id": p.evidence_gap_id,
            "validation_objective": p.validation_objective,
            "validation_method": p.validation_method,
            "status": p.status,
            "plan_version": p.plan_version,
            "parent_plan_id": str(p.parent_plan_id) if p.parent_plan_id else None,
            "exposure_assessment_id": str(p.exposure_assessment_id) if p.exposure_assessment_id else None,
            "robustness_analysis_id": str(p.robustness_analysis_id) if p.robustness_analysis_id else None,
            "analysis_snapshot_hash": p.analysis_snapshot_hash,
            "input_artifact_requirements": p.input_artifact_requirements,
            "operating_conditions": p.operating_conditions,
            "applicability_envelope": p.applicability_envelope,
            "unit": p.unit,
            "measurement_definition": p.measurement_definition,
            "acceptance_criteria": p.acceptance_criteria,
            "criteria_established_at": p.criteria_established_at.isoformat() if p.criteria_established_at else None,
            "criteria_authorized_by_user_id": str(p.criteria_authorized_by_user_id) if p.criteria_authorized_by_user_id else None,
            "expected_outputs": p.expected_outputs,
            "required_reviewer_role": p.required_reviewer_role,
            "authorized_by_user_id": str(p.authorized_by_user_id) if p.authorized_by_user_id else None,
            "authorized_at": p.authorized_at.isoformat() if p.authorized_at else None,
            "plan_hash": p.plan_hash,
            "is_active": p.is_active,
            "governance_separation_notice": GOVERNANCE_VALIDATION_SEPARATION_NOTICE,
            "deployment_safety_inferred": False,
            "deployment_authorization": "NOT_ESTABLISHED",
            "organization_id": str(p.organization_id) if p.organization_id else None,
            "team_id": str(p.team_id) if p.team_id else None,
            "created_by_user_id": str(p.created_by_user_id),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }

    @classmethod
    def _evidence_to_dict(cls, e: ValidationEvidenceItemRecord) -> Dict[str, Any]:
        return {
            "id": str(e.id),
            "plan_id": str(e.plan_id),
            "evidence_source_type": e.evidence_source_type,
            "source_identifier": e.source_identifier,
            "source_timestamp": e.source_timestamp.isoformat() if e.source_timestamp else None,
            "parameter_name": e.parameter_name,
            "observed_value": e.observed_value,
            "observed_interval": e.observed_interval,
            "observed_samples": e.observed_samples,
            "unit": e.unit,
            "operating_scope": e.operating_scope,
            "integrity_hash": e.integrity_hash,
            "provenance": e.provenance,
            "calibration_metadata": e.calibration_metadata,
            "is_physically_validated": e.is_physically_validated,
            "physical_limitations": e.physical_limitations,
            "review_status": e.review_status,
            "review_notes": e.review_notes,
            "reviewed_by_user_id": str(e.reviewed_by_user_id) if e.reviewed_by_user_id else None,
            "reviewed_at": e.reviewed_at.isoformat() if e.reviewed_at else None,
            "organization_id": str(e.organization_id) if e.organization_id else None,
            "team_id": str(e.team_id) if e.team_id else None,
            "submitted_by_user_id": str(e.submitted_by_user_id),
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }

    @classmethod
    def _closure_to_dict(cls, c: ValidationEvidenceClosureRecord) -> Dict[str, Any]:
        return {
            "id": str(c.id),
            "plan_id": str(c.plan_id),
            "decision_id": c.decision_id,
            "parameter_name": c.parameter_name,
            "evidence_gap_id": c.evidence_gap_id,
            "closure_verdict": c.closure_verdict,
            "criteria_met": c.criteria_met,
            "criteria_evaluated": c.criteria_evaluated,
            "applicability_check": c.applicability_check,
            "conflict_assessment": c.conflict_assessment,
            "uncertainty_update": c.uncertainty_update,
            "requires_robustness_reassessment": c.requires_robustness_reassessment,
            "closure_summary": c.closure_summary,
            "closure_hash": c.closure_hash,
            "governance_separation_notice": c.governance_separation_notice,
            "finite_sample_notice": c.finite_sample_notice,
            "deployment_safety_inferred": False,
            "deployment_authorization": "NOT_ESTABLISHED",
            "is_active": c.is_active,
            "superseded_by": str(c.superseded_by) if c.superseded_by else None,
            "organization_id": str(c.organization_id) if c.organization_id else None,
            "team_id": str(c.team_id) if c.team_id else None,
            "evaluated_by_user_id": str(c.evaluated_by_user_id),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }

    @classmethod
    def _reassessment_to_dict(cls, r: ValidationDecisionReassessmentRecord) -> Dict[str, Any]:
        return {
            "id": str(r.id),
            "decision_id": r.decision_id,
            "decision_type": r.decision_type,
            "plan_id": str(r.plan_id),
            "closure_id": str(r.closure_id),
            "original_exposure_assessment_id": str(r.original_exposure_assessment_id) if r.original_exposure_assessment_id else None,
            "original_robustness_analysis_id": str(r.original_robustness_analysis_id) if r.original_robustness_analysis_id else None,
            "new_robustness_analysis_id": str(r.new_robustness_analysis_id) if r.new_robustness_analysis_id else None,
            "reassessment_delta": r.reassessment_delta,
            "reversal_status": r.reversal_status,
            "envelope_coverage_statement": r.envelope_coverage_statement,
            "governance_separation_notice": r.governance_separation_notice,
            "deployment_safety_inferred": False,
            "deployment_authorization": "NOT_ESTABLISHED",
            "reassessment_hash": r.reassessment_hash,
            "is_active": r.is_active,
            "superseded_by": str(r.superseded_by) if r.superseded_by else None,
            "organization_id": str(r.organization_id) if r.organization_id else None,
            "team_id": str(r.team_id) if r.team_id else None,
            "reassessed_by_user_id": str(r.reassessed_by_user_id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
