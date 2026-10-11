"""
tests/test_phase3d_unit_normalization.py
========================================
Verification tests for Phase 3D Change #1: Telemetry Unit Normalization.
Ensures explicit per-channel unit metadata, verifiable conversion factors,
handling of Stanford Golf GTI cm-anomaly, ambiguous unit rejection, and pristine SI preservation.
"""

import numpy as np
import pytest

from suspensionlab.physics.telemetry_dataset import (
    ChannelUnitNormalizer,
    UnitNormalizationStatus,
    ChannelUnitMetadata,
    NormalizedChannelResult,
)


def test_cm_to_m_normalization():
    """Verify explicit cm declaration converts via 0.01 factor to SI meters."""
    raw = np.array([10.0, 25.5, -5.0])
    res = ChannelUnitNormalizer.normalize_channel(
        channel_name="damper_stroke",
        values=raw,
        declared_unit="cm",
        dataset_provenance="bench_rig_test"
    )
    assert res.metadata.status == UnitNormalizationStatus.NORMALIZED
    assert res.metadata.conversion_factor == 0.01
    assert res.metadata.detected_unit == "cm"
    assert res.metadata.normalized_SI_unit == "m"
    np.testing.assert_allclose(res.normalized_SI_values, [0.10, 0.255, -0.05])
    assert "0.01x" in res.metadata.audit_note


def test_mm_to_m_normalization():
    """Verify explicit mm declaration converts via 0.001 factor to SI meters."""
    raw = np.array([50.0, 120.0, -30.0])
    res = ChannelUnitNormalizer.normalize_channel(
        channel_name="ride_height",
        values=raw,
        declared_unit="mm",
        dataset_provenance="motec_export"
    )
    assert res.metadata.status == UnitNormalizationStatus.NORMALIZED
    assert res.metadata.conversion_factor == 0.001
    assert res.metadata.detected_unit == "mm"
    assert res.metadata.normalized_SI_unit == "m"
    np.testing.assert_allclose(res.normalized_SI_values, [0.05, 0.12, -0.03])


def test_pristine_m_to_m_preservation():
    """Verify true SI meter values are preserved with factor 1.0."""
    raw = np.array([0.02, 0.045, -0.015])
    res = ChannelUnitNormalizer.normalize_channel(
        channel_name="damper_pos_fl",
        values=raw,
        declared_unit="m",
        dataset_provenance="adams_cosim"
    )
    assert res.metadata.status == UnitNormalizationStatus.VERIFIED_SI
    assert res.metadata.conversion_factor == 1.0
    assert res.metadata.detected_unit == "m"
    assert res.metadata.normalized_SI_unit == "m"
    np.testing.assert_allclose(res.normalized_SI_values, raw)


def test_stanford_golf_gti_potentiometer_anomaly():
    """Verify Stanford Golf GTI potentiometers labeled '_m' but recorded in cm are correctly normalized."""
    # -3.2 cm to +3.8 cm stroke logged as numbers -3.2 to 3.8
    raw = np.array([-3.2, 0.0, 1.5, 3.8])
    for ch in ["suspFLpos_m", "suspFRpos_m", "suspRLpos_m"]:
        res = ChannelUnitNormalizer.normalize_channel(
            channel_name=ch,
            values=raw,
            declared_unit="m",
            dataset_provenance="stanford_vw_golf_thunderhill_2023_11"
        )
        assert res.metadata.status == UnitNormalizationStatus.NORMALIZED
        assert res.metadata.conversion_factor == 0.01
        assert res.metadata.detected_unit == "cm"
        assert res.metadata.normalized_SI_unit == "m"
        # 3.8 cm -> 0.038 m
        np.testing.assert_allclose(res.normalized_SI_values, [-0.032, 0.0, 0.015, 0.038])
        assert "Stanford Golf GTI potentiometer anomaly" in res.metadata.audit_note


def test_ambiguous_unit_rejection():
    """Verify missing or ambiguous units are flagged as UNIT_AMBIGUOUS without silent guessing."""
    raw = np.array([120.0, 450.0, 890.0])
    res = ChannelUnitNormalizer.normalize_channel(
        channel_name="unknown_adc_signal",
        values=raw,
        declared_unit="counts",
        dataset_provenance="raw_can_frame"
    )
    assert res.metadata.status == UnitNormalizationStatus.UNIT_AMBIGUOUS
    assert res.metadata.conversion_factor == 1.0
    np.testing.assert_allclose(res.normalized_SI_values, raw)
    assert "ambiguous or unverified" in res.metadata.audit_note


def test_already_normalized_si_data():
    """Verify already-normalized SI channels remain pristine."""
    raw = np.array([25.4, 30.1, 28.7])
    res = ChannelUnitNormalizer.normalize_channel(
        channel_name="Vx_mps",
        values=raw,
        declared_unit="m/s",
        dataset_provenance="rtk_gps"
    )
    # Since declared unit is m/s (not cm/mm), and no conflict
    assert res.metadata.conversion_factor == 1.0
    np.testing.assert_allclose(res.normalized_SI_values, raw)
