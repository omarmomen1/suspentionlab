"""
physics/contracts.py
====================
SuspensionLab PRO — Canonical Physics Contracts & Domain Definitions

Standardizes:
1. Coordinate Systems: ISO 8855 standard (+X forward, +Y left, +Z upward;
   Pitch positive nose-up; Roll positive right-side down; Yaw positive CCW from above).
2. Units: Strict SI standards (m, rad, s, N, N·m, kg, kg·m², Pa/bar, °C, W, J).
3. Sign Conventions: Explicitly typed and documented.
4. Motion Ratio Convention: MR = Δx_spring / Δx_wheel; k_w = k_s · MR²; c_w = c · MR².
5. Contact States: CONTACT, LIFTOFF, RECONTACT with strict non-negative vertical normal load (Fz >= 0).
6. Canonical Road Excitation: (x, z, dz/dx, curvature, bank, gradient, dz/dt = dz/dx · v).
7. Conservation Diagnostics: Structured PhysicsDiagnostics containing force, moment, momentum, and energy residuals.
8. Solver Execution Metadata & Provenance.
"""

from __future__ import annotations

import math
import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# 1. Coordinate Frames & Conventions
# ─────────────────────────────────────────────────────────────────────────────

class CoordinateSystem(str, Enum):
    """Standard vehicle dynamics coordinate systems."""
    ISO_8855 = "ISO_8855"  # +X: Forward, +Y: Left, +Z: Upward (Right-handed)
    SAE_J670 = "SAE_J670"  # +X: Forward, +Y: Right, +Z: Downward (Right-handed)


class SignConvention:
    """Documented ISO 8855 standard sign conventions."""
    LONGITUDINAL = "+X is forward (driving traction > 0, braking < 0)"
    LATERAL = "+Y is leftward (cornering left generates +Fy toward vehicle center)"
    VERTICAL = "+Z is upward (suspension jounce/compression increases normal load)"
    PITCH = "Positive pitch (+) is nose-up (squat), negative pitch (-) is nose-down (dive)"
    ROLL = "Positive roll (+) is right-side down (clockwise looking forward)"
    YAW = "Positive yaw rate (+) is counter-clockwise looking from above (turning left)"
    STEER = "Positive steering angle (+) steers front wheels to the left"
    CAMBER = "Negative camber (-) tilts top of wheel inward toward vehicle centerline"
    TOE = "Positive toe (+) is toe-in (front of tires angled inward)"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Contact State Machine
# ─────────────────────────────────────────────────────────────────────────────

class ContactState(str, Enum):
    """Instantaneous physical contact and friction state of tire."""
    CONTACT = "CONTACT"        # Tire is in continuous physical contact with road (Fz > 0)
    LIFTOFF = "LIFTOFF"        # Wheel airborne / normal load Fz == 0
    RECONTACT = "RECONTACT"    # Wheel re-engaging road surface after liftoff event
    ATTACHED = "ATTACHED"      # Linear adhesion elastic micro-slip
    SLIPPING = "SLIPPING"      # Non-linear transition / sliding zone
    SATURATED = "SATURATED"    # Peak grip limit reached / exceeded
    LOST = "LOST"              # No normal load (Fz <= 0)


