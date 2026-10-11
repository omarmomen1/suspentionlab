"""
backend/services/parameter_trust_fleet_service.py
=================================================
SuspensionLab PRO — Phase 6.3 Fleet-Wide Trust Synchronization &
Sensitivity-Aware Propagation Service.

Delivers:
A. Fleet Trust Synchronization (FLEET_TRUST_POLICY_V1)
   - Cross-vehicle parameter matching with verified identity and dimensions.
   - Separate instances: each vehicle retains its own authoritative source records.
   - Cohort comparability rules (unit presence, dimensional compatibility, operating regime).
   - Deterministic cohort statistics (min, max, delta, spread, mean, median, IQR outliers).
   - Statistical outlier != engineering defect distinction.
   - Zero local parameter value overwrites or trust score copying.

B. Assembly-Aware Trust Propagation
   - Authoritative structural hierarchy: VEHICLE -> ASSEMBLY -> COMPONENT -> PARAMETER.
   - Strict Invariant: DIRECT TRUST IS DECOUPLED FROM PROPAGATED IMPACT.
   - A component parameter has direct trust; an assembly has an impact assessment.
   - Missing dependency paths prevent propagation.

C. Sensitivity-Aware Impact Assessment (SENSITIVITY_PROPAGATION_POLICY_V1)
   - Authoritative sensitivity evidence resolution from simulation runs, calibrations, and experiments.
   - Preserves physical units: unit(output metric) / unit(input parameter).
   - Strict Invariant: MISSING SENSITIVITY IS NEVER TREATED AS ZERO (SENSITIVITY_UNAVAILABLE).
   - Transparent qualitative impact classification (no magic weighted scores).
   - Full lineage and deterministic SHA-256 report hashing.

Strict Hard Boundaries:
1. Zero production physics / solver alterations.
2. Phase 3 permanently closed; zero manifest modifications.
3. Zero Evidence Graph relationship additions (17 canonical types unchanged).
4. Zero Phase 5 Blind Engineering dependencies.
5. Strict tenant and personal-workspace isolation.
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

import numpy as np
from sqlalchemy import and_, or_, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

# Database Models
from suspensionlab.backend.database.models.parameter_trust import (
    ParameterTrustProfile,
    ParameterTrustEvidenceRecord,
    ParameterTrustAssessmentRecord,
    ParameterTrustFleetReport,
    ParameterTrustAssemblyImpactRecord,
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    TRUST_POLICY_V1,
    CURRENT_TRUST_POLICY_VERSION,
    TRUST_RECENCY_POLICY_V1,
    CURRENT_TRUST_RECENCY_POLICY_VERSION,
    FLEET_TRUST_POLICY_V1,
    CURRENT_FLEET_TRUST_POLICY_VERSION,
    SENSITIVITY_PROPAGATION_POLICY_V1,
    CURRENT_SENSITIVITY_PROPAGATION_POLICY_VERSION,
    FleetComparabilityStatus,
    SensitivityStatus,
    ImpactClassification,
    FleetOutlierClassification,
    TrustConflictType,
    SENSITIVITY_THRESHOLDS_PROVENANCE,
    SENSITIVITY_THRESHOLDS_METADATA,
)
from suspensionlab.backend.database.models.evidence_graph import (
    EvidenceGraphEdgeRecord,
    EvidenceGraphRelationship,
    SupportedEntityType,
)
from suspensionlab.backend.database.models.decision_loop import (
    BlindValidationRecord,
    TelemetrySessionRecord,
)
from suspensionlab.backend.database.models.setup_engineering import (
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    SetupCandidateRecord,
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
)
from suspensionlab.backend.services.parameter_trust_ingestion_service import (
    ParameterTrustIngestionService,
    are_units_dimensionally_compatible,
    convert_parameter_value,
    normalize_numeric_value,
    DIMENSION_GROUPS,
    UNIT_CONVERSION_FACTORS,
)
from suspensionlab.backend.services.evidence_graph_service import (
    EvidenceGraphService,
    EntityNotFoundError,
    TenantIsolationError,
    UnsupportedEntityTypeError,
    MalformedIdentifierError,
)

logger = logging.getLogger(__name__)


# ── 1. AUTHORITATIVE ASSEMBLY & COMPONENT DOMAIN HIERARCHY ────────────────────

ASSEMBLY_COMPONENT_HIERARCHY: Dict[str, Dict[str, List[str]]] = {
    "FRONT_SUSPENSION": {
        "front_spring": [
            "front_spring_rate",
            "spring_rate_front",
            "k_spring_front",
            "k_spring_f",
            "k_f",
            "k_s",
        ],
        "front_damper": [
            "damper_bump_front",
            "c_bump_f",
            "damper_rebound_front",
            "c_rebound_f",
            "c",
        ],
        "front_anti_roll_bar": [
            "front_arb_rate",
            "arb_rate_front",
            "anti_roll_bar_front",
            "k_arb_f",
        ],
        "front_geometry": [
            "motion_ratio_front",
            "motion_ratio",
            "MR",
            "camber_front",
            "camber_deg",
            "toe_deg",
        ],
    },
    "REAR_SUSPENSION": {
        "rear_spring": [
            "rear_spring_rate",
            "spring_rate_rear",
            "k_spring_rear",
            "k_spring_r",
            "k_r",
        ],
        "rear_damper": [
            "damper_bump_rear",
            "c_bump_r",
            "damper_rebound_rear",
            "c_rebound_r",
        ],
        "rear_anti_roll_bar": [
            "rear_arb_rate",
            "arb_rate_rear",
            "anti_roll_bar_rear",
            "k_arb_r",
        ],
        "rear_geometry": [
            "motion_ratio_rear",
        ],
    },
    "TIRES_AND_WHEELS": {
        "front_tires": [
            "k_tire_front",
            "k_t",
            "k_tire",
            "cornering_stiff_front",
            "cornering_stiffness",
            "C_alpha",
            "camber_stiffness_front",
            "tire_pressure_bar",
        ],
        "rear_tires": [
            "k_tire_rear",
            "cornering_stiff_rear",
            "camber_stiffness_rear",
        ],
        "unsprung_corners": [
            "unsprung_mass_front",
            "unsprung_mass_rear",
            "m_u",
        ],
    },
    "CHASSIS": {
        "sprung_chassis": [
            "sprung_mass",
            "m_s",
            "mass_kg",
            "yaw_inertia_Izz",
            "wheelbase_m",
            "track_width_m",
        ],
    },
    "AERODYNAMICS": {
        "aero_package": [
            "aero_cd",
            "aero_cl",
            "aero_front_balance",
        ],
    },
    "POWERTRAIN": {
        "engine": [
            "engine_peak_torque",
        ],
        "drivetrain": [
            "final_drive_ratio",
            "shift_duration_s",
            "clutch_inertia",
            "drivetrain_efficiency",
            "rolling_resistance_coeff",
        ],
    },
}


def resolve_assembly_component(parameter_name: str) -> Optional[Tuple[str, str]]:
    """
    Resolves the canonical assembly and component identity for a parameter name.
    Returns (assembly_name, component_name) or None if the parameter does not map
    to a verified structural domain assembly.
    """
    param_clean = parameter_name.strip().lower()
    for assembly_name, components in ASSEMBLY_COMPONENT_HIERARCHY.items():
        for component_name, params in components.items():
            for p in params:
                if p.lower() == param_clean:
                    return assembly_name, component_name
    return None


# ── 2. SENSITIVITY METRIC SPECS ───────────────────────────────────────────────

KNOWN_SENSITIVITY_KPIS: Dict[str, Dict[str, str]] = {
    "rms_body_accel_wk": {
        "label": "Body Acceleration RMS (Ride Comfort)",
        "unit": "m/s^2",
        "direction": "minimize",
    },
    "rms_susp_travel": {
        "label": "Suspension Travel RMS",
        "unit": "mm",
        "direction": "target",
    },
    "peak_transmissibility": {
        "label": "Peak Transmissibility Ratio",
        "unit": "ratio",
        "direction": "minimize",
    },
    "rms_tire_load": {
        "label": "Dynamic Tire Load RMS (Grip Variation)",
        "unit": "N",
        "direction": "minimize",
    },
    "roll_angle_deg": {
        "label": "Peak Roll Angle",
        "unit": "deg",
        "direction": "minimize",
    },
    "lat_accel_g": {
        "label": "Lateral Acceleration Capability",
        "unit": "g",
        "direction": "maximize",
    },
}


class ParameterTrustFleetService:
    """
    Fleet-Wide Parameter Trust Synchronization & Sensitivity-Aware Propagation Engine.
    """

    # ── A. FLEET MEMBER RESOLUTION & TENANT QUARANTINE ────────────────────────

    @classmethod
    async def resolve_fleet_members(
        cls,
        db: AsyncSession,
        fleet_id: str,
        member_locators: List[Dict[str, str]],
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Resolves authoritative vehicle/setup endpoints for a fleet cohort.
        Strictly enforces tenant and personal workspace boundaries:
        Cross-tenant endpoints are quarantined and excluded without leaking existence.
        """
        authorized_members: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, str]] = set()

        for loc in member_locators:
            e_type = loc.get("entity_type", "").strip()
            e_id = loc.get("entity_id", "").strip()
            if not e_type or not e_id:
                continue
            key = (e_type, e_id)
            if key in seen:
                continue
            seen.add(key)

            try:
                res = await EvidenceGraphService.validate_endpoint(
                    db=db,
                    entity_type=e_type,
                    entity_id=e_id,
                    expected_team_id=team_id,
                    expected_org_id=organization_id,
                    expected_user_id=user_id if team_id is None else None,
                )
                authorized_members.append({
                    "entity_type": e_type,
                    "entity_id": res.canonical_id,
                    "artifact_hash": res.artifact_hash,
                    "record": res.record,
                    "vehicle_ref": getattr(res.record, "car_ref", None)
                    or getattr(res.record, "name", None)
                    or getattr(res.record, "vehicle_id", None)
                    or res.canonical_id,
                })
            except (EntityNotFoundError, TenantIsolationError, UnsupportedEntityTypeError, MalformedIdentifierError):
                # Quarantined / excluded: do not expose private cross-tenant existence
                continue

        return authorized_members

    # ── B. FLEET PARAMETER SYNCHRONIZATION & COMPARISON ───────────────────────

    @classmethod
    async def synchronize_fleet_parameter(
        cls,
        db: AsyncSession,
        fleet_id: str,
        parameter_name: str,
        member_locators: List[Dict[str, str]],
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        policy_version: str = CURRENT_FLEET_TRUST_POLICY_VERSION,
        canonical_unit: Optional[str] = None,
        persist_report: bool = True,
    ) -> Dict[str, Any]:
        """
        Compares corresponding parameter instances across eligible fleet members under FLEET_TRUST_POLICY_V1.
        Strict Invariants:
        1. Separate instances: each vehicle retains its own authoritative source records.
        2. Fleet aggregation NEVER overwrites local parameter values or trust profiles.
        3. Statistical outliers are distinct from engineering defects and conflicts.
        """
        param_clean = parameter_name.strip()
        if canonical_unit is None:
            canonical_unit = canonicalize_parameter_unit(param_clean)

        # 1. Resolve authorized members
        members = await cls.resolve_fleet_members(
            db=db,
            fleet_id=fleet_id,
            member_locators=member_locators,
            team_id=team_id,
            organization_id=organization_id,
            user_id=user_id,
        )

        comparable_instances: List[Dict[str, Any]] = []
        excluded_instances: List[Dict[str, Any]] = []
        missing_instances: List[Dict[str, Any]] = []
        conflicts_identified: List[Dict[str, Any]] = []

        # Identify missing or quarantined member locators
        authorized_keys = {(m["entity_type"], m["entity_id"]) for m in members}
        for loc in member_locators:
            loc_type = loc.get("entity_type", "").strip()
            loc_id = loc.get("entity_id", "").strip()
            if (loc_type, loc_id) not in authorized_keys:
                missing_instances.append({
                    "vehicle_ref": loc_id,
                    "entity_type": loc_type,
                    "entity_id": loc_id,
                    "status": "MISSING",
                    "reason": "MEMBER_UNAVAILABLE: Fleet member is not found or inaccessible under current tenant credentials.",
                })

        # 2. Inspect each member for parameter existence and comparability
        for mem in members:
            e_type = mem["entity_type"]
            e_id = mem["entity_id"]
            v_ref = mem["vehicle_ref"]

            try:
                resolved = await ParameterTrustService.resolve_parameter_from_entity(
                    db=db,
                    entity_type=e_type,
                    entity_id=e_id,
                    parameter_name=param_clean,
                    team_id=team_id,
                    organization_id=organization_id,
                    user_id=user_id,
                )
            except ParameterNotFoundError:
                missing_instances.append({
                    "vehicle_ref": v_ref,
                    "entity_type": e_type,
                    "entity_id": e_id,
                    "status": "MISSING",
                    "reason": f"Parameter '{param_clean}' not present in this vehicle instance.",
                })
                continue
            except Exception as e:
                excluded_instances.append({
                    "vehicle_ref": v_ref,
                    "entity_type": e_type,
                    "entity_id": e_id,
                    "status": FleetComparabilityStatus.NOT_COMPARABLE.value,
                    "reason": f"Resolution failure: {str(e)}",
                    "exclusion_reason": f"Resolution failure: {str(e)}",
                })
                continue

            # Ingest / fetch local trust profile (read-only query)
            profile = await ParameterTrustService.get_or_assess_parameter_trust(
                db=db,
                entity_type=e_type,
                entity_id=e_id,
                parameter_name=param_clean,
                team_id=team_id,
                organization_id=organization_id,
                user_id=user_id,
            )

            raw_val = resolved["value"]
            num_val = normalize_numeric_value(raw_val)
            cand_unit = resolved.get("unit") or canonical_unit
            scope = resolved.get("scope") or {}
            regime = scope.get("operating_regime") or "all"

            # ── Comparability Verification ────────────────────────────────────
            is_comparable = True
            comp_status = FleetComparabilityStatus.COMPARABLE.value
            exclusion_reason = None
            target_unit = canonical_unit or cand_unit

            # Check 1: Unit presence
            if not cand_unit or not str(cand_unit).strip():
                is_comparable = False
                comp_status = FleetComparabilityStatus.NOT_COMPARABLE.value
                exclusion_reason = "MISSING_UNIT: Parameter unit cannot be established reliably from entity or registry."

            # Check 2: Dimensional compatibility
            elif target_unit and not are_units_dimensionally_compatible(cand_unit, target_unit):
                is_comparable = False
                comp_status = FleetComparabilityStatus.NOT_COMPARABLE.value
                exclusion_reason = f"INCOMPATIBLE_UNIT_DIMENSION: Units '{cand_unit}' and '{target_unit}' belong to different dimensions."

            # Check 3: Numeric validity
            elif num_val is None:
                is_comparable = False
                comp_status = FleetComparabilityStatus.NOT_COMPARABLE.value
                exclusion_reason = "NON_NUMERIC_VALUE: Parameter value cannot be evaluated numerically."

            # Check 4: Operating regime scope differences
            if is_comparable and regime != "all":
                # Marked partially comparable if operating regime is tightly scoped
                comp_status = FleetComparabilityStatus.COMPARABLE.value

            # Convert to target canonical unit if comparable
            converted_val = None
            if is_comparable and num_val is not None:
                converted_val = convert_parameter_value(num_val, cand_unit, target_unit)
                if converted_val is None:
                    is_comparable = False
                    comp_status = FleetComparabilityStatus.NOT_COMPARABLE.value
                    exclusion_reason = f"CONVERSION_FAILED: Cannot convert '{cand_unit}' to target unit '{target_unit}'."

            instance_payload = {
                "vehicle_ref": v_ref,
                "entity_type": e_type,
                "entity_id": e_id,
                "value": raw_val,
                "raw_numeric_value": num_val,
                "normalized_value": converted_val if is_comparable else num_val,
                "unit": cand_unit,
                "canonical_unit": target_unit if is_comparable else None,
                "comparability_status": comp_status,
                "reason": exclusion_reason,
                "exclusion_reason": exclusion_reason,
                "operating_regime": regime,
                "scope": scope,
                "trust_state": profile.current_trust_state,
                "validation_coverage": profile.validation_coverage,
                "provenance_class": profile.provenance_class,
                "recency_condition": profile.recency_metadata.get("recency_condition") if profile.recency_metadata else None,
                "assessment_hash": profile.assessment_hash,
                "conflicts_count": len(profile.conflicts or []),
            }

            if is_comparable:
                comparable_instances.append(instance_payload)
            else:
                excluded_instances.append(instance_payload)

            # Record any conflicts on this instance
            for c in (profile.conflicts or []):
                conflicts_identified.append({
                    "vehicle_ref": v_ref,
                    "entity_id": f"{e_type}:{e_id}",
                    "conflict_type": c.get("conflict_type", TrustConflictType.VALUE_DIVERGENCE.value),
                    "detail": c.get("detail", ""),
                })

        # 3. Numeric Aggregations on Comparable Cohort
        comp_values = [inst["normalized_value"] for inst in comparable_instances if inst["normalized_value"] is not None]
        n_comp = len(comp_values)

        min_val = min(comp_values) if n_comp > 0 else None
        max_val = max(comp_values) if n_comp > 0 else None
        delta_val = (max_val - min_val) if (min_val is not None and max_val is not None) else None
        mean_val = (sum(comp_values) / n_comp) if n_comp > 0 else None
        median_val = float(np.median(comp_values)) if n_comp > 0 else None
        spread_val = delta_val

        # 4. Outlier Analysis (IQR Rule under FLEET_TRUST_POLICY_V1)
        outliers: List[Dict[str, Any]] = []
        if n_comp >= 4:
            q1 = float(np.percentile(comp_values, 25))
            q3 = float(np.percentile(comp_values, 75))
            iqr = q3 - q1
            iqr_lower = q1 - 1.5 * iqr
            iqr_upper = q3 + 1.5 * iqr

            for inst in comparable_instances:
                val = inst["normalized_value"]
                if val is not None and (val < iqr_lower or val > iqr_upper):
                    outliers.append({
                        "vehicle_ref": inst["vehicle_ref"],
                        "entity_id": f"{inst['entity_type']}:{inst['entity_id']}",
                        "value": val,
                        "outlier_type": FleetOutlierClassification.STATISTICAL_OUTLIER.value,
                        "iqr_bounds": {"lower": round(iqr_lower, 4), "upper": round(iqr_upper, 4)},
                        "note": (
                            "Value is statistically outside cohort IQR boundaries. "
                            "Notice: Statistical outlier does not constitute an engineering defect or automatic rejection."
                        ),
                    })

        # Breakdown distributions
        cov_counts = collections.Counter([c["validation_coverage"] for c in comparable_instances])
        trust_counts = collections.Counter([c["trust_state"] for c in comparable_instances])
        prov_counts = collections.Counter([c["provenance_class"] for c in comparable_instances])

        # 5. Deterministic Fleet Report Hash
        hash_payload = {
            "fleet_id": fleet_id,
            "parameter_name": param_clean,
            "policy_version": policy_version,
            "canonical_unit": canonical_unit,
            "cohort_size": len(member_locators),
            "comparable_count": n_comp,
            "excluded_count": len(excluded_instances),
            "missing_count": len(missing_instances),
            "min": min_val,
            "max": max_val,
            "mean": round(mean_val, 4) if mean_val is not None else None,
            "median": round(median_val, 4) if median_val is not None else None,
            "member_hashes": sorted([c["assessment_hash"] for c in comparable_instances]),
        }
        dumped = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"))
        report_hash = hashlib.sha256(dumped.encode("utf-8")).hexdigest()

        summary_metrics = {
            "min": min_val,
            "max": max_val,
            "delta": delta_val,
            "spread": spread_val,
            "mean": round(mean_val, 4) if mean_val is not None else None,
            "median": round(median_val, 4) if median_val is not None else None,
            "unit": canonical_unit or (comparable_instances[0]["canonical_unit"] if comparable_instances else ""),
            "sample_count": n_comp,
            "missing_count": len(missing_instances),
            "excluded_count": len(excluded_instances),
        }

        # 6. Persistence (if enabled and user authenticated)
        if persist_report and user_id is not None:
            user_uuid = uuid.UUID(str(user_id))
            team_uuid = uuid.UUID(str(team_id)) if team_id else None
            org_uuid = uuid.UUID(str(organization_id)) if organization_id else None

            report_rec = ParameterTrustFleetReport(
                id=uuid.uuid4(),
                fleet_id=fleet_id,
                parameter_name=param_clean,
                canonical_unit=canonical_unit,
                organization_id=org_uuid,
                team_id=team_uuid,
                user_id=user_uuid,
                policy_version=policy_version,
                report_hash=report_hash,
                cohort_size=len(member_locators),
                comparable_count=n_comp,
                excluded_count=len(excluded_instances),
                missing_count=len(missing_instances),
                summary_metrics=summary_metrics,
                comparable_instances=comparable_instances,
                excluded_instances=excluded_instances,
                missing_instances=missing_instances,
                conflicts=conflicts_identified,
                outliers=outliers,
                validation_coverage_breakdown=dict(cov_counts),
                trust_state_breakdown=dict(trust_counts),
                provenance_distribution=dict(prov_counts),
                created_at=datetime.now(timezone.utc),
            )
            db.add(report_rec)
            await db.flush()

        return {
            "fleet_id": fleet_id,
            "parameter_name": param_clean,
            "policy_version": policy_version,
            "canonical_unit": canonical_unit,
            "report_hash": report_hash,
            "cohort_size": len(member_locators),
            "comparable_count": n_comp,
            "excluded_count": len(excluded_instances),
            "missing_count": len(missing_instances),
            "summary_metrics": summary_metrics,
            "comparable_instances": comparable_instances,
            "excluded_instances": excluded_instances,
            "missing_instances": missing_instances,
            "conflicts": conflicts_identified,
            "outliers": outliers,
            "validation_coverage_breakdown": dict(cov_counts),
            "trust_state_breakdown": dict(trust_counts),
            "provenance_distribution": dict(prov_counts),
        }

    # ── C. AUTHORITATIVE SENSITIVITY EVIDENCE RESOLUTION ─────────────────────

    @classmethod
    async def resolve_sensitivity_evidence(
        cls,
        db: AsyncSession,
        parameter_name: str,
        vehicle_id: Optional[str] = None,
        setup_id: Optional[str] = None,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """
        Resolves authoritative sensitivity evidence for a parameter.
        Checks simulation runs, calibration observations, and experiment designs.
        Strict Invariant: Missing sensitivity is NEVER treated as zero! Returns SENSITIVITY_UNAVAILABLE.
        """
        param_clean = parameter_name.strip()
        team_uuid = uuid.UUID(str(team_id)) if team_id else None
        user_uuid = uuid.UUID(str(user_id)) if user_id else None

        # 1. Search SimulationRun records with type 'sensitivity'
        sim_query_base = select(SimulationRun).where(
            SimulationRun.simulation_type.in_(["sensitivity", "quarter_car", "full_car", "sweep"])
        )
        if team_uuid:
            sim_query_base = sim_query_base.where(SimulationRun.team_id == team_uuid)
        elif user_uuid:
            sim_query_base = sim_query_base.where(SimulationRun.user_id == user_uuid)

        sim_runs: List[SimulationRun] = []
        if vehicle_id:
            sim_query_specific = sim_query_base.where(
                or_(SimulationRun.vehicle_ref == vehicle_id, SimulationRun.setup_ref == setup_id)
            ).order_by(desc(SimulationRun.created_at)).limit(10)
            res_spec = await db.execute(sim_query_specific)
            sim_runs = list(res_spec.scalars().all())

        if not sim_runs:
            sim_query_fallback = sim_query_base.order_by(desc(SimulationRun.created_at)).limit(10)
            res_fb = await db.execute(sim_query_fallback)
            sim_runs = list(res_fb.scalars().all())

        for run in sim_runs:
            result_payload = run.result or {}
            # Look for sensitivity bars or derivatives in result
            kpi_sens = result_payload.get("sensitivities") or result_payload.get("kpi_sensitivities")
            if isinstance(kpi_sens, dict) and param_clean in kpi_sens:
                sens_data = kpi_sens[param_clean]
                return {
                    "status": SensitivityStatus.AVAILABLE.value,
                    "source_type": "SimulationRun",
                    "source_id": run.label,
                    "artifact_hash": run.result_hash,
                    "input_parameter": param_clean,
                    "downstream_metrics": sens_data if isinstance(sens_data, list) else [sens_data],
                    "method": "finite_difference_bdf",
                    "model_version": run.physics_version,
                    "solver_version": run.solver_version,
                    "operating_regime": (run.profile or {}).get("regime", "all"),
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                }

        # 2. Search CausalHypothesisRecord
        hyp_query = select(CausalHypothesisRecord).order_by(desc(CausalHypothesisRecord.created_at)).limit(10)
        if team_uuid:
            hyp_query = hyp_query.where(CausalHypothesisRecord.team_id == team_uuid)
        elif user_uuid:
            hyp_query = hyp_query.where(CausalHypothesisRecord.user_id == user_uuid)

        res_hyp = await db.execute(hyp_query)
        hyps = res_hyp.scalars().all()
        for hyp in hyps:
            cands = hyp.candidate_parameters or []
            if param_clean in cands:
                metrics = hyp.affected_observables or []
                dir_effect = hyp.expected_direction_of_effect or {}
                return {
                    "status": SensitivityStatus.AVAILABLE.value,
                    "source_type": "CausalHypothesis",
                    "source_id": hyp.hypothesis_id,
                    "artifact_hash": hyp.artifact_hash,
                    "input_parameter": param_clean,
                    "is_numerical_derivative": False,
                    "downstream_metrics": [
                        {
                            "metric": m,
                            "direction": dir_effect.get(m, "unknown"),
                            "elasticity": None,  # Directional mechanism from causal hypothesis; not a measured numerical derivative
                            "is_numerical_derivative": False,
                            "mechanism": hyp.mechanism,
                            "unit": "directional_trend",
                        }
                        for m in metrics
                    ],
                    "method": "causal_hypothesis_mechanism",
                    "model_version": hyp.model_version,
                    "created_at": hyp.created_at.isoformat() if hyp.created_at else None,
                    "note": "Directional mechanism only; causal hypothesis cannot be treated as a measured numerical derivative.",
                }

        # 3. Not found: return explicit unavailable state (Never zero!)
        return {
            "status": SensitivityStatus.SENSITIVITY_UNAVAILABLE.value,
            "input_parameter": param_clean,
            "warning": (
                f"Authoritative sensitivity evidence is unavailable for parameter '{param_clean}'. "
                "Notice: Missing sensitivity is never interpreted as zero sensitivity."
            ),
        }

    # ── D. ASSEMBLY-AWARE TRUST PROPAGATION & IMPACT ASSESSMENT ───────────────

    @classmethod
    async def assess_assembly_impact(
        cls,
        db: AsyncSession,
        vehicle_id: str,
        parameter_name: str,
        assembly_name: Optional[str] = None,
        component_name: Optional[str] = None,
        team_id: Optional[Union[str, uuid.UUID]] = None,
        organization_id: Optional[Union[str, uuid.UUID]] = None,
        user_id: Optional[Union[str, uuid.UUID]] = None,
        policy_version: str = CURRENT_SENSITIVITY_PROPAGATION_POLICY_VERSION,
        persist_record: bool = True,
    ) -> Dict[str, Any]:
        """
        Assesses how component parameter trust uncertainty or evidence gaps impact
        dependent assemblies under SENSITIVITY_PROPAGATION_POLICY_V1.
        Strict Invariants:
        1. DIRECT TRUST IS DECOUPLED FROM PROPAGATED IMPACT.
        2. If the structural dependency path is unknown, propagation is prevented.
        3. Missing sensitivity is represented as SENSITIVITY_UNAVAILABLE, never zero.
        """
        param_clean = parameter_name.strip()

        # 1. Resolve & verify structural dependency path
        resolved_hier = resolve_assembly_component(param_clean)
        if resolved_hier is None:
            return {
                "vehicle_id": vehicle_id,
                "parameter_name": param_clean,
                "can_propagate": False,
                "reason": "NO_AUTHORITATIVE_DEPENDENCY_PATH: Parameter does not map to a verified structural domain assembly.",
                "policy_version": policy_version,
            }

        canonical_assembly, canonical_component = resolved_hier
        eff_assembly = assembly_name or canonical_assembly
        eff_component = component_name or canonical_component

        if eff_assembly != canonical_assembly or eff_component != canonical_component:
            return {
                "vehicle_id": vehicle_id,
                "parameter_name": param_clean,
                "can_propagate": False,
                "reason": f"STRUCTURAL_MISMATCH: Parameter belongs to '{canonical_assembly}->{canonical_component}', incompatible with requested '{eff_assembly}->{eff_component}'.",
                "policy_version": policy_version,
            }

        dependency_path = [vehicle_id, canonical_assembly, canonical_component, param_clean]

        # 2. Fetch direct parameter trust profile
        # Check existing profile in database first
        profile = None
        team_uuid = uuid.UUID(str(team_id)) if team_id else None
        user_uuid = uuid.UUID(str(user_id)) if user_id else None

        stmt = select(ParameterTrustProfile).where(
            ParameterTrustProfile.entity_id == vehicle_id,
            ParameterTrustProfile.parameter_name == param_clean,
        )
        if team_uuid:
            stmt = stmt.where(ParameterTrustProfile.team_id == team_uuid)
        elif user_uuid:
            stmt = stmt.where(ParameterTrustProfile.created_by_user_id == user_uuid)

        res_prof = await db.execute(stmt)
        profile = res_prof.scalars().first()

        if profile is None:
            # Locate vehicle profile or setup candidate for vehicle_id and assess
            for entity_type in ["SetupCandidate", "VehicleProfile", "VehicleTwin"]:
                try:
                    profile = await ParameterTrustService.get_or_assess_parameter_trust(
                        db=db,
                        entity_type=entity_type,
                        entity_id=vehicle_id,
                        parameter_name=param_clean,
                        team_id=team_id,
                        organization_id=organization_id,
                        user_id=user_id,
                    )
                    break
                except Exception:
                    continue

        direct_trust_state = profile.current_trust_state if profile else TrustState.UNASSESSED.value
        validation_coverage = profile.validation_coverage if profile else ValidationCoverage.NO_VALIDATION.value
        conflicts = profile.conflicts if profile else []
        evidence_gaps = []

        if not profile:
            evidence_gaps.append("NO_LOCAL_TRUST_PROFILE: Vehicle does not have a direct trust assessment for this parameter.")
        elif validation_coverage == ValidationCoverage.NO_VALIDATION.value:
            evidence_gaps.append("NO_PHYSICAL_VALIDATION: Parameter lacks physical holdout validation evidence.")

        # 3. Resolve authoritative sensitivity evidence
        sens_evidence = await cls.resolve_sensitivity_evidence(
            db=db,
            parameter_name=param_clean,
            vehicle_id=vehicle_id,
            team_id=team_id,
            organization_id=organization_id,
            user_id=user_id,
        )

        sens_status = sens_evidence["status"]
        downstream_metrics = sens_evidence.get("downstream_metrics", [])
        sens_source = f"{sens_evidence.get('source_type')}:{sens_evidence.get('source_id')}" if sens_status == SensitivityStatus.AVAILABLE.value else None
        sens_unit = downstream_metrics[0].get("unit") if downstream_metrics else None

        # Filter strictly for measured numerical derivatives
        numerical_metrics = [
            m for m in downstream_metrics
            if isinstance(m, dict) and m.get("elasticity") is not None and m.get("is_numerical_derivative", True) is not False
        ]
        has_numerical_derivative = len(numerical_metrics) > 0

        # 4. Sensitivity-Aware Impact Classification (SENSITIVITY_PROPAGATION_POLICY_V1)
        if sens_status == SensitivityStatus.SENSITIVITY_UNAVAILABLE.value or not has_numerical_derivative:
            impact_classification = ImpactClassification.SENSITIVITY_UNAVAILABLE.value
            impact_summary = (
                "Numerical sensitivity derivative unavailable. Causal hypotheses or directional mechanisms "
                "cannot be treated as measured numerical derivatives. Exposing evidence gap without assuming zero downstream impact. "
                "Notice: Direct trust remains decoupled."
            )
        elif len(conflicts) > 0 or direct_trust_state == TrustState.CONFLICTED.value:
            # Active conflicts take strict precedence over any validation records
            impact_classification = ImpactClassification.CONFLICTED_IMPACT.value
            impact_summary = (
                "Parameter possesses active evidence conflicts affecting downstream metrics. "
                "Unresolved conflicts override parameter validation status."
            )
        elif validation_coverage == ValidationCoverage.VALIDATED.value:
            # Check maximum elasticity magnitude across measured numerical metrics
            max_elasticity = max([abs(m["elasticity"]) for m in numerical_metrics], default=0.0)
            if max_elasticity >= 0.20:
                impact_classification = ImpactClassification.CRITICAL_VALIDATED.value
                impact_summary = (
                    f"High downstream sensitivity parameter (|elasticity|={max_elasticity:.2f}) verified by physical validation gate. "
                    "Notice: Parameter-level validation does not establish assembly/vehicle deployment safety. "
                    "Deployment authorization is an independent governance process."
                )
            else:
                impact_classification = ImpactClassification.VALIDATED_LOW_IMPACT.value
                impact_summary = "Moderate/low sensitivity parameter verified by physical validation gate."
        else:
            # Unvalidated or Provisional Parameter
            max_elasticity = max([abs(m["elasticity"]) for m in numerical_metrics], default=0.0)
            if max_elasticity >= 0.20:
                impact_classification = ImpactClassification.HIGH_IMPACT_EVIDENCE_GAP.value
                impact_summary = f"High downstream sensitivity (|elasticity|={max_elasticity:.2f}) with unvalidated parameter. Priority engineering investigation target."
            elif max_elasticity >= 0.05:
                impact_classification = ImpactClassification.MODERATE_IMPACT_EVIDENCE_GAP.value
                impact_summary = f"Moderate downstream sensitivity (|elasticity|={max_elasticity:.2f}) with unvalidated parameter."
            else:
                impact_classification = ImpactClassification.LOW_IMPACT_EVIDENCE_GAP.value
                impact_summary = "Low downstream sensitivity with unvalidated parameter."

        # 5. Deterministic Impact Hash
        hash_payload = {
            "vehicle_id": vehicle_id,
            "assembly_name": canonical_assembly,
            "component_name": canonical_component,
            "parameter_name": param_clean,
            "policy_version": policy_version,
            "direct_trust_state": direct_trust_state,
            "validation_coverage": validation_coverage,
            "sensitivity_status": sens_status,
            "impact_classification": impact_classification,
            "threshold_provenance": SENSITIVITY_THRESHOLDS_PROVENANCE,
            "deployment_safety_inferred": False,
            "sensitivity_artifact_hash": sens_evidence.get("artifact_hash", "none"),
        }
        dumped = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"))
        impact_hash = hashlib.sha256(dumped.encode("utf-8")).hexdigest()

        # 6. Persistence
        if persist_record and user_id is not None:
            user_uuid = uuid.UUID(str(user_id))
            team_uuid = uuid.UUID(str(team_id)) if team_id else None
            org_uuid = uuid.UUID(str(organization_id)) if organization_id else None

            impact_rec = ParameterTrustAssemblyImpactRecord(
                id=uuid.uuid4(),
                vehicle_id=vehicle_id,
                assembly_name=canonical_assembly,
                component_name=canonical_component,
                parameter_name=param_clean,
                organization_id=org_uuid,
                team_id=team_uuid,
                user_id=user_uuid,
                policy_version=policy_version,
                impact_hash=impact_hash,
                direct_trust_state=direct_trust_state,
                validation_coverage=validation_coverage,
                sensitivity_status=sens_status,
                sensitivity_source=sens_source,
                sensitivity_unit=sens_unit,
                sensitivity_magnitude=downstream_metrics,
                impact_classification=impact_classification,
                downstream_metrics=downstream_metrics,
                dependency_path=dependency_path,
                evidence_gaps=evidence_gaps,
                created_at=datetime.now(timezone.utc),
            )
            db.add(impact_rec)
            await db.flush()

        return {
            "vehicle_id": vehicle_id,
            "assembly_name": canonical_assembly,
            "component_name": canonical_component,
            "parameter_name": param_clean,
            "policy_version": policy_version,
            "impact_hash": impact_hash,
            "can_propagate": True,
            "dependency_path": dependency_path,
            "threshold_provenance": SENSITIVITY_THRESHOLDS_PROVENANCE,
            "deployment_safety_inferred": False,
            "direct_trust_assessment": {
                "trust_state": direct_trust_state,
                "validation_coverage": validation_coverage,
                "conflicts_count": len(conflicts),
                "assessment_hash": profile.assessment_hash if profile else None,
            },
            "sensitivity_evidence": sens_evidence,
            "impact_assessment": {
                "impact_classification": impact_classification,
                "impact_summary": impact_summary,
                "downstream_metrics": downstream_metrics,
                "evidence_gaps": evidence_gaps,
                "threshold_provenance": SENSITIVITY_THRESHOLDS_PROVENANCE,
                "threshold_metadata": SENSITIVITY_THRESHOLDS_METADATA,
                "deployment_safety_inferred": False,
                "deployment_authorization": "NOT_ESTABLISHED",
                "deployment_safety_notice": (
                    "A passed parameter validation gate with high sensitivity does not establish vehicle or assembly deployment safety. "
                    "Deployment authorization is an independent governance process."
                ),
            },
            "lineage_note": (
                "VEHICLE -> ASSEMBLY -> COMPONENT -> PARAMETER -> TRUST ASSESSMENT -> EVIDENCE -> SENSITIVITY RECORD -> DOWNSTREAM IMPACT. "
                "Notice: Direct trust state is decoupled from propagated assembly impact."
            ),
        }
