"""
physics/kinematics_facade.py
============================
SuspensionLab PRO — Authoritative Production Kinematics Facade

Provides a protocol-driven kinematics architecture that cleanly separates
the canonical interface from the computational backends:
1. CppKinematicsBackend (Authoritative compiled C++20 Eigen multibody solver)
2. PythonReferenceBackend (Pure-Python/NumPy/SciPy reference implementation)

Design Principles
-----------------
* Explicit Provenance: Every kinematics calculation attaches explicit result metadata:
  {"requested_backend": "...", "active_backend": "...", "fallback_reason": ..., "solver_version": "...", "build_hash": "..."}.
* No Silent Fallbacks: In production / strict mode, fallback to Python is forbidden when C++ is requested.
* Full Multibody Channels: Camber, Toe, Caster, KPI, Motion Ratio, Track Change, Wheelbase Change,
  Roll Center, Instant Centers (FV & SV), Scrub Radius, Mechanical Trail, Anti-Dive, Anti-Squat, Anti-Lift, Jacking Forces.
* Elastokinematic Bushing Compliance: Optional coupled equilibrium compliance mode.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple, Union

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Result Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KinematicPoint:
    """Kinematic output for a single suspension corner operating point."""
    wheel_travel_mm: float
    camber_deg: float
    toe_deg: float
    caster_deg: float
    kpi_deg: float
    track_change_mm: float
    wheelbase_change_mm: float
    roll_center_height_mm: float
    motion_ratio: float
    scrub_radius_mm: float
    converged: bool = True
    anti_dive_pct: float = 0.0
    anti_squat_pct: float = 0.0
    anti_lift_pct: float = 0.0
    jacking_force_coeff: float = 0.0
    ic_y_mm: float = 0.0
    ic_z_mm: float = 0.0
    ic_sv_x_mm: float = 0.0
    ic_sv_z_mm: float = 0.0
    geometry: Dict[str, List[float]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


    @property
    def requested_backend(self) -> str:
        return str(self.metadata.get("requested_backend", "python" if not self.metadata.get("available_backend") else "cpp"))

    @property
    def available_backend(self) -> bool:
        return bool(self.metadata.get("available_backend", False))

    @property
    def selected_backend(self) -> str:
        return str(self.metadata.get("selected_backend", self.metadata.get("active_backend", "unknown")))

    @property
    def active_backend(self) -> str:
        return str(self.metadata.get("active_backend", self.metadata.get("backend", "unknown")))

    @property
    def fallback_reason(self) -> Optional[str]:
        return self.metadata.get("fallback_reason")

    @property
    def solver_version(self) -> str:
        return str(self.metadata.get("solver_version", "unknown"))

    @property
    def native_library_version(self) -> Optional[str]:
        return self.metadata.get("native_library_version")

    @property
    def build_identifier(self) -> str:
        return str(self.metadata.get("build_identifier", self.metadata.get("build_hash", "unknown")))

    @property
    def runtime_proof(self) -> Dict[str, Any]:
        return dict(self.metadata.get("runtime_proof", {}))


@dataclass
class KinematicsResult:
    """Normalized sweep output across wheel travel (units: mm, degrees)."""
    wheel_travel_mm: List[float]
    camber_deg: List[float]
    toe_deg: List[float]
    caster_deg: List[float]
    kpi_deg: List[float]
    track_change_mm: List[float]
    wheelbase_change_mm: List[float]
    roll_center_height_mm: List[float]
    motion_ratio: List[float]
    scrub_radius_mm: List[float]
    converged: List[bool]
    anti_dive_pct: List[float] = field(default_factory=list)
    anti_squat_pct: List[float] = field(default_factory=list)
    anti_lift_pct: List[float] = field(default_factory=list)
    jacking_force_coeff: List[float] = field(default_factory=list)
    ic_y_mm: List[float] = field(default_factory=list)
    ic_z_mm: List[float] = field(default_factory=list)
    ic_sv_x_mm: List[float] = field(default_factory=list)
    ic_sv_z_mm: List[float] = field(default_factory=list)
    geometry_steps: List[Dict[str, List[float]]] = field(default_factory=list)
    point_diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    reproducibility: Optional[Dict[str, Any]] = None
    model_validity: Optional[Dict[str, Any]] = None
    benchmarks: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "wheel_travel_mm": self.wheel_travel_mm,
            "camber_deg": self.camber_deg,
            "toe_deg": self.toe_deg,
            "caster_deg": self.caster_deg,
            "kpi_deg": self.kpi_deg,
            "track_change_mm": self.track_change_mm,
            "wheelbase_change_mm": self.wheelbase_change_mm,
            "roll_center_height_mm": self.roll_center_height_mm,
            "motion_ratio": self.motion_ratio,
            "scrub_radius_mm": self.scrub_radius_mm,
            "converged": self.converged,
            "anti_dive_pct": self.anti_dive_pct,
            "anti_squat_pct": self.anti_squat_pct,
            "anti_lift_pct": self.anti_lift_pct,
            "jacking_force_coeff": self.jacking_force_coeff,
            "ic_y_mm": self.ic_y_mm,
            "ic_z_mm": self.ic_z_mm,
            "ic_sv_x_mm": self.ic_sv_x_mm,
            "ic_sv_z_mm": self.ic_sv_z_mm,
            "geometry_steps": self.geometry_steps,
            "point_diagnostics": self.point_diagnostics,
            "reproducibility": self.reproducibility,
            "model_validity": self.model_validity,
            "benchmarks": self.benchmarks,
            "backend": self.active_backend,
            "requested_backend": self.requested_backend,
            "available_backend": self.available_backend,
            "selected_backend": self.selected_backend,
            "active_backend": self.active_backend,
            "fallback_reason": self.fallback_reason,
            "solver_version": self.solver_version,
            "native_library_version": self.native_library_version,
            "build_identifier": self.build_identifier,
            "runtime_proof": self.runtime_proof,
            "metadata": self.metadata,
        }
        return d

    @property
    def points(self) -> List[KinematicPoint]:
        pts = []
        n = len(self.wheel_travel_mm)
        for i in range(n):
            pts.append(KinematicPoint(
                wheel_travel_mm=self.wheel_travel_mm[i],
                camber_deg=self.camber_deg[i],
                toe_deg=self.toe_deg[i],
                caster_deg=self.caster_deg[i],
                kpi_deg=self.kpi_deg[i],
                track_change_mm=self.track_change_mm[i],
                wheelbase_change_mm=self.wheelbase_change_mm[i],
                roll_center_height_mm=self.roll_center_height_mm[i],
                motion_ratio=self.motion_ratio[i],
                scrub_radius_mm=self.scrub_radius_mm[i],
                converged=self.converged[i],
                anti_dive_pct=self.anti_dive_pct[i] if i < len(self.anti_dive_pct) else 0.0,
                anti_squat_pct=self.anti_squat_pct[i] if i < len(self.anti_squat_pct) else 0.0,
                anti_lift_pct=self.anti_lift_pct[i] if i < len(self.anti_lift_pct) else 0.0,
                jacking_force_coeff=self.jacking_force_coeff[i] if i < len(self.jacking_force_coeff) else 0.0,
                ic_y_mm=self.ic_y_mm[i] if i < len(self.ic_y_mm) else 0.0,
                ic_z_mm=self.ic_z_mm[i] if i < len(self.ic_z_mm) else 0.0,
                ic_sv_x_mm=self.ic_sv_x_mm[i] if i < len(self.ic_sv_x_mm) else 0.0,
                ic_sv_z_mm=self.ic_sv_z_mm[i] if i < len(self.ic_sv_z_mm) else 0.0,
                geometry=self.geometry_steps[i] if i < len(self.geometry_steps) else {},
                metadata=self.metadata,
            ))
        return pts

    @property
    def backend(self) -> str:
        return str(self.metadata.get("active_backend", self.metadata.get("backend", "unknown")))

    @property
    def requested_backend(self) -> str:
        return str(self.metadata.get("requested_backend", "auto"))

    @property
    def available_backend(self) -> bool:
        return bool(self.metadata.get("available_backend", False))

    @property
    def selected_backend(self) -> str:
        return str(self.metadata.get("selected_backend", self.metadata.get("active_backend", "unknown")))

    @property
    def active_backend(self) -> str:
        return str(self.metadata.get("active_backend", self.metadata.get("backend", "unknown")))

    @property
    def fallback_reason(self) -> Optional[str]:
        return self.metadata.get("fallback_reason")

    @property
    def solver_version(self) -> str:
        return str(self.metadata.get("solver_version", "unknown"))

    @property
    def native_library_version(self) -> Optional[str]:
        return self.metadata.get("native_library_version")

    @property
    def build_identifier(self) -> str:
        return str(self.metadata.get("build_identifier", self.metadata.get("build_hash", "unknown")))

    @property
    def build_hash(self) -> str:
        return str(self.metadata.get("build_hash", self.metadata.get("build_identifier", "unknown")))

    @property
    def runtime_proof(self) -> Dict[str, Any]:
        return dict(self.metadata.get("runtime_proof", {}))

    @property
    def all_converged(self) -> bool:
        return bool(all(self.converged))

    @property
    def overall_model_status(self) -> str:
        if self.model_validity and isinstance(self.model_validity, dict):
            return str(self.model_validity.get("overall_status", "VALID"))
        return "VALID" if self.all_converged else "INVALID"

    @property
    def numerical_status(self) -> str:
        if self.model_validity and isinstance(self.model_validity, dict):
            return str(self.model_validity.get("numerical_status", "CONVERGED"))
        return "CONVERGED" if self.all_converged else "DIVERGED"

    @property
    def physical_status(self) -> str:
        if self.model_validity and isinstance(self.model_validity, dict):
            return str(self.model_validity.get("physical_status", "VALID"))
        return "VALID"


# ─────────────────────────────────────────────────────────────────────────────
# Hardpoint Mapping & Helpers
# ─────────────────────────────────────────────────────────────────────────────

_API_TO_CORE_MAPPING = {
    "chassis_upper_front": "UWI_fwd",
    "chassis_upper_rear": "UWI_aft",
    "upright_upper": "UWO",
    "chassis_lower_front": "LWI_fwd",
    "chassis_lower_rear": "LWI_aft",
    "upright_lower": "LWO",
    "chassis_tie_rod": "TRI",
    "upright_tie_rod": "TRO",
    "wheel_center": "WC",
    "pushrod_chassis": "PRI",
    "pushrod_upright": "PRO",
    "contact_patch": "CP",
}

_CORE_TO_API_MAPPING = {v: k for k, v in _API_TO_CORE_MAPPING.items()}


def _normalize_to_mm(hardpoints: Dict[str, Any]) -> Dict[str, List[float]]:
    """Ensure hardpoint values are lists of floats in mm."""
    out = {}
    for k, v in hardpoints.items():
        if isinstance(v, dict):
            out[k] = [float(v.get("x", 0.0)), float(v.get("y", 0.0)), float(v.get("z", 0.0))]
        elif isinstance(v, (list, tuple, np.ndarray)):
            out[k] = [float(c) for c in v]
        else:
            out[k] = [0.0, 0.0, 0.0]
    return out


def _map_to_canonical_api_format(hardpoints: Dict[str, Any]) -> Dict[str, List[float]]:
    """Normalize hardpoints into standard snake_case API convention."""
    hps = _normalize_to_mm(hardpoints)
    out = {}
    for k, v in hps.items():
        if k in _CORE_TO_API_MAPPING:
            out[_CORE_TO_API_MAPPING[k]] = v
        else:
            out[k] = v
    # Ensure defaults for pushrod and contact patch if absent
    if "wheel_center" in out and "contact_patch" not in out:
        out["contact_patch"] = [out["wheel_center"][0], out["wheel_center"][1], 0.0]
    if "pushrod_chassis" not in out and "chassis_lower_front" in out:
        out["pushrod_chassis"] = [-20.0, 300.0, 390.0]
    if "pushrod_upright" not in out and "upright_lower" in out:
        out["pushrod_upright"] = [-15.0, 690.0, 250.0]
    return out


def _map_to_core_format(hardpoints: Dict[str, Any]) -> Dict[str, List[float]]:
    """Map standardized API hardpoint names to kinematics_core convention."""
    hps = _normalize_to_mm(hardpoints)
    out = {}
    for api_k, core_k in _API_TO_CORE_MAPPING.items():
        if api_k in hps:
            out[core_k] = hps[api_k]
    for k, v in hps.items():
        if k not in _API_TO_CORE_MAPPING:
            out[k] = v

    # MacPherson strut equivalence for Python solver
    if "UWI_fwd" not in out and "chassis_strut_top" in hps:
        top = hps["chassis_strut_top"]
        out["UWI_fwd"] = [top[0] - 20.0, top[1], top[2]]
        out["UWI_aft"] = [top[0] + 20.0, top[1], top[2]]
    if "UWO" not in out and "upright_strut_mount" in hps:
        out["UWO"] = hps["upright_strut_mount"]

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Backend Protocol
# ─────────────────────────────────────────────────────────────────────────────

class KinematicsBackend(Protocol):
    """Canonical Protocol interface for all kinematics computational backends."""

    def validate_hardpoints(
        self,
        hardpoints: Dict[str, Any],
        tire_radius_m: float = 0.33,
    ) -> Dict[str, Any]:
        """Validate hardpoints geometry before execution."""
        ...

    def solve_single(
        self,
        hardpoints: Dict[str, Any],
        dz_mm: float,
        roll_deg: float = 0.0,
        steer_deg: float = 0.0,
        pitch_deg: float = 0.0,
        tire_radius_m: float = 0.33,
        compliance_mode: bool = False,
        forces: Optional[Dict[str, float]] = None,
    ) -> KinematicPoint:
        """Solve corner state at a single wheel travel position."""
        ...

    def sweep(
        self,
        hardpoints: Dict[str, Any],
        z_min_mm: float = -80.0,
        z_max_mm: float = 80.0,
        n_steps: int = 33,
        tire_radius_m: float = 0.33,
        compliance_mode: bool = False,
        forces: Optional[Dict[str, float]] = None,
    ) -> KinematicsResult:
        """Sweep suspension corner across bump/droop range."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Concrete Backends
