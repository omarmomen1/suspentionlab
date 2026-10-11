"""
tests/test_engineering_optimization_engine.py
=============================================
Comprehensive Engineering Optimization Engine Validation Suite

Covers:
- Step 1: Design Variables & Design Spaces (Units, Bounds, Justifications, Hardware Snapping)
- Step 2: Physical Constraints (Travel, Bottoming, Tire Contact, Damper Velocity, Thermal, Setup Bounds)
- Step 3: Multi-Objective Real Simulation Evaluator (Lap Time, Grip, Ride Quality, Stability, Tire Load)
- Step 4: Non-Dominated Pareto Frontier (Deb's NSGA-II, Dominance Ranks, Utopia Compromise, Persistence)
- Step 5: Multi-Scenario Robust Optimization (Real Scenario Runs, E[f], Var[f], Worst-Case, P(violation))
- Step 6: Local Sensitivity & Step-Size Convergence Verification (df/dx, h vs h/2 convergence, Rankings)
- Step 7: Uncertainty-Aware Surrogate Model with Mandatory Real-Simulation Validation Guard
- Step 8: Evidence-Backed Setup Proposal Engine with Cryptographic Provenance & Confidence Calculation
- Parametric Regression Tests: Verifying that changing parameters changes results and optimizer decisions.
"""

import copy
import math
import pytest
import numpy as np

from suspensionlab.physics.optimization_engine import (
    VariableCategory,
    DesignVariable,
    DesignSpace,
    create_quarter_car_design_space,
    create_racecar_full_design_space,
    ConstraintType,
    EngineeringConstraint,
    ConstraintEvaluationReport,
    ConstraintManager,
    ObjectiveType,
    OptimizationObjective,
    MultiObjectiveEvaluator,
    CandidateRecord,
    ParetoFrontierEngine,
    RobustScenario,
    RobustEvaluator,
    RobustOptimizationResult,
    SensitivityItem,
    SensitivityReport,
    LocalSensitivityEngine,
    UncertaintyAwareSurrogate,
    SurrogateOptimizationEngine,
    SetupParameterChange,
    SetupProposalRecord,
    SetupProposalEngine,
    run_engineering_optimization,
)
from suspensionlab.physics.contracts import PhysicsProvenance


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 TESTS: DESIGN VARIABLES & DESIGN SPACES
# ─────────────────────────────────────────────────────────────────────────────

def test_design_variable_attributes_and_validation():
    var = DesignVariable(
        name="k_spring_f",
        category=VariableCategory.SPRING,
        minimum=20000.0,
        maximum=120000.0,
        default_value=60000.0,
        step=5000.0,
        unit="N/m",
        source="Catalog Race Springs",
        physical_justification="Coil bind avoidance & packaging envelope",
    )
    assert var.name == "k_spring_f"
    assert var.category == VariableCategory.SPRING
    assert var.unit == "N/m"
    assert "Coil bind" in var.physical_justification

    with pytest.raises(ValueError):
        DesignVariable(
            name="invalid_var",
            category=VariableCategory.DAMPER,
            minimum=5000.0,
            maximum=2000.0,
            default_value=3000.0,
            unit="Ns/m",
            source="Test",
            physical_justification="Test",
        )

    with pytest.raises(ValueError):
        DesignVariable(
            name="invalid_default",
            category=VariableCategory.ARB,
            minimum=5000.0,
            maximum=20000.0,
            default_value=25000.0,
            unit="N/m",
            source="Test",
            physical_justification="Test",
        )


def test_design_variable_hardware_snapping():
    var_step = DesignVariable(
        name="k_spring",
        category=VariableCategory.SPRING,
        minimum=20000.0,
        maximum=100000.0,
        default_value=50000.0,
        step=5000.0,
        unit="N/m",
        source="Catalog",
        physical_justification="Step test",
    )
    assert var_step.snap_to_hardware(42300.0) == 40000.0
    assert var_step.snap_to_hardware(43800.0) == 45000.0
    assert var_step.snap_to_hardware(10000.0) == 20000.0
    assert var_step.snap_to_hardware(150000.0) == 100000.0

    var_discrete = DesignVariable(
        name="shim_thickness",
        category=VariableCategory.RIDE_HEIGHT,
        minimum=1.0,
        maximum=10.0,
        default_value=5.0,
        discrete_values=[1.0, 2.5, 5.0, 7.5, 10.0],
        unit="mm",
        source="Packer Kit",
        physical_justification="Discrete shim packs",
    )
    assert var_discrete.snap_to_hardware(2.1) == 2.5
    assert var_discrete.snap_to_hardware(6.8) == 7.5


