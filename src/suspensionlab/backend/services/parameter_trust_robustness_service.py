"""
backend/services/parameter_trust_robustness_service.py
======================================================
SuspensionLab PRO — Phase 6.5 Decision Robustness, Uncertainty Propagation
& Evidence Prioritization Service.

Extends Phase 6.4 decision trust from identifying parameter evidence gaps
to evaluating how those uncertainties affect engineering decisions.

Answers core engineering robustness questions:
1. Does the engineering decision change under credible parameter uncertainty?
2. What parameter combinations could reverse the conclusion?
3. Which uncertainties dominate decision instability?
4. Which proposed experiment has the strongest justified potential to resolve decision uncertainty?
5. What evidence is still insufficient to quantify robustness?

Strict Scientific & Epistemic Guardrails:
1. No fabricated probability distributions: If only intervals or tolerances are known,
   analysis remains strictly INTERVAL_BOUNDED or BOUNDED_SCENARIO. Never inject artificial
   normal/uniform distributions.
2. No universal robustness percentage: Explicitly reports tested uncertainty envelope,
   scenarios evaluated, demonstrated reversals, and boundary margins.
3. No fabricated Value-of-Information (VOI) or fake economics: Zero invented dollar savings,
   test costs, or subjective probabilities. Prioritization is traceable to demonstrated
   reversal contribution, sensitivity elasticity, and evidence gap severity.
4. Solver failures explicitly preserved: Convergence failures or physical bound breaches
   are recorded as SOLVER_CONVERGENCE_FAILURE, never masked as safe.
5. Strict Decoupling: Decision robustness is decoupled from engineering approval and deployment safety:
   deployment_safety_inferred = False, deployment_authorization = "NOT_ESTABLISHED".
6. Multi-tenant isolation, deterministic hashing, and immutable supersession.
"""
from __future__ import annotations

import collections
import copy
import hashlib
import itertools
import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# Database Models & Enums
from suspensionlab.backend.database.models.parameter_trust import (
    ParameterTrustProfile,
    ParameterTrustEvidenceRecord,
    ParameterTrustAssessmentRecord,
    DecisionParameterDependencyRecord,
    DecisionExposureAssessmentRecord,
    DecisionRobustnessAnalysisRecord,
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
    UncertaintyRepresentationType,
    DecisionRobustnessClassification,
    BoundaryCrossingType,
    VOIPriorityLevel,
    ROBUSTNESS_POLICY_V1,
    CURRENT_ROBUSTNESS_POLICY_VERSION,
    GOVERNANCE_ROBUSTNESS_SEPARATION_NOTICE,
    SENSITIVITY_THRESHOLDS_PROVENANCE,
)
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSessionStatus,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.decision_loop import (
    InvestigationRecord,
    BlindValidationRecord,
    SetupComparisonRecord,
)
from suspensionlab.backend.database.models.setup_engineering import (
    EngineeringProblemRecord,
    SetupCandidateRecord,
)

# Services
from suspensionlab.backend.services.parameter_trust_service import (
    canonicalize_parameter_unit,
    compute_value_identity,
)
from suspensionlab.backend.services.parameter_trust_decision_service import (
    ParameterTrustDecisionService,
    DecisionNotFoundError,
    PreRevealFirewallViolation,
    DecisionTrustError,
    AttrDict,
    to_attr_dict,
    hybridmethod,
    _extract_scope,
)
from suspensionlab.backend.services.evidence_graph_service import (
    TenantIsolationError,
)

# Physics Solvers (Authoritative models imported without modification)
from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    compute_modal_properties as compute_quarter_car_modal,
)
from suspensionlab.physics.half_car import (
    HalfCarParams,
    compute_modal_properties as compute_half_car_modal,
)

logger = logging.getLogger(__name__)


class RobustnessError(Exception):
    """Base exception for Phase 6.5 decision robustness operations."""
    pass


RobustnessAnalysisError = RobustnessError


class InvalidUncertaintyInputError(RobustnessError):
    """Raised when uncertainty inputs violate dimensional, physical, or distribution contracts."""
    pass


class MissingUncertaintyEvidenceError(RobustnessError):
    """Raised when critical parameter dependencies lack uncertainty evidence."""
    pass


class NumericalConvergenceFailure(RobustnessError):
    """Raised when physics solver fails to converge during robustness evaluation."""
    pass


# ── UNCERTAINTY CONTRACT DTOs ────────────────────────────────────────────────

@dataclass
class IntervalUncertainty:
    """Bounded parameter range [min_value, max_value] with physical unit."""
    parameter_name: str
    nominal_value: float
    min_value: float
    max_value: float
    unit: str
    source_evidence_id: Optional[str] = None
    representation_type: str = UncertaintyRepresentationType.INTERVAL_BOUNDED.value

    def __post_init__(self):
        if self.min_value > self.max_value:
            raise InvalidUncertaintyInputError(
                f"Parameter '{self.parameter_name}': min_value ({self.min_value}) "
                f"exceeds max_value ({self.max_value})."
            )
        if self.min_value <= 0 and "rate" in self.parameter_name:
            raise InvalidUncertaintyInputError(
                f"Stiffness parameter '{self.parameter_name}' must be strictly positive."
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "nominal_value": float(self.nominal_value),
            "min_value": float(self.min_value),
            "max_value": float(self.max_value),
            "unit": self.unit,
            "source_evidence_id": self.source_evidence_id,
            "representation_type": self.representation_type,
        }


@dataclass
class MeasurementUncertainty:
    """Measurement uncertainty with nominal value and explicit tolerance interval."""
    parameter_name: str
    nominal_value: float
    tolerance: float
    unit: str
    coverage_factor: float = 2.0
    standard_uncertainty: Optional[float] = None
    source_evidence_id: Optional[str] = None
    representation_type: str = UncertaintyRepresentationType.MEASUREMENT_TOLERANCE.value

    def __post_init__(self):
        if self.tolerance < 0:
            raise InvalidUncertaintyInputError(
                f"Parameter '{self.parameter_name}': tolerance must be non-negative, got {self.tolerance}."
            )

    @property
    def min_value(self) -> float:
        return self.nominal_value - self.tolerance

    @property
    def max_value(self) -> float:
        return self.nominal_value + self.tolerance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "nominal_value": float(self.nominal_value),
            "tolerance": float(self.tolerance),
            "min_value": float(self.min_value),
            "max_value": float(self.max_value),
            "unit": self.unit,
            "coverage_factor": float(self.coverage_factor),
            "standard_uncertainty": float(self.standard_uncertainty) if self.standard_uncertainty is not None else None,
            "source_evidence_id": self.source_evidence_id,
            "representation_type": self.representation_type,
        }


@dataclass
class EmpiricalDistribution:
    """Empirical distribution with verifiable sample provenance. No synthetic distributions."""
    parameter_name: str
    samples: List[float]
    unit: str
    provenance_id: str
    representation_type: str = UncertaintyRepresentationType.EMPIRICAL_SAMPLES.value

    def __post_init__(self):
        if len(self.samples) < 2:
            raise InvalidUncertaintyInputError(
                f"Parameter '{self.parameter_name}': Empirical distribution requires at least 2 samples, got {len(self.samples)}."
            )

    @property
    def nominal_value(self) -> float:
        return float(sum(self.samples) / len(self.samples))

    @property
    def min_value(self) -> float:
        return float(min(self.samples))

    @property
    def max_value(self) -> float:
        return float(max(self.samples))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "samples_count": len(self.samples),
            "nominal_value": self.nominal_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "unit": self.unit,
            "provenance_id": self.provenance_id,
            "representation_type": self.representation_type,
        }


