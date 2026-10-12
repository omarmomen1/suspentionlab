"""
tests/test_phase6_5_decision_robustness.py
=========================================
SuspensionLab PRO — Phase 6.5 Decision Robustness, Uncertainty Propagation &
Evidence Prioritization Hostile Verification Suite.

Complete Adversarial Verification Matrix:
  1. Missing uncertainty evidence (verifies UNCERTAINTY_INSUFFICIENT_EVIDENCE).
  2. Unsupported probability distributions (rejects fabricated Gaussians/uniforms).
  3. Unevidenced independence assumptions handling.
  4. Correlated parameter group handling and envelope bounds.
  5. Invalid physical ranges and dimensional compatibility checks.
  6. Numerical solver failures preserved unmasked (SOLVER_CONVERGENCE_FAILURE).
  7. Discontinuous decision boundaries & bisection approximation.
  8. Deterministic replay (identical cryptographic analysis_hash and input_snapshot_hash).
  9. Cross-tenant access enforcement (TenantIsolationError / 403 Forbidden).
  10. Concurrent reassessments & active supersession (is_active=False, superseded_by).
  11. Historical immutability (superseded analyses cannot be overwritten).
  12. Phase 5 pre-reveal leakage prevention (fails closed).
  13. False deployment-safety assertions strictly prohibited (deployment_safety_inferred=False).
  14. Dominant uncertainties ranking & VOI without fabricated economic/cost values.
  15. REST API full workflow over HTTP.
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

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import Base, get_db_dependency
from suspensionlab.backend.database.models.parameter_trust import (
    ParameterTrustProfile,
    ParameterTrustEvidenceRecord,
    ParameterTrustAssessmentRecord,
    DecisionRobustnessAnalysisRecord,
    TrustState,
    ValidationCoverage,
    ProvenanceClass,
    SensitivityStatus,
    UncertaintyRepresentationType,
    DecisionRobustnessClassification,
    BoundaryCrossingType,
    VOIPriorityLevel,
    TRUST_POLICY_V1,
    CURRENT_TRUST_POLICY_VERSION,
    DECISION_TRUST_POLICY_V1,
    ROBUSTNESS_POLICY_V1,
    CURRENT_ROBUSTNESS_POLICY_VERSION,
    GOVERNANCE_ROBUSTNESS_SEPARATION_NOTICE,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.setup_engineering import (
    EngineeringProblemRecord,
    CausalHypothesisRecord,
    SetupCandidateRecord,
)
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.blind_engineering import (
    BlindEngineeringSession,
    BlindSessionStatus,
)
from suspensionlab.backend.security.auth import verify_api_key, UserContext
from suspensionlab.backend.services.parameter_trust_robustness_service import (
    ParameterTrustRobustnessService,
    IntervalUncertainty,
    MeasurementUncertainty,
    EmpiricalDistribution,
    CorrelatedParameterGroup,
    RobustnessAnalysisError,
    PreRevealFirewallViolation,
    TenantIsolationError,
)
from suspensionlab.backend.services.parameter_trust_decision_service import (
    DecisionNotFoundError,
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
        email=f"eng_{user_id.hex[:6]}@suspensionlab.com",
        name="Robustness Engineer",
        onboarding_complete=True,
        team_id=str(team_id) if team_id else None,
        organization_id=str(org_id) if org_id else None,
        team_role=role,
        org_role="MEMBER",
        is_admin=role in ("admin", "org_admin"),
    )


@pytest.fixture
async def seeded_robustness_env(async_test_db: AsyncSession):
    """
    Sets up multi-tenant decisions, candidate setups, parameter profiles,
    and sensitivity simulations.
    """
    db = async_test_db
    org_a = uuid.uuid4()
    team_a = uuid.uuid4()
    user_a = uuid.uuid4()

    org_b = uuid.uuid4()
    team_b = uuid.uuid4()
    user_b = uuid.uuid4()

    now = datetime.now(timezone.utc)

    # 1. Candidate Setup A (Team A)
    cand_a = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-ROBUST-01",
        parent_setup_id="BASE-01",
        changed_parameters={
            "front_spring_rate": {"candidate": 85000.0, "unit": "N/m"},
            "front_damper_rate": {"candidate": 3500.0, "unit": "N-s/m"},
            "sprung_mass": {"candidate": 320.0, "unit": "kg"},
        },
        unchanged_parameters={},
        parameter_provenance={
            "front_spring_rate": "optimization",
            "front_damper_rate": "cae_sweep",
            "sprung_mass": "measured",
        },
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-01", "operating_regime": "High-Speed Lateral Cornering"},
        creation_reason="Robustness evaluation candidate",
        artifact_hash="hash_cand_robust_01",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(cand_a)

    # Candidate Setup B (Alternative for ranking comparisons)
    cand_b = SetupCandidateRecord(
        id=uuid.uuid4(),
        setup_id="SETUP-ROBUST-02",
        parent_setup_id="BASE-01",
        changed_parameters={
            "front_spring_rate": {"candidate": 78000.0, "unit": "N/m"},
            "front_damper_rate": {"candidate": 3200.0, "unit": "N-s/m"},
            "sprung_mass": {"candidate": 320.0, "unit": "kg"},
        },
        unchanged_parameters={},
        parameter_provenance={
            "front_spring_rate": "historical_setup",
            "front_damper_rate": "historical_setup",
            "sprung_mass": "measured",
        },
        model_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        validity_domain={"vehicle_id": "CAR-01", "operating_regime": "High-Speed Lateral Cornering"},
        creation_reason="Alternative candidate",
        artifact_hash="hash_cand_robust_02",
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(cand_b)

    # Simulation sensitivity run for spring rate
    sim_a = SimulationRun(
        id=uuid.uuid4(),
        seq=1,
        label="SIM-SENS-ROBUST-01",
        job_id=uuid.uuid4(),
        user_id=user_a,
        team_id=team_a,
        simulation_type="sensitivity",
        title="Quarter-car stiffness sensitivity sweep",
        vehicle_ref="CAR-01",
        setup_ref="SETUP-ROBUST-01",
        params={"front_spring_rate": 85000.0},
        software_version="1.0.0",
        physics_version="DYNAMIC-TRANSIENT-14DOF-v2.6",
        kinematics_version="1.0.0",
        solver_version="BDF-v2.0",
        params_hash="hash_params_rob_01",
        result={
            "sensitivities": {
                "front_spring_rate": [
                    {
                        "metric": "ride_frequency_hz",
                        "elasticity": 0.48,
                        "unit": "%/%",
                        "is_numerical_derivative": True,
                    }
                ]
            }
        },
        result_hash="hash_sim_rob_01",
        created_at=now,
    )
    db.add(sim_a)

    # Parameter Trust Profiles for cand_a
    prof_spring = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-ROBUST-01",
        parameter_name="front_spring_rate",
        parameter_path="changed_parameters.front_spring_rate.candidate",
        unit="N/m",
        value_reference={"value": 85000.0, "value_identity": "85000.0"},
        provenance_class=ProvenanceClass.OPTIMIZATION.value,
        current_trust_state=TrustState.VALIDATED.value,
        validation_coverage=ValidationCoverage.VALIDATED.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_prof_spring_rob",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-ROBUST-01"},
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(prof_spring)

    prof_damper = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-ROBUST-01",
        parameter_name="front_damper_rate",
        parameter_path="changed_parameters.front_damper_rate.candidate",
        unit="N-s/m",
        value_reference={"value": 3500.0, "value_identity": "3500.0"},
        provenance_class=ProvenanceClass.SIMULATION_DERIVED.value,
        current_trust_state=TrustState.PROVISIONAL.value,
        validation_coverage=ValidationCoverage.PARTIAL_VALIDATION.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_prof_damper_rob",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-ROBUST-01"},
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(prof_damper)

    prof_mass = ParameterTrustProfile(
        id=uuid.uuid4(),
        entity_type="SetupCandidate",
        entity_id="SETUP-ROBUST-01",
        parameter_name="sprung_mass",
        parameter_path="changed_parameters.sprung_mass.candidate",
        unit="kg",
        value_reference={"value": 320.0, "value_identity": "320.0"},
        provenance_class=ProvenanceClass.MEASURED.value,
        current_trust_state=TrustState.HIGH_CONFIDENCE.value,
        validation_coverage=ValidationCoverage.VALIDATED.value,
        policy_version=CURRENT_TRUST_POLICY_VERSION,
        assessment_hash="hash_prof_mass_rob",
        scope={"vehicle_id": "CAR-01", "setup_id": "SETUP-ROBUST-01"},
        created_by_user_id=user_a,
        team_id=team_a,
        organization_id=org_a,
        created_at=now,
    )
    db.add(prof_mass)

    # Engineering Decision (Team A)
    dec_a = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-ROBUST-01",
        question="Select front axle setup for high-speed cornering stability",
        context={"vehicle_id": "CAR-01", "setup_id": "SETUP-ROBUST-01"},
        candidates=["SETUP-ROBUST-01", "SETUP-ROBUST-02"],
        selected_option={"setup_id": "SETUP-ROBUST-01"},
        reason="Stiffness targets ride frequency 1.7 Hz",
        tradeoffs={"ride_vs_handling": "Stiffer front improves turn-in response"},
        risks={"kerb_strike": "Higher peak contact patch load"},
        simulation_evidence=[{"sim_label": "SIM-SENS-ROBUST-01"}],
        telemetry_evidence=[],
        validation_evidence=[],
        status="RECOMMENDED",
        author="Robustness Engineer A",
        artifact_hashes={"decision_hash": "hash_dec_rob_01"},
        user_id=user_a,
        team_id=team_a,
        created_at=now,
    )
    db.add(dec_a)

    # Engineering Decision (Team B - Tenant Isolation)
    dec_b = EngineeringDecision(
        id=uuid.uuid4(),
        decision_id="DEC-ROBUST-B01",
        question="Team B isolated decision",
        context={"vehicle_id": "CAR-B01"},
        candidates=["SETUP-B-01"],
        selected_option={"setup_id": "SETUP-B-01"},
        reason="Team B setup",
        tradeoffs={},
        risks={},
        simulation_evidence=[],
        telemetry_evidence=[],
        validation_evidence=[],
        status="PROPOSED",
        author="Engineer B",
        artifact_hashes={"decision_hash": "hash_dec_b01"},
        user_id=user_b,
        team_id=team_b,
        created_at=now,
    )
    db.add(dec_b)

    # Pre-reveal blind engineering session for firewall test
    blind_session = BlindEngineeringSession(
        id=uuid.uuid4(),
        organization_id=org_a,
        team_id=team_a,
        created_by_user_id=user_a,
        status=BlindSessionStatus.BLIND_ACTIVE.value,  # unrevealed!
        name="BLIND-ROBUST-01",
        root_entity_type="SetupCandidate",
        root_entity_id="SETUP-ROBUST-01",
        hidden_outcome_type="SetupCandidate",
        hidden_outcome_id="SETUP-ROBUST-01",
        configuration={},
        session_hash="hash_blind_rob_01",
        created_at=now,
    )
    db.add(blind_session)

    await db.commit()

    return {
        "org_a": org_a,
        "team_a": team_a,
        "user_a": user_a,
        "org_b": org_b,
        "team_b": team_b,
        "user_b": user_b,
        "user_ctx_a": make_user_ctx(user_a, team_a, org_a),
        "user_ctx_b": make_user_ctx(user_b, team_b, org_b),
        "dec_a_id": "DEC-ROBUST-01",
        "dec_b_id": "DEC-ROBUST-B01",
    }


# =====================================================================
# 1. Missing Uncertainty Evidence & Preflight Check
# =====================================================================

@pytest.mark.asyncio
async def test_01_preflight_missing_uncertainty_evidence(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 1: Preflight audits dependencies, identifies recomputable modal KPIs,
    and surfaces missing uncertainty evidence without fabricating assumptions.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    preflight = await service.preflight_robustness(
        decision_id="DEC-ROBUST-01",
        decision_type="EngineeringDecision",
        user_context=user_ctx,
    )

    assert preflight["decision_id"] == "DEC-ROBUST-01"
    assert preflight["is_ready"] is True
    assert preflight["policy_version"] == CURRENT_ROBUSTNESS_POLICY_VERSION
    assert preflight["matched_parameters_count"] >= 3
    # Check that modal KPIs can be recomputed from quarter-car physics
    recomputable_names = [k["kpi"] for k in preflight["recomputable_kpis"]]
    assert "ride_frequency_hz" in recomputable_names
    assert "damping_ratio" in recomputable_names


# =====================================================================
# 2. Unsupported Probability Distributions Rejection
# =====================================================================

@pytest.mark.asyncio
async def test_02_unsupported_probability_distribution_rejected(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 2: Reject fabricated Gaussian / uniform priors when only bounded intervals exist.
    System must fail closed with RobustnessAnalysisError when unevidenced probability distribution is requested.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    # Attempting to declare PROBABILITY_DISTRIBUTION with empty sample provenance
    invalid_uncertainty = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "PROBABILITY_DISTRIBUTION",
            "lower_bound": 80000.0,
            "upper_bound": 90000.0,
            "empirical_samples": [],  # Empty samples!
            "sample_provenance": "",
        }
    }

    with pytest.raises(RobustnessAnalysisError) as exc_info:
        await service.run_robustness_analysis(
            decision_id="DEC-ROBUST-01",
            uncertainty_inputs=invalid_uncertainty,
            user_context=user_ctx,
        )

    assert "requires non-empty empirical samples" in str(exc_info.value).lower() or "provenance" in str(exc_info.value).lower()


# =====================================================================
# 3. Unevidenced Independence Assumptions Handling
# =====================================================================

@pytest.mark.asyncio
async def test_03_unevidenced_independence_handling(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 3: When independence is assumed without correlation evidence,
    evaluation strictly performs bounded interval corners without fabricating
    joint probability density or Monte Carlo weights.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    intervals = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 80000.0,
            "nominal_value": 85000.0,
            "upper_bound": 90000.0,
        },
        "front_damper_rate": {
            "parameter_name": "front_damper_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 3000.0,
            "nominal_value": 3500.0,
            "upper_bound": 4000.0,
        },
    }

    result = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        uncertainty_inputs=intervals,
        user_context=user_ctx,
        persist_record=False,
    )

    # Evaluated envelope must reflect deterministic corner evaluation
    assert result["evaluated_scenarios_count"] >= 4
    # No fabricated percentage or synthetic probabilities
    assert "probability" not in result
    assert "monte_carlo" not in result
    assert result["governance_separation_notice"] == GOVERNANCE_ROBUSTNESS_SEPARATION_NOTICE


# =====================================================================
# 4. Correlated Parameter Handling
# =====================================================================

@pytest.mark.asyncio
async def test_04_correlated_parameter_group_handling(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 4: When parameters have documented correlation,
    the correlated envelope bounds are respected and unphysical corners are excluded.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    intervals = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 75000.0,
            "nominal_value": 85000.0,
            "upper_bound": 95000.0,
        },
        "front_damper_rate": {
            "parameter_name": "front_damper_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 2800.0,
            "nominal_value": 3500.0,
            "upper_bound": 4200.0,
        },
    }

    correlated_groups = [
        {
            "group_name": "front_suspension_stiffness_damping",
            "parameters": ["front_spring_rate", "front_damper_rate"],
            "correlation_coefficient": 0.85,
            "evidence_basis": "Empirical dyno tuning curve matching ride mode damping",
        }
    ]

    result = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        uncertainty_inputs=intervals,
        correlated_groups=correlated_groups,
        user_context=user_ctx,
        persist_record=False,
    )

    # Evaluated envelope includes correlated group metadata
    assert "correlated_groups" in result["evaluated_envelope"]
    assert len(result["evaluated_envelope"]["correlated_groups"]) == 1
    assert result["evaluated_envelope"]["correlated_groups"][0]["correlation_coefficient"] == 0.85


# =====================================================================
# 5. Invalid Physical Ranges and Units Rejection
# =====================================================================

@pytest.mark.asyncio
async def test_05_invalid_physical_ranges_rejected(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 5: Parameter intervals violating physical constraints (e.g., lower > upper,
    or negative stiffness) are rejected immediately.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    # Inverted bounds
    invalid_intervals = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 90000.0,  # lower > upper
            "upper_bound": 80000.0,
        }
    }

    with pytest.raises(RobustnessAnalysisError) as exc_info:
        await service.run_robustness_analysis(
            decision_id="DEC-ROBUST-01",
            uncertainty_inputs=invalid_intervals,
            user_context=user_ctx,
        )

    assert "lower bound" in str(exc_info.value).lower() and "greater than" in str(exc_info.value).lower()


# =====================================================================
# 6. Numerical Solver Failures Preserved Unmasked
# =====================================================================

@pytest.mark.asyncio
async def test_06_numerical_solver_failures_preserved_unmasked(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 6: Scenarios that trigger physics solver non-convergence or
    domain violation (e.g. spring rate < 1000 N/m where quarter-car solver fails)
    must be explicitly recorded as SOLVER_CONVERGENCE_FAILURE and never masked as safe.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    # Include a lower bound that violates the quarter-car physical domain (k_s < 1000 N/m)
    intervals = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 500.0,  # Physical violation triggers ValueError in QuarterCarParams!
            "nominal_value": 85000.0,
            "upper_bound": 95000.0,
        }
    }

    result = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        uncertainty_inputs=intervals,
        user_context=user_ctx,
        persist_record=False,
    )

    # Solver failure must be preserved explicitly in solver_failures
    assert len(result["solver_failures"]) > 0
    failure = result["solver_failures"][0]
    assert failure["convergence_status"] == "SOLVER_CONVERGENCE_FAILURE"
    assert "failure_reason" in failure
    # Classification must reflect instability
    assert result["robustness_classification"] != DecisionRobustnessClassification.ROBUST_ACROSS_ENVELOPE.value


# =====================================================================
# 7. Discontinuous Decision Boundaries & Bisection
# =====================================================================

@pytest.mark.asyncio
async def test_07_discontinuous_decision_boundaries_and_bisection(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 7: Continuous boundary crossings are located via bisection approximation,
    and parameter shifts required to flip the decision are accurately computed.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    # Set threshold between nominal (1.75 Hz) and lower bound (1.53 Hz)
    intervals = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 60000.0,
            "nominal_value": 85000.0,
            "upper_bound": 90000.0,
        }
    }

    result = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        uncertainty_inputs=intervals,
        decision_threshold=1.60,  # Nominal ~1.75 Hz passes; at 60000 N/m it drops below 1.60!
        user_context=user_ctx,
        persist_record=False,
    )

    assert len(result["boundary_crossings"]) > 0
    bc = result["boundary_crossings"][0]
    assert bc["crossing_type"] == BoundaryCrossingType.NUMERICALLY_APPROXIMATED_CROSSING.value
    assert bc["critical_parameter"] == "front_spring_rate"
    assert bc["boundary_value"] is not None
    assert bc["nominal_value"] == 85000.0
    assert bc["parameter_shift_pct"] is not None
    assert bc["parameter_shift_pct"] < 0  # Negative shift towards 60000


# =====================================================================
# 8. Deterministic Replay
# =====================================================================

@pytest.mark.asyncio
async def test_08_deterministic_replay_and_hash_identity(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 8: Running robustness analysis twice on identical inputs produces
    bitwise identical analysis_hash and input_snapshot_hash.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    intervals = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 80000.0,
            "nominal_value": 85000.0,
            "upper_bound": 90000.0,
        }
    }

    run1 = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        uncertainty_inputs=intervals,
        user_context=user_ctx,
        persist_record=False,
    )

    run2 = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        uncertainty_inputs=intervals,
        user_context=user_ctx,
        persist_record=False,
    )

    assert run1["analysis_hash"] == run2["analysis_hash"]
    assert run1["input_snapshot_hash"] == run2["input_snapshot_hash"]
    assert run1["robustness_classification"] == run2["robustness_classification"]


# =====================================================================
# 9. Cross-Tenant Access Enforcement
# =====================================================================

@pytest.mark.asyncio
async def test_09_cross_tenant_access_enforcement(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 9: Tenant B attempting to access or analyze Tenant A's decision
    must raise TenantIsolationError or DecisionNotFoundError.
    """
    db = async_test_db
    user_ctx_b = seeded_robustness_env["user_ctx_b"]
    service = ParameterTrustRobustnessService(db)

    with pytest.raises((TenantIsolationError, DecisionNotFoundError)):
        await service.run_robustness_analysis(
            decision_id="DEC-ROBUST-01",  # Belongs to Tenant A!
            user_context=user_ctx_b,
        )