def test_standard_design_spaces():
    qc_ds = create_quarter_car_design_space()
    assert "k_s" in qc_ds.variables
    assert "c" in qc_ds.variables
    assert qc_ds.variables["k_s"].category == VariableCategory.SPRING
    assert qc_ds.variables["c"].category == VariableCategory.DAMPER

    race_ds = create_racecar_full_design_space()
    assert len(race_ds.variables) >= 10
    assert "k_sf" in race_ds.variables
    assert "k_arb_f" in race_ds.variables
    assert "wing_front_deg" in race_ds.variables
    assert "camber_front_deg" in race_ds.variables


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 TESTS: PHYSICAL CONSTRAINTS
# ─────────────────────────────────────────────────────────────────────────────

def test_engineering_constraint_evaluation():
    c_rh = EngineeringConstraint(
        name="min_dynamic_ride_height_mm",
        constraint_type=ConstraintType.BOTTOMING,
        lower_bound=10.0,
        unit="mm",
        hard=True,
    )
    rep_safe = c_rh.evaluate(15.4)
    assert rep_safe.is_satisfied
    assert math.isclose(rep_safe.headroom, 5.4, rel_tol=1e-3)
    assert rep_safe.violation_penalty == 0.0

    rep_violated = c_rh.evaluate(6.2)
    assert not rep_violated.is_satisfied
    assert math.isclose(rep_violated.headroom, -3.8, rel_tol=1e-3)
    assert rep_violated.violation_penalty > 0.0

    c_vel = EngineeringConstraint(
        name="max_damper_velocity_mps",
        constraint_type=ConstraintType.DAMPER_VELOCITY,
        upper_bound=1.8,
        unit="m/s",
        hard=True,
    )
    assert c_vel.evaluate(1.2).is_satisfied
    assert not c_vel.evaluate(2.1).is_satisfied

    c_temp = EngineeringConstraint(
        name="tire_temp_c",
        constraint_type=ConstraintType.TEMPERATURE,
        lower_bound=75.0,
        upper_bound=110.0,
        unit="°C",
        hard=False,
    )
    assert c_temp.evaluate(90.0).is_satisfied
    assert not c_temp.evaluate(115.0).is_satisfied


def test_constraint_manager_all_types():
    cm = ConstraintManager.create_default_racing_constraints()
    metrics = {
        "min_dynamic_ride_height_mm": 12.5,
        "peak_susp_travel_mm": 22.0,
        "min_tire_contact_load_n": 850.0,
        "max_damper_velocity_mps": 0.95,
        "tire_peak_temp_c": 92.0,
        "roll_stiffness_dist_f": 0.52,
    }
    reports = cm.evaluate_all(metrics)
    assert len(reports) == 6
    assert all(r.is_satisfied for r in reports)

    metrics["min_dynamic_ride_height_mm"] = 4.0
    reports_viol = cm.evaluate_all(metrics)
    viol_item = next(r for r in reports_viol if r.name == "min_dynamic_ride_height_mm")
    assert not viol_item.is_satisfied
    assert viol_item.headroom < 0.0


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 TESTS: MULTI-OBJECTIVE REAL PHYSICS EVALUATION
# ─────────────────────────────────────────────────────────────────────────────

