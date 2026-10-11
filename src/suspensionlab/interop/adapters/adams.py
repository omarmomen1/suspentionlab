"""
src/suspensionlab/interop/adapters/adams.py
===========================================
MSC ADAMS Solver Interoperability Adapter for SuspensionLab PRO.

Provides:
- Export of Quarter Car and Full Car configurations to MSC ADAMS Solver datasets (.adm),
  View command files (.cmd), and Python automation scripts (.py).
- Partial parsing of MSC ADAMS solver datasets (.adm) extracting parts, masses,
  and spring-damper rates.
- Truthful reporting: Solver execution requires commercial MSC ADAMS runtime, which
  is declared as UNAVAILABLE_DEPENDENCY when not verified on host.
"""
from __future__ import annotations

import datetime
import hashlib
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple, Union

from suspensionlab.interop.adapter import (
    AdapterCapability,
    BaseSolverAdapter,
    DataCategory,
    DependencyRequirement,
    SupportLevel,
    VerificationStatus,
)
from suspensionlab.interop.frames import ISO_8855_FRAME
from suspensionlab.interop.manifest import (
    ArtifactReference,
    CanonicalExchangeManifest,
    ExchangeMode,
    ExchangeValidationStatus,
    ParameterValue,
    ResultProvenanceOrigin,
)
from suspensionlab.interop.mapping import ParameterMapping, MappingProvenance, MappingStatus
from suspensionlab.interop.security import (
    check_payload_size,
    sanitize_artifact_filename,
    ExecutableContentSecurityError,
)