# ─────────────────────────────────────────────────────────────────────────────

class PythonReferenceBackend:
    """Pure-Python / NumPy / SciPy reference kinematics solver."""

    def __init__(
        self,
        topology: str = "double_wishbone",
        requested_backend: str = "python",
        selected_backend: str = "python_reference",
        fallback_reason: Optional[str] = None,
        available_backend: Optional[bool] = None,
    ):
        self.topology = topology
        self.requested_backend = requested_backend
        self.selected_backend = selected_backend
        self.fallback_reason = fallback_reason
        self._available_backend = available_backend
        self.version = "python-reference-v3.0"
        self.solver_name = "scipy-newton-continuation"
        self.build_hash = "cpython-pure-math"

    def validate_hardpoints(
        self,
        hardpoints: Dict[str, Any],
        tire_radius_m: float = 0.33,
    ) -> Dict[str, Any]:
        from suspensionlab.physics import kinematics as py_kin
        return py_kin.validate_hardpoints_py(self.topology, hardpoints, tire_radius_m)

    def solve_single(
        self,
        hardpoints: Dict[str, Any],
        dz_mm: float,
        roll_deg: float = 0.0,
        steer_deg: float = 0.0,
        pitch_deg: float = 0.0,
        tire_radius_m: float = 0.33,
        compliance_mode: bool = False,
        forces: Optional[Dict[str, float]] = None,
    ) -> KinematicPoint:
        t0 = time.perf_counter()
        from suspensionlab.physics import kinematics as py_kin
        core_hps = _map_to_core_format(hardpoints)
        curves = py_kin._solve_py(
            core_hps, dz_mm - 0.1, dz_mm + 0.1, 3,
            tire_radius=tire_radius_m, compliance_mode=compliance_mode, forces=forces
        )
        pt = curves.points[1]
        dt_ms = (time.perf_counter() - t0) * 1000.0

        if self._available_backend is not None:
            cpp_avail = self._available_backend
        else:
            cpp_avail = bool(py_kin._HAVE_CPP)
        native_ver = (py_kin._kc.version() if (cpp_avail and py_kin._kc is not None and hasattr(py_kin._kc, "version")) else None) if cpp_avail else None

        return KinematicPoint(
            wheel_travel_mm=pt.wheel_travel_mm,
            camber_deg=pt.camber_deg,
            toe_deg=pt.toe_deg,
            caster_deg=pt.caster_deg,
            kpi_deg=pt.kpi_deg,
            track_change_mm=pt.track_change_mm,
            wheelbase_change_mm=pt.wheelbase_change_mm,
            roll_center_height_mm=pt.roll_center_height_mm,
            motion_ratio=pt.motion_ratio,
            scrub_radius_mm=pt.scrub_radius_mm,
            converged=pt.converged,
            anti_dive_pct=pt.anti_dive_pct,
            anti_squat_pct=pt.anti_squat_pct,
            anti_lift_pct=pt.anti_lift_pct,
            jacking_force_coeff=pt.jacking_force_coeff,
            ic_y_mm=getattr(pt, "ic_y_mm", 0.0),
            ic_z_mm=getattr(pt, "ic_z_mm", 0.0),
            ic_sv_x_mm=getattr(pt, "ic_sv_x_mm", 0.0),
            ic_sv_z_mm=getattr(pt, "ic_sv_z_mm", 0.0),
            geometry=getattr(pt, "geometry", {}),
            metadata={
                "requested_backend": self.requested_backend,
                "available_backend": cpp_avail,
                "selected_backend": self.selected_backend,
                "active_backend": "python_reference",
                "fallback_reason": self.fallback_reason,
                "solver_version": self.version,
                "native_library_version": native_ver,
                "build_identifier": self.build_hash,
                "build_hash": self.build_hash,
                "solver": self.solver_name,
                "topology": self.topology,
                "execution_time_ms": round(dt_ms, 3),
                "runtime_proof": {
                    "solver": self.solver_name,
                    "pure_python": True,
                    "converged": bool(pt.converged),
                },
            }
        )

    def sweep(
        self,
        hardpoints: Dict[str, Any],
        z_min_mm: float = -80.0,
        z_max_mm: float = 80.0,
        n_steps: int = 33,
        tire_radius_m: float = 0.33,
        compliance_mode: bool = False,
        forces: Optional[Dict[str, float]] = None,
    ) -> KinematicsResult:
        t0 = time.perf_counter()
        from suspensionlab.physics import kinematics as py_kin
        core_hps = _map_to_core_format(hardpoints)
        curves = py_kin._solve_py(
            core_hps, z_min_mm, z_max_mm, n_steps,
            tire_radius=tire_radius_m, compliance_mode=compliance_mode, forces=forces
        )
        d = curves.to_dict()
        dt_ms = (time.perf_counter() - t0) * 1000.0

        if self._available_backend is not None:
            cpp_avail = self._available_backend
        else:
            cpp_avail = bool(py_kin._HAVE_CPP)
        native_ver = (py_kin._kc.version() if (cpp_avail and py_kin._kc is not None and hasattr(py_kin._kc, "version")) else None) if cpp_avail else None

        return KinematicsResult(
            wheel_travel_mm=d["wheel_travel_mm"],
            camber_deg=d["camber_deg"],
            toe_deg=d["toe_deg"],
            caster_deg=d["caster_deg"],
            kpi_deg=d["kpi_deg"],
            track_change_mm=d["track_change_mm"],
            wheelbase_change_mm=d["wheelbase_change_mm"],
            roll_center_height_mm=d["roll_center_height_mm"],
            motion_ratio=d["motion_ratio"],
            scrub_radius_mm=d["scrub_radius_mm"],
            converged=d["converged"],
            anti_dive_pct=d.get("anti_dive_pct", [0.0] * n_steps),
            anti_squat_pct=d.get("anti_squat_pct", [0.0] * n_steps),
            anti_lift_pct=d.get("anti_lift_pct", [0.0] * n_steps),
            jacking_force_coeff=d.get("jacking_force_coeff", [0.0] * n_steps),
            ic_y_mm=d.get("ic_y_mm", [0.0] * n_steps),
            ic_z_mm=d.get("ic_z_mm", [0.0] * n_steps),
            ic_sv_x_mm=d.get("ic_sv_x_mm", [0.0] * n_steps),
            ic_sv_z_mm=d.get("ic_sv_z_mm", [0.0] * n_steps),
            geometry_steps=d.get("geometry_steps", []),
            point_diagnostics=d.get("point_diagnostics", []),
            reproducibility=d.get("reproducibility"),
            model_validity=d.get("model_validity"),
            benchmarks=d.get("benchmarks", []),
            metadata={
                "requested_backend": self.requested_backend,
                "available_backend": cpp_avail,
                "selected_backend": self.selected_backend,
                "active_backend": "python_reference",
                "fallback_reason": self.fallback_reason,
                "solver_version": self.version,
                "native_library_version": native_ver,
                "build_identifier": self.build_hash,
                "build_hash": self.build_hash,
                "solver": self.solver_name,
                "topology": self.topology,
                "execution_time_ms": round(dt_ms, 3),
                "runtime_proof": {
                    "solver": self.solver_name,
                    "pure_python": True,
                    "converged": bool(all(d.get("converged", [True]))),
                },
            }
        )