def test_quarter_car_real_physics_evaluation():
    ds = create_quarter_car_design_space()
    cm = ConstraintManager()
    cm.add_constraint(EngineeringConstraint("min_dynamic_ride_height_mm", ConstraintType.BOTTOMING, lower_bound=5.0))
    objs = [
        OptimizationObjective("rms_body_accel_wk", ObjectiveType.RIDE_QUALITY, minimize=True),
        OptimizationObjective("tire_load_variation", ObjectiveType.TIRE_LOAD_VARIATION, minimize=True),
    ]
    evaluator = MultiObjectiveEvaluator(ds, cm, objs, simulation_model="quarter_car")

    metrics, constraints, payload = evaluator.evaluate_physical_candidate({"k_s": 30000.0, "c": 2200.0})
    assert "rms_body_accel_wk" in metrics
    assert "tire_load_variation" in metrics
    # Strict physical bounds: quarter-car step response over road bump
    assert 1.0 <= metrics["rms_body_accel_wk"] <= 5.0, "RMS body accel out of realistic vehicle vibration domain"
    assert 20.0 <= metrics["peak_susp_travel_mm"] <= 60.0, "Suspension travel stroke outside physical suspension packaging"
    assert 200.0 <= metrics["tire_load_variation"] <= 1200.0, "Tire load variation unphysical"
    assert "quarter_car_result" in payload
    assert "diagnostics" in payload
    assert payload["diagnostics"].converged
    assert evaluator.total_simulations_run == 1


def test_coupled_racecar_physics_response_to_parameters():
    ds = create_racecar_full_design_space()
    cm = ConstraintManager.create_default_racing_constraints()
    objs = [
        OptimizationObjective("lap_time_s", ObjectiveType.LAP_TIME, minimize=True),
        OptimizationObjective("mechanical_grip", ObjectiveType.MECHANICAL_GRIP, minimize=False),
    ]
    evaluator = MultiObjectiveEvaluator(ds, cm, objs, simulation_model="coupled_lap_sim")

    p_base = ds.get_default_parameters()
    m_base, _, _ = evaluator.evaluate_physical_candidate(p_base)

    p_stiff_arb = copy.deepcopy(p_base)
    p_stiff_arb["k_arb_f"] = 40000.0
    m_arb, _, _ = evaluator.evaluate_physical_candidate(p_stiff_arb)

    # Stiffening front ARB from 22k to 40k N/m must shift roll stiffness forward by at least 3%
    assert m_arb["roll_stiffness_dist_f"] > m_base["roll_stiffness_dist_f"] + 0.03
    assert 0.52 <= m_arb["roll_stiffness_dist_f"] <= 0.62

    p_high_downforce = copy.deepcopy(p_base)
    p_high_downforce["wing_rear_deg"] = 35.0
    m_wing, _, _ = evaluator.evaluate_physical_candidate(p_high_downforce)

    # Increasing rear wing angle must increase tire normal load, boosting mechanical grip by >4%
    assert m_wing["mechanical_grip"] > m_base["mechanical_grip"] + 4.0
    # Increased aerodynamic downforce must compress suspension, lowering dynamic ride height
    assert m_wing["min_dynamic_ride_height_mm"] < m_base["min_dynamic_ride_height_mm"]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 TESTS: NON-DOMINATED PARETO FRONTIER
# ─────────────────────────────────────────────────────────────────────────────

def test_pareto_dominance_and_non_dominated_sort():
    objs = [
        OptimizationObjective("lap_time_s", ObjectiveType.LAP_TIME, minimize=True),
        OptimizationObjective("rms_accel", ObjectiveType.RIDE_QUALITY, minimize=True),
    ]
    engine = ParetoFrontierEngine(objs)

    prov = PhysicsProvenance("v3", "BDF", "HighFidelity", "hash123", "2026.1", "Enterprise")

    cand_a = CandidateRecord("CAND-A", {"k_s": 80000.0}, {"lap_time_s": 78.0, "rms_accel": 6.0}, [], True, prov)
    cand_b = CandidateRecord("CAND-B", {"k_s": 40000.0}, {"lap_time_s": 80.0, "rms_accel": 3.0}, [], True, prov)
    cand_c = CandidateRecord("CAND-C", {"k_s": 75000.0}, {"lap_time_s": 79.0, "rms_accel": 6.5}, [], True, prov)

    engine.add_candidate(cand_a)
    engine.add_candidate(cand_b)
    engine.add_candidate(cand_c)

    assert engine.dominates(cand_a, cand_c)
    assert not engine.dominates(cand_a, cand_b)
    assert not engine.dominates(cand_b, cand_a)

    frontier = engine.get_pareto_front()
    assert len(frontier) == 2
    frontier_ids = {c.candidate_id for c in frontier}
    assert "CAND-A" in frontier_ids
    assert "CAND-B" in frontier_ids
    assert "CAND-C" not in frontier_ids

    best_comp = engine.select_best_compromise()
    assert best_comp is not None
    assert best_comp.candidate_id in ("CAND-A", "CAND-B")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 TESTS: MULTI-SCENARIO ROBUST OPTIMIZATION
