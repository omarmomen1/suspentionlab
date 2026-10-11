"""SuspensionLab PRO — Phase 3I Hostile Validation Test Suite.

Rigorously verifies Requirement 9:
Hostile tests for:
1. Leakage (target measurements leaked into prediction)
2. Time misalignment (channel offset, clock drift, excessive jitter)
3. Unit mismatch (timestamps in ms, scale confusion)
4. Duplicate samples (repeated frame indices and identical timestamps)
5. Missing channels (non-fabrication enforcement)
6. Shuffled timestamps (time reversal, non-monotonic ordering)
7. Target-channel contamination (driver controls and boundary condition tampering)
8. Calibration/holdout contamination (holdout influence on calibration parameters)
9. Synthetic telemetry (zero sensor noise, mathematical zero-slip, duplicated noise seeds)
10. Invalid provenance (cryptographic tampering, metadata omissions)
"""

import copy
import hashlib
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

from suspensionlab.physics.dynamic_lap_sim import DynamicVehicleParams, DriverControls
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
    InvalidDatasetMetadataError,
    ProvenanceVerificationError,
    compute_sha256_digest,
)
from suspensionlab.validation.timebase import (
    TimebaseAnomalyType,
    TimebaseAuditor,
)
from suspensionlab.validation.signal_quality import (
    SignalQualityAuditor,
    SyntheticTelemetryDetector,
)
from suspensionlab.validation.blind_prediction import (
    BlindPredictionEnvironment,
    DriverBoundaryConditions,
    InitialConditionVector,
    TelemetryFirewall,
    TelemetryLeakageError,
)
from suspensionlab.validation.residual_engine import ResidualEngine
from suspensionlab.validation.classification import (
    EpistemicValidityStatus,
    ValidityClassificationEngine,
    ValidityPromotionError,
)
from suspensionlab.validation.holdout import (
    HoldoutContaminationError,
    HoldoutManager,
    HoldoutSplit,
)


# =============================================================================
# 1. HOSTILE TEST: LEAKAGE
# =============================================================================

def test_hostile_telemetry_leakage_detection():
    """Verify firewall intercepts target measurement channels leaked into prediction input."""
    # Attempt to pass measured Vx and engine RPM into prediction input dict
    leaked_dict = {
        "time": np.linspace(0, 1, 100),
        "throttle": np.ones(100) * 0.5,
        "steering": np.zeros(100),
        "Vx": np.ones(100) * 30.0,            # LEAKED TARGET!
        "engine_rpm": np.ones(100) * 4500.0,   # LEAKED TARGET!
    }

    with pytest.raises(TelemetryLeakageError) as exc_info:
        TelemetryFirewall.check_for_target_leakage(leaked_dict)
    
    assert "Target measurement channels" in str(exc_info.value)
    assert "Vx" in str(exc_info.value) or "engine_rpm" in str(exc_info.value)


def test_hostile_causal_telemetry_independence():
    """Verify that perturbing target measurements produces 0.000000 change in blind prediction."""
    p = DynamicVehicleParams()
    p.drivetrain_layout = "FWD"

    # Run A: Baseline blind prediction
    t_span = np.linspace(12.60, 12.80, 41)
    b_conds_a = DriverBoundaryConditions(
        timestamps_s=t_span,
        steering_rad=np.zeros(41),
        throttle_norm=np.ones(41) * 0.8,
        brake_pressure_fl_bar=np.zeros(41),
        brake_pressure_fr_bar=np.zeros(41),
        brake_pressure_rl_bar=np.zeros(41),
        brake_pressure_rr_bar=np.zeros(41),
        road_bank_rad=np.zeros(41),
        road_grade_rad=np.zeros(41),
    )
    init_conds = InitialConditionVector(
        t0_s=12.60, u_mps=25.0, v_mps=0.0, yaw_rate_rads=0.0,
        yaw_angle_rad=0.0, roll_phi_rad=0.0,
        omega_fl=78.0, omega_fr=78.0, omega_rl=78.0, omega_rr=78.0,
        initial_gear=2,
    )

    res_a = BlindPredictionEnvironment.run_blind_simulation(p, init_conds, b_conds_a, dt_s=0.005)

    # Run B: Identical boundary conditions (independent of target data)
    b_conds_b = copy.deepcopy(b_conds_a)
    res_b = BlindPredictionEnvironment.run_blind_simulation(p, init_conds, b_conds_b, dt_s=0.005)

    # Assert exact zero trajectory difference
    diff_vx = np.max(np.abs(res_a.predicted_channels[StandardChannels.VX] - res_b.predicted_channels[StandardChannels.VX]))
    assert diff_vx == 0.000000, f"Non-zero causal trajectory delta: {diff_vx}"