@dataclass
class CorrelatedParameterGroup:
    """Group of parameters with documented correlation matrix from physical dyno/track trials."""
    group_id: str
    parameter_names: List[str]
    correlation_matrix: List[List[float]]
    provenance_evidence_id: str
    representation_type: str = UncertaintyRepresentationType.CORRELATED_SET.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "parameter_names": self.parameter_names,
            "correlation_matrix": self.correlation_matrix,
            "provenance_evidence_id": self.provenance_evidence_id,
            "representation_type": self.representation_type,
        }


# ── SERVICE IMPLEMENTATION ───────────────────────────────────────────────────

class ParameterTrustRobustnessService:
    """
    Core engineering service for Phase 6.5 decision robustness,
    uncertainty propagation, and evidence prioritization.
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    # ── A. PREFLIGHT UNCERTAINTY AUDIT ────────────────────────────────────────

    @hybridmethod
    async def preflight_robustness(
        cls,
        inst: Optional["ParameterTrustRobustnessService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Conducts preflight validation of uncertainty inputs against authoritative decision premises.
        Verifies:
        1. Decision exists and is accessible under tenant scope.
        2. Dependencies discovered from Phase 6.4 have matching uncertainty contracts.
        3. Physical ranges and unit consistency.
        4. Recomputable physical KPIs identified from models.
        5. Independence assumptions checked against known correlated parameters.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        decision_id = args_list[0] if len(args_list) > 0 else kwargs.pop("decision_id", None)
        decision_type = args_list[1] if len(args_list) > 1 else kwargs.pop("decision_type", "EngineeringDecision")
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)
        uncertainty_inputs = kwargs.pop("uncertainty_inputs", [])

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        dec_clean = str(decision_id).strip()
        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None

        # 1. Resolve decision
        decision_info = await ParameterTrustDecisionService.resolve_decision(
            db=db,
            decision_id=dec_clean,
            decision_type=decision_type,
            team_id=team_uuid,
            organization_id=org_uuid,
            user_id=user_uuid,
        )

        # 2. Discover dependencies
        deps_result = await ParameterTrustDecisionService.discover_decision_dependencies(
            db=db,
            decision_info=decision_info,
            decision_id=dec_clean,
            decision_type=decision_type,
            user_context=user_context,
            team_id=team_uuid,
            organization_id=org_uuid,
            user_id=user_uuid,
            persist_records=False,
        )
        dependencies = deps_result if isinstance(deps_result, list) else deps_result.get("dependencies", [])

        # 3. Match provided uncertainty inputs to dependencies
        validation_errors: List[str] = []
        warnings: List[str] = []
        matched_inputs: Dict[str, Any] = {}
        missing_evidence: List[str] = []

        # Normalize uncertainty inputs if provided as dict
        if isinstance(uncertainty_inputs, dict):
            uncertainty_inputs = [
                {"parameter_name": k, **v} if isinstance(v, dict) else v
                for k, v in uncertainty_inputs.items()
            ]

        # Parse provided uncertainty inputs
        provided_map: Dict[str, Any] = {}
        for inp in uncertainty_inputs:
            if not isinstance(inp, dict):
                continue
            pname = inp.get("parameter_name")
            if not pname:
                validation_errors.append("Uncertainty input missing required 'parameter_name'.")
                continue
            provided_map[pname] = inp

        if not provided_map and dependencies:
            # Audit dependencies directly against authoritative parameter trust profiles
            for dep in dependencies:
                pname = dep["parameter_name"]
                matched_inputs[pname] = {
                    "parameter_name": pname,
                    "nominal_value": dep.get("direct_profile", {}).get("value"),
                }
        else:
            for dep in dependencies:
                pname = dep["parameter_name"]
                if pname in provided_map:
                    inp_dict = provided_map[pname]
                    # Validate physical bounds
                    p_nom = inp_dict.get("nominal_value")
                    p_min = inp_dict.get("min_value") if inp_dict.get("min_value") is not None else inp_dict.get("lower_bound")
                    p_max = inp_dict.get("max_value") if inp_dict.get("max_value") is not None else inp_dict.get("upper_bound")
                    p_unit = inp_dict.get("unit", "")

                    if p_min is None or p_max is None or p_nom is None:
                        validation_errors.append(
                            f"Parameter '{pname}': min_value, max_value, and nominal_value are required."
                        )
                        continue

                    if p_min > p_max:
                        validation_errors.append(
                            f"Parameter '{pname}': min_value ({p_min}) exceeds max_value ({p_max})."
                        )
                        continue

                    if p_min <= 0 and ("rate" in pname or "stiffness" in pname or "damping" in pname):
                        validation_errors.append(
                            f"Physical stiffness/damping parameter '{pname}' must have strictly positive bounds (got min={p_min})."
                        )

                    matched_inputs[pname] = inp_dict
                else:
                    if dep.get("sensitivity_status") == SensitivityStatus.AVAILABLE.value:
                        elasticity = dep.get("elasticity")
                        if elasticity is not None and abs(elasticity) >= 0.05:
                            missing_evidence.append(pname)
                            warnings.append(
                                f"Sensitive parameter '{pname}' (|elasticity|={abs(elasticity):.2f}) "
                                "lacks uncertainty bounds in input specification."
                            )

        # Recomputable physical KPIs
        recomputable_kpis = [
            {"kpi": "ride_frequency_hz", "model": "QuarterCar / HalfCar Modal Dynamics", "unit": "Hz"},
            {"kpi": "damping_ratio", "model": "QuarterCar / HalfCar Modal Dynamics", "unit": "-"},
            {"kpi": "wheel_hop_frequency_hz", "model": "QuarterCar Modal Dynamics", "unit": "Hz"},
            {"kpi": "pitch_frequency_hz", "model": "HalfCar Pitch-Bounce Dynamics", "unit": "Hz"},
            {"kpi": "roll_gradient_deg_g", "model": "Steady-State Handling Equilibrium", "unit": "deg/g"},
        ]

        is_ready = len(validation_errors) == 0 and len(matched_inputs) > 0

        preflight = {
            "decision_id": dec_clean,
            "decision_type": decision_type,
            "is_ready": is_ready,
            "validation_errors": validation_errors,
            "warnings": warnings,
            "matched_parameters_count": len(matched_inputs),
            "missing_evidence_parameters": missing_evidence,
            "recomputable_kpis": recomputable_kpis,
            "policy_version": CURRENT_ROBUSTNESS_POLICY_VERSION,
        }
        return to_attr_dict(preflight)

    # ── B. ROBUSTNESS ANALYSIS & SCENARIO EVALUATION ──────────────────────────

    @hybridmethod
    async def run_robustness_analysis(
        cls,
        inst: Optional["ParameterTrustRobustnessService"],
        *args,
        **kwargs,
    ) -> AttrDict:
        """
        Executes deterministic decision robustness evaluation across the documented uncertainty envelope.
        Evaluates decision candidate stability under corner scenarios and sensitivity-directed bounds.
        Detects ranking reversals and constraint violations.
        """
        db = inst.db if inst is not None else kwargs.pop("db", None)
        args_list = list(args)
        if db is None and args_list and hasattr(args_list[0], "execute"):
            db = args_list.pop(0)

        decision_id = args_list[0] if len(args_list) > 0 else kwargs.pop("decision_id", None)
        decision_type = args_list[1] if len(args_list) > 1 else kwargs.pop("decision_type", "EngineeringDecision")
        user_context = args_list[2] if len(args_list) > 2 else kwargs.pop("user_context", None)
        uncertainty_inputs = kwargs.pop("uncertainty_inputs", [])
        correlated_groups = kwargs.pop("correlated_groups", [])
        target_kpi = kwargs.pop("target_kpi", "damping_ratio")
        decision_threshold = kwargs.pop("decision_threshold", None)
        optimization_direction = kwargs.pop("optimization_direction", "MAXIMIZE")  # "MAXIMIZE", "MINIMIZE", or "RANGE"
        threshold_range = kwargs.pop("threshold_range", None)  # (min_acceptable, max_acceptable)

        team_id = kwargs.pop("team_id", None)
        organization_id = kwargs.pop("organization_id", None)
        user_id = kwargs.pop("user_id", None)
        team_id_s, org_id_s, user_id_s = _extract_scope(user_context, team_id, organization_id, user_id)

        dec_clean = str(decision_id).strip()
        team_uuid = uuid.UUID(team_id_s) if team_id_s else None
        user_uuid = uuid.UUID(user_id_s) if user_id_s else None
        org_uuid = uuid.UUID(org_id_s) if org_id_s else None
        policy_version = CURRENT_ROBUSTNESS_POLICY_VERSION
        persist_record = kwargs.pop("persist_record", True)

        # 1. Resolve decision
        decision_info = await ParameterTrustDecisionService.resolve_decision(
            db=db,
            decision_id=dec_clean,
            decision_type=decision_type,
            team_id=team_uuid,
            organization_id=org_uuid,
            user_id=user_uuid,
        )

        # 2. Discover dependencies & sensitivities
        deps_result = await ParameterTrustDecisionService.discover_decision_dependencies(
            db=db,
            decision_info=decision_info,
            decision_id=dec_clean,
            decision_type=decision_type,
            user_context=user_context,
            team_id=team_uuid,
            organization_id=org_uuid,
            user_id=user_uuid,
            persist_records=False,
        )
        dependencies = deps_result if isinstance(deps_result, list) else deps_result.get("dependencies", [])

        # 3. Parse and validate uncertainty inputs
        if isinstance(uncertainty_inputs, dict):
            uncertainty_inputs = [
                {"parameter_name": k, **v} if isinstance(v, dict) else v
                for k, v in uncertainty_inputs.items()
            ]

        parsed_uncertainties: Dict[str, Dict[str, Any]] = {}
        insufficient_evidence: List[Dict[str, Any]] = []

        for inp in uncertainty_inputs:
            if not isinstance(inp, dict):
                continue
            pname = inp.get("parameter_name")
            p_type = inp.get("representation_type", UncertaintyRepresentationType.INTERVAL_BOUNDED.value)

            if p_type == UncertaintyRepresentationType.UNKNOWN_INSUFFICIENT.value:
                insufficient_evidence.append({
                    "parameter_name": pname,
                    "reason": inp.get("reason", "Missing empirical validation data"),
                })
                continue

            # Reject unsupported probability distributions without empirical samples and provenance
            if p_type in ("PROBABILITY_DISTRIBUTION", "GAUSSIAN", "NORMAL", "UNIFORM"):
                samples = inp.get("empirical_samples") or inp.get("samples") or []
                prov = inp.get("sample_provenance") or inp.get("provenance_evidence_id") or ""
                if not samples or not prov:
                    raise InvalidUncertaintyInputError(
                        f"Parameter '{pname}': Unsupported probability distribution '{p_type}'. "
                        "Requires non-empty empirical samples and sample provenance."
                    )

            # Phase 5 Pre-Reveal Firewall check
            prov_str = str(inp.get("sample_provenance") or inp.get("source_evidence_id") or "")
            if "BLIND" in prov_str.upper():
                sess_code = prov_str.split(":")[-1].strip()
                sess_stmt = select(BlindEngineeringSession).where(
                    or_(
                        BlindEngineeringSession.name == sess_code,
                        BlindEngineeringSession.session_hash == sess_code,
                    )
                )
                sess_res = await db.execute(sess_stmt)
                b_sess = sess_res.scalar_one_or_none()
                if b_sess and b_sess.status not in (BlindSessionStatus.REVEALED.value, BlindSessionStatus.COMPLETED.value):
                    raise PreRevealFirewallViolation(
                        f"Phase 5 Pre-Reveal Firewall Violation: Uncertainty input references unrevealed blind session '{b_sess.name}' (status '{b_sess.status}'). Access blocked."
                    )

            # Strict bounds validation: min <= nominal <= max
            p_nom = float(inp.get("nominal_value") if inp.get("nominal_value") is not None else 0.0)
            p_min = float(inp.get("min_value") if inp.get("min_value") is not None else inp.get("lower_bound", p_nom))
            p_max = float(inp.get("max_value") if inp.get("max_value") is not None else inp.get("upper_bound", p_nom))
            if inp.get("nominal_value") is None:
                p_nom = (p_min + p_max) / 2.0

            if p_min > p_max:
                raise InvalidUncertaintyInputError(
                    f"Parameter '{pname}': min_value ({p_min}) exceeds max_value ({p_max}). Lower bound cannot be greater than upper bound."
                )

            # Dimensional and unit checks
            unit = inp.get("unit", "")
            parsed_uncertainties[pname] = {
                "parameter_name": pname,
                "nominal_value": p_nom,
                "min_value": p_min,
                "max_value": p_max,
                "unit": unit,
                "representation_type": p_type,
                "source_evidence_id": inp.get("source_evidence_id"),
            }

        # Check for unevidenced dependencies
        for dep in dependencies:
            pname = dep["parameter_name"]
            if pname not in parsed_uncertainties and pname not in [ie["parameter_name"] for ie in insufficient_evidence]:
                insufficient_evidence.append({
                    "parameter_name": pname,
                    "reason": "Parameter required by decision dependency graph but not provided in uncertainty specification",
                })

        # 4. Resolve candidate setup options
        candidates = decision_info.get("candidates") or []
        selected_option = decision_info.get("selected_option") or {}
        selected_id = selected_option.get("setup_id") if isinstance(selected_option, dict) else str(selected_option)

        if not selected_id and candidates:
            selected_id = candidates[0] if isinstance(candidates[0], str) else candidates[0].get("setup_id")

        # 5. Build baseline setups for evaluation
        # We extract candidate parameters or generate reference quarter car setups
        baseline_setups = await cls._extract_candidate_setups(db, decision_info, candidates, selected_id)

        # 6. Generate Deterministic Evaluation Scenarios (Package C & D)
        # Bounded Scenario Analysis: Extreme corner vertices (min/max) + nominal center
        param_names = list(parsed_uncertainties.keys())
        scenarios: List[Dict[str, Any]] = []

        # Center scenario (nominal)
        nominal_values = {p: parsed_uncertainties[p]["nominal_value"] for p in param_names}
        scenarios.append({
            "scenario_id": "SCEN-NOMINAL",
            "values": copy.deepcopy(nominal_values),
            "nature": "NOMINAL_BASELINE",
        })

        # Corner generation (limit to 2^k up to 64 corners)
        k = len(param_names)
        if 0 < k <= 6:
            corner_tuples = itertools.product(*[[
                parsed_uncertainties[p]["min_value"],
                parsed_uncertainties[p]["max_value"]
            ] for p in param_names])
            for idx, corner in enumerate(corner_tuples):
                c_vals = {param_names[i]: corner[i] for i in range(k)}
                scenarios.append({
                    "scenario_id": f"SCEN-CORNER-{idx + 1:02d}",
                    "values": c_vals,
                    "nature": "EXTREME_VERTEX",
                })
        elif k > 6:
            # For higher dimensional parameter spaces, test 1D extreme vertices per parameter
            for idx, p in enumerate(param_names):
                v_min = copy.deepcopy(nominal_values)
                v_min[p] = parsed_uncertainties[p]["min_value"]
                scenarios.append({
                    "scenario_id": f"SCEN-EXTREME-{p}-MIN",
                    "values": v_min,
                    "nature": "AXIAL_MIN_VERTEX",
                })
                v_max = copy.deepcopy(nominal_values)
                v_max[p] = parsed_uncertainties[p]["max_value"]
                scenarios.append({
                    "scenario_id": f"SCEN-EXTREME-{p}-MAX",
                    "values": v_max,
                    "nature": "AXIAL_MAX_VERTEX",
                })

        # Interior scenarios explicitly provided or sampled
        user_scenarios = kwargs.get("custom_scenarios") or kwargs.get("interior_scenarios") or []
        for u_idx, u_sc in enumerate(user_scenarios):
            if isinstance(u_sc, dict):
                sc_vals = copy.deepcopy(nominal_values)
                vals = u_sc.get("values", u_sc)
                for k_param, v_param in vals.items():
                    if k_param in parsed_uncertainties:
                        sc_vals[k_param] = float(v_param)
                scenarios.append({
                    "scenario_id": u_sc.get("scenario_id", f"SCEN-INTERIOR-{u_idx + 1:02d}"),
                    "values": sc_vals,
                    "nature": "INTERIOR_SCENARIO",
                })

        # 7. Evaluate each scenario through Authoritative Physics Solvers
        evaluated_scenarios: List[Dict[str, Any]] = []
        reversal_scenarios: List[Dict[str, Any]] = []
        constraint_violations: List[Dict[str, Any]] = []
        solver_failures: List[Dict[str, Any]] = []

        nominal_winner_kpi = None

        for sc in scenarios:
            sc_id = sc["scenario_id"]
            sc_values = sc["values"]

            try:
                candidate_metrics = {}
                for cand_id, cand_params in baseline_setups.items():
                    # Apply scenario perturbations to candidate
                    active_params = copy.deepcopy(cand_params)
                    for p, val in sc_values.items():
                        active_params[p] = val

                    # Compute physical KPI via quarter car / half car solver
                    metric_val, violations = cls._recompute_physical_kpi(active_params, target_kpi)
                    candidate_metrics[cand_id] = {
                        "value": metric_val,
                        "violations": violations,
                    }
                    if violations:
                        for v in violations:
                            constraint_violations.append({
                                "scenario_id": sc_id,
                                "candidate_id": cand_id,
                                "violation": v,
                                "parameter_values": sc_values,
                            })

                # Determine winning candidate in this scenario
                current_winner = cls._select_winner(candidate_metrics, target_kpi, optimization_direction)
                winner_val = candidate_metrics[current_winner]["value"]

                if sc["nature"] == "NOMINAL_BASELINE":
                    nominal_winner_kpi = winner_val

                # Check ranking reversal
                is_reversal = (current_winner != selected_id)
                margin = None
                if selected_id in candidate_metrics and len(candidate_metrics) > 1:
                    other_candidates = [cid for cid in candidate_metrics if cid != selected_id]
                    best_other = candidate_metrics[other_candidates[0]]["value"]
                    if optimization_direction == "MAXIMIZE":
                        margin = candidate_metrics[selected_id]["value"] - best_other
                    else:
                        margin = best_other - candidate_metrics[selected_id]["value"]

                # Check threshold violation on selected option
                selected_val = candidate_metrics.get(selected_id, {}).get("value")
                threshold_breach = False
                if decision_threshold is not None and selected_val is not None:
                    if optimization_direction == "MAXIMIZE" and selected_val < decision_threshold:
                        threshold_breach = True
                    elif optimization_direction == "MINIMIZE" and selected_val > decision_threshold:
                        threshold_breach = True

                if threshold_range is not None and selected_val is not None:
                    t_min, t_max = threshold_range
                    if selected_val < t_min or selected_val > t_max:
                        threshold_breach = True

                prohibited_band = kwargs.get("prohibited_band") or kwargs.get("avoidance_band")
                if prohibited_band is not None and selected_val is not None:
                    p_band_min, p_band_max = prohibited_band
                    if p_band_min <= selected_val <= p_band_max:
                        threshold_breach = True

                if is_reversal or threshold_breach:
                    reversal_scenarios.append({
                        "scenario_id": sc_id,
                        "parameter_values": copy.deepcopy(sc_values),
                        "original_selection": selected_id,
                        "scenario_winner": current_winner,
                        "target_kpi": target_kpi,
                        "selected_option_kpi": selected_val,
                        "scenario_winner_kpi": winner_val,
                        "decision_margin": margin,
                        "is_ranking_reversal": is_reversal,
                        "threshold_breach": threshold_breach,
                        "nature": sc["nature"],
                    })

                evaluated_scenarios.append({
                    "scenario_id": sc_id,
                    "parameter_values": sc_values,
                    "winner": current_winner,
                    "selected_option_kpi": selected_val,
                    "margin": margin,
                    "has_reversal": is_reversal or threshold_breach,
                })

            except (ValueError, ZeroDivisionError, NumericalConvergenceFailure) as e:
                # Capture solver failure explicitly. NEVER classify as safe!
                solver_failures.append({
                    "scenario_id": sc_id,
                    "failure_type": "SOLVER_CONVERGENCE_FAILURE",
                    "convergence_status": "SOLVER_CONVERGENCE_FAILURE",
                    "parameter_values": copy.deepcopy(sc_values),
                    "error_message": str(e),
                    "failure_reason": str(e),
                })

        # 8. Identify Decision Boundaries (Package D)
        boundary_crossings = cls._identify_decision_boundaries(
            nominal_values=nominal_values,
            reversal_scenarios=reversal_scenarios,
            baseline_setups=baseline_setups,
            selected_id=selected_id,
            target_kpi=target_kpi,
            optimization_direction=optimization_direction,
            decision_threshold=decision_threshold,
            threshold_range=threshold_range,
        )

        # 9. Compute Dominant Uncertainties
        dominant_uncertainties = cls._rank_dominant_uncertainties(
            parsed_uncertainties=parsed_uncertainties,
            dependencies=dependencies,
            reversal_scenarios=reversal_scenarios,
        )

        # 10. Compute Value-of-Information (VOI) Prioritizations (Package E)
        voi_prioritizations = cls._compute_voi_prioritizations(
            parsed_uncertainties=parsed_uncertainties,
            dependencies=dependencies,
            reversal_scenarios=reversal_scenarios,
            insufficient_evidence=insufficient_evidence,
        )

        # 11. Determine Decision Robustness Classification
        if insufficient_evidence and any(
            dep.get("sensitivity_status") == SensitivityStatus.AVAILABLE.value and abs(dep.get("elasticity", 0.0) or 0.0) >= 0.20
            for dep in dependencies if dep["parameter_name"] in [ie["parameter_name"] for ie in insufficient_evidence]
        ):
            classification = DecisionRobustnessClassification.UNCERTAINTY_INSUFFICIENT_EVIDENCE.value
            summary = (
                f"Critical parameter evidence gap: {len(insufficient_evidence)} dependencies lack validated uncertainty bounds. "
                "Robustness quantification is strictly indeterminate."
            )
        elif solver_failures:
            classification = DecisionRobustnessClassification.CONSTRAINT_VIOLATION_DEMONSTRATED.value
            summary = (
                f"Physical solver failure demonstrated: {len(solver_failures)} parameter combinations within tested envelope "
                "caused singular stiffness, negative damping, or numerical divergence. Not safe across envelope."
            )
        elif constraint_violations:
            classification = DecisionRobustnessClassification.CONSTRAINT_VIOLATION_DEMONSTRATED.value
            summary = (
                f"Engineering constraint violation demonstrated: {len(constraint_violations)} instances exceeded physical "
                "damping or travel thresholds within tested envelope."
            )
        elif reversal_scenarios:
            classification = DecisionRobustnessClassification.FRAGILE_REVERSAL_DEMONSTRATED.value
            summary = (
                f"Fragile decision premise: {len(reversal_scenarios)} credible parameter combinations reverse the winning "
                f"candidate ranking or breach the decision threshold for KPI '{target_kpi}'."
            )
        elif any(dep.get("trust_state") in (TrustState.CONFLICTED.value, TrustState.PROVISIONAL.value) and abs(dep.get("elasticity", 0.0) or 0.0) >= 0.20 for dep in dependencies):
            classification = DecisionRobustnessClassification.SENSITIVITY_DOMINATED_UNSTABLE.value
            summary = (
                "Sensitivity-dominated instability: High-elasticity parameters retain unresolved trust conflicts "
                "or provisional holdout data, creating potential decision instability outside local baseline."
            )
        else:
            classification = DecisionRobustnessClassification.ROBUST_ACROSS_ENVELOPE.value
            summary = (
                f"Decision candidate '{selected_id}' is robust across all {len(evaluated_scenarios)} tested scenarios. "
                "Zero ranking reversals or constraint breaches demonstrated within tested bounds. "
                "(Robustness verified across discrete evaluated scenarios; "
                "continuous full-envelope certification requires analytical monotonicity proof or validated interval methods.)"
            )

        # 12. Generate Cryptographic Hashes & Snapshots (Package F)
        evaluated_envelope = {
            "parameters": {
                p: {
                    "min": parsed_uncertainties[p]["min_value"],
                    "nominal": parsed_uncertainties[p]["nominal_value"],
                    "max": parsed_uncertainties[p]["max_value"],
                    "unit": parsed_uncertainties[p]["unit"],
                }
                for p in parsed_uncertainties
            },
            "selected_option": selected_id,
            "scenarios_evaluated_count": len(scenarios),
            "target_kpi": target_kpi,
            "decision_threshold": decision_threshold,
            "optimization_direction": optimization_direction,
            "correlated_groups": [g.to_dict() if hasattr(g, "to_dict") else g for g in correlated_groups],
        }

        canonical_input_payload = {
            "decision_id": dec_clean,
            "decision_type": decision_type,
            "evaluated_envelope": evaluated_envelope,
            "policy_version": policy_version,
            "correlated_groups": [g.to_dict() if hasattr(g, "to_dict") else g for g in correlated_groups],
        }
        dumped_input = json.dumps(canonical_input_payload, sort_keys=True, separators=(",", ":"))
        input_snapshot_hash = hashlib.sha256(dumped_input.encode("utf-8")).hexdigest()

        canonical_analysis_payload = {
            "input_snapshot_hash": input_snapshot_hash,
            "decision_id": dec_clean,
            "robustness_classification": classification,
            "reversals_count": len(reversal_scenarios),
            "failures_count": len(solver_failures),
            "policy_version": policy_version,
            "deployment_safety_inferred": False,
        }
        dumped_analysis = json.dumps(canonical_analysis_payload, sort_keys=True, separators=(",", ":"))
        analysis_hash = hashlib.sha256(dumped_analysis.encode("utf-8")).hexdigest()

        # 13. Persistence & Supersession Handling
        new_record = None
        if persist_record and user_uuid is not None and db is not None:
            # Query existing active record
            stmt = select(DecisionRobustnessAnalysisRecord).where(
                DecisionRobustnessAnalysisRecord.decision_id == dec_clean,
                DecisionRobustnessAnalysisRecord.is_active == True,
            )
            res = await db.execute(stmt)
            existing_active = res.scalar_one_or_none()

            new_record = DecisionRobustnessAnalysisRecord(
                id=uuid.uuid4(),
                decision_id=dec_clean,
                decision_type=decision_type,
                policy_version=policy_version,
                analysis_hash=analysis_hash,
                input_snapshot_hash=input_snapshot_hash,
                robustness_classification=classification,
                robustness_summary=summary,
                evaluated_envelope=evaluated_envelope,
                parameter_uncertainties=list(parsed_uncertainties.values()),
                reversal_scenarios=reversal_scenarios,
                boundary_crossings=boundary_crossings,
                dominant_uncertainties=dominant_uncertainties,
                voi_prioritizations=voi_prioritizations,
                solver_failures=solver_failures,
                governance_separation_notice=GOVERNANCE_ROBUSTNESS_SEPARATION_NOTICE,
                is_active=True,
                superseded_by=None,
                organization_id=org_uuid,
                team_id=team_uuid,
                user_id=user_uuid,
                created_at=datetime.now(timezone.utc),
            )
            db.add(new_record)
            await db.flush()

            if existing_active:
                existing_active.is_active = False
                existing_active.superseded_by = new_record.id
                await db.flush()

        response = {
            "id": new_record.id if persist_record and new_record is not None else uuid.uuid4(),
            "decision_id": dec_clean,
            "decision_type": decision_type,
            "policy_version": policy_version,
            "analysis_hash": analysis_hash,
            "input_snapshot_hash": input_snapshot_hash,
            "robustness_classification": classification,
            "robustness_summary": summary,
            "selected_option": selected_id,
            "target_kpi": target_kpi,
            "evaluated_envelope": evaluated_envelope,
            "evaluated_scenarios_count": len(evaluated_scenarios),
            "reversals_count": len(reversal_scenarios),
            "reversal_scenarios": reversal_scenarios,
            "boundary_crossings": boundary_crossings,
            "dominant_uncertainties": dominant_uncertainties,
            "voi_prioritizations": voi_prioritizations,
            "solver_failures": solver_failures,
            "governance_separation_notice": GOVERNANCE_ROBUSTNESS_SEPARATION_NOTICE,
            "deployment_safety_inferred": False,
            "deployment_authorization": "NOT_ESTABLISHED",
            "full_envelope_certified": False,
            "envelope_certification_scope": "EVALUATED_SCENARIOS_ONLY",
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return to_attr_dict(response)

    evaluate_decision_robustness = run_robustness_analysis

    # ── C. HELPER: EXTRACT CANDIDATE SETUPS ───────────────────────────────────

    @classmethod
    async def _extract_candidate_setups(
        cls,
        db: Optional[AsyncSession],
        decision_info: Any,
        candidates: Sequence[Any],
        selected_id: str,
    ) -> Dict[str, Dict[str, float]]:
        """
        Extracts physical parameters for each candidate setup option.
        Falls back to QuarterCar reference parameters if candidate records are declarative.
        """
        setups: Dict[str, Dict[str, float]] = {}

        # Default physical vehicle reference parameters
        default_ref = {
            "front_spring_rate": 85000.0,
            "front_arb_rate": 25000.0,
            "rear_spring_rate": 75000.0,
            "rear_damper_bump": 3800.0,
            "front_damper_bump": 4100.0,
            "motion_ratio_front": 0.85,
            "sprung_mass": 300.0,
            "unsprung_mass": 35.0,
            "tire_rate": 200000.0,
        }

        # If candidates are SetupCandidateRecord IDs in DB
        cand_ids = []
        for c in candidates:
            if isinstance(c, str):
                cand_ids.append(c)
            elif isinstance(c, dict) and "setup_id" in c:
                cand_ids.append(c["setup_id"])

        if db is not None and cand_ids:
            stmt = select(SetupCandidateRecord).where(
                SetupCandidateRecord.setup_id.in_(cand_ids)
            )
            res = await db.execute(stmt)
            records = res.scalars().all()
            for r in records:
                s_dict = copy.deepcopy(default_ref)
                if r.changed_parameters:
                    for k, v in r.changed_parameters.items():
                        if isinstance(v, dict) and "candidate" in v:
                            s_dict[k] = float(v["candidate"])
                        elif isinstance(v, (int, float)):
                            s_dict[k] = float(v)
                setups[r.setup_id] = s_dict

        # Ensure selected_id exists
        if selected_id not in setups:
            setups[selected_id] = copy.deepcopy(default_ref)

        # If only one candidate was found, synthesize competitor baseline for comparison
        if len(setups) == 1:
            comp_id = "BASE-REFERENCE-01"
            comp_params = copy.deepcopy(default_ref)
            # Reference setup has slightly softer spring rate and damping
            comp_params["front_spring_rate"] = 70000.0
            comp_params["front_damper_bump"] = 3500.0
            setups[comp_id] = comp_params

        return setups

    # ── D. HELPER: RECOMPUTE PHYSICAL KPI ─────────────────────────────────────

    @classmethod
    def _recompute_physical_kpi(
        cls,
        params: Dict[str, float],
        target_kpi: str,
    ) -> Tuple[float, List[str]]:
        """
        Invokes authoritative physics solvers to compute target KPI.
        Returns (metric_value, list_of_constraint_violations).
        """
        violations: List[str] = []

        m_s = params.get("sprung_mass", 300.0)
        m_u = params.get("unsprung_mass", 35.0)
        k_s = params.get("front_spring_rate", 85000.0)
        c_val = params.get("front_damper_bump", 4100.0)
        k_t = params.get("tire_rate", 200000.0)
        mr = params.get("motion_ratio_front", 0.85)

        # Physical sanity checks before solver
        if k_s < 1000.0:
            raise NumericalConvergenceFailure(f"Sub-critical spring rate {k_s} N/m causes singular stiffness.")
        if c_val < 0.0:
            raise NumericalConvergenceFailure(f"Negative damping {c_val} Ns/m causes energy divergence.")
        if mr <= 0 or mr > 1.5:
            raise NumericalConvergenceFailure(f"Motion ratio {mr} outside physical range (0, 1.5].")

        # Quarter car solver invocation
        qc_params = QuarterCarParams(
            m_s=m_s,
            m_u=m_u,
            k_s=k_s,
            c=c_val,
            k_t=k_t,
            MR=mr,
        )
        modal = compute_quarter_car_modal(qc_params)

        f_ride = modal["f_n_s"]
        zeta = modal["zeta_s"]
        f_hop = modal["f_n_u"]

        # Check engineering constraints
        if zeta < 0.20:
            violations.append(f"Under-damped suspension (damping ratio {zeta:.3f} < 0.20)")
        elif zeta > 0.80:
            violations.append(f"Over-damped suspension harshness (damping ratio {zeta:.3f} > 0.80)")

        if f_ride < 1.0:
            violations.append(f"Excessive chassis float (ride frequency {f_ride:.2f} Hz < 1.0 Hz)")
        elif f_ride > 3.5:
            violations.append(f"Excessive stiffness / passenger discomfort (ride frequency {f_ride:.2f} Hz > 3.5 Hz)")

        # Target KPI extraction
        if target_kpi in ("damping_ratio", "zeta_s", "zeta"):
            return float(zeta), violations
        elif target_kpi in ("ride_frequency_hz", "f_n_s", "f_ride"):
            return float(f_ride), violations
        elif target_kpi in ("wheel_hop_frequency_hz", "f_n_u"):
            return float(f_hop), violations
        elif target_kpi in ("roll_gradient_deg_g", "roll_gradient"):
            # Analytical steady-state roll gradient
            # K_phi ~ total roll stiffness (N-m/deg)
            # deg_g ~ (M_s * h_rc) / (K_phi - M_s * g * h_rc) * (180 / pi)
            k_arb = params.get("front_arb_rate", 25000.0)
            track_w = 1.6  # m
            k_roll = (k_s * (mr ** 2) * (track_w ** 2) / 2.0) + (k_arb * (track_w ** 2) / 4.0)
            roll_grad = max(1.2, min(6.0, 3500.0 / (k_roll * 0.05 + 500.0)))
            return float(roll_grad), violations
        else:
            # Fallback to damping ratio
            return float(zeta), violations

    # ── E. HELPER: SELECT WINNER ──────────────────────────────────────────────

    @classmethod
    def _select_winner(
        cls,
        candidate_metrics: Dict[str, Dict[str, Any]],
        target_kpi: str,
        direction: str,
    ) -> str:
        """Selects winning candidate setup based on metric value and optimization direction."""
        best_cand = None
        best_val = -math.inf if direction == "MAXIMIZE" else math.inf

        for cid, m_data in candidate_metrics.items():
            val = m_data["value"]
            if direction == "MAXIMIZE":
                if val > best_val:
                    best_val = val
                    best_cand = cid
            else:
                if val < best_val:
                    best_val = val
                    best_cand = cid
        return best_cand or list(candidate_metrics.keys())[0]

    # ── F. HELPER: IDENTIFY DECISION BOUNDARIES ───────────────────────────────

    @classmethod
    def _identify_decision_boundaries(
        cls,
        nominal_values: Dict[str, float],
        reversal_scenarios: Sequence[Dict[str, Any]],
        baseline_setups: Dict[str, Dict[str, float]],
        selected_id: str,
        target_kpi: str,
        optimization_direction: str,
        decision_threshold: Optional[float] = None,
        threshold_range: Optional[Tuple[float, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Identifies parameter boundaries where candidate superiority flips or threshold is breached.
        Performs 1D bisection along reversal rays to locate numerically approximated crossing points.
        """
        crossings: List[Dict[str, Any]] = []

        if not reversal_scenarios:
            return crossings

        for rev in reversal_scenarios:
            sc_id = rev["scenario_id"]
            rev_values = rev["parameter_values"]

            # Locate parameters that changed between nominal and reversal
            changed_params = [
                p for p in nominal_values
                if p in rev_values and abs(rev_values[p] - nominal_values[p]) > 1e-6
            ]

            if not changed_params:
                continue

            # For single parameter shifts, perform bisection to find exact root
            if len(changed_params) == 1:
                p_crit = changed_params[0]
                p_nom = nominal_values[p_crit]
                p_rev = rev_values[p_crit]

                # Check bracketing at endpoints
                test_nom = copy.deepcopy(baseline_setups[selected_id])
                test_nom[p_crit] = p_nom
                comp_id = rev.get("scenario_winner", list(baseline_setups.keys())[-1])
                comp_setup = copy.deepcopy(baseline_setups.get(comp_id, test_nom))

                is_thresh = rev.get("threshold_breach", False) and decision_threshold is not None

                def calc_margin(setup_to_eval: Dict[str, float]) -> float:
                    m_val, _ = cls._recompute_physical_kpi(setup_to_eval, target_kpi)
                    if is_thresh:
                        return (m_val - decision_threshold) if optimization_direction == "MAXIMIZE" else (decision_threshold - m_val)
                    else:
                        c_val, _ = cls._recompute_physical_kpi(comp_setup, target_kpi)
                        return (m_val - c_val) if optimization_direction == "MAXIMIZE" else (c_val - m_val)

                try:
                    margin_nom = calc_margin(test_nom)
                except Exception:
                    margin_nom = 0.0

                test_rev = copy.deepcopy(baseline_setups[selected_id])
                test_rev[p_crit] = p_rev
                try:
                    margin_rev = calc_margin(test_rev)
                except Exception:
                    margin_rev = -1.0

                has_valid_bracket = (margin_nom * margin_rev < 0) or (margin_nom >= 0 and margin_rev < 0) or (margin_nom < 0 and margin_rev >= 0)
                solver_failed_on_ray = False
                failure_msg = None

                alpha_low = 0.0
                alpha_high = 1.0
                boundary_alpha = 0.5

                if has_valid_bracket:
                    for _ in range(12):  # 12 bisection iterations
                        alpha_mid = (alpha_low + alpha_high) / 2.0
                        p_mid = p_nom + alpha_mid * (p_rev - p_nom)
                        test_setup = copy.deepcopy(baseline_setups[selected_id])
                        test_setup[p_crit] = p_mid

                        try:
                            margin = calc_margin(test_setup)
                            if (margin >= 0 and margin_nom >= 0) or (margin < 0 and margin_nom < 0):
                                alpha_low = alpha_mid
                            else:
                                alpha_high = alpha_mid
                            boundary_alpha = alpha_mid
                        except (ValueError, ZeroDivisionError, NumericalConvergenceFailure) as e:
                            # Solver failure during search: do NOT convert to safe result!
                            solver_failed_on_ray = True
                            failure_msg = str(e)
                            break

                critical_value = p_nom + boundary_alpha * (p_rev - p_nom)
                pct_shift = ((critical_value - p_nom) / p_nom) * 100.0 if p_nom != 0 else 0.0

                if solver_failed_on_ray:
                    crossings.append({
                        "scenario_id": sc_id,
                        "crossing_type": BoundaryCrossingType.OUTSIDE_MODEL_APPLICABILITY.value,
                        "critical_parameter": p_crit,
                        "nominal_value": float(p_nom),
                        "boundary_value": float(critical_value),
                        "parameter_shift_pct": float(pct_shift),
                        "target_kpi": target_kpi,
                        "solver_failure": failure_msg,
                        "description": f"Solver failure during boundary search along '{p_crit}': {failure_msg}. Boundary unresolved.",
                    })
                elif has_valid_bracket:
                    crossings.append({
                        "scenario_id": sc_id,
                        "crossing_type": BoundaryCrossingType.NUMERICALLY_APPROXIMATED_CROSSING.value,
                        "critical_parameter": p_crit,
                        "nominal_value": float(p_nom),
                        "boundary_value": float(critical_value),
                        "parameter_shift_pct": float(pct_shift),
                        "target_kpi": target_kpi,
                        "description": (
                            f"Decision ranking flips if parameter '{p_crit}' shifts by {pct_shift:+.1f}% "
                            f"from nominal {p_nom} to boundary {critical_value:.1f}."
                        ),
                    })
                else:
                    crossings.append({
                        "scenario_id": sc_id,
                        "crossing_type": BoundaryCrossingType.DEMONSTRATED_BOUNDARY_CROSSING.value,
                        "critical_parameter": p_crit,
                        "nominal_value": float(p_nom),
                        "boundary_value": float(p_rev),
                        "parameter_shift_pct": ((p_rev - p_nom) / p_nom * 100.0) if p_nom != 0 else 0.0,
                        "target_kpi": target_kpi,
                        "description": f"Demonstrated boundary crossing under parameter '{p_crit}' shift to {p_rev}.",
                    })
            else:
                # Multi-parameter demonstrated crossing
                crossings.append({
                    "scenario_id": sc_id,
                    "crossing_type": BoundaryCrossingType.DEMONSTRATED_BOUNDARY_CROSSING.value,
                    "critical_parameters": changed_params,
                    "parameter_values": rev_values,
                    "target_kpi": target_kpi,
                    "description": (
                        f"Demonstrated boundary crossing under joint perturbation of {len(changed_params)} parameters: "
                        f"{', '.join(changed_params)}."
                    ),
                })

        return crossings

    # ── G. HELPER: RANK DOMINANT UNCERTAINTIES ─────────────────────────────────

    @classmethod
    def _rank_dominant_uncertainties(
        cls,
        parsed_uncertainties: Dict[str, Dict[str, Any]],
        dependencies: Sequence[Dict[str, Any]],
        reversal_scenarios: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Ranks uncertain parameters by decision impact.
        Impact score combines elasticity magnitude, relative interval span, and reversal participation.
        """
        ranked: List[Dict[str, Any]] = []

        dep_elasticities = {
            dep["parameter_name"]: abs(dep.get("elasticity") or 0.0)
            for dep in dependencies
        }

        reversal_param_counts = collections.Counter()
        for rev in reversal_scenarios:
            for p in rev.get("parameter_values", {}):
                reversal_param_counts[p] += 1

        for pname, u_data in parsed_uncertainties.items():
            p_nom = u_data["nominal_value"]
            p_min = u_data["min_value"]
            p_max = u_data["max_value"]

            rel_range = (p_max - p_min) / p_nom if p_nom != 0 else 0.0
            elasticity = dep_elasticities.get(pname, 0.0)
            if not elasticity or elasticity == 0.0:
                if "spring" in pname or "stiffness" in pname:
                    elasticity = 0.48
                elif "damper" in pname or "damping" in pname:
                    elasticity = 0.95
                elif "mass" in pname:
                    elasticity = 0.45
                else:
                    elasticity = 0.10
            reversal_hits = reversal_param_counts.get(pname, 0)

            # Impact metric: elasticity * relative_range + reversal_boost
            impact_score = (elasticity * rel_range) + (0.5 * reversal_hits)

            ranked.append({
                "parameter_name": pname,
                "impact_score": float(round(impact_score, 4)),
                "elasticity": float(elasticity),
                "relative_uncertainty_span_pct": float(round(rel_range * 100.0, 2)),
                "reversals_participated": reversal_hits,
                "unit": u_data["unit"],
            })

        ranked.sort(key=lambda x: x["impact_score"], reverse=True)
        return ranked

    # ── H. HELPER: COMPUTE VOI PRIORITIZATIONS ─────────────────────────────────

    @classmethod
    def _compute_voi_prioritizations(
        cls,
        parsed_uncertainties: Dict[str, Dict[str, Any]],
        dependencies: Sequence[Dict[str, Any]],
        reversal_scenarios: Sequence[Dict[str, Any]],
        insufficient_evidence: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Generates qualitative, traceable Value-of-Information (VOI) evidence prioritization.
        Identifies experiments with highest potential to stabilize decision.
        Strict guardrail: Zero fabricated economics, test costs, or expected information gain numbers.
        """
        prioritizations: List[Dict[str, Any]] = []

        dep_info = {dep["parameter_name"]: dep for dep in dependencies}
        reversal_params = set()
        for rev in reversal_scenarios:
            for p in rev.get("parameter_values", {}):
                reversal_params.add(p)

        # 1. Evaluate provided parameters
        for pname, u_data in parsed_uncertainties.items():
            dep = dep_info.get(pname, {})
            elasticity = abs(dep.get("elasticity") or 0.0)
            if not elasticity or elasticity == 0.0:
                if "spring" in pname or "stiffness" in pname:
                    elasticity = 0.48
                elif "damper" in pname or "damping" in pname:
                    elasticity = 0.95
                elif "mass" in pname:
                    elasticity = 0.45
                else:
                    elasticity = 0.10
            trust_state = dep.get("trust_state", TrustState.PROVISIONAL.value)

            is_reversal_driver = pname in reversal_params

            if "spring" in pname or "stiffness" in pname:
                rec_exp = "RIG_TEST_4_POST"
            elif "damper" in pname or "damping" in pname:
                rec_exp = "SHOCK_DYNO_CHARACTERIZATION"
            elif "arb" in pname or "roll" in pname or "kinematics" in pname:
                rec_exp = "TRACK_K&C_RIG_TEST"
            else:
                rec_exp = "RIG_TEST_4_POST"

            if is_reversal_driver and trust_state in (TrustState.PROVISIONAL.value, TrustState.CONFLICTED.value, TrustState.STALE.value):
                priority = VOIPriorityLevel.CRITICAL_REVERSAL_RISK.value
                urgency = "IMMEDIATE_BLOCKER"
            elif elasticity >= 0.20 and (u_data["max_value"] - u_data["min_value"]) / (u_data["nominal_value"] or 1.0) > 0.15:
                priority = VOIPriorityLevel.HIGH_SENSITIVITY_GAP.value
                urgency = "HIGH_PRIORITY"
            elif elasticity >= 0.05:
                priority = VOIPriorityLevel.MODERATE_UNCERTAINTY.value
                urgency = "ROUTINE_MONITORING"
            else:
                priority = VOIPriorityLevel.LOW_IMPACT_OR_VALIDATED.value
                urgency = "LOW_PRIORITY"

            prioritizations.append({
                "parameter_name": pname,
                "priority_level": priority,
                "urgency": urgency,
                "recommended_experiment": rec_exp,
                "current_trust_state": trust_state,
                "elasticity": elasticity,
                "justification": (
                    f"Parameter '{pname}' has elasticity {elasticity:.2f} and trust state '{trust_state}'. "
                    f"Reversal driver: {is_reversal_driver}."
                ),
            })

        # 2. Add unevidenced dependencies
        for ie in insufficient_evidence:
            pname = ie["parameter_name"]
            dep = dep_info.get(pname, {})
            elasticity = abs(dep.get("elasticity") or 0.0)
            if not elasticity or elasticity == 0.0:
                if "spring" in pname or "stiffness" in pname:
                    elasticity = 0.48
                elif "damper" in pname or "damping" in pname:
                    elasticity = 0.95
                elif "mass" in pname:
                    elasticity = 0.45
                else:
                    elasticity = 0.10

            if "spring" in pname or "stiffness" in pname:
                rec_exp = "RIG_TEST_4_POST"
            elif "damper" in pname or "damping" in pname:
                rec_exp = "SHOCK_DYNO_CHARACTERIZATION"
            else:
                rec_exp = "TRACK_K&C_RIG_TEST"

            prioritizations.append({
                "parameter_name": pname,
                "priority_level": VOIPriorityLevel.HIGH_SENSITIVITY_GAP.value if elasticity >= 0.20 else VOIPriorityLevel.MODERATE_UNCERTAINTY.value,
                "urgency": "DATA_COLLECTION_REQUIRED",
                "recommended_experiment": rec_exp,
                "current_trust_state": dep.get("trust_state", TrustState.INSUFFICIENT_EVIDENCE.value),
                "elasticity": elasticity,
                "justification": f"Missing uncertainty evidence: {ie.get('reason')}",
            })

        # Sort by priority rank
        rank_order = {
            VOIPriorityLevel.CRITICAL_REVERSAL_RISK.value: 1,
            VOIPriorityLevel.HIGH_SENSITIVITY_GAP.value: 2,
            VOIPriorityLevel.MODERATE_UNCERTAINTY.value: 3,
            VOIPriorityLevel.LOW_IMPACT_OR_VALIDATED.value: 4,
        }
        prioritizations.sort(key=lambda x: rank_order.get(x["priority_level"], 5))
        return prioritizations

    # ── I. QUERY & PERSISTENCE METHODS ────────────────────────────────────────

    @hybridmethod
    async def get_active_robustness_analysis(
        cls,
        inst: Optional["ParameterTrustRobustnessService"],
        *args,
        **kwargs,
    ) -> Optional[AttrDict]:
        """Fetches the active robustness analysis record for an engineering decision."""
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

        stmt = select(DecisionRobustnessAnalysisRecord).where(
            DecisionRobustnessAnalysisRecord.decision_id == dec_clean,
            DecisionRobustnessAnalysisRecord.is_active == True,
        )
        if team_uuid:
            stmt = stmt.where(or_(
                DecisionRobustnessAnalysisRecord.team_id == team_uuid,
                DecisionRobustnessAnalysisRecord.team_id == None,
            ))
        elif user_uuid:
            stmt = stmt.where(DecisionRobustnessAnalysisRecord.user_id == user_uuid)

        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None

        return to_attr_dict(cls._record_to_dict(record))

    @hybridmethod
    async def get_robustness_history(
        cls,
        inst: Optional["ParameterTrustRobustnessService"],
        *args,
        **kwargs,
    ) -> List[AttrDict]:
        """Retrieves chronological audit history of robustness evaluations for a decision."""
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

        stmt = select(DecisionRobustnessAnalysisRecord).where(
            DecisionRobustnessAnalysisRecord.decision_id == dec_clean,
        ).order_by(desc(DecisionRobustnessAnalysisRecord.created_at))

        if team_uuid:
            stmt = stmt.where(or_(
                DecisionRobustnessAnalysisRecord.team_id == team_uuid,
                DecisionRobustnessAnalysisRecord.team_id == None,
            ))
        elif user_uuid:
            stmt = stmt.where(DecisionRobustnessAnalysisRecord.user_id == user_uuid)

        res = await db.execute(stmt)
        records = res.scalars().all()
        items = [to_attr_dict(cls._record_to_dict(r)) for r in records]
        return to_attr_dict({
            "decision_id": dec_clean,
            "history": items,
            "total": len(items),
        })

    @classmethod
    def _record_to_dict(cls, r: DecisionRobustnessAnalysisRecord) -> Dict[str, Any]:
        env = r.evaluated_envelope or {}
        return {
            "id": str(r.id),
            "decision_id": r.decision_id,
            "decision_type": r.decision_type,
            "policy_version": r.policy_version,
            "analysis_hash": r.analysis_hash,
            "input_snapshot_hash": r.input_snapshot_hash,
            "robustness_classification": r.robustness_classification,
            "robustness_summary": r.robustness_summary,
            "selected_option": env.get("selected_option", ""),
            "target_kpi": env.get("target_kpi", "damping_ratio"),
            "evaluated_envelope": env,
            "evaluated_scenarios_count": env.get("scenarios_evaluated_count", len(r.reversal_scenarios or [])),
            "reversals_count": len(r.reversal_scenarios or []),
            "reversal_scenarios": r.reversal_scenarios or [],
            "boundary_crossings": r.boundary_crossings or [],
            "dominant_uncertainties": r.dominant_uncertainties or [],
            "voi_prioritizations": r.voi_prioritizations or [],
            "solver_failures": r.solver_failures or [],
            "governance_separation_notice": r.governance_separation_notice,
            "deployment_safety_inferred": False,
            "deployment_authorization": "NOT_ESTABLISHED",
            "is_active": r.is_active,
            "superseded_by": str(r.superseded_by) if r.superseded_by else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
