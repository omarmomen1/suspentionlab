"""tests/test_phase3j_parameter_identification.py
=================================================
Hostile & Scientific Verification Suite for Phase 3J:
Physical Parameter Identification & Observability.

Requirements:
1. Parameter Registry:
   - 11 physical parameter families already represented in models
   - No invented parameters
2. Observability Analysis:
   - Sensitivity matrix, parameter correlation, excitation coverage, condition number, rank
   - Classification: IDENTIFIABLE, PARTIALLY_IDENTIFIABLE, UNIDENTIFIABLE
3. Refuse impossible calibration:
   - If data cannot identify a parameter, return UNIDENTIFIABLE with no fitted value
4. Calibration dataset isolation:
   - Cryptographic separation (SHA-256) of calibration and holdout data
   - Firewall prevents leakage
5. Optimization:
   - Robust derivative-free optimization (Powell / Nelder-Mead)
6. Regularization:
   - Prevents physically meaningless parameter combinations
7. Multi-start calibration:
   - Demonstrates convergence to parameter region vs local minima
8. Sensitivity analysis:
   - Local sensitivity, parameter correlation, uncertainty, channel elasticities
9. Blind holdout:
   - Parameters frozen, untouched holdout data, zero retuning
10. Required outputs & hostile tests:
   - Flat signal -> UNIDENTIFIABLE
   - Insufficient excitation -> UNIDENTIFIABLE
   - Perfectly correlated parameters -> Collinearity detected
   - Noisy telemetry -> Uncertainty expansion
   - Optimizer failure -> Handled gracefully
   - Local minima -> Multi-start dispersion detected
   - Parameter outside bounds -> Strictly guarded
   - Missing target channel -> Strict rejection
   - Calibration leakage -> CalibrationLeakageError
   - Overfitting -> Refuses "validated" verdict
12. Never report "validated" unless independent physical holdout criteria are actually satisfied!
"""

import math
import numpy as np
import pytest

from suspensionlab.calibration.registry import (
    ParameterFamily,
    ParameterDefinition,
    ParameterRegistry,
    GaussianPrior,
    UniformPrior,
    ValidityDomain,
    STANDARD_PARAMETER_REGISTRY,
)
from suspensionlab.calibration.isolation import (
    CalibrationLeakageError,
    CalibrationSplitType,
    CryptographicDatasetIsolation,
)
from suspensionlab.calibration.regularization import (
    PhysicalInvariants,
    PhysicalRegularizer,
)
from suspensionlab.calibration.observability import (
    ObservabilityAnalyzer,
    ObservabilityStatus,
)
from suspensionlab.calibration.optimizer import (
    DerivativeFreeSolver,
    MultiStartConvergenceStatus,
    MultiStartOptimizer,
)
from suspensionlab.calibration.sensitivity import SensitivityAnalyzer
from suspensionlab.calibration.engine import (
    IdentificationConfig,
    ParameterIdentificationEngine,
)
from suspensionlab.calibration.report import PhysicalCalibrationReport


# ─────────────────────────────────────────────────────────────────────────────
# 1. Parameter Registry & Physical Integrity
# ─────────────────────────────────────────────────────────────────────────────

def test_parameter_registry_families_and_completeness():
    """Verify registry contains all 11 potential parameter families already represented in the model."""
    reg = STANDARD_PARAMETER_REGISTRY
    assert len(reg.list_names()) >= 20

    families = {p.family for p in reg.list_all()}
    expected_families = {
        ParameterFamily.TIRE_STIFFNESS,
        ParameterFamily.TIRE_LOAD_SENSITIVITY,
        ParameterFamily.CAMBER_SENSITIVITY,
        ParameterFamily.AERO_COEFFICIENTS,
        ParameterFamily.AERO_BALANCE,
        ParameterFamily.DRIVETRAIN_EFFICIENCY,
        ParameterFamily.ROLLING_RESISTANCE,
        ParameterFamily.SUSPENSION_STIFFNESS,
        ParameterFamily.DAMPING,
        ParameterFamily.MASS_INERTIA,
        ParameterFamily.POWERTRAIN,
    }
    assert expected_families.issubset(families)

    for p in reg.list_all():
        assert p.name != ""
        assert p.physical_meaning != ""
        assert p.units != ""
        assert p.bounds[0] < p.bounds[1]
        assert p.bounds[0] <= p.nominal_value <= p.bounds[1]
        assert p.prior is not None
        assert p.source != ""
        assert len(p.model_dependency) >= 1
        assert p.validity_domain is not None
        assert p.validity_domain.contains(p.nominal_value)