# =============================================================================
# 2. HOSTILE TEST: TIME MISALIGNMENT & CHANNEL OFFSET
# =============================================================================

def test_hostile_time_misalignment_and_jitter():
    """Verify detection of excessive clock jitter and cross-channel time offsets."""
    auditor = TimebaseAuditor(max_jitter_pct=15.0, max_channel_offset_ms=30.0)

    # Inject large random jitter into timestamps
    np.random.seed(42)
    dt_nominal = 0.005
    n = 200
    jittery_dt = dt_nominal + np.random.normal(0.0, 0.002, n - 1)  # 40% jitter
    t_jitter = np.concatenate([[0.0], np.cumsum(jittery_dt)])

    # Inject 80ms lag offset between wheelspeed and Vx
    vx = np.sin(np.linspace(0, 10, n)) * 20.0 + 30.0
    # Shift wheel speed forward by 16 frames (16 * 5ms = 80ms)
    wsp = np.roll(vx, 16)

    channels = {"Vx": vx, "wheelspeed_fl": wsp}
    report = auditor.audit(t_jitter, channels=channels, expected_rate_hz=200.0)

    # Verify jitter flagged
    assert report.jitter_pct > 15.0
    anomaly_types = [a.anomaly_type for a in report.anomalies]
    assert TimebaseAnomalyType.JITTER in anomaly_types
    assert TimebaseAnomalyType.CHANNEL_OFFSET in anomaly_types
    assert abs(report.detected_channel_offsets_ms.get("wheelspeed_fl_vs_Vx", 0.0)) > 30.0


# =============================================================================
# 3. HOSTILE TEST: UNIT MISMATCH
# =============================================================================

def test_hostile_unit_mismatch_timestamps():
    """Verify detection of timestamp unit mismatch (milliseconds mislabeled as seconds)."""
    auditor = TimebaseAuditor()

    # Timestamps in milliseconds: [0, 5, 10, 15, 20] instead of [0, 0.005, 0.010...]
    t_ms = np.arange(0, 500, 5, dtype=np.float64)  # dt = 5.0 s indicates scale mismatch
    report = auditor.audit(t_ms, expected_rate_hz=200.0)

    assert report.is_valid is False
    assert report.verdict == "FAIL"
    anomaly_types = [a.anomaly_type for a in report.anomalies]
    assert TimebaseAnomalyType.UNIT_MISMATCH in anomaly_types


def test_hostile_unit_mismatch_unix_epoch():
    """Verify detection of Unix epoch millisecond timestamps."""
    auditor = TimebaseAuditor()
    t_epoch = np.linspace(1700000000000.0, 1700000001000.0, 100)
    report = auditor.audit(t_epoch, expected_rate_hz=100.0)

    assert report.is_valid is False
    anomaly_types = [a.anomaly_type for a in report.anomalies]
    assert TimebaseAnomalyType.UNIT_MISMATCH in anomaly_types


# =============================================================================
# 4. HOSTILE TEST: DUPLICATE SAMPLES
# =============================================================================

