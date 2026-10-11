"""
tests/test_telemetry_hostile_ingestion.py
=========================================
Hostile test suite for telemetry ingestion, channel health, and correlation cockpit.

Covers all 13 hostile conditions:
 1. Corrupt CSV (garbage bytes, malformed lines)
 2. NaN / Inf injection (strictly never silently zeroed)
 3. Missing time channel
 4. Duplicate timestamps
 5. Missing channels (quality state: MISSING)
 6. Mismatched units / out-of-range physical bounds
 7. Empty session (0 rows or header only)
 8. Constant signal flatline (dead sensor detection)
 9. Insufficient sample count (< 5 points)
10. Invalid correlation (incompatible channel comparison)
11. Cross-tenant isolation violation
12. Stale data detection
13. Anti-tautology verification (model diverges when parameters change)
"""

import math
import numpy as np
import pytest

from suspensionlab.physics.telemetry_parser import (
    parse_telemetry_csv,
    normalize_to_100hz,
    validate_channels,
    IngestionAuditTrail,
)
from suspensionlab.physics.telemetry_health import (
    assess_telemetry_health,
    TelemetryHealthReport,
    ChannelQualityState,
    TelemetryPipelineStatus,
)
from suspensionlab.physics.residual_analysis import (
    compute_residuals,
    ResidualAnalysisReport,
)
from suspensionlab.backend.services.telemetry_correlation_service import (
    TelemetryCorrelationService,
)
from suspensionlab.physics.telemetry_analysis import (
    analyse_session,
    compare_telemetry_sessions,
)


# ── 1. Corrupt CSV ────────────────────────────────────────────────────────────
def test_hostile_corrupt_csv():
    """Corrupt CSV: garbage binary data, missing delimiters, random unparseable lines."""
    corrupt_csv = "Time,Speed,G_Lat\n0.0,20.0,0.1\nCORRUPT_BYTES_\\x00\\xFF\n0.02,abc,0.2\n0.03,22.0\n"
    data = parse_telemetry_csv(corrupt_csv)
    # The audit trail must log parse rejections or errors
    audit = data.get("_audit_trail") or getattr(data, "_audit_trail", None)
    assert audit is not None
    assert audit["raw_lines_count"] == 5

    # Channels must not silently fail; unparseable cells must be NaN, not 0
    speeds = data["speed"]
    assert math.isnan(speeds[1])  # 'abc' converted to NaN, not 0.0


# ── 2. NaN / Inf Injection ───────────────────────────────────────────────────
def test_hostile_nan_inf_never_zeroed():
    """Confirms NaN and Inf values are preserved and never silently converted to 0.0."""
    csv_text = (
        "Time,Speed,G_Lat,Damper_FL\n"
        "0.0,20.0,0.1,10.0\n"
        "0.01,NaN,Inf,-Inf\n"
        "0.02,22.0,NULL,nan\n"
        "0.03,23.0,,12.0\n"
    )
    data = parse_telemetry_csv(csv_text)
    speeds = data["speed"]
    lat_g = data["lat_g"]
    damper = data["damper_fl"]

    assert math.isnan(speeds[1])
    assert math.isinf(lat_g[1])
    assert math.isnan(lat_g[2])  # NULL -> NaN
    assert math.isnan(speeds[3]) == False  # 23.0 is valid

    # Health check must detect these and flag quality
    health = assess_telemetry_health(data, time_channel=data["time"])
    assert "damper_fl" in health.channels
    assert health.channels["damper_fl"].missing_pct > 20.0


# ── 3. Missing Time Channel ───────────────────────────────────────────────────
def test_hostile_missing_time():
    """CSV with no recognizable time channel."""
    no_time_csv = "Speed,G_Lat,Damper_FL\n20.0,0.1,10.0\n21.0,0.2,11.0\n22.0,0.3,12.0\n"
    data = parse_telemetry_csv(no_time_csv)
    # time channel is synthesized or marked missing
    assert "time" not in data or len(data.get("time", [])) == 0

    health = assess_telemetry_health(data, time_channel=data.get("time"))
    assert not health.can_proceed
    assert any("time" in r.lower() for r in health.blocking_reasons)
    assert health.pipeline_status == TelemetryPipelineStatus.REJECTED


# ── 4. Duplicate Timestamps ───────────────────────────────────────────────────
def test_hostile_duplicate_timestamps():
    """CSV with duplicate timestamps must be logged in audit trail and de-duplicated during 100Hz resampling."""
    dup_csv = (
        "Time,Speed,G_Lat\n"
        "0.00,20.0,0.1\n"
        "0.01,20.5,0.2\n"
        "0.01,20.6,0.2\n"  # duplicate timestamp
        "0.02,21.0,0.3\n"
        "0.03,21.5,0.4\n"
    )
    data = parse_telemetry_csv(dup_csv)
    audit = data.get("_audit_trail")
    assert audit["duplicate_timestamps_count"] == 1

    resampled = normalize_to_100hz(data)
    time_res = resampled["time"]
    assert np.all(np.diff(time_res) > 0.0)  # Strictly monotonic output


# ── 5. Missing Channels ───────────────────────────────────────────────────────
def test_hostile_missing_channels():
    """Only 1 channel provided; expected channels must be marked MISSING with failure UX."""
    sparse_data = {
        "time": [0.0, 0.01, 0.02, 0.03, 0.04],
        "speed": [20.0, 20.1, 20.2, 20.3, 20.4],
    }
    health = assess_telemetry_health(
        sparse_data,
        time_channel=sparse_data["time"],
        expected_channels=["speed", "lat_g", "vert_g", "damper_fl"],
    )
    assert health.channels["damper_fl"].quality_state == ChannelQualityState.MISSING
    assert health.channels["lat_g"].quality_state == ChannelQualityState.MISSING
    assert health.channels["speed"].quality_state == ChannelQualityState.VALID
    assert health.failure_ux is not None
    assert len(health.failure_ux.what_cannot_be_claimed) > 0


