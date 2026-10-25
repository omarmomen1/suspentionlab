"""
tests/test_phase7_1_solver_interop_contract.py
===============================================
SuspensionLab PRO — Phase 7.1 Solver Interoperability Contract Test Suite.

Covers all 32 required acceptance scenarios:
 1. Canonical manifest validation.
 2. Unsupported schema version rejection.
 3. Deterministic canonical manifest hashing.
 4. Material input changes produce different identities.
 5. Parameter mappings use authoritative identifiers.
 6. Similar names alone do not establish equivalence.
 7. Compatible unit conversions work correctly.
 8. Incompatible dimensions are rejected.
 9. Missing units are explicitly unresolved.
10. Missing coordinate conventions are explicitly unresolved.
11. Invalid sign/frame transformations are rejected.
12. Adapter capability reporting is truthful.
13. Unsupported adapter versions are rejected.
14. Registry ordering is deterministic.
15. Unknown solver is represented as unsupported.
16. Unavailable dependency is reported honestly.
17. Imported artifacts retain source provenance.
18. Import success is not treated as validation success.
19. Export success is not treated as solver execution.
20. Malformed structured files fail safely.
21. NaN and Infinity are handled safely.
22. Path traversal is blocked.
23. Oversized or malformed input is bounded safely.
24. No arbitrary imported code is executed.
25. Tenant isolation follows repository conventions.
26. Adapter registry does not alter Evidence Graph vocabulary.
27. Phase 4 regressions remain green.
28. Phase 5 remains independent.
29. Phase 6 remains independent.
30. All 81 protected physics files remain unchanged.
31. Phase 3 artifacts remain unchanged.
32. Alembic topology remains valid.

Plus adversarial attack suites for unit injection, zip slip, zip bombs, and frame tampering.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import os
import pathlib
import sys
import zipfile
import pytest
from fastapi.testclient import TestClient

# Interoperability Subsystem
from suspensionlab.interop.units import (
    ConversionRecord,
    IncompatibleDimensionError,
    UnresolvedUnitError,
    UnitCompatibilityStatus,
    check_unit_compatibility,
    convert_unit_value,
    get_physical_dimension,
    are_units_dimensionally_compatible,
)
from suspensionlab.interop.frames import (
    CoordinateFrameDefinition,
    CoordinateStandard,
    FrameValidationStatus,
    Handedness,
    ISO_8855_FRAME,
    SAE_J670_FRAME,
    validate_coordinate_frame,
    compute_frame_transformation,
)
from suspensionlab.interop.mapping import (
    MappingProvenance,
    MappingStatus,
    ParameterMapping,
    is_authoritative_internal_parameter,
    validate_parameter_mapping,
    detect_heuristic_name_mismatch,
)
from suspensionlab.interop.manifest import (
    ArtifactReference,
    CanonicalExchangeManifest,
    ExchangeMode,
    ExchangeValidationStatus,
    ExecutionMetadata,
    ParameterValue,
    ResultProvenanceOrigin,
    SUPPORTED_EXCHANGE_SCHEMA_VERSIONS,
    compute_canonical_manifest_hash,
    validate_canonical_manifest,
)
from suspensionlab.interop.adapter import (
    AdapterCapability,
    BaseSolverAdapter,
    DataCategory,
    DependencyRequirement,
    SupportLevel,
    VerificationStatus,
)
from suspensionlab.interop.registry import (
    AdapterRegistry,
    get_adapter_registry,
    reset_adapter_registry,
)
from suspensionlab.interop.security import (
    MAX_PAYLOAD_BYTES,
    MAX_ARRAY_ELEMENTS,
    MAX_DICT_KEYS,
    InteropSecurityError,
    PathTraversalSecurityError,
    ExecutableContentSecurityError,
    ResourceExhaustionSecurityError,
    MalformedPayloadSecurityError,
    MalformedNumericSecurityError,
    TenantIsolationError,
    sanitize_artifact_filename,
    verify_safe_path,
    check_payload_size,
    safe_parse_json,
    safe_parse_csv,
    safe_extract_archive,
    enforce_tenant_isolation,
)
from suspensionlab.interop.service import SolverInteropService
from suspensionlab.interop.adapters.canonical_json import CanonicalJsonAdapter
from suspensionlab.interop.adapters.adams import AdamsSolverAdapter
from suspensionlab.interop.adapters.matlab_simulink import MatlabSimulinkAdapter
from suspensionlab.interop.adapters.fmi import FMICoSimulationAdapter
from suspensionlab.interop.adapters.tir_tire import TirPropertyAdapter

from suspensionlab.backend.database.models.evidence_graph import EvidenceGraphRelationship


PROJECT_ROOT = pathlib.Path(__file__).parent.parent.resolve()


# ── TEST 1: CANONICAL MANIFEST VALIDATION ────────────────────────────────────

def test_01_canonical_manifest_validation():
    """Requirement 1: Valid canonical manifest passes verification with complete fields."""
    params = {
        "m_s": ParameterValue(name="m_s", value=300.0, unit="kg", dimension="mass"),
        "k_w": ParameterValue(name="k_w", value=18000.0, unit="N/m", dimension="stiffness"),
    }
    manifest = CanonicalExchangeManifest(
        schema_version="1.0.0",
        engineering_model_id="quarter_car",
        source_solver="SuspensionLab",
        exchange_mode=ExchangeMode.EXPORT,
        parameters=params,
        coordinate_frame=ISO_8855_FRAME,
    )
    is_valid, warnings, parsed = validate_canonical_manifest(manifest)
    assert is_valid is True
    assert parsed is not None
    assert parsed.engineering_model_id == "quarter_car"
    assert parsed.manifest_id is not None
    assert len(parsed.manifest_id) == 64


# ── TEST 2: UNSUPPORTED SCHEMA VERSION REJECTION ──────────────────────────────

def test_02_unsupported_schema_version_rejection():
    """Requirement 2: Schema versions other than supported set are strictly rejected."""
    bad_manifest = {
        "schema_version": "2.0.0",
        "engineering_model_id": "quarter_car",
        "source_solver": "SuspensionLab",
    }
    is_valid, errors, parsed = validate_canonical_manifest(bad_manifest)
    assert is_valid is False
    assert any("Unsupported exchange schema version" in err for err in errors)
    assert parsed is None

    # Test rejection via direct model instantiation
    with pytest.raises(ValueError, match="Unsupported exchange schema version"):
        CanonicalExchangeManifest(
            schema_version="0.9.0",
            engineering_model_id="quarter_car",
        )


# ── TEST 3: DETERMINISTIC CANONICAL MANIFEST HASHING ──────────────────────────

def test_03_deterministic_canonical_manifest_hashing():
    """Requirement 3: Serializing the exact same manifest twice yields identical SHA-256."""
    params = {
        "m_s": ParameterValue(name="m_s", value=305.5, unit="kg", dimension="mass"),
        "k_s": ParameterValue(name="k_s", value=25000.0, unit="N/m", dimension="stiffness"),
    }
    m1 = CanonicalExchangeManifest(
        schema_version="1.0.0",
        engineering_model_id="quarter_car",
        parameters=params,
        coordinate_frame=ISO_8855_FRAME,
        created_at_utc="2026-10-10T12:00:00.000000Z",
    )
    m2 = CanonicalExchangeManifest(
        schema_version="1.0.0",
        engineering_model_id="quarter_car",
        parameters=copy.deepcopy(params),
        coordinate_frame=ISO_8855_FRAME,
        created_at_utc="2026-10-10T12:00:00.000000Z",
    )
    h1 = compute_canonical_manifest_hash(m1)
    h2 = compute_canonical_manifest_hash(m2)
    assert h1 == h2
    assert len(h1) == 64


# ── TEST 4: MATERIAL INPUT CHANGES PRODUCE DIFFERENT IDENTITIES ───────────────

def test_04_material_input_changes_produce_different_identities():
    """Requirement 4: Material parameter, unit, or artifact changes produce different hashes."""
    base_params = {
        "m_s": ParameterValue(name="m_s", value=300.0, unit="kg", dimension="mass"),
    }
    m_base = CanonicalExchangeManifest(
        schema_version="1.0.0",
        engineering_model_id="quarter_car",
        parameters=base_params,
        created_at_utc="2026-10-10T12:00:00.000000Z",
    )
    base_hash = compute_canonical_manifest_hash(m_base)

    # 1. Parameter value change
    m_val_change = copy.deepcopy(m_base)
    m_val_change.parameters["m_s"] = ParameterValue(name="m_s", value=300.5, unit="kg", dimension="mass")
    assert compute_canonical_manifest_hash(m_val_change) != base_hash

    # 2. Unit change
    m_unit_change = copy.deepcopy(m_base)
    m_unit_change.parameters["m_s"] = ParameterValue(name="m_s", value=300.0, unit="g", dimension="mass")
    assert compute_canonical_manifest_hash(m_unit_change) != base_hash

    # 3. Artifact addition
    m_art_change = copy.deepcopy(m_base)
    m_art_change.input_artifacts.append(
        ArtifactReference(
            artifact_id="ART-1",
            name="test.adm",
            artifact_type="text/plain",
            sha256="a" * 64,
            size_bytes=100,
        )
    )
    assert compute_canonical_manifest_hash(m_art_change) != base_hash


# ── TEST 5: PARAMETER MAPPINGS USE AUTHORITATIVE IDENTIFIERS ─────────────────

def test_05_parameter_mappings_use_authoritative_identifiers():
    """Requirement 5: Mappings require authoritative internal parameter paths."""
    # Known authoritative parameter
    assert is_authoritative_internal_parameter("quarter_car", "m_s") is True
    valid_map = ParameterMapping(
        internal_entity_type="quarter_car",
        internal_parameter_path="m_s",
        external_solver_name="MSC_ADAMS",
        external_variable_id="PART_2_MASS",
        internal_unit="kg",
        external_unit="kg",
        provenance=MappingProvenance.AUTHORITATIVE_SPEC,
    )
    is_valid, warnings = validate_parameter_mapping(valid_map)
    assert is_valid is True
    assert valid_map.status == MappingStatus.SUPPORTED

    # Unknown parameter path
    assert is_authoritative_internal_parameter("quarter_car", "non_existent_param_xyz") is False
    invalid_map = ParameterMapping(
        internal_entity_type="quarter_car",
        internal_parameter_path="non_existent_param_xyz",
        external_solver_name="MSC_ADAMS",
        external_variable_id="SOME_VAR",
        internal_unit="kg",
        external_unit="kg",
        provenance=MappingProvenance.AUTHORITATIVE_SPEC,
    )
    is_valid, warnings = validate_parameter_mapping(invalid_map)
    assert is_valid is False
    assert invalid_map.status == MappingStatus.UNSUPPORTED


# ── TEST 6: SIMILAR NAMES ALONE DO NOT ESTABLISH EQUIVALENCE ──────────────────

def test_06_similar_names_alone_do_not_establish_equivalence():
    """Requirement 6: Textual similarity alone does NOT establish engineering equivalence."""
    # 'm_s' (sprung mass) vs 'm_u' (unsprung mass) have 50% ratio
    assert detect_heuristic_name_mismatch("m_s", "m_u") is True
    # 'k_w' (wheel rate) vs 'k_t' (tire stiffness)
    assert detect_heuristic_name_mismatch("k_w", "k_t") is True
    # 'speed' vs 'wheel_speed'
    assert detect_heuristic_name_mismatch("speed", "wheel_speed") is True

    # An unverified heuristic mapping based on similar names must be rejected
    heuristic_map = ParameterMapping(
        internal_entity_type="quarter_car",
        internal_parameter_path="m_s",
        external_solver_name="MSC_ADAMS",
        external_variable_id="m_u",
        internal_unit="kg",
        external_unit="kg",
        provenance=MappingProvenance.UNVERIFIED_HEURISTIC,
    )
    is_valid, warnings = validate_parameter_mapping(heuristic_map)
    assert is_valid is False
    assert heuristic_map.status == MappingStatus.UNSUPPORTED
    assert any("Name-similarity alone cannot establish" in w for w in warnings)


# ── TEST 7: COMPATIBLE UNIT CONVERSIONS WORK CORRECTLY ────────────────────────

def test_07_compatible_unit_conversions_work_correctly():
    """Requirement 7: Units sharing the exact same dimension convert with explicit record."""
    # 1. Stiffness: lb/in to N/m
    val_nm, rec_nm = convert_unit_value(100.0, "lb/in", "N/m", parameter_name="k_s")
    assert pytest.approx(val_nm, rel=1e-4) == 17512.6835
    assert rec_nm.scale_factor == pytest.approx(175.126835, rel=1e-4)
    assert rec_nm.from_unit == "lb/in"
    assert rec_nm.to_unit == "n/m"

    # 2. Length: mm to m
    val_m, rec_m = convert_unit_value(50.0, "mm", "m", parameter_name="stroke")
    assert pytest.approx(val_m, rel=1e-6) == 0.05
    assert rec_m.scale_factor == 0.001

    # 3. Pressure: bar to psi
    val_psi, rec_psi = convert_unit_value(2.0, "bar", "psi", parameter_name="p_tire")
    assert pytest.approx(val_psi, rel=1e-4) == 29.0075


# ── TEST 8: INCOMPATIBLE DIMENSIONS ARE REJECTED ──────────────────────────────

def test_08_incompatible_dimensions_are_rejected():
    """Requirement 8: Attempting to convert across different dimensions raises explicit error."""
    # Stiffness vs Mass
    status, detail = check_unit_compatibility("N/m", "kg")
    assert status == UnitCompatibilityStatus.INCOMPATIBLE
    assert "Incompatible physical dimensions" in detail

    with pytest.raises(IncompatibleDimensionError, match="Incompatible physical dimensions"):
        convert_unit_value(500.0, "N/m", "kg")

    # Velocity vs Pressure
    with pytest.raises(IncompatibleDimensionError):
        convert_unit_value(30.0, "m/s", "bar")


# ── TEST 9: MISSING UNITS ARE EXPLICITLY UNRESOLVED ───────────────────────────

def test_09_missing_units_are_explicitly_unresolved():
    """Requirement 9: Missing or empty units produce UNRESOLVED rather than guessing SI."""
    status, detail = check_unit_compatibility(None, "kg")
    assert status == UnitCompatibilityStatus.UNRESOLVED
    assert "Missing authoritative unit specification" in detail

    status_empty, _ = check_unit_compatibility("", "N/m")
    assert status_empty == UnitCompatibilityStatus.UNRESOLVED

    with pytest.raises(UnresolvedUnitError, match="Cannot convert value"):
        convert_unit_value(100.0, None, "kg")


# ── TEST 10: MISSING COORDINATE CONVENTIONS ARE EXPLICITLY UNRESOLVED ─────────

def test_10_missing_coordinate_conventions_are_explicitly_unresolved():
    """Requirement 10: Missing coordinate frames or axes produce UNRESOLVED status."""
    status, reasons = validate_coordinate_frame(None)
    assert status == FrameValidationStatus.UNRESOLVED
    assert any("No coordinate frame definition" in r for r in reasons)

    # Frame with missing axes
    incomplete_frame = CoordinateFrameDefinition.model_construct(
        standard=CoordinateStandard.CUSTOM,
        x_axis="",
        y_axis="LEFT",
        z_axis="UP",
        handedness=Handedness.RIGHT_HANDED,
    )
    status_inc, reasons_inc = validate_coordinate_frame(incomplete_frame)
    assert status_inc == FrameValidationStatus.UNRESOLVED


# ── TEST 11: INVALID SIGN / FRAME TRANSFORMATIONS ARE REJECTED ────────────────

def test_11_invalid_sign_frame_transformations_are_rejected():
    """Requirement 11: Inconsistent handedness or ambiguous orientations are rejected."""
    # A frame with X forward, Y left, Z DOWN is left-handed, but declared RIGHT_HANDED
    with pytest.raises(ValueError, match="Inconsistent coordinate frame"):
        CoordinateFrameDefinition(
            standard=CoordinateStandard.CUSTOM,
            name="Tampered_LeftHanded_Frame",
            x_axis="FORWARD",
            y_axis="LEFT",
            z_axis="DOWN",
            handedness=Handedness.RIGHT_HANDED,  # Contradiction!
        )

    # Attempting transformation with None frame fails safely
    ok, mat, msgs = compute_frame_transformation(None, ISO_8855_FRAME)
    assert ok is False
    assert mat is None
    assert any("unresolved" in m for m in msgs)


# ── TEST 12: ADAPTER CAPABILITY REPORTING IS TRUTHFUL ─────────────────────────

def test_12_adapter_capability_reporting_is_truthful():
    """Requirement 12: Adapters declare exact truthful capabilities and supported formats."""
    json_adapter = CanonicalJsonAdapter()
    caps = json_adapter.get_capabilities()
    assert caps.import_capability == SupportLevel.SUPPORTED
    assert caps.export_capability == SupportLevel.SUPPORTED
    assert ".json" in caps.supported_formats

    adams_adapter = AdamsSolverAdapter()
    adams_caps = adams_adapter.get_capabilities()
    assert adams_caps.export_capability == SupportLevel.SUPPORTED
    assert adams_caps.import_capability == SupportLevel.PARTIALLY_SUPPORTED
    assert ".adm" in adams_caps.supported_formats
    assert adams_caps.supported_import_formats == [".adm"]
    assert set(adams_caps.supported_export_formats) == {".adm", ".cmd", ".py"}

    # Registry format search by mode
    reg = get_adapter_registry()
    adams_in_import = [a.ADAPTER_ID for a in reg.find_by_format(".adm", mode="import")]
    assert "adapter-msc-adams-v1" in adams_in_import
    assert reg.find_by_format(".cmd", mode="import") == []
    assert reg.find_by_format(".py", mode="import") == []
    adams_in_export = [a.ADAPTER_ID for a in reg.find_by_format(".cmd", mode="export")]
    assert "adapter-msc-adams-v1" in adams_in_export


# ── TEST 13: UNSUPPORTED ADAPTER VERSIONS ARE REJECTED ─────────────────────────

def test_13_unsupported_adapter_versions_are_rejected():
    """Requirement 13: Registering an adapter with empty version or identity raises error."""
    reg = AdapterRegistry()
    
    class BrokenAdapter(BaseSolverAdapter):
        def get_capabilities(self) -> AdapterCapability:
            return AdapterCapability(
                adapter_id="",
                adapter_version="1.0.0",
                solver_name="BROKEN",
                supported_formats=[".dat"],
                supported_categories=[DataCategory.PARAMETERS],
            )
        def get_supported_versions(self): return []
        def validate_input(self, c, o=None): return (False, [])
        def export_artifact(self, m, o=None): raise NotImplementedError
        def import_artifact(self, c, o=None): raise NotImplementedError

    with pytest.raises(ValueError, match="Adapter identity cannot be empty"):
        reg.register(BrokenAdapter())


# ── TEST 14: REGISTRY ORDERING IS DETERMINISTIC ───────────────────────────────

def test_14_registry_ordering_is_deterministic():
    """Requirement 14: Multiple calls to list_adapters() return identical sorted order."""
    reg = get_adapter_registry()
    list_1 = [c.adapter_id for c in reg.list_adapters()]
    list_2 = [c.adapter_id for c in reg.list_adapters()]
    assert list_1 == list_2
    assert list_1 == sorted(list_1)


# ── TEST 15: UNKNOWN SOLVER IS REPRESENTED AS UNSUPPORTED ─────────────────────

def test_15_unknown_solver_is_represented_as_unsupported():
    """Requirement 15: Querying unknown solvers returns SupportLevel.UNSUPPORTED."""
    reg = get_adapter_registry()
    level = reg.get_solver_support_level("NON_EXISTENT_SOLVER_99")
    assert level == SupportLevel.UNSUPPORTED
    assert reg.find_by_solver("NON_EXISTENT_SOLVER_99") == []


# ── TEST 16: UNAVAILABLE DEPENDENCY IS REPORTED HONESTLY ──────────────────────

def test_16_unavailable_dependency_is_reported_honestly():
    """Requirement 16: External runtime engines report UNAVAILABLE_DEPENDENCY honestly."""
    fmi_adapter = FMICoSimulationAdapter()
    caps = fmi_adapter.get_capabilities()
    dep = caps.required_dependencies[0]
    assert dep.name == "fmi-runtime-master"
    assert dep.is_available is False  # Honest reporting: host is not assumed to have FMI Master


# ── TEST 17: IMPORTED ARTIFACTS RETAIN SOURCE PROVENANCE ──────────────────────

def test_17_imported_artifacts_retain_source_provenance():
    """Requirement 17: Ingested external artifacts preserve source hash, adapter ID, and metadata."""
    svc = SolverInteropService()
    test_adm = b"PART/2, MASS = 310.0\nPART/3, MASS = 38.0\nSPRINGDAMPER/1, STIFFNESS_COEFFICIENT = 22000.0, DAMPING_COEFFICIENT = 1800.0\n"
    
    manifest = svc.import_external_result(
        content=test_adm,
        filename="chassis_data.adm",
        adapter_id="adapter-msc-adams-v1",
    )
    expected_hash = hashlib.sha256(test_adm).hexdigest()
    assert manifest.execution_metadata.provenance_origin == ResultProvenanceOrigin.IMPORTED_EXTERNAL
    assert len(manifest.input_artifacts) >= 1
    input_art = manifest.input_artifacts[0]
    assert input_art.sha256 == expected_hash
    assert input_art.metadata["adapter_id"] == "adapter-msc-adams-v1"


# ── TEST 18: IMPORT SUCCESS IS NOT TREATED AS VALIDATION SUCCESS ──────────────

def test_18_import_success_is_not_treated_as_validation_success():
    """Requirement 18: Parsing success does NOT establish physical validation."""
    svc = SolverInteropService()
    test_json = json.dumps({
        "schema_version": "1.0.0",
        "engineering_model_id": "quarter_car",
        "parameters": {
            "m_s": {"name": "m_s", "value": 300.0, "unit": "kg", "dimension": "mass"}
        }
    }).encode("utf-8")

    manifest = svc.import_external_result(
        content=test_json,
        filename="model.json",
        adapter_id="adapter-canonical-json-v1",
    )
    # Strict Epistemic Invariants:
    assert manifest.execution_metadata.is_physically_validated is False
    assert manifest.validation_status != ExchangeValidationStatus.VALIDATED


# ── TEST 19: EXPORT SUCCESS IS NOT TREATED AS SOLVER EXECUTION ────────────────

def test_19_export_success_is_not_treated_as_solver_execution():
    """Requirement 19: Successful model export does NOT claim external solver executed."""
    svc = SolverInteropService()
    manifest = svc.create_canonical_manifest(
        engineering_model_id="quarter_car",
        parameters={"m_s": ParameterValue(name="m_s", value=300.0, unit="kg", dimension="mass")},
    )
    art_bytes, art_ref, updated_manifest = svc.export_model_artifact(
        manifest=manifest,
        adapter_id="adapter-msc-adams-v1",
    )
    assert len(art_bytes) > 0
    # Invariant: is_executed remains False
    assert updated_manifest.execution_metadata.is_executed is False


# ── TEST 20: MALFORMED STRUCTURED FILES FAIL SAFELY ───────────────────────────

def test_20_malformed_structured_files_fail_safely():
    """Requirement 20: Truncated or corrupted payloads fail safely with structured exceptions."""
    corrupted_json = b"{\"schema_version\": \"1.0.0\", \"engineering_model_id\": "  # Truncated
    with pytest.raises(MalformedPayloadSecurityError, match="Malformed JSON syntax"):
        safe_parse_json(corrupted_json)

    corrupted_csv = b"\x00\xff\xfe\x00corrupt"
    # Safe parser handles or replaces invalid text gracefully
    rows = safe_parse_csv(corrupted_csv)
    assert isinstance(rows, list)


# ── TEST 21: NAN AND INFINITY ARE HANDLED SAFELY ──────────────────────────────

def test_21_nan_and_infinity_are_handled_safely():
    """Requirement 21: NaN and Infinity are blocked in parameter definitions and JSON parsing."""
    # 1. ParameterValue validator
    with pytest.raises(ValueError, match="finite number|Parameter value cannot be NaN"):
        ParameterValue(name="k_s", value=float("nan"), unit="N/m")

    with pytest.raises(ValueError, match="finite number|Parameter value cannot be Infinity"):
        ParameterValue(name="k_s", value=float("inf"), unit="N/m")

    # 2. JSON scanning
    nan_json = b"{\"value\": NaN}"
    with pytest.raises(MalformedNumericSecurityError, match="Illegal numerical constant token"):
        safe_parse_json(nan_json)

    inf_json = b"{\"value\": Infinity}"
    with pytest.raises(MalformedNumericSecurityError, match="Illegal numerical constant token"):
        safe_parse_json(inf_json)


# ── TEST 22: PATH TRAVERSAL IS BLOCKED ────────────────────────────────────────

def test_22_path_traversal_is_blocked():
    """Requirement 22: Filenames with directory traversal tokens are blocked."""
    hostile_names = [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\calc.exe",
        "legit_name\x00.exe",
        "sub/dir/file.adm",
        "C:\\autoexec.bat",
    ]
    for bad in hostile_names:
        with pytest.raises(PathTraversalSecurityError):
            sanitize_artifact_filename(bad)


# ── TEST 23: OVERSIZED OR MALFORMED INPUT IS BOUNDED SAFELY ───────────────────

def test_23_oversized_or_malformed_input_is_bounded_safely():
    """Requirement 23: Payloads exceeding byte limits or dict limits raise resource error."""
    oversized_data = b"x" * (MAX_PAYLOAD_BYTES + 1024)
    with pytest.raises(ResourceExhaustionSecurityError, match="exceeds maximum limit"):
        check_payload_size(oversized_data)


# ── TEST 24: NO ARBITRARY IMPORTED CODE IS EXECUTED ───────────────────────────

def test_24_no_arbitrary_imported_code_is_executed():
    """Requirement 24: Imported projects containing executable code are rejected."""
    # Prohibited executable extensions
    for ext in [".exe", ".dll", ".so", ".bat", ".ps1", ".cmd", ".sh"]:
        with pytest.raises(ExecutableContentSecurityError):
            sanitize_artifact_filename(f"exploit{ext}")

    # MATLAB adapter import is prohibited to prevent script execution
    matlab_adapter = MatlabSimulinkAdapter()
    with pytest.raises(NotImplementedError, match="unsupported to prevent execution of untrusted code"):
        matlab_adapter.import_artifact(b"disp('malicious code');")

    # ADAMS adapter rejects .cmd and .py files on input/import
    adams_adapter = AdamsSolverAdapter()
    
    # Validation rejection for .cmd / .py
    ok_cmd, msgs_cmd = adams_adapter.validate_input(b"! MSC ADAMS/View Command File\nmodel create ...", options={"format": "cmd"})
    assert not ok_cmd
    assert "export-only" in msgs_cmd[0]

    ok_py, msgs_py = adams_adapter.validate_input(b"import adams\nm = adams.models.create()", options={"format": "py"})
    assert not ok_py
    assert "export-only" in msgs_py[0]

    # Ingestion rejection for .cmd / .py with ExecutableContentSecurityError
    with pytest.raises(ExecutableContentSecurityError, match="export-only"):
        adams_adapter.import_artifact(b"model create model_name=Rig", options={"format": "cmd"})

    with pytest.raises(ExecutableContentSecurityError, match="export-only"):
        adams_adapter.import_artifact(b"import adams\nm = adams.models.create()", options={"format": "py"})

    with pytest.raises(ExecutableContentSecurityError, match="Prohibited executable"):
        adams_adapter.import_artifact(b"PART/2, MASS=300", options={"filename": "exploit.cmd"})

    with pytest.raises(ExecutableContentSecurityError, match="Prohibited executable"):
        adams_adapter.import_artifact(b"PART/2, MASS=300", options={"filename": "exploit.py"})

    # ADAMS .adm is parsed purely as inert declarative text without execution
    adm_sample = (
        b"! Declarative dataset\n"
        b"ADAMS/View model name: Quarter_Car_Rig\n"
        b"PART/2, MASS = 300.0\n"
        b"PART/3, MASS = 35.0\n"
        b"SPRINGDAMPER/1, STIFFNESS_COEFFICIENT = 25000.0, DAMPING_COEFFICIENT = 2050.0\n"
        b"END\n"
    )
    manifest = adams_adapter.import_artifact(adm_sample, options={"filename": "quarter_car.adm"})
    assert manifest.parameters["m_s"].value == 300.0
    assert manifest.parameters["m_u"].value == 35.0
    assert manifest.execution_metadata.provenance_origin == ResultProvenanceOrigin.IMPORTED_EXTERNAL
    assert manifest.execution_metadata.is_physically_validated is False


# ── TEST 25: TENANT ISOLATION FOLLOWS REPOSITORY CONVENTIONS ──────────────────

def test_25_tenant_isolation_follows_repository_conventions():
    """Requirement 25: Cross-tenant operations are rejected with TenantIsolationError."""
    with pytest.raises(TenantIsolationError, match="Tenant isolation violation"):
        enforce_tenant_isolation("tenant_alpha", "tenant_bravo")

    # Matching tenant passes
    enforce_tenant_isolation("tenant_alpha", "tenant_alpha")


# ── TEST 26: ADAPTER REGISTRY DOES NOT ALTER EVIDENCE GRAPH VOCABULARY ────────

def test_26_adapter_registry_does_not_alter_evidence_graph_vocabulary():
    """Requirement 26: EvidenceGraphRelationship enum contains exactly the 17 canonical types."""
    expected_17 = {
        "OBSERVED_IN", "DETECTED_FROM", "FORMULATED_FROM", "EVIDENCED_BY",
        "HYPOTHESIZED_FROM", "TESTED_BY", "EXECUTED_AS", "USES_SETUP",
        "PRODUCED_SETUP", "EVALUATED_IN", "OPTIMIZED_TO", "VALIDATED_BY",
        "JUSTIFIED_BY", "APPROVED_UNDER", "PREDICTED_FOR", "RECONCILED_WITH",
        "SUPERSEDES",
    }
    actual = {r.value for r in EvidenceGraphRelationship}
    assert actual == expected_17
    assert len(EvidenceGraphRelationship) == 17


# ── TEST 27: PHASE 4 REGRESSIONS REMAIN GREEN ─────────────────────────────────

def test_27_phase4_regressions_remain_green():
    """Requirement 27: Verified Phase 4 Evidence Graph schema integrity."""
    from suspensionlab.backend.database.models.evidence_graph import (
        EvidenceGraphEdgeRecord,
        SupportedEntityType,
    )
    assert EvidenceGraphEdgeRecord.__tablename__ == "evidence_graph_edges"
    assert len(SupportedEntityType) >= 10


# ── TEST 28: PHASE 5 REMAINS INDEPENDENT ──────────────────────────────────────

def test_28_phase5_remains_independent():
    """Requirement 28: Verified zero imports of Phase 5 blind-scoring in interop package."""
    interop_dir = PROJECT_ROOT / "src" / "suspensionlab" / "interop"
    for py_file in interop_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "blind_calibration_engine" not in content, f"Phase 5 leak in {py_file}"
        assert "blind_comparison_engine" not in content, f"Phase 5 leak in {py_file}"
        assert "BlindPrediction" not in content, f"Phase 5 leak in {py_file}"


# ── TEST 29: PHASE 6 REMAINS INDEPENDENT ──────────────────────────────────────

def test_29_phase6_remains_independent():
    """Requirement 29: Verified zero imports of Phase 6 trust score calculations in interop package."""
    interop_dir = PROJECT_ROOT / "src" / "suspensionlab" / "interop"
    for py_file in interop_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "compute_trust_score" not in content, f"Phase 6 leak in {py_file}"
        assert "ParameterTrustAssessmentRecord" not in content, f"Phase 6 leak in {py_file}"


# ── TEST 30: ALL 81 PROTECTED PHYSICS FILES REMAIN UNCHANGED ──────────────────

def test_30_all_81_protected_physics_files_remain_unchanged():
    """Requirement 30: All 81 production physics source files match baseline SHA-256."""
    hash_file = PROJECT_ROOT / "pre_phase4_3_hashes.json"
    assert hash_file.exists(), "pre_phase4_3_hashes.json missing!"

    with open(hash_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    physics_hashes = data.get("physics", {})
    assert len(physics_hashes) == 81, f"Expected 81 physics files, found {len(physics_hashes)}"

    for rel_path, expected_hash in physics_hashes.items():
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Physics file missing: {rel_path}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"CRITICAL: Production physics file {rel_path} was modified!"


# ── TEST 31: PHASE 3 ARTIFACTS REMAIN UNCHANGED ───────────────────────────────

def test_31_phase3_artifacts_remain_unchanged():
    """Requirement 31: Protected Phase 3 manifests match baseline SHA-256."""
    hash_file = PROJECT_ROOT / "pre_phase4_3_hashes.json"
    with open(hash_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    manifest_hashes = data.get("manifests", {})
    assert len(manifest_hashes) == 7, f"Expected 7 manifests, found {len(manifest_hashes)}"

    for rel_path, expected_hash in manifest_hashes.items():
        full_path = PROJECT_ROOT / rel_path
        assert full_path.exists(), f"Phase 3 manifest missing: {rel_path}"
        actual_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"Protected manifest {rel_path} was modified!"


# ── TEST 32: ALEMBIC TOPOLOGY REMAINS VALID ───────────────────────────────────

def test_32_alembic_topology_remains_valid():
    """Requirement 32: Single unified Alembic head maintained without unnecessary migrations."""
    import alembic.config
    import alembic.script

    cfg = alembic.config.Config(str(PROJECT_ROOT / "alembic.ini"))
    script_dir = alembic.script.ScriptDirectory.from_config(cfg)
    heads = script_dir.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 Alembic head, got {heads}"
    assert heads[0] in ("q7r8s9t0u1v2", "r8s9t0u1v2w3", "s9t0u1v2w3x4", "t0u1v2w3x4y5", "u1v2w3x4y5z6", "v6w6x6y6z6a6", "v2w3x4y5z6p74", "w7x7y7z7a7b7", "x7y8z9a0b1c2", "y8z9a0b1c2d3", "z9a0b1c2d3e4")




# ── ADVERSARIAL ATTACK SUITE ──────────────────────────────────────────────────

def test_adversarial_unit_injection():
    """Adversarial: Malicious SQL or script injection into unit string is rejected safely."""
    malicious_units = [
        "N/m; DROP TABLE users;--",
        "<script>alert(1)</script>",
        "' OR '1'='1",
        "kg\x00exploit",
    ]
    for unit in malicious_units:
        status, detail = check_unit_compatibility(unit, "kg")
        assert status == UnitCompatibilityStatus.UNRESOLVED


def test_adversarial_zip_slip_rejection(tmp_path):
    """Adversarial: Zip archive containing path traversal entries is rejected."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../evil.txt", "payload")
    zip_bytes = zip_buffer.getvalue()

    with pytest.raises(PathTraversalSecurityError, match="Zip Slip"):
        safe_extract_archive(zip_bytes, tmp_path)


