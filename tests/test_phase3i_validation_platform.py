"""tests/test_phase3i_validation_platform.py
=============================================
Phase 3I Independent Vehicle Validation Platform Verification Suite.

Validates that the complete Phase 3I framework passes:
1. Universal Channel Schema & coordinate conventions (ISO 8855)
2. Dataset Registry with cryptographic provenance
3. Timebase Auditor (jitter, duplicates, discontinuities)
4. Signal Quality Auditor & Synthetic Telemetry Detection
5. Blind Prediction Environment with zero-leakage firewall
6. Comprehensive Residual Engine (RMSE, MAE, R2, operating dependencies)
7. Epistemic Validity Classification Engine & strict anti-upgrade governance
8. Cryptographically Sequestered Holdout Manager
9. End-to-End Independent Validation Pipeline
"""

import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from suspensionlab.validation.schema import (
    ChannelDefinition,
    ChannelRole,
    ChannelSchema,
    CoordinateConvention,
    MissingChannelError,
    ProvenanceClassification,
    StandardChannels,
    UNIVERSAL_CHANNEL_DEFINITIONS,
)
from suspensionlab.validation.registry import (
    DatasetRecord,
    DatasetRegistry,
)
from suspensionlab.validation.timebase import (
    TimebaseAuditor,
    TimebaseAnomalyType,
)
from suspensionlab.validation.signal_quality import (
    SignalQualityAuditor,
    SyntheticTelemetryDetector,
)
from suspensionlab.validation.blind_prediction import (
    BlindPredictionEnvironment,
    DriverBoundaryConditions,
    InitialConditionVector,
    TelemetryLeakageError,
)
from suspensionlab.validation.residual_engine import (
    ResidualEngine,
)
from suspensionlab.validation.classification import (
    EpistemicValidityStatus,
    ValidityClassificationEngine,
)
from suspensionlab.validation.holdout import (
    HoldoutContaminationError,
    HoldoutManager,
    HoldoutSplit,
)
from suspensionlab.validation.pipeline import (
    IndependentValidationPipeline,
)


def test_phase3i_channel_schema_and_definitions():
    """Verify universal channel definitions and ISO 8855 convention."""
    assert len(UNIVERSAL_CHANNEL_DEFINITIONS) >= 20
    assert StandardChannels.TIME in UNIVERSAL_CHANNEL_DEFINITIONS
    assert StandardChannels.VX in UNIVERSAL_CHANNEL_DEFINITIONS
    assert StandardChannels.YAW_RATE in UNIVERSAL_CHANNEL_DEFINITIONS

    vx_def = UNIVERSAL_CHANNEL_DEFINITIONS[StandardChannels.VX]
    assert vx_def.canonical_unit == "m/s"
    assert vx_def.role == ChannelRole.VEHICLE_STATE
    assert vx_def.provenance_class == ProvenanceClassification.TARGET_MEASUREMENT


def test_phase3i_dataset_registry_and_provenance():
    """Verify dataset registry enforces cryptographic SHA-256 provenance."""
    registry = DatasetRegistry()
    dummy_bytes = b"time,Vx,Vy\n0.0,10.0,0.0\n0.01,10.1,0.01\n"
    prov_hash = hashlib.sha256(dummy_bytes).hexdigest()

    rec = DatasetRecord(
        dataset_id="test_prov_dataset_01",
        source="Test Benchmark",
        vehicle_identity="VW Golf GTI",
        vehicle_configuration="FWD DSG",
        track="Thunderhill",
        session="2023-11",
        timestamp="2023-11-15T14:32:00Z",
        sampling_rate=200.0,
        units={"time": "s", "Vx": "m/s"},
        coordinate_convention=CoordinateConvention.ISO_8855.value,
        channel_definitions={
            "Vx": {
                "canonical_unit": "m/s",
                "role": ChannelRole.VEHICLE_STATE.value,
                "provenance_class": ProvenanceClassification.TARGET_MEASUREMENT.value,
                "description": "Longitudinal speed",
            }
        },
        provenance_hash=prov_hash,
        licensing_metadata={"license": "CC-BY-4.0"},
    )
    registry.register_dataset(rec, raw_payload=dummy_bytes)
    retrieved = registry.get_dataset("test_prov_dataset_01")
    assert retrieved.provenance_hash == prov_hash
    assert retrieved.dataset_id == "test_prov_dataset_01"


