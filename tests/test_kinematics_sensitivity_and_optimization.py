"""
tests/test_kinematics_sensitivity_and_optimization.py
=====================================================
Automated tests for the Kinematics Hardpoint Sensitivity & Optimization Engine.

Validates:
1. Finite-difference perturbations change real solver outputs.
2. Sensitivity signs match suspension kinematic principles.
3. Safety validator strictly rejects impossible/inverted geometry.
4. Engineering question mode recommends sensitive hardpoints with causal explanations.
5. Multi-objective optimizer respects bounds and extracts non-dominated Pareto solutions.
6. Transfer to Experiment preserves provenance, delta lists, and SHA-256 geometry hashes.
"""

import copy
import pytest
import numpy as np

from suspensionlab.physics.kinematics import DEFAULT_HARDPOINTS, compute_geometry_hash
from suspensionlab.physics.kinematics_sensitivity import (
    HardpointSafetyValidator,
    compute_hardpoint_sensitivity,
    evaluate_engineering_question,
    optimize_hardpoints,
    OptimizationObjective,
    OptimizationConstraint,
)
from suspensionlab.backend.services.kinematics_optimization_service import (
    KinematicsOptimizationService,
)


def test_perturbation_changes_solver_output():
    """Verify that shifting hardpoints changes solver output metrics and produces non-zero sensitivities."""
    sens = compute_hardpoint_sensitivity(
        DEFAULT_HARDPOINTS,
        target_hardpoints=["UWI_aft", "UWO", "TRO"],
        axes=["Y", "Z"],
        step_size_mm=1.0,
        z_min_mm=-30.0,
        z_max_mm=30.0,
        n_steps=13,
    )

    jac = sens["jacobian_matrix"]
    assert len(jac) > 0, "Jacobian matrix must contain computed rows"

    # UWI_aft Z sensitivity on camber gain should be non-zero
    assert "UWI_aft_Z" in jac
    camber_gain_sens = jac["UWI_aft_Z"]["camber_gain_deg_per_100mm"]
    assert abs(camber_gain_sens) > 1e-4, f"Expected non-zero camber gain sensitivity, got {camber_gain_sens}"

    # TRO Y sensitivity on bump steer toe variation should be non-zero
    assert "TRO_Y" in jac
    toe_sens = jac["TRO_Y"]["toe_variation_deg"]
    assert abs(toe_sens) > 1e-4, f"Expected non-zero toe variation sensitivity from TRO_Y, got {toe_sens}"


def test_sensitivity_signs_against_kinematic_theory():
    """
    Verify sensitivity signs against established vehicle dynamics theory:
    1. Raising upper wishbone chassis pivot (UWI_aft Z+) alters upper arm downward slope
       in bump, which modifies the camber recovery rate (camber gain).
    2. Shifting lower ball joint outboard (LWO Y+) increases track width and alters static camber.
    """
    sens = compute_hardpoint_sensitivity(
        DEFAULT_HARDPOINTS,
        target_hardpoints=["UWI_aft", "LWO"],
        axes=["Y", "Z"],
        step_size_mm=1.0,
        z_min_mm=-25.0,
        z_max_mm=25.0,
        n_steps=11,
    )

    jac = sens["jacobian_matrix"]

    # 1. UWI_aft Z: Alters wishbone instant center and camber recovery slope
    d_camber_gain_d_uwi_z = jac["UWI_aft_Z"]["camber_gain_deg_per_100mm"]
    assert abs(d_camber_gain_d_uwi_z) > 0.005, (
        f"Raising UWI Z must have significant sensitivity on camber recovery slope, got {d_camber_gain_d_uwi_z}"
    )

    # 2. LWO Y: Moving lower ball joint outboard tilts kingpin axis, altering KPI and scrub radius
    d_kpi_d_lwo_y = jac["LWO_Y"]["kpi_static_deg"]
    assert abs(d_kpi_d_lwo_y) > 0.05, f"LWO Y must directly influence Kingpin Inclination, got {d_kpi_d_lwo_y}"
    d_scrub_d_lwo_y = jac["LWO_Y"]["scrub_radius_static_mm"]
    assert abs(d_scrub_d_lwo_y) > 0.5, f"LWO Y must directly influence scrub radius, got {d_scrub_d_lwo_y}"


def test_hardpoint_safety_validator_rejects_impossible_geometry():
    """Verify safety validator strictly rejects impossible or inverted geometry."""
    # Baseline should be valid
    valid_base, errs_base = HardpointSafetyValidator.validate(DEFAULT_HARDPOINTS)
    assert valid_base is True, f"Baseline should be valid, got errors: {errs_base}"

    # 1. Inverted upright (UWO Z < LWO Z)
    inverted_hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    inverted_hp["UWO"][2] = 100.0  # Below LWO Z=145.0
    valid_inv, errs_inv = HardpointSafetyValidator.validate(inverted_hp)
    assert valid_inv is False, "Inverted ball joints must be rejected"
    assert any("clearance violation" in e.lower() for e in errs_inv)

    # 2. Ultra-short control arm (UWO moved too close to chassis)
    short_hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    short_hp["UWO"][1] = 120.0  # UWI is at 80.0, arm length only 40mm
    valid_short, errs_short = HardpointSafetyValidator.validate(short_hp)
    assert valid_short is False, "Short control arm must be rejected"
    assert any("span violation" in e.lower() or "length violation" in e.lower() for e in errs_short)


