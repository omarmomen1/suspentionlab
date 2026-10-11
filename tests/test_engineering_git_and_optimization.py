"""
tests/test_engineering_git_and_optimization.py
==============================================
Tests for Engineering Git, Setup Diff with Causal Chains, Constrained/Robust Optimization,
and Parameter Sensitivity Ranking.
"""

import pytest
import numpy as np

from suspensionlab.physics.engineering_git import (
    SetupCommit,
    compare_setups,
    SetupDiffReport,
)
from suspensionlab.physics.constrained_optimization import (
    optimize_setup_constrained,
    ConstrainedOptimizationReport,
    SensitivityRankItem,
)


def test_engineering_git_setup_commits():
    commit1 = SetupCommit.create(
        author="RaceEngineer_A",
        change_reason="Soften rear spring for traction",
        parameters={"k_sf": 35.0, "k_sr": 40.0},
    )
    assert commit1.commit_id.startswith("commit-")
    assert commit1.approval_status == "APPROVED"

    # Child commit with parent pointer
    commit2 = SetupCommit.create(
        author="RaceEngineer_B",
        change_reason="Increase front ARB for turn-in balance",
        parameters={"k_sf": 35.0, "k_sr": 40.0, "k_arb_f": 60.0},
        parent_commit_id=commit1.commit_id,
    )
    assert commit2.parent_commit_id == commit1.commit_id


def test_setup_diff_and_causal_chains():
    setup_a = {"k_sf": 110.0, "k_sr": 130.0, "k_arb_f": 55.0, "toe_r": 0.10, "ride_height_f": 28.0}
    setup_b = {"k_sf": 115.0, "k_sr": 125.0, "k_arb_f": 60.0, "toe_r": 0.06, "ride_height_f": 26.0}

    report = compare_setups(setup_a, setup_b, "Setup A", "Setup B")
    assert isinstance(report, SetupDiffReport)
    assert len(report.parameter_diffs) == 5
    
    # Predicted performance metrics
    assert report.estimated_lap_time_delta_s < 0.0  # Faster lap time
    assert report.rear_stability_delta_pct > 0.0     # Rear stability improvement
    
    # Causal Chain validation
    assert len(report.causal_chain) >= 3
    mechanisms = [c.physics_mechanism for c in report.causal_chain]
    assert any("Lateral Load Transfer" in m for m in mechanisms)
    assert any("Tire Friction" in m for m in mechanisms)


def test_constrained_and_robust_optimization():
    initial = {"k_sf": 30000.0, "k_sr": 35000.0, "c_f": 2000.0, "c_r": 2200.0, "k_arb_f": 10000.0, "k_arb_r": 8000.0}
    
    report = optimize_setup_constrained(
        initial_parameters=initial,
        min_dynamic_ride_height_mm=15.0,
        max_damper_velocity_mps=1.5,
    )
    assert isinstance(report, ConstrainedOptimizationReport)
    assert report.is_feasible
    assert report.optimized_lap_time_s <= report.baseline_lap_time_s
    assert len(report.pareto_frontier) >= 2
    assert len(report.sensitivity_rankings) >= 4
    
    # Check top sensitivity item
    top_param = report.sensitivity_rankings[0]
    assert top_param.variance_explained_pct > 15.0
    assert len(top_param.suggested_tuning_direction) > 5

