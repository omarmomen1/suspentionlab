"""
physics/capability_contract.py
==============================
SuspensionLab PRO — Model Capability Contracts & Engineering Credibility

Every physics model in SuspensionLab declares an explicit capability contract.
No feature may claim a level of engineering fidelity higher than the underlying
model actually supports.

Design Principles
-----------------
* Scientific Credibility: Professional engineers need to know exact model capabilities,
  assumptions, validated operating envelopes, and validation statuses.
* Transparency: A model never silently pretends to simulate effects (such as tire contact loss,
  aero elasticity, or nonlinear kinematics) when they are not present in its equations of motion.
* Quantitative Confidence: Confidence scores (0–100%) are computed objectively against
  supplied parameters, operating boundary conditions, and telemetry correlation.

Model Validation Statuses:
- VALIDATED: Formally benchmarked against analytical solutions, ISO standards, or physical data.
- CONDITIONAL: Valid within strict parameter ranges and operating conditions; degrades outside.
- EXPERIMENTAL: Research / advanced prototype model subject to active refinement.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional, Tuple
import math

ValidationStatus = Literal["VALIDATED", "CONDITIONAL", "EXPERIMENTAL"]


@dataclass(frozen=True)
class ValidatedRange:
    """Operating domain where the model's equations are physically and mathematically valid."""
    parameter: str
    min_val: float
    max_val: float
    units: str
    description: str

    def is_within(self, val: float) -> bool:
        return self.min_val <= val <= self.max_val