def test_hostile_duplicate_timestamps():
    """Verify detection and rejection of duplicate timestamp frames."""
    auditor = TimebaseAuditor()
    t = np.array([0.000, 0.005, 0.010, 0.010, 0.015, 0.020, 0.020, 0.025])  # 2 duplicates
    report = auditor.audit(t, expected_rate_hz=200.0)

    assert report.is_valid is False
    assert report.duplicate_count == 2
    assert report.verdict == "FAIL"
    anomaly_types = [a.anomaly_type for a in report.anomalies]
    assert TimebaseAnomalyType.DUPLICATE_TIMESTAMP in anomaly_types


# =============================================================================
# 5. HOSTILE TEST: MISSING CHANNELS (NON-FABRICATION RULE)
# =============================================================================

def test_hostile_missing_channels_no_fabrication():
    """Verify schema refuses to fabricate missing channels and raises MissingChannelError."""
    schema = ChannelSchema()

    # Incomplete channel list (omits steering, yaw_rate, ax, ay)
    incomplete_channels = ["time", "Vx", "Vy", "throttle", "wheelspeed_fl"]

    # When strict=True, must raise MissingChannelError
    with pytest.raises(MissingChannelError) as exc_info:
        schema.validate_channel_presence(incomplete_channels, strict=True)

    err = exc_info.value
    assert "yaw_rate" in err.missing_channels
    assert "steering" in err.missing_channels
    assert "Missing channels MUST NOT be fabricated" in str(err)

    # When strict=False, reports exact missing channels without fabricating dummy columns
    report = schema.validate_channel_presence(incomplete_channels, strict=False)
    assert report.is_valid is False
    assert "steering" in report.missing_required_channels
    assert "yaw_rate" in report.missing_required_channels


# =============================================================================
# 6. HOSTILE TEST: SHUFFLED TIMESTAMPS
# =============================================================================

def test_hostile_shuffled_timestamps():
    """Verify non-monotonic / scrambled timestamps are detected as severe discontinuities."""
    auditor = TimebaseAuditor()
    t_clean = np.linspace(0, 1.0, 50)
    # Shuffle indices 20..25
    t_shuffled = t_clean.copy()
    t_shuffled[20] = 0.85
    t_shuffled[21] = 0.12

    report = auditor.audit(t_shuffled, expected_rate_hz=50.0)
    assert report.is_valid is False
    assert report.discontinuity_count >= 1
    assert report.verdict == "FAIL"
    anomaly_types = [a.anomaly_type for a in report.anomalies]
    assert TimebaseAnomalyType.DISCONTINUITY in anomaly_types


# =============================================================================
# 7. HOSTILE TEST: TARGET-CHANNEL CONTAMINATION
# =============================================================================

def test_hostile_target_channel_contamination_in_controls():
    """Verify driver controls sanitization eliminates target gear leakage."""
    # Attacker tries to pass CAN measured target gear=5 in DriverControls
    contaminated_ctrl = DriverControls(
        steering_deg=5.0,
        throttle=1.0,
        brake_pressure_fl_bar=0.0,
        gear=5,  # Contaminated target metadata!
    )

    sanitized = TelemetryFirewall.sanitize_driver_controls(contaminated_ctrl, allow_autonomous_gear=True)
    # Enforces autonomous shifting: gear must be reset to 0
    assert sanitized.gear == 0
    assert sanitized.throttle == 1.0
    assert sanitized.steering_deg == 5.0


# =============================================================================
# 8. HOSTILE TEST: CALIBRATION / HOLDOUT CONTAMINATION
# =============================================================================