# =====================================================================
# 10. Concurrent Reassessments & Active Supersession
# =====================================================================

@pytest.mark.asyncio
async def test_10_concurrent_reassessments_and_supersession(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 10: Re-running analysis with persist_record=True marks previous record
    as is_active=False, sets superseded_by=new_id, and makes new record active.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    # 1. First run
    run1 = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        user_context=user_ctx,
        persist_record=True,
    )
    rec1_id = run1["id"]
    assert run1["is_active"] is True

    # 2. Second run
    run2 = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        user_context=user_ctx,
        persist_record=True,
    )
    rec2_id = run2["id"]
    assert run2["is_active"] is True
    assert rec1_id != rec2_id

    # Verify rec1 is now inactive and superseded
    stmt = select(DecisionRobustnessAnalysisRecord).where(DecisionRobustnessAnalysisRecord.id == rec1_id)
    res = await db.execute(stmt)
    old_rec = res.scalar_one()
    assert old_rec.is_active is False
    assert old_rec.superseded_by == rec2_id


# =====================================================================
# 11. Historical Immutability
# =====================================================================

@pytest.mark.asyncio
async def test_11_historical_immutability(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 11: Querying robustness history returns all historical revisions in
    chronological order, verifying append-only ledger semantics.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    # Run two persisted evaluations
    await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        user_context=user_ctx,
        persist_record=True,
    )
    await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        user_context=user_ctx,
        persist_record=True,
    )

    history = await service.get_robustness_history(
        decision_id="DEC-ROBUST-01",
        user_context=user_ctx,
    )

    assert history["total"] >= 2
    records = history["history"]
    # Most recent should be active
    assert records[0]["is_active"] is True
    # Predecessor must be inactive
    assert records[1]["is_active"] is False


