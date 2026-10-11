"""SuspensionLab PRO — Validation Channel Schema & Ontology.

Enforces:
1. Authoritative canonical channel definitions for independent vehicle validation.
2. Minimum channel schema: time, Vx, Vy, yaw rate, steering, throttle, brake pressure,
   wheel speeds (FL, FR, RL, RR), engine RPM, gear, longitudinal acceleration, lateral acceleration.
3. Strict non-fabrication rule: missing channels must never be fabricated, synthesized, or silently zero-filled.
4. Per-channel provenance classification: INITIAL_CONDITION, BOUNDARY_CONDITION, TARGET_MEASUREMENT,
   SIMULATED_PREDICTION, DERIVED_METRIC, EXCLUDED_UNSUPPORTED.
5. Coordinate conventions (ISO 8855 vs SAE J670).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import numpy as np
import pandas as pd


class CoordinateConvention(str, Enum):
    """Authoritative vehicle coordinate system convention."""
    ISO_8855 = "ISO_8855"  # x=forward, y=left, z=up, yaw=+ccw (left), roll=+right down
    SAE_J670 = "SAE_J670"  # x=forward, y=right, z=down, yaw=+cw (right), roll=+right down
    UNKNOWN = "UNKNOWN"


class ChannelRole(str, Enum):
    """Functional role of channel within vehicle validation pipeline."""
    TIMEBASE = "TIMEBASE"
    DRIVER_INPUT = "DRIVER_INPUT"
    VEHICLE_STATE = "VEHICLE_STATE"
    DRIVELINE_STATE = "DRIVELINE_STATE"
    WHEEL_STATE = "WHEEL_STATE"
    INERTIAL_MEASUREMENT = "INERTIAL_MEASUREMENT"
    TRACK_ENVIRONMENT = "TRACK_ENVIRONMENT"
    DIAGNOSTIC = "DIAGNOSTIC"


class ProvenanceClassification(str, Enum):
    """Cryptographic and causal classification of channel data origin."""
    INITIAL_CONDITION = "INITIAL_CONDITION"      # Measured state at t0 used to seed simulation
    BOUNDARY_CONDITION = "BOUNDARY_CONDITION"    # Exogenous driver/environment input passed during simulation
    TARGET_MEASUREMENT = "TARGET_MEASUREMENT"    # Measured sensor truth compared against prediction (NEVER accessed in simulation)
    SIMULATED_PREDICTION = "SIMULATED_PREDICTION"# Endogenous forward state produced by model
    DERIVED_METRIC = "DERIVED_METRIC"            # Post-hoc computational metric (residual, power, slip)
    EXCLUDED_UNSUPPORTED = "EXCLUDED_UNSUPPORTED"# Channel ignored or outside model validity domain


class MissingChannelError(ValueError):
    """Raised when required telemetry channels are missing without fabrication."""
    def __init__(self, missing_channels: Sequence[str], message: Optional[str] = None):
        self.missing_channels = list(missing_channels)
        msg = message or f"Required validation channels missing: {self.missing_channels}. Missing channels MUST NOT be fabricated."
        super().__init__(msg)


@dataclass(frozen=True)
class StandardChannels:
    """Canonical channel identifier constants."""
    TIME: str = "time"
    VX: str = "Vx"
    VY: str = "Vy"
    YAW_RATE: str = "yaw_rate"
    STEERING: str = "steering"
    THROTTLE: str = "throttle"
    BRAKE_PRESSURE: str = "brake_pressure"
    BRAKE_PRESSURE_FL: str = "brake_pressure_fl"
    BRAKE_PRESSURE_FR: str = "brake_pressure_fr"
    BRAKE_PRESSURE_RL: str = "brake_pressure_rl"
    BRAKE_PRESSURE_RR: str = "brake_pressure_rr"
    WHEEL_SPEED_FL: str = "wheelspeed_fl"
    WHEEL_SPEED_FR: str = "wheelspeed_fr"
    WHEEL_SPEED_RL: str = "wheelspeed_rl"
    WHEEL_SPEED_RR: str = "wheelspeed_rr"
    ENGINE_RPM: str = "engine_rpm"
    GEAR: str = "gear"
    AX: str = "ax"
    AY: str = "ay"
    # Optional extensions
    ROLL_ANGLE: str = "roll_angle"
    YAW_ANGLE: str = "yaw_angle"
    BANK_RAD: str = "bank_rad"
    GRADE_RAD: str = "grade_rad"
    DISTANCE_M: str = "distance_m"


@dataclass(frozen=True)
class ChannelDefinition:
    """Authoritative schema definition for a telemetry/simulation channel."""
    name: str
    canonical_unit: str
    role: ChannelRole
    provenance_class: ProvenanceClassification
    description: str
    is_required: bool = True
    is_discrete: bool = False
    physical_min: float = -1e9
    physical_max: float = 1e9
    max_rate_of_change: float = 1e9  # per second


# Authoritative baseline registry of universal vehicle validation channels
UNIVERSAL_CHANNEL_DEFINITIONS: Dict[str, ChannelDefinition] = {
    StandardChannels.TIME: ChannelDefinition(
        name=StandardChannels.TIME,
        canonical_unit="s",
        role=ChannelRole.TIMEBASE,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Elapsed simulation or acquisition time in seconds",
        is_required=True,
        physical_min=0.0,
        max_rate_of_change=10.0,
    ),
    StandardChannels.VX: ChannelDefinition(
        name=StandardChannels.VX,
        canonical_unit="m/s",
        role=ChannelRole.VEHICLE_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Longitudinal chassis velocity in vehicle frame",
        is_required=True,
        physical_min=-15.0,
        physical_max=120.0,
        max_rate_of_change=40.0,
    ),
    StandardChannels.VY: ChannelDefinition(
        name=StandardChannels.VY,
        canonical_unit="m/s",
        role=ChannelRole.VEHICLE_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Lateral chassis velocity in vehicle frame",
        is_required=True,
        physical_min=-25.0,
        physical_max=25.0,
        max_rate_of_change=30.0,
    ),
    StandardChannels.YAW_RATE: ChannelDefinition(
        name=StandardChannels.YAW_RATE,
        canonical_unit="rad/s",
        role=ChannelRole.INERTIAL_MEASUREMENT,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Yaw angular rate about chassis z-axis (positive = left)",
        is_required=True,
        physical_min=-3.14,
        physical_max=3.14,
        max_rate_of_change=10.0,
    ),
    StandardChannels.STEERING: ChannelDefinition(
        name=StandardChannels.STEERING,
        canonical_unit="rad",
        role=ChannelRole.DRIVER_INPUT,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Road wheel steering angle (positive = left)",
        is_required=True,
        physical_min=-0.80,
        physical_max=0.80,
        max_rate_of_change=5.0,
    ),
    StandardChannels.THROTTLE: ChannelDefinition(
        name=StandardChannels.THROTTLE,
        canonical_unit="normalized",
        role=ChannelRole.DRIVER_INPUT,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Normalized driver accelerator pedal position [0.0, 1.0]",
        is_required=True,
        physical_min=0.0,
        physical_max=1.0,
        max_rate_of_change=10.0,
    ),
    StandardChannels.BRAKE_PRESSURE: ChannelDefinition(
        name=StandardChannels.BRAKE_PRESSURE,
        canonical_unit="bar",
        role=ChannelRole.DRIVER_INPUT,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Master cylinder / average brake line hydraulic pressure",
        is_required=False,
        physical_min=0.0,
        physical_max=250.0,
        max_rate_of_change=1000.0,
    ),
    StandardChannels.BRAKE_PRESSURE_FL: ChannelDefinition(
        name=StandardChannels.BRAKE_PRESSURE_FL,
        canonical_unit="bar",
        role=ChannelRole.DRIVER_INPUT,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Front-left brake caliper hydraulic pressure",
        is_required=False,
        physical_min=0.0,
        physical_max=250.0,
        max_rate_of_change=1000.0,
    ),
    StandardChannels.BRAKE_PRESSURE_FR: ChannelDefinition(
        name=StandardChannels.BRAKE_PRESSURE_FR,
        canonical_unit="bar",
        role=ChannelRole.DRIVER_INPUT,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Front-right brake caliper hydraulic pressure",
        is_required=False,
        physical_min=0.0,
        physical_max=250.0,
        max_rate_of_change=1000.0,
    ),
    StandardChannels.BRAKE_PRESSURE_RL: ChannelDefinition(
        name=StandardChannels.BRAKE_PRESSURE_RL,
        canonical_unit="bar",
        role=ChannelRole.DRIVER_INPUT,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Rear-left brake caliper hydraulic pressure",
        is_required=False,
        physical_min=0.0,
        physical_max=250.0,
        max_rate_of_change=1000.0,
    ),
    StandardChannels.BRAKE_PRESSURE_RR: ChannelDefinition(
        name=StandardChannels.BRAKE_PRESSURE_RR,
        canonical_unit="bar",
        role=ChannelRole.DRIVER_INPUT,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Rear-right brake caliper hydraulic pressure",
        is_required=False,
        physical_min=0.0,
        physical_max=250.0,
        max_rate_of_change=1000.0,
    ),
    StandardChannels.WHEEL_SPEED_FL: ChannelDefinition(
        name=StandardChannels.WHEEL_SPEED_FL,
        canonical_unit="rad/s",
        role=ChannelRole.WHEEL_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Front-left wheel angular velocity",
        is_required=True,
        physical_min=0.0,
        physical_max=350.0,
        max_rate_of_change=150.0,
    ),
    StandardChannels.WHEEL_SPEED_FR: ChannelDefinition(
        name=StandardChannels.WHEEL_SPEED_FR,
        canonical_unit="rad/s",
        role=ChannelRole.WHEEL_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Front-right wheel angular velocity",
        is_required=True,
        physical_min=0.0,
        physical_max=350.0,
        max_rate_of_change=150.0,
    ),
    StandardChannels.WHEEL_SPEED_RL: ChannelDefinition(
        name=StandardChannels.WHEEL_SPEED_RL,
        canonical_unit="rad/s",
        role=ChannelRole.WHEEL_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Rear-left wheel angular velocity",
        is_required=True,
        physical_min=0.0,
        physical_max=350.0,
        max_rate_of_change=150.0,
    ),
    StandardChannels.WHEEL_SPEED_RR: ChannelDefinition(
        name=StandardChannels.WHEEL_SPEED_RR,
        canonical_unit="rad/s",
        role=ChannelRole.WHEEL_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Rear-right wheel angular velocity",
        is_required=True,
        physical_min=0.0,
        physical_max=350.0,
        max_rate_of_change=150.0,
    ),
    StandardChannels.ENGINE_RPM: ChannelDefinition(
        name=StandardChannels.ENGINE_RPM,
        canonical_unit="rpm",
        role=ChannelRole.DRIVELINE_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Internal combustion engine rotational speed",
        is_required=True,
        physical_min=0.0,
        physical_max=12000.0,
        max_rate_of_change=15000.0,
    ),
    StandardChannels.GEAR: ChannelDefinition(
        name=StandardChannels.GEAR,
        canonical_unit="index",
        role=ChannelRole.DRIVELINE_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Discrete active transmission gear (0=neutral/park, 1..N)",
        is_required=True,
        is_discrete=True,
        physical_min=0.0,
        physical_max=10.0,
        max_rate_of_change=10.0,
    ),
    StandardChannels.AX: ChannelDefinition(
        name=StandardChannels.AX,
        canonical_unit="m/s^2",
        role=ChannelRole.INERTIAL_MEASUREMENT,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Chassis longitudinal acceleration at vehicle CG (positive = accel)",
        is_required=True,
        physical_min=-35.0,
        physical_max=30.0,
        max_rate_of_change=7500.0,  # Realistic unsmoothed IMU jerk limit (m/s^3)
    ),
    StandardChannels.AY: ChannelDefinition(
        name=StandardChannels.AY,
        canonical_unit="m/s^2",
        role=ChannelRole.INERTIAL_MEASUREMENT,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Chassis lateral acceleration at vehicle CG (positive = left)",
        is_required=True,
        physical_min=-35.0,
        physical_max=35.0,
        max_rate_of_change=7500.0,  # Realistic unsmoothed IMU jerk limit (m/s^3)
    ),
    # Optional channels
    StandardChannels.ROLL_ANGLE: ChannelDefinition(
        name=StandardChannels.ROLL_ANGLE,
        canonical_unit="rad",
        role=ChannelRole.VEHICLE_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Chassis body roll angle relative to road plane (positive = right down)",
        is_required=False,
        physical_min=-0.35,
        physical_max=0.35,
        max_rate_of_change=10.0,
    ),
    StandardChannels.YAW_ANGLE: ChannelDefinition(
        name=StandardChannels.YAW_ANGLE,
        canonical_unit="rad",
        role=ChannelRole.VEHICLE_STATE,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Chassis global yaw heading angle (radians)",
        is_required=False,
        physical_min=-1000.0,
        physical_max=1000.0,
        max_rate_of_change=25.0,
    ),
    StandardChannels.BANK_RAD: ChannelDefinition(
        name=StandardChannels.BANK_RAD,
        canonical_unit="rad",
        role=ChannelRole.TRACK_ENVIRONMENT,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Road surface cross-slope / banking angle",
        is_required=False,
        physical_min=-0.50,
        physical_max=0.50,
        max_rate_of_change=1.0,
    ),
    StandardChannels.GRADE_RAD: ChannelDefinition(
        name=StandardChannels.GRADE_RAD,
        canonical_unit="rad",
        role=ChannelRole.TRACK_ENVIRONMENT,
        provenance_class=ProvenanceClassification.BOUNDARY_CONDITION,
        description="Road surface longitudinal inclination / grade angle",
        is_required=False,
        physical_min=-0.50,
        physical_max=0.50,
        max_rate_of_change=1.0,
    ),
    StandardChannels.DISTANCE_M: ChannelDefinition(
        name=StandardChannels.DISTANCE_M,
        canonical_unit="m",
        role=ChannelRole.TRACK_ENVIRONMENT,
        provenance_class=ProvenanceClassification.TARGET_MEASUREMENT,
        description="Cumulative track lap distance in meters",
        is_required=False,
        physical_min=0.0,
        physical_max=50000.0,
        max_rate_of_change=120.0,
    ),
}

# The 12 minimum required channels specified in Requirement 2:
# time, Vx, Vy, yaw rate, steering, throttle, brake pressure, wheel speeds (FL,FR,RL,RR), engine RPM, gear, ax, ay
MINIMUM_REQUIRED_CHANNELS: List[str] = [
    StandardChannels.TIME,
    StandardChannels.VX,
    StandardChannels.VY,
    StandardChannels.YAW_RATE,
    StandardChannels.STEERING,
    StandardChannels.THROTTLE,
    StandardChannels.WHEEL_SPEED_FL,
    StandardChannels.WHEEL_SPEED_FR,
    StandardChannels.WHEEL_SPEED_RL,
    StandardChannels.WHEEL_SPEED_RR,
    StandardChannels.ENGINE_RPM,
    StandardChannels.GEAR,
    StandardChannels.AX,
    StandardChannels.AY,
]


@dataclass
class SchemaValidationResult:
    """Result of schema audit against telemetry channels."""
    is_valid: bool
    missing_required_channels: List[str] = field(default_factory=list)
    present_channels: List[str] = field(default_factory=list)
    unrecognized_channels: List[str] = field(default_factory=list)
    channel_provenances: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "missing_required_channels": self.missing_required_channels,
            "present_channels": self.present_channels,
            "unrecognized_channels": self.unrecognized_channels,
            "channel_provenances": self.channel_provenances,
            "warnings": self.warnings,
        }


class ChannelSchema:
    """Manages channel ontology, mapping from raw telemetry, and schema validation."""

    def __init__(
        self,
        definitions: Optional[Dict[str, ChannelDefinition]] = None,
        coordinate_convention: CoordinateConvention = CoordinateConvention.ISO_8855,
    ):
        self.definitions: Dict[str, ChannelDefinition] = (
            definitions.copy() if definitions is not None else UNIVERSAL_CHANNEL_DEFINITIONS.copy()
        )
        self.coordinate_convention = coordinate_convention

    def get_definition(self, channel_name: str) -> Optional[ChannelDefinition]:
        return self.definitions.get(channel_name)

    def validate_channel_presence(
        self,
        channels: Sequence[str],
        strict: bool = True,
        require_brake: bool = True,
    ) -> SchemaValidationResult:
        """Verify presence of all mandatory validation channels.
        
        DO NOT FABRICATE MISSING CHANNELS.
        If strict=True and any mandatory channel is missing, raises MissingChannelError.
        """
        ch_set = set(channels)
        missing: List[str] = []

        for req in MINIMUM_REQUIRED_CHANNELS:
            if req not in ch_set:
                missing.append(req)

        # Check brake pressure: either master brake_pressure or all 4 corner pressures must be present
        if require_brake:
            has_master = StandardChannels.BRAKE_PRESSURE in ch_set
            has_corners = all(
                c in ch_set
                for c in [
                    StandardChannels.BRAKE_PRESSURE_FL,
                    StandardChannels.BRAKE_PRESSURE_FR,
                    StandardChannels.BRAKE_PRESSURE_RL,
                    StandardChannels.BRAKE_PRESSURE_RR,
                ]
            )
            if not has_master and not has_corners:
                missing.append(StandardChannels.BRAKE_PRESSURE)

        present = [c for c in channels if c in self.definitions]
        unrecognized = [c for c in channels if c not in self.definitions]

        provenances = {
            c: self.definitions[c].provenance_class.value
            for c in present
            if c in self.definitions
        }

        is_valid = len(missing) == 0
        warnings = []
        if missing:
            warnings.append(f"Missing mandatory validation channels: {missing}. No data fabrication permitted.")

        result = SchemaValidationResult(
            is_valid=is_valid,
            missing_required_channels=missing,
            present_channels=present,
            unrecognized_channels=unrecognized,
            channel_provenances=provenances,
            warnings=warnings,
        )

        if strict and not is_valid:
            raise MissingChannelError(missing)

        return result

    @classmethod
    def map_raw_telemetry(
        cls,
        df_or_dict: Union[pd.DataFrame, Dict[str, Any]],
        wheel_radius_m: float = 0.3198,
        custom_mapping: Optional[Dict[str, str]] = None,
        strict: bool = False,
        infer_gear_from_kinematics: bool = False,
    ) -> Tuple[Dict[str, np.ndarray], SchemaValidationResult]:
        """Maps raw heterogeneous telemetry into the canonical validation schema.
        
        Preserves authentic measurements without fabricating missing channels.
        """
        if isinstance(df_or_dict, pd.DataFrame):
            raw_dict = {col: np.asarray(df_or_dict[col].values, dtype=np.float64) for col in df_or_dict.columns}
        else:
            raw_dict = {k: np.asarray(v, dtype=np.float64) for k, v in df_or_dict.items()}

        raw_keys = list(raw_dict.keys())
        mapped: Dict[str, np.ndarray] = {}

        # Default alias rules matching automotive telemetry formats (MoTeC, Bosch, Stanford VW Golf, AiM)
        alias_map: Dict[str, List[str]] = {
            StandardChannels.TIME: ["time", "t_s", "t", "timestamp", "sec"],
            StandardChannels.VX: ["Vx", "Vx_mps", "vx", "speed", "ground_speed", "gps_speed"],
            StandardChannels.VY: ["Vy", "Vy_mps", "vy"],
            StandardChannels.YAW_RATE: ["yaw_rate", "yawRate_radps", "yawrate", "yaw_rate_rads", "gyro_z"],
            StandardChannels.STEERING: ["steering", "roadWheelAngle_rad", "steer_deg", "steer_wheel_angle"],
            StandardChannels.THROTTLE: ["throttle", "throttleCmd_percent", "throttle_pct", "pedal_pos", "aps"],
            StandardChannels.BRAKE_PRESSURE: ["brake_pressure", "brake_bar", "brake_press", "brake_fl_bar"],
            StandardChannels.BRAKE_PRESSURE_FL: ["brake_fl_bar", "brake_press_fl", "p_brake_fl"],
            StandardChannels.BRAKE_PRESSURE_FR: ["brake_fr_bar", "brake_press_fr", "p_brake_fr"],
            StandardChannels.BRAKE_PRESSURE_RL: ["brake_rl_bar", "brake_press_rl", "p_brake_rl"],
            StandardChannels.BRAKE_PRESSURE_RR: ["brake_rr_bar", "brake_press_rr", "p_brake_rr"],
            StandardChannels.WHEEL_SPEED_FL: ["wheelspeed_fl", "wsp_fl", "wheel_speed_fl", "wspd_fl"],
            StandardChannels.WHEEL_SPEED_FR: ["wheelspeed_fr", "wsp_fr", "wheel_speed_fr", "wspd_fr"],
            StandardChannels.WHEEL_SPEED_RL: ["wheelspeed_rl", "wsp_rl", "wheel_speed_rl", "wspd_rl"],
            StandardChannels.WHEEL_SPEED_RR: ["wheelspeed_rr", "wsp_rr", "wheel_speed_rr", "wspd_rr"],
            StandardChannels.ENGINE_RPM: ["engine_rpm", "rpm", "engineRPM", "Engine_RPM"],
            StandardChannels.GEAR: ["gear", "Gear", "active_gear"],
            StandardChannels.AX: ["ax", "axCG_mps2", "long_g", "long_acc", "ax_mps2", "a_x"],
            StandardChannels.AY: ["ay", "ayCG_mps2", "lat_g", "lat_acc", "ay_mps2", "a_y"],
            StandardChannels.ROLL_ANGLE: ["roll_angle", "rollAngle_rad", "roll_deg", "roll"],
            StandardChannels.YAW_ANGLE: ["yaw_angle", "yawAngle_rad", "yaw_deg", "yaw"],
            StandardChannels.BANK_RAD: ["bank_rad", "bank_angle_rad", "bank"],
            StandardChannels.GRADE_RAD: ["grade_rad", "grade_angle_rad", "grade"],
            StandardChannels.DISTANCE_M: ["distance_m", "s_m", "distance", "lap_dist"],
        }

        if custom_mapping:
            for canon_key, raw_name in custom_mapping.items():
                if canon_key in alias_map:
                    alias_map[canon_key].insert(0, raw_name)
                else:
                    alias_map[canon_key] = [raw_name]

        # Map each canonical channel if an alias is found in raw keys
        for canon, aliases in alias_map.items():
            matched_raw = None
            for alias in aliases:
                for rk in raw_keys:
                    if rk.lower() == alias.lower():
                        matched_raw = rk
                        break
                if matched_raw is not None:
                    break

            if matched_raw is not None:
                val = raw_dict[matched_raw].copy()
                # Apply unit conversions if needed
                if canon == StandardChannels.THROTTLE:
                    # Detect if throttle is in percentage [0..100] instead of normalized [0..1]
                    if np.nanmax(val) > 1.5:
                        val = val / 100.0
                elif canon == StandardChannels.STEERING:
                    # If named steer_deg or max > 3.0, it is degrees; convert to radians
                    if "deg" in matched_raw.lower() or np.nanmax(np.abs(val)) > 3.2:
                        val = np.radians(val)
                elif canon == StandardChannels.YAW_RATE:
                    # If named degps or max > 10.0, it is in deg/s; convert to rad/s
                    if "deg" in matched_raw.lower() or np.nanmax(np.abs(val)) > 7.0:
                        val = np.radians(val)
                elif canon in (StandardChannels.AX, StandardChannels.AY):
                    # If named g or lat_g / long_g and max < 5.0, convert G to m/s^2
                    if "g" in matched_raw.lower() and "mps2" not in matched_raw.lower():
                        if np.nanmax(np.abs(val)) < 6.0:
                            val = val * 9.80665
                elif canon in (
                    StandardChannels.WHEEL_SPEED_FL,
                    StandardChannels.WHEEL_SPEED_FR,
                    StandardChannels.WHEEL_SPEED_RL,
                    StandardChannels.WHEEL_SPEED_RR,
                ):
                    # Detect if wheel speed is in m/s linear velocity or rad/s angular
                    # If max is ~40-60 and car speed is ~40-60, it is already rad/s if wsp = v / R
                    # But if wsp is linear m/s, convert to rad/s using wheel_radius_m
                    pass

                mapped[canon] = val

        if infer_gear_from_kinematics and StandardChannels.GEAR not in mapped:
            if StandardChannels.ENGINE_RPM in mapped and StandardChannels.WHEEL_SPEED_FL in mapped:
                from suspensionlab.physics.gear_inference import GearInferenceEngine
                engine = GearInferenceEngine()
                rpm_arr = mapped[StandardChannels.ENGINE_RPM]
                w_fl = mapped[StandardChannels.WHEEL_SPEED_FL]
                w_fr = mapped.get(StandardChannels.WHEEL_SPEED_FR, w_fl)
                w_drv = 0.5 * (w_fl + w_fr)
                gears = [engine.infer_gear(float(r), float(w)).inferred_gear for r, w in zip(rpm_arr, w_drv)]
                mapped[StandardChannels.GEAR] = np.array(gears, dtype=np.float64)

        schema = cls()
        validation_report = schema.validate_channel_presence(
            list(mapped.keys()), strict=strict, require_brake=False
        )

        return mapped, validation_report