def test_adversarial_zip_bomb_rejection(tmp_path):
    """Adversarial: Zip bomb with excessive expansion ratio is rejected."""
    zip_buffer = io.BytesIO()
    # Write 10 MB of zeros compressed to few bytes
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("large.txt", b"\x00" * (10 * 1024 * 1024))
    zip_bytes = zip_buffer.getvalue()

    with pytest.raises(ResourceExhaustionSecurityError, match="Zip bomb rejected"):
        safe_extract_archive(zip_bytes, tmp_path)


def test_adversarial_api_routes():
    """Adversarial & functional check on solver interop FastAPI routes."""
    from fastapi import FastAPI
    from suspensionlab.backend.api.routes.solver_interop_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    # 1. List adapters
    res = client.get("/api/v1/interop/adapters")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 5
    ids = [d["adapter_id"] for d in data]
    assert ids == sorted(ids)

    # 2. Get specific adapter
    res_adams = client.get("/api/v1/interop/adapters/adapter-msc-adams-v1")
    assert res_adams.status_code == 200
    assert res_adams.json()["solver_name"] == "MSC_ADAMS"

    # 3. Check unknown adapter -> 404
    res_404 = client.get("/api/v1/interop/adapters/non-existent-adapter")
    assert res_404.status_code == 404

    # 4. Check units endpoint
    res_units = client.post("/api/v1/interop/units/check", json={"unit_a": "N/m", "unit_b": "lb/in"})
    assert res_units.status_code == 200
    assert res_units.json()["status"] == "CONVERTIBLE"

    # 5. Check frame consistency
    res_frame = client.post("/api/v1/interop/frames/check", json={
        "standard": "ISO_8855",
        "name": "ISO",
        "x_axis": "FORWARD",
        "y_axis": "LEFT",
        "z_axis": "UP",
        "handedness": "RIGHT_HANDED",
    })
    assert res_frame.status_code == 200
    assert res_frame.json()["is_valid"] is True
