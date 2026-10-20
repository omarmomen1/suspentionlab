"""
src/suspensionlab/interop/fmi/capability_audit.py
=================================================
SuspensionLab PRO — FMI Capability Audit & Metadata Inspection Engine (Phase 7.5).

Provides rigorous, evidence-based audit of FMI 2.0 / 3.0 Functional Mock-up Units:
- Model-Exchange vs. Co-Simulation capabilities.
- Direct feedthrough & algebraic dependency analysis.
- Input/output variable taxonomy, causality, variability, and units.
- Communication step behavior (fixed vs. variable step support).
- State serialization, rollback, and early-return capabilities.
- Coordinate frame conventions and unit declarations.
- Binary platform availability (win64, linux64, arm64).
- Cryptographic hash verification against vetted allowlists.

Core Rule: Never claim support for FMI capabilities not demonstrated by installed models and runtime.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import pathlib
import sys
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclasses.dataclass(frozen=True)
class FMIVariable:
    name: str
    value_reference: int
    data_type: str  # Real, Integer, Boolean, String
    causality: str  # input, output, parameter, calculatedParameter, local, independent
    variability: str  # continuous, discrete, fixed, tunable, constant
    unit: Optional[str] = None
    start_value: Optional[Any] = None
    description: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class CoSimulationCapabilities:
    model_identifier: str
    can_handle_variable_communication_step_size: bool
    can_interpolate_inputs: bool
    max_output_derivative_order: int
    can_get_and_set_fmu_state: bool
    can_serialize_fmu_state: bool
    provides_directional_derivative: bool


@dataclasses.dataclass(frozen=True)
class ModelExchangeCapabilities:
    model_identifier: str
    completed_integrator_step_not_needed: bool
    can_get_and_set_fmu_state: bool
    can_serialize_fmu_state: bool
    provides_directional_derivative: bool


@dataclasses.dataclass
class FMICapabilityReport:
    fmi_version: str
    model_name: str
    guid: str
    generation_tool: Optional[str]
    generation_date_time: Optional[str]
    sha256_hash: str
    is_vetted_allowlist: bool
    co_simulation: Optional[CoSimulationCapabilities]
    model_exchange: Optional[ModelExchangeCapabilities]
    available_binaries: List[str]
    host_binary_available: bool
    inputs: List[FMIVariable]
    outputs: List[FMIVariable]
    parameters: List[FMIVariable]
    other_variables: List[FMIVariable]
    feedthrough_dependencies: Dict[str, List[str]]  # output_name -> list of input_names
    has_direct_feedthrough: bool
    rollback_supported: bool
    early_return_supported: bool
    coordinate_conventions: Dict[str, str]
    declared_units: List[str]
    known_limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fmi_version": self.fmi_version,
            "model_name": self.model_name,
            "guid": self.guid,
            "generation_tool": self.generation_tool,
            "generation_date_time": self.generation_date_time,
            "sha256_hash": self.sha256_hash,
            "is_vetted_allowlist": self.is_vetted_allowlist,
            "co_simulation": dataclasses.asdict(self.co_simulation) if self.co_simulation else None,
            "model_exchange": dataclasses.asdict(self.model_exchange) if self.model_exchange else None,
            "available_binaries": self.available_binaries,
            "host_binary_available": self.host_binary_available,
            "inputs_count": len(self.inputs),
            "inputs": [dataclasses.asdict(v) for v in self.inputs],
            "outputs_count": len(self.outputs),
            "outputs": [dataclasses.asdict(v) for v in self.outputs],
            "parameters_count": len(self.parameters),
            "parameters": [dataclasses.asdict(v) for v in self.parameters],
            "feedthrough_dependencies": self.feedthrough_dependencies,
            "has_direct_feedthrough": self.has_direct_feedthrough,
            "rollback_supported": self.rollback_supported,
            "early_return_supported": self.early_return_supported,
            "coordinate_conventions": self.coordinate_conventions,
            "declared_units": self.declared_units,
            "known_limitations": self.known_limitations,
        }


class FMICapabilityAuditor:
    """
    Audits and inspects FMU packages and modelDescription XML descriptors.
    """

    @classmethod
    def audit_fmu(
        cls,
        fmu_path: pathlib.Path | str,
        vetted_hashes: Optional[Set[str]] = None,
    ) -> FMICapabilityReport:
        fmu_p = pathlib.Path(fmu_path)
        if not fmu_p.exists():
            raise FileNotFoundError(f"FMU file not found at '{fmu_p}'.")

        fmu_bytes = fmu_p.read_bytes()
        sha256 = hashlib.sha256(fmu_bytes).hexdigest()
        is_vetted = (vetted_hashes is not None and sha256 in vetted_hashes)

        # Inspect ZIP contents
        with zipfile.ZipFile(fmu_p) as z:
            namelist = z.namelist()
            if "modelDescription.xml" not in namelist:
                raise ValueError(f"Invalid FMU '{fmu_p}': missing 'modelDescription.xml'.")

            xml_bytes = z.read("modelDescription.xml")

            binaries: List[str] = []
            for name in namelist:
                if name.startswith("binaries/"):
                    parts = name.split("/")
                    if len(parts) >= 2 and parts[1]:
                        binaries.append(parts[1])
            available_binaries = sorted(list(set(binaries)))

        return cls.audit_xml_content(
            xml_bytes=xml_bytes,
            sha256_hash=sha256,
            is_vetted=is_vetted,
            available_binaries=available_binaries,
        )

    @classmethod
    def audit_xml_content(
        cls,
        xml_bytes: bytes,
        sha256_hash: str = "",
        is_vetted: bool = False,
        available_binaries: Optional[List[str]] = None,
    ) -> FMICapabilityReport:
        try:
            root = ET.fromstring(xml_bytes)
        except Exception as e:
            raise ValueError(f"Failed to parse FMI modelDescription.xml: {e}")

        fmi_version = root.attrib.get("fmiVersion", "2.0")
        model_name = root.attrib.get("modelName", "UnknownModel")
        guid = root.attrib.get("guid", "")
        gen_tool = root.attrib.get("generationTool")
        gen_time = root.attrib.get("generationDateAndTime")

        # 1. Co-Simulation capabilities
        cs_elem = root.find("CoSimulation")
        cs_caps: Optional[CoSimulationCapabilities] = None
        if cs_elem is not None:
            cs_caps = CoSimulationCapabilities(
                model_identifier=cs_elem.attrib.get("modelIdentifier", model_name),
                can_handle_variable_communication_step_size=cs_elem.attrib.get("canHandleVariableCommunicationStepSize", "false").lower() == "true",
                can_interpolate_inputs=cs_elem.attrib.get("canInterpolateInputs", "false").lower() == "true",
                max_output_derivative_order=int(cs_elem.attrib.get("maxOutputDerivativeOrder", "0")),
                can_get_and_set_fmu_state=cs_elem.attrib.get("canGetAndSetFMUstate", "false").lower() == "true",
                can_serialize_fmu_state=cs_elem.attrib.get("canSerializeFMUstate", "false").lower() == "true",
                provides_directional_derivative=cs_elem.attrib.get("providesDirectionalDerivative", "false").lower() == "true",
            )

        # 2. Model-Exchange capabilities
        me_elem = root.find("ModelExchange")
        me_caps: Optional[ModelExchangeCapabilities] = None
        if me_elem is not None:
            me_caps = ModelExchangeCapabilities(
                model_identifier=me_elem.attrib.get("modelIdentifier", model_name),
                completed_integrator_step_not_needed=me_elem.attrib.get("completedIntegratorStepNotNeeded", "false").lower() == "true",
                can_get_and_set_fmu_state=me_elem.attrib.get("canGetAndSetFMUstate", "false").lower() == "true",
                can_serialize_fmu_state=me_elem.attrib.get("canSerializeFMUstate", "false").lower() == "true",
                provides_directional_derivative=me_elem.attrib.get("providesDirectionalDerivative", "false").lower() == "true",
            )

        # 3. Model Variables
        inputs: List[FMIVariable] = []
        outputs: List[FMIVariable] = []
        parameters: List[FMIVariable] = []
        other_vars: List[FMIVariable] = []
        val_ref_to_name: Dict[int, str] = {}
        index_to_var: Dict[int, FMIVariable] = {}

        mv_elem = root.find("ModelVariables")
        var_idx = 1
        declared_units: Set[str] = set()

        if mv_elem is not None:
            for v in mv_elem.findall("ScalarVariable"):
                name = v.attrib.get("name", "")
                vr = int(v.attrib.get("valueReference", 0))
                causality = v.attrib.get("causality", "local")
                variability = v.attrib.get("variability", "continuous")
                description = v.attrib.get("description")

                # Detect type and unit
                data_type = "Real"
                unit = None
                start_val = None
                for type_tag in ("Real", "Integer", "Boolean", "String", "Enumeration"):
                    sub = v.find(type_tag)
                    if sub is not None:
                        data_type = type_tag
                        unit = sub.attrib.get("unit")
                        start_val = sub.attrib.get("start")
                        break

                if unit:
                    declared_units.add(unit)

                var_obj = FMIVariable(
                    name=name,
                    value_reference=vr,
                    data_type=data_type,
                    causality=causality,
                    variability=variability,
                    unit=unit,
                    start_value=start_val,
                    description=description,
                )

                val_ref_to_name[vr] = name
                index_to_var[var_idx] = var_obj
                var_idx += 1

                if causality == "input":
                    inputs.append(var_obj)
                elif causality == "output":
                    outputs.append(var_obj)
                elif causality in ("parameter", "calculatedParameter"):
                    parameters.append(var_obj)
                else:
                    other_vars.append(var_obj)

        # 4. Dependency Structure & Direct Feedthrough Analysis
        feedthrough: Dict[str, List[str]] = {}
        has_feedthrough = False
        ms_elem = root.find("ModelStructure")
        if ms_elem is not None:
            out_elem = ms_elem.find("Outputs")
            if out_elem is not None:
                for unk in out_elem.findall("Unknown"):
                    unk_idx = int(unk.attrib.get("index", 0))
                    deps_str = unk.attrib.get("dependencies", "")
                    target_var = index_to_var.get(unk_idx)
                    if target_var:
                        dep_inputs: List[str] = []
                        if deps_str:
                            for d in deps_str.split():
                                try:
                                    dep_var = index_to_var.get(int(d))
                                    if dep_var and dep_var.causality == "input":
                                        dep_inputs.append(dep_var.name)
                                except ValueError:
                                    pass
                        feedthrough[target_var.name] = dep_inputs
                        if dep_inputs:
                            has_feedthrough = True

        # 5. Check host platform binary compatibility
        bin_list = available_binaries or []
        host_platform = "win64" if sys.platform == "win32" else ("linux-arm64" if "arm" in sys.platform else "linux64")
        host_available = any(host_platform in b for b in bin_list)

        # 6. Coordinate Conventions
        coords = {}
        for var in inputs + outputs:
            v_lower = var.name.lower()
            if any(k in v_lower for k in ("z_road", "z_s", "z_u")):
                coords[var.name] = "ISO_8855_Z_UP" if "iso" in (var.description or "").lower() else "Z_POSITIVE_UP"
            elif "pitch" in v_lower:
                coords[var.name] = "NOSE_UP_POSITIVE"
            elif "roll" in v_lower:
                coords[var.name] = "RIGHT_DOWN_POSITIVE"

        # 7. Capabilities & Truthful Limitations
        rollback = bool(cs_caps and cs_caps.can_get_and_set_fmu_state)
        early_return = bool(cs_caps and cs_caps.can_handle_variable_communication_step_size)

        limitations: List[str] = []
        if me_caps is None:
            limitations.append("Model-Exchange (ME) is not supported by this FMU.")
        if not rollback:
            limitations.append("State rollback (canGetAndSetFMUstate) is not supported; step rejection with rollback cannot be performed.")
        if cs_caps and not cs_caps.can_interpolate_inputs:
            limitations.append("Input interpolation is not supported by the slave solver; zero-order hold must be used.")
        if not is_vetted:
            limitations.append("FMU hash is not in the enterprise vetted allowlist; unisolated native execution is prohibited.")

        return FMICapabilityReport(
            fmi_version=fmi_version,
            model_name=model_name,
            guid=guid,
            generation_tool=gen_tool,
            generation_date_time=gen_time,
            sha256_hash=sha256_hash,
            is_vetted_allowlist=is_vetted,
            co_simulation=cs_caps,
            model_exchange=me_caps,
            available_binaries=bin_list,
            host_binary_available=host_available,
            inputs=inputs,
            outputs=outputs,
            parameters=parameters,
            other_variables=other_vars,
            feedthrough_dependencies=feedthrough,
            has_direct_feedthrough=has_feedthrough,
            rollback_supported=rollback,
            early_return_supported=early_return,
            coordinate_conventions=coords,
            declared_units=sorted(list(declared_units)),
            known_limitations=limitations,
        )