def test_phase3i_timebase_auditor():
    """Verify timebase audit flags duplicates, jitter, and non-monotonicity."""
    auditor = TimebaseAuditor(max_jitter_pct=15.0)

    # 1. Clean monotonic time
    t_clean = np.linspace(0.0, 1.0, 101)
    rep_clean = auditor.audit(t_clean)
    assert rep_clean.is_valid
    assert rep_clean.duplicate_count == 0
    assert rep_clean.verdict in ["PASS", "WARN"]

    # 2. Corrupted time with duplicate and non-monotonicity
    t_corrupt = np.array([0.0, 0.01, 0.01, 0.02, 0.015, 0.03])
    rep_corrupt = auditor.audit(t_corrupt)
    assert rep_corrupt.duplicate_count == 1
    assert rep_corrupt.verdict in ["WARN", "FAIL"]


def test_phase3i_synthetic_telemetry_detection():
    """Verify synthetic telemetry detector catches quantized/fabricated data."""
    detector = SyntheticTelemetryDetector()

    # Synthetic constant signal (zero sensor noise)
    synthetic_arr = np.full(100, 25.0)
    rep = detector.analyze({"Vx": synthetic_arr})
    assert not rep.is_authentic or rep.synthetic_probability > 0.40

    # Authentic noisy sensor signal
    rng = np.random.default_rng(42)
    t = np.linspace(0, 2, 200)
    authentic_signal = 15.0 + 2.0 * np.sin(t) + rng.normal(0, 0.05, 200)
    rep_auth = detector.analyze({"Vx": authentic_signal})
    assert rep_auth.is_authentic


def test_phase3i_blind_prediction_firewall():
    """Verify blind prediction mode firewall blocks state leakage from future telemetry."""
    n = 50
    t = np.linspace(0, 0.25, n)
    driver = DriverBoundaryConditions(
        timestamps_s=t,
        steering_rad=np.zeros(n),
        throttle_norm=np.ones(n) * 0.5,
        brake_pressure_fl_bar=np.zeros(n),
        brake_pressure_fr_bar=np.zeros(n),
        brake_pressure_rl_bar=np.zeros(n),
        brake_pressure_rr_bar=np.zeros(n),
        road_bank_rad=np.zeros(n),
        road_grade_rad=np.zeros(n),
    )
    init_state = InitialConditionVector(
        t0_s=0.0,
        u_mps=20.0,
        v_mps=0.0,
        yaw_rate_rads=0.0,
        yaw_angle_rad=0.0,
        roll_phi_rad=0.0,
        omega_fl=20.0 / 0.3198,
        omega_fr=20.0 / 0.3198,
        omega_rl=20.0 / 0.3198,
        omega_rr=20.0 / 0.3198,
        initial_gear=2,
    )
    from suspensionlab.physics.dynamic_lap_sim import DynamicVehicleParams
    params = DynamicVehicleParams()
    sim_res = BlindPredictionEnvironment.run_blind_simulation(params, init_state, driver, dt_s=0.005)
    assert len(sim_res.predicted_channels[StandardChannels.VX]) == n
    assert sim_res.predicted_channels[StandardChannels.VX][0] == 20.0
    assert sim_res.firewall_verified_leak_free


def test_phase3i_residual_engine():
    """Verify residual engine computes comprehensive statistics and dependencies."""
    engine = ResidualEngine()
    y_true = np.array([10.0, 12.0, 14.0, 16.0, 18.0])
    y_pred = np.array([10.2, 11.9, 13.8, 16.1, 18.2])

    summary = engine.evaluate(measured={"Vx": y_true}, predicted={"Vx": y_pred})
    vx_summary = summary.channels["Vx"]
    assert vx_summary.rmse > 0.0
    assert vx_summary.correlation_r2 > 0.90
    assert abs(vx_summary.bias) < 0.25


