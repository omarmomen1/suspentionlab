"""
physics/fidelity_modes.py
=========================
SuspensionLab PRO — Authoritative Vehicle Dynamics Fidelity Modes

Establishes the three canonical engineering simulation fidelity tiers:
1. FAST_QSS:
   Quasi-steady-state lap screening, parameter sweeps, and concept exploration.
2. TRANSIENT_ENGINEERING:
   Time-domain non-linear vehicle simulation (4-DOF pitch/heave, 8/20-state handling).
3. HIGH_FIDELITY_LAP:
   Fully coupled 14-DOF transient multi-body vehicle + driver + 3D track simulation.

Scientific Honesty & Governance Laws:
-------------------------------------
1. Each mode must explicitly expose its assumptions, valid domain, parameter sources,
   numerical method, validation status, and known limitations.
2. No silent model switching: Downstream code must never switch between fidelity modes
   without an explicit configuration request.
3. Upstream validity inheritance: A degraded upstream validity status
   (e.g., EXTRAPOLATED or UNSUPPORTED) must never be upgraded by any fidelity solver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from suspensionlab.physics.validity import (
    PhysicsValidityRecord,
    PhysicsValidityStatus,
)


class FidelityMode(str, Enum):
    """Authoritative vehicle dynamics simulation fidelity modes."""
    FAST_QSS = "FAST_QSS"
    TRANSIENT_ENGINEERING = "TRANSIENT_ENGINEERING"
    HIGH_FIDELITY_LAP = "HIGH_FIDELITY_LAP"


@dataclass
class FidelityModeSpec:
    """Explicit architectural specification and physical assumptions for a fidelity mode.

    Attributes
    ----------
    mode                    : Canonical FidelityMode enum.
    name                    : Human-readable engineering title.
    description             : Detailed technical description of model capability.
    assumptions             : List of fundamental physical and structural assumptions.
    valid_domain            : Dictionary mapping operational variables to valid bounds.
    parameter_sources       : Primary data source provenance (e.g., CAD, K&C rig, CFD).
    numerical_method        : Mathematical formulation and time-stepping / solver method.
    validation_status       : Baseline epistemic validity status.
    uncertainty_limitations : Known limitations and regime boundaries where model degrades.
    """
    mode: FidelityMode
    name: str
    description: str
    assumptions: List[str] = field(default_factory=list)
    valid_domain: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    parameter_sources: Dict[str, str] = field(default_factory=dict)
    numerical_method: str = "Analytical / Forward Integration"
    validation_status: PhysicsValidityStatus = PhysicsValidityStatus.SIMULATION_ESTIMATE
    uncertainty_limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "name": self.name,
            "description": self.description,
            "assumptions": list(self.assumptions),
            "valid_domain": {k: list(v) for k, v in self.valid_domain.items()},
            "parameter_sources": dict(self.parameter_sources),
            "numerical_method": self.numerical_method,
            "validation_status": self.validation_status.value,
            "uncertainty_limitations": list(self.uncertainty_limitations),
        }


# Authoritative Specifications for each Fidelity Mode
FIDELITY_SPECIFICATIONS: Dict[FidelityMode, FidelityModeSpec] = {
    FidelityMode.FAST_QSS: FidelityModeSpec(
        mode=FidelityMode.FAST_QSS,
        name="Fast Quasi-Steady-State Lap & Sensitivity Engine",
        description=(
            "Point-mass / quasi-steady 3D track simulation with steady-state load transfer, "
            "steady-state ARB roll balance, Pacejka magic formula tire limits, and "
            "iterative aero-ride height coupling."
        ),
        assumptions=[
            "Chassis body behaves quasi-statically; transient pitch and roll inertial dynamics are neglected",
            "Tire forces operate along steady-state slip curves without carcass relaxation lengths",
            "Tire normal loads assume algebraic equilibrium with instantaneous longitudinal/lateral accelerations",
            "Unsprung wheel hop modes are omitted",
            "Vertical tire contact assumes idealized single point-contact (POINT_CONTACT) without carcass enveloping",
            "Driver operates at friction limit (closed-loop minimum-time formulation)",
        ],
        valid_domain={
            "speed_mps": (5.0, 110.0),
            "lat_accel_g": (0.0, 4.5),
            "long_accel_g": (-5.0, 3.5),
            "track_grade_rad": (-0.25, 0.25),
            "track_bank_rad": (-0.35, 0.35),
        },
        parameter_sources={
            "mass_properties": "CAD / Weight scales",
            "aero_map": "Wind tunnel / CFD polar matrix",
            "tire_model": "Pacejka MF 5.2 flat-trac test bench",
            "suspension_kinematics": "3D hardpoint kinematics solver",
        },
        numerical_method="Forward-backward apex speed integration with 1D secant iterative aero solve",
        validation_status=PhysicsValidityStatus.MODEL_SUPPORTED,
        uncertainty_limitations=[
            "Under-predicts lap time over harsh kerbs and rough track surfaces",
            "Does not capture damper transient lag or packager bottoming during rapid direction changes",
            "Assumes infinite steer rate; does not resolve steering rack compliance",
        ],
    ),
    FidelityMode.TRANSIENT_ENGINEERING: FidelityModeSpec(
        mode=FidelityMode.TRANSIENT_ENGINEERING,
        name="Transient Engineering Vehicle Dynamics Engine",
        description=(
            "Time-domain dynamic ODE solver integrating 4-DOF pitch-plane half-car dynamics "
            "and 8/20-state non-linear handling dynamics with physical load transfer relaxation, "
            "tire relaxation lengths, rotational wheel dynamics, and 3D suspension anti-geometry."
        ),
        assumptions=[
            "Rigid chassis structural assumption (infinite torsional and bending stiffness between axles)",
            "Kinematic anti-reactions derived from 3D hardpoints modulate suspension deflections",
            "Dual-path suspension compliance (kinematic control arm reactions + elastic spring/damper)",
            "First-order relaxation length models for longitudinal and lateral tire carcass deflection",
            "Non-linear bump stops and progressive velocity-dependent damping curves",
            "Vertical tire contact supports GEOMETRIC_ENVELOPING finite contact patch (2a) and carcass cam follower",
        ],
        valid_domain={
            "speed_mps": (0.1, 120.0),
            "slip_angle_deg": (-35.0, 35.0),
            "slip_ratio": (-1.0, 1.0),
            "wheel_travel_mm": (-100.0, 100.0),
            "chassis_pitch_deg": (-8.0, 8.0),
            "chassis_roll_deg": (-10.0, 10.0),
        },
        parameter_sources={
            "suspension_geometry": "3D suspension hardpoint nodal coordinates",
            "damper_curves": "Shock dyno velocity-force lookups",
            "spring_rates": "Load cell spring rate measurements",
            "bushing_compliance": "Elastomeric bushing test rig",
        },
        numerical_method="Stiff ODE integration (Scipy Radau / BDF / LSODA with analytical Jacobians)",
        validation_status=PhysicsValidityStatus.CORRELATED,
        uncertainty_limitations=[
            "Chassis frame compliance neglected; structural modes above 25 Hz not captured",
            "Aerodynamic pitch sensitivity uses quasi-static map rather than full unsteady CFD",
            "Assumes uniform track contact friction without localized thermal rubber deposition",
        ],
    ),
    FidelityMode.HIGH_FIDELITY_LAP: FidelityModeSpec(
        mode=FidelityMode.HIGH_FIDELITY_LAP,
        name="High-Fidelity 14-DOF Transient Lap & Track Simulator",
        description=(
            "Coupled multi-body 14-DOF transient vehicle simulation resolving 3D translation/yaw, "
            "7-DOF sprung mass ride/pitch/roll, 4 unsprung corner wheel hops, 4 wheel spin states, "
            "Pacejka MF 5.2 tire forces, 3D suspension anti-dive/anti-squat link reactions, "
            "coupled aero ride-height maps, 2026 ERS energy management, and closed-loop driver model."
        ),
        assumptions=[
            "Fully coupled multi-body Newton-Euler equations of motion for sprung and unsprung masses",
            "True 3D suspension force paths: tire Fx applies vertical reaction forces to chassis via anti-geometry",
            "Independent 4-corner wheel hop ODEs resolving tire liftoff and contact loss",
            "Continuous dynamic tire carcass relaxation ODEs (tau = sigma / V_x) coupled with Pacejka MF 5.2 combined-slip forces",
            "Multidimensional aerodynamic lookups coupled directly to dynamic corner ride heights",
            "Powertrain gearbox shift transients and ERS thermodynamic state tracking",
            "Track elevation, banking, and curvature resolved in 3D Frenet-Serret reference frame",
            "Vertical tire contact supports ADVANCED_ENVELOPING with dynamic footprint 2a(Fz, p), 3D surface integration, and horizontal obstacle reaction force Fx_env coupling",
        ],
        valid_domain={
            "speed_mps": (1.0, 130.0),
            "wheel_hop_freq_hz": (0.0, 35.0),
            "chassis_heave_mm": (-80.0, 80.0),
            "chassis_pitch_deg": (-12.0, 12.0),
            "chassis_roll_deg": (-15.0, 15.0),
            "battery_temp_c": (10.0, 95.0),
        },
        parameter_sources={
            "chassis_inertia": "Trifilar pendulum / CAD mass property report",
            "suspension_hardpoints": "Laser scanned / 3D CAD suspension nodes",
            "aero_map": "High-fidelity wind tunnel / scale-model CFD database",
            "track_data": "LiDAR 3D point cloud / DGPS survey",
        },
        numerical_method="Coupled fixed-step Runge-Kutta 4th Order (RK4) with sub-stepping and contact clamping",
        validation_status=PhysicsValidityStatus.MODEL_SUPPORTED,
        uncertainty_limitations=[
            "High computational cost relative to QSS screening",
            "Requires fully specified 3D track centerline, banking, and elevation profiles",
            "Non-linear tire carcass deflection at extreme slip angles (> 20°) carries ~5% empirical uncertainty",
        ],
    ),
}


def get_fidelity_spec(mode: FidelityMode | str) -> FidelityModeSpec:
    """Retrieve the authoritative engineering specification for a fidelity mode."""
    if isinstance(mode, str):
        try:
            mode = FidelityMode(mode)
        except ValueError:
            raise ValueError(f"Unknown fidelity mode '{mode}'. Available modes: {[m.value for m in FidelityMode]}")
    return FIDELITY_SPECIFICATIONS[mode]


def create_mode_validity_record(
    mode: FidelityMode | str,
    upstream_validity: Optional[PhysicsValidityStatus] = None,
    parameter_domain_checks: Optional[Dict[str, float]] = None,
) -> PhysicsValidityRecord:
    """Create a validated PhysicsValidityRecord for a specific fidelity mode.

    Guarantees:
    - Inherits and enforces upstream degradation rules (never upgrades degraded state).
    - Checks parameter values against valid domain boundaries and flags EXTRAPOLATED if violated.
    """
    spec = get_fidelity_spec(mode)
    status = spec.validation_status
    extrapolated = False
    warnings_list = []

    if parameter_domain_checks:
        for param, val in parameter_domain_checks.items():
            if param in spec.valid_domain:
                lo, hi = spec.valid_domain[param]
                if val < lo or val > hi:
                    extrapolated = True
                    warnings_list.append(
                        f"Parameter '{param}' value {val:.3f} outside valid domain [{lo}, {hi}] for {spec.mode.value}."
                    )

    if extrapolated:
        status = PhysicsValidityStatus.EXTRAPOLATED

    return PhysicsValidityRecord(
        status=status,
        model=f"SuspensionLab-{spec.mode.value}",
        assumptions=list(spec.assumptions),
        valid_parameter_domain=dict(spec.valid_domain),
        extrapolation_status=extrapolated,
        validation_evidence=f"Configured under {spec.mode.value} specifications via {spec.numerical_method}",
        data_provenance=dict(spec.parameter_sources),
        warnings=warnings_list,
        upstream_validity_state=upstream_validity,
    )
