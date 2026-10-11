"""
backend/services/parameter_trust_decision_service.py
===================================================
SuspensionLab PRO — Phase 6.4 Decision-Aware Parameter Trust &
Engineering Evidence Integration Service.

Answers core engineering decision-support questions:
1. Which uncertain or conflicting parameters materially affect my engineering question?
2. Which conclusions depend on those parameters?
3. What evidence supports each parameter's trust assessment?
4. Which evidence is missing, stale, contradictory, or outside the relevant operating conditions?
5. Which engineering experiment or validation activity could reduce the uncertainty?
6. What happens to the decision's evidentiary status when underlying parameter evidence changes?

Strict Invariants & Hard Boundaries:
1. Reuses existing authoritative models: EngineeringDecision, EngineeringProblemRecord, InvestigationRecord.
   Zero parallel decision or evidence stores created.
2. Distinct concepts strictly preserved:
   - Parameter Trust (component/local state)
   - Sensitivity or Impact (downstream physical derivative)
   - Evidence Completeness (data coverage & recency)
   - Decision Exposure (vulnerability of decision premises)
   - Approval Authorization (human role sign-off)
   - Deployment Safety (independent commissioning gate, NEVER inferred)
3. Zero universal score compression: explicit qualitative classifications only.
4. Qualitative causal mechanisms NEVER fabricate numerical derivatives.
5. Missing sensitivity is NEVER treated as zero or low impact.
6. Active conflicts strictly override holdout validation gates.
7. Phase 5 pre-reveal firewall strictly preserved: unrevealed blind data is inaccessible.
8. Evidence Graph vocabulary unchanged: strictly 17 frozen canonical relationships.
9. Deterministic reproducible input snapshots and cryptographic SHA-256 hashes.
"""
from __future__ import annotations

import collections
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy import and_, or_, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

# Database Models
from suspensionlab.backend.database.models.parameter_trust import (
    ParameterTrustProfile,
    ParameterTrustEvidenceRecord,
    ParameterTrustAssessmentRecord,
    ParameterTrustFleetReport,
    ParameterTrustAssemblyImpactRecord,
    DecisionParameterDependencyRecord,
    DecisionExposureAssessmentRecord,
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    TrustConflictType,
    SensitivityStatus,
    ImpactClassification,
    RecencyCondition,
    DependencyNature,
    DecisionExposureClassification,
    EvidenceGapSeverity,
    DECISION_TRUST_POLICY_V1,
    CURRENT_DECISION_TRUST_POLICY_VERSION,
    SENSITIVITY_PROPAGATION_POLICY_V1,
    SENSITIVITY_THRESHOLDS_PROVENANCE,
    SENSITIVITY_THRESHOLDS_METADATA,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.decision_loop import (
    InvestigationRecord,
    BlindValidationRecord,
    SetupComparisonRecord,
    OptimizationRecord,
    ApprovalRecord,
)
from suspensionlab.backend.database.models.setup_engineering import (
    EngineeringProblemRecord,
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
    PostTrackReconciliationRecord,
)
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
    SupportedEntityType,
)
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSessionStatus,
)

# Services
from suspensionlab.backend.services.parameter_trust_service import (
    ParameterTrustService,
    canonicalize_parameter_unit,
    compute_value_identity,
)
from suspensionlab.backend.services.parameter_trust_fleet_service import (
    ParameterTrustFleetService,
    resolve_assembly_component,
)
from suspensionlab.backend.services.evidence_graph_service import (
    EvidenceGraphService,
    EntityNotFoundError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
    MalformedIdentifierError,
)

logger = logging.getLogger(__name__)


class DecisionTrustError(Exception):
    """Base error for Phase 6.4 decision trust operations."""
    pass


class DecisionNotFoundError(DecisionTrustError):
    """Raised when an engineering decision or problem cannot be located."""
    pass


class PreRevealFirewallViolation(DecisionTrustError):
    """Raised when an operation attempts to access unrevealed Phase 5 blind evaluation data."""
    pass


class AttrDict(dict):
    """Dictionary subclass with attribute-style access."""
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'AttrDict' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError:
            raise AttributeError(f"'AttrDict' object has no attribute '{name}'")


def to_attr_dict(val: Any) -> Any:
    """Recursively wraps dicts in AttrDict for dual attr/key access."""
    if isinstance(val, dict):
        return AttrDict({k: to_attr_dict(v) for k, v in val.items()})
    elif isinstance(val, list):
        return [to_attr_dict(v) for v in val]
    return val


class ResolvedDecision(tuple):
    """
    Hybrid representation of a resolved decision entity.
    Can be unpacked as a 2-tuple `(entity, dtype)`:
        dec, dtype = await svc.resolve_decision(...)
    Or used directly as an AttrDict / dict:
        info["decision_id"], info.decision_id, info.get(...)
    """
    def __new__(cls, entity: Any, dtype: str):
        return super().__new__(cls, (entity, dtype))

    @property
    def entity(self) -> Any:
        return self[0]

    @property
    def dtype(self) -> str:
        return self[1]

    def __getattr__(self, name: str) -> Any:
        if name in ("entity", "dtype"):
            return object.__getattribute__(self, name)
        if hasattr(self[0], name):
            return getattr(self[0], name)
        if isinstance(self[0], dict) and name in self[0]:
            return self[0][name]
        raise AttributeError(f"'ResolvedDecision' object has no attribute '{name}'")

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return super().__getitem__(key)
        if key == "decision_type":
            return self[1]
        if isinstance(self[0], dict):
            return self[0][key]
        return getattr(self[0], key)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "decision_type":
            return self[1]
        if isinstance(self[0], dict):
            return self[0].get(key, default)
        return getattr(self[0], key, default)

    def keys(self):
        if isinstance(self[0], dict):
            k = set(self[0].keys())
            k.add("decision_type")
            return list(k)
        return []

    def values(self):
        return [self.get(k) for k in self.keys()]

    def items(self):
        return [(k, self.get(k)) for k in self.keys()]

    def __contains__(self, key: Any) -> bool:
        if key == "decision_type":
            return True
        if isinstance(self[0], dict):
            return key in self[0]
        return hasattr(self[0], key)


class hybridmethod:
    """Decorator allowing a method to be called either on an instance or on the class."""
    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        if instance is None:
            async def class_wrapper(*args, **kwargs):
                return await self.func(owner, None, *args, **kwargs)
            return class_wrapper
        else:
            async def instance_wrapper(*args, **kwargs):
                return await self.func(owner, instance, *args, **kwargs)
            return instance_wrapper