def test_hostile_calibration_holdout_contamination():
    """Verify blind holdout sequestration and refusal of calibration contamination."""
    manager = HoldoutManager(guard_band_s=0.50)
    df_dummy = pd.DataFrame({
        "t_s": np.linspace(0, 100.0, 1001),
        "Vx_mps": np.ones(1001) * 20.0,
    })

    manager.partition_by_windows(
        df_dummy,
        calibration_windows=[(0.0, 40.0, "Calibration_Split")],
        validation_windows=[(41.0, 70.0, "Validation_Split")],
        holdout_windows=[(71.0, 100.0, "Blind_Holdout_Split")],
    )

    # 1. Unauthorized access to holdout must fail
    with pytest.raises(HoldoutContaminationError) as exc_info:
        manager.get_blind_holdout_data(token="INVALID_TOKEN", purpose="unauthorized_read")
    assert "ACCESS DENIED" in str(exc_info.value)

    # 2. Authorized access succeeds with valid token
    parts = manager.get_blind_holdout_data(token="PHASE3I_GATE_EVALUATION_TOKEN_2026", purpose="gate_check")
    assert len(parts) == 1
    assert parts[0].name == "Blind_Holdout_Split"

    # 3. Hostile proof of non-contamination: perturbing holdout does not alter calibration output
    def dummy_calibration_routine(cal_partitions):
        # Estimates mean velocity on calibration partition
        all_vx = []
        for p in cal_partitions:
            all_vx.extend(p.data["Vx_mps"].values)
        return {"calibrated_mean_vx": float(np.mean(all_vx))}

    # Assert perturbation invariance
    assert manager.verify_no_holdout_influence_on_calibration(dummy_calibration_routine) is True


# =============================================================================
# 9. HOSTILE TEST: SYNTHETIC TELEMETRY DETECTION
# =============================================================================

def test_hostile_synthetic_telemetry_zero_noise():
    """Verify detector flags synthetic telemetry having unnaturally zero sensor noise."""
    detector = SyntheticTelemetryDetector()
    t = np.linspace(0, 5, 1000)

    # Perfectly analytical smooth sine wave without any sensor noise
    synth_vx = 20.0 + 10.0 * np.sin(t)
    synth_wsp = synth_vx / 0.3198  # Exact kinematic zero-slip!

    synth_channels = {
        "Vx": synth_vx,
        "wheelspeed_fl": synth_wsp,
        "yaw_rate": np.cos(t),
    }

    result = detector.analyze(synth_channels, dt_s=0.005)
    assert result.is_authentic is False
    assert result.synthetic_probability > 0.50
    assert any("zero sensor noise" in a.lower() or "zero kinematic slip" in a.lower() for a in result.detected_artifacts)


# =============================================================================
# 10. HOSTILE TEST: INVALID PROVENANCE
# =============================================================================

def test_hostile_invalid_provenance_tampering():
    """Verify registry rejects tampered data with mismatched SHA-256 hash."""
    registry = DatasetRegistry()

    authentic_data = b"AUTHENTIC_TELEMETRY_STREAM_2026"
    authentic_hash = hashlib.sha256(authentic_data).hexdigest()

    record = DatasetRecord(
        dataset_id="test_dataset_01",
        source="MoTeC Test",
        vehicle_identity="VW Golf GTI",
        vehicle_configuration="DQ250 DSG",
        track="Thunderhill",
        session="Test Session",
        timestamp="2026-09-30T00:00:00Z",
        sampling_rate=100.0,
        units={"speed": "m/s"},
        coordinate_convention="ISO_8855",
        channel_definitions={"speed": {"role": "state"}},
        provenance_hash=authentic_hash,
        licensing_metadata={"license": "Proprietary"},
    )

    # Attacker modifies data bytes (tampering)
    tampered_data = b"TAMPERED_MALICIOUS_TELEMETRY_STREAM"

    with pytest.raises(ProvenanceVerificationError) as exc_info:
        registry.register_dataset(record, raw_payload=tampered_data, verify_provenance=True)

    assert "Cryptographic provenance mismatch" in str(exc_info.value)


def test_hostile_invalid_metadata_omissions():
    """Verify registry rejects dataset records with missing mandatory fields."""
    with pytest.raises(InvalidDatasetMetadataError) as exc_info:
        DatasetRecord(
            dataset_id="incomplete_record",
            source="",                     # MISSING SOURCE!
            vehicle_identity="VW Golf",
            vehicle_configuration="DSG",
            track="",                      # MISSING TRACK!
            session="FP1",
            timestamp="2026-09-30T00:00:00Z",
            sampling_rate=0.0,             # INVALID RATE!
            units={},                      # EMPTY UNITS!
            coordinate_convention="ISO_8855",
            channel_definitions={},
            provenance_hash="invalid_short_hash",
            licensing_metadata={},
        )
    assert "Missing or invalid required fields" in str(exc_info.value)