# ─────────────────────────────────────────────────────────────────────────────

def test_multi_scenario_robust_optimization():
    ds = create_racecar_full_design_space()
    cm = ConstraintManager.create_default_racing_constraints()
    objs = [
        OptimizationObjective("lap_time_s", ObjectiveType.LAP_TIME, minimize=True),
        OptimizationObjective("tire_load_variation", ObjectiveType.TIRE_LOAD_VARIATION, minimize=True),
    ]
    evaluator = MultiObjectiveEvaluator(ds, cm, objs, simulation_model="coupled_lap_sim")

    robust_eval = RobustEvaluator.sample_scenarios(evaluator, n_scenarios=8, seed=123)
    assert len(robust_eval.scenarios) == 8

    res = robust_eval.evaluate_robustness(ds.get_default_parameters())
    assert isinstance(res, RobustOptimizationResult)
    assert res.scenarios_evaluated == 8
    assert "lap_time_s" in res.expected_performance
    assert "lap_time_s" in res.std_dev_performance
    # Strict physical bounds: lap time variation under 8 varied track grip/fuel scenarios
    assert 0.10 <= res.std_dev_performance["lap_time_s"] <= 8.0, "Lap time variation across operating conditions out of physical domain"
    assert 60.0 <= res.expected_performance["lap_time_s"] <= 95.0, "Expected lap time unphysical"
    assert res.worst_case_performance["lap_time_s"] >= res.expected_performance["lap_time_s"]
    assert 0.0 <= res.probability_constraint_violation <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 TESTS: LOCAL SENSITIVITY & STEP-SIZE CONVERGENCE
# ─────────────────────────────────────────────────────────────────────────────

def test_local_sensitivity_and_convergence_verification():
    ds = create_racecar_full_design_space()
    cm = ConstraintManager.create_default_racing_constraints()
    objs = [OptimizationObjective("lap_time_s", ObjectiveType.LAP_TIME, minimize=True)]
    evaluator = MultiObjectiveEvaluator(ds, cm, objs, simulation_model="coupled_lap_sim")

    engine = LocalSensitivityEngine(evaluator)
    report = engine.compute_sensitivity(
        nominal_parameters=ds.get_default_parameters(),
        target_objective="lap_time_s",
        nominal_step_fraction=0.02,
        convergence_tolerance=0.25,
    )

    assert isinstance(report, SensitivityReport)
    assert len(report.rankings) == len(ds.variables)
    assert math.isclose(sum(r.variance_explained_pct for r in report.rankings), 100.0, rel_tol=1e-2)

    top_item = report.rankings[0]
    # Central finite difference step-size convergence error must be bounded within tolerance
    assert 0.0 <= top_item.step_size_convergence_error <= 0.20, "Step-size convergence error too large"
    assert top_item.variance_explained_pct > 10.0, "Dominant design variable explains negligible variance"
    assert abs(top_item.gradient) > 1e-6
    assert report.baseline_objective_value > 50.0
    assert top_item.is_step_size_converged
    assert "Increase" in top_item.tuning_direction or "Reduce" in top_item.tuning_direction


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 TESTS: SURROGATE MODELING WITH REAL-SIMULATION VALIDATION GUARD
# ─────────────────────────────────────────────────────────────────────────────

