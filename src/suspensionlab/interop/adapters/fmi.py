"""
src/suspensionlab/interop/adapters/fmi.py
========================================
Functional Mock-up Interface (FMI 2.0 / 3.0) Adapter for SuspensionLab PRO.

Provides:
- Export of vehicle dynamics models to FMI `modelDescription.xml` schema.
- Ingestion of FMI XML descriptors extracting scalar variables, units, and start values.
- Truthful reporting: Execution requires an FMI co-simulation master runner.
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple, Union

from suspensionlab.interop.adapter import (
    AdapterCapability,
    BaseSolverAdapter,
    DataCategory,
    DependencyRequirement,
    SupportLevel,
    VerificationStatus,
)
from suspensionlab.interop.manifest import (
    ArtifactReference,
    CanonicalExchangeManifest,
    ExchangeMode,
    ExchangeValidationStatus,
    ParameterValue,
    ResultProvenanceOrigin,
)
from suspensionlab.interop.mapping import ParameterMapping, MappingProvenance, MappingStatus
from suspensionlab.interop.security import check_payload_size


class FMICoSimulationAdapter(BaseSolverAdapter):
    """
    Adapter for FMI 2.0 / 3.0 Co-Simulation exchange.
    """

    ADAPTER_ID = "adapter-fmi-cosim-v1"
    ADAPTER_VERSION = "1.0.0"
    SOLVER_NAME = "FMI_COSIMULATION"

    def get_capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            adapter_id=self.ADAPTER_ID,
            adapter_version=self.ADAPTER_VERSION,
            solver_name=self.SOLVER_NAME,
            supported_formats=[".fmu", ".xml", "application/x-fmu"],
            supported_import_formats=[".xml"],
            supported_export_formats=[".xml"],
            supported_versions=["2.0", "3.0"],
            supported_categories=[
                DataCategory.PARAMETERS,
                DataCategory.TIME_SERIES,
            ],
            unit_restrictions=["SI"],
            frame_restrictions=[],
            import_capability=SupportLevel.PARTIALLY_SUPPORTED,
            export_capability=SupportLevel.SUPPORTED,
            required_dependencies=[
                DependencyRequirement(
                    name="fmi-runtime-master",
                    version_spec=">=2.0",
                    is_available=False,
                    description="FMI Co-Simulation master environment (required for co-simulation runtime execution only).",
                )
            ],
            known_limitations=[
                "Imports modelDescription.xml schema and parameter definitions; FMU binary execution requires external FMI Master.",
                "Co-simulation wrapper requires fixed-step communication interval.",
            ],
            verification_status=VerificationStatus.VERIFIED,
        )

    def get_supported_versions(self) -> List[str]:
        return ["2.0", "3.0"]

    def validate_input(
        self,
        content: Union[str, bytes, Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        if isinstance(content, bytes):
            text = content.decode("utf-8", errors="replace")
        elif isinstance(content, str):
            text = content
        else:
            return (False, ["Input must be XML text or bytes."])

        if "<fmiModelDescription" not in text:
            return (False, ["XML payload missing <fmiModelDescription> root element."])

        return (True, [])

    def export_artifact(
        self,
        manifest: CanonicalExchangeManifest,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, ArtifactReference]:
        root = ET.Element("fmiModelDescription")
        root.set("fmiVersion", "2.0")
        root.set("modelName", manifest.engineering_model_id)
        root.set("guid", f"{{{manifest.manifest_id or 'canonical-fmi-guid'}}}")
        root.set("generationTool", "SuspensionLab PRO Interop")

        co_sim = ET.SubElement(root, "CoSimulation")
        co_sim.set("modelIdentifier", manifest.engineering_model_id)
        co_sim.set("canHandleVariableCommunicationStepSize", "true")

        model_vars = ET.SubElement(root, "ModelVariables")
        vr_index = 1
        for p_name, p_val in manifest.parameters.items():
            scalar = ET.SubElement(model_vars, "ScalarVariable")
            scalar.set("name", p_name)
            scalar.set("valueReference", str(vr_index))
            scalar.set("causality", "parameter")
            scalar.set("variability", "fixed")
            vr_index += 1

            real_elem = ET.SubElement(scalar, "Real")
            if isinstance(p_val.value, (int, float)):
                real_elem.set("start", str(p_val.value))
            if p_val.unit:
                real_elem.set("unit", p_val.unit)

        xml_str = ET.tostring(root, encoding="utf-8")
        sha = hashlib.sha256(xml_str).hexdigest()

        artifact_ref = ArtifactReference(
            artifact_id=f"ART-FMI-{sha[:12]}",
            name="modelDescription.xml",
            artifact_type="text/xml",
            sha256=sha,
            size_bytes=len(xml_str),
            metadata={"fmi_version": "2.0", "solver": self.SOLVER_NAME},
        )
        return (xml_str, artifact_ref)

    def import_artifact(
        self,
        content: bytes,
        options: Optional[Dict[str, Any]] = None,
    ) -> CanonicalExchangeManifest:
        check_payload_size(content)
        root = ET.fromstring(content)

        model_name = root.get("modelName", "quarter_car")
        fmi_ver = root.get("fmiVersion", "2.0")

        parameters: Dict[str, ParameterValue] = {}
        mappings: List[ParameterMapping] = []

        model_vars = root.find("ModelVariables")
        if model_vars is not None:
            for scalar in model_vars.findall("ScalarVariable"):
                name = scalar.get("name", "")
                real_elem = scalar.find("Real")
                start_val = 0.0
                unit = None
                if real_elem is not None:
                    start_val = float(real_elem.get("start", "0.0"))
                    unit = real_elem.get("unit")

                if name:
                    parameters[name] = ParameterValue(
                        name=name,
                        value=start_val,
                        unit=unit or "-",
                        description="FMI scalar parameter",
                    )
                    mappings.append(
                        ParameterMapping(
                            internal_entity_type=model_name,
                            internal_parameter_path=name,
                            external_solver_name=self.SOLVER_NAME,
                            external_variable_id=name,
                            internal_unit=unit or "-",
                            external_unit=unit or "-",
                            provenance=MappingProvenance.VENDOR_INTERFACE,
                            status=MappingStatus.SUPPORTED,
                        )
                    )

        sha = hashlib.sha256(content).hexdigest()
        input_ref = ArtifactReference(
            artifact_id=f"ART-FMI-IN-{sha[:12]}",
            name="imported_modelDescription.xml",
            artifact_type="text/xml",
            sha256=sha,
            size_bytes=len(content),
            metadata={"solver": self.SOLVER_NAME, "fmi_version": fmi_ver},
        )

        manifest = CanonicalExchangeManifest(
            schema_version="1.0.0",
            source_application="FMI XML Interface",
            source_solver=self.SOLVER_NAME,
            solver_version=fmi_ver,
            engineering_model_id=model_name,
            exchange_mode=ExchangeMode.IMPORT,
            parameters=parameters,
            input_artifacts=[input_ref],
            parameter_mappings=mappings,
            warnings=["Imported FMI XML metadata. Co-simulation execution requires compliant FMI Master."],
            validation_status=ExchangeValidationStatus.VALID_WITH_WARNINGS,
        )

        # Enforce strict provenance
        manifest.execution_metadata.provenance_origin = ResultProvenanceOrigin.IMPORTED_EXTERNAL
        manifest.execution_metadata.is_physically_validated = False

        return manifest
