"""
tests/test_engineering_errors_and_confidence.py
===============================================
Tests for structured engineering failure reports and simulation confidence banner (Findings 66, 67).
"""

import pytest

from suspensionlab.physics.engineering_failure import (
    EngineeringFailureReport,
    create_tire_liftoff_failure,
    create_damper_bottoming_failure,
)
from suspensionlab.physics.confidence_banner import (
    SimulationConfidenceBanner,
    ValidityStatus,
)


def test_structured_engineering_failure_reports():
    # 1. Tire liftoff failure
    fail_tire = create_tire_liftoff_failure(time_s=3.82, corner="FL", travel_mm=42.3)
    assert fail_tire.error_code == "ERR_TIRE_CONTACT_LOSS"
    assert fail_tire.time_s == 3.82
    assert "FL tire lost physical contact" in fail_tire.human_message
    assert len(fail_tire.suggested_actions) >= 2
    
    callout_md = fail_tire.to_markdown_callout()
    assert "Engineering Simulation Failure" in callout_md
    assert "t = 3.82 s" in callout_md

    # 2. Damper bottoming failure
    fail_damper = create_damper_bottoming_failure(time_s=1.45, corner="RR")
    assert fail_damper.error_code == "ERR_DAMPER_BOTTOMING"
    assert "metal-to-metal bump stop" in fail_damper.human_message


def test_simulation_confidence_banner_evaluation():
    # Fully validated setup
    banner_val = SimulationConfidenceBanner.evaluate(
        tire_calibrated=True,
        aero_calibrated=True,
        correlation_pct=94.5,
        kinematics_valid="PASS",
        out_of_envelope_count=0,
    )
    assert banner_val.validity_status == ValidityStatus.VALIDATED
    assert banner_val.confidence_score_pct >= 85.0
    assert not banner_val.operating_range_exceeded

    badge_md = banner_val.to_markdown_badge()
    assert "MODEL VALIDITY: 🟢 VALIDATED" in badge_md
    assert "Tire parameters calibrated:    ✅ YES" in badge_md

    # Conditional setup with uncalibrated aero map & out of envelope points
    banner_cond = SimulationConfidenceBanner.evaluate(
        tire_calibrated=True,
        aero_calibrated=False,
        correlation_pct=82.0,
        kinematics_valid="PASS",
        out_of_envelope_count=2,
    )
    assert banner_cond.validity_status == ValidityStatus.CONDITIONAL
    assert banner_cond.operating_range_exceeded
    assert banner_cond.out_of_envelope_points == 2