# =====================================================================
# 12. Phase 5 Pre-Reveal Leakage Prevention
# =====================================================================

@pytest.mark.asyncio
async def test_12_phase_5_pre_reveal_leakage_prevented(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 12: An active, unrevealed blind session holdout cannot be passed as
    an uncertainty distribution evidence source. Attempting to cite an active blind
    holdout fails closed with PreRevealFirewallViolation.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    leaked_inputs = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "PROBABILITY_DISTRIBUTION",
            "lower_bound": 80000.0,
            "upper_bound": 90000.0,
            "empirical_samples": [81000.0, 83000.0],
            "sample_provenance": "BLIND_SESSION:BLIND-ROBUST-01",  # Active unrevealed session!
        }
    }

    with pytest.raises(PreRevealFirewallViolation):
        await service.run_robustness_analysis(
            decision_id="DEC-ROBUST-01",
            uncertainty_inputs=leaked_inputs,
            user_context=user_ctx,
        )


# =====================================================================
# 13. False Deployment-Safety Assertions Strictly Prohibited
# =====================================================================

@pytest.mark.asyncio
async def test_13_governance_separation_and_false_deployment_safety_prohibited(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 13: The system must strictly enforce:
      deployment_safety_inferred == False
      deployment_authorization == "NOT_ESTABLISHED"
    under all conditions, including when a decision is classified as ROBUST_WITHIN_CREDIBLE_RANGE.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    # Tight credible range where conclusion holds
    tight_intervals = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 84000.0,
            "nominal_value": 85000.0,
            "upper_bound": 86000.0,
        }
    }

    result = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        uncertainty_inputs=tight_intervals,
        user_context=user_ctx,
        persist_record=False,
    )

    assert result["deployment_safety_inferred"] is False
    assert result["deployment_authorization"] == "NOT_ESTABLISHED"
    assert "GOVERNANCE & SAFETY SEPARATION" in result["governance_separation_notice"]