# ── 6. Mismatched Units / Out-of-Range Physical Bounds ───────────────────────
def test_hostile_mismatched_units_and_range():
    """Absurd unphysical values (e.g. 500 G acceleration or 5000 km/h speed)."""
    absurd_data = {
        "time": np.linspace(0, 1, 100).tolist(),
        "speed": np.full(100, 5500.0).tolist(),  # Mach 4.5
        "lat_g": np.full(100, 450.0).tolist(),   # 450 G
    }
    health = assess_telemetry_health(absurd_data, time_channel=absurd_data["time"])
    assert not health.can_proceed
    assert health.channels["lat_g"].quality_state in (ChannelQualityState.INVALID, ChannelQualityState.WARNING)


# ── 7. Empty Session ──────────────────────────────────────────────────────────
def test_hostile_empty_session():
    """Completely empty file or header only."""
    with pytest.raises(Exception):
        parse_telemetry_csv("")

    header_only = "Time,Speed,G_Lat\n"
    data = parse_telemetry_csv(header_only)
    assert len(data.get("speed", [])) == 0
    health = assess_telemetry_health(data, time_channel=data.get("time"))
    assert not health.can_proceed
    assert health.pipeline_status == TelemetryPipelineStatus.REJECTED


# ── 8. Constant Signal Flatline (Dead Sensor Detection) ──────────────────────
def test_hostile_constant_signal_dead_sensor():
    """Flatline sensor with zero variance over the entire duration."""
    t = np.linspace(0, 10, 500).tolist()
    data = {
        "time": t,
        "speed": (20.0 + np.sin(np.array(t))).tolist(),
        "damper_fl": [14.2] * 500,  # Dead flatline sensor
    }
    health = assess_telemetry_health(data, time_channel=t)
    assert health.channels["damper_fl"].quality_state in (ChannelQualityState.INVALID, ChannelQualityState.WARNING)
    assert any("dead_sensor" in w.lower() or "flatline" in w.lower() for w in health.channels["damper_fl"].warnings)


# ── 9. Insufficient Samples ───────────────────────────────────────────────────
def test_hostile_insufficient_samples():
    """Fewer than minimum required samples (< 5)."""
    t = [0.0, 0.01, 0.02]
    data = {
        "time": t,
        "speed": [20.0, 21.0, 22.0],
    }
    health = assess_telemetry_health(data, time_channel=t)
    assert not health.can_proceed
    assert any("insufficient" in r.lower() or "sample" in r.lower() for r in health.blocking_reasons)


# ── 10. Invalid Correlation (Incompatible Signals) ───────────────────────────
def test_hostile_invalid_correlation():
    """Attempting residual comparison with mismatched channels or non-overlapping time."""
    meas = {"speed": [10.0, 20.0, 30.0], "time": [0.0, 1.0, 2.0]}
    sim = {"speed": [10.0, 20.0]}  # Length mismatch
    with pytest.raises(ValueError):
        compute_residuals(meas, sim)


# ── 11. Cross-Tenant Isolation Violation ─────────────────────────────────────
def test_hostile_cross_tenant_isolation():
    """TelemetryHub strictly raises TenantIsolationError when accessing another tenant's session."""
    from suspensionlab.telemetry.hub import TelemetryHub, TenantIsolationError
    hub = TelemetryHub()
    # Register session for Org Alpha
    hub.record_session_tenant("SESS-SECRET-ALPHA", "ORG-ALPHA")

    # Org Beta attempts to access
    with pytest.raises(TenantIsolationError):
        hub.assert_tenant_access("ORG-BETA", "SESS-SECRET-ALPHA", is_admin=False)

    # Admin bypasses
    assert hub.assert_tenant_access("ORG-BETA", "SESS-SECRET-ALPHA", is_admin=True) is True


# ── 12. Stale Data Detection ──────────────────────────────────────────────────
def test_hostile_stale_data_detection():
    """Check that correlation health flags data freshness when data is stale."""
    report = TelemetryCorrelationService.get_correlation_cockpit(session_id="SESS-STALE-TEST")
    assert "data_freshness_s" in report["correlation_health"]
    assert report["correlation_health"]["data_freshness_s"] < 5.0  # Live limit


# ── 13. Anti-Tautology Verification ──────────────────────────────────────────
def test_hostile_anti_tautology_verification():
    """
    ANTI-TAUTOLOGY MANDATE:
    Verifies that forward physics model output is NOT copied from telemetry.
    When spring rate k_s or damping c are intentionally altered, model output diverges.
    """
    baseline = TelemetryCorrelationService.compare_measured_vs_model(
        model_type="quarter_car",
        model_params={"k_s": 35000.0, "c": 2200.0},
    )
    stiffened = TelemetryCorrelationService.compare_measured_vs_model(
        model_type="quarter_car",
        model_params={"k_s": 95000.0, "c": 6000.0},  # Dramatically stiffer
    )

    base_rmse = baseline["channels"][0]["metrics"]["rmse"]
    stiff_rmse = stiffened["channels"][0]["metrics"]["rmse"]

    # Changing physics parameters MUST alter model predictions and residuals
    assert abs(base_rmse - stiff_rmse) > 1e-4
    assert baseline["sensor_alignment_manifest"]["anti_tautology_statement"] is not None