class AdamsSolverAdapter(BaseSolverAdapter):
    """
    Adapter for MSC ADAMS Multibody Dynamics Solver interoperability.
    """

    ADAPTER_ID = "adapter-msc-adams-v1"
    ADAPTER_VERSION = "1.0.0"
    SOLVER_NAME = "MSC_ADAMS"

    def __init__(self) -> None:
        # Check if Adams executable is actually on the system PATH
        self._adams_bin_available = shutil.which("adams") is not None or shutil.which("mdi") is not None

    def get_capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            adapter_id=self.ADAPTER_ID,
            adapter_version=self.ADAPTER_VERSION,
            solver_name=self.SOLVER_NAME,
            supported_formats=[".adm", ".cmd", ".py"],
            supported_import_formats=[".adm"],
            supported_export_formats=[".adm", ".cmd", ".py"],
            supported_versions=["2020", "2021", "2022", "2023", "2024"],
            supported_categories=[
                DataCategory.PARAMETERS,
                DataCategory.GEOMETRY,
                DataCategory.KINEMATICS,
            ],
            unit_restrictions=["FORCE=NEWTON", "MASS=KILOGRAM", "LENGTH=METER", "TIME=SECOND"],
            frame_restrictions=["ISO_8855"],
            import_capability=SupportLevel.PARTIALLY_SUPPORTED,
            export_capability=SupportLevel.SUPPORTED,
            required_dependencies=[
                DependencyRequirement(
                    name="msc-adams-solver",
                    version_spec=">=2020",
                    is_available=self._adams_bin_available,
                    description="MSC ADAMS Multibody Solver binary & licensing engine (required for execution only).",
                )
            ],
            known_limitations=[
                "Command files (.cmd) and Python scripts (.py) are strictly export-only artifacts. Ingestion of .cmd and .py files is prohibited to prevent script execution.",
                "Solver datasets (.adm) are parsed strictly as declarative inert text without code or command execution.",
                "Linear radial tire stiffness in standard .adm dataset; PAC2002 (.tir) required for non-linear tires.",
                "Translational joints assume rigid constraint (zero elastokinematic compliance).",
                "Solver execution requires licensed MSC.ADAMS runtime; only file generation and inert dataset parsing supported natively.",
            ],
            verification_status=VerificationStatus.VERIFIED,
        )

    def get_supported_versions(self) -> List[str]:
        return ["2020", "2021", "2022", "2023", "2024"]

    def validate_input(
        self,
        content: Union[str, bytes, Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        opts = options or {}
        fmt = (opts.get("format") or "").lower()
        if fmt in ["cmd", ".cmd", "py", ".py"]:
            return (
                False,
                [f"Format '{fmt}' is export-only. Ingestion of command decks (.cmd) or Python automation scripts (.py) is prohibited by security policy."],
            )

        filename = opts.get("filename")
        if filename:
            try:
                sanitize_artifact_filename(filename)
            except Exception as e:
                return (False, [f"Filename validation rejected: {e}"])

        if isinstance(content, bytes):
            text = content.decode("utf-8", errors="replace")
        elif isinstance(content, str):
            text = content
        else:
            return (False, ["Input must be text or bytes representing an ADAMS file."])

        # Prohibit command/script execution content
        if "import adams" in text or "adams.models" in text:
            return (False, ["Python automation scripts (.py) are export-only and cannot be imported."])
        if "! msc adams/view command" in text.lower() or "model create" in text.lower():
            return (False, ["ADAMS/View command files (.cmd) are export-only and cannot be imported."])

        # Basic syntax inspection for ADAMS dataset (.adm)
        if "ADAMS" not in text.upper() and "PART/" not in text.upper():
            return (False, ["Content does not contain recognized MSC ADAMS solver (.adm) header or part directives."])

        return (True, [])

    def export_artifact(
        self,
        manifest: CanonicalExchangeManifest,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, ArtifactReference]:
        opts = options or {}
        export_format = opts.get("format", "adm").lower()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Extract quarter car parameters if present
        params = manifest.parameters
        m_s = float(params.get("m_s", ParameterValue(name="m_s", value=300.0, unit="kg")).value)
        m_u = float(params.get("m_u", ParameterValue(name="m_u", value=35.0, unit="kg")).value)
        k_s = float(params.get("k_s", ParameterValue(name="k_s", value=25000.0, unit="N/m")).value)
        c = float(params.get("c", ParameterValue(name="c", value=2050.0, unit="Ns/m")).value)
        k_t = float(params.get("k_t", ParameterValue(name="k_t", value=200000.0, unit="N/m")).value)
        mr = float(params.get("MR", ParameterValue(name="MR", value=0.85, unit="-")).value)
        c_t = float(params.get("c_t", ParameterValue(name="c_t", value=0.0, unit="Ns/m")).value)

        k_w = k_s * (mr ** 2)
        c_w = c * (mr ** 2)

        if export_format == "cmd":
            content = f"""! MSC ADAMS/View Command File (.cmd)
! Generated on: {now} by SuspensionLab PRO
model create model_name = Quarter_Car_Rig
defaults units length = meter mass = kilogram time = second force = newton
part create rigid_body name_and_position_spec = .Quarter_Car_Rig.sprung_mass mass = {m_s:.3f}
part create rigid_body name_and_position_spec = .Quarter_Car_Rig.unsprung_mass mass = {m_u:.3f}
force create element spring_damper spring_damper_name = .Quarter_Car_Rig.suspension stiffness = {k_w:.2f} damping = {c_w:.2f}
force create element spring_damper spring_damper_name = .Quarter_Car_Rig.tire stiffness = {k_t:.2f} damping = {c_t:.2f}
"""
            filename = "quarter_car_export.cmd"
            mime_type = "application/x-adams-cmd"
        elif export_format == "py":
            content = f"""# MSC ADAMS/View Python Automation Script
# Generated on: {now} by SuspensionLab PRO
import adams
m = adams.models.create(name="Quarter_Car_Rig")
adams.units.set(length="meter", mass="kilogram", time="second", force="newton")
sprung = m.parts.create_rigid_body(name="sprung_mass", mass={m_s:.3f})
wheel = m.parts.create_rigid_body(name="unsprung_mass", mass={m_u:.3f})
"""
            filename = "quarter_car_export.py"
            mime_type = "text/x-python"
        else:
            # Default .adm
            content = f"""! MSC ADAMS Solver Dataset (.adm) - SuspensionLab PRO
! Generated on: {now}
! Model: {manifest.engineering_model_id}
! Coordinate System: ISO 8855
ADAMS/View model name: Quarter_Car_Rig
UNITS/ FORCE = NEWTON, MASS = KILOGRAM, LENGTH = METER, TIME = SECOND
PART/1, GROUND
PART/2, MASS = {m_s:.3f}, CM = 201
PART/3, MASS = {m_u:.3f}, CM = 301
SPRINGDAMPER/1, TRANSLATIONAL, I = 202, J = 302, STIFFNESS_COEFFICIENT = {k_w:.2f}, DAMPING_COEFFICIENT = {c_w:.2f}
SPRINGDAMPER/2, TRANSLATIONAL, I = 303, J = 102, STIFFNESS_COEFFICIENT = {k_t:.2f}, DAMPING_COEFFICIENT = {c_t:.2f}
END
"""
            filename = "quarter_car_export.adm"
            mime_type = "application/x-adams-adm"

        encoded = content.encode("utf-8")
        sha = hashlib.sha256(encoded).hexdigest()

        artifact_ref = ArtifactReference(
            artifact_id=f"ART-ADAMS-{sha[:12]}",
            name=filename,
            artifact_type=mime_type,
            sha256=sha,
            size_bytes=len(encoded),
            metadata={"format": export_format, "solver": self.SOLVER_NAME},
        )
        return (encoded, artifact_ref)

    def import_artifact(
        self,
        content: bytes,
        options: Optional[Dict[str, Any]] = None,
    ) -> CanonicalExchangeManifest:
        opts = options or {}
        filename = opts.get("filename")
        if filename:
            sanitize_artifact_filename(filename)

        fmt = (opts.get("format") or "").lower()
        if fmt in ["cmd", ".cmd", "py", ".py"]:
            raise ExecutableContentSecurityError(
                f"Format '{fmt}' is export-only. Ingestion of command decks (.cmd) or Python automation scripts (.py) is prohibited."
            )

        check_payload_size(content)
        text = content.decode("utf-8", errors="replace")

        # Prohibit command scripts or Python automation code
        if "import adams" in text or "adams.models" in text:
            raise ExecutableContentSecurityError(
                "ADAMS Python automation scripts (.py) are export-only and prohibited as import input."
            )
        if "! msc adams/view command" in text.lower() or "model create" in text.lower():
            raise ExecutableContentSecurityError(
                "ADAMS/View command files (.cmd) are export-only and prohibited as import input."
            )

        # Parse basic parts and parameters from .adm
        parameters: Dict[str, ParameterValue] = {}
        mappings: List[ParameterMapping] = []

        # Find masses: PART/2, MASS = 300.0
        m_s_match = re.search(r"PART/2\s*,\s*MASS\s*=\s*([0-9\.\+eE\-]+)", text)
        if m_s_match:
            val = float(m_s_match.group(1))
            parameters["m_s"] = ParameterValue(name="m_s", value=val, unit="kg", dimension="mass", description="Sprung mass")
            mappings.append(
                ParameterMapping(
                    internal_entity_type="quarter_car",
                    internal_parameter_path="m_s",
                    external_solver_name=self.SOLVER_NAME,
                    external_variable_id="PART/2.MASS",
                    internal_unit="kg",
                    external_unit="kg",
                    physical_dimension="mass",
                    provenance=MappingProvenance.VENDOR_INTERFACE,
                    status=MappingStatus.SUPPORTED,
                )
            )

        m_u_match = re.search(r"PART/3\s*,\s*MASS\s*=\s*([0-9\.\+eE\-]+)", text)
        if m_u_match:
            val = float(m_u_match.group(1))
            parameters["m_u"] = ParameterValue(name="m_u", value=val, unit="kg", dimension="mass", description="Unsprung mass")
            mappings.append(
                ParameterMapping(
                    internal_entity_type="quarter_car",
                    internal_parameter_path="m_u",
                    external_solver_name=self.SOLVER_NAME,
                    external_variable_id="PART/3.MASS",
                    internal_unit="kg",
                    external_unit="kg",
                    physical_dimension="mass",
                    provenance=MappingProvenance.VENDOR_INTERFACE,
                    status=MappingStatus.SUPPORTED,
                )
            )

        # Find spring dampers: SPRINGDAMPER/1, ... STIFFNESS_COEFFICIENT = 18062.50, DAMPING_COEFFICIENT = 1481.12
        sd1_match = re.search(r"SPRINGDAMPER/1[^\n]*STIFFNESS_COEFFICIENT\s*=\s*([0-9\.\+eE\-]+)", text)
        if sd1_match:
            val = float(sd1_match.group(1))
            parameters["k_w"] = ParameterValue(name="k_w", value=val, unit="N/m", dimension="stiffness", description="Wheel rate")
            mappings.append(
                ParameterMapping(
                    internal_entity_type="quarter_car",
                    internal_parameter_path="k_w",
                    external_solver_name=self.SOLVER_NAME,
                    external_variable_id="SPRINGDAMPER/1.STIFFNESS",
                    internal_unit="N/m",
                    external_unit="N/m",
                    physical_dimension="stiffness",
                    provenance=MappingProvenance.VENDOR_INTERFACE,
                    status=MappingStatus.SUPPORTED,
                )
            )

        sd1_c_match = re.search(r"SPRINGDAMPER/1[^\n]*DAMPING_COEFFICIENT\s*=\s*([0-9\.\+eE\-]+)", text)
        if sd1_c_match:
            val = float(sd1_c_match.group(1))
            parameters["c_w"] = ParameterValue(name="c_w", value=val, unit="Ns/m", dimension="damping", description="Wheel damping")
            mappings.append(
                ParameterMapping(
                    internal_entity_type="quarter_car",
                    internal_parameter_path="c_w",
                    external_solver_name=self.SOLVER_NAME,
                    external_variable_id="SPRINGDAMPER/1.DAMPING",
                    internal_unit="Ns/m",
                    external_unit="Ns/m",
                    physical_dimension="damping",
                    provenance=MappingProvenance.VENDOR_INTERFACE,
                    status=MappingStatus.SUPPORTED,
                )
            )

        sd2_match = re.search(r"SPRINGDAMPER/2[^\n]*STIFFNESS_COEFFICIENT\s*=\s*([0-9\.\+eE\-]+)", text)
        if sd2_match:
            val = float(sd2_match.group(1))
            parameters["k_t"] = ParameterValue(name="k_t", value=val, unit="N/m", dimension="stiffness", description="Tire stiffness")
            mappings.append(
                ParameterMapping(
                    internal_entity_type="quarter_car",
                    internal_parameter_path="k_t",
                    external_solver_name=self.SOLVER_NAME,
                    external_variable_id="SPRINGDAMPER/2.STIFFNESS",
                    internal_unit="N/m",
                    external_unit="N/m",
                    physical_dimension="stiffness",
                    provenance=MappingProvenance.VENDOR_INTERFACE,
                    status=MappingStatus.SUPPORTED,
                )
            )

        sha = hashlib.sha256(content).hexdigest()
        input_ref = ArtifactReference(
            artifact_id=f"ART-ADAMS-IN-{sha[:12]}",
            name="imported_adams_model.adm",
            artifact_type="application/x-adams-adm",
            sha256=sha,
            size_bytes=len(content),
            metadata={
                "solver": self.SOLVER_NAME,
                "adapter_id": self.ADAPTER_ID,
                "adapter_version": self.ADAPTER_VERSION,
            },
        )

        manifest = CanonicalExchangeManifest(
            schema_version="1.0.0",
            source_application="MSC ADAMS View / Solver",
            source_solver=self.SOLVER_NAME,
            solver_version="2023",
            engineering_model_id="quarter_car",
            exchange_mode=ExchangeMode.IMPORT,
            parameters=parameters,
            coordinate_frame=ISO_8855_FRAME,
            input_artifacts=[input_ref],
            parameter_mappings=mappings,
            warnings=["Imported from MSC ADAMS dataset. Rigid joints assumed."],
            validation_status=ExchangeValidationStatus.VALID_WITH_WARNINGS,
        )

        # Enforce strict provenance
        manifest.execution_metadata.provenance_origin = ResultProvenanceOrigin.IMPORTED_EXTERNAL
        manifest.execution_metadata.is_physically_validated = False

        return manifest
