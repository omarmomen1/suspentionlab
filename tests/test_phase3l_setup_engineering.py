"""
tests/test_phase3l_setup_engineering.py
========================================
SuspensionLab PRO — Phase 3L Setup Engineering & Causal Experimentation Test Suite.

Verifies:
1. Engineering Problem Definition & 4-way Epistemic Demarcation.
2. Parameter Eligibility Gate (IDENTIFIABLE, PARTIALLY_IDENTIFIABLE, UNIDENTIFIABLE, NUMERICALLY_FAILED).
3. Causal Hypothesis Formulation with Statistical Grounding (no generic confidence scores).
4. Controlled Experiment Design with Isolated Treatment Interventions.
5. Setup Candidate Generation with Real Setup Objects and Provenance Lineage.
6. Genuine 14-DOF Production Simulation Execution (no mock solvers).
7. Setup Comparison with Absolute/Pct Deltas, Residuals, and 95% Confidence Intervals.
8. Multi-Objective Evaluation & Pareto Frontier Analysis with Strict Constraints.
9. Sealed Blind Holdout Validation with Zero Data Leakage (D_fit ∩ D_holdout = ∅).
10. Engineering Decision Formulation & Non-Repudiable HMAC Human Approval.
11. Immutable Track-Test Prediction Generation.
12. Post-Track Telemetry Reconciliation (Zero retroactive alteration of predictions).
13. 14 Comprehensive Failure Modes UX Diagnostics (All 5 mandatory sections).
14. The 12 Hostile Invariants Mandated in Phase 3L.
15. FastAPI REST Endpoints Integration.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.setup_engineering import (
    EngineeringProblemRecord,
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
    PostTrackReconciliationRecord,
)
from suspensionlab.backend.database.models.engineering_decision import EngineeringDecision
from suspensionlab.backend.database.models.decision_loop import ApprovalRecord
from suspensionlab.backend.services.phase3l_setup_engineering_service import (
    Phase3LSetupEngineeringService,
    UnidentifiableParameterError,
    UncertaintyConstraintMissingError,
    NumericallyFailedParameterError,
    PhysicalBoundsViolationError,
    ValidityDomainViolationError,
    HoldoutLeakageError,
    ImmutablePredictionError,
    StaleModelError,
    SolverExecutionError,
    NoFeasibleSetupError,
)


@pytest.fixture
async def async_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── TEST 1: COMPLETE END-TO-END WORKFLOW INTEGRATION ───────────────────────────

@pytest.mark.asyncio
async def test_phase3l_complete_setup_engineering_workflow(async_test_db: AsyncSession):
    """
    Executes the complete Phase 3L Setup Engineering workflow:
    Problem -> Parameter Gate -> Hypothesis -> Experiment -> Setup -> Real Simulation ->
    Comparison -> Multi-Objective -> Sealed Blind Validation -> Decision -> Approval ->
    Track Prediction -> Post-Track Reconciliation -> 14-Step Lineage.
    """
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    approver_name = "Elena Rostova"
    approver_role = "Chief Race Engineer & Technical Director"

    bundle = await Phase3LSetupEngineeringService.execute_full_workflow(
        db=async_test_db,
        user_id=user_id,
        team_id=team_id,
        approver_name=approver_name,
        approver_role=approver_role,
    )

    # 1. Top-level status check
    assert bundle["status"] == "SETUP_ENGINEERING_WORKFLOW_READY"
    assert "execution_timestamp_iso" in bundle

    # 2. Stage 1: Problem Definition
    prob = bundle["problem"]
    assert prob["problem_id"] == "PROB-P3L-01"
    assert "Turn 8 exit" in prob["observable"]
    epistemic = prob["epistemic_classification"]
    assert "OBSERVED_FACT" in epistemic
    assert "HYPOTHESIS" in epistemic
    assert "MODEL_INFERENCE" in epistemic
    assert "ENGINEERING_DECISION" in epistemic
    assert len(epistemic["OBSERVED_FACT"]) >= 3

    # 3. Stage 2: Parameter Eligibility Gate
    gate = bundle["parameter_gate"]
    assert gate["gate_passed"] is True
    assert "anti_roll_bar_front" in gate["eligible_parameters"]

    # 4. Stage 3: Causal Hypothesis
    hypo = bundle["hypothesis"]
    assert hypo["hypothesis_id"] == "HYP-P3L-01"
    assert "load transfer" in hypo["mechanism"].lower()
    assert len(hypo["supporting_evidence"]) >= 3
    assert len(hypo["contradicting_evidence"]) >= 3
    # Verify statistical confidence structure
    conf = hypo["confidence_uncertainty"]
    assert "parameter_standard_errors" in conf
    assert "t_statistics" in conf
    assert "bootstrap_ci_95" in conf

    # 5. Stage 4: Controlled Experiment
    exp = bundle["experiment"]
    assert exp["experiment_id"] == "EXP-P3L-01"
    assert exp["isolation_verified"] is True
    assert "k_arb_front_nm" in exp["treatment_variables"]
    assert "mass_kg" in exp["control_variables"] or "vehicle_mass_kg" in exp["control_variables"]

    # 6. Stage 5: Real Setup Candidate
    setup = bundle["setup"]
    assert setup["setup_id"] == "SETUP-P3L-CAND-01"
    assert setup["parent_setup_id"] == "SETUP-GTI-BASE"
    assert "k_arb_front_nm" in setup["changed_parameters"]
    assert setup["changed_parameters"]["k_arb_front_nm"]["delta_pct"] == pytest.approx(32.0, abs=0.5)

    # 7. Stage 6: Real Simulation Execution
    sim = bundle["simulation"]
    assert sim["solver_status"] == "SUCCESS"
    assert sim["solver_version"] == "ODE-14DOF-v3.11-RK45"
    assert sim["runtime_s"] > 0.0
    assert len(sim["input_hash"]) == 64
    assert len(sim["output_hash"]) == 64
    assert sim["metrics"]["peak_roll_angle_deg"] > 0.0

    # 8. Stage 7: Setup Comparison
    comp = bundle["comparison"]
    assert comp["overall_beneficial"] is True
    roll_delta = next(d for d in comp["deltas"] if d["metric"] == "peak_roll_angle_deg")
    assert roll_delta["direction_desired"] == "LOWER"
    assert len(roll_delta["ci_95"]) == 2

    # 9. Stage 8: Multi-Objective Evaluation
    mo = bundle["multi_objective"]
    assert mo["feasible_count"] >= 1
    assert mo["infeasible_count"] >= 1
    assert mo["optimal_setup"]["setup_id"] == "SETUP-P3L-CAND-01"

    # 10. Stage 9: Sealed Blind Holdout Validation
    val = bundle["validation"]
    assert val["is_zero_leakage"] is True
    assert val["gate_verdict"] == "PASSED"
    assert val["parameters_frozen"] is True
    assert val["holdout_r2"] >= 0.70

    # 11. Stage 10: Engineering Decision & Approval
    dec = bundle["decision"]
    assert dec["decision_id"] == "DEC-P3L-01"
    assert dec["outcome"] == "ACCEPT"
    assert dec["status"] == "VALIDATED"  # Pre-approval status

    appr = bundle["approval"]
    assert appr["status"] == "APPROVED"
    assert appr["approver_name"] == approver_name
    assert len(appr["approval_signature"]) == 64

    # 12. Stage 11: Track-Test Prediction
    pred = bundle["prediction"]
    assert pred["prediction_id"] == "PRED-P3L-01"
    assert pred["is_immutable"] is True
    assert "peak_lateral_accel_g" in pred["expected_delta"]
    assert len(pred["failure_conditions"]) >= 3

    # 13. Stage 12: Post-Track Reconciliation
    recon = bundle["reconciliation"]
    assert recon["reconciliation_id"] == "RECON-P3L-01"
    assert recon["directional_agreement"] is True
    assert recon["reconciliation_status"] == "RECONCILED_CONFIRMED"
    assert recon["original_prediction_hash_verified"] is True

    # 14. Stage 13: 14-Step Lineage
    lin = bundle["lineage"]
    assert len(lin) == 14
    assert lin[0]["stage"] == "RECONCILIATION"
    assert lin[-1]["stage"] == "DATASET_PROVENANCE"


# ── TEST 2: PARAMETER ELIGIBILITY GATE BEHAVIORS ──────────────────────────────

def test_parameter_eligibility_gate_classifications():
    """
    Section 2: Verifies that:
    - IDENTIFIABLE parameters are eligible
    - PARTIALLY_IDENTIFIABLE without uncertainty are refused
    - PARTIALLY_IDENTIFIABLE with explicit uncertainty constraints are permitted
    - UNIDENTIFIABLE parameters are strictly prohibited
    - NUMERICALLY_FAILED parameters are strictly prohibited
    """
    # Case A: Identifiable parameter
    res_ident = Phase3LSetupEngineeringService.audit_parameter_eligibility(["spring_rate_front", "damper_bump_front"])
    assert res_ident["gate_passed"] is True
    assert len(res_ident["eligible_parameters"]) == 2

    # Case B: Partially identifiable WITHOUT uncertainty constraint
    res_part_no = Phase3LSetupEngineeringService.audit_parameter_eligibility(["anti_roll_bar_rear"])
    assert res_part_no["gate_passed"] is False
    assert "anti_roll_bar_rear" in res_part_no["requires_uncertainty"]

    # Case C: Partially identifiable WITH explicit uncertainty constraint
    res_part_yes = Phase3LSetupEngineeringService.audit_parameter_eligibility(
        candidate_parameters=["anti_roll_bar_rear"],
        uncertainty_handling={"anti_roll_bar_rear": {"has_explicit_constraint": True, "sigma_bounds": 1.5}},
    )
    assert res_part_yes["gate_passed"] is True
    assert "anti_roll_bar_rear" in res_part_yes["eligible_parameters"]

    # Case D: Unidentifiable parameter refusal
    res_unident = Phase3LSetupEngineeringService.audit_parameter_eligibility(["camber_stiffness_front"])
    assert res_unident["gate_passed"] is False
    assert "camber_stiffness_front" in res_unident["prohibited_parameters"]

    # Case E: Numerically failed parameter refusal
    res_num_fail = Phase3LSetupEngineeringService.audit_parameter_eligibility(["tire_load_degressivity"])
    assert res_num_fail["gate_passed"] is False
    assert "tire_load_degressivity" in res_num_fail["prohibited_parameters"]


# ── HOSTILE TESTS (MANDATE 14) ────────────────────────────────────────────────

def test_hostile_1_unidentifiable_parameters_refusal():
    """Hostile Invariant 1: Unidentifiable parameters cannot enter optimization."""
    with pytest.raises(UnidentifiableParameterError, match="UNIDENTIFIABLE"):
        Phase3LSetupEngineeringService.assert_parameters_eligible(["camber_stiffness_front"])


@pytest.mark.asyncio
async def test_hostile_2_setup_provenance_preserved(async_test_db: AsyncSession):
    """Hostile Invariant 2: Setup provenance is preserved with parent linkage."""
    user_id = str(uuid.uuid4())
    setup = await Phase3LSetupEngineeringService.create_setup_candidate(
        db=async_test_db,
        user_id=user_id,
        setup_id="SETUP-TEST-PROV",
        parent_setup_id="SETUP-PARENT-91",
        changed_parameters={"k_arb_front_nm": {"baseline": 25000.0, "candidate": 32000.0, "delta_pct": 28.0}},
        unchanged_parameters={"mass_kg": 1420.0},
        parameter_provenance={"k_arb_front_nm": "IDENTIFIED_PRIOR_PHASE3J"},
        creation_reason="Audit test",
    )
    assert setup["parent_setup_id"] == "SETUP-PARENT-91"
    assert setup["parameter_provenance"]["k_arb_front_nm"] == "IDENTIFIED_PRIOR_PHASE3J"
    assert len(setup["artifact_hash"]) == 64


def test_hostile_3_model_version_consistency():
    """Hostile Invariant 3: Baseline and candidate must use the same model version."""
    sim = Phase3LSetupEngineeringService.execute_real_simulation(setup_id="SETUP-MODEL-CHECK")
    assert sim["model_version"] == Phase3LSetupEngineeringService.MODEL_VERSION
    assert sim["solver_version"] == Phase3LSetupEngineeringService.SOLVER_VERSION


def test_hostile_4_simulation_outputs_real_solver():
    """Hostile Invariant 4: Simulation outputs are real solver outputs (varying dynamically)."""
    # Run two different setups and verify the numerical states actually differ
    sim1 = Phase3LSetupEngineeringService.execute_real_simulation("SETUP-S1", k_arb_front=25000.0, c_damper_front=3800.0)
    sim2 = Phase3LSetupEngineeringService.execute_real_simulation("SETUP-S2", k_arb_front=45000.0, c_damper_front=5500.0)

    # State trajectories must not be identical
    assert sim1["input_hash"] != sim2["input_hash"]
    assert sim1["output_hash"] != sim2["output_hash"]
    assert sim1["metrics"]["peak_lateral_accel_g"] != sim2["metrics"]["peak_lateral_accel_g"]
    assert sim1["metrics"]["yaw_rate_rmse_radps"] != sim2["metrics"]["yaw_rate_rmse_radps"]
    assert sim1["runtime_s"] > 0.0


@pytest.mark.asyncio
async def test_hostile_5_and_6_holdout_remains_untouched_and_zero_leakage(async_test_db: AsyncSession):
    """Hostile Invariants 5 & 6: Holdout remains untouched and zero data leakage is proven."""
    user_id = str(uuid.uuid4())
    val = await Phase3LSetupEngineeringService.execute_sealed_blind_validation(
        db=async_test_db,
        user_id=user_id,
        candidate_setup_id="SETUP-OPT",
        candidate_params={"k_arb_front_nm": 33000.0, "c_damper_front_nsm": 4200.0},
        fit_window=(39.0, 42.0),
        holdout_window=(42.0, 44.0),
    )
    assert val["is_zero_leakage"] is True
    assert val["parameters_frozen"] is True

    # Test leakage rejection if windows overlap
    with pytest.raises(HoldoutLeakageError, match="Data leakage detected"):
        await Phase3LSetupEngineeringService.execute_sealed_blind_validation(
            db=async_test_db,
            user_id=user_id,
            candidate_setup_id="SETUP-OPT",
            candidate_params={"k_arb_front_nm": 33000.0},
            fit_window=(39.0, 43.0),
            holdout_window=(42.0, 45.0),
        )


@pytest.mark.asyncio
async def test_hostile_7_and_8_prediction_immutability_and_reconciliation(async_test_db: AsyncSession):
    """Hostile Invariants 7 & 8: Prediction is immutable; reconciliation cannot alter historical evidence."""
    user_id = str(uuid.uuid4())

    # 1. Create prediction
    pred = await Phase3LSetupEngineeringService.generate_track_test_prediction(
        db=async_test_db,
        user_id=user_id,
        decision_id="DEC-TEST",
        candidate_setup_id="SETUP-TEST",
        prediction_id="PRED-HOSTILE-01",
    )
    assert pred["is_immutable"] is True

    # 2. Tamper check: if prediction hash in DB is corrupted, reconciliation refuses
    res = await async_test_db.execute(
        select(TrackTestPredictionRecord).where(TrackTestPredictionRecord.prediction_id == "PRED-HOSTILE-01")
    )
    rec = res.scalar_one()
    original_hash = rec.prediction_hash

    # Malicious modification simulation
    rec.expected_candidate_metric = {"peak_roll_angle_deg": 1.0}  # falsified number
    await async_test_db.flush()

    with pytest.raises(ImmutablePredictionError, match="prediction hash mismatch"):
        await Phase3LSetupEngineeringService.reconcile_post_track_session(
            db=async_test_db,
            user_id=user_id,
            prediction_id="PRED-HOSTILE-01",
        )

    # Restore correct hash
    rec.expected_candidate_metric = {"peak_roll_angle_deg": 2.45, "peak_lateral_accel_g": 1.99, "front_susp_travel_mm": 48.5}
    await async_test_db.flush()


def test_hostile_9_failed_simulations_cannot_become_accepted():
    """Hostile Invariant 9: Candidates with constraint violations or solver divergence are rejected."""
    candidates = [
        {"setup_id": "CAND-FAILED-TRAVEL", "metrics": {"max_suspension_travel_mm": 62.0, "peak_roll_angle_deg": 2.10, "peak_lateral_accel_g": 1.90, "yaw_rate_rmse_radps": 0.05}},
    ]
    with pytest.raises(NoFeasibleSetupError, match="0 feasible setups"):
        Phase3LSetupEngineeringService.evaluate_multi_objective(candidates)


def test_hostile_10_stale_models_are_rejected():
    """Hostile Invariant 10: Stale models trigger failure diagnostics and cannot be accepted."""
    diag = Phase3LSetupEngineeringService.diagnose_failure("stale_model")
    assert "Stale model version detected" in diag["WHAT_FAILED"]
    assert "cannot" in diag["WHAT_CANNOT_BE_CLAIMED"].lower()


@pytest.mark.asyncio
async def test_hostile_11_invalid_parameter_combinations_rejected(async_test_db: AsyncSession):
    """Hostile Invariant 11: Setups violating physical boundaries are rejected."""
    with pytest.raises(PhysicalBoundsViolationError, match="outside physical"):
        await Phase3LSetupEngineeringService.create_setup_candidate(
            db=async_test_db,
            user_id=str(uuid.uuid4()),
            setup_id="SETUP-INVALID",
            parent_setup_id="SETUP-BASE",
            changed_parameters={"anti_roll_bar_front": {"candidate": 999999.0}},  # Unphysical
            unchanged_parameters={},
            parameter_provenance={},
            creation_reason="Invalid test",
        )


@pytest.mark.asyncio
async def test_hostile_12_decision_has_complete_lineage(async_test_db: AsyncSession):
    """Hostile Invariant 12: Every final decision has a complete 14-step lineage."""
    user_id = str(uuid.uuid4())
    bundle = await Phase3LSetupEngineeringService.execute_full_workflow(
        db=async_test_db,
        user_id=user_id,
        approver_name="Elena Rostova",
        approver_role="Chief Race Engineer",
    )
    lineage = bundle["lineage"]
    assert len(lineage) == 14
    stages = [s["stage"] for s in lineage]
    assert "RECONCILIATION" in stages
    assert "TRACK_PREDICTION" in stages
    assert "DECISION" in stages
    assert "BLIND_VALIDATION" in stages
    assert "MULTI_OBJECTIVE" in stages
    assert "SIMULATION" in stages
    assert "SETUP_CANDIDATE" in stages
    assert "EXPERIMENT_DESIGN" in stages
    assert "CAUSAL_HYPOTHESIS" in stages
    assert "PARAMETER_GATE" in stages
    assert "PROBLEM_DEFINITION" in stages
    assert "DATASET_PROVENANCE" in stages


# ── TEST 13: 14 FAILURE MODES UX DIAGNOSTICS (SECTION 13) ──────────────────────

def test_phase3l_all_14_failure_modes_diagnostics():
    """
    Section 13: Verifies that all 14 failure modes produce the mandatory 5 sections:
    WHAT FAILED, WHY, WHAT REMAINS VALID, WHAT CANNOT BE CLAIMED, WHAT CAN BE DONE NEXT.
    """
    failure_types = [
        "unidentifiable_parameter_selected",
        "partially_identifiable_without_uncertainty",
        "setup_violates_physical_bounds",
        "setup_violates_validity_domain",
        "solver_failure",
        "optimizer_failure",
        "candidate_outside_model_envelope",
        "validation_failure",
        "holdout_leakage",
        "missing_provenance",
        "stale_model",
        "conflicting_objectives",
        "no_feasible_setup",
        "track_prediction_unavailable",
    ]

    for mode in failure_types:
        diag = Phase3LSetupEngineeringService.diagnose_failure(
            failure_type=mode,
            context={"parameter": "camber_stiffness_front", "value": 95000.0},
        )

        for mandatory_key in ["WHAT_FAILED", "WHY", "WHAT_REMAINS_VALID", "WHAT_CANNOT_BE_CLAIMED", "WHAT_CAN_BE_DONE_NEXT"]:
            assert mandatory_key in diag, f"Missing '{mandatory_key}' in failure mode '{mode}'"
            assert len(diag[mandatory_key]) > 10, f"Section '{mandatory_key}' too short in '{mode}'"

        # Check explicit negative assertion
        assert "cannot" in diag["WHAT_CANNOT_BE_CLAIMED"].lower() or "must not" in diag["WHAT_CANNOT_BE_CLAIMED"].lower()


# ── TEST 14: FASTAPI REST ENDPOINTS INTEGRATION ────────────────────────────────

@pytest.mark.asyncio
async def test_phase3l_fastapi_rest_endpoints():
    """
    Verifies FastAPI REST routes mounted under /api/v1/setup-engineering/ and /api/v1/decision-loop/phase3l/.
    """
    from fastapi.testclient import TestClient
    from suspensionlab.backend.api.main import app
    from suspensionlab.backend.security.auth import verify_api_key, UserContext
    from suspensionlab.backend.database.core import get_db_dependency

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    test_user = UserContext(
        user_id=str(uuid.uuid4()),
        email="elena.rostova@suspensionlab.com",
        name="Elena Rostova",
        plan="PRO",
        onboarding_complete=True,
        team_role="ENGINEER",
        permissions=["setup:create", "vehicle:read", "simulation:run", "setup:approve"],
    )

    app.dependency_overrides[get_db_dependency] = override_get_db
    app.dependency_overrides[verify_api_key] = lambda: test_user

    client = TestClient(app)

    try:
        # 1. Parameter Gate endpoint
        resp_gate = client.post(
            "/api/v1/setup-engineering/gate-parameters",
            json={"candidate_parameters": ["spring_rate_front", "camber_stiffness_front"]},
        )
        assert resp_gate.status_code == 200
        gate_data = resp_gate.json()
        assert gate_data["gate_passed"] is False
        assert "camber_stiffness_front" in gate_data["prohibited_parameters"]

        # 2. Failure Diagnostic endpoint
        resp_diag = client.post(
            "/api/v1/setup-engineering/diagnose-failure",
            json={"failure_type": "solver_failure"},
        )
        assert resp_diag.status_code == 200
        diag_data = resp_diag.json()
        assert "WHAT_FAILED" in diag_data
        assert "Numerical Solver Divergence" in diag_data["WHAT_FAILED"]

        # 3. Setup Simulation endpoint
        resp_sim = client.post(
            "/api/v1/setup-engineering/simulate",
            json={
                "setup_id": "SETUP-TEST-API",
                "k_arb_front": 33000.0,
                "c_damper_front": 4200.0,
                "telemetry_window_s": [39.0, 42.0],
                "dt_s": 0.005,
            },
        )
        assert resp_sim.status_code == 200
        sim_data = resp_sim.json()
        assert sim_data["solver_status"] == "SUCCESS"
        assert "metrics" in sim_data

        # 4. Manifest endpoint
        resp_manifest = client.get("/api/v1/setup-engineering/manifest")
        assert resp_manifest.status_code == 200
        manifest_data = resp_manifest.json()
        assert manifest_data["status"] == "SETUP_ENGINEERING_WORKFLOW_READY"

    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
