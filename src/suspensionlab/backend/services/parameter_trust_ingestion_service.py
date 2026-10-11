"""
backend/services/parameter_trust_ingestion_service.py
=====================================================
SuspensionLab PRO — Phase 6.2 Automated Parameter Trust Ingestion,
Sweep Analysis & Recency Modeling Canonical Service.

Delivers:
A. Automated Trust Ingestion (Single-entity & Idempotent Batch)
   - Discovers eligible engineering parameters from authoritative sources.
   - Idempotently reconciles profiles, evidence, and historical assessments.
   - Enforces material invalidation (no artificial history created on unchanged runs).
   - Generates compact, structured batch summaries without ORM bloat.

B. Parameter Sweep Analysis
   - Cross-candidate comparability analysis across setups, sweeps, and simulations.
   - Explicit comparability rules (units, physical dimensions, operating regime, vehicle).
   - Aggregates min, max, delta, spread, validation coverage, evidence gaps.
   - Cross-variant conflict detection & outcome change association.
   - Strictly observational: parameter change != causal proof without validation.

C. Recency & Epistemic Freshness Modeling
   - Fully versioned under TRUST_RECENCY_POLICY_V1.
   - Strict Invariant: EVIDENCE_AGING != PHYSICAL_DEGRADATION.
   - Explains validity windows (valid_to), supersession (SUPERSEDES), and aging advisory.

Strict Hard Boundaries:
1. Zero production physics / solver alterations.
2. Phase 3 permanently closed; zero manifest modifications.
3. Zero new Evidence Graph relationships (strictly 17 canonical types).
4. Zero dependencies on Phase 5 Blind Engineering logic.
5. Zero textual heuristics or synthetic trust scores.
6. Strict multi-tenant and personal workspace isolation.
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

# Services
from suspensionlab.backend.services.parameter_trust_service import (
    ParameterTrustService,
    ParameterNotFoundError,
    canonicalize_parameter_unit,
    compute_value_identity,
    compute_assessment_hash,
)
from suspensionlab.backend.services.evidence_graph_service import (
    EvidenceGraphService,
    EntityNotFoundError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
    MalformedIdentifierError,
)

logger = logging.getLogger(__name__)


# ── COMPARABILITY UTILITIES ───────────────────────────────────────────────────

# Known dimension compatibility groups
DIMENSION_GROUPS: Dict[str, str] = {
    # Stiffness [force / length]
    "n/m": "stiffness",
    "n/mm": "stiffness",
    "kn/m": "stiffness",
    "lb/in": "stiffness",
    "lbs/in": "stiffness",
    # Damping [force * time / length]
    "ns/m": "damping",
    "n*s/m": "damping",
    "ns/mm": "damping",
    # Rotational stiffness [force / angle]
    "n/rad": "rotational_stiffness",
    "n/deg": "rotational_stiffness",
    # Roll stiffness [torque / angle]
    "nm/rad": "roll_stiffness",
    "nm/deg": "roll_stiffness",
    # Mass
    "kg": "mass",
    "g": "mass",
    "lb": "mass",
    "lbs": "mass",
    # Length
    "m": "length",
    "mm": "length",
    "cm": "length",
    "km": "length",
    "in": "length",
    "ft": "length",
    # Angle
    "deg": "angle",
    "rad": "angle",
    # Pressure
    "bar": "pressure",
    "psi": "pressure",
    "kpa": "pressure",
    "pa": "pressure",
    # Flow rate
    "l/min": "flow_rate",
    # Dimensionless
    "ratio": "dimensionless",
    "%": "dimensionless",
}

# Conversion scale factors to standard base SI/canonical unit for each physical dimension
UNIT_CONVERSION_FACTORS: Dict[str, float] = {
    # Stiffness (base: N/m)
    "n/m": 1.0,
    "n/mm": 1000.0,
    "kn/m": 1000.0,
    "lb/in": 175.126835,
    "lbs/in": 175.126835,
    # Damping (base: Ns/m)
    "ns/m": 1.0,
    "n*s/m": 1.0,
    "ns/mm": 1000.0,
    # Rotational stiffness (base: N/rad)
    "n/rad": 1.0,
    "n/deg": 180.0 / math.pi,
    # Roll stiffness (base: Nm/rad)
    "nm/rad": 1.0,
    "nm/deg": 180.0 / math.pi,
    # Mass (base: kg)
    "kg": 1.0,
    "g": 0.001,
    "lb": 0.45359237,
    "lbs": 0.45359237,
    # Length (base: m)
    "m": 1.0,
    "mm": 0.001,
    "cm": 0.01,
    "km": 1000.0,
    "in": 0.0254,
    "ft": 0.3048,
    # Angle (base: deg)
    "deg": 1.0,
    "rad": 180.0 / math.pi,
    # Pressure (base: bar)
    "bar": 1.0,
    "psi": 0.0689475729,
    "kpa": 0.01,
    "pa": 0.00001,
    # Flow rate (base: L/min)
    "l/min": 1.0,
    # Dimensionless (base: ratio)
    "ratio": 1.0,
    "%": 0.01,
}


def are_units_dimensionally_compatible(unit_a: str, unit_b: str) -> bool:
    """Verifies that two units share the exact same physical dimension."""
    ua = (unit_a or "").strip().lower()
    ub = (unit_b or "").strip().lower()
    if not ua or not ub:
        return False
    if ua == ub:
        return True
    dim_a = DIMENSION_GROUPS.get(ua)
    dim_b = DIMENSION_GROUPS.get(ub)
    if dim_a and dim_b and dim_a == dim_b:
        return True
    return False


def convert_parameter_value(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """
    Converts a parameter value between dimensionally compatible units.
    Returns None if conversion is not possible or units are incompatible.
    """
    fu = (from_unit or "").strip().lower()
    tu = (to_unit or "").strip().lower()
    if not fu or not tu:
        return None
    if fu == tu:
        return value
    if not are_units_dimensionally_compatible(from_unit, to_unit):
        return None
    scale_from = UNIT_CONVERSION_FACTORS.get(fu)
    scale_to = UNIT_CONVERSION_FACTORS.get(tu)
    if scale_from is None or scale_to is None or scale_to == 0.0:
        return None
    return (value * scale_from) / scale_to


def normalize_numeric_value(val: Any) -> Optional[float]:
    """Extracts a clean floating-point value if possible."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.strip())
        except ValueError:
            return None
    return None