def test_uncertainty_aware_surrogate_and_real_validation_guard():
    ds = create_quarter_car_design_space()
    cm = ConstraintManager()
    cm.add_constraint(EngineeringConstraint("peak_susp_travel_mm", ConstraintType.TRAVEL, upper_bound=45.0))
    objs = [OptimizationObjective("rms_body_accel_wk", ObjectiveType.RIDE_QUALITY, minimize=True)]
    evaluator = MultiObjectiveEvaluator(ds, cm, objs, simulation_model="quarter_car")

    surrogate_engine = SurrogateOptimizationEngine(evaluator)
    surrogate_engine.train_surrogate_from_simulations(n_samples=15, seed=42)

    proposed_params, real_metrics, uncert, is_valid = surrogate_engine.optimize_and_validate(
        target_objective_idx=0,
        n_surrogate_evals=200,
        seed=42,
    )

    assert isinstance(proposed_params, dict)
    assert "rms_body_accel_wk" in real_metrics
    # Real validation guard must return physically bounded quarter-car metrics
    assert 0.5 <= real_metrics["rms_body_accel_wk"] <= 5.0, "Surrogate validated output is unphysical"
    assert 0.0 <= uncert <= 5.0, "Surrogate uncertainty estimate out of bounds"
    assert "k_s" in proposed_params and "c" in proposed_params
    assert isinstance(is_valid, bool)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 TESTS: SETUP PROPOSAL & PROVENANCE LINEAGE
# ─────────────────────────────────────────────────────────────────────────────

def test_setup_proposal_evidence_and_confidence():
    ds = create_racecar_full_design_space()
    cm = ConstraintManager.create_default_racing_constraints()
    objs = [
        OptimizationObjective("lap_time_s", ObjectiveType.LAP_TIME, minimize=True),
        OptimizationObjective("mechanical_grip", ObjectiveType.MECHANICAL_GRIP, minimize=False),
    ]
    evaluator = MultiObjectiveEvaluator(ds, cm, objs, simulation_model="coupled_lap_sim")

    p_base = ds.get_default_parameters()
    p_opt = copy.deepcopy(p_base)
    p_opt["wing_rear_deg"] = 30.0
    p_opt["k_sf"] = 90000.0

    proposal_engine = SetupProposalEngine(evaluator)
    proposal = proposal_engine.generate_proposal(p_base, p_opt, "Improve high-speed cornering stability")

    assert isinstance(proposal, SetupProposalRecord)
    assert proposal.proposal_id.startswith("PROP-")
    assert len(proposal.parameter_changes) == 2
    assert "lap_time_delta_s" in proposal.predicted_effects
    assert proposal.real_simulations_evaluated >= 2
    # Statistical evidence confidence calculated from sample size and constraint headroom
    assert 0.30 <= proposal.confidence_score <= 0.98, f"Confidence {proposal.confidence_score} outside statistical bounds"

    prov = proposal.provenance
    assert prov.model_version == "SuspensionLab-AeroCoupled-v3.2"
    assert prov.solver == "Scipy-RK45-BDF"
    assert prov.backend == "HighFidelity-MultiAxle"
    assert len(prov.input_dataset_hash) == 16, "Dataset hash must be a valid 16-character SHA-256 digest"
    assert prov.software_build != ""


# ─────────────────────────────────────────────────────────────────────────────
# PARAMETRIC REGRESSION & OPTIMIZER DECISION TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_optimizer_decision_changes_with_parameters_and_objectives():
    """Proves that changing parameters and objectives changes simulation results and optimizer decisions."""
    ds = create_racecar_full_design_space()
    cm = ConstraintManager.create_default_racing_constraints()

    # Case 1: Pure Lap Time Optimization
    objs_lap = [OptimizationObjective("lap_time_s", ObjectiveType.LAP_TIME, minimize=True)]
    res_lap = run_engineering_optimization(
        design_space=ds,
        constraint_manager=cm,
        objectives=objs_lap,
        enable_robustness=False,
        seed=42,
    )

    # Case 2: Pure Ride Quality Optimization
    objs_comfort = [OptimizationObjective("rms_body_accel_wk", ObjectiveType.RIDE_QUALITY, minimize=True)]
    res_comfort = run_engineering_optimization(
        design_space=ds,
        constraint_manager=cm,
        objectives=objs_comfort,
        enable_robustness=False,
        seed=42,
    )

    # Optimal parameters must differ between lap time and ride comfort objectives
    p_lap = res_lap["optimal_parameters"]
    p_comfort = res_comfort["optimal_parameters"]

    assert p_lap != p_comfort, "Optimizer arrived at identical setup for conflicting objectives!"
    assert res_lap["optimal_metrics"]["lap_time_s"] != res_comfort["optimal_metrics"]["lap_time_s"]