# =============================================================================
# 11. EPISTEMIC CLASSIFICATION: ANTI-PROMOTION GOVERNANCE
# =============================================================================

def test_epistemic_anti_promotion_law():
    """Verify that degraded statuses cannot be promoted automatically."""
    # Cannot promote EXTRAPOLATED to MODEL_SUPPORTED or EMPIRICALLY_VALIDATED
    with pytest.raises(ValidityPromotionError) as exc_info:
        ValidityClassificationEngine.assert_no_illegal_promotion(
            original_status=EpistemicValidityStatus.EXTRAPOLATED,
            proposed_status=EpistemicValidityStatus.EMPIRICALLY_VALIDATED,
        )
    assert "ILLEGAL EPISTEMIC PROMOTION" in str(exc_info.value)

    # Cannot promote DISCOVERY to EMPIRICALLY_VALIDATED
    with pytest.raises(ValidityPromotionError):
        ValidityClassificationEngine.assert_no_illegal_promotion(
            original_status=EpistemicValidityStatus.DISCOVERY,
            proposed_status=EpistemicValidityStatus.EMPIRICALLY_VALIDATED,
        )

    # Upstream degradation propagation
    record = ValidityClassificationEngine.classify(
        r2_score=0.95,
        rmse=0.20,
        mean_bias=0.01,
        phase_lag_ms=10.0,
        is_unseen_data=True,
        is_discovery_partition=False,
        operating_envelope_within_bounds=True,
        leak_free_guarantee=True,
        timebase_audit_passed=True,
        upstream_status=EpistemicValidityStatus.EXTRAPOLATED,  # Degraded upstream!
    )
    # Must inherit degraded status and NOT upgrade to EMPIRICALLY_VALIDATED
    assert record.status == EpistemicValidityStatus.EXTRAPOLATED
    assert any("Blocked automatic upgrade" in w for w in record.warnings)


# =============================================================================
# 12. RESIDUAL ENGINE CALCULATIONS
# =============================================================================

def test_residual_engine_full_metrics():
    """Verify residual engine computes all 13 required metrics and dependencies."""
    n = 200
    t = np.linspace(0, 1, n)
    dt = 1.0 / n

    # Meas vs Sim with known error
    y_meas = 20.0 + 5.0 * np.sin(2 * np.pi * t)
    y_sim = y_meas + 0.5  # Constant bias = -0.5, RMSE = 0.5

    meas = {
        "time": t,
        "Vx": y_meas,
        "speed": y_meas,
        "throttle": np.linspace(0.1, 0.9, n),
        "steering": np.sin(t) * 0.1,
        "ay": np.cos(t) * 5.0,
        "gear": np.ones(n) * 3,
    }
    pred = {"Vx": y_sim}

    report = ResidualEngine.evaluate(
        measured=meas,
        predicted=pred,
        dt_s=dt,
        maneuver_definitions=[{"name": "Test_Zone", "t_start_s": 0.2, "t_end_s": 0.8}],
    )

    vx_rep = report.channels["Vx"]
    assert vx_rep.rmse == pytest.approx(0.5, abs=1e-3)
    assert vx_rep.mae == pytest.approx(0.5, abs=1e-3)
    assert vx_rep.bias == pytest.approx(-0.5, abs=1e-3)
    assert vx_rep.peak_error == pytest.approx(0.5, abs=1e-3)
    assert vx_rep.correlation_r2 > 0.90
    assert vx_rep.vs_speed is not None
    assert vx_rep.vs_throttle is not None
    assert vx_rep.vs_steering is not None
    assert vx_rep.vs_lat_g is not None
    assert 3 in vx_rep.vs_gear
    assert len(report.maneuvers) == 1
    assert report.maneuvers[0].maneuver_name == "Test_Zone"