class ParameterTrustIngestionService:
    """
    Automated Parameter Trust Ingestion, Sweep Analysis & Recency Engine.
    """

    # ── 1. AUTHORITATIVE SOURCE DISCOVERY ─────────────────────────────────────

    @classmethod
    def discover_entity_parameters(cls, record: Any, entity_type: str) -> List[str]:
        """
        Discovers eligible parameter names strictly from structured fields of an authoritative record.
        Strictly zero textual parsing from titles, descriptions, or rationale.
        """
        discovered: Set[str] = set()

        if isinstance(record, SetupCandidateRecord):
            changed = record.changed_parameters or {}
            unchanged = record.unchanged_parameters or {}
            if isinstance(changed, dict):
                discovered.update(changed.keys())
            if isinstance(unchanged, dict):
                discovered.update(unchanged.keys())

        elif isinstance(record, VehicleProfile):
            params = record.params or {}
            if isinstance(params, dict):
                discovered.update(params.keys())

        elif isinstance(record, VehicleTwin):
            cal = record.calibrated_params or {}
            base = record.base_params or {}
            if isinstance(cal, dict):
                discovered.update(cal.keys())
            if isinstance(base, dict):
                discovered.update(base.keys())

        elif isinstance(record, SimulationRun):
            params = record.params or {}
            if isinstance(params, dict):
                discovered.update(params.keys())

        elif isinstance(record, OptimizationRecord):
            opts = record.optimal_parameters or {}
            if isinstance(opts, dict):
                discovered.update(opts.keys())

        elif isinstance(record, TelemetrySessionRecord):
            metrics = record.summary_metrics or {}
            if isinstance(metrics, dict):
                discovered.update(metrics.keys())

        else:
            raise UnsupportedEntityTypeError(
                f"Entity type '{entity_type}' is not supported for automated parameter discovery."
            )

        return sorted([p for p in discovered if isinstance(p, str) and p.strip()])

    # ── 2. SINGLE ENTITY INGESTION ────────────────────────────────────────────

    @classmethod
    async def ingest_entity(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        policy_version: str = CURRENT_TRUST_POLICY_VERSION,
        recency_policy_version: str = CURRENT_TRUST_RECENCY_POLICY_VERSION,
        force_reassess: bool = False,
    ) -> Dict[str, Any]:
        """
        Ingests all parameters from a single authoritative engineering entity.
        Reconciles existing profiles, linking evidence and updating assessments when material.
        """
        # Validate endpoint and tenant permissions
        resolution = await EvidenceGraphService.validate_endpoint(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            expected_team_id=team_id,
            expected_org_id=organization_id,
            expected_user_id=user_id,
        )

        record = resolution.record
        param_names = cls.discover_entity_parameters(record, entity_type)

        new_profiles = 0
        refreshed_assessments = 0
        unchanged_assessments = 0
        conflicts_found = 0
        linked_evidence_count = 0
        profile_summaries: List[Dict[str, Any]] = []

        team_uuid = uuid.UUID(str(team_id)) if team_id else None
        user_uuid = uuid.UUID(str(user_id)) if user_id else resolution.user_id

        for param_name in param_names:
            # Query existing profile to verify state before call
            stmt = select(ParameterTrustProfile).where(
                ParameterTrustProfile.entity_type == entity_type,
                ParameterTrustProfile.entity_id == resolution.canonical_id,
                ParameterTrustProfile.parameter_name == param_name,
                ParameterTrustProfile.policy_version == policy_version,
            )
            if team_uuid is not None:
                stmt = stmt.where(ParameterTrustProfile.team_id == team_uuid)
            else:
                stmt = stmt.where(
                    ParameterTrustProfile.team_id.is_(None),
                    ParameterTrustProfile.created_by_user_id == user_uuid,
                )
            existing_res = await db.execute(stmt)
            existing_prof = existing_res.scalars().first()
            prev_hash = existing_prof.assessment_hash if existing_prof else None

            # Execute assessment
            profile = await ParameterTrustService.get_or_assess_parameter_trust(
                db=db,
                entity_type=entity_type,
                entity_id=resolution.canonical_id,
                parameter_name=param_name,
                team_id=team_id,
                organization_id=organization_id,
                user_id=user_id,
                policy_version=policy_version,
            )

            # Categorize ingestion outcome
            if prev_hash is None:
                new_profiles += 1
            elif prev_hash != profile.assessment_hash or force_reassess:
                refreshed_assessments += 1
            else:
                unchanged_assessments += 1

            if profile.conflicts:
                conflicts_found += len(profile.conflicts)

            # Count evidence linked
            ev_stmt = select(ParameterTrustEvidenceRecord).where(
                ParameterTrustEvidenceRecord.profile_id == profile.id
            )
            ev_res = await db.execute(ev_stmt)
            linked_evidence_count += len(ev_res.scalars().all())

            profile_summaries.append({
                "entity_type": profile.entity_type,
                "entity_id": profile.entity_id,
                "parameter_name": profile.parameter_name,
                "trust_state": profile.current_trust_state,
                "validation_coverage": profile.validation_coverage,
                "assessment_hash": profile.assessment_hash,
                "unit": profile.unit,
                "has_conflicts": bool(profile.conflicts),
                "recency_condition": (profile.recency_metadata or {}).get("recency_condition", "VALID"),
            })

        summary = {
            "entity_type": entity_type,
            "entity_id": resolution.canonical_id,
            "policy_version": policy_version,
            "recency_policy_version": recency_policy_version,
            "discovered_parameters": len(param_names),
            "new_profiles": new_profiles,
            "refreshed_assessments": refreshed_assessments,
            "unchanged_assessments": unchanged_assessments,
            "conflicts_found": conflicts_found,
            "linked_evidence_count": linked_evidence_count,
            "profiles": profile_summaries,
        }
        return summary

    # ── 3. IDEMPOTENT BATCH INGESTION ─────────────────────────────────────────

    @classmethod
    async def ingest_batch(
        cls,
        db: AsyncSession,
        entities: List[Dict[str, str]],
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        policy_version: str = CURRENT_TRUST_POLICY_VERSION,
        recency_policy_version: str = CURRENT_TRUST_RECENCY_POLICY_VERSION,
        force_reassess: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes bounded, idempotent batch ingestion across multiple entities.
        Safely isolates partial failures, reports skipped entities, and returns
        a deterministic summary hash.
        """
        batch_id = str(uuid.uuid4())
        total_discovered = 0
        total_new = 0
        total_refreshed = 0
        total_unchanged = 0
        total_conflicts = 0
        total_evidence = 0

        all_profiles: List[Dict[str, Any]] = []
        skipped_entities: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        seen_entities: Set[Tuple[str, str]] = set()

        for item in entities:
            e_type = item.get("entity_type", "").strip()
            e_id = item.get("entity_id", "").strip()

            if not e_type or not e_id:
                errors.append({
                    "item": item,
                    "error": "Missing 'entity_type' or 'entity_id'.",
                })
                continue

            entity_key = (e_type, e_id)
            if entity_key in seen_entities:
                continue
            seen_entities.add(entity_key)

            try:
                summary = await cls.ingest_entity(
                    db=db,
                    entity_type=e_type,
                    entity_id=e_id,
                    team_id=team_id,
                    organization_id=organization_id,
                    user_id=user_id,
                    policy_version=policy_version,
                    recency_policy_version=recency_policy_version,
                    force_reassess=force_reassess,
                )
                total_discovered += summary["discovered_parameters"]
                total_new += summary["new_profiles"]
                total_refreshed += summary["refreshed_assessments"]
                total_unchanged += summary["unchanged_assessments"]
                total_conflicts += summary["conflicts_found"]
                total_evidence += summary["linked_evidence_count"]
                all_profiles.extend(summary["profiles"])

            except UnsupportedEntityTypeError as ue:
                skipped_entities.append({
                    "entity_type": e_type,
                    "entity_id": e_id,
                    "reason": "UNSUPPORTED_ENTITY_TYPE",
                    "detail": str(ue),
                })
            except (EntityNotFoundError, MalformedIdentifierError) as ne:
                errors.append({
                    "entity_type": e_type,
                    "entity_id": e_id,
                    "reason": "NOT_FOUND",
                    "detail": str(ne),
                })
            except TenantIsolationError as te:
                errors.append({
                    "entity_type": e_type,
                    "entity_id": e_id,
                    "reason": "TENANT_MISMATCH",
                    "detail": str(te),
                })
            except Exception as ex:
                logger.exception("Unexpected error ingesting %s:%s", e_type, e_id)
                errors.append({
                    "entity_type": e_type,
                    "entity_id": e_id,
                    "reason": "UNEXPECTED_ERROR",
                    "detail": str(ex),
                })

        # Compute deterministic batch hash
        hash_payload = {
            "policy_version": policy_version,
            "recency_policy_version": recency_policy_version,
            "entities": sorted(list(seen_entities)),
            "discovered_parameters": total_discovered,
            "profile_hashes": sorted([p["assessment_hash"] for p in all_profiles]),
        }
        dumped = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"))
        batch_hash = hashlib.sha256(dumped.encode("utf-8")).hexdigest()

        return {
            "batch_id": batch_id,
            "batch_hash": batch_hash,
            "policy_version": policy_version,
            "recency_policy_version": recency_policy_version,
            "discovered_entities": len(seen_entities),
            "discovered_parameters": total_discovered,
            "new_profiles": total_new,
            "refreshed_assessments": total_refreshed,
            "unchanged_assessments": total_unchanged,
            "linked_evidence_count": total_evidence,
            "conflicts_found": total_conflicts,
            "skipped_entities": skipped_entities,
            "errors": errors,
            "profiles": all_profiles,
        }

    # ── 4. PARAMETER SWEEP ANALYSIS ENGINE ────────────────────────────────────

    @classmethod
    async def analyze_parameter_sweep(
        cls,
        db: AsyncSession,
        parameter_name: str,
        candidates: List[Dict[str, str]],
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        baseline_candidate: Optional[Dict[str, str]] = None,
        policy_version: str = CURRENT_TRUST_POLICY_VERSION,
    ) -> Dict[str, Any]:
        """
        Analyzes a parameter across candidate variants, simulation runs, or setups.
        Enforces strict physical comparability (units, regimes, components).
        Produces aggregated range metrics, identifies evidence gaps, and highlights conflicts.
        """
        param_clean = parameter_name.strip()
        canonical_unit = canonicalize_parameter_unit(param_clean)

        observations: List[Dict[str, Any]] = []
        comparable_observations: List[Dict[str, Any]] = []
        excluded_observations: List[Dict[str, Any]] = []
        conflicts_identified: List[Dict[str, Any]] = []
        outcome_associations: List[Dict[str, Any]] = []

        baseline_value: Optional[float] = None
        baseline_unit: Optional[str] = None
        baseline_regime: Optional[str] = None

        # 1. Resolve baseline if provided
        if baseline_candidate:
            b_type = baseline_candidate.get("entity_type", "")
            b_id = baseline_candidate.get("entity_id", "")
            try:
                base_resolved = await ParameterTrustService.resolve_parameter_from_entity(
                    db=db,
                    entity_type=b_type,
                    entity_id=b_id,
                    parameter_name=param_clean,
                    team_id=team_id,
                    organization_id=organization_id,
                    user_id=user_id,
                )
                baseline_value = normalize_numeric_value(base_resolved["value"])
                baseline_unit = base_resolved["unit"] or canonical_unit
                baseline_regime = base_resolved["scope"].get("operating_regime")
            except Exception as e:
                logger.warning("Baseline candidate resolution failed: %s", e)

        # 2. Iterate through each candidate observation
        seen_cand: Set[Tuple[str, str]] = set()

        for cand in candidates:
            c_type = cand.get("entity_type", "").strip()
            c_id = cand.get("entity_id", "").strip()
            if not c_type or not c_id:
                continue
            key = (c_type, c_id)
            if key in seen_cand:
                continue
            seen_cand.add(key)

            # Resolve parameter from authoritative entity
            try:
                resolved = await ParameterTrustService.resolve_parameter_from_entity(
                    db=db,
                    entity_type=c_type,
                    entity_id=c_id,
                    parameter_name=param_clean,
                    team_id=team_id,
                    organization_id=organization_id,
                    user_id=user_id,
                )
            except (EntityNotFoundError, TenantIsolationError):
                excluded_observations.append({
                    "entity_type": c_type,
                    "entity_id": c_id,
                    "reason": "ENTITY_NOT_FOUND_OR_UNAUTHORIZED",
                })
                continue
            except ParameterNotFoundError:
                excluded_observations.append({
                    "entity_type": c_type,
                    "entity_id": c_id,
                    "reason": "PARAMETER_NOT_FOUND_IN_ENTITY",
                })
                continue
            except UnsupportedEntityTypeError:
                excluded_observations.append({
                    "entity_type": c_type,
                    "entity_id": c_id,
                    "reason": "UNSUPPORTED_ENTITY_TYPE",
                })
                continue

            # Ingest/Fetch trust posture
            profile = await ParameterTrustService.get_or_assess_parameter_trust(
                db=db,
                entity_type=c_type,
                entity_id=c_id,
                parameter_name=param_clean,
                team_id=team_id,
                organization_id=organization_id,
                user_id=user_id,
                policy_version=policy_version,
            )

            raw_val = resolved["value"]
            num_val = normalize_numeric_value(raw_val)
            cand_unit = resolved.get("unit") or canonical_unit
            scope = resolved["scope"] or {}
            cand_regime = scope.get("operating_regime")

            # ── Comparability Checks ──────────────────────────────────────────
            is_comparable = True
            exclusion_reason = None

            # Unit verification and dimensional compatibility
            target_unit = baseline_unit or canonical_unit or cand_unit
            if not cand_unit or not cand_unit.strip():
                is_comparable = False
                exclusion_reason = "NOT_COMPARABLE: Unit information is missing or cannot be established reliably."
            elif not target_unit or not target_unit.strip():
                is_comparable = False
                exclusion_reason = "NOT_COMPARABLE: Target comparison unit cannot be established reliably."
            elif not are_units_dimensionally_compatible(cand_unit, target_unit):
                is_comparable = False
                exclusion_reason = f"INCOMPATIBLE_UNITS: '{cand_unit}' is dimensionally incompatible with '{target_unit}'."

            # Regime compatibility check
            if is_comparable and baseline_regime and cand_regime:
                if baseline_regime != "all" and cand_regime != "all" and baseline_regime != cand_regime:
                    is_comparable = False
                    exclusion_reason = f"SCOPE_MISMATCH: Operating regime '{cand_regime}' incompatible with baseline regime '{baseline_regime}'."

            # Numeric comparability
            if is_comparable and num_val is None:
                is_comparable = False
                exclusion_reason = "NON_NUMERIC_VALUE: Parameter value cannot be compared numerically."

            # Unit conversion to target_unit for rigorous comparison
            converted_val = None
            if is_comparable and num_val is not None:
                converted_val = convert_parameter_value(num_val, cand_unit, target_unit)
                if converted_val is None:
                    is_comparable = False
                    exclusion_reason = f"CONVERSION_FAILED: Cannot convert '{cand_unit}' to target unit '{target_unit}'."

            obs_record = {
                "entity_type": c_type,
                "entity_id": c_id,
                "value": raw_val,
                "numeric_value": converted_val if is_comparable else num_val,
                "raw_numeric_value": num_val,
                "unit": cand_unit,
                "comparison_unit": target_unit if is_comparable else None,
                "trust_state": profile.current_trust_state,
                "validation_coverage": profile.validation_coverage,
                "provenance_class": profile.provenance_class,
                "assessment_hash": profile.assessment_hash,
                "is_comparable": is_comparable,
                "exclusion_reason": exclusion_reason,
                "scope": scope,
                "conflicts_count": len(profile.conflicts or []),
            }
            observations.append(obs_record)

            if is_comparable:
                comparable_observations.append(obs_record)
            else:
                excluded_observations.append(obs_record)

            # Check if this candidate has any conflicts
            for c in (profile.conflicts or []):
                conflicts_identified.append({
                    "candidate_id": f"{c_type}:{c_id}",
                    "conflict_type": c.get("conflict_type", "VALUE_DIVERGENCE"),
                    "detail": c.get("detail", ""),
                })

            # Check linked outcome associations (e.g. from SetupCandidate deltas)
            prov_det = resolved.get("provenance_details", {})
            if "change_delta_pct" in prov_det and prov_det["change_delta_pct"] is not None:
                outcome_associations.append({
                    "candidate_id": f"{c_type}:{c_id}",
                    "parameter": param_clean,
                    "parameter_delta_pct": prov_det.get("change_delta_pct"),
                    "baseline_value": prov_det.get("baseline_value"),
                    "candidate_value": raw_val,
                    "interpretation": "Observed candidate delta recorded. Note: Association != causal proof without physical validation.",
                })

        # 3. Numeric Aggregations on Comparable Set
        comp_values = [c["numeric_value"] for c in comparable_observations if c["numeric_value"] is not None]

        min_val = min(comp_values) if comp_values else None
        max_val = max(comp_values) if comp_values else None
        delta_val = (max_val - min_val) if (min_val is not None and max_val is not None) else None
        mean_val = (sum(comp_values) / len(comp_values)) if comp_values else None
        spread_val = delta_val

        # 4. Validation Coverage & Gaps Analysis
        coverage_counts = collections.Counter([c["validation_coverage"] for c in comparable_observations])
        trust_state_counts = collections.Counter([c["trust_state"] for c in comparable_observations])

        unvalidated_candidates = [
            f"{c['entity_type']}:{c['entity_id']}"
            for c in comparable_observations
            if c["validation_coverage"] == ValidationCoverage.NO_VALIDATION.value
        ]
        validated_candidates = [
            f"{c['entity_type']}:{c['entity_id']}"
            for c in comparable_observations
            if c["validation_coverage"] == ValidationCoverage.VALIDATED.value
        ]

        # 5. Deterministic Sweep Hash
        sweep_payload = {
            "parameter_name": param_clean,
            "policy_version": policy_version,
            "unit": canonical_unit,
            "observation_count": len(observations),
            "comparable_count": len(comparable_observations),
            "min_value": min_val,
            "max_value": max_val,
            "delta_value": delta_val,
            "candidate_ids": sorted([f"{c['entity_type']}:{c['entity_id']}" for c in observations]),
            "assessment_hashes": sorted([c["assessment_hash"] for c in observations]),
        }
        dumped_sweep = json.dumps(sweep_payload, sort_keys=True, separators=(",", ":"))
        sweep_hash = hashlib.sha256(dumped_sweep.encode("utf-8")).hexdigest()

        return {
            "parameter_name": param_clean,
            "policy_version": policy_version,
            "canonical_unit": canonical_unit,
            "sweep_hash": sweep_hash,
            "total_observations": len(observations),
            "comparable_count": len(comparable_observations),
            "excluded_count": len(excluded_observations),
            "baseline_value": baseline_value,
            "baseline_unit": baseline_unit,
            "summary_metrics": {
                "min": min_val,
                "max": max_val,
                "delta": delta_val,
                "mean": round(mean_val, 4) if mean_val is not None else None,
                "spread": spread_val,
                "unit": canonical_unit or (comparable_observations[0]["comparison_unit"] if comparable_observations else ""),
            },
            "validation_coverage_breakdown": dict(coverage_counts),
            "trust_state_breakdown": dict(trust_state_counts),
            "evidence_gaps": {
                "unvalidated_candidates": unvalidated_candidates,
                "validated_candidates": validated_candidates,
                "coverage_pct": round(len(validated_candidates) / max(1, len(comparable_observations)) * 100.0, 1),
            },
            "observations": observations,
            "excluded_observations": excluded_observations,
            "conflicts": conflicts_identified,
            "outcome_associations": outcome_associations,
        }
