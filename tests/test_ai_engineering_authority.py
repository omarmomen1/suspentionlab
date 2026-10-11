"""
tests/test_ai_engineering_authority.py
======================================
Tests for AI Tool-Execution Architecture and Engineering Answer Provenance certification.
"""

import pytest
import numpy as np

from suspensionlab.physics.ai_engineering_authority import (
    AIEngineeringToolRegistry,
    EngineeringAnswerProvenance,
)


def test_ai_tool_registry_deterministic_execution():
    # 1. run_simulation
    sim_res = AIEngineeringToolRegistry.run_simulation({"k_s": 30000.0, "c": 1800.0})
    assert sim_res["status"] == "SUCCESS"
    assert sim_res["f_n_s"] > 1.0

    # 2. run_kinematics
    kin_res = AIEngineeringToolRegistry.run_kinematics()
    assert kin_res["status"] == "SUCCESS"
    assert kin_res["point_count"] == 9

    # 3. compare_runs
    comp_res = AIEngineeringToolRegistry.compare_runs(
        {"k_sf": 30.0, "k_sr": 35.0},
        {"k_sf": 32.0, "k_sr": 34.0},
    )
    assert "predictions" in comp_res
    assert len(comp_res["causal_chain"]) > 0


def test_engineering_answer_provenance_badge():
    prov = AIEngineeringToolRegistry.create_setup_proposal(
        recommendation="Rear low-speed rebound -4.0%",
        target_metric="Corner-exit stability",
        evidence_runs=["Run-184", "Run-191"],
        evidence_sessions=["Telemetry-FP2-004"],
        sim_count=1250,
        correlation_pct=94.2,
        confidence_score=0.91,
        model_version="VehicleModel-7DOF-v14",
    )
    assert isinstance(prov, EngineeringAnswerProvenance)
    assert prov.confidence_score == 0.91
    assert prov.simulation_count == 1250
    assert prov.correlation_pct == 94.2
    assert prov.model_version == "VehicleModel-7DOF-v14"
    assert len(prov.result_hash) == 16
    
    # Hash integrity: different evidence produces different cryptographic hash
    prov_diff = AIEngineeringToolRegistry.create_setup_proposal(
        recommendation="Front anti-roll bar +10%",
        target_metric="Turn-in response",
        evidence_runs=["Run-201"],
        evidence_sessions=["Telemetry-FP3-001"],
        sim_count=400,
    )
    assert prov_diff.result_hash != prov.result_hash

    md_badge = prov.to_markdown_block()
    assert "Engineering Answer Provenance" in md_badge
    assert "Run-184, Run-191" in md_badge
    assert "`1250` verified runs" in md_badge
    assert "94.2%" in md_badge