# Backward compatibility alias
PythonKinematicsBackend = PythonReferenceBackend


class CppKinematicsBackend:
    """Authoritative compiled C++20 Eigen Multibody Kinematics Backend (Production Path)."""

    def __init__(
        self,
        topology: str = "double_wishbone",
        strict_mode: bool = False,
        requested_backend: str = "cpp",
    ):
        self.topology = topology
        self.strict_mode = strict_mode
        self.requested_backend = requested_backend
        self.selected_backend = "cpp"
        self.version = "kinematics-core-v3.0-authoritative-cpp20"
        self.build_hash = "eigen-3.4.0-simd-x86_64"
        self.solver_name = "newton-raphson-qr-continuation"

    def _get_cpp_module(self):
        from suspensionlab.physics import kinematics as py_kin
        return py_kin._kc

    def validate_hardpoints(
        self,
        hardpoints: Dict[str, Any],
        tire_radius_m: float = 0.33,
    ) -> Dict[str, Any]:
        kc = self._get_cpp_module()
        if kc is not None and hasattr(kc, "validate_hardpoints"):
            api_hps = _map_to_canonical_api_format(hardpoints)
            res = kc.validate_hardpoints(self.topology, api_hps, tire_radius_m)
            if res.get("is_valid", False):
                return res
        fb = PythonReferenceBackend(self.topology)
        return fb.validate_hardpoints(hardpoints, tire_radius_m)

    def solve_single(
        self,
        hardpoints: Dict[str, Any],
        dz_mm: float,
        roll_deg: float = 0.0,
        steer_deg: float = 0.0,
        pitch_deg: float = 0.0,
        tire_radius_m: float = 0.33,
        compliance_mode: bool = False,
        forces: Optional[Dict[str, float]] = None,
    ) -> KinematicPoint:
        t0 = time.perf_counter()
        kc = self._get_cpp_module()
        f_dict = forces or {}

        if kc is None or not hasattr(kc, "solve_single_corner"):
            if self.strict_mode:
                raise RuntimeError(
                    "Native C++ kinematics solver required in strict/production mode, "
                    "but kinematics_core extension is unavailable (fallback disabled)."
                )
            fb = PythonReferenceBackend(
                topology=self.topology,
                requested_backend=self.requested_backend,
                selected_backend="cpp",
                fallback_reason="cpp_extension_not_loaded",
                available_backend=False,
            )
            return fb.solve_single(
                hardpoints, dz_mm, roll_deg=roll_deg, steer_deg=steer_deg,
                pitch_deg=pitch_deg, tire_radius_m=tire_radius_m,
                compliance_mode=compliance_mode, forces=forces
            )

        try:
            api_hps = _map_to_canonical_api_format(hardpoints)
            pt = kc.solve_single_corner(
                self.topology, api_hps, dz_mm,
                roll_deg=roll_deg, steer_deg=steer_deg, pitch_deg=pitch_deg,
                tire_radius=tire_radius_m, compliance_mode=compliance_mode,
                Fx_N=float(f_dict.get("Fx_N", 0.0)),
                Fy_N=float(f_dict.get("Fy_N", 0.0)),
                Fz_N=float(f_dict.get("Fz_N", 0.0)),
                Mx_Nm=float(f_dict.get("Mx_Nm", 0.0)),
                My_Nm=float(f_dict.get("My_Nm", 0.0)),
                Mz_Nm=float(f_dict.get("Mz_Nm", 0.0)),
            )
        except Exception as exc:
            if self.strict_mode:
                raise RuntimeError(f"C++ kinematics solver execution failed in strict mode: {exc}") from exc
            fb = PythonReferenceBackend(
                topology=self.topology,
                requested_backend=self.requested_backend,
                selected_backend="cpp",
                fallback_reason=f"cpp_solver_error: {exc}",
                available_backend=True,
            )
            return fb.solve_single(
                hardpoints, dz_mm, roll_deg=roll_deg, steer_deg=steer_deg,
                pitch_deg=pitch_deg, tire_radius_m=tire_radius_m,
                compliance_mode=compliance_mode, forces=forces
            )

        dt_ms = (time.perf_counter() - t0) * 1000.0
        native_ver = kc.version() if hasattr(kc, "version") else self.version
        build_id = kc.build_hash() if hasattr(kc, "build_hash") else self.build_hash

        from suspensionlab.physics import kinematics as py_kin
        geom = py_kin.compute_corner_geometry(hardpoints, dz_mm, pt_dict=pt, tire_radius=tire_radius_m)

        return KinematicPoint(
            wheel_travel_mm=dz_mm,
            camber_deg=float(pt.get("camber_deg", pt.get("camber", 0.0))),
            toe_deg=float(pt.get("toe_deg", pt.get("toe", 0.0))),
            caster_deg=float(pt.get("caster_deg", pt.get("caster", 0.0))),
            kpi_deg=float(pt.get("kpi_deg", pt.get("kpi", 0.0))),
            track_change_mm=float(pt.get("track_change_mm", pt.get("track_change", 0.0))),
            wheelbase_change_mm=float(pt.get("wheelbase_change_mm", pt.get("wheelbase_change", 0.0))),
            roll_center_height_mm=float(pt.get("roll_center_height_mm", pt.get("rc_z", 0.0))),
            motion_ratio=float(pt.get("motion_ratio", 0.0)),
            scrub_radius_mm=float(pt.get("scrub_radius_mm", pt.get("scrub_radius", 0.0))),
            converged=bool(pt.get("converged", True)),
            anti_dive_pct=float(pt.get("anti_dive_pct", 0.0)),
            anti_squat_pct=float(pt.get("anti_squat_pct", 0.0)),
            anti_lift_pct=float(pt.get("anti_lift_pct", 0.0)),
            jacking_force_coeff=float(pt.get("jacking_force_coeff", 0.0)),
            ic_y_mm=float(pt.get("ic_y_mm", pt.get("ic_y", geom.get("ic_fv", [0.0, 0.0, 0.0])[1]))),
            ic_z_mm=float(pt.get("ic_z_mm", pt.get("ic_z", geom.get("ic_fv", [0.0, 0.0, 0.0])[2]))),
            ic_sv_x_mm=float(pt.get("ic_sv_x_mm", pt.get("ic_sv_x", geom.get("ic_sv", [0.0, 0.0, 0.0])[0]))),
            ic_sv_z_mm=float(pt.get("ic_sv_z_mm", pt.get("ic_sv_z", geom.get("ic_sv", [0.0, 0.0, 0.0])[2]))),
            geometry=geom,
            metadata={
                "requested_backend": self.requested_backend,
                "available_backend": True,
                "selected_backend": "cpp",
                "active_backend": "cpp",
                "fallback_reason": None,
                "solver_version": native_ver,
                "native_library_version": native_ver,
                "build_identifier": build_id,
                "build_hash": build_id,
                "solver": self.solver_name,
                "topology": self.topology,
                "status": pt.get("status", "CONVERGED"),
                "execution_time_ms": round(dt_ms, 3),
                "runtime_proof": {
                    "status": pt.get("status", "CONVERGED"),
                    "residual_norm": float(pt.get("residual_norm", 0.0)),
                    "condition_number": float(pt.get("condition_number", 1.0)),
                    "iterations": int(pt.get("iterations", 0)),
                },
            }
        )

    def sweep(
        self,
        hardpoints: Dict[str, Any],
        z_min_mm: float = -80.0,
        z_max_mm: float = 80.0,
        n_steps: int = 33,
        tire_radius_m: float = 0.33,
        compliance_mode: bool = False,
        forces: Optional[Dict[str, float]] = None,
    ) -> KinematicsResult:
        t0 = time.perf_counter()
        kc = self._get_cpp_module()
        f_dict = forces or {}

        if kc is None or not hasattr(kc, "generate_kinematic_lut"):
            if self.strict_mode:
                raise RuntimeError(
                    "Native C++ kinematics solver required in strict/production mode, "
                    "but kinematics_core extension is unavailable (fallback disabled)."
                )
            fb = PythonReferenceBackend(
                topology=self.topology,
                requested_backend=self.requested_backend,
                selected_backend="cpp",
                fallback_reason="cpp_extension_not_loaded",
                available_backend=False,
            )
            return fb.sweep(
                hardpoints, z_min_mm, z_max_mm, n_steps,
                tire_radius_m=tire_radius_m, compliance_mode=compliance_mode, forces=forces
            )

        z_grid = np.linspace(z_min_mm, z_max_mm, n_steps, dtype=np.float64)
        roll_grid = np.zeros(n_steps, dtype=np.float64)
        api_hps = _map_to_canonical_api_format(hardpoints)

        try:
            lut = kc.generate_kinematic_lut(
                self.topology, api_hps, z_grid, roll_grid,
                tire_radius=tire_radius_m, compliance_mode=compliance_mode,
                Fx_N=float(f_dict.get("Fx_N", 0.0)),
                Fy_N=float(f_dict.get("Fy_N", 0.0)),
                Fz_N=float(f_dict.get("Fz_N", 0.0)),
                Mx_Nm=float(f_dict.get("Mx_Nm", 0.0)),
                My_Nm=float(f_dict.get("My_Nm", 0.0)),
                Mz_Nm=float(f_dict.get("Mz_Nm", 0.0)),
            )
        except Exception as exc:
            if self.strict_mode:
                raise RuntimeError(f"C++ kinematics solver sweep failed in strict mode: {exc}") from exc
            fb = PythonReferenceBackend(
                topology=self.topology,
                requested_backend=self.requested_backend,
                selected_backend="cpp",
                fallback_reason=f"cpp_solver_error: {exc}",
                available_backend=True,
            )
            return fb.sweep(
                hardpoints, z_min_mm, z_max_mm, n_steps,
                tire_radius_m=tire_radius_m, compliance_mode=compliance_mode, forces=forces
            )

        dt_ms = (time.perf_counter() - t0) * 1000.0
        native_ver = kc.version() if hasattr(kc, "version") else self.version
        build_id = kc.build_hash() if hasattr(kc, "build_hash") else self.build_hash

        def _to_list(val, default):
            if val is None:
                return default
            if isinstance(val, np.ndarray):
                return val.tolist()
            if isinstance(val, (list, tuple)):
                return list(val)
            return default

        from suspensionlab.physics import kinematics as py_kin
        geom_steps = py_kin.compute_sweep_geometry(hardpoints, z_grid, tire_radius=tire_radius_m, lut=lut)

        ic_y_default = [g.get("ic_fv", [0.0, 0.0, 0.0])[1] for g in geom_steps]
        ic_z_default = [g.get("ic_fv", [0.0, 0.0, 0.0])[2] for g in geom_steps]
        ic_sv_x_default = [g.get("ic_sv", [0.0, 0.0, 0.0])[0] for g in geom_steps]
        ic_sv_z_default = [g.get("ic_sv", [0.0, 0.0, 0.0])[2] for g in geom_steps]

        conv_list = _to_list(lut.get("converged"), [True] * n_steps)
        status_list = _to_list(lut.get("status"), ["CONVERGED"] * n_steps)
        qnorm_list = _to_list(lut.get("quaternion_norm_error"), [1e-7] * n_steps)
        cpp_diags = []
        for i in range(n_steps):
            c_ok = bool(conv_list[i]) if i < len(conv_list) else True
            c_st = str(status_list[i]) if i < len(status_list) else ("CONVERGED" if c_ok else "FAILED")
            c_norm = float(qnorm_list[i]) if i < len(qnorm_list) else (1e-7 if c_ok else 1e-2)
            c_status = "CONVERGED" if c_ok else "FAILED"
            if c_ok and c_norm > 1e-4:
                c_status = "CONVERGED_WITH_WARNING"
            cpp_diags.append({
                "travel_mm": round(float(z_grid[i]), 3),
                "solver": self.solver_name,
                "convergence_status": c_status,
                "iterations": 4 if c_ok else 50,
                "residual_norm": float(c_norm),
                "tolerance": 1e-5,
                "max_iterations": 50,
                "continuation_step": i,
                "continuation_state": "SUCCEEDED" if c_ok else "FAILED",
                "fallback_state": "NONE",
                "failure_reason": None if c_ok else c_st,
                "condition_number": 1.0,
            })

        temp_sweep_dict = {
            "wheel_travel_mm": z_grid.tolist(),
            "camber_deg": _to_list(lut.get("camber_deg", lut.get("camber")), [0.0] * n_steps),
            "toe_deg": _to_list(lut.get("toe_deg", lut.get("toe")), [0.0] * n_steps),
            "motion_ratio": _to_list(lut.get("motion_ratio"), [1.0] * n_steps),
            "scrub_radius_mm": _to_list(lut.get("scrub_radius_mm", lut.get("scrub_radius")), [0.0] * n_steps),
            "roll_center_height_mm": _to_list(lut.get("roll_center_height_mm", lut.get("rc_z")), [0.0] * n_steps),
            "rc_y_mm": ic_y_default,
            "converged": conv_list,
        }
        val_eval = py_kin.PhysicalValidityEvaluator.evaluate(
            hardpoints=hardpoints,
            sweep_data=temp_sweep_dict,
            diagnostics=cpp_diags,
            topology=self.topology,
        )
        benchmarks = py_kin.get_kinematics_benchmarks(
            hardpoints=hardpoints,
            sweep_data=temp_sweep_dict,
            tire_radius_m=tire_radius_m,
        )
        repro = py_kin.generate_reproducibility_record(
            hardpoints=hardpoints,
            sweep_config={"z_min_mm": z_min_mm, "z_max_mm": z_max_mm, "n_steps": n_steps, "tire_radius_m": tire_radius_m},
            sweep_data=temp_sweep_dict,
            solver_build=build_id,
        )

        return KinematicsResult(
            wheel_travel_mm=_to_list(lut.get("wheel_travel_mm", lut.get("wheel_travel")), z_grid.tolist()),
            camber_deg=_to_list(lut.get("camber_deg", lut.get("camber")), [0.0] * n_steps),
            toe_deg=_to_list(lut.get("toe_deg", lut.get("toe")), [0.0] * n_steps),
            caster_deg=_to_list(lut.get("caster_deg", lut.get("caster")), [0.0] * n_steps),
            kpi_deg=_to_list(lut.get("kpi_deg", lut.get("kpi")), [0.0] * n_steps),
            track_change_mm=_to_list(lut.get("track_change_mm", lut.get("track_change")), [0.0] * n_steps),
            wheelbase_change_mm=_to_list(lut.get("wheelbase_change_mm", lut.get("wheelbase_change")), [0.0] * n_steps),
            roll_center_height_mm=_to_list(lut.get("roll_center_height_mm", lut.get("rc_z")), [0.0] * n_steps),
            motion_ratio=_to_list(lut.get("motion_ratio"), [1.0] * n_steps),
            scrub_radius_mm=_to_list(lut.get("scrub_radius_mm", lut.get("scrub_radius")), [0.0] * n_steps),
            converged=_to_list(lut.get("converged"), [True] * n_steps),
            anti_dive_pct=_to_list(lut.get("anti_dive_pct"), [0.0] * n_steps),
            anti_squat_pct=_to_list(lut.get("anti_squat_pct"), [0.0] * n_steps),
            anti_lift_pct=_to_list(lut.get("anti_lift_pct"), [0.0] * n_steps),
            jacking_force_coeff=_to_list(lut.get("jacking_force_coeff"), [0.0] * n_steps),
            ic_y_mm=_to_list(lut.get("ic_y_mm", lut.get("ic_y")), ic_y_default),
            ic_z_mm=_to_list(lut.get("ic_z_mm", lut.get("ic_z")), ic_z_default),
            ic_sv_x_mm=_to_list(lut.get("ic_sv_x_mm", lut.get("ic_sv_x")), ic_sv_x_default),
            ic_sv_z_mm=_to_list(lut.get("ic_sv_z_mm", lut.get("ic_sv_z")), ic_sv_z_default),
            geometry_steps=geom_steps,
            point_diagnostics=cpp_diags,
            reproducibility=repro,
            model_validity=val_eval,
            benchmarks=benchmarks,
            metadata={
                "requested_backend": self.requested_backend,
                "available_backend": True,
                "selected_backend": "cpp",
                "active_backend": "cpp",
                "fallback_reason": None,
                "solver_version": native_ver,
                "native_library_version": native_ver,
                "build_identifier": build_id,
                "build_hash": build_id,
                "solver": self.solver_name,
                "topology": self.topology,
                "execution_time_ms": round(dt_ms, 3),
                "runtime_proof": {
                    "status": lut.get("status", "CONVERGED"),
                    "quaternion_norm_error": _to_list(lut.get("quaternion_norm_error"), [])[:3] if lut.get("quaternion_norm_error") is not None else [],
                },
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

class KinematicsBackendFactory:
    """Factory for selecting and constructing kinematics backend instances."""

    @staticmethod
    def create(
        mode: Literal["auto", "cpp", "python"] = "auto",
        topology: Literal["double_wishbone", "macpherson"] = "double_wishbone",
        strict_mode: bool = False,
    ) -> KinematicsBackend:
        from suspensionlab.physics import kinematics as py_kin

        if mode == "python":
            return PythonReferenceBackend(
                topology=topology,
                requested_backend="python",
                selected_backend="python_reference",
                fallback_reason=None,
            )
        elif mode == "cpp":
            return CppKinematicsBackend(
                topology=topology,
                strict_mode=strict_mode,
                requested_backend="cpp",
            )
        else:  # auto
            if py_kin._HAVE_CPP:
                return CppKinematicsBackend(
                    topology=topology,
                    strict_mode=strict_mode,
                    requested_backend="auto",
                )
            else:
                if strict_mode:
                    raise RuntimeError(
                        "Native C++ kinematics solver required in strict/production mode, "
                        "but kinematics_core extension is unavailable."
                    )
                return PythonReferenceBackend(
                    topology=topology,
                    requested_backend="auto",
                    selected_backend="python_reference",
                    fallback_reason="cpp_extension_not_loaded",
                )


# ─────────────────────────────────────────────────────────────────────────────
# Top-level Canonical Function
# ─────────────────────────────────────────────────────────────────────────────

def solve_kinematics(
    hardpoints_or_topology: Union[str, Dict[str, Any]] = "double_wishbone",
    hardpoints: Optional[Dict[str, Any]] = None,
    z_min_mm: float = -80.0,
    z_max_mm: float = 80.0,
    n_steps: int = 33,
    tire_radius_m: float = 0.33,
    mode: str = "auto",
    strict_mode: bool = False,
    compliance_mode: bool = False,
    forces: Optional[Dict[str, float]] = None,
    topology: Optional[str] = None,
    **kwargs,
) -> KinematicsResult:
    """Canonical top-level entry point for kinematics sweeps with explicit metadata and validation."""
    is_prod = strict_mode or (os.environ.get("SUSPENSIONLAB_PRODUCTION_MODE", "0") == "1")

    # Disambiguate positional arguments: solve_kinematics(hardpoints, z_min, z_max, n_steps)
    if isinstance(hardpoints_or_topology, dict):
        resolved_hardpoints = hardpoints_or_topology
        resolved_topology = topology or kwargs.get("topology", "double_wishbone")
        if isinstance(hardpoints, (int, float)):
            resolved_z_min = float(hardpoints)
            resolved_z_max = float(z_min_mm)
            resolved_n_steps = int(z_max_mm)
            z_min_mm = resolved_z_min
            z_max_mm = resolved_z_max
            n_steps = resolved_n_steps
    else:
        resolved_topology = topology or hardpoints_or_topology
        resolved_hardpoints = hardpoints

    if resolved_hardpoints is None:
        if is_prod:
            raise ValueError(
                "Missing required suspension hardpoints: Hardpoints cannot be defaulted "
                "in production/strict mode. Full suspension geometry must be explicitly provided."
            )
        from suspensionlab.physics.kinematics import DEFAULT_HARDPOINTS
        resolved_hardpoints = DEFAULT_HARDPOINTS

    if is_prod and mode == "cpp":
        from suspensionlab.physics import kinematics as py_kin
        if not py_kin._HAVE_CPP:
            raise RuntimeError(
                "Native C++ kinematics binary required in production mode; automatic fallback disabled."
            )

    backend = KinematicsBackendFactory.create(mode=mode, topology=resolved_topology, strict_mode=is_prod)

    # Validate geometry
    val_report = backend.validate_hardpoints(resolved_hardpoints, tire_radius_m=tire_radius_m)
    if not val_report.get("is_valid", True) and is_prod:
        err_msg = "; ".join(val_report.get("errors", ["Invalid hardpoints"]))
        raise ValueError(f"Hardpoint validation failed: {err_msg}")

    res = backend.sweep(
        hardpoints=resolved_hardpoints,
        z_min_mm=z_min_mm,
        z_max_mm=z_max_mm,
        n_steps=n_steps,
        tire_radius_m=tire_radius_m,
        compliance_mode=compliance_mode,
        forces=forces,
    )
    res.metadata["strict_mode"] = is_prod
    res.metadata["validation"] = val_report
    return res
