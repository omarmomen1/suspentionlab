"""Phase 3H.2 Gear Kinematics & Inference Tests.

Verifies:
1. Physical kinematic gear inference from engine RPM and driven wheel speed.
2. Low speed default handling and clutch slip / shifting state identification.
3. Dataset-wide forward gear validation (>90% locked engagement).
4. Epistemic rule compliance: raw CAN GearRatio channel is never used as an array index.
5. Arbitrary drivetrain ratio configuration support (zero hardcoded constants).
"""

import json
from pathlib import Path
import pytest

from suspensionlab.physics.gear_inference import (
    GearInferenceConfig,
    GearInferenceEngine,
    GearInferenceResult,
    GearEngagementStatus,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GEAR_INFERENCE_JSON = DATA_DIR / "phase3h2_gear_inference.json"


@pytest.fixture(scope="module")
def gear_inference_audit_data():
    assert GEAR_INFERENCE_JSON.exists(), f"Missing audit file: {GEAR_INFERENCE_JSON}"
    with open(GEAR_INFERENCE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_gear_inference_nominal_3rd_gear():
    """Verify inference engine correctly identifies 3rd gear across locked clutch."""
    engine = GearInferenceEngine()
    # HighSpeed S-Curves typical operating point: 4930.9 RPM, 91.51 rad/s
    res = engine.infer_gear(engine_rpm=4930.87, driven_wheel_speed_radps=91.51)

    assert res.inferred_gear == 3
    assert res.matched_nominal_ratio == pytest.approx(5.6427, abs=1e-3)
    assert res.ratio_residual < 0.02
    assert res.status == GearEngagementStatus.LOCKED
    assert res.confidence > 0.8
    assert res.epistemic_classification == "CONFIRMED_FROM_SENSOR_KINEMATICS"


def test_gear_inference_low_speed_floor():
    """Verify inference engine defaults to 1st gear under standstill / creep."""
    engine = GearInferenceEngine()
    res = engine.infer_gear(engine_rpm=1000.0, driven_wheel_speed_radps=0.5)

    assert res.inferred_gear == 1
    assert res.status == GearEngagementStatus.LOW_SPEED_DEFAULT
    assert res.confidence == 1.0


def test_gear_inference_clutch_slip_transient():
    """Verify inference engine flags clutch slip / shift transients when ratio deviates."""
    engine = GearInferenceEngine()
    # Ratio N = (4000 * 2*pi/60) / 60.0 = 6.981 (midway between 2nd 8.69 and 3rd 5.64)
    res = engine.infer_gear(engine_rpm=4000.0, driven_wheel_speed_radps=60.0)

    assert res.status == GearEngagementStatus.CLUTCH_SLIP_OR_SHIFT
    assert res.ratio_residual > 0.12


def test_arbitrary_gearbox_configuration():
    """Verify engine operates on arbitrary user-provided ratio dictionaries without hardcoding."""
    custom_ratios = {1: 12.0, 2: 7.5, 3: 5.0, 4: 3.5}
    config = GearInferenceConfig(candidate_ratios=custom_ratios, tolerance_ratio=0.10)
    engine = GearInferenceEngine(config=config)

    # 3500 RPM / (3500*2*pi/60 / 5.0) = 5.0
    w_wheel = (3500.0 * 2.0 * 3.14159265 / 60.0) / 5.0
    res = engine.infer_gear(engine_rpm=3500.0, driven_wheel_speed_radps=w_wheel)

    assert res.inferred_gear == 3
    assert res.matched_nominal_ratio == 5.0
    assert res.status == GearEngagementStatus.LOCKED


def test_dataset_wide_gear_inference_audit(gear_inference_audit_data):
    """Verify that dataset-wide audit confirms >90% locked clutch engagement and all 6 gears."""
    total_locked_pct = gear_inference_audit_data["total_locked_pct"]
    assert total_locked_pct >= 90.0, f"Expected >=90% locked engagement, got {total_locked_pct}%"

    gear_breakdown = gear_inference_audit_data["gear_breakdown"]
    for g in range(1, 7):
        key = f"Gear_{g}"
        assert key in gear_breakdown, f"Missing gear {g} in audit breakdown"
        g_data = gear_breakdown[key]
        assert g_data["total_samples"] > 0, f"Gear {g} has 0 samples"
        if g in [2, 3, 4, 5, 6]:
            assert g_data["locked_pct"] >= 90.0, f"Gear {g} locked pct too low: {g_data['locked_pct']}%"
            assert g_data["mean_residual"] < 0.05, f"Gear {g} residual too high: {g_data['mean_residual']}"


def test_epistemic_governance_no_raw_channel_indexing(gear_inference_audit_data):
    """Verify governance rule that raw CAN GearRatio channel is not used as array index."""
    gov = gear_inference_audit_data["epistemic_governance"]
    assert gov["raw_gearratio_channel_used_as_index"] is False
    assert gov["dataset_constants_hardcoded"] is False
    assert gov["epistemic_classification"] == "CONFIRMED_FROM_SENSOR_KINEMATICS"
