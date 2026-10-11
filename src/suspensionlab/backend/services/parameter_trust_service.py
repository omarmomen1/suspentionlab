"""
backend/services/parameter_trust_service.py
===========================================
SuspensionLab PRO — Phase 6.1 Parameter Trust Map Canonical Service.

Answers with auditable precision:
"How much confidence should an engineering user place in this parameter, and why?"

Core Conceptual Chain:
    PARAMETER
        ↓
    SOURCE / PROVENANCE
        ↓
    EVIDENCE (Traversed via existing Evidence Graph relationships)
        ↓
    VALIDATION HISTORY
        ↓
    TRUST STATE
        ↓
    ENGINEERING USE

Strict Invariants:
1. Pure provenance/trust layer: NEVER overwrites authoritative parameters.
2. Zero magic scores or opaque weighting formulas.
3. Explicit Trust States & Validation Coverage vocabularies.
4. Deterministic SHA-256 assessment hashing (identical inputs -> identical hash).
5. Zero textual heuristics: trust is never inferred from title, description, or notes.
6. Tenant & personal workspace isolation enforced at query boundaries.
7. Zero dependencies on Phase 5 blind engineering logic.
"""
from __future__ import annotations

import collections
import hashlib
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy import and_, or_, select, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

# Database Models
from suspensionlab.backend.database.models.parameter_trust import (
    ParameterTrustProfile,
    ParameterTrustEvidenceRecord,
    ParameterTrustAssessmentRecord,
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    TRUST_POLICY_V1,
    CURRENT_TRUST_POLICY_VERSION,
    TRUST_RECENCY_POLICY_V1,
    CURRENT_TRUST_RECENCY_POLICY_VERSION,
    DEFAULT_RECENCY_ADVISORY_THRESHOLD_DAYS,
    RecencyCondition,
    TrustConflictType,
)
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
    SupportedEntityType,
)
from suspensionlab.backend.database.models.decision_loop import (
    ApprovalRecord,
    BlindValidationRecord,
    InvestigationRecord,
    OptimizationRecord,
    SetupComparisonRecord,
    TelemetrySessionRecord,
)
from suspensionlab.backend.database.models.setup_engineering import (
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    EngineeringProblemRecord,
    PostTrackReconciliationRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
)
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin
from suspensionlab.backend.services.evidence_graph_service import (
    EvidenceGraphService,
    EntityNotFoundError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
    MalformedIdentifierError,
)

logger = logging.getLogger(__name__)


# ── CANONICAL UNITS REGISTRY ──────────────────────────────────────────────────
# Standard engineering unit mapping based on automotive engineering standards.
CANONICAL_PARAMETER_UNITS: Dict[str, str] = {
    # Stiffness / Rates
    "k_s": "N/m",
    "k_sf": "N/m",
    "k_sr": "N/m",
    "k_spring_f": "N/m",
    "k_spring_r": "N/m",
    "k_spring_front": "N/m",
    "k_spring_rear": "N/m",
    "front_spring_rate": "N/m",
    "rear_spring_rate": "N/m",
    "spring_rate_front": "N/m",
    "spring_rate_rear": "N/m",
    "k_arb_f": "N/m",
    "k_arb_r": "N/m",
    "front_arb_rate": "N/m",
    "rear_arb_rate": "N/m",
    "arb_rate_front": "N/m",
    "arb_rate_rear": "N/m",
    "k_t": "N/m",
    "k_tire": "N/m",
    "cornering_stiffness": "N/rad",
    "C_alpha": "N/rad",
    # Damping
    "c": "Ns/m",
    "c_bump_f": "Ns/m",
    "c_bump_r": "Ns/m",
    "c_rebound_f": "Ns/m",
    "c_rebound_r": "Ns/m",
    "damper_bump_front": "Ns/m",
    "damper_bump_rear": "Ns/m",
    # Masses & Geometries
    "m_s": "kg",
    "m_u": "kg",
    "mass_kg": "kg",
    "wheelbase_m": "m",
    "track_width_m": "m",
    "MR": "ratio",
    "motion_ratio": "ratio",
    "roll_angle_deg": "deg",
    "camber_deg": "deg",
    "toe_deg": "deg",
    # Fluids & Pressures
    "coolant_flow_rate": "L/min",
    "tire_pressure_bar": "bar",
}


def canonicalize_parameter_unit(param_name: str, fallback_unit: Optional[str] = None) -> str:
    """Returns the canonical engineering unit for a given parameter name."""
    if fallback_unit and fallback_unit.strip():
        return fallback_unit.strip()
    clean = param_name.lower().strip()
    return CANONICAL_PARAMETER_UNITS.get(clean, "")


def compute_value_identity(value: Any) -> str:
    """Produces a deterministic hash representation of a parameter value."""
    if isinstance(value, float):
        formatted = f"{value:.8g}"
    elif isinstance(value, (dict, list)):
        formatted = json.dumps(value, sort_keys=True, separators=(",", ":"))
    else:
        formatted = str(value)
    return hashlib.sha256(formatted.encode("utf-8")).hexdigest()[:16]