def test_phase3i_validity_classification_anti_upgrade():
    """Verify strict anti-upgrade governance prevents classifying poor models as VALIDATED."""
    classifier = ValidityClassificationEngine()

    # 1. Discovery partition cannot be EMPIRICALLY_VALIDATED even with perfect R2
    rec_disc = classifier.classify(
        r2_score=0.99,
        rmse=0.01,
        mean_bias=0.0,
        phase_lag_ms=0.0,
        is_unseen_data=False,
        is_discovery_partition=True,
        operating_envelope_within_bounds=True,
        leak_free_guarantee=True,
        timebase_audit_passed=True,
    )
    assert rec_disc.status == EpistemicValidityStatus.DISCOVERY
    assert rec_disc.status != EpistemicValidityStatus.EMPIRICALLY_VALIDATED

    # 2. Out of bounds must be EXTRAPOLATED
    rec_extra = classifier.classify(
        r2_score=0.95,
        rmse=0.1,
        mean_bias=0.0,
        phase_lag_ms=0.0,
        is_unseen_data=True,
        is_discovery_partition=False,
        operating_envelope_within_bounds=False,
        leak_free_guarantee=True,
        timebase_audit_passed=True,
    )
    assert rec_extra.status == EpistemicValidityStatus.EXTRAPOLATED

    # 3. Degraded upstream status cannot be upgraded
    rec_degraded = classifier.classify(
        r2_score=0.99,
        rmse=0.01,
        mean_bias=0.0,
        phase_lag_ms=0.0,
        is_unseen_data=True,
        is_discovery_partition=False,
        operating_envelope_within_bounds=True,
        leak_free_guarantee=True,
        timebase_audit_passed=True,
        upstream_status=EpistemicValidityStatus.UNSUPPORTED,
    )
    assert rec_degraded.status == EpistemicValidityStatus.UNSUPPORTED


def test_phase3i_holdout_manager_sequestration():
    """Verify HoldoutManager enforces cryptographic sealing and audit trail."""
    manager = HoldoutManager(guard_band_s=0.50)
    t = np.linspace(0, 10, 500)
    df = pd.DataFrame({"time": t, "Vx": 10.0 + np.sin(t)})

    manager.partition_by_windows(
        df,
        calibration_windows=[(0.0, 5.0, "cal")],
        validation_windows=[(5.5, 7.5, "val")],
        holdout_windows=[(8.0, 10.0, "hold")],
    )

    # Holdout is sealed without token
    with pytest.raises(HoldoutContaminationError, match="ACCESS DENIED"):
        manager.get_blind_holdout_data(token="INVALID_TOKEN")

    # Access with valid token succeeds
    hold_parts = manager.get_blind_holdout_data(token="PHASE3I_GATE_EVALUATION_TOKEN_2026")
    assert len(hold_parts) > 0
    assert not hold_parts[0].is_sealed


def test_phase3i_end_to_end_pipeline_execution():
    """Prerequisite verification: Phase 3I pipeline runs and passes on authentic telemetry."""
    raw_path = Path("data/external/stanford_vw_golf_thunderhill_2023_11.csv")
    if not raw_path.exists():
        pytest.skip("Authentic Stanford dataset not found.")

    df_raw = pd.read_csv(raw_path, comment="#")
    prov_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()

    dataset_record = DatasetRecord(
        dataset_id="stanford_vw_golf_thunderhill_2023_11",
        source="Stanford Dynamic Design Lab",
        vehicle_identity="2017 VW Golf VII GTI Performance",
        vehicle_configuration="FWD DQ250",
        track="Thunderhill",
        session="2023-11",
        timestamp="2023-11-15T14:32:00Z",
        sampling_rate=200.0,
        units={"time": "s", "Vx": "m/s"},
        coordinate_convention=CoordinateConvention.ISO_8855.value,
        channel_definitions={
            k: {
                "canonical_unit": v.canonical_unit,
                "role": v.role.value,
                "provenance_class": v.provenance_class.value,
                "description": v.description,
            }
            for k, v in UNIVERSAL_CHANNEL_DEFINITIONS.items()
        },
        provenance_hash=prov_hash,
        licensing_metadata={"license": "CC-BY-NC-4.0"},
        file_path=str(raw_path),
    )

    windows = [
        {"name": "Window_A_Upshift", "t_start_s": 12.60, "t_end_s": 12.80, "role": "BLIND_HOLDOUT", "init_gear": 2},
        {"name": "Turn_3_Approach", "t_start_s": 39.00, "t_end_s": 44.00, "role": "VALIDATION", "init_gear": 3},
    ]

    pipeline = IndependentValidationPipeline()
    res = pipeline.run_pipeline(
        raw_data=df_raw,
        dataset_record=dataset_record,
        validation_windows=windows,
        dt_s=0.005,
        unlock_token="PHASE3I_GATE_EVALUATION_TOKEN_2026",
        infer_gear_from_kinematics=True,
    )

    assert res is not None
    assert res.overall_pipeline_verdict in ["PASS", "WARN"]
    assert res.dataset_metadata["provenance_hash"] == prov_hash
    assert len(res.classification_records) == 2
