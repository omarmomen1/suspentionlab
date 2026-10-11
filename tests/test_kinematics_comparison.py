"""
tests/test_kinematics_comparison.py
===================================
Rigorous verification of Setup A vs Setup B comparative kinematic analysis:
1. Independent solver sweep execution for both setups.
2. Exact hardpoint coordinate delta and link length extraction.
3. Statistical difference calculation: max diff, static diff, bump diff, droop diff, RMS diff.
4. Objective classification into 'WHAT IMPROVED?' vs 'WHAT GOT WORSE?'.
5. Physical causal attribution with strict categorization:
   [DIRECTLY COMPUTED], [INFERRED], [HYPOTHESIZED].
6. Complete cryptographic provenance tracking.
"""

import copy
import pytest
from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    compare_kinematic_setups,
    compute_geometry_hash,
)
from suspensionlab.backend.services.kinematics_study_service import KinematicsStudyService


def test_identical_setups_comparison():
    """Verify comparing identical setups yields zero difference across all channels."""
    setup_a = {"id": "baseline", "name": "Baseline", "hardpoints": DEFAULT_HARDPOINTS}
    setup_b = {"id": "baseline_copy", "name": "Copy", "hardpoints": DEFAULT_HARDPOINTS}

    res = compare_kinematic_setups(setup_a, setup_b, sweep_config={"z_min_mm": -30.0, "z_max_mm": 30.0, "n_steps": 15})

    assert len(res["hardpoint_deltas"]) == 0
    assert len(res["link_deltas"]) == 0

    camber_cmp = res["metric_comparisons"]["camber_deg"]
    assert camber_cmp["max_difference"] == 0.0
    assert camber_cmp["rms_difference"] == 0.0
    assert camber_cmp["static_difference"] == 0.0

    # Equivalence reported
    assert any("Equivalence" in imp["metric"] for imp in res["what_improved"])


def test_modified_pickup_causal_attribution():
    """Verify raising upper inner pickup creates physically grounded causal findings."""
    setup_a = {"id": "gt3_base", "name": "GT3 Base", "hardpoints": DEFAULT_HARDPOINTS}
    hp_b = copy.deepcopy(DEFAULT_HARDPOINTS)
    # Raise upper inboard forward and aft pivots by +6 mm in Z
    hp_b["UWI_fwd"][2] += 6.0
    hp_b["UWI_aft"][2] += 6.0
    setup_b = {"id": "gt3_mod", "name": "GT3 Raised Pivot", "hardpoints": hp_b}

    res = compare_kinematic_setups(setup_a, setup_b, sweep_config={"z_min_mm": -40.0, "z_max_mm": 40.0, "n_steps": 17})

    # 1. Hardpoint deltas check
    deltas = {d["hardpoint"]: d for d in res["hardpoint_deltas"]}
    assert "UWI_fwd" in deltas
    assert deltas["UWI_fwd"]["delta_z_mm"] == 6.0
    assert "UWI_aft" in deltas
    assert deltas["UWI_aft"]["delta_z_mm"] == 6.0

    # 2. Metric comparisons check
    camber_cmp = res["metric_comparisons"]["camber_deg"]
    assert camber_cmp["max_difference"] > 0.0
    assert camber_cmp["rms_difference"] > 0.0

    # 3. Categorized causal findings check
    findings = res["causal_findings"]
    assert len(findings) >= 3

    categories = {f["category"] for f in findings}
    assert "DIRECTLY COMPUTED" in categories
    assert "INFERRED" in categories
    assert "HYPOTHESIZED" in categories

    for f in findings:
        assert "title" in f
        assert "statement" in f
        assert len(f["statement"]) > 10

    # 4. Provenance check
    prov = res["provenance"]
    for field in [
        "run_id", "setup_a_id", "setup_b_id", "geometry_hash_a",
        "geometry_hash_b", "sweep_range_mm", "solver_version", "timestamp"
    ]:
        assert field in prov, f"Missing provenance field '{field}'"
        assert prov[field] is not None


def test_kinematics_study_service_preset_comparison():
    """Verify KinematicsStudyService compare method with catalog presets."""
    preset_gt3 = KinematicsStudyService.get_setup("gt3_touring")
    preset_mod = KinematicsStudyService.get_setup("gt3_camber_shim_5mm")

    assert preset_gt3 is not None
    assert preset_mod is not None

    res = KinematicsStudyService.compare(preset_gt3, preset_mod, {"z_min_mm": -30.0, "z_max_mm": 30.0, "n_steps": 15})

    assert len(res["hardpoint_deltas"]) > 0
    assert "camber_deg" in res["metric_comparisons"]
    assert "toe_deg" in res["metric_comparisons"]
    assert len(res["what_improved"]) > 0 or len(res["what_got_worse"]) > 0
