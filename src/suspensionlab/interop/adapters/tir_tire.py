"""
src/suspensionlab/interop/adapters/tir_tire.py
==============================================
PAC2002 / Magic Formula (.tir) Tyre Property Adapter for SuspensionLab PRO.

Provides bidirectional import and export of standard industry tyre property files (.tir),
mapping Pacejka MF5.2 coefficients to canonical exchange manifests.
"""
from __future__ import annotations

import datetime
import hashlib
import re
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


class TirPropertyAdapter(BaseSolverAdapter):
    """
    Adapter for PAC2002 / Magic Formula .tir property file exchange.
    """

    ADAPTER_ID = "adapter-pac2002-tir-v1"
    ADAPTER_VERSION = "1.0.0"
    SOLVER_NAME = "PAC2002_MAGIC_FORMULA"

    def get_capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            adapter_id=self.ADAPTER_ID,
            adapter_version=self.ADAPTER_VERSION,
            solver_name=self.SOLVER_NAME,
            supported_formats=[".tir", "text/plain"],
            supported_import_formats=[".tir"],
            supported_export_formats=[".tir"],
            supported_versions=["MF5.2", "MF6.1", "PAC2002"],
            supported_categories=[
                DataCategory.PARAMETERS,
                DataCategory.TIRE_PROPERTY,
            ],
            unit_restrictions=["UNITS='SI'"],
            frame_restrictions=["ISO_8855", "TYRE_AXIS_SAE"],
            import_capability=SupportLevel.SUPPORTED,
            export_capability=SupportLevel.SUPPORTED,
            required_dependencies=[
                DependencyRequirement(
                    name="python-core",
                    version_spec=">=3.10",
                    is_available=True,
                    description="Standard Python runtime.",
                )
            ],
            known_limitations=[
                "Pure slip and combined slip Pacejka formulation; excludes thermal carcass dynamics.",
            ],
            verification_status=VerificationStatus.VERIFIED,
        )

    def get_supported_versions(self) -> List[str]:
        return ["MF5.2", "MF6.1", "PAC2002"]

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
            return (False, ["Input must be text or bytes."])

        if "[MDI_HEADER]" not in text and "[TYRE_DATA]" not in text and "FNOMIN" not in text:
            return (False, [".tir file missing standard sections ([MDI_HEADER] or FNOMIN)."])

        return (True, [])

    def export_artifact(
        self,
        manifest: CanonicalExchangeManifest,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, ArtifactReference]:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        params = manifest.parameters

        fz0 = float(params.get("Fz0", ParameterValue(name="Fz0", value=4000.0, unit="N")).value)
        p0 = float(params.get("p0_bar", ParameterValue(name="p0_bar", value=2.0, unit="bar")).value)
        pcy1 = float(params.get("pCy1", ParameterValue(name="pCy1", value=1.3, unit="-")).value)
        pdy1 = float(params.get("pDy1", ParameterValue(name="pDy1", value=1.0, unit="-")).value)
        pey1 = float(params.get("pEy1", ParameterValue(name="pEy1", value=-0.8, unit="-")).value)
        pky1 = float(params.get("pKy1", ParameterValue(name="pKy1", value=-15.0, unit="N/rad")).value)
        pkx1 = float(params.get("pKx1", ParameterValue(name="pKx1", value=21.0, unit="N")).value)

        tir_content = f"""! ==============================================================================
! PAC2002 / Magic Formula 5.2 Tyre Property File (.tir)
! Generated on: {now} by SuspensionLab PRO Interop
! ==============================================================================
[MDI_HEADER]
FILE_TYPE                = 'tir'
FILE_VERSION             = 3.0
FILE_FORMAT              = 'ASCII'

[DIMENSION]
UNITS                    = 'SI'

[VERTICAL]
FNOMIN                   = {fz0:.1f}
NOMPRES                  = {p0 * 100000.0:.1f}

[LATERAL_COEFFICIENTS]
PCY1                     = {pcy1:.4f}
PDY1                     = {pdy1:.4f}
PEY1                     = {pey1:.4f}
PKY1                     = {pky1:.4f}

[LONGITUDINAL_COEFFICIENTS]
PKX1                     = {pkx1:.4f}
"""
        encoded = tir_content.encode("utf-8")
        sha = hashlib.sha256(encoded).hexdigest()

        artifact_ref = ArtifactReference(
            artifact_id=f"ART-TIR-{sha[:12]}",
            name="tyre_model.tir",
            artifact_type="text/plain",
            sha256=sha,
            size_bytes=len(encoded),
            metadata={"format": "tir", "solver": self.SOLVER_NAME},
        )
        return (encoded, artifact_ref)

    def import_artifact(
        self,
        content: bytes,
        options: Optional[Dict[str, Any]] = None,
    ) -> CanonicalExchangeManifest:
        check_payload_size(content)
        text = content.decode("utf-8", errors="replace")

        parameters: Dict[str, ParameterValue] = {}
        mappings: List[ParameterMapping] = []

        # Parse key = value pairs
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("!") or line.startswith("[") or line.startswith("$"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip().upper()
                v_str = v.split("$")[0].split("!")[0].strip().strip("'\"")
                try:
                    val = float(v_str)
                    if k == "FNOMIN":
                        parameters["Fz0"] = ParameterValue(name="Fz0", value=val, unit="N", dimension="force")
                    elif k in ("PNOMIN", "NOMPRES"):
                        # In .tir NOMPRES is in Pa, convert to bar
                        parameters["p0_bar"] = ParameterValue(name="p0_bar", value=val / 100000.0, unit="bar", dimension="pressure")
                    elif k == "PCY1":
                        parameters["pCy1"] = ParameterValue(name="pCy1", value=val, unit="-", dimension="dimensionless")
                    elif k == "PDY1":
                        parameters["pDy1"] = ParameterValue(name="pDy1", value=val, unit="-", dimension="dimensionless")
                    elif k == "PEY1":
                        parameters["pEy1"] = ParameterValue(name="pEy1", value=val, unit="-", dimension="dimensionless")
                    elif k == "PKY1":
                        parameters["pKy1"] = ParameterValue(name="pKy1", value=val, unit="N/rad", dimension="rotational_stiffness")
                    elif k == "PKX1":
                        parameters["pKx1"] = ParameterValue(name="pKx1", value=val, unit="N", dimension="force")
                except ValueError:
                    pass

        sha = hashlib.sha256(content).hexdigest()
        input_ref = ArtifactReference(
            artifact_id=f"ART-TIR-IN-{sha[:12]}",
            name="imported_tire.tir",
            artifact_type="text/plain",
            sha256=sha,
            size_bytes=len(content),
            metadata={"solver": self.SOLVER_NAME},
        )

        manifest = CanonicalExchangeManifest(
            schema_version="1.0.0",
            source_application="PAC2002 Tyre Interface",
            source_solver=self.SOLVER_NAME,
            solver_version="MF5.2",
            engineering_model_id="tire_mf52",
            exchange_mode=ExchangeMode.IMPORT,
            parameters=parameters,
            input_artifacts=[input_ref],
            parameter_mappings=mappings,
            warnings=["Imported Pacejka tire property coefficients."],
            validation_status=ExchangeValidationStatus.VALID_WITH_WARNINGS,
        )

        # Enforce strict provenance
        manifest.execution_metadata.provenance_origin = ResultProvenanceOrigin.IMPORTED_EXTERNAL
        manifest.execution_metadata.is_physically_validated = False

        return manifest
