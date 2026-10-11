"""
physics/fmi_exporter.py
=======================
SuspensionLab PRO — Functional Mock-up Interface (FMI 2.0 / 3.0) Exporter

Generates standard FMI-compliant `modelDescription.xml` and co-simulation interface wrappers
for integrating SuspensionLab vehicle models into enterprise simulation ecosystems
(MATLAB/Simulink, IPG CarMaker, VI-CarRealTime, Adams, dSPACE).

Supported FMI Standards:
------------------------
- FMI 2.0 Co-Simulation (Standard industry interchange)
- FMI 3.0 Co-Simulation (Next-gen multi-rate co-simulation)

Model Variables Managed:
------------------------
- Model inputs (road displacement, road vertical velocity)
- Model outputs (sprung mass displacement, unsprung mass displacement, suspension travel, tire load, sprung body acceleration, simulation time)
- Model parameters (sprung mass, unsprung mass, spring rate, damping rate, tire stiffness, motion ratio, tire damping)
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import xml.dom.minidom
import pathlib


@dataclass
class FMIVariable:
    """Scalar variable definition for FMI modelDescription.xml."""
    name: str
    value_reference: int
    data_type: str = "Real"            # "Real", "Integer", "Boolean", "String"
    causality: str = "local"           # "input", "output", "parameter", "calculatedParameter", "local"
    variability: str = "continuous"    # "constant", "fixed", "tunable", "discrete", "continuous"
    initial: Optional[str] = None      # "exact", "approx", "calculated"
    start: Optional[Any] = None
    unit: Optional[str] = None
    description: Optional[str] = None


@dataclass
class FMIModelDescription:
    """FMI Model Description container."""
    model_name: str
    guid: str
    fmi_version: str = "2.0"           # "2.0" or "3.0"
    generation_tool: str = "SuspensionLab PRO FMI Exporter v2.0"
    description: str = "SuspensionLab Multibody Vehicle Dynamics Co-Simulation Model"
    variables: List[FMIVariable] = field(default_factory=list)

    def generate_xml(self) -> str:
        """Generate canonical FMI XML model description."""
        root = ET.Element("fmiModelDescription")
        root.set("fmiVersion", self.fmi_version)
        root.set("modelName", self.model_name)
        root.set("guid", self.guid)
        root.set("generationTool", self.generation_tool)
        root.set("generationDateAndTime", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        root.set("variableNamingConvention", "flat")
        root.set("description", self.description)
        root.set("numberOfEventIndicators", "0")

        # Co-simulation capability element
        co_sim = ET.SubElement(root, "CoSimulation")
        co_sim.set("modelIdentifier", self.model_name)
        co_sim.set("canHandleVariableCommunicationStepSize", "true")
        co_sim.set("canInterpolateInputs", "true")
        co_sim.set("maxOutputDerivativeOrder", "0")

        # Unit Definitions
        unit_defs = ET.SubElement(root, "UnitDefinitions")
        units_spec = [
            ("kg", {"kg": "1"}),
            ("N/m", {"kg": "1", "s": "-2"}),
            ("Ns/m", {"kg": "1", "s": "-1"}),
            ("m", {"m": "1"}),
            ("m/s", {"m": "1", "s": "-1"}),
            ("m/s2", {"m": "1", "s": "-2"}),
            ("N", {"kg": "1", "m": "1", "s": "-2"}),
            ("s", {"s": "1"}),
            ("-", {}),
        ]
        for uname, base_dict in units_spec:
            unit_el = ET.SubElement(unit_defs, "Unit")
            unit_el.set("name", uname)
            if base_dict:
                base_el = ET.SubElement(unit_el, "BaseUnit")
                for k, v in base_dict.items():
                    base_el.set(k, v)

        # Model variables
        model_vars = ET.SubElement(root, "ModelVariables")
        for v in self.variables:
            var_elem = ET.SubElement(model_vars, "ScalarVariable")
            var_elem.set("name", v.name)
            var_elem.set("valueReference", str(v.value_reference))
            var_elem.set("causality", v.causality)
            var_elem.set("variability", v.variability)
            if v.initial:
                var_elem.set("initial", v.initial)
            elif v.causality == "parameter":
                var_elem.set("initial", "exact")
            elif v.causality == "output":
                var_elem.set("initial", "calculated")
            if v.description:
                var_elem.set("description", v.description)

            type_elem = ET.SubElement(var_elem, v.data_type)
            if v.start is not None:
                type_elem.set("start", str(v.start))
            if v.unit:
                type_elem.set("unit", v.unit)

        # Model structure
        struct_elem = ET.SubElement(root, "ModelStructure")
        outputs_elem = ET.SubElement(struct_elem, "Outputs")
        init_unknowns_elem = ET.SubElement(struct_elem, "InitialUnknowns")

        for idx, v in enumerate(self.variables, 1):
            if v.causality == "output":
                unknown = ET.SubElement(outputs_elem, "Unknown")
                unknown.set("index", str(idx))
                
                init_unk = ET.SubElement(init_unknowns_elem, "Unknown")
                init_unk.set("index", str(idx))

        rough_string = ET.tostring(root, encoding="utf-8")
        reparsed = xml.dom.minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")


def create_quarter_car_fmi_description(model_name: str = "QuarterCarRideModel") -> FMIModelDescription:
    """Create standard FMI 2.0/3.0 model description for the 2-DOF Quarter Car Model."""
    vars_list = [
        # Parameters (tunable inputs)
        FMIVariable(name="m_s", value_reference=1, causality="parameter", variability="fixed", start=300.0, unit="kg", description="Sprung mass"),
        FMIVariable(name="m_u", value_reference=2, causality="parameter", variability="fixed", start=35.0, unit="kg", description="Unsprung mass"),
        FMIVariable(name="k_s", value_reference=3, causality="parameter", variability="fixed", start=25000.0, unit="N/m", description="Suspension spring rate"),
        FMIVariable(name="c", value_reference=4, causality="parameter", variability="fixed", start=2050.0, unit="Ns/m", description="Damper damping rate"),
        FMIVariable(name="k_t", value_reference=5, causality="parameter", variability="fixed", start=200000.0, unit="N/m", description="Tire radial stiffness"),
        FMIVariable(name="MR", value_reference=6, causality="parameter", variability="fixed", start=0.85, unit="-", description="Motion ratio (spring travel / wheel travel)"),
        FMIVariable(name="c_t", value_reference=7, causality="parameter", variability="fixed", start=0.0, unit="Ns/m", description="Tire damping rate"),
        
        # Inputs (continuous excitation)
        FMIVariable(name="z_road", value_reference=10, causality="input", variability="continuous", start=0.0, unit="m", description="Road surface vertical displacement profile"),
        FMIVariable(name="dz_road", value_reference=11, causality="input", variability="continuous", start=0.0, unit="m/s", description="Road vertical velocity"),
        
        # Outputs
        FMIVariable(name="z_s", value_reference=20, causality="output", variability="continuous", unit="m", description="Sprung mass vertical displacement"),
        FMIVariable(name="z_u", value_reference=21, causality="output", variability="continuous", unit="m", description="Unsprung mass vertical displacement"),
        FMIVariable(name="susp_travel", value_reference=22, causality="output", variability="continuous", unit="m", description="Suspension stroke deflection (z_s - z_u)"),
        FMIVariable(name="tire_load_dynamic", value_reference=23, causality="output", variability="continuous", unit="N", description="Dynamic tire contact load variation"),
        FMIVariable(name="body_accel", value_reference=24, causality="output", variability="continuous", unit="m/s2", description="Sprung mass vertical acceleration"),
        FMIVariable(name="time", value_reference=25, causality="output", variability="continuous", unit="s", description="Simulation elapsed time"),
    ]

    return FMIModelDescription(
        model_name=model_name,
        guid="{8c3f4e21-9a7b-4d61-b531-ec72f0941ab2}",
        variables=vars_list,
    )


def build_and_package_quarter_car_fmu(output_path: Optional[str | pathlib.Path] = None) -> pathlib.Path:
    """Build and package QuarterCarRideModel.fmu."""
    from suspensionlab.physics.fmi_builder import build_fmu
    if output_path is None:
        output_path = pathlib.Path("QuarterCarRideModel.fmu")
    return build_fmu(pathlib.Path(output_path), model_name="QuarterCarRideModel")
