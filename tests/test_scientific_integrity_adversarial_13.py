"""
tests/test_scientific_integrity_adversarial_13.py
=================================================
Hostile Adversarial Test Suite for Scientific Integrity (13 Cases)

Validates:
 1. Simulation without telemetry -> UNVALIDATED (0.0% score).
 2. Incomplete / zero-sample telemetry -> UNVALIDATED / DATA_MISSING, never PASS.
 3. Synthetic telemetry dataset -> DEGRADED (0.0% score), never VALIDATED.
 4. Diverged / non-converged simulation -> FAILED / FAILED_NUMERICAL, never COMPLETED.
 5. Pacejka tire model with NaN slip angle -> safe finite bounds, zero NaN propagation.
 6. Sub-physical spring stiffness (k_s < 1000 N/m) -> rejected by parameter validation.
 7. Sub-physical tire stiffness (k_t < 10000 N/m) -> rejected by parameter validation.
 8. Worker handling of NaN/divergence in solver -> status FAILED_NUMERICAL, never COMPLETED.
 9. Engineering report without suspension hardpoints -> kinematic curves NOT_AVAILABLE.
10. Engineering report without aero polar -> aerodynamic downforce NOT_AVAILABLE.
11. G-G diagram without simulated points -> zero fake demo points injected.
12. Digital twin without empirical telemetry -> validation_score_pct is 0.0, no artificial floor.
13. Report cryptographic provenance -> input_hash, result_hash, and artifact_hash strictly bound.
"""

import pytest
import math
import numpy as np
from suspensionlab.physics.confidence_banner import (
    SimulationConfidenceBanner,
    ValidityStatus,
)
from suspensionlab.physics.magic_formula import (
    calc_tire_forces,
    calc_tire_forces_3d,
    PacejkaMF52TireModel,
    TireCoeffs,
)
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile
from suspensionlab.physics.half_car import HalfCarParams
from suspensionlab.physics.full_car import FullCarParams
from suspensionlab.physics.handling_model import HandlingParams
from suspensionlab.physics.digital_twin import (
    create_digital_twin_from_calibration,
    create_reference_digital_twin,
    CalibrationResult,
)
from suspensionlab.backend.services.report_service import (
    calculate_kinematic_curves,
    calculate_downforce_curve,
    calculate_gg_envelope,
    build_canonical_artifact_hash,
)


def _make_full_car_params(**overrides):
    base = {
        "m_s": 1500.0,
        "I_x": 400.0,
        "I_y": 2000.0,
        "m_uf": 40.0,
        "m_ur": 40.0,
        "k_sf": 25000.0,
        "k_sr": 30000.0,
        "c_f": 2000.0,
        "c_r": 2000.0,
        "k_arb_f": 10000.0,
        "k_arb_r": 5000.0,
        "k_tf": 250000.0,
        "k_tr": 250000.0,
        "L": 2.8,
        "a": 1.2,
        "b": 1.6,
        "tw_f": 1.5,
        "tw_r": 1.5,
        "speed_mps": 20.0,
    }
    base.update(overrides)
    return FullCarParams(**base)


def test_case_01_no_telemetry_strictly_unvalidated():
    """Test 1: Simulation evaluated with zero telemetry must return UNVALIDATED and 0.0%."""
    banner = SimulationConfidenceBanner.evaluate(
        correlation_pct=None,
        tire_calibrated=False,
        aero_calibrated=False,
    )
    assert banner.validity_status == ValidityStatus.UNVALIDATED
    assert banner.confidence_score_pct == 0.0
    badge = banner.to_markdown_badge()
    assert "UNVALIDATED" in badge
    assert "0.0%" in badge


def test_case_02_empty_telemetry_never_passes():
    """Test 2: Empty telemetry list must not produce a PASS or positive confidence score."""
    banner = SimulationConfidenceBanner.evaluate(
        correlation_pct=None,
        sample_count=0,
    )
    assert banner.validity_status in (ValidityStatus.UNVALIDATED, ValidityStatus.DATA_MISSING)
    assert banner.confidence_score_pct == 0.0
    assert banner.validity_status != ValidityStatus.PASS
    assert banner.validity_status != ValidityStatus.VALIDATED