def test_parameter_registry_disallows_invented_parameters():
    """Verify registry rejects unregistered or invented parameters."""
    engine = ParameterIdentificationEngine()
    t = np.linspace(0, 3, 100)
    telem = {"vert_g": np.sin(t), "time": t}

    cfg = IdentificationConfig(
        candidate_parameters=["invented_magic_curve_fit_param"],
        target_channels=["vert_g"],
    )

    with pytest.raises(KeyError, match="not in the parameter registry"):
        engine.identify_parameters(
            telemetry=telem,
            config=cfg,
            model_evaluator=lambda p, d: {"vert_g": np.zeros(len(d["time"]))},
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cryptographic Dataset Isolation & Sequestration Firewall
# ─────────────────────────────────────────────────────────────────────────────

def test_cryptographic_isolation_sealing_and_leakage():
    """Requirement 4 & 11: Calibration data and holdout data must be cryptographically separated.

    Attempting to access holdout data during calibration raises CalibrationLeakageError.
    """
    t = np.linspace(0, 10.0, 500)
    data = {"vert_g": 0.5 * np.sin(t), "time": t}

    isolation = CryptographicDatasetIsolation(guard_band_s=0.50)
    cal_part, hold_part = isolation.partition_dataset(data, holdout_ratio=0.25)

    assert cal_part.is_sealed is False
    assert hold_part.is_sealed is True
    assert len(cal_part.provenance_hash) == 64
    assert len(hold_part.provenance_hash) == 64
    assert cal_part.provenance_hash != hold_part.provenance_hash

    # Calibration access succeeds
    cal_data = isolation.get_calibration_data(caller="optimizer")
    assert len(cal_data["time"]) > 0

    # Leakage attempt without token MUST be blocked and raise CalibrationLeakageError
    with pytest.raises(CalibrationLeakageError, match="CALIBRATION FIREWALL LEAKAGE DETECTED"):
        isolation.get_holdout_data(token=None, caller="optimizer")

    with pytest.raises(CalibrationLeakageError, match="CALIBRATION FIREWALL LEAKAGE DETECTED"):
        isolation.get_holdout_data(token="INVALID_TOKEN_12345", caller="unauthorized_subsystem")

    # Access with authoritative token succeeds
    hold_data = isolation.get_holdout_data(token=isolation.unlock_token, caller="holdout_evaluator")
    assert len(hold_data["time"]) > 0
    assert hold_part.is_sealed is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Hostile Tests: Observability & Calibration Refusal
# ─────────────────────────────────────────────────────────────────────────────

def test_hostile_flat_signal_refused_unidentifiable():
    """Requirement 3 & 11: Flat signal with zero variance must be declared UNIDENTIFIABLE.

    No fitted value may be returned.
    """
    t = np.linspace(0, 5.0, 200)
    # Zero dynamic excitation flatline
    flat_data = {"vert_g": np.zeros(200), "time": t}

    engine = ParameterIdentificationEngine()
    cfg = IdentificationConfig(
        candidate_parameters=["spring_rate_front", "damper_bump_front"],
        target_channels=["vert_g"],
    )

    # Toy simulation evaluator
    def evaluator(params, telem_slice):
        k = params.get("spring_rate_front", 32000.0)
        c = params.get("damper_bump_front", 2200.0)
        tt = telem_slice["time"]
        return {"vert_g": 0.01 * np.sin(math.sqrt(k / 300.0) * tt)}

    report = engine.identify_parameters(flat_data, cfg, evaluator)

    assert isinstance(report, PhysicalCalibrationReport)
    assert report.validity_classification == "UNIDENTIFIABLE"
    assert report.is_validated is False
    assert len(report.unidentifiable_parameters) == 2

    for p_name in ["spring_rate_front", "damper_bump_front"]:
        p_res = report.fitted_parameters[p_name]
        # Must refuse calibration and retain nominal value
        assert p_res.is_fitted is False
        assert p_res.observability_status == ObservabilityStatus.UNIDENTIFIABLE.value
        assert p_res.calibrated_value == p_res.nominal_value
        assert p_res.delta_pct == 0.0
        assert p_res.rejection_reason is not None


def test_hostile_insufficient_excitation_refusal():
    """Requirement 11: Insufficient excitation in observable channels must refuse calibration for those parameters.

    In straight-line telemetry (zero lateral acceleration), cornering stiffness is UNIDENTIFIABLE.
    """
    t = np.linspace(0, 5.0, 200)
    # Active vertical excitation, but ZERO lateral excitation
    telem = {
        "vert_g": 1.2 * np.sin(2 * np.pi * 1.5 * t),
        "ay": np.zeros(200),
        "time": t,
    }

    engine = ParameterIdentificationEngine()
    cfg = IdentificationConfig(
        candidate_parameters=["spring_rate_front", "cornering_stiff_front"],
        target_channels=["vert_g", "ay"],
    )

    def evaluator(params, telem_slice):
        k = params.get("spring_rate_front", 32000.0)
        c_alpha = params.get("cornering_stiff_front", 85000.0)
        tt = telem_slice["time"]
        return {
            "vert_g": 1.2 * np.sin(math.sqrt(k / 360.0) * tt),
            "ay": np.zeros(len(tt)),
        }

    report = engine.identify_parameters(telem, cfg, evaluator)

    # cornering_stiff_front had zero lateral excitation: must be UNIDENTIFIABLE
    cornering_p = report.fitted_parameters["cornering_stiff_front"]
    assert cornering_p.observability_status == ObservabilityStatus.UNIDENTIFIABLE.value
    assert cornering_p.is_fitted is False
    assert cornering_p.calibrated_value == cornering_p.nominal_value
    assert "Insufficient excitation" in cornering_p.rejection_reason


def test_hostile_collinear_parameters_detection():
    """Requirement 11: Perfectly or highly correlated parameters must be detected in Fisher correlation matrix.

    Collinear parameters must not be falsely reported as independently identifiable.
    """
    reg = STANDARD_PARAMETER_REGISTRY
    analyzer = ObservabilityAnalyzer(registry=reg, collinearity_threshold=0.90)

    t = np.linspace(0, 4.0, 200)
    data = {"vert_g": 1.5 * np.sin(2 * np.pi * 1.5 * t), "time": t}

    # Model where p1 and p2 have identical / linearly dependent effects: y = (p1 * p2) * sin(t)
    def collinear_evaluator(param_dict):
        p1 = param_dict.get("spring_rate_front", 32000.0)
        p2 = param_dict.get("k_tire_front", 210000.0)
        # Linear product -> Jacobian columns are parallel
        lumped = (p1 / 32000.0) + (p2 / 210000.0)
        return {"vert_g": lumped * np.sin(2 * np.pi * 1.5 * t)}

    obs_summary = analyzer.analyze_observability(
        data=data,
        candidate_params=["spring_rate_front", "k_tire_front"],
        evaluator_fn=collinear_evaluator,
    )

    corr_matrix = np.array(obs_summary.correlation_matrix)
    # Correlation between the two parameters must be near 1.0 (or -1.0)
    off_diag = abs(corr_matrix[0, 1])
    assert off_diag > 0.90, f"Expected high collinearity, got {off_diag}"

    p1_rec = obs_summary.records["spring_rate_front"]
    assert p1_rec.status in [ObservabilityStatus.PARTIALLY_IDENTIFIABLE, ObservabilityStatus.UNIDENTIFIABLE]
    assert p1_rec.max_correlation_with == "k_tire_front"


def test_hostile_noisy_telemetry_uncertainty_expansion():
    """Requirement 11 & 8: High noise increases residual variance and expands confidence intervals."""
    analyzer = SensitivityAnalyzer(registry=STANDARD_PARAMETER_REGISTRY)

    t = np.linspace(0, 3.0, 100)
    def toy_eval(p_dict):
        k = p_dict["spring_rate_front"]
        return {"vert_g": 0.5 * (k / 32000.0) * np.sin(2 * np.pi * 1.5 * t)}

    # Low noise case
    res_low = analyzer.analyze(
        fitted_params={"spring_rate_front": 32000.0},
        evaluator_fn=toy_eval,
        residual_variance=0.001,
    )
    se_low = res_low.uncertainties["spring_rate_front"].std_error

    # High noise case
    res_high = analyzer.analyze(
        fitted_params={"spring_rate_front": 32000.0},
        evaluator_fn=toy_eval,
        residual_variance=0.100,
    )
    se_high = res_high.uncertainties["spring_rate_front"].std_error

    # Standard error must scale with sqrt(residual variance)
    assert se_high > 5.0 * se_low


def test_hostile_optimizer_failure_semantics():
    """Requirement 11: Solver failure or non-integrable model raises handled failure without crash or hallucination."""
    engine = ParameterIdentificationEngine()
    t = np.linspace(0, 3.0, 100)
    telem = {"vert_g": np.sin(t), "time": t}

    cfg = IdentificationConfig(
        candidate_parameters=["spring_rate_front"],
        target_channels=["vert_g"],
        max_iter=5,
    )

    # Simulator that blows up / returns NaN
    def failing_evaluator(params, telem_slice):
        raise FloatingPointError("Numerical singularity in adaptive ODE solver")

    # Must handle gracefully without unhandled crash
    report = engine.identify_parameters(telem, cfg, failing_evaluator)
    assert isinstance(report, PhysicalCalibrationReport)
    assert report.is_validated is False


def test_hostile_parameter_outside_bounds_prevented():
    """Requirement 6 & 11: Parameters outside bounds or physically impossible combinations are rejected by regularizer."""
    regularizer = PhysicalRegularizer(registry=STANDARD_PARAMETER_REGISTRY)

    # Test 1: Out of bounds spring rate
    pen_oob = regularizer.evaluate({"spring_rate_front": 5000.0})  # min bound is 15000.0
    assert not pen_oob.is_physically_admissible
    assert pen_oob.barrier_penalty > 0.0
    assert any("below lower bound" in v for v in pen_oob.violations)

    # Test 2: Unphysical damping ratio (c=50 Ns/m with k=32000 N/m -> zeta < 0.12)
    pen_underdamped = regularizer.evaluate({
        "spring_rate_front": 32000.0,
        "damper_bump_front": 100.0,
        "sprung_mass": 1320.0,
    })
    assert any("Front damping ratio" in v for v in pen_underdamped.violations)

    # Test 3: Negative tire load degressivity
    pen_degress = regularizer.evaluate({"tire_load_degressivity": -0.05})
    assert any("must be positive" in v for v in pen_degress.violations)


def test_hostile_missing_target_channel_rejected():
    """Requirement 11: Missing target channel strictly raises ValueError."""
    engine = ParameterIdentificationEngine()
    t = np.linspace(0, 3.0, 100)
    telem = {"vert_g": np.sin(t), "time": t}

    cfg = IdentificationConfig(
        candidate_parameters=["spring_rate_front"],
        target_channels=["nonexistent_pressure_channel"],
    )

    with pytest.raises(ValueError, match="is missing from telemetry dataset"):
        engine.identify_parameters(
            telemetry=telem,
            config=cfg,
            model_evaluator=lambda p, d: {"vert_g": np.zeros(len(d["time"]))},
        )


def test_hostile_overfitting_refuses_validated_verdict():
    """Requirement 12: Never report 'validated' unless independent physical holdout criteria are satisfied.

    If model fits train but fails holdout, report MUST refuse validation.
    """
    t = np.linspace(0, 8.0, 400)
    # Sine wave
    y = np.sin(2 * np.pi * 1.5 * t)
    telem = {"vert_g": y, "time": t}

    engine = ParameterIdentificationEngine()
    cfg = IdentificationConfig(
        candidate_parameters=["spring_rate_front"],
        target_channels=["vert_g"],
        holdout_ratio=0.30,
        holdout_r2_threshold=0.50,
    )

    # Model that memorizes / matches training slice but produces corrupted garbage on holdout
    def overfit_evaluator(params, telem_slice):
        tt = telem_slice["time"]
        # If this is calibration slice (first 70%), good fit
        if tt[0] < 4.0:
            return {"vert_g": np.sin(2 * np.pi * 1.5 * tt)}
        else:
            # On holdout: massive mismatch / phase inversion
            return {"vert_g": -5.0 * np.sin(2 * np.pi * 7.5 * tt)}

    report = engine.identify_parameters(telem, cfg, overfit_evaluator)

    # Generalization gap must be flagged and validated verdict MUST be False
    assert report.is_validated is False
    assert report.validity_classification in ["OVERFIT", "UNIDENTIFIABLE", "EXTRAPOLATED"]
    assert report.validity_classification != "VALIDATED"
    assert report.validity_classification != "MODEL_SUPPORTED"
    assert report.holdout_performance.criteria_satisfied is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Multi-Start Optimization & Convergence
# ─────────────────────────────────────────────────────────────────────────────

def test_multi_start_local_minima_detection():
    """Requirement 7 & 11: Multi-start optimizer detects local minima dispersion."""
    reg = STANDARD_PARAMETER_REGISTRY
    regularizer = PhysicalRegularizer(registry=reg)

    optimizer = MultiStartOptimizer(
        registry=reg,
        regularizer=regularizer,
        solver=DerivativeFreeSolver.NELDER_MEAD,
        num_starts=3,
        dispersion_threshold_pct=10.0,
    )

    # Objective with two distinct wells: one near 25000, one near 55000
    def multi_modal_obj(p_dict):
        k = p_dict["spring_rate_front"]
        well1 = (k - 25000.0) ** 2
        well2 = (k - 55000.0) ** 2
        # Smooth double well
        return min(well1, well2)

    res = optimizer.optimize(["spring_rate_front"], multi_modal_obj)
    assert res.num_starts == 3
    # Solutions from different starting points land in different wells -> dispersion > 10%
    assert res.dispersion_pct > 10.0
    assert res.status == MultiStartConvergenceStatus.LOCAL_MINIMA_DETECTED


def test_multi_start_global_cluster_convergence():
    """Requirement 7: Unimodal physical problem converges to the same parameter region."""
    reg = STANDARD_PARAMETER_REGISTRY
    regularizer = PhysicalRegularizer(registry=reg)

    optimizer = MultiStartOptimizer(
        registry=reg,
        regularizer=regularizer,
        num_starts=3,
        dispersion_threshold_pct=15.0,
        max_iter=30,
    )

    # True parameter is 38000.0 N/m
    def unimodal_obj(p_dict):
        k = p_dict["spring_rate_front"]
        return ((k - 38000.0) / 38000.0) ** 2

    res = optimizer.optimize(["spring_rate_front"], unimodal_obj)
    assert res.status == MultiStartConvergenceStatus.CONVERGED_GLOBAL_CLUSTER
    assert abs(res.best_parameters["spring_rate_front"] - 38000.0) < 1500.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. End-to-End Successful Identification on Quarter-Car Model
# ─────────────────────────────────────────────────────────────────────────────

def test_end_to_end_quarter_car_identification_and_holdout():
    """Full pipeline verification: identifiable parameters converge, reduce error, and satisfy holdout."""
    t = np.linspace(0, 6.0, 300)
    true_k = 36000.0
    true_c = 2600.0

    # Synthetic authentic response
    omega = math.sqrt(true_k / 360.0)
    vert_g_true = 0.8 * np.sin(omega * t) * np.exp(-0.05 * t)
    telem = {"vert_g": vert_g_true, "time": t}

    engine = ParameterIdentificationEngine()
    # Perturb initial guess by -25%
    cfg = IdentificationConfig(
        candidate_parameters=["spring_rate_front", "damper_bump_front"],
        target_channels=["vert_g"],
        nominal_overrides={"spring_rate_front": 27000.0, "damper_bump_front": 2000.0},
        holdout_ratio=0.25,
        max_iter=25,
        holdout_r2_threshold=0.40,
    )

    def physical_evaluator(p_dict, slice_data):
        k = p_dict.get("spring_rate_front", 27000.0)
        c = p_dict.get("damper_bump_front", 2000.0)
        tt = slice_data["time"]
        w = math.sqrt(k / 360.0)
        decay = c / (2.0 * math.sqrt(k * 360.0)) * 0.1
        sim_vg = 0.8 * np.sin(w * tt) * np.exp(-decay * tt)
        return {"vert_g": sim_vg}

    report = engine.identify_parameters(telem, cfg, physical_evaluator)

    assert isinstance(report, PhysicalCalibrationReport)
    assert report.residual_changes.rmse_reduction_pct >= 0.0
    assert report.fitted_parameters["spring_rate_front"].is_fitted is True
    assert report.fitted_parameters["damper_bump_front"].is_fitted is True

    # Calibrated values moved towards true parameters
    cal_k = report.fitted_parameters["spring_rate_front"].calibrated_value
    assert cal_k > 27000.0, f"Expected spring rate to increase towards true 36000, got {cal_k}"

    # Holdout performance verified
    assert report.holdout_performance.holdout_r2 > 0.40
    assert report.is_validated is True
    assert report.validity_classification in ["MODEL_SUPPORTED", "CORRELATED"]
