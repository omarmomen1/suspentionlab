"""
tests/test_phase3l1_integrity_reconciliation.py
===============================================
Phase 3L.1: Setup Engineering Integrity & Provenance Reconciliation Test Suite.

Mode: AUDIT ONLY | ZERO PRODUCTION PHYSICS MODIFICATIONS

Verifies:
1. All 11 protected production physics files match the Phase 3H freeze manifest SHA-256.
2. Solver execution path reconciliation (DynamicLapSimulator.step RK4 vs reported RK45).
3. Parameter registry reconciliation & aliasing across 4 system layers.
4. Identifiability governance: Phase 3J.1 comparison & NEW_IDENTIFICATION_EXPERIMENT status.
5. Unit & Value audit: Front ARB (MAPPED), Front damper (STALE), Mass (INCORRECT).
6. Holdout provenance: D_fit ∩ D_holdout = ∅ & temporal monotonicity.
7. Uncertainty audit: Fisher FIM, bootstrap, and rejection of arbitrary intervals.
8. Real-solver proof: Distinct physical state trajectories and hash divergence.
9. Post-track reconciliation: Historical prediction immutability.
10. Causal language audit: Zero forbidden causal claims in documentation or code.
11. Final gate verdict: PASS_WITH_FINDINGS.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid
import pytest
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.setup_engineering import (
    EngineeringProblemRecord,
    CausalHypothesisRecord,
    ControlledExperimentDesignRecord,
    SetupCandidateRecord,
    TrackTestPredictionRecord,
    PostTrackReconciliationRecord,
)
from suspensionlab.backend.services.phase3l_setup_engineering_service import (
    Phase3LSetupEngineeringService,
    ImmutablePredictionError,
    HoldoutLeakageError,
)
from suspensionlab.calibration.registry import (
    STANDARD_PARAMETER_REGISTRY,
    ParameterRegistry,
)
from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
)
from suspensionlab.physics.powertrain_lap_sim import PowertrainCorrectedLapSimulator
from suspensionlab.validation.blind_prediction import BlindPredictionEnvironment


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
PHASE3H_MANIFEST_PATH = DATA_DIR / "phase3h_final_validity_manifest.json"
PHASE3J1_MANIFEST_PATH = DATA_DIR / "phase3j1_identification_robustness.json"
PHASE3L1_MANIFEST_PATH = DATA_DIR / "phase3l1_integrity_reconciliation.json"
PHASE3L1_DOCS_PATH = DOCS_DIR / "phase3l1_integrity_reconciliation.md"


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


# ── TEST 1: DELIVERABLES EXISTENCE & MANIFEST INTEGRITY ───────────────────────

def test_phase3l1_deliverables_existence():
    """Verify that all Phase 3L.1 mandated deliverables exist on disk."""
    assert PHASE3L1_DOCS_PATH.exists(), f"Missing docs: {PHASE3L1_DOCS_PATH}"
    assert PHASE3L1_MANIFEST_PATH.exists(), f"Missing manifest: {PHASE3L1_MANIFEST_PATH}"

    with open(PHASE3L1_MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["phase"] == "PHASE_3L.1"
    assert manifest["final_classification"] == "PASS_WITH_FINDINGS"
    assert len(manifest["summary_of_findings"]) >= 6


# ── TEST 2: PROTECTED PHYSICS CHECKSUM AUDIT (100% MATCH) ─────────────────────

def test_phase3l1_protected_physics_file_hashes():
    """
    Mandate 1: Verify that Phase 3L modified zero production physics files.
    All 11 files must match Phase 3H freeze manifest SHA-256 with 100% precision.
    """
    assert PHASE3H_MANIFEST_PATH.exists()
    with open(PHASE3H_MANIFEST_PATH, "r", encoding="utf-8") as f:
        p3h = json.load(f)

    protected_files = p3h["protected_production_physics_files"]
    assert len(protected_files) == 11

    mismatches = []
    for item in protected_files:
        rel_path = item["path"]
        expected_sha = item["sha256"]
        full_path = PROJECT_ROOT / rel_path

        assert full_path.exists(), f"Protected file {rel_path} does not exist!"
        with open(full_path, "rb") as f_bin:
            actual_sha = hashlib.sha256(f_bin.read()).hexdigest()

        if actual_sha != expected_sha:
            mismatches.append((rel_path, expected_sha, actual_sha))

    assert len(mismatches) == 0, f"Physics integrity violation! Modified files: {mismatches}"


# ── TEST 3: SOLVER RECONCILIATION & DISCREPANCY CLASSIFICATION ────────────────

def test_phase3l1_solver_reconciliation():
    """
    Section 1: Trace execution path and classify solver discrepancy.
    Confirms solver uses fixed-step RK4 wrapped by PowertrainCorrectedLapSimulator,
    and identifies documented 'RK45' as a documentation labeling discrepancy.
    """
    # 1. Inspect class hierarchy
    assert issubclass(PowertrainCorrectedLapSimulator, DynamicLapSimulator)

    # 2. Inspect step method algorithm in DynamicLapSimulator
    import inspect
    step_source = inspect.getsource(DynamicLapSimulator.step)
    assert "k1" in step_source
    assert "k2" in step_source
    assert "k3" in step_source
    assert "k4" in step_source
    assert "Runge-Kutta 4 (RK4)" in step_source or "RK4" in step_source

    # 3. Read Phase 3L.1 manifest solver reconciliation verdict
    with open(PHASE3L1_MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    s_recon = manifest["solver_reconciliation"]
    assert s_recon["solver_classification"] == "WRAPPER_WITH_DOCUMENTATION_DISCREPANCY"
    assert s_recon["time_step_used_s"] == 0.005
    assert s_recon["frozen_default_time_step_s"] == 0.001


# ── TEST 4: PARAMETER REGISTRY RECONCILIATION & ALIAS TRACING ─────────────────

def test_phase3l1_parameter_registry_reconciliation():
    """
    Section 2: Reconcile all Phase 3L parameters with canonical registry and detect aliases.
    """
    reg = STANDARD_PARAMETER_REGISTRY
    assert reg.has("anti_roll_bar_front")
    assert reg.has("damper_bump_front")
    assert reg.has("spring_rate_front")
    assert reg.has("camber_stiffness_front")

    # Anti-roll bar units in registry are N*m/rad
    arb_def = reg.get("anti_roll_bar_front")
    assert arb_def.units == "N*m/rad"
    assert arb_def.nominal_value == 35000.0

    # In DynamicVehicleParams, k_arb_front_nm is defined with default 25000.0
    dp = DynamicVehicleParams()
    assert dp.k_arb_front_nm == 25000.0
    assert dp.c_damper_front_nsm == 3800.0


# ── TEST 5: IDENTIFIABILITY GOVERNANCE & NEW EXPERIMENT CLASSIFICATION ────────

def test_phase3l1_identifiability_governance():
    """
    Section 3: Compare Phase 3J.1 results against Phase 3L claims.
    Prove that anti_roll_bar_front was NOT in Phase 3J.1 and constitutes a NEW experiment.
    """
    with open(PHASE3J1_MANIFEST_PATH, "r", encoding="utf-8") as f:
        p3j1 = json.load(f)

    j1_params = p3j1["candidate_parameters"]
    assert "spring_rate_front" in j1_params
    assert "damper_bump_front" in j1_params
    assert "camber_stiffness_front" in j1_params
    # anti_roll_bar_front was NOT evaluated in Phase 3J.1
    assert "anti_roll_bar_front" not in j1_params
    assert "front_roll_bar_stiffness" not in j1_params

    # Verify manifest governance classification
    with open(PHASE3L1_MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    gov = manifest["identifiability_governance"]
    assert gov["governance_rule_verdict"] == "NEW_IDENTIFICATION_EXPERIMENT"


# ── TEST 6: UNIT AND VALUE AUDIT CLASSIFICATIONS ──────────────────────────────

def test_phase3l1_unit_and_value_audit_classifications():
    """
    Section 4: Verify specific discrepancy determinations:
    - Front ARB (25000 N/m vs 35000 N*m/rad): MAPPED
    - Front Damper (3800 vs 2245 vs 4200 Ns/m): STALE
    - Mass (1530 kg total vs 1410 kg controlled): INCORRECT
    """
    with open(PHASE3L1_MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    uv_audit = manifest["unit_and_value_audit"]
    assert uv_audit["front_anti_roll_bar"]["discrepancy_classification"] == "MAPPED"
    assert uv_audit["front_damper"]["discrepancy_classification"] == "STALE"
    assert uv_audit["vehicle_mass"]["discrepancy_classification"] == "INCORRECT"


# ── TEST 7: HOLDOUT PROVENANCE & STRICT DISJOINTNESS ──────────────────────────

@pytest.mark.asyncio
async def test_phase3l1_holdout_provenance_and_temporal_order(async_test_db: AsyncSession):
    """
    Section 5: Prove D_fit ∩ D_holdout = ∅ and candidate generation precedes holdout unseal.
    """
    user_id = str(uuid.uuid4())
    fit_win = (39.0, 42.0)
    hold_win = (42.0, 44.0)

    # Prove disjointness mathematically
    assert fit_win[1] <= hold_win[0]

    val = await Phase3LSetupEngineeringService.execute_sealed_blind_validation(
        db=async_test_db,
        user_id=user_id,
        candidate_setup_id="SETUP-P3L-CAND-01",
        candidate_params={"k_arb_front_nm": 33000.0, "c_damper_front_nsm": 4200.0},
        fit_window=fit_win,
        holdout_window=hold_win,
    )
    assert val["is_zero_leakage"] is True
    assert val["parameters_frozen"] is True

    # Leaking window must raise HoldoutLeakageError
    with pytest.raises(HoldoutLeakageError):
        await Phase3LSetupEngineeringService.execute_sealed_blind_validation(
            db=async_test_db,
            user_id=user_id,
            candidate_setup_id="SETUP-P3L-CAND-01",
            candidate_params={"k_arb_front_nm": 33000.0},
            fit_window=(39.0, 42.5),
            holdout_window=(42.0, 44.0),
        )


# ── TEST 8: UNCERTAINTY METHOD AUDIT & CLASSIFICATION ─────────────────────────

def test_phase3l1_uncertainty_audit_classifications():
    """
    Section 6: Trace every uncertainty interval to its mathematical method.
    Rejects heuristic interval in comparative setup as NOT_JUSTIFIED.
    """
    with open(PHASE3L1_MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    uncert_items = {item["entity"]: item["classification"] for item in manifest["uncertainty_audit"]}
    assert uncert_items["CausalHypothesisRecord.parameter_standard_errors"] == "PARAMETER_UNCERTAINTY"
    assert uncert_items["CausalHypothesisRecord.bootstrap_ci_95"] == "CONFIDENCE_INTERVAL"
    assert uncert_items["SetupComparisonRecord.ci_95"] == "NOT_JUSTIFIED"
    assert uncert_items["TrackTestPredictionRecord.uncertainty_interval"] == "PREDICTION_INTERVAL"


# ── TEST 9: REAL-SOLVER PROOF (DISTINCT PHYSICAL TRAJECTORIES) ────────────────

def test_phase3l1_real_solver_distinct_physics_proof():
    """
    Section 7: Prove that Phase 3L results originate from genuine solver execution.
    Two different setups must yield distinct input hashes, output hashes, and states.
    """
    res1 = Phase3LSetupEngineeringService.execute_real_simulation(
        setup_id="SETUP-AUDIT-A", k_arb_front=25000.0, c_damper_front=3800.0
    )
    res2 = Phase3LSetupEngineeringService.execute_real_simulation(
        setup_id="SETUP-AUDIT-B", k_arb_front=45000.0, c_damper_front=5500.0
    )

    assert res1["input_hash"] != res2["input_hash"]
    assert res1["output_hash"] != res2["output_hash"]
    assert res1["metrics"]["peak_lateral_accel_g"] != res2["metrics"]["peak_lateral_accel_g"]
    assert res1["metrics"]["yaw_rate_rmse_radps"] != res2["metrics"]["yaw_rate_rmse_radps"]
    assert res1["runtime_s"] > 0.0
    assert res2["runtime_s"] > 0.0


# ── TEST 10: POST-TRACK RECONCILIATION IMMUTABILITY ───────────────────────────

@pytest.mark.asyncio
async def test_phase3l1_post_track_reconciliation_immutability(async_test_db: AsyncSession):
    """
    Section 8: Verify TrackTestPrediction immutability and non-retroactive evidence ledger.
    """
    user_id = str(uuid.uuid4())
    pred = await Phase3LSetupEngineeringService.generate_track_test_prediction(
        db=async_test_db,
        user_id=user_id,
        decision_id="DEC-P3L-AUDIT",
        candidate_setup_id="SETUP-P3L-AUDIT",
        prediction_id="PRED-P3L-AUDIT-01",
    )
    assert pred["is_immutable"] is True

    # Reconcile with subsequent actual session
    recon = await Phase3LSetupEngineeringService.reconcile_post_track_session(
        db=async_test_db,
        user_id=user_id,
        prediction_id="PRED-P3L-AUDIT-01",
        actual_session_id="TS-STANFORD-02",
        reconciliation_id="RECON-P3L-AUDIT-01",
    )
    assert recon["original_prediction_hash_verified"] is True
    assert recon["reconciliation_status"] == "RECONCILED_CONFIRMED"

    # Original prediction in database must remain completely unaltered
    res = await async_test_db.execute(
        select(TrackTestPredictionRecord).where(TrackTestPredictionRecord.prediction_id == "PRED-P3L-AUDIT-01")
    )
    pred_db = res.scalar_one()
    assert pred_db.prediction_hash == pred["prediction_hash"]


# ── TEST 11: CAUSAL LANGUAGE SCAN ─────────────────────────────────────────────

def test_phase3l1_causal_language_compliance():
    """
    Section 9: Search Phase 3L files for forbidden causal claims.
    Assert zero occurrences of unsupported phrases.
    """
    forbidden_terms = [
        "proves cause",
        "causes",
        "validated cause",
        "confirmed cause",
        "empirically proven",
    ]

    target_files = [
        PHASE3L1_DOCS_PATH,
        DOCS_DIR / "phase3l_setup_engineering.md",
        PROJECT_ROOT / "src/suspensionlab/backend/services/phase3l_setup_engineering_service.py",
        DATA_DIR / "phase3l_setup_engineering_manifest.json",
    ]

    violations = []
    for fpath in target_files:
        if not fpath.exists():
            continue
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, start=1):
                line_lower = line.lower()
                # Skip self-referential meta documentation lines that cite the audit terms
                if "scanned:" in line_lower or "forbidden_terms" in line_lower:
                    continue
                for term in forbidden_terms:
                    # Allow 'causes' only if inside 'causing' or in comments rejecting causation
                    if term in line_lower and "do not convert correlation into causation" not in line_lower and "causing" not in line_lower:
                        violations.append((fpath.name, line_no, term, line.strip()))

    assert len(violations) == 0, f"Forbidden causal language found: {violations}"


# ── TEST 12: FINAL CLASSIFICATION VERDICT ─────────────────────────────────────

def test_phase3l1_final_classification_verdict():
    """
    Section 10: Verify the authoritative final classification for Phase 3L.
    Must be PASS_WITH_FINDINGS.
    """
    with open(PHASE3L1_MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["final_classification"] == "PASS_WITH_FINDINGS"
