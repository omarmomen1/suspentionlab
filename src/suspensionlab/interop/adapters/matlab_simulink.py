"""
src/suspensionlab/interop/adapters/matlab_simulink.py
=====================================================
MATLAB / Simulink Interoperability Adapter for SuspensionLab PRO.

Generates production MATLAB (.m) initialization scripts containing State-Space (LTI)
matrices and parameter dictionaries for Simulink integration.

Truthful Reporting:
- Export: SUPPORTED.
- Import: UNSUPPORTED (parsing and executing arbitrary MATLAB code is unsupported and untrusted).
- Execution: UNAVAILABLE_DEPENDENCY unless commercial MATLAB is installed.
"""
from __future__ import annotations

import datetime
import hashlib
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
from suspensionlab.interop.manifest import (
    ArtifactReference,
    CanonicalExchangeManifest,
    ParameterValue,
)


class MatlabSimulinkAdapter(BaseSolverAdapter):
    """
    Adapter for MATLAB & Simulink LTI state-space and parameter export.
    """

    ADAPTER_ID = "adapter-matlab-simulink-v1"
    ADAPTER_VERSION = "1.0.0"
    SOLVER_NAME = "MATLAB_SIMULINK"

    def __init__(self) -> None:
        self._matlab_bin_available = shutil.which("matlab") is not None

    def get_capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            adapter_id=self.ADAPTER_ID,
            adapter_version=self.ADAPTER_VERSION,
            solver_name=self.SOLVER_NAME,
            supported_formats=[".m", "text/x-matlab"],
            supported_import_formats=[],
            supported_export_formats=[".m", "text/x-matlab"],
            supported_versions=["R2021a", "R2022a", "R2023a", "R2024a"],
            supported_categories=[
                DataCategory.PARAMETERS,
                DataCategory.MODAL_STATES,
                DataCategory.FREQUENCY_RESPONSE,
            ],
            unit_restrictions=["SI"],
            frame_restrictions=["ISO_8855"],
            import_capability=SupportLevel.UNSUPPORTED,
            export_capability=SupportLevel.SUPPORTED,
            required_dependencies=[
                DependencyRequirement(
                    name="matlab-engine",
                    version_spec=">=R2021a",
                    is_available=self._matlab_bin_available,
                    description="MathWorks MATLAB engine and Control System Toolbox (required for execution only).",
                )
            ],
            known_limitations=[
                "Export-only pipeline: Ingestion of arbitrary .m scripts is unsupported to prevent code execution.",
                "Generates linearized Continuous-Time State-Space (LTI) representation around equilibrium.",
                "Direct solver execution requires MathWorks MATLAB license; only .m file generation supported natively.",
            ],
            verification_status=VerificationStatus.VERIFIED,
        )

    def get_supported_versions(self) -> List[str]:
        return ["R2021a", "R2022a", "R2023a", "R2024a"]

    def validate_input(
        self,
        content: Union[str, bytes, Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        return (
            False,
            ["MATLAB .m script import is unsupported. Execution of arbitrary imported script code is prohibited."],
        )

    def export_artifact(
        self,
        manifest: CanonicalExchangeManifest,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, ArtifactReference]:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

        script = f"""%% SuspensionLab PRO - MATLAB / Simulink State-Space Exporter
%% Generated on: {now}
%% Model: {manifest.engineering_model_id}

clear; clc;

%% 1. Physical Parameters
m_s = {m_s};    % Sprung mass [kg]
m_u = {m_u};     % Unsprung mass [kg]
k_s = {k_s};  % Suspension spring rate [N/m]
c   = {c};     % Damper coefficient [Ns/m]
k_t = {k_t}; % Tire vertical stiffness [N/m]
MR  = {mr};     % Motion ratio [-]
c_t = {c_t};     % Tire damping [Ns/m]

k_w = {k_w:.2f};   % Wheel spring rate [N/m]
c_w = {c_w:.2f};     % Wheel damping rate [Ns/m]

%% 2. Continuous-Time State-Space Formulation
% State vector:  x = [z_s; dz_s; z_u; dz_u]
% Input vector:  u = [z_road]
% Output vector: y = [z_s; z_u; z_s - z_u; k_t*(z_u - z_road); ddz_s]

A = [   0,        1,        0,       0;
     -k_w/m_s,  -c_w/m_s,  k_w/m_s,  c_w/m_s;
        0,        0,        0,       1;
      k_w/m_u,   c_w/m_u, -(k_w+k_t)/m_u, -(c_w+c_t)/m_u ];

B = [ 0;
      0;
      0;
      k_t/m_u ];

C = [ 1,  0,  0,  0;
      0,  0,  1,  0;
      1,  0, -1,  0;
      0,  0,  k_t, 0;
     -k_w/m_s, -c_w/m_s, k_w/m_s, c_w/m_s ];

D = [ 0;
      0;
      0;
     -k_t;
      0 ];

sys = ss(A, B, C, D);
sys.StateName = {{'z_s', 'dz_s', 'z_u', 'dz_u'}};
sys.InputName = {{'z_road'}};
sys.OutputName = {{'z_s', 'z_u', 'susp_travel', 'tire_load_dynamic', 'body_accel'}};
"""
        encoded = script.encode("utf-8")
        sha = hashlib.sha256(encoded).hexdigest()

        artifact_ref = ArtifactReference(
            artifact_id=f"ART-MATLAB-{sha[:12]}",
            name="quarter_car_state_space.m",
            artifact_type="text/x-matlab",
            sha256=sha,
            size_bytes=len(encoded),
            metadata={"solver": self.SOLVER_NAME},
        )
        return (encoded, artifact_ref)

    def import_artifact(
        self,
        content: bytes,
        options: Optional[Dict[str, Any]] = None,
    ) -> CanonicalExchangeManifest:
        raise NotImplementedError(
            "MATLAB script import is deliberately unsupported to prevent execution of untrusted code."
        )