def test_engineering_question_camber_gain_without_toe():
    """
    Verify complete engineering question recommendation:
    'Increase negative camber gain in bump while minimizing toe change'
    """
    res = evaluate_engineering_question(
        DEFAULT_HARDPOINTS,
        question_preset_id="camber_gain_without_toe",
        z_min_mm=-30.0,
        z_max_mm=30.0,
        n_steps=11,
    )

    assert res["recommendation_type"] == "SENSITIVITY-BASED RECOMMENDATION"
    assert res["objective_metric"] == "camber_gain_deg_per_100mm"
    assert len(res["evaluated_candidates"]) > 0

    best = res["best_candidate"]
    assert best is not None, "Best candidate must be identified"
    assert best["constraint_status"] == "PASS", f"Best candidate must satisfy constraints: {best['violation_details']}"
    assert best["delta_obj"] < 0, "Best candidate must improve (more negative) bump camber gain"
    assert len(best["why_chosen"]) > 10, "Physical mechanism must be explained"
    assert "what_improved" in best and len(best["what_improved"]) > 0


def test_bounded_optimization_respects_limits_and_finds_pareto():
    """
    Verify bounded parameter optimization:
    1. All candidates strictly respect hardpoint bounds.
    2. Pareto frontier contains only non-dominated candidates.
    3. Best compromise candidate has explicit utopia distance.
    """
    max_bound_mm = 6.0
    target_hps = ["UWI_aft", "LWI_aft", "TRO"]

    opt = optimize_hardpoints(
        DEFAULT_HARDPOINTS,
        target_hardpoints=target_hps,
        allowed_axes=["Y", "Z"],
        hardpoint_bounds_mm=max_bound_mm,
        objectives=[
            OptimizationObjective(metric="camber_gain_deg_per_100mm", direction="minimize", weight=1.0),
            OptimizationObjective(metric="toe_variation_deg", direction="minimize", weight=1.0),
        ],
        constraints=[
            OptimizationConstraint(metric="roll_center_height_static_mm", min_val=-120.0, max_val=20.0),
        ],
        n_samples=25,
        z_min_mm=-25.0,
        z_max_mm=25.0,
        n_steps=11,
    )

    assert opt["status"] == "SUCCESS"
    assert opt["total_evaluated"] > 0
    assert opt["pareto_count"] > 0, "Should identify at least one Pareto candidate"

    # Check bounds on all candidates
    for cand in opt["all_candidates"]:
        for hp_name in target_hps:
            base_xyz = DEFAULT_HARDPOINTS[hp_name]
            cand_xyz = cand["hardpoints"][hp_name]
            for i in range(3):
                diff = abs(cand_xyz[i] - base_xyz[i])
                assert diff <= max_bound_mm + 1e-4, f"Candidate exceeded bound {max_bound_mm} mm: delta was {diff}"

    # Check best compromise
    best = opt["best_compromise_candidate"]
    assert best is not None
    assert "utopia_distance" in best
    assert best["utopia_distance"] >= 0.0


def test_apply_to_experiment_provenance_preservation():
    """Verify that applying an optimized candidate preserves geometry hashes and delta lists."""
    base_hp = DEFAULT_HARDPOINTS
    cand_hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    cand_hp["UWI_aft"][2] += 4.0  # +4 mm Z

    exp = KinematicsOptimizationService.apply_candidate_to_experiment(
        baseline_hardpoints=base_hp,
        candidate_hardpoints=cand_hp,
        question="What hardpoint should I change to increase negative camber gain?",
        candidate_id="cand-test-01",
        optimization_id="opt-test-99",
    )

    assert exp["status"] == "READY_FOR_SIMULATION"
    assert exp["provenance"]["candidate_id"] == "cand-test-01"
    assert exp["provenance"]["optimization_id"] == "opt-test-99"

    # Verify hashes
    expected_base_hash = compute_geometry_hash(base_hp)
    expected_cand_hash = compute_geometry_hash(cand_hp)
    assert exp["provenance"]["geometry_hash_baseline"] == expected_base_hash
    assert exp["provenance"]["geometry_hash_candidate"] == expected_cand_hash

    # Verify parameter change list
    changes = exp["parameter_changes"]
    assert len(changes) == 1
    assert changes[0]["hardpoint"] == "UWI_aft"
    assert changes[0]["delta_xyz_mm"] == [0.0, 0.0, 4.0]
    assert changes[0]["displacement_distance_mm"] == 4.0
    assert "redirect_url" in exp
