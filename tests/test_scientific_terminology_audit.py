"""
tests/test_scientific_terminology_audit.py
===========================================
Verification suite for scientific terminology corrections across the integrated
SuspensionLab PRO pipeline:

1. Epistemic replacement: 'MODEL_SUPPORTED' replaces 'PROVEN' for isolated simulation changes;
   'EMPIRICALLY_VALIDATED' is reserved for qualifying physical telemetry.
2. Dimensional audit: Exact distinction between kinematic rates (dγ/dz) and parameter sensitivities (∂(dγ/dz)/∂p)
   across camber, toe, roll center, motion ratio, track, ride height, springs, ARBs, dampers, aero, mass, tire friction.
3. Model boundary grounding: Every numerical boundary discloses a REFERENCE, CONFIGURATION-SPECIFIC ASSUMPTION, or USER-CONFIGURED LIMIT.
4. Multi-criteria empirical validation: 7 strict criteria for EMPIRICALLY_VALIDATED.
"""

import pytest
import numpy as np
from suspensionlab.physics.lap_delta import CausalConfidence
from suspensionlab.physics.race_engineer_decision import synthesize_race_engineer_decision
from suspensionlab.physics.lap_sim import solve_lap, ModelAssumptions
from tests.test_lap_sim_phase3 import make_vehicle, make_curved_track
from suspensionlab.physics.kinematics import validate_hardpoints_py, get_kinematics_benchmarks, DEFAULT_HARDPOINTS
from suspensionlab.physics.kinematics_sensitivity import (
    compute_hardpoint_sensitivity,
    METRIC_DIMENSIONAL_SPEC,
    METRIC_UNITS,
)
from suspensionlab.physics.setup_sweep import PARAM_METADATA, SweepParameter
from suspensionlab.physics.handling_analysis import (
    compute_handling_diagram,
    simulate_yaw_response_scenario,
    HandlingParams,
)
from suspensionlab.physics.confidence_banner import (
    SimulationConfidenceBanner,
    ValidityStatus,
    EpistemicTier,
)
from suspensionlab.physics.residual_analysis import (
    compute_residuals,
    ChannelResidualMetrics,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Epistemic Labeling Audit
# ─────────────────────────────────────────────────────────────────────────────

def test_epistemic_tier_model_supported_replaces_proven():
    """Verify that isolated simulation setup differences receive MODEL_SUPPORTED, not PROVEN."""
    assert CausalConfidence.MODEL_SUPPORTED.value == "MODEL_SUPPORTED"
    # Backward compatibility alias works
    assert CausalConfidence.PROVEN.value == "MODEL_SUPPORTED"

    track, dists, curvs = make_curved_track(n_points=120, length_m=1000.0)
    veh_base = make_vehicle(total_mass=800.0, cl_base=1.80)
    # Candidate setup modifies ONLY 1 parameter (total_mass)
    veh_cand = make_vehicle(total_mass=830.0, cl_base=1.80)

    res_a = solve_lap(veh_base, track)
    res_b = solve_lap(veh_cand, track)

    setup_base = {"mass": 800.0, "cl_base": 1.80}
    setup_cand = {"mass": 830.0, "cl_base": 1.80}

    decision = synthesize_race_engineer_decision(
        res_a, res_b,
        setup_baseline=setup_base,
        setup_candidate=setup_cand,
    )

    # Must be MODEL_SUPPORTED for an isolated simulation perturbation, never an ungrounded real-vehicle claim
    assert decision.confidence_rating == "MODEL_SUPPORTED"
    assert "PROVEN" not in decision.confidence_rating or decision.confidence_rating == "MODEL_SUPPORTED"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dimensional Meaning Audit
# ─────────────────────────────────────────────────────────────────────────────

def test_kinematic_vs_parameter_sensitivity_dimensions():
    """Verify mathematical derivative notation and compound units for kinematics."""
    # 1. Camber: rate dγ/dz [°/100mm] vs sensitivity ∂(dγ/dz)/∂p [(°/100mm)/mm]
    spec_camber_gain = METRIC_DIMENSIONAL_SPEC["camber_gain_deg_per_100mm"]
    assert spec_camber_gain["metric_symbol"] == "dγ/dz"
    assert spec_camber_gain["metric_unit"] == "°/100mm"
    assert spec_camber_gain["derivative_symbol"] == "∂(dγ/dz)/∂p"
    assert spec_camber_gain["derivative_unit"] == "(°/100mm)/mm"

    # Static camber: γ₀ [°] vs ∂γ₀/∂p [°/mm]
    spec_camber_static = METRIC_DIMENSIONAL_SPEC["camber_static_deg"]
    assert spec_camber_static["metric_symbol"] == "γ₀"
    assert spec_camber_static["metric_unit"] == "°"
    assert spec_camber_static["derivative_symbol"] == "∂γ₀/∂p"
    assert spec_camber_static["derivative_unit"] == "°/mm"

    # 2. Toe: rate d(toe)/dz [°/100mm] vs sensitivity ∂(d(toe)/dz)/∂p [(°/100mm)/mm]
    spec_toe_gain = METRIC_DIMENSIONAL_SPEC["toe_gain_deg_per_100mm"]
    assert spec_toe_gain["metric_symbol"] == "d(toe)/dz"
    assert spec_toe_gain["derivative_symbol"] == "∂(d(toe)/dz)/∂p"
    assert spec_toe_gain["derivative_unit"] == "(°/100mm)/mm"

    # 3. Roll center: migration rate d(RC_z)/dz [mm/mm] vs sensitivity ∂(d(RC_z)/dz)/∂p [(mm/mm)/mm]
    spec_rc_rate = METRIC_DIMENSIONAL_SPEC["rc_migration_rate"]
    assert spec_rc_rate["metric_symbol"] == "d(RC_z)/dz"
    assert spec_rc_rate["derivative_symbol"] == "∂(d(RC_z)/dz)/∂p"
    assert spec_rc_rate["derivative_unit"] == "(mm/mm)/mm"

    # 4. Motion ratio: MR₀ [-] vs ∂MR/∂p [1/mm]
    spec_mr = METRIC_DIMENSIONAL_SPEC["motion_ratio_static"]
    assert spec_mr["metric_symbol"] == "MR₀"
    assert spec_mr["metric_unit"] == "-"
    assert spec_mr["derivative_symbol"] == "∂MR/∂p"
    assert spec_mr["derivative_unit"] == "1/mm"

    # 5. Track scrub: Δtrack [mm] vs ∂(Δtrack)/∂p [mm/mm]
    spec_track = METRIC_DIMENSIONAL_SPEC["track_change_max_mm"]
    assert spec_track["derivative_unit"] == "mm/mm"


def test_vehicle_setup_parameter_sensitivity_dimensions():
    """Verify setup sweep parameter metadata dimensions for all 12 key vehicle variables."""
    # 6. Ride height: ∂T/∂rh [s/mm]
    assert PARAM_METADATA[SweepParameter.RIDE_HEIGHT_FRONT]["derivative_symbol"] == "∂T/∂rh,f"
    assert PARAM_METADATA[SweepParameter.RIDE_HEIGHT_FRONT]["sensitivity_unit"] == "s/mm"

    # 7. Spring rate: ∂T/∂Ks [s/(N/m)]
    assert PARAM_METADATA[SweepParameter.SPRING_FRONT]["derivative_symbol"] == "∂T/∂Ks,f"
    assert PARAM_METADATA[SweepParameter.SPRING_FRONT]["sensitivity_unit"] == "s/(N/m)"

    # 8. ARB stiffness: ∂T/∂Karb [s/(N/m)]
    assert PARAM_METADATA[SweepParameter.ARB_FRONT]["derivative_symbol"] == "∂T/∂Karb,f"
    assert PARAM_METADATA[SweepParameter.ARB_FRONT]["sensitivity_unit"] == "s/(N/m)"

    # 9. Aero downforce & drag: ∂T/∂CL [s], ∂T/∂CD [s]
    assert PARAM_METADATA[SweepParameter.AERO_CL]["derivative_symbol"] == "∂T/∂CL"
    assert PARAM_METADATA[SweepParameter.AERO_CL]["sensitivity_unit"] == "s"
    assert PARAM_METADATA[SweepParameter.AERO_CD]["derivative_symbol"] == "∂T/∂CD"
    assert PARAM_METADATA[SweepParameter.AERO_CD]["sensitivity_unit"] == "s"

    # 10. Mass: ∂T/∂m [s/kg]
    assert PARAM_METADATA[SweepParameter.MASS]["derivative_symbol"] == "∂T/∂m"
    assert PARAM_METADATA[SweepParameter.MASS]["sensitivity_unit"] == "s/kg"

    # 11. Tire friction: ∂T/∂μ [s/multiplier]
    assert PARAM_METADATA[SweepParameter.TIRE_MU_SCALE]["derivative_symbol"] == "∂T/∂μ"


def test_jacobian_sensitivity_matrix_units_output():
    """Verify compute_hardpoint_sensitivity returns mathematically unambiguous derivative units."""
    res = compute_hardpoint_sensitivity(DEFAULT_HARDPOINTS, step_size_mm=1.0)
    units = res["metric_units"]
    assert units["camber_gain_deg_per_100mm"] == "(°/100mm)/mm"
    assert units["toe_gain_deg_per_100mm"] == "(°/100mm)/mm"
    assert units["rc_migration_rate"] == "(mm/mm)/mm"
    assert units["motion_ratio_static"] == "1/mm"
    assert units["track_change_max_mm"] == "mm/mm"
    assert "metric_dimensional_spec" in res


# ─────────────────────────────────────────────────────────────────────────────
# 3. Model Boundary Grounding Audit
# ─────────────────────────────────────────────────────────────────────────────

def test_model_boundary_statements_have_citations():
    """Verify every numerical model limitation cites literature, config assumption, or user limit."""
    # Kinematics compliance disclosures
    geom_val = validate_hardpoints_py(DEFAULT_HARDPOINTS)
    assumptions = geom_val["model_assumptions"]
    assert "REFERENCE" in assumptions["elastokinematic_deflection"] or "ASSUMPTION" in assumptions["elastokinematic_deflection"]
    assert "Reimpell & Stoll" in assumptions["disclaimer"]
    assert "0.02" in assumptions["disclaimer"] and "0.08" in assumptions["disclaimer"]

    # Benchmark citations
    benchmarks = get_kinematics_benchmarks(DEFAULT_HARDPOINTS)
    bench5 = [b for b in benchmarks if b["id"] == "BENCH-05-TOE-COMPLIANCE"][0]
    assert "REFERENCE / LITERATURE SOURCE" in bench5["reference_source"]

    # Lap sim assumptions
    lap_assumptions = ModelAssumptions()
    not_modeled_text = " ".join(lap_assumptions.not_modeled)
    assert "5%–15%" in lap_assumptions.tire_thermal_assumption
    assert "Pacejka" in lap_assumptions.tire_thermal_assumption
    assert "GPS" in not_modeled_text
    assert "CEP 2.5–5.0 m" in not_modeled_text or "±5–10 m" in not_modeled_text
    assert "USER-CONFIGURED LIMIT" in not_modeled_text
    assert "ISO 15037-1" in not_modeled_text

    # Dynamic handling open-loop disclosures
    handling_params = HandlingParams()
    understeer_res = compute_handling_diagram(handling_params)
    assert "ISO 4138" in understeer_res["model_assumptions"]["driver_model"]

    yaw_res = simulate_yaw_response_scenario(handling_params, duration_s=1.0)
    assert "ISO 7401" in yaw_res["model_assumptions"]["driver_model"]
    assert "150–250 ms" in yaw_res["model_assumptions"]["driver_model"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Multi-Criteria Empirical Validation Audit
# ─────────────────────────────────────────────────────────────────────────────

def test_four_epistemic_tiers_distinction():
    """Verify distinction among SIMULATION_ESTIMATE, MODEL_SUPPORTED, CORRELATED, EMPIRICALLY_VALIDATED."""
    # Tier 1: SIMULATION_ESTIMATE (zero data, default assumptions)
    banner_raw = SimulationConfidenceBanner.evaluate(
        correlation_pct=None,
        tire_calibrated=False,
        aero_calibrated=False,
    )
    assert banner_raw.epistemic_tier == EpistemicTier.SIMULATION_ESTIMATE
    assert banner_raw.confidence_score_pct == 0.0

    # Tier 2: MODEL_SUPPORTED (calibrated physics models, but no telemetry)
    banner_model = SimulationConfidenceBanner.evaluate(
        correlation_pct=None,
        tire_calibrated=True,
        aero_calibrated=True,
        kinematics_valid="PASS",
    )
    assert banner_model.epistemic_tier == EpistemicTier.MODEL_SUPPORTED

    # Tier 3: CORRELATED (telemetry correlation exists, but sample < 100 or holdout < 0.80)
    banner_corr = SimulationConfidenceBanner.evaluate(
        tire_calibrated=True,
        aero_calibrated=True,
        correlation_pct=88.0,
        kinematics_valid="PASS",
        sample_count=60,  # < 100 points
    )
    assert banner_corr.epistemic_tier == EpistemicTier.CORRELATED

    # Tier 4: EMPIRICALLY_VALIDATED (all 7 strict criteria satisfied)
    banner_emp = SimulationConfidenceBanner.evaluate(
        tire_calibrated=True,
        aero_calibrated=True,
        correlation_pct=92.0,
        kinematics_valid="PASS",
        sample_count=250,
        holdout_r2=0.89,
        rmse=0.08,
        mean_bias=0.005,  # |bias| = 0.005 <= 0.15 * 0.08 = 0.012 (passes bias test)
        phase_lag_ms=15.0,  # <= 50 ms
        operating_domain_coverage_pct=75.0,
    )
    assert banner_emp.epistemic_tier == EpistemicTier.EMPIRICALLY_VALIDATED
    assert banner_emp.validity_status in (ValidityStatus.VALIDATED, ValidityStatus.EMPIRICALLY_VALIDATED)
    assert "EMPIRICALLY_VALIDATED" in banner_emp.to_markdown_badge()


def test_empirical_validation_rejects_systematic_bias_violation():
    """Verify that high R² alone does NOT grant EMPIRICALLY_VALIDATED if systematic bias exceeds 15% of RMSE."""
    banner_biased = SimulationConfidenceBanner.evaluate(
        tire_calibrated=True,
        aero_calibrated=True,
        correlation_pct=94.0,  # high R²
        kinematics_valid="PASS",
        sample_count=200,
        holdout_r2=0.90,
        rmse=0.10,
        mean_bias=0.04,  # |bias| = 0.04 > 0.15 * 0.10 = 0.015 (fails bias check!)
        phase_lag_ms=10.0,
    )
    # Must NOT be EMPIRICALLY_VALIDATED due to systematic model-reality divergence
    assert banner_biased.epistemic_tier != EpistemicTier.EMPIRICALLY_VALIDATED
    assert banner_biased.validity_status == ValidityStatus.CONDITIONAL


def test_residual_analysis_channel_epistemic_tiering():
    """Verify compute_channel_residuals evaluates 7 validation criteria on actual series."""
    t = np.linspace(0, 10, 200)
    # High-quality calibrated channel (R² > 0.9, holdout > 0.9, low bias, zero lag)
    y_tel = np.sin(t) + np.random.normal(0, 0.02, len(t))
    y_sim = np.sin(t)

    res = compute_residuals(
        {"vert_g": y_tel.tolist()},
        {"vert_g": y_sim.tolist()},
        sample_rate_hz=20.0,
    )

    channel_metric = res.channels["vert_g"]
    assert channel_metric.correlation_r2 >= 0.85
    assert channel_metric.r2_holdout >= 0.80
    assert channel_metric.epistemic_label == "EMPIRICALLY_VALIDATED"