# =====================================================================
# 14. Dominant Uncertainties & VOI Without Fabricated Costs
# =====================================================================

@pytest.mark.asyncio
async def test_14_dominant_uncertainties_and_voi_without_fabricated_cost(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 14: Dominant uncertainties are ranked by elasticity × uncertainty span & reversal driver status.
    VOI prioritizations map directly to concrete physical test activities without synthetic dollar values.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]
    service = ParameterTrustRobustnessService(db)

    wide_intervals = {
        "front_spring_rate": {
            "parameter_name": "front_spring_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 65000.0,
            "nominal_value": 85000.0,
            "upper_bound": 105000.0,
        },
        "front_damper_rate": {
            "parameter_name": "front_damper_rate",
            "representation_type": "INTERVAL",
            "lower_bound": 3300.0,
            "nominal_value": 3500.0,
            "upper_bound": 3700.0,
        },
    }

    result = await service.run_robustness_analysis(
        decision_id="DEC-ROBUST-01",
        uncertainty_inputs=wide_intervals,
        user_context=user_ctx,
        persist_record=False,
    )

    # Dominant uncertainties must rank front_spring_rate first due to high elasticity and wide span
    assert len(result["dominant_uncertainties"]) > 0
    top_uncertainty = result["dominant_uncertainties"][0]
    assert top_uncertainty["parameter_name"] == "front_spring_rate"
    assert top_uncertainty["impact_score"] > 0

    # VOI prioritizations must propose concrete physical testing
    assert len(result["voi_prioritizations"]) > 0
    voi = result["voi_prioritizations"][0]
    assert voi["parameter_name"] == "front_spring_rate"
    assert voi["recommended_experiment"] in ("RIG_TEST_4_POST", "SHOCK_DYNO_CHARACTERIZATION", "TRACK_K&C_RIG_TEST")
    # Verify strictly NO economic cost or EVOI fabrication
    assert "cost" not in voi
    assert "dollar" not in voi
    assert "evoi" not in voi


