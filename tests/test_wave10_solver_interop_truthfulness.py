"""
tests/test_wave10_solver_interop_truthfulness.py
================================================
Wave 10 — Solver interop: no toy data, no meaningless comparison.

Pins:
1. The solver-import form starts empty (no typed-in demo Adams deck).
2. When the imported dataset declares its road input, the native side replays exactly that input.
3. When it does not, the comparison is labeled "not comparable" and carries no correlation verdict.
4. Host runtime unavailability is still reported truthfully.
"""

import os
import re

import pytest

from suspensionlab.backend.services.cae_integration_service import CaeIntegrationService
from suspensionlab.interop.execution.runtimes import RuntimeAvailability, SolverRuntimeRegistry

TRACE_CSV = """time,ddz_s,susp_travel_mm,tire_load_N
0.000,0.010,0.5,3200
0.010,-0.120,1.1,3210
0.020,0.240,1.8,3230
0.030,-0.310,2.2,3250
0.040,0.180,1.6,3220
0.050,-0.060,0.9,3190
"""

PARAMS = {"m_s": 320.0, "m_u": 45.0, "k_s": 35000.0, "c": 2200.0, "k_t": 220000.0, "MR": 0.85}


def _dataset(inputs_meta=None):
    return CaeIntegrationService.import_and_normalize_external_run(
        source_tool="MSC Adams",
        version="2024.1",
        solver="WSTIFF",
        parameters=PARAMS,
        raw_trace_csv=TRACE_CSV,
        inputs_meta=inputs_meta,
    )


def test_import_form_starts_empty():
    """The import form must not ship a typed-in demo deck.

    Static guard: this is a React client component with no JSX test runner in this
    repository, so the initial state is asserted from the source itself.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "frontend", "components", "engineering", "SolverInteropWorkspace.tsx")
    source = open(path, encoding="utf-8").read()
    assert 'useState<string>("")' in source
    assert "MSC ADAMS / Solver Dataset" not in source
    assert "PART/1, MASS = 300.0" not in source
    assert "SPRING/1, K = 25000.0" not in source
    assert 'placeholder="Paste your .adm / .cmd / .fmu export here"' in source
    # the content state itself must start empty
    assert re.search(r'const \[importContent, setImportContent\] = useState<string>\(""\)', source)


def test_compare_uses_external_excitation_when_available():
    """When the dataset declares its road input, the native side runs exactly that input."""
    dataset = _dataset({"road_profile": {"profile_type": "sine", "amplitude": 0.02, "frequency": 2.5}})
    result = CaeIntegrationService.compare_external_vs_native(dataset)

    assert result["excitation_match"] is True
    assert result["excitation_source"] == "external_dataset"
    assert result["verdict_suppressed"] is False
    assert "2.5" in result["excitation_description"]
    assert "0.02" in result["excitation_description"]
    assert result["correlation_metrics"]["r2_comparable"] is True
    assert result["correlation_metrics"]["agreement_status"] != "NOT_COMPARABLE"
    assert "Same excitation replayed" in result["comparison_label"]
    assert "matching road profile excitation" in result["boundary_notes"]


def test_compare_without_excitation_is_labeled_not_comparable():
    """With no declared excitation the fixed 1.8 Hz sine is not a matching input: no verdict."""
    dataset = _dataset()
    result = CaeIntegrationService.compare_external_vs_native(dataset)

    assert result["excitation_match"] is False
    assert result["excitation_source"] == "native_default"
    assert result["verdict_suppressed"] is True
    assert result["comparison_label"] == (
        "Different excitation: native 1.8 Hz sine vs external run input - R2 not comparable"
    )
    assert result["correlation_metrics"]["agreement_status"] == "NOT_COMPARABLE"
    assert result["correlation_metrics"]["r2_comparable"] is False
    assert result["channel_metrics"]["ddz_s"]["agreement_status"] == "NOT_COMPARABLE"
    assert result["channel_metrics"]["ddz_s"]["r2_comparable"] is False
    # No PASS / CORRELATED verdict may survive anywhere in the payload.
    blob = repr(result).upper()
    assert "STRONG_CORRELATION" not in blob
    assert "MODERATE_CORRELATION" not in blob
    assert "PASS" not in blob


def test_runtime_unavailable_reporting_unchanged():
    """A missing host solver is still reported as unavailable, with its reason and no fake version."""
    info = SolverRuntimeRegistry.inspect_fmi_runtime()
    payload = info.to_dict()
    assert payload["solver_name"] == "FMI_COSIMULATION"
    assert payload["adapter_id"] == "adapter-fmi-cosim-v1"
    if info.is_available:
        assert info.availability != RuntimeAvailability.UNAVAILABLE
        assert info.executable_path
    else:
        assert info.availability == RuntimeAvailability.UNAVAILABLE
        assert payload["is_available"] is False
        assert info.executable_path is None
        assert "unavailable" in info.notes.lower() or "not detected" in info.notes.lower()