def _extract_scope(
    user_context: Optional[Any],
    team_id: Optional[Union[str, uuid.UUID]] = None,
    organization_id: Optional[Union[str, uuid.UUID]] = None,
    user_id: Optional[Union[str, uuid.UUID]] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if user_context is not None:
        if hasattr(user_context, "team_id"):
            team_id = getattr(user_context, "team_id")
        elif isinstance(user_context, dict) and "team_id" in user_context:
            team_id = user_context["team_id"]

        if hasattr(user_context, "organization_id"):
            organization_id = getattr(user_context, "organization_id")
        elif isinstance(user_context, dict) and "organization_id" in user_context:
            organization_id = user_context["organization_id"]

        if hasattr(user_context, "user_id"):
            user_id = getattr(user_context, "user_id")
        elif isinstance(user_context, dict) and "user_id" in user_context:
            user_id = user_context["user_id"]
    return (
        str(team_id) if team_id else None,
        str(organization_id) if organization_id else None,
        str(user_id) if user_id else None,
    )


class ParameterTrustDecisionService:
    """
    Authoritative service implementing Phase 6.4 Decision-Aware Parameter Trust
    under DECISION_TRUST_POLICY_V1.
    Supports both instance usage `svc = ParameterTrustDecisionService(db)`
    and classmethod usage `ParameterTrustDecisionService.resolve_decision(db=db, ...)`.
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    # ── A. RESOLVE & AUTHORIZE ENGINEERING DECISION ───────────────────────────

    @hybridmethod
    async def resolve_decision(
        cls,
        inst: Optional["ParameterTrustDecisionService"],
        *args,
        **kwargs,
    ) -> ResolvedDecision:
        """
        Resolves an authoritative engineering decision, problem, or investigation,
        enforcing strict multi-tenant boundaries and the Phase 5 pre-reveal firewall.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        decision_id = args_list[0] if len(args_list) > 0 else kwargs.pop("decision_id", None)
        decision_type = args_list[1] if len(args_list) > 1 else kwargs.pop("decision_type", "EngineeringDecision")
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        dec_clean = str(decision_id).strip()
        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        # 1. Phase 5 Pre-Reveal Firewall Check
        try:
            stmt_blind = select(BlindEngineeringSession).where(
                or_(
                    BlindEngineeringSession.name == dec_clean,
                    BlindEngineeringSession.root_entity_id == dec_clean,
                    BlindEngineeringSession.hidden_outcome_id == dec_clean,
                    BlindEngineeringSession.id == uuid.UUID(dec_clean) if len(dec_clean) == 36 else False,
                )
            )
            res_blind = await db.execute(stmt_blind)
            blind_session = res_blind.scalars().first()
            if blind_session and blind_session.status not in (
                BlindSessionStatus.REVEALED.value,
                BlindSessionStatus.COMPLETED.value,
            ):
                raise PreRevealFirewallViolation(
                    f"Phase 5 Pre-Reveal Firewall Violation: Blind engineering session '{dec_clean}' "
                    f"is in state '{blind_session.status}'. Unrevealed ground truth holdout data cannot be accessed."
                )
        except PreRevealFirewallViolation:
            raise
        except Exception:
            pass

        # 2. Polymorphic Entity Resolution
        # 2a. Primary: EngineeringDecision
        stmt_dec = select(EngineeringDecision).where(EngineeringDecision.decision_id == dec_clean)
        res_dec = await db.execute(stmt_dec)
        dec_obj = res_dec.scalars().first()

        if dec_obj:
            # Check context for unrevealed blind session reference
            ctx = dec_obj.context or {}
            blind_ref = ctx.get("blind_session_id") or ctx.get("session_id")
            if blind_ref:
                stmt_bref = select(BlindEngineeringSession).where(
                    or_(
                        BlindEngineeringSession.name == blind_ref,
                        BlindEngineeringSession.root_entity_id == blind_ref,
                        BlindEngineeringSession.id == uuid.UUID(str(blind_ref)) if len(str(blind_ref)) == 36 else False,
                    )
                )
                res_bref = await db.execute(stmt_bref)
                b_sess = res_bref.scalars().first()
                if b_sess and b_sess.status not in (
                    BlindSessionStatus.REVEALED.value,
                    BlindSessionStatus.COMPLETED.value,
                ):
                    raise PreRevealFirewallViolation(
                        f"Phase 5 Pre-Reveal Firewall Violation: Decision '{dec_clean}' references "
                        f"unrevealed blind session '{blind_ref}' (status '{b_sess.status}'). Access blocked."
                    )

            # Tenant isolation check
            if team_uuid and dec_obj.team_id and dec_obj.team_id != team_uuid:
                raise TenantIsolationError(
                    f"Access denied: Decision '{dec_clean}' belongs to team '{dec_obj.team_id}', unauthorized for '{team_uuid}'."
                )
            if not team_uuid and user_uuid and dec_obj.user_id != user_uuid:
                raise TenantIsolationError(
                    f"Access denied: Decision '{dec_clean}' is isolated to user '{dec_obj.user_id}'."
                )

            entity_data = AttrDict({
                "decision_id": dec_obj.decision_id,
                "decision_type": "EngineeringDecision",
                "question": dec_obj.question,
                "context": dec_obj.context or {},
                "candidates": dec_obj.candidates or [],
                "selected_option": dec_obj.selected_option or {},
                "reason": dec_obj.reason,
                "tradeoffs": dec_obj.tradeoffs or {},
                "risks": dec_obj.risks or {},
                "simulation_evidence": dec_obj.simulation_evidence or [],
                "telemetry_evidence": dec_obj.telemetry_evidence or [],
                "validation_evidence": dec_obj.validation_evidence or [],
                "status": dec_obj.status,
                "author": dec_obj.author,
                "approver": dec_obj.approver,
                "approved_at": dec_obj.approved_at.isoformat() if dec_obj.approved_at else None,
                "approval_signature": dec_obj.approval_signature,
                "artifact_hashes": dec_obj.artifact_hashes or {},
                "team_id": dec_obj.team_id,
                "user_id": dec_obj.user_id,
                "created_at": dec_obj.created_at.isoformat() if dec_obj.created_at else None,
            })
            return ResolvedDecision(entity_data, "EngineeringDecision")

        # 2b. Secondary: EngineeringProblemRecord
        stmt_prob = select(EngineeringProblemRecord).where(EngineeringProblemRecord.problem_id == dec_clean)
        res_prob = await db.execute(stmt_prob)
        prob_obj = res_prob.scalars().first()

        if prob_obj:
            if team_uuid and prob_obj.team_id and prob_obj.team_id != team_uuid:
                raise TenantIsolationError(
                    f"Access denied: Problem '{dec_clean}' belongs to team '{prob_obj.team_id}', unauthorized for '{team_uuid}'."
                )
            if not team_uuid and user_uuid and prob_obj.user_id != user_uuid:
                raise TenantIsolationError(
                    f"Access denied: Problem '{dec_clean}' is isolated to user '{prob_obj.user_id}'."
                )

            entity_data = AttrDict({
                "decision_id": prob_obj.problem_id,
                "problem_id": prob_obj.problem_id,
                "decision_type": "EngineeringProblemRecord",
                "question": prob_obj.observable,
                "observable": prob_obj.observable,
                "context": {
                    "operating_condition": prob_obj.operating_condition or {},
                    "track_context": prob_obj.track_context or {},
                    "session_context": prob_obj.session_context or {},
                    "telemetry_session_id": prob_obj.telemetry_session_id,
                    "investigation_id": prob_obj.investigation_id,
                    "engineering_question_id": prob_obj.engineering_question_id,
                },
                "candidates": [],
                "selected_option": {},
                "reason": "Engineering problem definition",
                "tradeoffs": {},
                "risks": {},
                "simulation_evidence": [],
                "telemetry_evidence": [{"baseline_metric": prob_obj.baseline_metric}],
                "validation_evidence": [{"target_metric": prob_obj.target_metric}],
                "status": "PROBLEM_OPEN",
                "author": "Engineering Team",
                "approver": None,
                "approved_at": None,
                "approval_signature": None,
                "artifact_hashes": {"problem_hash": prob_obj.artifact_hash},
                "team_id": prob_obj.team_id,
                "user_id": prob_obj.user_id,
                "created_at": prob_obj.created_at.isoformat() if prob_obj.created_at else None,
            })
            return ResolvedDecision(entity_data, "EngineeringProblemRecord")

        # 2c. Tertiary: InvestigationRecord
        stmt_inv = select(InvestigationRecord).where(
            or_(
                InvestigationRecord.investigation_code == dec_clean,
                InvestigationRecord.id == uuid.UUID(dec_clean) if len(dec_clean) == 36 else False,
            )
        )
        res_inv = await db.execute(stmt_inv)
        inv_obj = res_inv.scalars().first()

        if inv_obj:
            if team_uuid and inv_obj.team_id and inv_obj.team_id != team_uuid:
                raise TenantIsolationError(
                    f"Access denied: Investigation '{dec_clean}' belongs to team '{inv_obj.team_id}', unauthorized for '{team_uuid}'."
                )
            if not team_uuid and user_uuid and inv_obj.user_id != user_uuid:
                raise TenantIsolationError(
                    f"Access denied: Investigation '{dec_clean}' is isolated to user '{inv_obj.user_id}'."
                )

            entity_data = AttrDict({
                "decision_id": inv_obj.investigation_code,
                "investigation_id": inv_obj.investigation_code,
                "investigation_code": inv_obj.investigation_code,
                "decision_type": "InvestigationRecord",
                "question": inv_obj.symptom,
                "symptom": inv_obj.symptom,
                "context": {
                    "detection_type": inv_obj.detection_type,
                    "affected_regime": inv_obj.affected_regime,
                    "session_code": inv_obj.session_code,
                    "severity": inv_obj.severity,
                },
                "candidates": [],
                "selected_option": {},
                "reason": f"Anomaly Investigation {inv_obj.detection_type}",
                "tradeoffs": {},
                "risks": {},
                "simulation_evidence": [],
                "telemetry_evidence": [inv_obj.evidence_snapshot] if inv_obj.evidence_snapshot else [],
                "validation_evidence": [],
                "status": inv_obj.status,
                "author": "Telemetry Analyst",
                "approver": None,
                "approved_at": None,
                "approval_signature": None,
                "artifact_hashes": {"investigation_hash": inv_obj.artifact_hash},
                "team_id": inv_obj.team_id,
                "user_id": inv_obj.user_id,
                "created_at": inv_obj.created_at.isoformat() if inv_obj.created_at else None,
            })
            return ResolvedDecision(entity_data, "InvestigationRecord")

        raise DecisionNotFoundError(f"Engineering decision, problem, or investigation '{dec_clean}' not found.")

    # ── B. DISCOVER DECISION PARAMETER DEPENDENCIES ───────────────────────────

    @hybridmethod
    async def discover_decision_dependencies(
        cls,
        inst: Optional["ParameterTrustDecisionService"],
        *args,
        **kwargs,
    ) -> List[Any]:
        """
        Extracts, classifies, and traceably associates all parameters relevant
        to the engineering decision.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        dec_or_info = args_list[0] if len(args_list) > 0 else (kwargs.pop("decision_info", None) or kwargs.pop("decision", None))
        user_context = args_list[1] if len(args_list) > 1 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        # If dec_or_info is a string or not resolved, resolve it
        if isinstance(dec_or_info, str):
            dec_or_info = await cls.resolve_decision(
                db=db,
                decision_id=dec_or_info,
                team_id=team_uuid,
                organization_id=org_uuid,
                user_id=user_uuid,
            )

        decision_id = dec_or_info.get("decision_id") if hasattr(dec_or_info, "get") else getattr(dec_or_info, "decision_id", "")
        decision_type = dec_or_info.get("decision_type") if hasattr(dec_or_info, "get") else getattr(dec_or_info, "decision_type", "EngineeringDecision")

        parameters_map: Dict[str, Dict[str, Any]] = {}

        # 1. Discover parameters from Candidate Setups / Selected Option
        candidates = dec_or_info.get("candidates", []) if hasattr(dec_or_info, "get") else getattr(dec_or_info, "candidates", [])
        selected_option = dec_or_info.get("selected_option", {}) if hasattr(dec_or_info, "get") else getattr(dec_or_info, "selected_option", {})
        all_setup_sources = []
        if isinstance(selected_option, dict) and "setup_id" in selected_option:
            all_setup_sources.append(selected_option["setup_id"])
        elif isinstance(selected_option, str) and selected_option:
            all_setup_sources.append(selected_option)

        for c in candidates:
            if isinstance(c, dict) and "setup_id" in c:
                all_setup_sources.append(c["setup_id"])
            elif isinstance(c, str):
                all_setup_sources.append(c)

        for sid in set(all_setup_sources):
            stmt_sc = select(SetupCandidateRecord).where(SetupCandidateRecord.setup_id == sid)
            # Tenant isolation on candidates
            if team_uuid:
                stmt_sc = stmt_sc.where(SetupCandidateRecord.team_id == team_uuid)
            elif user_uuid:
                stmt_sc = stmt_sc.where(SetupCandidateRecord.user_id == user_uuid)

            res_sc = await db.execute(stmt_sc)
            sc_rec = res_sc.scalars().first()
            if sc_rec:
                ch = sc_rec.changed_parameters or {}
                for pname, pinfo in ch.items():
                    val = pinfo.get("candidate") if isinstance(pinfo, dict) else pinfo
                    unit = pinfo.get("unit", "") if isinstance(pinfo, dict) else ""
                    if pname not in parameters_map:
                        parameters_map[pname] = {
                            "parameter_name": pname,
                            "entity_type": "SetupCandidate",
                            "entity_id": sc_rec.setup_id,
                            "value": val,
                            "unit": unit,
                            "provenance_hint": (sc_rec.parameter_provenance or {}).get(pname, "optimization"),
                            "source_evidence_ids": [sc_rec.setup_id],
                            "source_artifact_hashes": [sc_rec.artifact_hash] if sc_rec.artifact_hash else [],
                            "operating_conditions": sc_rec.validity_domain or {},
                            "model_version": sc_rec.model_version,
                            "in_selected_setup": (sid == selected_option.get("setup_id", "") or sid == selected_option),
                        }

                unch = sc_rec.unchanged_parameters or {}
                for pname, val in unch.items():
                    if pname not in parameters_map:
                        parameters_map[pname] = {
                            "parameter_name": pname,
                            "entity_type": "SetupCandidate",
                            "entity_id": sc_rec.setup_id,
                            "value": val,
                            "unit": "",
                            "provenance_hint": "baseline",
                            "source_evidence_ids": [sc_rec.setup_id],
                            "source_artifact_hashes": [sc_rec.artifact_hash] if sc_rec.artifact_hash else [],
                            "operating_conditions": sc_rec.validity_domain or {},
                            "model_version": sc_rec.model_version,
                            "in_selected_setup": False,
                        }

        # 2. Discover parameters from Causal Hypotheses
        stmt_hyp = select(CausalHypothesisRecord).where(
            or_(
                CausalHypothesisRecord.problem_id == decision_id,
                CausalHypothesisRecord.hypothesis_id == decision_id,
            )
        )
        if team_uuid:
            stmt_hyp = stmt_hyp.where(CausalHypothesisRecord.team_id == team_uuid)
        elif user_uuid:
            stmt_hyp = stmt_hyp.where(CausalHypothesisRecord.user_id == user_uuid)

        res_hyp = await db.execute(stmt_hyp)
        hyp_records = res_hyp.scalars().all()

        hyp_parameters: Dict[str, CausalHypothesisRecord] = {}
        for hyp in hyp_records:
            cand_params = hyp.candidate_parameters or []
            for cp in cand_params:
                hyp_parameters[cp] = hyp
                if cp not in parameters_map:
                    parameters_map[cp] = {
                        "parameter_name": cp,
                        "entity_type": "CausalHypothesis",
                        "entity_id": hyp.hypothesis_id,
                        "value": None,
                        "unit": "",
                        "provenance_hint": "hypothesis",
                        "source_evidence_ids": [hyp.hypothesis_id],
                        "source_artifact_hashes": [hyp.artifact_hash] if hyp.artifact_hash else [],
                        "operating_conditions": {},
                        "model_version": hyp.model_version,
                        "in_selected_setup": False,
                        "is_pure_hypothesis": True,
                    }

        # 3. Discover parameters from Telemetry Investigation snapshot
        telemetry_ev = dec_or_info.get("telemetry_evidence", []) if hasattr(dec_or_info, "get") else getattr(dec_or_info, "telemetry_evidence", [])
        if isinstance(telemetry_ev, list):
            for t_item in telemetry_ev:
                if isinstance(t_item, dict) and "affected_parameters" in t_item:
                    for aff_p in t_item["affected_parameters"]:
                        if aff_p not in parameters_map:
                            parameters_map[aff_p] = {
                                "parameter_name": aff_p,
                                "entity_type": "Investigation",
                                "entity_id": decision_id,
                                "value": None,
                                "unit": "",
                                "provenance_hint": "telemetry_anomaly",
                                "source_evidence_ids": [decision_id],
                                "source_artifact_hashes": [],
                                "operating_conditions": dec_or_info.get("context", {}) if hasattr(dec_or_info, "get") else {},
                                "model_version": "v2.6",
                                "in_selected_setup": False,
                            }

        default_vehicle_id = (
            (dec_or_info.get("context", {}).get("vehicle_id") if hasattr(dec_or_info, "get") else None)
            or (all_setup_sources[0] if all_setup_sources else None)
            or decision_id
        )

        dependencies: List[Any] = []

        # 4. Resolve trust profiles and sensitivity evidence for every discovered parameter
        for pname, pmeta in parameters_map.items():
            param_clean = pname.strip()
            entity_type = pmeta["entity_type"]
            entity_id = pmeta["entity_id"]
            model_ver = pmeta.get("model_version", "v2.6")
            op_conditions = pmeta.get("operating_conditions", {})

            # 4a. Retrieve direct parameter trust profile
            profile = None
            stmt_prof = select(ParameterTrustProfile).where(
                ParameterTrustProfile.parameter_name == param_clean,
                ParameterTrustProfile.entity_id == entity_id,
            )
            if team_uuid:
                stmt_prof = stmt_prof.where(ParameterTrustProfile.team_id == team_uuid)
            elif user_uuid:
                stmt_prof = stmt_prof.where(ParameterTrustProfile.created_by_user_id == user_uuid)
            res_prof = await db.execute(stmt_prof)
            profile = res_prof.scalars().first()

            if not profile:
                try:
                    profile = await ParameterTrustService.get_or_assess_parameter_trust(
                        db=db,
                        entity_type=entity_type if entity_type in ["SetupCandidate", "VehicleProfile", "VehicleTwin"] else "SetupCandidate",
                        entity_id=entity_id if entity_type in ["SetupCandidate", "VehicleProfile", "VehicleTwin"] else default_vehicle_id,
                        parameter_name=param_clean,
                        team_id=team_uuid,
                        organization_id=org_uuid,
                        user_id=user_uuid,
                    )
                except Exception as e:
                    logger.debug("Profile lookup for %s yielded exception: %s", param_clean, e)

            # Query evidence records for recency if needed
            profile_recency = dict(profile.recency_metadata or {}) if profile else {}
            if profile and not profile_recency.get("age_days"):
                stmt_evs = select(ParameterTrustEvidenceRecord).where(
                    ParameterTrustEvidenceRecord.profile_id == profile.id
                )
                res_evs = await db.execute(stmt_evs)
                ev_recs = res_evs.scalars().all()
                if ev_recs:
                    timestamps = [e.evidence_timestamp for e in ev_recs if e.evidence_timestamp]
                    if not timestamps:
                        timestamps = [e.created_at for e in ev_recs if e.created_at]
                    if timestamps:
                        latest_ts = max(timestamps)
                        now_utc = datetime.now(timezone.utc)
                        if latest_ts.tzinfo is None:
                            latest_ts = latest_ts.replace(tzinfo=timezone.utc)
                        age_days = (now_utc - latest_ts).total_seconds() / 86400.0
                        profile_recency["age_days"] = int(age_days)
                        if age_days > 180:
                            profile_recency["recency_condition"] = RecencyCondition.VALIDITY_EXPIRED.value
                        else:
                            profile_recency["recency_condition"] = RecencyCondition.VALID.value

            # 4b. Resolve Authoritative Sensitivity Evidence
            sens_evidence = await ParameterTrustFleetService.resolve_sensitivity_evidence(
                db=db,
                parameter_name=param_clean,
                vehicle_id=entity_id if entity_type in ["SetupCandidate", "VehicleProfile"] else default_vehicle_id,
                team_id=team_uuid,
                organization_id=org_uuid,
                user_id=user_uuid,
            )

            downstream_metrics = sens_evidence.get("downstream_metrics", [])
            numerical_metrics = [
                m for m in downstream_metrics
                if isinstance(m, dict) and m.get("elasticity") is not None and m.get("is_numerical_derivative", True) is not False
            ]
            has_numerical_sensitivity = len(numerical_metrics) > 0

            # 4c. Classify Dependency Nature & Sensitivity Status
            dependency_nature = DependencyNature.UNRESOLVED_DEPENDENCY.value
            elasticity_val: Optional[float] = None
            numerical_deriv_val: Optional[float] = None
            derivative_unit: Optional[str] = None
            kpi_metrics: List[str] = []

            if has_numerical_sensitivity:
                dependency_nature = DependencyNature.QUANTITATIVELY_SENSITIVE.value
                top_m = max(numerical_metrics, key=lambda m: abs(m["elasticity"]))
                elasticity_val = float(top_m["elasticity"])
                numerical_deriv_val = float(top_m.get("numerical_derivative")) if top_m.get("numerical_derivative") is not None else None
                derivative_unit = top_m.get("unit")
                kpi_metrics = [m["metric"] for m in numerical_metrics]

                if profile and profile.validation_coverage == ValidationCoverage.VALIDATED.value and pmeta.get("in_selected_setup"):
                    dependency_nature = DependencyNature.DIRECTLY_EVIDENCED.value

                sens_status = SensitivityStatus.AVAILABLE.value
            elif param_clean in hyp_parameters or pmeta.get("is_pure_hypothesis"):
                dependency_nature = DependencyNature.QUALITATIVE_HYPOTHESIS.value
                hyp_rec = hyp_parameters.get(param_clean)
                kpi_metrics = hyp_rec.affected_observables if hyp_rec and hyp_rec.affected_observables else []
                elasticity_val = None
                numerical_deriv_val = None
                derivative_unit = "directional_trend"
                sens_status = SensitivityStatus.SENSITIVITY_UNAVAILABLE.value
            elif profile and profile.validation_coverage == ValidationCoverage.VALIDATED.value:
                dependency_nature = DependencyNature.DIRECTLY_EVIDENCED.value
                elasticity_val = None
                derivative_unit = None
                kpi_metrics = ["vehicle_compliance"]
                sens_status = SensitivityStatus.SENSITIVITY_UNAVAILABLE.value
            else:
                dependency_nature = DependencyNature.UNRESOLVED_DEPENDENCY.value
                elasticity_val = None
                derivative_unit = None
                sens_status = SensitivityStatus.SENSITIVITY_UNAVAILABLE.value

            ev_ids = list(pmeta.get("source_evidence_ids", []))
            ev_hashes = list(pmeta.get("source_artifact_hashes", []))
            if sens_evidence.get("source_id"):
                ev_ids.append(f"{sens_evidence.get('source_type')}:{sens_evidence.get('source_id')}")
            if sens_evidence.get("artifact_hash"):
                ev_hashes.append(sens_evidence.get("artifact_hash"))
            if profile and profile.assessment_hash:
                ev_hashes.append(profile.assessment_hash)

            dep_entry = {
                "decision_id": decision_id,
                "decision_type": decision_type,
                "parameter_name": param_clean,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "dependency_nature": dependency_nature,
                "kpi_metrics": kpi_metrics,
                "sensitivity_status": sens_status,
                "elasticity": elasticity_val,
                "numerical_derivative": numerical_deriv_val,
                "derivative_unit": derivative_unit,
                "source_artifact_hashes": list(set(ev_hashes)),
                "source_evidence_ids": list(set(ev_ids)),
                "operating_conditions": op_conditions,
                "model_version": model_ver,
                "notes": (
                    "Directional causal hypothesis mechanism; not a measured numerical derivative."
                    if dependency_nature == DependencyNature.QUALITATIVE_HYPOTHESIS.value
                    else "Authoritative dependency link."
                ),
                "direct_profile": {
                    "trust_state": profile.current_trust_state if profile else TrustState.UNASSESSED.value,
                    "validation_coverage": profile.validation_coverage if profile else ValidationCoverage.NO_VALIDATION.value,
                    "conflicts": profile.conflicts if profile else [],
                    "recency_metadata": profile_recency,
                    "assessment_hash": profile.assessment_hash if profile else None,
                },
            }
            dependencies.append(to_attr_dict(dep_entry))

        return dependencies

    # ── C. ASSESS DECISION EXPOSURE UNDER DECISION_TRUST_POLICY_V1 ────────────

    @hybridmethod
    async def assess_decision_exposure(
        cls,
        inst: Optional["ParameterTrustDecisionService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Executes a deterministic, versioned decision exposure assessment under DECISION_TRUST_POLICY_V1.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        decision_id = args_list[0] if len(args_list) > 0 else kwargs.pop("decision_id", None)
        decision_type = args_list[1] if len(args_list) > 1 else kwargs.pop("decision_type", "EngineeringDecision")
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        dec_clean = str(decision_id).strip()
        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None
        policy_version = CURRENT_DECISION_TRUST_POLICY_VERSION

        force_reassess = kwargs.pop("force_reassess", False)
        persist_record = kwargs.pop("persist_record", True)

        # 1. Resolve and authenticate decision record
        decision_info = await cls.resolve_decision(
            db=db,
            decision_id=dec_clean,
            decision_type=decision_type,
            team_id=team_uuid,
            organization_id=org_uuid,
            user_id=user_uuid,
        )

        # 2. Check existing active assessment
        stmt_exist = select(DecisionExposureAssessmentRecord).where(
            DecisionExposureAssessmentRecord.decision_id == dec_clean,
            DecisionExposureAssessmentRecord.is_active.is_(True),
        )
        if team_uuid:
            stmt_exist = stmt_exist.where(DecisionExposureAssessmentRecord.team_id == team_uuid)
        elif user_uuid:
            stmt_exist = stmt_exist.where(DecisionExposureAssessmentRecord.user_id == user_uuid)

        stmt_exist = stmt_exist.order_by(desc(DecisionExposureAssessmentRecord.created_at)).limit(1)
        res_exist = await db.execute(stmt_exist)
        existing_assessment = res_exist.scalars().first()

        # 3. Discover and trace parameter dependencies
        dependencies = await cls.discover_decision_dependencies(
            db=db,
            decision_info=decision_info,
            team_id=team_uuid,
            organization_id=org_uuid,
            user_id=user_uuid,
        )

        # 4. Generate Actionable Evidence Gaps & Synthesize Exposure
        evidence_gaps: List[Dict[str, Any]] = []
        actionable_recommendations: List[Dict[str, Any]] = []

        has_scope_or_unit_mismatch = False
        has_active_conflict = False
        has_high_sensitivity_unvalidated = False
        has_moderate_sensitivity_unvalidated = False
        has_stale_evidence = False
        all_sensitivities_unavailable = True

        for dep in dependencies:
            pname = dep["parameter_name"]
            profile_data = dep["direct_profile"]
            trust_state = profile_data["trust_state"]
            val_cov = profile_data["validation_coverage"]
            conflicts = profile_data["conflicts"]
            rec_meta = profile_data["recency_metadata"]
            sens_status = dep["sensitivity_status"]
            elasticity = dep["elasticity"]
            nature = dep["dependency_nature"]

            if elasticity is not None:
                all_sensitivities_unavailable = False

            # Check 1: Incompatible units or scope mismatch
            for c in conflicts:
                if c.get("conflict_type") in [TrustConflictType.INCOMPATIBLE_UNITS.value, TrustConflictType.SCOPE_MISMATCH.value]:
                    has_scope_or_unit_mismatch = True
                    evidence_gaps.append({
                        "parameter_name": pname,
                        "decision_id": dec_clean,
                        "severity": EvidenceGapSeverity.CRITICAL.value,
                        "reason": f"PHYSICAL_SCOPE_MISMATCH: Parameter has conflicting units or operating scope: {c.get('detail')}",
                        "supporting_sources": dep["source_evidence_ids"],
                        "contradicting_sources": [c.get("source_b", "unknown")],
                        "relevant_operating_conditions": dep["operating_conditions"],
                        "candidate_experiment_type": "RigKinematicSweep (Dimension & Unit Alignment)",
                        "expected_information_gain": "Unquantified qualitative reduction of epistemic uncertainty",
                        "unresolved_assumptions": ["Dimension compatibility assumed without canonical conversion"],
                        "recommendation_disclaimer": "RECOMMENDATION_ONLY: Suggested experiments are advisory research designs, not approved work orders.",
                    })

            # Check 1b: Operating regime mismatch between candidate and decision context
            cand_domain = dep.get("operating_conditions", {})
            dec_context = decision_info.get("context", {})
            cand_regime = cand_domain.get("operating_regime") if isinstance(cand_domain, dict) else None
            dec_regime = dec_context.get("operating_regime") if isinstance(dec_context, dict) else None
            if cand_regime and dec_regime and str(cand_regime).strip().lower() != str(dec_regime).strip().lower():
                evidence_gaps.append({
                    "parameter_name": pname,
                    "decision_id": dec_clean,
                    "severity": EvidenceGapSeverity.WARNING.value,
                    "reason": f"OPERATING_REGIME_MISMATCH: Parameter validity domain ('{cand_regime}') differs from decision operating regime ('{dec_regime}').",
                    "supporting_sources": dep["source_evidence_ids"],
                    "contradicting_sources": [],
                    "relevant_operating_conditions": dep["operating_conditions"],
                    "candidate_experiment_type": "RegimeSpecificTrackValidation (Cross-Domain Verification)",
                    "expected_information_gain": "Validates parameter transferability into target operating regime",
                    "unresolved_assumptions": ["Assumed parameter invariance across wet/dry operating conditions"],
                    "recommendation_disclaimer": "RECOMMENDATION_ONLY: Suggested experiments are advisory research designs, not approved work orders.",
                })

            # Check 2: Active Conflicts
            if len(conflicts) > 0 or trust_state == TrustState.CONFLICTED.value:
                has_active_conflict = True
                evidence_gaps.append({
                    "parameter_name": pname,
                    "decision_id": dec_clean,
                    "severity": EvidenceGapSeverity.CRITICAL.value,
                    "reason": "UNRESOLVED_VALUE_CONFLICT: Parameter possesses active value divergence or contradictory validation records.",
                    "supporting_sources": dep["source_evidence_ids"],
                    "contradicting_sources": [c.get("source_b", "unknown") for c in conflicts],
                    "relevant_operating_conditions": dep["operating_conditions"],
                    "candidate_experiment_type": "IndependentRigCalibration & ReconciliationSweep",
                    "expected_information_gain": "Isolates source measurement discrepancies across test rigs",
                    "unresolved_assumptions": ["Assumed single physical ground truth despite divergent source records"],
                    "recommendation_disclaimer": "RECOMMENDATION_ONLY: Suggested experiments are advisory research designs, not approved work orders.",
                })

            # Check 3: Missing Validation on High or Moderate Sensitivity
            if elasticity is not None:
                mag = abs(elasticity)
                if mag >= 0.20:
                    if val_cov != ValidationCoverage.VALIDATED.value:
                        has_high_sensitivity_unvalidated = True
                        evidence_gaps.append({
                            "parameter_name": pname,
                            "decision_id": dec_clean,
                            "severity": EvidenceGapSeverity.CRITICAL.value,
                            "reason": f"HIGH_SENSITIVITY_EVIDENCE_GAP: Parameter exhibits high downstream sensitivity (|elasticity|={mag:.2f}) but lacks physical holdout validation.",
                            "supporting_sources": dep["source_evidence_ids"],
                            "contradicting_sources": [],
                            "relevant_operating_conditions": dep["operating_conditions"],
                            "candidate_experiment_type": "FourPostRigHoldout (Physical Dynamic Response)",
                            "expected_information_gain": f"Expected to bound downstream KPI sensitivity within ±0.03 based on current measured elasticity ({elasticity:.2f})",
                            "unresolved_assumptions": ["Linearization validity across high lateral acceleration regime"],
                            "recommendation_disclaimer": "RECOMMENDATION_ONLY: Suggested experiments are advisory research designs, not approved work orders.",
                        })
                elif mag >= 0.05:
                    if val_cov != ValidationCoverage.VALIDATED.value:
                        has_moderate_sensitivity_unvalidated = True
                        evidence_gaps.append({
                            "parameter_name": pname,
                            "decision_id": dec_clean,
                            "severity": EvidenceGapSeverity.WARNING.value,
                            "reason": f"MODERATE_SENSITIVITY_EVIDENCE_GAP: Parameter has moderate sensitivity (|elasticity|={mag:.2f}) without holdout validation.",
                            "supporting_sources": dep["source_evidence_ids"],
                            "contradicting_sources": [],
                            "relevant_operating_conditions": dep["operating_conditions"],
                            "candidate_experiment_type": "TransientTrackManeuver (Controlled Coastdown & Turn-in)",
                            "expected_information_gain": f"Quantitatively bounds parameter response within operating band (elasticity: {elasticity:.2f})",
                            "unresolved_assumptions": ["Constant ambient operating temperature"],
                            "recommendation_disclaimer": "RECOMMENDATION_ONLY: Suggested experiments are advisory research designs, not approved work orders.",
                        })

            # Check 4: Qualitative Hypothesis Only
            if nature == DependencyNature.QUALITATIVE_HYPOTHESIS.value:
                evidence_gaps.append({
                    "parameter_name": pname,
                    "decision_id": dec_clean,
                    "severity": EvidenceGapSeverity.WARNING.value,
                    "reason": "QUALITATIVE_HYPOTHESIS_ONLY: Dependency is supported solely by a causal hypothesis without measured numerical sensitivity.",
                    "supporting_sources": dep["source_evidence_ids"],
                    "contradicting_sources": [],
                    "relevant_operating_conditions": dep["operating_conditions"],
                    "candidate_experiment_type": "ControlledExperiment (Single-Factor Treatment Isolation)",
                    "expected_information_gain": "Unquantified qualitative reduction of epistemic uncertainty",
                    "unresolved_assumptions": ["Directional trend assumed proportional without measured numerical derivative"],
                    "recommendation_disclaimer": "RECOMMENDATION_ONLY: Suggested experiments are advisory research designs, not approved work orders.",
                })

            # Check 5: Recency Condition
            rec_cond = rec_meta.get("recency_condition", RecencyCondition.VALID.value)
            age_days = rec_meta.get("age_days", 0)
            if rec_cond in [RecencyCondition.VALIDITY_EXPIRED.value, RecencyCondition.REASSESSMENT_RECOMMENDED.value] or (age_days and age_days > 180):
                has_stale_evidence = True
                evidence_gaps.append({
                    "parameter_name": pname,
                    "decision_id": dec_clean,
                    "severity": EvidenceGapSeverity.WARNING.value,
                    "reason": f"STALE_VALIDATION_EVIDENCE: Supporting validation is beyond advisory recency threshold ({age_days} days old, stale validation).",
                    "supporting_sources": dep["source_evidence_ids"],
                    "contradicting_sources": [],
                    "relevant_operating_conditions": dep["operating_conditions"],
                    "candidate_experiment_type": "ValidationRecencyReassessment",
                    "expected_information_gain": "Confirms parameter calibration stability against physical component degradation",
                    "unresolved_assumptions": ["Assumed physical spring/damper rates have not degraded over operational life"],
                    "recommendation_disclaimer": "RECOMMENDATION_ONLY: Suggested experiments are advisory research designs, not approved work orders.",
                })

            # Check 6: Missing Sensitivity Model
            if sens_status == SensitivityStatus.SENSITIVITY_UNAVAILABLE.value:
                evidence_gaps.append({
                    "parameter_name": pname,
                    "decision_id": dec_clean,
                    "severity": EvidenceGapSeverity.WARNING.value,
                    "reason": "MISSING_SENSITIVITY_MODEL: Parameter lacks authoritative numerical sensitivity or derivative data.",
                    "supporting_sources": dep["source_evidence_ids"],
                    "contradicting_sources": [],
                    "relevant_operating_conditions": dep["operating_conditions"],
                    "candidate_experiment_type": "NumericalSensitivityPerturbationSweep (Dyno / Simulation Parameter Sweep)",
                    "expected_information_gain": "Computes local partial derivative and numerical sensitivity elasticity",
                    "unresolved_assumptions": ["Assumed linear response around operating point"],
                    "recommendation_disclaimer": "RECOMMENDATION_ONLY: Suggested experiments are advisory research designs, not approved work orders.",
                })

        # Synthesize recommendations from actionable gaps
        for gap in evidence_gaps:
            actionable_recommendations.append({
                "target_parameter": gap["parameter_name"],
                "severity": gap["severity"],
                "candidate_experiment_type": gap["candidate_experiment_type"],
                "expected_information_gain": gap["expected_information_gain"],
                "unresolved_assumptions": gap["unresolved_assumptions"],
                "notice": gap["recommendation_disclaimer"],
            })

        # Order actionable recommendations by severity (CRITICAL < WARNING < ADVISORY)
        SEVERITY_ORDER = {
            EvidenceGapSeverity.CRITICAL.value: 0,
            EvidenceGapSeverity.WARNING.value: 1,
            EvidenceGapSeverity.ADVISORY.value: 2,
        }
        actionable_recommendations.sort(key=lambda r: SEVERITY_ORDER.get(r["severity"], 99))

        # 5. Synthesize Decision Exposure Classification
        if has_scope_or_unit_mismatch:
            exposure_class = DecisionExposureClassification.NOT_COMPARABLE.value
            exposure_summary = "Physical scope or unit incompatibility detected across parameter dependencies."
        elif has_active_conflict:
            exposure_class = DecisionExposureClassification.CRITICAL_CONFLICT_EXPOSURE.value
            exposure_summary = "Decision depends on parameters with unresolved active evidence conflicts or value divergences. Unresolved conflicts override holdout validation status."
        elif len(dependencies) == 0:
            exposure_class = DecisionExposureClassification.INSUFFICIENT_EVIDENCE.value
            exposure_summary = "No parameter dependencies could be traced for this engineering decision. Insufficient evidence."
        elif all_sensitivities_unavailable and not any(d["direct_profile"]["validation_coverage"] == ValidationCoverage.VALIDATED.value for d in dependencies):
            exposure_class = DecisionExposureClassification.INSUFFICIENT_EVIDENCE.value
            exposure_summary = "Authoritative sensitivity and validation evidence are unavailable for decision parameters. Missing sensitivity is never assumed to be low impact."
        elif has_high_sensitivity_unvalidated:
            exposure_class = DecisionExposureClassification.HIGH_EXPOSURE.value
            exposure_summary = "Decision is highly exposed to parameter uncertainty: high-sensitivity parameters lack physical holdout validation."
        elif has_moderate_sensitivity_unvalidated or has_stale_evidence:
            exposure_class = DecisionExposureClassification.MODERATE_EXPOSURE.value
            exposure_summary = "Decision has moderate exposure to parameter uncertainty due to moderate sensitivity evidence gaps or stale validation."
        else:
            exposure_class = DecisionExposureClassification.LOW_EXPOSURE.value
            exposure_summary = "Decision parameters are physically validated with fresh evidence and no active conflicts."

        governance_notice = (
            "GOVERNANCE SEPARATION: Parameter Trust Map and Decision Exposure assessments provide "
            "provenance-aware engineering decision support only. They do not constitute human engineering approval, "
            "work order authorization, or vehicle deployment safety certification. "
            "Deployment safety is an independent operational commissioning gate."
        )

        # 6. Deterministic Cryptographic Hashes
        canonical_input_payload = {
            "decision_id": dec_clean,
            "decision_type": decision_type,
            "policy_version": policy_version,
            "dependencies": [
                {
                    "parameter_name": d["parameter_name"],
                    "entity_type": d["entity_type"],
                    "entity_id": d["entity_id"],
                    "dependency_nature": d["dependency_nature"],
                    "sensitivity_status": d["sensitivity_status"],
                    "elasticity": d["elasticity"],
                    "trust_state": d["direct_profile"]["trust_state"],
                    "validation_coverage": d["direct_profile"]["validation_coverage"],
                    "conflicts_count": len(d["direct_profile"]["conflicts"]),
                }
                for d in sorted(dependencies, key=lambda x: x["parameter_name"])
            ],
        }
        dumped_input = json.dumps(canonical_input_payload, sort_keys=True, separators=(",", ":"))
        input_snapshot_hash = hashlib.sha256(dumped_input.encode("utf-8")).hexdigest()

        canonical_assessment_payload = {
            "input_snapshot_hash": input_snapshot_hash,
            "decision_id": dec_clean,
            "exposure_classification": exposure_class,
            "gaps_count": len(evidence_gaps),
            "policy_version": policy_version,
            "threshold_provenance": SENSITIVITY_THRESHOLDS_PROVENANCE,
            "deployment_safety_inferred": False,
        }
        dumped_assess = json.dumps(canonical_assessment_payload, sort_keys=True, separators=(",", ":"))
        assessment_hash = hashlib.sha256(dumped_assess.encode("utf-8")).hexdigest()

        if existing_assessment and existing_assessment.assessment_hash == assessment_hash and not force_reassess:
            return to_attr_dict(cls._build_assessment_response(existing_assessment, decision_info, dependencies))

        # 7. Persistence & Supersession Handling
        new_record = None
        differential: Optional[Dict[str, Any]] = None

        if persist_record and user_uuid is not None:
            if existing_assessment:
                differential = {
                    "previous_assessment_id": str(existing_assessment.id),
                    "previous_classification": existing_assessment.exposure_classification,
                    "new_classification": exposure_class,
                    "classification_changed": existing_assessment.exposure_classification != exposure_class,
                    "previous_hash": existing_assessment.assessment_hash,
                    "new_hash": assessment_hash,
                    "rationale": (
                        f"Reassessment under {policy_version}: exposure shifted from "
                        f"{existing_assessment.exposure_classification} to {exposure_class}."
                    ),
                }

            new_record = DecisionExposureAssessmentRecord(
                id=uuid.uuid4(),
                decision_id=dec_clean,
                decision_type=decision_type,
                policy_version=policy_version,
                assessment_hash=assessment_hash,
                input_snapshot_hash=input_snapshot_hash,
                exposure_classification=exposure_class,
                exposure_summary=exposure_summary,
                parameter_dependencies=dependencies,
                evidence_gaps=evidence_gaps,
                actionable_recommendations=actionable_recommendations,
                governance_separation_notice=governance_notice,
                is_active=True,
                superseded_by=None,
                organization_id=org_uuid,
                team_id=team_uuid,
                user_id=user_uuid,
                created_at=datetime.now(timezone.utc),
            )
            db.add(new_record)
            await db.flush()

            if existing_assessment:
                existing_assessment.is_active = False
                existing_assessment.superseded_by = new_record.id
                await db.flush()

            for dep in dependencies:
                dep_rec = DecisionParameterDependencyRecord(
                    id=uuid.uuid4(),
                    decision_id=dec_clean,
                    decision_type=decision_type,
                    parameter_name=dep["parameter_name"],
                    entity_type=dep["entity_type"],
                    entity_id=dep["entity_id"],
                    dependency_nature=dep["dependency_nature"],
                    kpi_metrics=dep["kpi_metrics"],
                    sensitivity_status=dep["sensitivity_status"],
                    elasticity=dep["elasticity"],
                    numerical_derivative=dep["numerical_derivative"],
                    derivative_unit=dep["derivative_unit"],
                    source_artifact_hashes=dep["source_artifact_hashes"],
                    source_evidence_ids=dep["source_evidence_ids"],
                    operating_conditions=dep["operating_conditions"],
                    model_version=dep["model_version"],
                    notes=dep["notes"],
                    organization_id=org_uuid,
                    team_id=team_uuid,
                    user_id=user_uuid,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(dep_rec)
            await db.flush()

        response = {
            "decision_id": dec_clean,
            "decision_type": decision_type,
            "policy_version": policy_version,
            "assessment_id": str(new_record.id) if new_record else None,
            "assessment_hash": assessment_hash,
            "input_snapshot_hash": input_snapshot_hash,
            "exposure_classification": exposure_class,
            "exposure_summary": exposure_summary,
            "threshold_provenance": SENSITIVITY_THRESHOLDS_PROVENANCE,
            "threshold_metadata": SENSITIVITY_THRESHOLDS_METADATA,
            "parameter_dependencies": dependencies,
            "evidence_gaps": evidence_gaps,
            "actionable_recommendations": actionable_recommendations,
            "differential": differential,
            "governance_separation": {
                "parameter_trust_states": {d["parameter_name"]: d["direct_profile"]["trust_state"] for d in dependencies},
                "sensitivity_impacts": {d["parameter_name"]: d["sensitivity_status"] for d in dependencies},
                "evidence_completeness": {
                    d["parameter_name"]: {
                        "validation_coverage": d["direct_profile"]["validation_coverage"],
                        "conflicts_count": len(d["direct_profile"]["conflicts"]),
                    }
                    for d in dependencies
                },
                "decision_exposure": exposure_class,
                "approval_authorization": {
                    "decision_status": decision_info.get("status", "RECOMMENDED") if hasattr(decision_info, "get") else "RECOMMENDED",
                    "approver": decision_info.get("approver") if hasattr(decision_info, "get") else None,
                    "approved_at": decision_info.get("approved_at") if hasattr(decision_info, "get") else None,
                    "is_human_approved": (decision_info.get("status") == "APPROVED") if hasattr(decision_info, "get") else False,
                },
                "deployment_safety": {
                    "deployment_safety_inferred": False,
                    "deployment_authorization": "NOT_ESTABLISHED",
                    "notice": "Decision exposure assessment does not grant vehicle deployment authorization.",
                },
            },
            "governance_separation_notice": governance_notice,
            "created_at": new_record.created_at.isoformat() if new_record else datetime.now(timezone.utc).isoformat(),
        }
        return to_attr_dict(response)

    @classmethod
    def _build_assessment_response(
        cls,
        rec: DecisionExposureAssessmentRecord,
        decision_info: Dict[str, Any],
        dependencies: List[Any],
    ) -> Dict[str, Any]:
        """Formats an existing persisted assessment record for API return."""
        return {
            "decision_id": rec.decision_id,
            "decision_type": rec.decision_type,
            "policy_version": rec.policy_version,
            "assessment_id": str(rec.id),
            "assessment_hash": rec.assessment_hash,
            "input_snapshot_hash": rec.input_snapshot_hash,
            "exposure_classification": rec.exposure_classification,
            "exposure_summary": rec.exposure_summary,
            "threshold_provenance": SENSITIVITY_THRESHOLDS_PROVENANCE,
            "threshold_metadata": SENSITIVITY_THRESHOLDS_METADATA,
            "parameter_dependencies": rec.parameter_dependencies or dependencies,
            "evidence_gaps": rec.evidence_gaps or [],
            "actionable_recommendations": rec.actionable_recommendations or [],
            "differential": None,
            "governance_separation": {
                "parameter_trust_states": {d["parameter_name"]: d["direct_profile"]["trust_state"] for d in dependencies},
                "sensitivity_impacts": {d["parameter_name"]: d["sensitivity_status"] for d in dependencies},
                "evidence_completeness": {
                    d["parameter_name"]: {
                        "validation_coverage": d["direct_profile"]["validation_coverage"],
                        "conflicts_count": len(d["direct_profile"]["conflicts"]),
                    }
                    for d in dependencies
                },
                "decision_exposure": rec.exposure_classification,
                "approval_authorization": {
                    "decision_status": decision_info.get("status", "RECOMMENDED") if hasattr(decision_info, "get") else "RECOMMENDED",
                    "approver": decision_info.get("approver") if hasattr(decision_info, "get") else None,
                    "approved_at": decision_info.get("approved_at") if hasattr(decision_info, "get") else None,
                    "is_human_approved": (decision_info.get("status") == "APPROVED") if hasattr(decision_info, "get") else False,
                },
                "deployment_safety": {
                    "deployment_safety_inferred": False,
                    "deployment_authorization": "NOT_ESTABLISHED",
                    "notice": "Decision exposure assessment does not grant vehicle deployment authorization.",
                },
            },
            "governance_separation_notice": rec.governance_separation_notice,
            "created_at": rec.created_at.isoformat() if rec.created_at else "",
        }

    # ── D. RETRIEVE REVISION HISTORY & DIFFERENTIAL ANALYSIS ──────────────────

    @hybridmethod
    async def get_assessment_history(
        cls,
        inst: Optional["ParameterTrustDecisionService"],
        *args,
        **kwargs,
    ) -> List[Any]:
        """
        Retrieves historical assessment revisions for an engineering decision under tenant scope.
        """
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
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None
        limit = kwargs.pop("limit", 50)

        stmt = select(DecisionExposureAssessmentRecord).where(
            DecisionExposureAssessmentRecord.decision_id == dec_clean
        )
        if team_uuid:
            stmt = stmt.where(DecisionExposureAssessmentRecord.team_id == team_uuid)
        elif org_uuid:
            stmt = stmt.where(DecisionExposureAssessmentRecord.organization_id == org_uuid)
        elif user_uuid:
            stmt = stmt.where(DecisionExposureAssessmentRecord.user_id == user_uuid)

        stmt = stmt.order_by(desc(DecisionExposureAssessmentRecord.created_at)).limit(limit)
        res = await db.execute(stmt)
        records = res.scalars().all()

        history: List[Any] = []
        for r in records:
            history.append(to_attr_dict({
                "assessment_id": str(r.id),
                "decision_id": r.decision_id,
                "policy_version": r.policy_version,
                "assessment_hash": r.assessment_hash,
                "input_snapshot_hash": r.input_snapshot_hash,
                "exposure_classification": r.exposure_classification,
                "exposure_summary": r.exposure_summary,
                "gaps_count": len(r.evidence_gaps or []),
                "dependencies_count": len(r.parameter_dependencies or []),
                "is_active": r.is_active,
                "superseded_by": str(r.superseded_by) if r.superseded_by else None,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }))
        return history

    @hybridmethod
    async def get_decision_history(
        cls,
        inst: Optional["ParameterTrustDecisionService"],
        *args,
        **kwargs,
    ) -> List[Any]:
        """Alias for get_assessment_history."""
        target = inst.get_assessment_history if inst is not None else cls.get_assessment_history
        return await target(*args, **kwargs)

    @hybridmethod
    async def reassess_decision(
        cls,
        inst: Optional["ParameterTrustDecisionService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """Forces supersession and reassessment of decision exposure."""
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        decision_id = args_list[0] if len(args_list) > 0 else kwargs.pop("decision_id", None)
        second = args_list[1] if len(args_list) > 1 else None
        third = args_list[2] if len(args_list) > 2 else None
        fourth = args_list[3] if len(args_list) > 3 else None

        if isinstance(second, str) and second in ("EngineeringDecision", "EngineeringProblem", "Investigation", "EngineeringProblemRecord", "InvestigationRecord"):
            decision_type = second
            user_context = third
            reason = fourth or kwargs.pop("reason", "Reassessment")
        else:
            decision_type = kwargs.pop("decision_type", "EngineeringDecision")
            user_context = second or kwargs.pop("user_context", None)
            reason = third or kwargs.pop("reason", "Reassessment")

        target = inst.assess_decision_exposure if inst is not None else cls.assess_decision_exposure
        return await target(
            db=db,
            decision_id=decision_id,
            decision_type=decision_type,
            user_context=user_context,
            force_reassess=True,
            persist_record=True,
            **kwargs,
        )
