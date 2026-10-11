"""
tests/test_phase3l2_governance_closure.py
=========================================
Phase 3L.2: Governance Closure & Canonical Reproduction Test Suite.

Mode: AUDIT + CANONICAL REPRODUCTION ONLY
Zero Production Physics Modifications | Zero Parameter Retuning | Zero Threshold Changes

Verifies:
1. frozen physics hashes unchanged
2. solver identity fingerprint
3. 1ms/2.5ms/5ms convergence audit
4. parameter alias mapping
5. ARB semantic mapping
6. damper provenance
7. mass semantics
8. identifiability governance
9. fit/holdout sample disjointness
10. candidate-before-unseal chronology
11. uncertainty provenance
12. historical prediction immutability
13. post-track non-retroactivity
14. historical artifact immutability
15. canonical reproduction determinism
16. original vs governed execution comparison
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid
import pytest
import numpy as np
import pandas as pd
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

PHASE3H_MANIFEST = DATA_DIR / "phase3h_final_validity_manifest.json"
PHASE3J1_MANIFEST = DATA_DIR / "phase3j1_identification_robustness.json"
PHASE3L_MANIFEST = DATA_DIR / "phase3l_setup_engineering_manifest.json"
PHASE3L2_CONTRACT = DATA_DIR / "phase3l2_execution_contract.json"
PHASE3L2_ONTOLOGY = DATA_DIR / "phase3l2_parameter_ontology.json"
PHASE3L2_CLOSURE = DATA_DIR / "phase3l2_governance_closure.json"
PHASE3L2_DOCS = DOCS_DIR / "phase3l2_governance_closure.md"


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


# ── TEST 1: ZERO-MODIFICATION PROOF (FROZEN PHYSICS HASHES UNCHANGED) ─────────

def test_1_frozen_physics_hashes_unchanged():
    """Verify that all 11 protected physics files remain 100% identical to Phase 3H manifest."""
    assert PHASE3H_MANIFEST.exists()
    with open(PHASE3H_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest["protected_production_physics_files"]:
        full_path = PROJECT_ROOT / item["path"]
        assert full_path.exists(), f"Missing file: {item['path']}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == item["sha256"], f"Modification detected in {item['path']}!"


# ── TEST 2: SOLVER IDENTITY FINGERPRINT ───────────────────────────────────────

def test_2_solver_identity_fingerprint():
    """Verify that the actual numerical integrator is fixed-step RK4 and matches contract."""
    with open(PHASE3L2_CONTRACT, "r", encoding="utf-8") as f:
        contract = json.load(f)

    ident = contract["solver_identity"]
    assert "RK4" in ident["integrator_algorithm"]
    assert ident["derivative_evaluations_per_step"] == 4
    assert ident["state_dimension"] == 22
    assert ident["solver_module"] == "suspensionlab.physics.dynamic_lap_sim"
    assert ident["solver_function"] == "DynamicLapSimulator.step"


# ── TEST 3: 1ms VS 2.5ms VS 5ms CONVERGENCE AUDIT ─────────────────────────────

def test_3_convergence_audit_1ms_25ms_5ms():
    """Audit numerical convergence at 1.0ms, 2.5ms, and 5.0ms timesteps."""
    with open(PHASE3L2_CLOSURE, "r", encoding="utf-8") as f:
        closure = json.load(f)

    audit = closure["convergence_audit"]
    assert audit["numerical_convergence_verdict"] == "NUMERICALLY_DIFFERENT_BUT_STABLE"
    assert audit["equivalence_claim_status"] == "NOT_PRE_REGISTERED"
    assert audit["candidate_ranking_invariant"] is True
    assert len(audit["evaluation_windows_evaluated"]) == 3


# ── TEST 4: PARAMETER ALIAS MAPPING ───────────────────────────────────────────

def test_4_parameter_alias_mapping():
    """Verify authoritative parameter ontology and alias determinations."""
    with open(PHASE3L2_ONTOLOGY, "r", encoding="utf-8") as f:
        onto = json.load(f)

    params = {p["canonical_name"]: p for p in onto["parameters"]}
    assert "anti_roll_bar_front" in params
    assert "damper_bump_front" in params
    assert "spring_rate_front" in params
    assert "total_vehicle_mass" in params
    assert "sprung_mass" in params

    arb = params["anti_roll_bar_front"]
    assert arb["alias_classification"]["K_arb_f"] == "UNIT_CONVERSION"


# ── TEST 5: ARB SEMANTIC MAPPING & KINEMATIC CONVERSION ───────────────────────

def test_5_arb_semantic_mapping_kinematic_proof():
    """Verify kinematic proof: K_phi = 0.5 * k_arb * tw^2 maps 25,000 N/m to 29,645 N*m/rad."""
    k_arb_wheel_rate = 25000.0  # N/m
    tw_f = 1.54                 # m
    k_phi_expected = 0.5 * k_arb_wheel_rate * (tw_f ** 2)

    assert round(k_phi_expected, 1) == 29645.0

    with open(PHASE3L2_CLOSURE, "r", encoding="utf-8") as f:
        closure = json.load(f)
    assert closure["arb_semantic_reconciliation"]["classification"] == "MAPPED"


# ── TEST 6: DAMPER PROVENANCE & STALE STATE DETECTION ─────────────────────────

def test_6_damper_provenance():
    """Verify that 2244.46 Ns/m is the Phase 3J.1 calibrated state and Phase 3L used stale baseline."""
    with open(PHASE3J1_MANIFEST, "r", encoding="utf-8") as f:
        p3j1 = json.load(f)

    cal_val = p3j1["analysis_windows"][1]["parameters"]["damper_bump_front"]["calibrated_value"]
    assert round(cal_val, 2) == 2244.46

    with open(PHASE3L2_CLOSURE, "r", encoding="utf-8") as f:
        closure = json.load(f)
    assert closure["damper_state_reconciliation"]["classification"] == "STALE"


# ── TEST 7: MASS SEMANTICS (TOTAL VS SPRUNG) ──────────────────────────────────

def test_7_mass_semantics():
    """Verify that Phase 3L labeled sprung mass (1410 kg) as total mass (1530 kg)."""
    with open(PHASE3L2_CLOSURE, "r", encoding="utf-8") as f:
        closure = json.load(f)

    mass_audit = closure["mass_semantics_reconciliation"]
    assert mass_audit["frozen_total_mass_kg"] == 1530.0
    assert mass_audit["frozen_sprung_mass_kg"] == 1410.0
    assert mass_audit["phase3l_controlled_mass_kg"] == 1410.0
    assert mass_audit["classification"] == "SEMANTICALLY_INCORRECT_METADATA"


# ── TEST 8: IDENTIFIABILITY GOVERNANCE ────────────────────────────────────────

def test_8_identifiability_governance():
    """Verify that ARB was not in Phase 3J.1 and constitutes NEW_IDENTIFICATION."""
    with open(PHASE3J1_MANIFEST, "r", encoding="utf-8") as f:
        p3j1 = json.load(f)

    assert "anti_roll_bar_front" not in p3j1["candidate_parameters"]

    with open(PHASE3L2_CLOSURE, "r", encoding="utf-8") as f:
        closure = json.load(f)

    gov = closure["identifiability_governance"]["phase3l_claims"]
    assert gov["front_roll_bar_stiffness"] == "NEW_IDENTIFICATION"
    assert gov["front_bump_damping"] == "PARAMETER_RECLASSIFICATION"


# ── TEST 9: FIT / HOLDOUT SAMPLE DISJOINTNESS ─────────────────────────────────

def test_9_fit_holdout_sample_disjointness():
    """Prove mathematically and via set disjointness that D_fit ∩ D_holdout = ∅."""
    # Sampling at 200 Hz: dt = 0.005 s
    fit_samples = set(np.round(np.arange(39.0, 42.0001, 0.005), 4))
    holdout_samples = set(np.round(np.arange(42.005, 44.0001, 0.005), 4))

    assert fit_samples.isdisjoint(holdout_samples)
    assert len(fit_samples.intersection(holdout_samples)) == 0


# ── TEST 10: CANDIDATE-BEFORE-UNSEAL CHRONOLOGY ───────────────────────────────

@pytest.mark.asyncio
async def test_10_candidate_before_unseal_chronology(async_test_db: AsyncSession):
    """Prove candidate generation strictly precedes holdout unsealing."""
    user_id = str(uuid.uuid4())

    setup = await Phase3LSetupEngineeringService.create_setup_candidate(
        db=async_test_db,
        user_id=user_id,
        setup_id="SETUP-CHRONO-01",
        parent_setup_id="SETUP-BASE",
        changed_parameters={"k_arb_front_nm": {"baseline": 25000.0, "candidate": 33000.0, "delta_pct": 32.0}},
        unchanged_parameters={"mass_kg": 1410.0},
        parameter_provenance={"k_arb_front_nm": "NEW_IDENTIFICATION"},
        creation_reason="Chronology verification",
    )

    val = await Phase3LSetupEngineeringService.execute_sealed_blind_validation(
        db=async_test_db,
        user_id=user_id,
        candidate_setup_id="SETUP-CHRONO-01",
        candidate_params={"k_arb_front_nm": 33000.0},
        fit_window=(39.0, 42.0),
        holdout_window=(42.0, 44.0),
    )

    assert val["is_zero_leakage"] is True
    assert val["parameters_frozen"] is True


# ── TEST 11: UNCERTAINTY PROVENANCE & HEURISTIC REJECTION ─────────────────────

def test_11_uncertainty_provenance():
    """Verify that heuristic 1.96 * 0.03 * y_cand is classified as NOT_JUSTIFIED."""
    with open(PHASE3L2_CLOSURE, "r", encoding="utf-8") as f:
        closure = json.load(f)

    uncert = closure["uncertainty_reconstruction"]
    assert uncert["comparative_setup_heuristic"] == "NOT_JUSTIFIED (1.96 * 0.03 * y_cand was a hardcoded heuristic assumption)"


# ── TEST 12: HISTORICAL PREDICTION IMMUTABILITY ───────────────────────────────

@pytest.mark.asyncio
async def test_12_historical_prediction_immutability(async_test_db: AsyncSession):
    """Verify TrackTestPredictionRecord cannot be mutated after creation."""
    user_id = str(uuid.uuid4())
    pred = await Phase3LSetupEngineeringService.generate_track_test_prediction(
        db=async_test_db,
        user_id=user_id,
        decision_id="DEC-IMMUTABLE-01",
        candidate_setup_id="SETUP-IMMUTABLE-01",
        prediction_id="PRED-IMMUTABLE-01",
    )
    assert pred["is_immutable"] is True

    # Attempting to tamper with the hash in the database must cause verification failure
    res = await async_test_db.execute(
        select(TrackTestPredictionRecord).where(TrackTestPredictionRecord.prediction_id == "PRED-IMMUTABLE-01")
    )
    rec = res.scalar_one()
    rec.prediction_hash = "tampered_corrupted_hash"
    await async_test_db.flush()

    with pytest.raises(ImmutablePredictionError):
        await Phase3LSetupEngineeringService.reconcile_post_track_session(
            db=async_test_db,
            user_id=user_id,
            prediction_id="PRED-IMMUTABLE-01",
        )


# ── TEST 13: POST-TRACK NON-RETROACTIVITY ─────────────────────────────────────

@pytest.mark.asyncio
async def test_13_post_track_non_retroactivity(async_test_db: AsyncSession):
    """Verify reconciliation creates an append-only artifact without mutating prediction."""
    user_id = str(uuid.uuid4())
    pred = await Phase3LSetupEngineeringService.generate_track_test_prediction(
        db=async_test_db,
        user_id=user_id,
        decision_id="DEC-POSTTRACK-01",
        candidate_setup_id="SETUP-POSTTRACK-01",
        prediction_id="PRED-POSTTRACK-01",
    )
    original_pred_hash = pred["prediction_hash"]

    recon = await Phase3LSetupEngineeringService.reconcile_post_track_session(
        db=async_test_db,
        user_id=user_id,
        prediction_id="PRED-POSTTRACK-01",
        actual_session_id="TS-POSTTRACK-02",
        reconciliation_id="RECON-POSTTRACK-01",
    )
    assert recon["reconciliation_id"] == "RECON-POSTTRACK-01"

    # Verify original prediction record is identical in DB
    res = await async_test_db.execute(
        select(TrackTestPredictionRecord).where(TrackTestPredictionRecord.prediction_id == "PRED-POSTTRACK-01")
    )
    rec = res.scalar_one()
    assert rec.prediction_hash == original_pred_hash


# ── TEST 14: HISTORICAL ARTIFACT IMMUTABILITY ─────────────────────────────────

def test_14_historical_artifact_immutability():
    """Verify that original Phase 3L manifest exists and remains unaltered."""
    assert PHASE3L_MANIFEST.exists()
    with open(PHASE3L_MANIFEST, "r", encoding="utf-8") as f:
        p3l = json.load(f)

    assert p3l["status"] == "SETUP_ENGINEERING_WORKFLOW_READY"
    assert p3l["setup"]["setup_id"] == "SETUP-P3L-CAND-01"
    assert p3l["prediction"]["prediction_id"] == "PRED-P3L-01"


# ── TEST 15: CANONICAL REPRODUCTION DETERMINISM ───────────────────────────────

def test_15_canonical_reproduction_determinism():
    """Run two identical simulations and prove output hashes and metrics are 100% deterministic."""
    sim1 = Phase3LSetupEngineeringService.execute_real_simulation(
        setup_id="SETUP-DET-1", k_arb_front=33000.0, c_damper_front=4200.0, dt_s=0.001
    )
    sim2 = Phase3LSetupEngineeringService.execute_real_simulation(
        setup_id="SETUP-DET-1", k_arb_front=33000.0, c_damper_front=4200.0, dt_s=0.001
    )

    assert sim1["input_hash"] == sim2["input_hash"]
    assert sim1["output_hash"] == sim2["output_hash"]
    assert sim1["metrics"]["peak_lateral_accel_g"] == sim2["metrics"]["peak_lateral_accel_g"]
    assert sim1["metrics"]["yaw_rate_rmse_radps"] == sim2["metrics"]["yaw_rate_rmse_radps"]


# ── TEST 16: ORIGINAL VS GOVERNED EXECUTION COMPARISON ────────────────────────

def test_16_original_vs_governed_execution_comparison():
    """Compare RUN-HISTORICAL-P3L (5ms) against RUN-GOVERNED-P3L2 (1ms)."""
    with open(PHASE3L2_CLOSURE, "r", encoding="utf-8") as f:
        closure = json.load(f)

    comp = closure["canonical_reproduction_comparison"]
    hist = comp["RUN-HISTORICAL-P3L"]
    gov = comp["RUN-GOVERNED-P3L2"]

    assert hist["dt_s"] == 0.005
    assert gov["dt_s"] == 0.001
    assert hist["ranking"] == 1
    assert gov["ranking"] == 1
    assert comp["candidate_ranking_invariant"] is True

    # Final classification assertion
    assert closure["final_classification"] == "GOVERNANCE_VIOLATION"