def test_case_03_synthetic_telemetry_marked_degraded():
    """Test 3: Synthetic telemetry must strictly yield DEGRADED and 0.0% score, never VALIDATED."""
    banner = SimulationConfidenceBanner.evaluate(
        correlation_pct=95.0,
        sample_count=500,
        is_synthetic=True,
    )
    assert banner.validity_status == ValidityStatus.DEGRADED
    assert banner.confidence_score_pct == 0.0
    assert banner.validity_status != ValidityStatus.VALIDATED
    assert banner.provenance.is_synthetic is True


def test_case_04_diverged_simulation_yields_failed():
    """Test 4: Poor correlation or non-convergence must strictly return FAIL."""
    banner = SimulationConfidenceBanner.evaluate(
        correlation_pct=30.0,
        sample_count=100,
    )
    assert banner.validity_status in (ValidityStatus.FAIL, ValidityStatus.FAILED)
    assert banner.confidence_score_pct == 0.0


def test_case_05_pacejka_nan_slip_angle_finite_guard():
    """Test 5: NaN slip angle into Pacejka must be safely handled without NaN propagation into Mz."""
    coeffs = TireCoeffs()
    model = PacejkaMF52TireModel(coeffs)

    # 1. Direct function call with NaN
    fx, fy = calc_tire_forces(Fz=4000.0, alpha_rad=float("nan"), kappa=0.0, coeffs=coeffs)
    assert not math.isnan(fx)
    assert not math.isnan(fy)
    assert fx == 0.0 and fy == 0.0

    # 2. 3D forces call with NaN
    fx_3d, fy_3d, mz_3d = calc_tire_forces_3d(Fz=4000.0, alpha_rad=float("nan"), kappa=0.0, coeffs=coeffs)
    assert not math.isnan(fx_3d)
    assert not math.isnan(fy_3d)
    assert not math.isnan(mz_3d)
    assert mz_3d == 0.0

    # 3. Model evaluate check with NaN
    eval_res = model.evaluate(Fz=4000.0, alpha_rad=float("nan"), kappa=0.0)
    assert not math.isnan(eval_res.Fx)
    assert not math.isnan(eval_res.Fy)
    assert not math.isnan(eval_res.Mz)
    assert eval_res.is_valid is False


def test_case_06_spring_stiffness_minimum_bound():
    """Test 6: Spring stiffness below 1,000 N/m must be rejected across quarter, half, full, handling models."""
    with pytest.raises(ValueError, match="at least 1,000 N/m"):
        QuarterCarParams(k_s=500.0)

    with pytest.raises(ValueError, match="at least 1,000 N/m"):
        QuarterCarParams(k_s=0.0)

    with pytest.raises(ValueError, match="at least 1,000 N/m"):
        HalfCarParams(k_sf=800.0)

    with pytest.raises(ValueError, match="at least 1,000 N/m"):
        _make_full_car_params(k_sf=999.0)

    with pytest.raises(ValueError, match="at least 1000.0 N/m"):
        HandlingParams(K_spring_f=500.0)


def test_case_07_tire_stiffness_minimum_bound():
    """Test 7: Tire stiffness below 10,000 N/m must be rejected to prevent carcass collapse."""
    with pytest.raises(ValueError, match="at least 10,000 N/m"):
        QuarterCarParams(k_t=5000.0)

    with pytest.raises(ValueError, match="at least 10,000 N/m"):
        QuarterCarParams(k_t=-100.0)

    with pytest.raises(ValueError, match="at least 10,000 N/m"):
        HalfCarParams(k_tf=2000.0)

    with pytest.raises(ValueError, match="at least 10,000 N/m"):
        _make_full_car_params(k_tf=9999.0)


