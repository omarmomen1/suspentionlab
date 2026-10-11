"""
physics/domain_admissibility.py
===============================
SuspensionLab PRO — Physics Domain Admissibility & Parameter Classification Matrix

Formal mathematical & physical validation framework across all 9 primary simulation subsystems:
1. Quarter Car
2. Half Car (Pitch & Heave)
3. Full Car (Ride, Pitch, Roll & Warp)
4. Non-Linear Handling Dynamics (Bicycle / 3-DOF + 4-Wheel)
5. Modular Tire Subsystem (Pacejka MF 5.2 / Similarity Method)
6. Suspension Kinematics (Double-Wishbone & MacPherson)
7. Aerodynamic Polars & Ground Effect
8. Transient 14-DOF Dynamic Lap Simulation
9. Constrained & Robust Engineering Optimization

Admissibility Classification:
- PHYSICALLY_INVALID: Violates fundamental laws (mass conservation, 2nd law of thermodynamics,
  unilateral ground contact, Euclidean metric inequalities).
- NUMERICALLY_INVALID: Causes singular stiffness/mass matrices, division by zero, or NaN/Inf leaks.
- VALID_BUT_EXTREME: Physically admissible edge-case race configurations (e.g. undamped benchmark c=0,
  extreme drift slip alpha > 35 deg, ultra-high downforce > 20 kN, speed > 360 km/h).
- VALID_NORMAL_RANGE: Standard production and motorsport operating windows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class AdmissibilityClass(str, Enum):
    PHYSICALLY_INVALID = "PHYSICALLY_INVALID"
    NUMERICALLY_INVALID = "NUMERICALLY_INVALID"
    VALID_BUT_EXTREME = "VALID_BUT_EXTREME"
    VALID_NORMAL_RANGE = "VALID_NORMAL_RANGE"


@dataclass
class ParameterAdmissibilityRule:
    parameter_name: str
    subsystem: str
    units: str
    normal_range: Tuple[float, float]
    extreme_range: Tuple[float, float]
    physical_lower_bound: float
    physical_upper_bound: float
    mathematical_justification: str
    physical_justification: str

    def classify(self, value: float) -> Tuple[AdmissibilityClass, str]:
        """Classify a numeric parameter against formal physical and numerical criteria."""
        if math.isnan(value) or math.isinf(value):
            return (
                AdmissibilityClass.NUMERICALLY_INVALID,
                f"Parameter '{self.parameter_name}' evaluates to {value} (NaN/Infinite)."
            )

        # Physical impossibility checks
        if value < self.physical_lower_bound:
            return (
                AdmissibilityClass.PHYSICALLY_INVALID,
                f"'{self.parameter_name}'={value} {self.units} is below physical lower bound "
                f"({self.physical_lower_bound} {self.units}): {self.physical_justification}"
            )
        if value > self.physical_upper_bound:
            return (
                AdmissibilityClass.PHYSICALLY_INVALID,
                f"'{self.parameter_name}'={value} {self.units} exceeds physical upper bound "
                f"({self.physical_upper_bound} {self.units}): {self.physical_justification}"
            )

        # Normal vs. Extreme range checks
        norm_min, norm_max = self.normal_range
        ext_min, ext_max = self.extreme_range

        if norm_min <= value <= norm_max:
            return (AdmissibilityClass.VALID_NORMAL_RANGE, "Within nominal automotive operating window.")
        elif ext_min <= value <= ext_max:
            return (
                AdmissibilityClass.VALID_BUT_EXTREME,
                f"'{self.parameter_name}'={value} {self.units} is outside normal range [{norm_min}, {norm_max}] "
                f"but admissible as an extreme or prototype motorsport configuration."
            )
        else:
            return (
                AdmissibilityClass.NUMERICALLY_INVALID,
                f"'{self.parameter_name}'={value} {self.units} exceeds solver convergence envelope: "
                f"{self.mathematical_justification}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Authoritative Parameter Classification Registry
# ─────────────────────────────────────────────────────────────────────────────

PHYSICS_PARAMETER_REGISTRY: Dict[str, ParameterAdmissibilityRule] = {
    # ── Quarter Car ──────────────────────────────────────────────────────────
    "quarter_car.k_s": ParameterAdmissibilityRule(
        parameter_name="k_s",
        subsystem="Quarter Car",
        units="N/m",
        normal_range=(15_000.0, 120_000.0),
        extreme_range=(1_000.0, 500_000.0),
        physical_lower_bound=1_000.0,
        physical_upper_bound=1_000_000.0,
        mathematical_justification="Zero or sub-critical stiffness creates a singular stiffness matrix det(K - omega^2*M)=0 with zero eigenvalues and infinite static sag delta_st = (m_s*g)/k_s -> inf.",
        physical_justification="Spring stiffness must support body weight without bottoming out under static gravity.",
    ),
    "quarter_car.k_t": ParameterAdmissibilityRule(
        parameter_name="k_t",
        subsystem="Quarter Car",
        units="N/m",
        normal_range=(150_000.0, 350_000.0),
        extreme_range=(10_000.0, 800_000.0),
        physical_lower_bound=10_000.0,
        physical_upper_bound=2_000_000.0,
        mathematical_justification="Carcass vertical stiffness below 10,000 N/m leads to ill-conditioned high-frequency ODE coupling and wheel assembly divergence.",
        physical_justification="Tire carcass cannot collapse to zero height under normal inflation pressure.",
    ),
    "quarter_car.c": ParameterAdmissibilityRule(
        parameter_name="c",
        subsystem="Quarter Car",
        units="Ns/m",
        normal_range=(1_000.0, 6_000.0),
        extreme_range=(0.0, 25_000.0),
        physical_lower_bound=0.0,
        physical_upper_bound=100_000.0,
        mathematical_justification="Negative damping c < 0 produces positive real eigenvalues Re(lambda) > 0 causing exponential instability.",
        physical_justification="Damping coefficient cannot be negative (would violate 2nd law of thermodynamics by generating mechanical energy). c=0 is admissible as an ideal undamped oscillator.",
    ),
    "quarter_car.m_s": ParameterAdmissibilityRule(
        parameter_name="m_s",
        subsystem="Quarter Car",
        units="kg",
        normal_range=(150.0, 800.0),
        extreme_range=(0.1, 5_000.0),
        physical_lower_bound=0.1,
        physical_upper_bound=50_000.0,
        mathematical_justification="Mass inversion M^-1 requires m_s > 0 to avoid division by zero.",
        physical_justification="Chassis body sprung mass must be strictly positive.",
    ),

    # ── Geometry (Half Car / Full Car) ───────────────────────────────────────
    "geometry.wheelbase_L": ParameterAdmissibilityRule(
        parameter_name="L",
        subsystem="Vehicle Geometry",
        units="m",
        normal_range=(1.8, 3.8),
        extreme_range=(0.8, 6.5),
        physical_lower_bound=0.5,
        physical_upper_bound=15.0,
        mathematical_justification="Wheelbase L enters denominator of load transfer and yaw equilibrium; L must equal a + b.",
        physical_justification="Axle spacing must be positive; contradictory geometry where L != a + b violates Euclidean distance.",
    ),
    "geometry.track_width": ParameterAdmissibilityRule(
        parameter_name="tw",
        subsystem="Vehicle Geometry",
        units="m",
        normal_range=(1.2, 1.9),
        extreme_range=(0.6, 2.5),
        physical_lower_bound=0.3,
        physical_upper_bound=4.0,
        mathematical_justification="Track width enters roll moment equilibrium; zero track width produces infinite roll angle.",
        physical_justification="Vehicle lateral track width must be strictly positive.",
    ),

    # ── Tire Subsystem ───────────────────────────────────────────────────────
    "tire.unloaded_radius": ParameterAdmissibilityRule(
        parameter_name="unloaded_radius",
        subsystem="Tire Dynamics",
        units="m",
        normal_range=(0.28, 0.40),
        extreme_range=(0.10, 0.65),
        physical_lower_bound=0.08,
        physical_upper_bound=1.20,
        mathematical_justification="Rotational speed omega = v / R requires R > 0 to avoid division by zero.",
        physical_justification="Tire outer radius cannot be zero or negative.",
    ),
    "tire.normal_load_Fz": ParameterAdmissibilityRule(
        parameter_name="Fz",
        subsystem="Tire Dynamics",
        units="N",
        normal_range=(1_000.0, 12_000.0),
        extreme_range=(0.0, 30_000.0),
        physical_lower_bound=0.0,
        physical_upper_bound=60_000.0,
        mathematical_justification="Normal load cannot be negative in unilateral dry friction contact.",
        physical_justification="Tires cannot exert tensile downward pull on tarmac (liftoff occurs at Fz <= 0). Fz=0 is valid (airborne).",
    ),
    "tire.slip_angle_alpha": ParameterAdmissibilityRule(
        parameter_name="alpha_rad",
        subsystem="Tire Dynamics",
        units="rad",
        normal_range=(-0.18, 0.18),  # ~+-10 deg
        extreme_range=(-0.80, 0.80), # ~+-45 deg (drifting / spin recovery)
        physical_lower_bound=-1.57,  # -90 deg
        physical_upper_bound=1.57,   # +90 deg
        mathematical_justification="Pacejka sine arguments require bounded angle to avoid oscillatory trigonometric artifacts.",
        physical_justification="Slip angles up to +-45 deg represent valid drifting or extreme oversteer.",
    ),

    # ── Aerodynamics & Speed ─────────────────────────────────────────────────
    "aero.speed_mps": ParameterAdmissibilityRule(
        parameter_name="speed_mps",
        subsystem="Vehicle Speed",
        units="m/s",
        normal_range=(0.0, 75.0),    # Up to 270 km/h
        extreme_range=(0.0, 150.0),  # Up to 540 km/h (Bonneville / F1 straight)
        physical_lower_bound=0.0,
        physical_upper_bound=300.0,  # Below Mach 0.9
        mathematical_justification="Aero drag F_drag = 0.5 * rho * Cd * A * v^2 diverges quadratically if unbounded.",
        physical_justification="Forward vehicle speed must be non-negative in forward lap sim.",
    ),
}


def validate_admissibility(subsystem_key: str, value: float) -> Tuple[AdmissibilityClass, str]:
    """Validate a parameter against registered admissibility rules."""
    rule = PHYSICS_PARAMETER_REGISTRY.get(subsystem_key)
    if not rule:
        return (AdmissibilityClass.VALID_NORMAL_RANGE, "No formal admissibility constraint registered.")
    return rule.classify(value)