@dataclass
class ModelCapabilityContract:
    """Explicit engineering capability contract for a simulation model."""
    model_name: str
    version: str
    dof: int
    validation_status: ValidationStatus
    description: str
    assumptions: List[str]
    capabilities: Dict[str, bool | str]
    validated_ranges: List[ValidatedRange]
    known_limitations: List[str]
    recommended_use_cases: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "version": self.version,
            "dof": self.dof,
            "validation_status": self.validation_status,
            "description": self.description,
            "assumptions": self.assumptions,
            "capabilities": self.capabilities,
            "validated_ranges": [
                {
                    "parameter": r.parameter,
                    "min_val": r.min_val,
                    "max_val": r.max_val,
                    "units": r.units,
                    "description": r.description
                }
                for r in self.validated_ranges
            ],
            "known_limitations": self.known_limitations,
            "recommended_use_cases": self.recommended_use_cases,
        }

    def assess_confidence(
        self,
        operating_params: Dict[str, float],
        has_nonlinear_damper: bool = False,
        has_telemetry_correlation: Optional[float] = None,
        has_thermal_model: bool = False,
    ) -> Dict[str, Any]:
        """Compute an objective 0–100% confidence score and detailed diagnostic report."""
        checks: List[Dict[str, Any]] = []
        score = 100.0
        warnings: List[str] = []

        # 1. Check validated parameter ranges
        for r in self.validated_ranges:
            if r.parameter in operating_params:
                val = float(operating_params[r.parameter])
                if not r.is_within(val):
                    score -= 15.0
                    warnings.append(
                        f"Operating parameter '{r.parameter}' = {val:g} {r.units} is outside "
                        f"validated range [{r.min_val:g}, {r.max_val:g}] {r.units}."
                    )
                    checks.append({
                        "name": f"Range: {r.parameter}",
                        "status": "FAIL",
                        "detail": f"{val:g} outside [{r.min_val:g}, {r.max_val:g}] {r.units}"
                    })
                else:
                    checks.append({
                        "name": f"Range: {r.parameter}",
                        "status": "PASS",
                        "detail": f"{val:g} inside [{r.min_val:g}, {r.max_val:g}] {r.units}"
                    })

        # 2. Check damper capability
        if "nonlinear_damper" in self.capabilities:
            if self.capabilities["nonlinear_damper"] and not has_nonlinear_damper:
                score -= 10.0
                checks.append({
                    "name": "Damper Fidelity",
                    "status": "WARN",
                    "detail": "Linear damping assumed; asymmetric compression/rebound not captured."
                })
            else:
                checks.append({
                    "name": "Damper Fidelity",
                    "status": "PASS",
                    "detail": "Nonlinear damper curve active."
                })

        # 3. Check telemetry calibration
        if has_telemetry_correlation is not None:
            corr_pct = has_telemetry_correlation * 100.0
            if corr_pct >= 85.0:
                score += 5.0  # Bonus for high physical correlation
                checks.append({
                    "name": "Physical Correlation",
                    "status": "PASS",
                    "detail": f"Telemetry correlation: {corr_pct:.1f}%."
                })
            elif corr_pct >= 60.0:
                checks.append({
                    "name": "Physical Correlation",
                    "status": "WARN",
                    "detail": f"Telemetry correlation: {corr_pct:.1f}% (calibration advised)."
                })
            else:
                score -= 20.0
                checks.append({
                    "name": "Physical Correlation",
                    "status": "FAIL",
                    "detail": f"Low telemetry correlation: {corr_pct:.1f}%."
                })
        else:
            checks.append({
                "name": "Physical Correlation",
                "status": "WARN",
                "detail": "Uncorrelated model: purely theoretical simulation."
            })

        score = max(10.0, min(100.0, score))
        band = "High" if score >= 80.0 else ("Medium" if score >= 55.0 else "Low")

        return {
            "model_name": self.model_name,
            "version": self.version,
            "validation_status": self.validation_status,
            "confidence_score": round(score, 1),
            "confidence_band": band,
            "checks": checks,
            "warnings": warnings,
            "limitations": self.known_limitations,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Model Registry of Formal Capability Contracts
# ─────────────────────────────────────────────────────────────────────────────

CONTRACTS: Dict[str, ModelCapabilityContract] = {
    "QuarterCar": ModelCapabilityContract(
        model_name="QuarterCar",
        version="quarter-car-v2",
        dof=2,
        validation_status="VALIDATED",
        description="2-DOF vertical ride dynamics model with sprung and unsprung masses.",
        assumptions=[
            "Linear vertical travel with constant or travel-dependent motion ratio.",
            "Linear/bilinear tire vertical spring without lateral/longitudinal coupling.",
            "Road input acts purely vertically through the tire contact patch.",
            "Static equilibrium reference frame."
        ],
        capabilities={
            "nonlinear_damper": True,
            "motion_ratio_travel_dependent": True,
            "tire_damping": True,
            "tire_contact_loss": True,
            "aero_coupling": False,
            "camber_migration": False,
        },
        validated_ranges=[
            ValidatedRange("frequency_hz", 0.1, 25.0, "Hz", "Excitation frequency"),
            ValidatedRange("travel_mm", -50.0, 50.0, "mm", "Wheel bump/droop travel"),
            ValidatedRange("sprung_mass_kg", 50.0, 1500.0, "kg", "Quarter-car sprung mass"),
        ],
        known_limitations=[
            "Does not account for pitch or roll mass transfer.",
            "Kinematic camber, toe, and roll-center migrations are not modeled.",
            "No aerodynamic downforce or ground-effect coupling."
        ],
        recommended_use_cases=[
            "Primary ride frequency and damping ratio optimization (0.8–2.5 Hz).",
            "Wheel-hop resonance tuning and damping (10–15 Hz).",
            "Damper dyno curve evaluation and equivalent linearization."
        ]
    ),

    "HalfCar": ModelCapabilityContract(
        model_name="HalfCar",
        version="half-car-v2",
        dof=4,
        validation_status="VALIDATED",
        description="4-DOF pitch-bounce longitudinal vehicle ride dynamics model.",
        assumptions=[
            "Planar pitch and bounce motions with front-to-rear wheelbase time delay.",
            "Uncoupled left-right suspension behavior.",
            "Small pitch angles (sin theta approx theta)."
        ],
        capabilities={
            "pitch_bounce_modal_decoupling": True,
            "wheelbase_delay_transport": True,
            "anti_dive_anti_squat_geometry": True,
            "nonlinear_damper": True,
            "roll_dynamics": False,
        },
        validated_ranges=[
            ValidatedRange("frequency_hz", 0.1, 20.0, "Hz", "Road input frequency"),
            ValidatedRange("wheel_travel_mm", -60.0, 60.0, "mm", "Wheel travel"),
            ValidatedRange("pitch_angle_deg", -5.0, 5.0, "deg", "Chassis pitch angle"),
            ValidatedRange("speed_kph", 5.0, 350.0, "km/h", "Forward speed for wheelbase delay"),
        ],
        known_limitations=[
            "Zero lateral load transfer or roll dynamics.",
            "Aerodynamic center of pressure shift with pitch requires coupled aero mode."
        ],
        recommended_use_cases=[
            "Pitch-bounce frequency matching and flat ride tuning (Olley criteria).",
            "Braking pitch and acceleration squat optimization.",
            "Front-to-rear damping balance."
        ]
    ),

    "FullCar": ModelCapabilityContract(
        model_name="FullCar",
        version="full-car-v3",
        dof=7,
        validation_status="VALIDATED",
        description="7-DOF heave, pitch, roll, and 4-wheel independent vertical ride dynamics model.",
        assumptions=[
            "7-state body dynamics: heave (z), pitch (theta), roll (phi), and 4 wheel hops (z_u1..4).",
            "Anti-roll bars modeled as torsional roll stiffness couples.",
            "Small angular excursions (< 8 deg)."
        ],
        capabilities={
            "four_wheel_independent_inputs": True,
            "anti_roll_bar_stiffness_distribution": True,
            "modal_energy_decomposition": True,
            "iso_2631_comfort_weighting": True,
            "nonlinear_dampers": True,
            "aero_downforce_mapping": True,
        },
        validated_ranges=[
            ValidatedRange("frequency_hz", 0.1, 30.0, "Hz", "Four-post shaker excitation"),
            ValidatedRange("roll_angle_deg", -6.0, 6.0, "deg", "Chassis roll angle"),
            ValidatedRange("pitch_angle_deg", -5.0, 5.0, "deg", "Chassis pitch angle"),
            ValidatedRange("wheel_travel_mm", -75.0, 75.0, "mm", "Corner wheel travels"),
        ],
        known_limitations=[
            "Tire lateral friction coupling is evaluated quasi-statically.",
            "Chassis torsional flexibility is assumed rigid (infinite stiffness)."
        ],
        recommended_use_cases=[
            "4-post shaker simulation and full-car modal analysis.",
            "Roll stiffness distribution (front-to-rear ARB tuning).",
            "Ride-comfort vibration dose value (VDV) and ISO 2631-1 assessment."
        ]
    ),

    "Kinematics": ModelCapabilityContract(
        model_name="Kinematics",
        version="kin-core-v2",
        dof=5,
        validation_status="VALIDATED",
        description="Nonlinear constraint multibody suspension kinematics solver (Double Wishbone & MacPherson).",
        assumptions=[
            "Rigid control arms, uprights, tie-rods, and chassis mountings.",
            "Newton-Raphson nonlinear distance constraint satisfaction.",
            "Spherical joints and revolute bushings."
        ],
        capabilities={
            "camber_gain_curve": True,
            "bump_steer_curve": True,
            "roll_center_migration": True,
            "instant_center_tracking": True,
            "motion_ratio_derivative": True,
            "scrub_radius_mechanical_trail": True,
            "heave_roll_steer_tensor_lut": True,
            "bushing_compliance": False,
        },
        validated_ranges=[
            ValidatedRange("wheel_travel_mm", -100.0, 100.0, "mm", "Wheel bump/droop travel"),
            ValidatedRange("roll_angle_deg", -8.0, 8.0, "deg", "Chassis roll angle"),
            ValidatedRange("steer_angle_deg", -25.0, 25.0, "deg", "Steering rack input"),
        ],
        known_limitations=[
            "Elastic bushing compliance (elastokinematics) is not included; hardpoints are rigid.",
            "Structural arm deflection under high aerodynamic/braking loads is omitted."
        ],
        recommended_use_cases=[
            "Suspension geometry hardpoint design and bump-steer elimination.",
            "Camber curve synthesis and kingpin angle (KPI/caster) optimization.",
            "Lookup table (LUT) generation for real-time handling and lap simulation."
        ]
    ),

    "TireModel": ModelCapabilityContract(
        model_name="TireModel",
        version="pacejka-mf52-v1",
        dof=0,
        validation_status="VALIDATED",
        description="Pacejka Magic Formula MF 5.2 semi-empirical tire model with Similarity Method combined slip.",
        assumptions=[
            "Magic Formula sine-arctan transcendental equations.",
            "Similarity Method Gxalpha and Gykappa combined-slip coupling functions.",
            "Degressive load sensitivity and camber thrust."
        ],
        capabilities={
            "pure_longitudinal_fx": True,
            "pure_lateral_fy": True,
            "combined_slip_similarity": True,
            "load_sensitivity_dfz": True,
            "camber_thrust_gamma": True,
            "thermal_friction_scaling": True,
            "relaxation_length_lag": True,
            "transient_carcass_deflection": False,
        },
        validated_ranges=[
            ValidatedRange("normal_load_N", 500.0, 18000.0, "N", "Tire vertical load Fz"),
            ValidatedRange("slip_angle_deg", -16.0, 16.0, "deg", "Tire slip angle alpha"),
            ValidatedRange("slip_ratio", -0.30, 0.30, "-", "Longitudinal slip ratio kappa"),
            ValidatedRange("camber_deg", -6.0, 6.0, "deg", "Inclination angle gamma"),
            ValidatedRange("temperature_c", 20.0, 130.0, "°C", "Bulk carcass temperature"),
        ],
        known_limitations=[
            "Valid only within calibrated contact patch envelope.",
            "Tread wear degradation is modeled empirically.",
            "Zero normal load Fz <= 0 represents contact loss."
        ],
        recommended_use_cases=[
            "High-accuracy cornering and braking force computation.",
            "GGV friction ellipse envelope generation.",
            "Vehicle handling limit analysis and lap simulation."
        ]
    ),

    "Handling": ModelCapabilityContract(
        model_name="Handling",
        version="handling-v2",
        dof=3,
        validation_status="VALIDATED",
        description="3-DOF non-linear single-track handling model with 4-wheel quasi-static load transfer.",
        assumptions=[
            "Planar vehicle motion: longitudinal velocity (u), lateral velocity (v), yaw rate (r).",
            "Quasi-static lateral and longitudinal load transfer with physical relaxation lag.",
            "Nonlinear Pacejka tire forces modulated by suspension kinematics lookup tables."
        ],
        capabilities={
            "understeer_gradient_assessment": True,
            "step_steer_transient_response": True,
            "quasi_static_load_transfer": True,
            "kinematics_lut_coupling": True,
            "aerodynamic_downforce_drag": True,
            "torque_vectoring_diff": False,
        },
        validated_ranges=[
            ValidatedRange("lateral_accel_g", 0.0, 2.5, "g", "Lateral acceleration"),
            ValidatedRange("speed_kph", 20.0, 320.0, "km/h", "Forward velocity"),
            ValidatedRange("steer_input_deg", -15.0, 15.0, "deg", "Road wheel steer angle"),
        ],
        known_limitations=[
            "Roll and pitch angles are evaluated via suspension stiffnesses rather than independent 6-DOF Euler angles.",
            "Road bank and grade angles are assumed zero."
        ],
        recommended_use_cases=[
            "Vehicle balance, understeer gradient, and yaw response time evaluation.",
            "Transient maneuver stability (step steer, sine with dwell).",
            "Aerodynamic aero balance and mechanical grip tuning."
        ]
    ),

    "LapSim": ModelCapabilityContract(
        model_name="LapSim",
        version="qss-lapsim-v2",
        dof=0,
        validation_status="CONDITIONAL",
        description="Quasi-steady-state 3-pass forward/backward lap time simulator with GGV envelope.",
        assumptions=[
            "Track discretized into segments with local curvature and elevation.",
            "Point-mass quasi-steady-state vehicle with 4-wheel load transfer and aero map.",
            "Tire forces bounded by combined-slip GGV envelope."
        ],
        capabilities={
            "ggv_friction_ellipse_envelope": True,
            "forward_backward_speed_profile": True,
            "ride_height_aero_coupling": True,
            "gearbox_shift_time_powertrain": True,
            "tire_thermal_lap_warmup": True,
            "driver_in_the_loop": False,
        },
        validated_ranges=[
            ValidatedRange("corner_radius_m", 5.0, 1000.0, "m", "Track corner radius"),
            ValidatedRange("vehicle_speed_kph", 10.0, 380.0, "km/h", "Vehicle speed"),
            ValidatedRange("lateral_grip_mu", 0.5, 3.5, "-", "Peak tire friction coefficient"),
        ],
        known_limitations=[
            "Quasi-steady-state formulation assumes instant weight transfer between discrete points.",
            "Does not model driver reaction times, overshooting, or micro-corrections."
        ],
        recommended_use_cases=[
            "Lap time sensitivity analysis (gear ratios, downforce, tire compound).",
            "Telemetry overlay and speed trace comparison.",
            "Energy deployment and brake energy recovery sizing."
        ]
    ),

    "ActiveQuarterCar": ModelCapabilityContract(
        model_name="ActiveQuarterCar",
        version="active-quarter-car-v1",
        dof=2,
        validation_status="EXPERIMENTAL",
        description="Active suspension quarter-car model with Skyhook and Linear Quadratic Regulator (LQR) control.",
        assumptions=[
            "Ideal force actuator placed in parallel with suspension spring and damper.",
            "State feedback with full state availability or observer estimation.",
            "Actuator saturation limits bounded."
        ],
        capabilities={
            "skyhook_damping_control": True,
            "lqr_optimal_control": True,
            "actuator_force_saturation": True,
            "power_consumption_tracking": True,
            "preview_control": False,
        },
        validated_ranges=[
            ValidatedRange("actuator_force_N", -5000.0, 5000.0, "N", "Active actuator force"),
            ValidatedRange("control_bandwidth_hz", 1.0, 50.0, "Hz", "Actuator bandwidth"),
        ],
        known_limitations=[
            "Actuator hydraulic / electromagnetic lag is modeled as first-order delay.",
            "Sensor noise and quantization effects are idealised."
        ],
        recommended_use_cases=[
            "Active and semi-active suspension controller design.",
            "Ride vs handling Pareto frontier exploration.",
            "Actuator power requirements sizing."
        ]
    ),
}


def get_capability_contract(model_name: str) -> ModelCapabilityContract:
    """Retrieve the formal capability contract for any simulation model in the system."""
    if model_name not in CONTRACTS:
        available = ", ".join(sorted(CONTRACTS.keys()))
        raise KeyError(f"Unknown model contract '{model_name}'. Available: {available}")
    return CONTRACTS[model_name]


def list_contracts() -> List[Dict[str, Any]]:
    """Return all capability contracts in the platform."""
    return [c.to_dict() for c in CONTRACTS.values()]