def test_case_08_worker_nan_detection_failed_numerical():
    """Test 8: Worker post-process nan/inf check correctly identifies numerical corruption."""
    from suspensionlab.backend.workers.unified_worker import _check_has_nan_or_inf

    clean_dict = {"time": [0.0, 0.1, 0.2], "accel": [0.0, 1.2, 0.8]}
    assert _check_has_nan_or_inf(clean_dict) is False

    corrupted_dict = {"time": [0.0, 0.1, 0.2], "accel": [0.0, float("nan"), 0.8]}
    assert _check_has_nan_or_inf(corrupted_dict) is True

    corrupted_inf = {"states": {"velocity": [10.0, float("inf")]}}
    assert _check_has_nan_or_inf(corrupted_inf) is True


def test_case_09_report_kinematics_not_available_without_geometry():
    """Test 9: Kinematics curve generator must return NOT_AVAILABLE when hardpoint geometry is absent."""
    res = calculate_kinematic_curves(hardpoints=None, lut_dict=None)
    assert res["status"] == "NOT_AVAILABLE"
    assert "No suspension kinematics geometry model" in res["reason"]
    assert len(res["heave_travel_mm"]) == 0
    assert len(res["camber_deg"]) == 0


def test_case_10_report_downforce_not_available_without_polar():
    """Test 10: Downforce curve generator must return NOT_AVAILABLE when no aero polar is provided."""
    res = calculate_downforce_curve(cl_base=None, cd_base=None, frontal_area=None)
    assert res["status"] == "NOT_AVAILABLE"
    assert "No aerodynamic polar configured" in res["reason"]
    assert len(res["downforce_n"]) == 0


def test_case_11_gg_envelope_no_synthetic_demo_points():
    """Test 11: G-G envelope must not inject simulated demo points when simulation points are absent."""
    res = calculate_gg_envelope(mu_tire=1.5, sim_lat=None, sim_long=None)
    assert len(res["sim_lat_g"]) == 0
    assert len(res["sim_long_g"]) == 0
    assert len(res["boundary_lat_g"]) == 24


def test_case_12_digital_twin_unvalidated_without_correlation():
    """Test 12: Digital twin created without calibration holdout data must have validation_score_pct = 0.0."""
    class EmptyCalibrationReport:
        holdout_r2 = None
        train_r2 = None
        train_rmse = 0.05
        holdout_rmse = 0.06
        residual_reduction_pct = 0.0
        total_telemetry_samples = 0

    twin = create_digital_twin_from_calibration(EmptyCalibrationReport(), twin_id="TEST-TWIN")
    assert twin.validation_score_pct == 0.0
    assert twin.calibrated_samples_count == 0


def test_case_13_artifact_hash_provenance_binding():
    """Test 13: Canonical artifact hash must change whenever input or result hashes change."""
    hash1 = build_canonical_artifact_hash(
        run_id="RUN-000001",
        vehicle_ref="VEHICLE-01",
        setup_ref="SETUP-A",
        tire_ref="TIRE-01",
        track_ref="TRACK-01",
        physics_version="2.0.0",
        solver_version="scipy-1.11",
        software_build="build-abc",
        input_hash="hash_input_1",
        result_hash="hash_result_1",
        metrics={"RMS": "1.2 m/s²"},
        validation_status="UNVALIDATED",
    )

    # Change result hash
    hash2 = build_canonical_artifact_hash(
        run_id="RUN-000001",
        vehicle_ref="VEHICLE-01",
        setup_ref="SETUP-A",
        tire_ref="TIRE-01",
        track_ref="TRACK-01",
        physics_version="2.0.0",
        solver_version="scipy-1.11",
        software_build="build-abc",
        input_hash="hash_input_1",
        result_hash="hash_result_2",
        metrics={"RMS": "1.2 m/s²"},
        validation_status="UNVALIDATED",
    )

    assert hash1 != hash2
    assert len(hash1) == 64
    assert len(hash2) == 64