def compute_assessment_hash(
    entity_type: str,
    entity_id: str,
    parameter_name: str,
    parameter_path: str,
    value_identity: str,
    policy_version: str,
    trust_state: str,
    validation_coverage: str,
    scope: Dict[str, Any],
    evidence_hashes: Sequence[str],
    conflicts: Sequence[Dict[str, Any]],
) -> str:
    """
    Computes a deterministic SHA-256 identity for a trust assessment.
    Guarantees that identical inputs produce an identical assessment hash,
    and any change in evidence or value yields a different hash.
    """
    payload = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "parameter_name": parameter_name,
        "parameter_path": parameter_path,
        "value_identity": value_identity,
        "policy_version": policy_version,
        "trust_state": trust_state,
        "validation_coverage": validation_coverage,
        "scope": scope,
        "evidence_hashes": sorted(list(evidence_hashes)),
        "conflicts": list(conflicts),
    }
    dumped = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


class ParameterNotFoundError(Exception):
    """Raised when the specified parameter name cannot be found in the authoritative entity."""
    pass


class ParameterTrustService:
    """
    Canonical Parameter Trust Service implementing the Phase 6.1 Trust Map.
    """

    @classmethod
    async def resolve_parameter_from_entity(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        parameter_name: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """
        Resolves the parameter identity, path, value, unit, and structured provenance
        from the underlying authoritative entity.
        Enforces tenant isolation using EvidenceGraphService.validate_endpoint.
        """
        resolution = await EvidenceGraphService.validate_endpoint(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            expected_team_id=team_id,
            expected_org_id=organization_id,
            expected_user_id=user_id,
        )
        record = resolution.record
        param_clean = parameter_name.strip()

        param_value = None
        param_path = ""
        provenance_cls = ProvenanceClass.INFERRED.value
        provenance_details: Dict[str, Any] = {
            "source_type": entity_type,
            "source_id": resolution.canonical_id,
            "artifact_hash": resolution.artifact_hash,
        }
        scope: Dict[str, Any] = {}
        entity_unit: Optional[str] = None

        # ── 1. SetupCandidateRecord ───────────────────────────────────────────
        if isinstance(record, SetupCandidateRecord):
            changed = record.changed_parameters or {}
            unchanged = record.unchanged_parameters or {}
            prov_map = record.parameter_provenance or {}
            validity_dom = record.validity_domain or {}

            # Check structured unit on entity
            if param_clean in changed:
                item = changed[param_clean]
                if isinstance(item, dict) and "unit" in item and item["unit"]:
                    entity_unit = str(item["unit"]).strip()
                param_value = item.get("candidate") if isinstance(item, dict) else item
                param_path = f"changed_parameters.{param_clean}.candidate"
                prov_str = prov_map.get(param_clean, "optimization")
                provenance_cls = prov_str if prov_str in [p.value for p in ProvenanceClass] else ProvenanceClass.OPTIMIZATION.value
                provenance_details["change_delta_pct"] = item.get("delta_pct") if isinstance(item, dict) else None
                provenance_details["baseline_value"] = item.get("baseline") if isinstance(item, dict) else None
            elif param_clean in unchanged:
                item = unchanged[param_clean]
                if isinstance(item, dict) and "unit" in item and item["unit"]:
                    entity_unit = str(item["unit"]).strip()
                    param_value = item.get("value", item)
                else:
                    param_value = item
                param_path = f"unchanged_parameters.{param_clean}"
                prov_str = prov_map.get(param_clean, "historical_setup")
                provenance_cls = prov_str if prov_str in [p.value for p in ProvenanceClass] else ProvenanceClass.HISTORICAL_SETUP.value
            else:
                raise ParameterNotFoundError(
                    f"Parameter '{param_clean}' not found in SetupCandidate '{record.setup_id}'."
                )

            # Check validity_domain for structured units mapping
            if not entity_unit and isinstance(validity_dom, dict):
                v_units = validity_dom.get("parameter_units") or validity_dom.get("units")
                if isinstance(v_units, dict) and param_clean in v_units and v_units[param_clean]:
                    entity_unit = str(v_units[param_clean]).strip()

            # Populate scope from structured validity_domain
            scope = {
                "setup_id": record.setup_id,
                "parent_setup_id": record.parent_setup_id,
                "operating_regime": validity_dom.get("operating_regime") or validity_dom.get("regime") or "all",
                "valid_from": str(record.created_at.isoformat()) if record.created_at else None,
                "valid_to": validity_dom.get("valid_to"),
                "vehicle_id": validity_dom.get("vehicle_id") or validity_dom.get("car_ref"),
            }

        # ── 2. VehicleProfile ─────────────────────────────────────────────────
        elif isinstance(record, VehicleProfile):
            params = record.params or {}
            if param_clean not in params:
                raise ParameterNotFoundError(
                    f"Parameter '{param_clean}' not found in VehicleProfile '{record.name}'."
                )
            param_value = params[param_clean]
            param_path = f"params.{param_clean}"
            provenance_cls = ProvenanceClass.MANUALLY_ENTERED.value
            scope = {
                "vehicle_id": str(record.id),
                "profile_name": record.name,
                "vehicle_type": record.vehicle_type,
                "version": record.version,
            }
            if isinstance(params, dict) and f"{param_clean}_unit" in params:
                entity_unit = str(params[f"{param_clean}_unit"]).strip()

        # ── 3. VehicleTwin ────────────────────────────────────────────────────
        elif isinstance(record, VehicleTwin):
            cal_params = record.calibrated_params or {}
            base_params = record.base_params or {}
            scope = {
                "car_ref": record.car_ref,
                "setup_ref": record.setup_ref,
                "track_ref": record.track_ref,
            }
            if param_clean in cal_params:
                param_value = cal_params[param_clean]
                param_path = f"calibrated_params.{param_clean}"
                provenance_cls = ProvenanceClass.CALIBRATED.value
                provenance_details["calibration_count"] = record.calibration_count
                provenance_details["last_calibration_at"] = record.last_calibration_at.isoformat() if record.last_calibration_at else None
            elif param_clean in base_params:
                param_value = base_params[param_clean]
                param_path = f"base_params.{param_clean}"
                provenance_cls = ProvenanceClass.LITERATURE_REFERENCE.value
            else:
                raise ParameterNotFoundError(
                    f"Parameter '{param_clean}' not found in VehicleTwin '{record.car_ref}'."
                )

        # ── 4. SimulationRun ──────────────────────────────────────────────────
        elif isinstance(record, SimulationRun):
            params = record.params or {}
            if param_clean not in params:
                raise ParameterNotFoundError(
                    f"Parameter '{param_clean}' not found in SimulationRun '{record.label}'."
                )
            param_value = params[param_clean]
            param_path = f"params.{param_clean}"
            provenance_cls = ProvenanceClass.SIMULATION_DERIVED.value
            scope = {
                "simulation_label": record.label,
                "simulation_type": record.simulation_type,
                "vehicle_ref": record.vehicle_ref,
                "setup_ref": record.setup_ref,
                "track_ref": record.track_ref,
            }
            provenance_details["solver_version"] = record.solver_version
            provenance_details["software_version"] = record.software_version
            if isinstance(params, dict):
                if f"{param_clean}_unit" in params:
                    entity_unit = str(params[f"{param_clean}_unit"]).strip()
                elif isinstance(params.get("units"), dict) and param_clean in params["units"]:
                    entity_unit = str(params["units"][param_clean]).strip()

        # ── 5. OptimizationRecord ─────────────────────────────────────────────
        elif isinstance(record, OptimizationRecord):
            opt_params = record.optimal_parameters or {}
            if param_clean not in opt_params:
                raise ParameterNotFoundError(
                    f"Parameter '{param_clean}' not found in OptimizationRecord '{record.optimization_code}'."
                )
            param_value = opt_params[param_clean]
            param_path = f"optimal_parameters.{param_clean}"
            provenance_cls = ProvenanceClass.OPTIMIZATION.value
            scope = {
                "optimization_code": record.optimization_code,
                "optimal_setup_id": record.optimal_setup_id,
            }
            provenance_details["status"] = record.status
            provenance_details["solver_calls"] = record.solver_calls

        # ── 6. TelemetrySessionRecord ─────────────────────────────────────────
        elif isinstance(record, TelemetrySessionRecord):
            summary = record.summary_metrics or {}
            if param_clean not in summary:
                raise ParameterNotFoundError(
                    f"Parameter '{param_clean}' not found in summary metrics of TelemetrySession '{record.session_code}'."
                )
            param_value = summary[param_clean]
            param_path = f"summary_metrics.{param_clean}"
            provenance_cls = ProvenanceClass.MEASURED.value
            scope = {
                "session_code": record.session_code,
                "vehicle_id": record.vehicle_id,
                "setup_id": record.setup_id,
                "track_name": record.track_name,
            }
            provenance_details["sample_count"] = record.sample_count
            provenance_details["duration_s"] = record.duration_s

        else:
            raise UnsupportedEntityTypeError(
                f"Entity type '{entity_type}' does not provide structured engineering parameters."
            )

        # Resolve unit: structured entity unit takes precedence over canonical registry
        if entity_unit and entity_unit.strip():
            unit = entity_unit.strip()
        else:
            unit = canonicalize_parameter_unit(param_clean)

        val_id = compute_value_identity(param_value)
        return {
            "entity_type": entity_type,
            "entity_id": resolution.canonical_id,
            "parameter_name": param_clean,
            "parameter_path": param_path,
            "value": param_value,
            "value_identity": val_id,
            "unit": unit,
            "provenance_class": provenance_cls,
            "provenance_details": provenance_details,
            "scope": scope,
            "artifact_hash": resolution.artifact_hash,
            "user_id": resolution.user_id,
            "team_id": resolution.team_id,
            "organization_id": resolution.organization_id,
            "record": record,
        }

    @classmethod
    async def traverse_supporting_evidence(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Traverses the Evidence Graph rooted at the parameter's owning entity
        using strictly CANONICAL relationships to gather supporting evidence.
        Enforces tenant isolation and service-level entity validation.
        """
        # Query 1-hop and 2-hop edges connected to this entity
        edges = await EvidenceGraphService.list_edges(
            db=db,
            team_id=team_id,
            user_id=user_id,
            organization_id=organization_id,
            source_type=entity_type,
            source_id=entity_id,
            limit=100,
        )
        incoming_edges = await EvidenceGraphService.list_edges(
            db=db,
            team_id=team_id,
            user_id=user_id,
            organization_id=organization_id,
            target_type=entity_type,
            target_id=entity_id,
            limit=100,
        )

        all_edges = list(edges) + list(incoming_edges)
        evidence_items: List[Dict[str, Any]] = []
        seen_targets: Set[Tuple[str, str]] = set()

        for edge in all_edges:
            # Determine neighbor entity
            if edge.source_type == entity_type and edge.source_id == entity_id:
                neighbor_type = edge.target_type
                neighbor_id = edge.target_id
                rel = edge.relationship
            else:
                neighbor_type = edge.source_type
                neighbor_id = edge.source_id
                rel = edge.relationship

            key = (neighbor_type, neighbor_id)
            if key in seen_targets:
                continue
            seen_targets.add(key)

            try:
                res = await EvidenceGraphService.validate_endpoint(
                    db=db,
                    entity_type=neighbor_type,
                    entity_id=neighbor_id,
                    expected_team_id=team_id,
                    expected_org_id=organization_id,
                    expected_user_id=user_id,
                )
            except (EntityNotFoundError, TenantIsolationError):
                continue

            # Extract structured metadata from authoritative record
            meta: Dict[str, Any] = {}
            rec = res.record
            ts: Optional[datetime] = getattr(rec, "created_at", None) or getattr(rec, "timestamp", None)

            if isinstance(rec, BlindValidationRecord):
                meta["gate_verdict"] = rec.gate_verdict
                meta["holdout_r2"] = rec.holdout_r2
                meta["is_zero_leakage"] = rec.is_zero_leakage
            elif isinstance(rec, SimulationRun):
                meta["model_validity"] = rec.model_validity
                meta["simulation_type"] = rec.simulation_type
                meta["warnings"] = rec.warnings
            elif isinstance(rec, TelemetrySessionRecord):
                meta["sample_count"] = rec.sample_count
                meta["duration_s"] = rec.duration_s
            elif isinstance(rec, ApprovalRecord):
                meta["status"] = rec.status
                meta["approver_role"] = rec.approver_role
            elif isinstance(rec, OptimizationRecord):
                meta["status"] = rec.status
                meta["solver_calls"] = rec.solver_calls
            elif isinstance(rec, SetupComparisonRecord):
                meta["validity"] = rec.validity
                meta["deltas"] = rec.deltas
            elif isinstance(rec, PostTrackReconciliationRecord):
                meta["model_version"] = rec.model_version

            evidence_items.append({
                "evidence_type": neighbor_type,
                "evidence_id": res.canonical_id,
                "artifact_hash": res.artifact_hash,
                "relationship": rel,
                "evidence_timestamp": ts,
                "metadata": meta,
                "record": rec,
            })

        # Deterministic sorting
        evidence_items.sort(key=lambda x: (x["evidence_type"], x["evidence_id"], x["relationship"]))
        return evidence_items

    @classmethod
    async def detect_conflicts(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        parameter_name: str,
        current_value: Any,
        scope: Dict[str, Any],
        evidence_items: Sequence[Dict[str, Any]],
        team_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Detects conflicting evidence or diverging values across authoritative sources
        within the same scope without overwriting either source.
        """
        conflicts: List[Dict[str, Any]] = []

        # 1. Check for contradictory validation outcomes
        val_records = [e for e in evidence_items if e["evidence_type"] == SupportedEntityType.BLIND_VALIDATION.value]
        passed = [v for v in val_records if v["metadata"].get("gate_verdict") == "PASSED"]
        failed = [v for v in val_records if v["metadata"].get("gate_verdict") == "FAILED"]

        if passed and failed:
            conflicts.append({
                "conflict_type": "CONTRADICTORY_VALIDATION",
                "source_a": passed[0]["evidence_id"],
                "verdict_a": "PASSED",
                "source_b": failed[0]["evidence_id"],
                "verdict_b": "FAILED",
                "detail": f"Conflicting validation verdicts: {passed[0]['evidence_id']} passed but {failed[0]['evidence_id']} failed gate criteria.",
            })

        # 2. Check for value divergence in linked SetupComparison records
        comp_records = [e for e in evidence_items if e["evidence_type"] == SupportedEntityType.SETUP_COMPARISON.value]
        for comp in comp_records:
            rec = comp["record"]
            deltas = getattr(rec, "deltas", []) or []
            if isinstance(deltas, list):
                for d in deltas:
                    if isinstance(d, dict) and d.get("metric") == parameter_name:
                        base_val = d.get("baseline")
                        cand_val = d.get("candidate")
                        if base_val is not None and cand_val is not None and base_val != cand_val:
                            # If delta exceeds 5%, record structured divergence conflict
                            delta_pct = abs(d.get("delta_pct", 0.0))
                            if delta_pct > 5.0:
                                conflicts.append({
                                    "conflict_type": "VALUE_DIVERGENCE",
                                    "source_a": f"Baseline:{rec.baseline_setup_id}",
                                    "value_a": base_val,
                                    "source_b": f"Candidate:{rec.candidate_setup_id}",
                                    "value_b": cand_val,
                                    "delta": d.get("delta_abs", abs(cand_val - base_val)),
                                    "delta_pct": delta_pct,
                                    "detail": f"Parameter divergence of {delta_pct:.2f}% identified in setup comparison {rec.comparison_code}.",
                                })

        # 3. Check for external conflicting candidates in the same scope (e.g. same vehicle)
        vehicle_id = scope.get("vehicle_id") or scope.get("car_ref")
        if vehicle_id and isinstance(current_value, (int, float)):
            # Search other setups in the same team for conflicting values
            stmt = select(SetupCandidateRecord)
            if team_id is not None:
                stmt = stmt.where(SetupCandidateRecord.team_id == uuid.UUID(str(team_id)))
            elif user_id is not None:
                stmt = stmt.where(
                    SetupCandidateRecord.team_id.is_(None),
                    SetupCandidateRecord.user_id == uuid.UUID(str(user_id)),
                )
            stmt = stmt.where(SetupCandidateRecord.setup_id != entity_id)
            res = await db.execute(stmt.limit(10))
            other_setups = res.scalars().all()

            superseded_ids = {
                e["evidence_id"]
                for e in evidence_items
                if e.get("relationship") == EvidenceGraphRelationship.SUPERSEDES.value
            }

            for other in other_setups:
                if other.setup_id in superseded_ids:
                    continue
                other_dom = other.validity_domain or {}
                if (other_dom.get("vehicle_id") == vehicle_id or other_dom.get("car_ref") == vehicle_id):
                    # Check other's changed parameters
                    other_changed = other.changed_parameters or {}
                    if parameter_name in other_changed:
                        item = other_changed[parameter_name]
                        other_val = item.get("candidate") if isinstance(item, dict) else item
                        if isinstance(other_val, (int, float)) and abs(other_val - current_value) > 1e-6:
                            rel_diff = abs(other_val - current_value) / (abs(current_value) + 1e-9) * 100.0
                            if rel_diff > 1.0: # Discrepancy > 1%
                                conflicts.append({
                                    "conflict_type": "VALUE_DIVERGENCE",
                                    "source_a": f"SetupCandidate:{entity_id}",
                                    "value_a": current_value,
                                    "source_b": f"SetupCandidate:{other.setup_id}",
                                    "value_b": other_val,
                                    "delta": abs(other_val - current_value),
                                    "delta_pct": round(rel_diff, 2),
                                    "detail": f"Conflicting values between {entity_id} ({current_value}) and {other.setup_id} ({other_val}) for vehicle {vehicle_id}.",
                                })

        return conflicts

    @classmethod
    def evaluate_trust_posture(
        cls,
        parameter_name: str,
        value: Any,
        provenance_class: str,
        provenance_details: Dict[str, Any],
        evidence_items: Sequence[Dict[str, Any]],
        conflicts: Sequence[Dict[str, Any]],
        scope: Dict[str, Any],
        policy_version: str = CURRENT_TRUST_POLICY_VERSION,
    ) -> Tuple[TrustState, ValidationCoverage, Dict[str, Any], Dict[str, Any]]:
        """
        Pure, deterministic state machine computing:
        (TrustState, ValidationCoverage, Explanation, RecencyMetadata).
        Strictly zero textual heuristics.
        """
        # ── 1. Validation Coverage Evaluation ─────────────────────────────────
        val_records = [e for e in evidence_items if e["evidence_type"] == SupportedEntityType.BLIND_VALIDATION.value]
        passed_vals = [v for v in val_records if v["metadata"].get("gate_verdict") == "PASSED"]
        failed_vals = [v for v in val_records if v["metadata"].get("gate_verdict") == "FAILED"]

        reconcil_records = [e for e in evidence_items if e["evidence_type"] == SupportedEntityType.POST_TRACK_RECONCILIATION.value]

        if passed_vals and failed_vals:
            coverage = ValidationCoverage.CONFLICTING_VALIDATION
        elif passed_vals or reconcil_records:
            # Check rigorous threshold (holdout_r2 >= 0.85 and zero leakage)
            all_passed_rigorous = all(
                v["metadata"].get("holdout_r2", 0.0) >= 0.85 and v["metadata"].get("is_zero_leakage") is True
                for v in passed_vals
            )
            if all_passed_rigorous or reconcil_records:
                coverage = ValidationCoverage.VALIDATED
            else:
                coverage = ValidationCoverage.PARTIAL_VALIDATION
        elif failed_vals:
            coverage = ValidationCoverage.PARTIAL_VALIDATION
        else:
            coverage = ValidationCoverage.NO_VALIDATION

        # ── 2. Recency Metadata Computation ───────────────────────────────────
        all_timestamps = [
            e["evidence_timestamp"] for e in evidence_items if e["evidence_timestamp"] is not None
        ]
        val_timestamps = [
            v["evidence_timestamp"] for v in val_records if v["evidence_timestamp"] is not None
        ]

        latest_ev_ts = max(all_timestamps) if all_timestamps else None
        latest_val_ts = max(val_timestamps) if val_timestamps else None
        latest_val_id = passed_vals[0]["evidence_id"] if passed_vals else (val_records[0]["evidence_id"] if val_records else None)

        now = datetime.now(timezone.utc)
        age_days = None
        if latest_ev_ts is not None:
            # Normalize naive / aware
            ts_aware = latest_ev_ts if latest_ev_ts.tzinfo else latest_ev_ts.replace(tzinfo=timezone.utc)
            age_days = max(0.0, round((now - ts_aware).total_seconds() / 86400.0, 2))

        # Check supersession
        is_superseded = any(
            e.get("relationship") == EvidenceGraphRelationship.SUPERSEDES.value for e in evidence_items
        )

        # Check validity window expiration
        valid_to_str = scope.get("valid_to")
        is_validity_expired = False
        if valid_to_str:
            try:
                # Handle YYYY-MM-DD or ISO format safely
                v_to = datetime.fromisoformat(str(valid_to_str))
                if not v_to.tzinfo:
                    v_to = v_to.replace(tzinfo=timezone.utc)
                if now > v_to:
                    is_validity_expired = True
            except Exception:
                pass

        # Determine canonical recency condition under TRUST_RECENCY_POLICY_V1
        advisory_threshold = DEFAULT_RECENCY_ADVISORY_THRESHOLD_DAYS
        reassessment_recommended = False
        reassessment_reason = None

        if is_validity_expired:
            recency_condition = RecencyCondition.VALIDITY_EXPIRED.value
            reassessment_recommended = True
            reassessment_reason = f"Declared validity window expired at '{valid_to_str}'."
        elif is_superseded:
            recency_condition = RecencyCondition.SUPERSEDED.value
            reassessment_recommended = True
            reassessment_reason = "Parameter source has been superseded by a newer engineering artifact in the Evidence Graph."
        elif age_days is not None and age_days > advisory_threshold:
            recency_condition = RecencyCondition.REASSESSMENT_RECOMMENDED.value
            reassessment_recommended = True
            reassessment_reason = f"Supporting evidence is {age_days:.1f} days old (exceeds advisory threshold of {advisory_threshold:.0f} days). Epistemic freshness review recommended."
        elif latest_ev_ts is not None or latest_val_ts is not None:
            recency_condition = RecencyCondition.VALID.value
        else:
            recency_condition = RecencyCondition.INSUFFICIENT_RECENCY_INFORMATION.value

        recency_meta = {
            "recency_policy_version": TRUST_RECENCY_POLICY_V1,
            "recency_condition": recency_condition,
            "reassessment_recommended": reassessment_recommended,
            "reassessment_reason": reassessment_reason,
            "is_validity_expired": is_validity_expired,
            "is_superseded": is_superseded,
            "evidence_timestamp": latest_ev_ts.isoformat() if latest_ev_ts else None,
            "validation_timestamp": latest_val_ts.isoformat() if latest_val_ts else None,
            "source_version": scope.get("version") or provenance_details.get("artifact_hash", "v1")[:8],
            "latest_supporting_validation": latest_val_id,
            "valid_from": scope.get("valid_from"),
            "valid_to": scope.get("valid_to"),
            "age_days": age_days,
            "advisory_threshold_days": advisory_threshold,
            "epistemic_aging_note": "Evidence aging reflects epistemic recency, NOT physical component degradation.",
            "reference_time": now.isoformat(),
        }

        # ── 3. Trust State Determination (Deterministic Rule Set) ─────────────
        reasons: List[str] = []
        limitations: List[str] = []

        # Scope limitations
        if scope.get("operating_regime") and scope.get("operating_regime") != "all":
            limitations.append(f"Trust valid strictly within operating regime '{scope['operating_regime']}'.")
        if scope.get("valid_to"):
            if is_validity_expired:
                limitations.append(f"Trust validity interval expired at '{scope['valid_to']}'.")
            else:
                limitations.append(f"Trust validity interval expires at '{scope['valid_to']}'.")

        if reassessment_recommended and not is_validity_expired and not is_superseded:
            limitations.append(f"Evidence age ({age_days:.1f} days) exceeds advisory threshold ({advisory_threshold:.0f} days). Epistemic freshness review recommended.")

        # Check for validity expiration
        if is_validity_expired:
            state = TrustState.STALE
            reasons.append(f"Declared validity window expired at '{valid_to_str}'. Parameter requires reassessment.")
        # Check for superseding / staleness
        elif is_superseded:
            state = TrustState.STALE
            reasons.append("Parameter has been superseded by a newer engineering artifact in the Evidence Graph.")
        # Check for conflicts
        elif conflicts:
            state = TrustState.CONFLICTED
            for c in conflicts:
                reasons.append(f"Conflict detected: {c.get('detail')}")
        # Check for failed validation
        elif failed_vals:
            state = TrustState.REJECTED
            reasons.append(
                f"Validation artifact '{failed_vals[0]['evidence_id']}' failed gate criteria (holdout RMSE or R2 out of spec)."
            )
        # Check if validation passed
        elif coverage == ValidationCoverage.VALIDATED:
            approvals = [e for e in evidence_items if e["evidence_type"] == SupportedEntityType.APPROVAL.value and e["metadata"].get("status") == "APPROVED"]
            is_cal_or_measured = provenance_class in (ProvenanceClass.MEASURED.value, ProvenanceClass.CALIBRATED.value)

            if is_cal_or_measured and approvals:
                state = TrustState.HIGH_CONFIDENCE
                reasons.append(
                    f"Parameter verified by out-of-sample physical validation ({latest_val_id}), calibrated provenance ({provenance_class}), and engineering sign-off ({approvals[0]['evidence_id']})."
                )
            else:
                state = TrustState.VALIDATED
                reasons.append(
                    f"Parameter validated through out-of-sample holdout gate ({latest_val_id})."
                )
        # Check if supported by simulation / optimization / experiment
        elif any(e["evidence_type"] in (SupportedEntityType.SIMULATION_RUN.value, SupportedEntityType.OPTIMIZATION.value, SupportedEntityType.EXPERIMENT.value) for e in evidence_items):
            state = TrustState.SUPPORTED
            sim_item = next((e for e in evidence_items if e["evidence_type"] == SupportedEntityType.SIMULATION_RUN.value), None)
            if sim_item:
                reasons.append(f"Supported by simulation run '{sim_item['evidence_id']}'. Note: Simulation existence != physical validation.")
            else:
                reasons.append(f"Supported by optimization / experiment artifact without physical holdout validation.")
        # Check provisional
        elif provenance_class in (ProvenanceClass.MANUALLY_ENTERED.value, ProvenanceClass.IMPORTED.value, ProvenanceClass.INFERRED.value):
            state = TrustState.PROVISIONAL
            reasons.append(f"Parameter is {provenance_class} without corroborating simulation or validation records.")
        # Insufficient evidence
        elif not evidence_items:
            state = TrustState.INSUFFICIENT_EVIDENCE
            reasons.append("No supporting evidence or relationships found in the Evidence Graph for this parameter.")
        else:
            state = TrustState.UNASSESSED
            reasons.append("Parameter has not been evaluated under current trust policy.")

        # Add provenance reason
        reasons.append(f"Authoritative source provenance confirmed as '{provenance_class}'.")

        explanation = {
            "state": state.value,
            "reasons": reasons,
            "supporting_evidence": [
                {
                    "evidence_type": e["evidence_type"],
                    "evidence_id": e["evidence_id"],
                    "artifact_hash": e["artifact_hash"],
                    "relationship": e["relationship"],
                    "timestamp": e["evidence_timestamp"].isoformat() if e["evidence_timestamp"] else None,
                }
                for e in evidence_items
            ],
            "conflicts": list(conflicts),
            "scope": scope,
            "limitations": limitations,
        }

        return state, coverage, explanation, recency_meta

    @classmethod
    async def get_or_assess_parameter_trust(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        parameter_name: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        policy_version: str = CURRENT_TRUST_POLICY_VERSION,
    ) -> ParameterTrustProfile:
        """
        Assesses or updates the Parameter Trust Profile for a given parameter identity.
        Persists an immutable ParameterTrustAssessmentRecord if assessment state or evidence changes.
        """
        # 1. Resolve parameter from authoritative entity
        resolved = await cls.resolve_parameter_from_entity(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            parameter_name=parameter_name,
            team_id=team_id,
            organization_id=organization_id,
            user_id=user_id,
        )

        # 2. Traverse supporting evidence via Evidence Graph
        evidence_items = await cls.traverse_supporting_evidence(
            db=db,
            entity_type=resolved["entity_type"],
            entity_id=resolved["entity_id"],
            team_id=team_id,
            user_id=user_id,
            organization_id=organization_id,
        )

        # 3. Detect conflicts
        conflicts = await cls.detect_conflicts(
            db=db,
            entity_type=resolved["entity_type"],
            entity_id=resolved["entity_id"],
            parameter_name=resolved["parameter_name"],
            current_value=resolved["value"],
            scope=resolved["scope"],
            evidence_items=evidence_items,
            team_id=team_id,
            user_id=user_id,
            organization_id=organization_id,
        )

        # 4. Evaluate trust state machine
        state, coverage, explanation, recency_meta = cls.evaluate_trust_posture(
            parameter_name=resolved["parameter_name"],
            value=resolved["value"],
            provenance_class=resolved["provenance_class"],
            provenance_details=resolved["provenance_details"],
            evidence_items=evidence_items,
            conflicts=conflicts,
            scope=resolved["scope"],
            policy_version=policy_version,
        )

        evidence_hashes = [e["artifact_hash"] for e in evidence_items]

        # 5. Compute deterministic assessment hash
        assess_hash = compute_assessment_hash(
            entity_type=resolved["entity_type"],
            entity_id=resolved["entity_id"],
            parameter_name=resolved["parameter_name"],
            parameter_path=resolved["parameter_path"],
            value_identity=resolved["value_identity"],
            policy_version=policy_version,
            trust_state=state.value,
            validation_coverage=coverage.value,
            scope=resolved["scope"],
            evidence_hashes=evidence_hashes,
            conflicts=conflicts,
        )

        value_ref = {
            "value": resolved["value"],
            "value_identity": resolved["value_identity"],
            "unit": resolved["unit"],
            "source_entity": f"{resolved['entity_type']}:{resolved['entity_id']}",
        }

        # 6. Find or create ParameterTrustProfile
        team_uuid = uuid.UUID(str(team_id)) if team_id else None
        org_uuid = uuid.UUID(str(organization_id)) if organization_id else None
        user_uuid = uuid.UUID(str(user_id)) if user_id else resolved["user_id"]

        stmt = select(ParameterTrustProfile).where(
            ParameterTrustProfile.entity_type == resolved["entity_type"],
            ParameterTrustProfile.entity_id == resolved["entity_id"],
            ParameterTrustProfile.parameter_name == resolved["parameter_name"],
            ParameterTrustProfile.policy_version == policy_version,
        )
        if team_uuid is not None:
            stmt = stmt.where(ParameterTrustProfile.team_id == team_uuid)
        else:
            stmt = stmt.where(
                ParameterTrustProfile.team_id.is_(None),
                ParameterTrustProfile.created_by_user_id == user_uuid,
            )

        res = await db.execute(stmt)
        profile = res.scalars().first()

        hash_changed = False
        if profile is None:
            hash_changed = True
            profile = ParameterTrustProfile(
                organization_id=org_uuid or resolved["organization_id"],
                team_id=team_uuid or resolved["team_id"],
                created_by_user_id=user_uuid,
                entity_type=resolved["entity_type"],
                entity_id=resolved["entity_id"],
                parameter_name=resolved["parameter_name"],
                parameter_path=resolved["parameter_path"],
                unit=resolved["unit"],
                value_reference=value_ref,
                provenance_class=resolved["provenance_class"],
                provenance_details=resolved["provenance_details"],
                scope=resolved["scope"],
                current_trust_state=state.value,
                validation_coverage=coverage.value,
                policy_version=policy_version,
                assessment_hash=assess_hash,
                explanation=explanation,
                conflicts=conflicts,
                recency_metadata=recency_meta,
            )
            db.add(profile)
            await db.flush()
        else:
            if profile.assessment_hash != assess_hash:
                hash_changed = True
                profile.value_reference = value_ref
                profile.current_trust_state = state.value
                profile.validation_coverage = coverage.value
                profile.assessment_hash = assess_hash
                profile.explanation = explanation
                profile.conflicts = conflicts
                profile.recency_metadata = recency_meta
                profile.updated_at = datetime.now(timezone.utc)
                await db.flush()

        # Update evidence records and record historical assessment only if hash changed or profile is new
        if hash_changed:
            existing_ev_stmt = select(ParameterTrustEvidenceRecord).where(
                ParameterTrustEvidenceRecord.profile_id == profile.id
            )
            existing_ev_res = await db.execute(existing_ev_stmt)
            existing_evs = existing_ev_res.scalars().all()
            for ev in existing_evs:
                await db.delete(ev)

            for e in evidence_items:
                ev_rec = ParameterTrustEvidenceRecord(
                    profile_id=profile.id,
                    organization_id=profile.organization_id,
                    team_id=profile.team_id,
                    evidence_type=e["evidence_type"],
                    evidence_id=e["evidence_id"],
                    artifact_hash=e["artifact_hash"],
                    relationship=e["relationship"],
                    evidence_timestamp=e["evidence_timestamp"],
                    metadata_=e["metadata"],
                )
                db.add(ev_rec)

            assessment_log = ParameterTrustAssessmentRecord(
                profile_id=profile.id,
                organization_id=profile.organization_id,
                team_id=profile.team_id,
                user_id=user_uuid,
                trust_state=state.value,
                validation_coverage=coverage.value,
                policy_version=policy_version,
                assessment_hash=assess_hash,
                value_identity=resolved["value_identity"],
                supporting_evidence_hashes=evidence_hashes,
                explanation=explanation,
                conflicts=conflicts,
                recency_metadata=recency_meta,
            )
            db.add(assessment_log)

        await db.commit()
        await db.refresh(profile)
        return profile

    @classmethod
    async def get_parameter_evidence(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        parameter_name: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the supporting evidence references for a parameter.
        """
        profile = await cls.get_or_assess_parameter_trust(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            parameter_name=parameter_name,
            team_id=team_id,
            organization_id=organization_id,
            user_id=user_id,
        )

        stmt = (
            select(ParameterTrustEvidenceRecord)
            .where(ParameterTrustEvidenceRecord.profile_id == profile.id)
            .order_by(asc(ParameterTrustEvidenceRecord.evidence_type), asc(ParameterTrustEvidenceRecord.evidence_id))
        )
        res = await db.execute(stmt)
        evs = res.scalars().all()
        return [
            {
                "id": str(e.id),
                "evidence_type": e.evidence_type,
                "evidence_id": e.evidence_id,
                "artifact_hash": e.artifact_hash,
                "relationship": e.relationship,
                "evidence_timestamp": e.evidence_timestamp.isoformat() if e.evidence_timestamp else None,
                "metadata": e.metadata_ or {},
            }
            for e in evs
        ]

    @classmethod
    async def explain_parameter_trust(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        parameter_name: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """
        Returns the structured, deterministic explanation object for a parameter's trust.
        """
        profile = await cls.get_or_assess_parameter_trust(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            parameter_name=parameter_name,
            team_id=team_id,
            organization_id=organization_id,
            user_id=user_id,
        )
        return {
            "parameter_identity": {
                "entity_type": profile.entity_type,
                "entity_id": profile.entity_id,
                "parameter_name": profile.parameter_name,
                "parameter_path": profile.parameter_path,
            },
            "trust_state": profile.current_trust_state,
            "policy_version": profile.policy_version,
            "assessment_hash": profile.assessment_hash,
            "explanation": profile.explanation,
        }

    @classmethod
    async def get_parameter_trust_history(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        parameter_name: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns the chronological history of assessments for this parameter.
        Deterministically ordered by created_at desc, id asc.
        """
        profile = await cls.get_or_assess_parameter_trust(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            parameter_name=parameter_name,
            team_id=team_id,
            organization_id=organization_id,
            user_id=user_id,
        )

        stmt = (
            select(ParameterTrustAssessmentRecord)
            .where(ParameterTrustAssessmentRecord.profile_id == profile.id)
            .order_by(desc(ParameterTrustAssessmentRecord.created_at), asc(ParameterTrustAssessmentRecord.id))
        )
        res = await db.execute(stmt)
        assessments = res.scalars().all()
        return [
            {
                "id": str(a.id),
                "trust_state": a.trust_state,
                "validation_coverage": a.validation_coverage,
                "policy_version": a.policy_version,
                "assessment_hash": a.assessment_hash,
                "value_identity": a.value_identity,
                "supporting_evidence_hashes": a.supporting_evidence_hashes,
                "explanation": a.explanation,
                "conflicts": a.conflicts,
                "recency_metadata": a.recency_metadata,
                "created_at": a.created_at.isoformat(),
            }
            for a in assessments
        ]
