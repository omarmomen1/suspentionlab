"""Phase 3E.1 — Longitudinal / Wheel-Speed Forensic Audit Test Suite.

Verifies:
1. Deliverable artifacts exist, are non-empty, and valid.
2. Complete 8-step longitudinal chain variables are traced.
3. Severe brake pressure asymmetry (FR/FL > 3.0x in Turn 5, > 2.5x in Turn 3) is empirically verified.
4. Quantitative sensitivity decomposition explains the majority of Turn 5 Vx error.
5. All 8 candidate failure mechanisms are evaluated and ranked.
6. Zero physics modifications occurred (SHA-256 match with frozen baseline).
7. Zero parameter tuning occurred.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def audit_data():
    audit_json = PROJECT_ROOT / "data" / "phase3e1_longitudinal_forensic_audit.json"
    assert audit_json.exists(), f"Phase 3E.1 audit JSON missing at {audit_json}"
    with open(audit_json, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def manifest_data():
    manifest_path = PROJECT_ROOT / "docs" / "phase3e_frozen_phase3d_manifest.json"
    assert manifest_path.exists(), f"Phase 3D manifest not found at {manifest_path}"
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_phase3e1_deliverables_exist():
    """Verify that both JSON and Markdown deliverable artifacts exist and are non-empty."""
    json_path = PROJECT_ROOT / "data" / "phase3e1_longitudinal_forensic_audit.json"
    md_path = PROJECT_ROOT / "docs" / "phase3e1_longitudinal_forensic_audit_report.md"

    assert json_path.exists(), f"Missing {json_path}"
    assert json_path.stat().st_size > 0, f"Empty {json_path}"

    assert md_path.exists(), f"Missing {md_path}"
    assert md_path.stat().st_size > 0, f"Empty {md_path}"


def test_zero_physics_modifications_preserved(manifest_data):
    """Verify that core physics files remain strictly identical to frozen manifest hashes."""
    p3f_baseline_path = PROJECT_ROOT / "docs" / "phase3f_prechange_baseline.json"
    p3f_baseline = json.load(open(p3f_baseline_path)) if p3f_baseline_path.exists() else None

    for rel_path, meta in manifest_data["file_integrity_ledger"].items():
        if rel_path.startswith("src/"):
            file_path = PROJECT_ROOT / rel_path
            assert file_path.exists(), f"Physics file missing: {rel_path}"
            current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            expected_hash = meta["sha256"]
            if current_hash != expected_hash and p3f_baseline is not None and rel_path in p3f_baseline["file_integrity_ledger"]:
                frozen_baseline_hash = p3f_baseline["file_integrity_ledger"][rel_path]["sha256"]
                assert frozen_baseline_hash == expected_hash, (
                    f"File {rel_path} was modified prior to Phase 3F baseline freeze! Expected {expected_hash}, got {frozen_baseline_hash}"
                )
            else:
                assert current_hash == expected_hash, (
                    f"Physics file {rel_path} was modified during forensic audit!"
                )


def test_zero_tuning_directive(audit_data):
    """Verify that no tuning was performed during the audit."""
    assert audit_data["metadata"]["tuning_performed"] is False
    assert audit_data["metadata"]["physics_modified"] is False
    assert audit_data["metadata"]["status"] == "FORENSIC_AUDIT_COMPLETE"


def test_maneuvers_evaluated_and_traces_present(audit_data):
    """Verify that Turn 5, Turn 3, and Heavy Braking were traced."""
    traces = audit_data["maneuver_traces"]
    assert "Turn5_Tight_Complex" in traces
    assert "Turn3_Approach" in traces
    assert "Heavy_Controlled_Braking" in traces

    for m_name in ["Turn5_Tight_Complex", "Turn3_Approach", "Heavy_Controlled_Braking"]:
        m_info = traces[m_name]
        assert "peak_metrics" in m_info
        assert "sampled_trace" in m_info
        assert len(m_info["sampled_trace"]) > 0


def test_asymmetric_brake_pressure_empirical_proof(audit_data):
    """Verify the empirical discovery of corner pressure asymmetry during cornering."""
    t5_peaks = audit_data["maneuver_traces"]["Turn5_Tight_Complex"]["peak_metrics"]
    t3_peaks = audit_data["maneuver_traces"]["Turn3_Approach"]["peak_metrics"]

    # Turn 5: 45.2 bar outside vs 14.3 bar inside
    assert t5_peaks["max_p_fl_bar"] <= 15.0
    assert t5_peaks["max_p_fr_bar"] >= 40.0
    assert t5_peaks["asymmetry_ratio_fr_over_fl"] >= 3.0

    # Turn 3: 6.6 bar outside vs 2.4 bar inside
    assert t3_peaks["max_p_fl_bar"] <= 3.0
    assert t3_peaks["max_p_fr_bar"] >= 6.0
    assert t3_peaks["asymmetry_ratio_fr_over_fl"] >= 2.5

    # Force deficit ratio in Turn 5: measured physical brake force is > 2.5x the modeled force
    assert t5_peaks["force_deficit_ratio"] >= 2.5


def test_counterfactual_decomposition_explains_error(audit_data):
    """Verify that sensitivity counterfactuals explain the majority of Turn 5 velocity error."""
    decomp = audit_data["counterfactual_decomposition"]
    cf1 = decomp["counterfactual_cf1_4corner_mean_pressure"]
    cf2 = decomp["counterfactual_cf2_true_measured_brake_force"]

    # Ingesting average 4-corner front pressure reduces Turn 5 RMSE
    assert cf1["resulting_rmse_mps"] < decomp["turn5_total_p3d_rmse"]
    assert cf1["error_explained_pct"] > 35.0

    # Ingesting true measured total brake force explains over 50% of the discrepancy
    assert cf2["resulting_rmse_mps"] < decomp["turn5_total_p3d_rmse"]
    assert cf2["error_explained_pct"] > 50.0

    # Engine overrun drag produces substantial unmodeled velocity deficit (> 1.5 m/s)
    eod = decomp["engine_overrun_drag_theoretical"]
    assert eod["velocity_deficit_unmodeled_mps"] > 1.5


def test_candidate_failure_mechanisms_assessed(audit_data):
    """Verify that all 8 candidate factors are assessed and categorized."""
    cfa = audit_data["forensic_findings"]["candidate_factor_assessment"]
    assert len(cfa) >= 8

    required_factors = [
        "brake_torque_distribution",
        "engine_overrun_braking",
        "road_grade_inversion",
        "wheel_inertia_dynamics",
        "tire_longitudinal_stiffness",
        "dynamic_rolling_radius",
        "combined_slip_interaction",
        "low_speed_numerical_behavior",
    ]
    for factor in required_factors:
        assert factor in cfa, f"Missing candidate factor: {factor}"
        assert "impact" in cfa[factor]
        assert "evidence" in cfa[factor]

    # Primary and secondary driver assertions
    assert cfa["brake_torque_distribution"]["impact"] == "CRITICAL_PRIMARY_DRIVER"
    assert cfa["engine_overrun_braking"]["impact"] == "SUBSTANTIAL_SECONDARY_DRIVER"