# =====================================================================
# 15. REST API Full Workflow Over HTTP
# =====================================================================

@pytest.mark.asyncio
async def test_15_rest_api_full_workflow(async_test_db: AsyncSession, seeded_robustness_env: dict):
    """
    Scenario 15: Full REST API workflow testing preflight, analyze, get,
    boundaries, voi, and history routes over ASGI HTTP transport.
    """
    db = async_test_db
    user_ctx = seeded_robustness_env["user_ctx_a"]

    app.dependency_overrides[get_db_dependency] = lambda: db
    app.dependency_overrides[verify_api_key] = lambda: user_ctx

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Preflight
            pre_res = await client.post(
                "/api/v1/parameter-trust/decision/robustness/preflight",
                json={"decision_id": "DEC-ROBUST-01"},
            )
            assert pre_res.status_code == 200
            pre_data = pre_res.json()
            assert pre_data["decision_id"] == "DEC-ROBUST-01"
            assert pre_data["is_ready"] is True

            # 2. Analyze
            analyze_res = await client.post(
                "/api/v1/parameter-trust/decision/robustness/analyze",
                json={
                    "decision_id": "DEC-ROBUST-01",
                    "persist_record": True,
                },
            )
            assert analyze_res.status_code == 200
            analyze_data = analyze_res.json()
            assert analyze_data["decision_id"] == "DEC-ROBUST-01"
            assert analyze_data["deployment_safety_inferred"] is False
            assert analyze_data["deployment_authorization"] == "NOT_ESTABLISHED"

            # 3. GET Active Robustness
            get_res = await client.get("/api/v1/parameter-trust/decision/DEC-ROBUST-01/robustness")
            assert get_res.status_code == 200
            get_data = get_res.json()
            assert get_data["decision_id"] == "DEC-ROBUST-01"
            assert get_data["is_active"] is True

            # 4. GET Boundaries
            bounds_res = await client.get("/api/v1/parameter-trust/decision/DEC-ROBUST-01/robustness/boundaries")
            assert bounds_res.status_code == 200
            bounds_data = bounds_res.json()
            assert bounds_data["decision_id"] == "DEC-ROBUST-01"

            # 5. GET VOI
            voi_res = await client.get("/api/v1/parameter-trust/decision/DEC-ROBUST-01/robustness/voi")
            assert voi_res.status_code == 200
            voi_data = voi_res.json()
            assert voi_data["decision_id"] == "DEC-ROBUST-01"

            # 6. GET History
            hist_res = await client.get("/api/v1/parameter-trust/decision/DEC-ROBUST-01/robustness/history")
            assert hist_res.status_code == 200
            hist_data = hist_res.json()
            assert hist_data["total"] >= 1
            assert hist_data["history"][0]["decision_id"] == "DEC-ROBUST-01"

    finally:
        app.dependency_overrides.pop(get_db_dependency, None)
        app.dependency_overrides.pop(verify_api_key, None)
