"""
tests/test_vnv_matrix.py
========================
Tests for the formal Verification & Validation matrix and conservation law monitors.
"""

import pytest
from suspensionlab.physics.vnv.framework import (
    run_vnv_suite,
    render_vnv_markdown,
    PhysicsDiagnostics,
)


def test_vnv_suite_execution():
    results = run_vnv_suite()
    assert len(results) >= 5
    for r in results:
        assert r.status == "PASS", f"V&V Case {r.id} ({r.title}) failed with error {r.error_pct:.2f}% > tol {r.tolerance_pct:.2f}%"
        assert len(r.solver_version) > 0
        assert len(r.physics_version) > 0


def test_vnv_markdown_report():
    results = run_vnv_suite()
    report = render_vnv_markdown(results)
    assert "# SuspensionLab PRO — Formal Verification & Validation" in report
    assert "QC-FREQ-001" in report
    assert "TIRE-COMB-005" in report
    assert "FULLCAR-ENERGY-006" in report


def test_physics_diagnostics_validation():
    diag = PhysicsDiagnostics(
        energy_error=0.002,
        momentum_error=0.001,
        constraint_error=1e-8,
        contact_violations=0,
        static_equilibrium_error=0.0001,
    )
    assert diag.is_valid()
    
    # Violation of contact force condition
    diag_invalid = PhysicsDiagnostics(
        energy_error=0.002,
        momentum_error=0.001,
        constraint_error=1e-8,
        contact_violations=3,
    )
    assert not diag_invalid.is_valid()


def test_vnv_json_report_generation(tmp_path):
    from suspensionlab.physics.vnv.framework import generate_vnv_json_report
    results = run_vnv_suite()
    out_file = str(tmp_path / "vnv_report.json")
    report = generate_vnv_json_report(results, output_path=out_file)
    
    assert report["overall_status"] == "PASS"
    assert report["total_tests"] >= 5
    assert len(report["results"]) == len(results)
    assert "QC-FREQ-001" in [r["test_id"] for r in report["results"]]