class SlipState(str, Enum):
    """Instantaneous contact patch friction regime."""
    ATTACHED = "ATTACHED"      # Linear adhesion elastic micro-slip (< 3° alpha, < 5% kappa)
    SLIPPING = "SLIPPING"      # Non-linear transition / sliding zone
    SATURATED = "SATURATED"    # Peak grip limit reached / exceeded
    LOST = "LOST"              # No normal load (Fz <= 0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Canonical Road Excitation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CanonicalRoadProfile:
    """Standardized 3D Road Profile with spatial derivatives and kinematics.

    Attributes
    ----------
    x           : Longitudinal distance array [m]
    z           : Elevation profile array [m]
    dz_dx       : Spatial derivative (slope) array [-] (inferred via gradient if None)
    curvature   : Horizontal road curvature [1/m] (0 for straight)
    bank_rad    : Road cross-fall / banking angle [rad] (+ right side higher)
    gradient_rad: Road longitudinal slope angle [rad] (+ uphill)
    friction_mu : Road surface friction coefficient [-] (nominal 1.0)
    """
    x: np.ndarray
    z: np.ndarray
    dz_dx: Optional[np.ndarray] = None
    curvature: Optional[np.ndarray] = None
    bank_rad: Optional[np.ndarray] = None
    gradient_rad: Optional[np.ndarray] = None
    friction_mu: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        self.x = np.asarray(self.x, dtype=np.float64)
        self.z = np.asarray(self.z, dtype=np.float64)
        if len(self.x) != len(self.z):
            raise ValueError(f"x ({len(self.x)}) and z ({len(self.z)}) arrays must have identical length.")
        if len(self.x) < 2:
            raise ValueError("Road profile must contain at least 2 spatial points.")
        if any(self.x[i + 1] <= self.x[i] for i in range(len(self.x) - 1)):
            raise ValueError("Longitudinal coordinate x must be strictly monotonically increasing.")

        if self.dz_dx is None:
            self.dz_dx = np.gradient(self.z, self.x)
        else:
            self.dz_dx = np.asarray(self.dz_dx, dtype=np.float64)

        if self.curvature is None:
            self.curvature = np.zeros_like(self.x)
        if self.bank_rad is None:
            self.bank_rad = np.zeros_like(self.x)
        if self.gradient_rad is None:
            self.gradient_rad = np.zeros_like(self.x)
        if self.friction_mu is None:
            self.friction_mu = np.ones_like(self.x)

    def evaluate_at_distance(self, dist_m: float) -> Tuple[float, float, float, float, float, float]:
        """Interpolate road elevation, slope, curvature, bank, gradient, and friction at exact distance.

        Returns (z, dz_dx, curvature, bank, gradient, friction_mu).
        """
        z_val = float(np.interp(dist_m, self.x, self.z, left=self.z[0], right=self.z[-1]))
        slope_val = float(np.interp(dist_m, self.x, self.dz_dx, left=self.dz_dx[0], right=self.dz_dx[-1]))
        curv_val = float(np.interp(dist_m, self.x, self.curvature, left=self.curvature[0], right=self.curvature[-1]))
        bank_val = float(np.interp(dist_m, self.x, self.bank_rad, left=self.bank_rad[0], right=self.bank_rad[-1]))
        grad_val = float(np.interp(dist_m, self.x, self.gradient_rad, left=self.gradient_rad[0], right=self.gradient_rad[-1]))
        mu_val = float(np.interp(dist_m, self.x, self.friction_mu, left=self.friction_mu[0], right=self.friction_mu[-1]))
        return z_val, slope_val, curv_val, bank_val, grad_val, mu_val

    def get_time_excitation(
        self,
        vehicle_speed_mps: float,
        duration_s: Optional[float] = None,
        dt: float = 0.001,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Convert spatial profile to time-domain excitation: dz/dt = (dz/dx) * speed.

        Returns (time_array, z_road_array, dz_road_dt_array).
        """
        speed = max(vehicle_speed_mps, 0.1)
        total_dist = self.x[-1] - self.x[0]
        max_duration = total_dist / speed
        if duration_s is None or duration_s > max_duration:
            duration_s = max_duration

        t_arr = np.arange(0.0, duration_s, dt)
        x_eval = self.x[0] + speed * t_arr

        z_road = np.interp(x_eval, self.x, self.z, left=self.z[0], right=self.z[-1])
        dz_dx_eval = np.interp(x_eval, self.x, self.dz_dx, left=self.dz_dx[0], right=self.dz_dx[-1])
        dz_dt = dz_dx_eval * speed

        return t_arr, z_road, dz_dt


# ─────────────────────────────────────────────────────────────────────────────
# 4. Conservation & Physics Diagnostics
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PhysicsDiagnostics:
    """Rigorous physical and numerical conservation diagnostics for a simulation run.

    Attributes
    ----------
    force_residual_max_n     : Max absolute force residual ||Σ F - m·a|| [N]
    moment_residual_max_nm   : Max absolute moment residual ||Σ M - I·alpha|| [N·m]
    energy_residual_max_j    : Max energy balance residual |E_kin + E_pot + E_diss - W_ext| [J]
    energy_conservation_ratio: Normalized energy conservation error ΔE / max(E_total) [-]
    momentum_residual_max_ns : Max linear momentum error [N·s]
    contact_violations_count : Number of unphysical negative normal load violations (Fz < 0)
    contact_states           : Array or list of ContactState across simulation
    liftoff_time_s           : First liftoff event timestamp [s] (None if no liftoff)
    recontact_time_s         : Recontact timestamp following liftoff [s] (None if no liftoff)
    liftoff_duration_total_s : Cumulative time wheels were airborne [s]
    minimum_Fz_n             : Minimum instantaneous tire vertical normal force observed [N]
    solver_name              : Solver algorithm used (e.g. "BDF", "Radau", "RK45")
    solver_steps_taken       : Total integration steps taken
    solver_evaluations       : Right-hand side function evaluations count
    converged                : Whether solver met convergence criteria without fallback
    warnings                 : List of physical/numerical warning messages
    """
    force_residual_max_n: float = 0.0
    moment_residual_max_nm: float = 0.0
    energy_residual_max_j: float = 0.0
    energy_conservation_ratio: float = 0.0
    momentum_residual_max_ns: float = 0.0
    contact_violations_count: int = 0
    contact_states: List[ContactState] = field(default_factory=list)
    liftoff_time_s: Optional[float] = None
    recontact_time_s: Optional[float] = None
    liftoff_duration_total_s: float = 0.0
    minimum_Fz_n: float = 0.0
    solver_name: str = "BDF"
    solver_steps_taken: int = 0
    solver_evaluations: int = 0
    converged: bool = True
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["contact_states"] = [s.value if isinstance(s, ContactState) else str(s) for s in self.contact_states]
        return d


# ─────────────────────────────────────────────────────────────────────────────
# 5. Scientific Provenance & Metadata Contract
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PhysicsProvenance:
    """Cryptographic provenance and software build metadata for every simulation result."""
    model_version: str
    solver: str
    backend: str
    input_dataset_hash: str
    parameter_version: str
    software_build: str = "SuspensionLab-PRO-v3.0.0-enterprise"
    timestamp_iso: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def compute_dataset_hash(data: Any) -> str:
    """Compute SHA-256 hash for arbitrary structured dictionary or array inputs."""
    if isinstance(data, np.ndarray):
        raw = data.tobytes()
    elif isinstance(data, dict):
        raw = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    elif hasattr(data, "__dict__"):
        raw = json.dumps(data.__dict__, sort_keys=True, default=str).encode("utf-8")
    else:
        raw = str(data).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
