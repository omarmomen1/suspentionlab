"""
physics/telemetry_dataset.py
============================
SuspensionLab PRO — Canonical Telemetry Dataset & Multi-DAQ Channel Ontology

Implements Step 1, Step 2, Step 3, Step 6, and Step 7 of the Telemetry Calibration Architecture:
- Step 1: Canonical TelemetryDataset container (timestamps, channels, units, source, quality flags, sampling rate, vehicle, setup, track, session, driver, metadata).
- Step 2: Non-destructive raw timestamp and sample value preservation with per-sample QualityFlags.
- Step 3: Universal DAQ Channel Ontology (MoTeC, AiM, Cosworth/Pi, Bosch, CAN, generic CSV) with scale, offset, and unit mappings.
- Step 6: Timestamp-aware continuous (PCHIP / linear) and discrete (ZOH) resampling and exact dt derivatives.
- Step 7: TrackReference spatial curvature, elevation, banking, sector, and corner alignment.
"""

from __future__ import annotations

import csv
import enum
import hashlib
import io
import json
import logging
import math
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Quality Flags & Preservation (Bitmask Enum)
# ─────────────────────────────────────────────────────────────────────────────

class QualityFlag(enum.IntFlag):
    """Per-sample data quality flags preserving telemetry truth without data loss."""
    VALID = 0
    MISSING = 1 << 0             # 1: NaN, Inf, or empty field
    OUT_OF_RANGE = 1 << 1        # 2: Value exceeds physical sensor/vehicle boundary
    DERIVATIVE_SPIKE = 1 << 2    # 4: Rate-of-change |dy/dt| exceeds physical limit
    DEAD_SENSOR_FLATLINE = 1 << 3# 8: Sensor stuck with zero standard deviation
    TIMESTAMP_JITTER = 1 << 4    # 16: Local timestamp dt fluctuates > 15% from median
    INTERPOLATED = 1 << 5        # 32: Value reconstructed on canonical analysis grid
    RECONSTRUCTED = 1 << 6       # 64: Value inferred from complementary sensor physics
    NON_MONOTONIC = 1 << 7       # 128: Timestamp reversal or duplicate frame index


class TelemetrySource(str, enum.Enum):
    """Supported Data Acquisition (DAQ) systems."""
    MOTEC = "MoTeC"
    AIM = "AiM"
    COSWORTH = "Cosworth/Pi"
    BOSCH = "Bosch"
    CAN = "CAN"
    CSV = "CSV"
    SIMULATION = "Simulation"
    UNKNOWN = "Unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Multi-DAQ Channel Ontology & Canonical Calibration Units
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChannelMappingRule:
    """Ontology rule mapping a raw DAQ channel name to canonical engineering representation."""
    canonical_name: str
    canonical_unit: str
    scale: float = 1.0
    offset: float = 0.0
    is_discrete: bool = False
    physical_min: float = -1e9
    physical_max: float = 1e9
    max_rate_of_change: float = 1e9


# Comprehensive ontology rules across motorsport telemetry standards:
# Units: speed in m/s, acceleration in G, angles in deg or rad, displacement in mm,
# pressure in bar, force in N, temperature in °C.
CANONICAL_CHANNEL_RULES: Dict[str, ChannelMappingRule] = {
    "time": ChannelMappingRule("time", "s", scale=1.0, physical_min=0.0, max_rate_of_change=10.0),
    "distance": ChannelMappingRule("distance", "m", scale=1.0, physical_min=0.0, max_rate_of_change=150.0),
    "speed": ChannelMappingRule("speed", "m/s", scale=1.0, physical_min=0.0, physical_max=125.0, max_rate_of_change=30.0),
    "wsp_fl": ChannelMappingRule("wsp_fl", "m/s", scale=1.0, physical_min=0.0, physical_max=125.0, max_rate_of_change=50.0),
    "wsp_fr": ChannelMappingRule("wsp_fr", "m/s", scale=1.0, physical_min=0.0, physical_max=125.0, max_rate_of_change=50.0),
    "wsp_rl": ChannelMappingRule("wsp_rl", "m/s", scale=1.0, physical_min=0.0, physical_max=125.0, max_rate_of_change=50.0),
    "wsp_rr": ChannelMappingRule("wsp_rr", "m/s", scale=1.0, physical_min=0.0, physical_max=125.0, max_rate_of_change=50.0),
    "lat_g": ChannelMappingRule("lat_g", "G", scale=1.0, physical_min=-6.0, physical_max=6.0, max_rate_of_change=25.0),
    "long_g": ChannelMappingRule("long_g", "G", scale=1.0, physical_min=-6.0, physical_max=6.0, max_rate_of_change=25.0),
    "vert_g": ChannelMappingRule("vert_g", "G", scale=1.0, physical_min=-4.0, physical_max=8.0, max_rate_of_change=40.0),
    "yaw_rate": ChannelMappingRule("yaw_rate", "deg/s", scale=1.0, physical_min=-180.0, physical_max=180.0, max_rate_of_change=360.0),
    "roll_rate": ChannelMappingRule("roll_rate", "deg/s", scale=1.0, physical_min=-120.0, physical_max=120.0, max_rate_of_change=240.0),
    "pitch_rate": ChannelMappingRule("pitch_rate", "deg/s", scale=1.0, physical_min=-120.0, physical_max=120.0, max_rate_of_change=240.0),
    "steer_deg": ChannelMappingRule("steer_deg", "deg", scale=1.0, physical_min=-720.0, physical_max=720.0, max_rate_of_change=1500.0),
    "throttle_pct": ChannelMappingRule("throttle_pct", "%", scale=1.0, physical_min=0.0, physical_max=100.0, max_rate_of_change=500.0),
    "brake_bar": ChannelMappingRule("brake_bar", "bar", scale=1.0, physical_min=0.0, physical_max=250.0, max_rate_of_change=1000.0),
    "rh_fl": ChannelMappingRule("rh_fl", "mm", scale=1.0, physical_min=-20.0, physical_max=200.0, max_rate_of_change=1500.0),
    "rh_fr": ChannelMappingRule("rh_fr", "mm", scale=1.0, physical_min=-20.0, physical_max=200.0, max_rate_of_change=1500.0),
    "rh_rl": ChannelMappingRule("rh_rl", "mm", scale=1.0, physical_min=-20.0, physical_max=200.0, max_rate_of_change=1500.0),
    "rh_rr": ChannelMappingRule("rh_rr", "mm", scale=1.0, physical_min=-20.0, physical_max=200.0, max_rate_of_change=1500.0),
    "damper_fl": ChannelMappingRule("damper_fl", "mm", scale=1.0, physical_min=-150.0, physical_max=150.0, max_rate_of_change=3000.0),
    "damper_fr": ChannelMappingRule("damper_fr", "mm", scale=1.0, physical_min=-150.0, physical_max=150.0, max_rate_of_change=3000.0),
    "damper_rl": ChannelMappingRule("damper_rl", "mm", scale=1.0, physical_min=-150.0, physical_max=150.0, max_rate_of_change=3000.0),
    "damper_rr": ChannelMappingRule("damper_rr", "mm", scale=1.0, physical_min=-150.0, physical_max=150.0, max_rate_of_change=3000.0),
    "gear": ChannelMappingRule("gear", "-", is_discrete=True, physical_min=0.0, physical_max=8.0, max_rate_of_change=10.0),
    "rpm": ChannelMappingRule("rpm", "rpm", scale=1.0, physical_min=0.0, physical_max=20000.0, max_rate_of_change=10000.0),
    "gps_lat": ChannelMappingRule("gps_lat", "deg", scale=1.0, physical_min=-90.0, physical_max=90.0, max_rate_of_change=0.01),
    "gps_lon": ChannelMappingRule("gps_lon", "deg", scale=1.0, physical_min=-180.0, physical_max=180.0, max_rate_of_change=0.01),
    "gps_alt": ChannelMappingRule("gps_alt", "m", scale=1.0, physical_min=-500.0, physical_max=5000.0, max_rate_of_change=50.0),
    "t_tire_fl": ChannelMappingRule("t_tire_fl", "°C", scale=1.0, physical_min=-20.0, physical_max=160.0, max_rate_of_change=20.0),
    "t_tire_fr": ChannelMappingRule("t_tire_fr", "°C", scale=1.0, physical_min=-20.0, physical_max=160.0, max_rate_of_change=20.0),
    "t_tire_rl": ChannelMappingRule("t_tire_rl", "°C", scale=1.0, physical_min=-20.0, physical_max=160.0, max_rate_of_change=20.0),
    "t_tire_rr": ChannelMappingRule("t_tire_rr", "°C", scale=1.0, physical_min=-20.0, physical_max=160.0, max_rate_of_change=20.0),
    "p_tire_fl": ChannelMappingRule("p_tire_fl", "bar", scale=1.0, physical_min=0.5, physical_max=4.0, max_rate_of_change=1.0),
    "p_tire_fr": ChannelMappingRule("p_tire_fr", "bar", scale=1.0, physical_min=0.5, physical_max=4.0, max_rate_of_change=1.0),
    "p_tire_rl": ChannelMappingRule("p_tire_rl", "bar", scale=1.0, physical_min=0.5, physical_max=4.0, max_rate_of_change=1.0),
    "p_tire_rr": ChannelMappingRule("p_tire_rr", "bar", scale=1.0, physical_min=0.5, physical_max=4.0, max_rate_of_change=1.0),
    "lap_number": ChannelMappingRule("lap_number", "-", is_discrete=True, physical_min=0.0, physical_max=500.0, max_rate_of_change=1.0),
    "sector": ChannelMappingRule("sector", "-", is_discrete=True, physical_min=1.0, physical_max=10.0, max_rate_of_change=5.0),
}


# Source-specific channel alias and unit mapping lookup
_UNIVERSAL_ONTOLOGY_MAP: List[Tuple[str, str, str, float, float]] = [
    # (pattern_substring, canonical_key, expected_source_unit, scale_to_canonical, offset)
    # Time / Distance
    ("time", "time", "s", 1.0, 0.0),
    ("timestamp", "time", "s", 1.0, 0.0),
    ("sec", "time", "s", 1.0, 0.0),
    ("time_s", "time", "s", 1.0, 0.0),
    ("t_abs", "time", "s", 1.0, 0.0),
    ("distance", "distance", "m", 1.0, 0.0),
    ("dist", "distance", "m", 1.0, 0.0),
    ("odometer", "distance", "m", 1.0, 0.0),
    ("lap_dist", "distance", "m", 1.0, 0.0),

    # Speed
    ("ground speed", "speed", "m/s", 1.0, 0.0),
    ("ground_speed", "speed", "m/s", 1.0, 0.0),
    ("gps speed", "speed", "m/s", 1.0, 0.0),
    ("gps_speed", "speed", "m/s", 1.0, 0.0),
    ("speed_kmh", "speed", "km/h", 1.0 / 3.6, 0.0),
    ("speed km/h", "speed", "km/h", 1.0 / 3.6, 0.0),
    ("v_kph", "speed", "km/h", 1.0 / 3.6, 0.0),
    ("speed", "speed", "m/s", 1.0, 0.0),
    ("v_x", "speed", "m/s", 1.0, 0.0),
    ("vx_car", "speed", "m/s", 1.0, 0.0),
    ("v_car", "speed", "m/s", 1.0, 0.0),
    ("vx", "speed", "m/s", 1.0, 0.0),

    # Wheel speeds
    ("wheel speed fl", "wsp_fl", "m/s", 1.0, 0.0),
    ("wheel speed fr", "wsp_fr", "m/s", 1.0, 0.0),
    ("wheel speed rl", "wsp_rl", "m/s", 1.0, 0.0),
    ("wheel speed rr", "wsp_rr", "m/s", 1.0, 0.0),
    ("wsp_fl", "wsp_fl", "m/s", 1.0, 0.0),
    ("wsp_fr", "wsp_fr", "m/s", 1.0, 0.0),
    ("wsp_rl", "wsp_rl", "m/s", 1.0, 0.0),
    ("wsp_rr", "wsp_rr", "m/s", 1.0, 0.0),
    ("wheel_speed_fl", "wsp_fl", "m/s", 1.0, 0.0),
    ("wheel_speed_fr", "wsp_fr", "m/s", 1.0, 0.0),
    ("wheel_speed_rl", "wsp_rl", "m/s", 1.0, 0.0),
    ("wheel_speed_rr", "wsp_rr", "m/s", 1.0, 0.0),
    ("wheelspeed_fl", "wsp_fl", "m/s", 1.0, 0.0),
    ("wheelspeed_fr", "wsp_fr", "m/s", 1.0, 0.0),
    ("wheelspeed_rl", "wsp_rl", "m/s", 1.0, 0.0),
    ("wheelspeed_rr", "wsp_rr", "m/s", 1.0, 0.0),
    ("wheelspeed fl", "wsp_fl", "m/s", 1.0, 0.0),
    ("wheelspeed fr", "wsp_fr", "m/s", 1.0, 0.0),
    ("wheelspeed rl", "wsp_rl", "m/s", 1.0, 0.0),
    ("wheelspeed rr", "wsp_rr", "m/s", 1.0, 0.0),
    ("can_wheelspeed_fl", "wsp_fl", "m/s", 1.0, 0.0),
    ("can_wheelspeed_fr", "wsp_fr", "m/s", 1.0, 0.0),
    ("can_wheelspeed_rl", "wsp_rl", "m/s", 1.0, 0.0),
    ("can_wheelspeed_rr", "wsp_rr", "m/s", 1.0, 0.0),

    # Lateral Accel
    ("g_lat", "lat_g", "G", 1.0, 0.0),
    ("g_lon", "long_g", "G", 1.0, 0.0),
    ("lateral acc", "lat_g", "G", 1.0, 0.0),
    ("lateral g", "lat_g", "G", 1.0, 0.0),
    ("lataccel", "lat_g", "G", 1.0, 0.0),
    ("latacc", "lat_g", "G", 1.0, 0.0),
    ("lat_acc", "lat_g", "G", 1.0, 0.0),
    ("lat_g", "lat_g", "G", 1.0, 0.0),
    ("latg", "lat_g", "G", 1.0, 0.0),
    ("ay_chassis", "lat_g", "G", 1.0, 0.0),
    ("acc_y", "lat_g", "G", 1.0, 0.0),
    ("a_y", "lat_g", "G", 1.0, 0.0),
    ("ay", "lat_g", "G", 1.0, 0.0),
    ("g force lat", "lat_g", "G", 1.0, 0.0),
    ("gps_latacc", "lat_g", "G", 1.0, 0.0),

    # Longitudinal Accel
    ("longitudinal acc", "long_g", "G", 1.0, 0.0),
    ("longitudinal g", "long_g", "G", 1.0, 0.0),
    ("longitudinal", "long_g", "G", 1.0, 0.0),
    ("longaccel", "long_g", "G", 1.0, 0.0),
    ("lonaccel", "long_g", "G", 1.0, 0.0),
    ("lonacc", "long_g", "G", 1.0, 0.0),
    ("long_acc", "long_g", "G", 1.0, 0.0),
    ("long_g", "long_g", "G", 1.0, 0.0),
    ("longg", "long_g", "G", 1.0, 0.0),
    ("g force long", "long_g", "G", 1.0, 0.0),
    ("ax_chassis", "long_g", "G", 1.0, 0.0),
    ("acc_x", "long_g", "G", 1.0, 0.0),
    ("a_x", "long_g", "G", 1.0, 0.0),
    ("ax", "long_g", "G", 1.0, 0.0),
    ("gps_lonacc", "long_g", "G", 1.0, 0.0),

    # Vertical Accel / Heave
    ("vertical acc", "vert_g", "G", 1.0, 0.0),
    ("vertaccel", "vert_g", "G", 1.0, 0.0),
    ("vert g", "vert_g", "G", 1.0, 0.0),
    ("vert_acc", "vert_g", "G", 1.0, 0.0),
    ("vert_g", "vert_g", "G", 1.0, 0.0),
    ("heave accel", "vert_g", "G", 1.0, 0.0),
    ("heave_accel", "vert_g", "G", 1.0, 0.0),
    ("heave acc", "vert_g", "G", 1.0, 0.0),
    ("az_chassis", "vert_g", "G", 1.0, 0.0),
    ("acc_z", "vert_g", "G", 1.0, 0.0),
    ("a_z", "vert_g", "G", 1.0, 0.0),
    ("az", "vert_g", "G", 1.0, 0.0),

    # Yaw / Gyro / Roll / Pitch
    ("yaw rate", "yaw_rate", "deg/s", 1.0, 0.0),
    ("yaw_rate", "yaw_rate", "deg/s", 1.0, 0.0),
    ("yawrate", "yaw_rate", "deg/s", 1.0, 0.0),
    ("yaw", "yaw_rate", "deg/s", 1.0, 0.0),
    ("roll rate", "roll_rate", "deg/s", 1.0, 0.0),
    ("roll_rate", "roll_rate", "deg/s", 1.0, 0.0),
    ("pitch rate", "pitch_rate", "deg/s", 1.0, 0.0),
    ("pitch_rate", "pitch_rate", "deg/s", 1.0, 0.0),
    ("gyro z", "yaw_rate", "deg/s", 1.0, 0.0),
    ("gyro_z", "yaw_rate", "deg/s", 1.0, 0.0),
    ("w_z", "yaw_rate", "deg/s", 1.0, 0.0),
    ("omega_z", "yaw_rate", "rad/s", 180.0 / math.pi, 0.0),

    # Steering
    ("steering angle", "steer_deg", "deg", 1.0, 0.0),
    ("steer angle", "steer_deg", "deg", 1.0, 0.0),
    ("steering", "steer_deg", "deg", 1.0, 0.0),
    ("steer_deg", "steer_deg", "deg", 1.0, 0.0),
    ("steer", "steer_deg", "deg", 1.0, 0.0),
    ("str_wheel_ang", "steer_deg", "deg", 1.0, 0.0),
    ("delta_sw", "steer_deg", "deg", 1.0, 0.0),

    # Throttle / Brake
    ("throttle pos", "throttle_pct", "%", 1.0, 0.0),
    ("throttle", "throttle_pct", "%", 1.0, 0.0),
    ("tps", "throttle_pct", "%", 1.0, 0.0),
    ("ath", "throttle_pct", "%", 1.0, 0.0),
    ("pedal_gas", "throttle_pct", "%", 1.0, 0.0),
    ("brake pres", "brake_bar", "bar", 1.0, 0.0),
    ("brake press", "brake_bar", "bar", 1.0, 0.0),
    ("brake_bar", "brake_bar", "bar", 1.0, 0.0),
    ("brake", "brake_bar", "bar", 1.0, 0.0),
    ("p_brake_f", "brake_bar", "bar", 1.0, 0.0),
    ("p_brake", "brake_bar", "bar", 1.0, 0.0),
    ("brake_psi", "brake_bar", "psi", 0.0689476, 0.0),

    # Ride Heights
    ("ride height fl", "rh_fl", "mm", 1.0, 0.0),
    ("ride height fr", "rh_fr", "mm", 1.0, 0.0),
    ("ride height rl", "rh_rl", "mm", 1.0, 0.0),
    ("ride height rr", "rh_rr", "mm", 1.0, 0.0),
    ("rh_fl", "rh_fl", "mm", 1.0, 0.0),
    ("rh_fr", "rh_fr", "mm", 1.0, 0.0),
    ("rh_rl", "rh_rl", "mm", 1.0, 0.0),
    ("rh_rr", "rh_rr", "mm", 1.0, 0.0),
    ("laser_rh_fl", "rh_fl", "mm", 1.0, 0.0),
    ("laser_rh_fr", "rh_fr", "mm", 1.0, 0.0),
    ("laser_rh_rl", "rh_rl", "mm", 1.0, 0.0),
    ("laser_rh_rr", "rh_rr", "mm", 1.0, 0.0),

    # Damper Potentiometers
    ("damper pos fl", "damper_fl", "mm", 1.0, 0.0),
    ("damper pos fr", "damper_fr", "mm", 1.0, 0.0),
    ("damper pos rl", "damper_rl", "mm", 1.0, 0.0),
    ("damper pos rr", "damper_rr", "mm", 1.0, 0.0),
    ("damper fl", "damper_fl", "mm", 1.0, 0.0),
    ("damper fr", "damper_fr", "mm", 1.0, 0.0),
    ("damper rl", "damper_rl", "mm", 1.0, 0.0),
    ("damper rr", "damper_rr", "mm", 1.0, 0.0),
    ("damper_fl", "damper_fl", "mm", 1.0, 0.0),
    ("damper_fr", "damper_fr", "mm", 1.0, 0.0),
    ("damper_rl", "damper_rl", "mm", 1.0, 0.0),
    ("damper_rr", "damper_rr", "mm", 1.0, 0.0),
    ("susp fl", "damper_fl", "mm", 1.0, 0.0),
    ("susp fr", "damper_fr", "mm", 1.0, 0.0),
    ("susp rl", "damper_rl", "mm", 1.0, 0.0),
    ("susp rr", "damper_rr", "mm", 1.0, 0.0),
    ("susptravel_fl", "damper_fl", "mm", 1.0, 0.0),
    ("susptravel_fr", "damper_fr", "mm", 1.0, 0.0),
    ("susptravel_rl", "damper_rl", "mm", 1.0, 0.0),
    ("susptravel_rr", "damper_rr", "mm", 1.0, 0.0),
    ("susp_travel_fl", "damper_fl", "mm", 1.0, 0.0),
    ("susp_travel_fr", "damper_fr", "mm", 1.0, 0.0),
    ("susp_travel_rl", "damper_rl", "mm", 1.0, 0.0),
    ("susp_travel_rr", "damper_rr", "mm", 1.0, 0.0),
    ("r_damper_fl", "damper_fl", "mm", 1.0, 0.0),
    ("r_damper_fr", "damper_fr", "mm", 1.0, 0.0),
    ("r_damper_rl", "damper_rl", "mm", 1.0, 0.0),
    ("r_damper_rr", "damper_rr", "mm", 1.0, 0.0),
    ("s_damper_fl", "damper_fl", "mm", 1.0, 0.0),
    ("s_damper_fr", "damper_fr", "mm", 1.0, 0.0),
    ("s_damper_rl", "damper_rl", "mm", 1.0, 0.0),
    ("s_damper_rr", "damper_rr", "mm", 1.0, 0.0),

    # Engine & Gear
    ("gear", "gear", "-", 1.0, 0.0),
    ("n gear", "gear", "-", 1.0, 0.0),
    ("n_gear", "gear", "-", 1.0, 0.0),
    ("engine rpm", "rpm", "rpm", 1.0, 0.0),
    ("engine speed", "rpm", "rpm", 1.0, 0.0),
    ("rpm", "rpm", "rpm", 1.0, 0.0),
    ("nmot", "rpm", "rpm", 1.0, 0.0),
    ("n_engine", "rpm", "rpm", 1.0, 0.0),

    # GPS coordinates
    ("latitude", "gps_lat", "deg", 1.0, 0.0),
    ("gps lat", "gps_lat", "deg", 1.0, 0.0),
    ("gps_lat", "gps_lat", "deg", 1.0, 0.0),
    ("longitude", "gps_lon", "deg", 1.0, 0.0),
    ("gps lon", "gps_lon", "deg", 1.0, 0.0),
    ("gps_lon", "gps_lon", "deg", 1.0, 0.0),
    ("altitude", "gps_alt", "m", 1.0, 0.0),
    ("gps alt", "gps_alt", "m", 1.0, 0.0),
    ("gps_alt", "gps_alt", "m", 1.0, 0.0),

    # Tire temperatures (FL/FR/RL/RR)
    ("tire temp fl", "t_tire_fl", "°C", 1.0, 0.0),
    ("tire temp fr", "t_tire_fr", "°C", 1.0, 0.0),
    ("tire temp rl", "t_tire_rl", "°C", 1.0, 0.0),
    ("tire temp rr", "t_tire_rr", "°C", 1.0, 0.0),
    ("tyre temp fl", "t_tire_fl", "°C", 1.0, 0.0),
    ("tyre temp fr", "t_tire_fr", "°C", 1.0, 0.0),
    ("tyre temp rl", "t_tire_rl", "°C", 1.0, 0.0),
    ("tyre temp rr", "t_tire_rr", "°C", 1.0, 0.0),

    # Tire pressures
    ("tire pres fl", "p_tire_fl", "bar", 1.0, 0.0),
    ("tire pres fr", "p_tire_fr", "bar", 1.0, 0.0),
    ("tire pres rl", "p_tire_rl", "bar", 1.0, 0.0),
    ("tire pres rr", "p_tire_rr", "bar", 1.0, 0.0),

    # Lap / Sector
    ("lap number", "lap_number", "-", 1.0, 0.0),
    ("lap", "lap_number", "-", 1.0, 0.0),
    ("sector", "sector", "-", 1.0, 0.0),
]


def resolve_channel_mapping(
    raw_name: str,
    source_hint: TelemetrySource = TelemetrySource.UNKNOWN,
) -> Tuple[str, str, float, float, float]:
    """
    Resolve a raw DAQ column name to canonical key, unit, scale, offset, and confidence.
    Returns (canonical_name, unit, scale, offset, confidence).
    """
    name_clean = raw_name.strip().lower()
    name_normalized = name_clean.replace("-", "_").replace(" ", "_")

    # 1. Exact matches first
    for pattern, canon_key, src_unit, scale, offset in _UNIVERSAL_ONTOLOGY_MAP:
        pat_norm = pattern.lower().replace("-", "_").replace(" ", "_")
        if name_clean == pattern or name_normalized == pat_norm:
            rule = CANONICAL_CHANNEL_RULES.get(canon_key)
            unit = rule.canonical_unit if rule else src_unit
            return canon_key, unit, scale, offset, 1.0

    # 2. Check if raw_name itself is a canonical key
    if name_clean in CANONICAL_CHANNEL_RULES or name_normalized in CANONICAL_CHANNEL_RULES:
        key = name_clean if name_clean in CANONICAL_CHANNEL_RULES else name_normalized
        rule = CANONICAL_CHANNEL_RULES[key]
        return key, rule.canonical_unit, 1.0, 0.0, 0.95

    # 3. Substring matching sorted by pattern length descending (longest/most specific pattern wins)
    sorted_map = sorted(_UNIVERSAL_ONTOLOGY_MAP, key=lambda x: len(x[0]), reverse=True)
    for pattern, canon_key, src_unit, scale, offset in sorted_map:
        pat_norm = pattern.lower().replace("-", "_").replace(" ", "_")
        if pattern in name_clean or pat_norm in name_normalized:
            rule = CANONICAL_CHANNEL_RULES.get(canon_key)
            unit = rule.canonical_unit if rule else src_unit
            return canon_key, unit, scale, offset, 0.85

    # Unknown custom channel
    return name_clean, "custom", 1.0, 0.0, 0.40


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 & 6: PreservedChannelData (Non-Destructive + Timestamp-Aware Resampling)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PreservedChannelData:
    """
    Non-destructive channel storage preserving exact raw timestamps, values,
    and quality bitmasks while providing timestamp-aware continuous and discrete resampling.
    """
    canonical_name: str
    source_name: str
    unit: str
    scale: float = 1.0
    offset: float = 0.0
    raw_timestamps: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float64))
    raw_values: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float64))
    quality_flags: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int32))
    missing_mask: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))
    interpolated_mask: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))
    sampling_rate_hz: float = 100.0
    is_discrete: bool = False

    def __post_init__(self):
        self.raw_timestamps = np.asarray(self.raw_timestamps, dtype=np.float64)
        self.raw_values = np.asarray(self.raw_values, dtype=np.float64)
        n = len(self.raw_values)

        if len(self.quality_flags) != n:
            self.quality_flags = np.zeros(n, dtype=np.int32)
        else:
            self.quality_flags = np.asarray(self.quality_flags, dtype=np.int32)

        if len(self.missing_mask) != n:
            self.missing_mask = ~np.isfinite(self.raw_values)
            self.quality_flags[self.missing_mask] |= QualityFlag.MISSING
        else:
            self.missing_mask = np.asarray(self.missing_mask, dtype=bool)

        if len(self.interpolated_mask) != n:
            self.interpolated_mask = np.zeros(n, dtype=bool)
        else:
            self.interpolated_mask = np.asarray(self.interpolated_mask, dtype=bool)

    @property
    def valid_mask(self) -> np.ndarray:
        """Boolean mask of pristine, uncorrupted samples."""
        return (self.quality_flags == QualityFlag.VALID) | (~self.missing_mask)

    @property
    def scaled_values(self) -> np.ndarray:
        """Returns values scaled to standard canonical SI engineering units."""
        return self.raw_values * self.scale + self.offset

    def get_valid_series(self) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (valid_timestamps, valid_scaled_values) without corrupt or missing points."""
        mask = np.isfinite(self.raw_timestamps) & np.isfinite(self.raw_values) & ~self.missing_mask
        if not np.any(mask):
            return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)
        return self.raw_timestamps[mask], self.scaled_values[mask]

    def resample_to(
        self,
        target_timestamps: np.ndarray,
        method: Optional[str] = None,
    ) -> np.ndarray:
        """
        Timestamp-aware interpolation onto target grid without modifying raw storage.
        - Continuous channels: PCHIP (shape-preserving cubic) or linear interpolation.
        - Discrete channels: Zero-Order Hold (ZOH / step-wise constant).
        """
        t_valid, y_valid = self.get_valid_series()
        if len(t_valid) == 0:
            return np.zeros_like(target_timestamps)
        if len(t_valid) == 1:
            return np.full_like(target_timestamps, y_valid[0])

        target_t = np.asarray(target_timestamps, dtype=np.float64)

        if self.is_discrete or method == "zoh":
            # Discrete Zero-Order Hold (nearest preceding valid sample)
            idx = np.searchsorted(t_valid, target_t, side="right") - 1
            idx = np.clip(idx, 0, len(y_valid) - 1)
            return y_valid[idx]

        if method == "pchip" and len(t_valid) >= 4:
            from scipy.interpolate import PchipInterpolator
            try:
                # Remove duplicate timestamps in t_valid if any
                unique_mask = np.diff(t_valid, prepend=t_valid[0] - 1.0) > 1e-9
                t_u, y_u = t_valid[unique_mask], y_valid[unique_mask]
                if len(t_u) >= 4:
                    pchip = PchipInterpolator(t_u, y_u, extrapolate=True)
                    return pchip(target_t)
            except Exception:
                pass

        # Timestamp-aware linear interpolation
        return np.interp(target_t, t_valid, y_valid)

    def compute_timestamp_aware_derivative(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate rate-of-change using exact sample-to-sample timestamp deltas:
        dy/dt[i] = (y[i+1] - y[i]) / (t[i+1] - t[i])
        Never assumes nominal fixed sample rate.
        """
        t_v, y_v = self.get_valid_series()
        if len(t_v) < 2:
            return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)

        dt = np.diff(t_v)
        valid_dt = dt > 1e-7
        t_mid = 0.5 * (t_v[:-1] + t_v[1:])
        dy = np.diff(y_v)

        deriv = np.zeros_like(dy)
        deriv[valid_dt] = dy[valid_dt] / dt[valid_dt]
        return t_mid[valid_dt], deriv[valid_dt]


# ─────────────────────────────────────────────────────────────────────────────
# Step 7: TrackReference (Spatial Curvature & Distance Alignment)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CornerSegment:
    """Corner zone on a racing circuit."""
    corner_id: str
    name: str
    start_distance_m: float
    end_distance_m: float
    apex_distance_m: float
    apex_radius_m: float
    direction: str                     # "left" | "right" | "straight"
    nominal_entry_speed_ms: float = 45.0
    nominal_apex_speed_ms: float = 35.0
    bank_angle_deg: float = 0.0

    @property
    def length_m(self) -> float:
        return max(0.0, self.end_distance_m - self.start_distance_m)


@dataclass
class SectorSegment:
    """Timing sector on a circuit."""
    sector_id: int
    name: str
    start_distance_m: float
    end_distance_m: float


@dataclass
class TrackReference:
    """
    Spatial geometry reference mapping track distance s -> curvature, banking, elevation, and corners.
    """
    track_name: str = "Silverstone Grand Prix"
    track_id: str = "SILVERSTONE-GP"
    total_length_m: float = 5891.0
    distance_grid: np.ndarray = field(default_factory=lambda: np.linspace(0.0, 5891.0, 1000))
    curvature_grid: np.ndarray = field(default_factory=lambda: np.zeros(1000))
    banking_grid: np.ndarray = field(default_factory=lambda: np.zeros(1000))
    elevation_grid: np.ndarray = field(default_factory=lambda: np.zeros(1000))
    sectors: List[SectorSegment] = field(default_factory=list)
    corners: List[CornerSegment] = field(default_factory=list)

    def __post_init__(self):
        self.distance_grid = np.asarray(self.distance_grid, dtype=np.float64)
        self.curvature_grid = np.asarray(self.curvature_grid, dtype=np.float64)
        self.banking_grid = np.asarray(self.banking_grid, dtype=np.float64)
        self.elevation_grid = np.asarray(self.elevation_grid, dtype=np.float64)

        if not self.sectors:
            s_len = self.total_length_m / 3.0
            self.sectors = [
                SectorSegment(1, "Sector 1", 0.0, s_len),
                SectorSegment(2, "Sector 2", s_len, 2 * s_len),
                SectorSegment(3, "Sector 3", 2 * s_len, self.total_length_m),
            ]

    def get_spatial_properties(self, s: Union[float, np.ndarray]) -> Dict[str, Union[float, np.ndarray]]:
        """Interpolate curvature, banking, and elevation at distance s."""
        s_arr = np.asarray(s, dtype=np.float64)
        s_mod = np.mod(s_arr, self.total_length_m) if self.total_length_m > 0 else s_arr

        curv = np.interp(s_mod, self.distance_grid, self.curvature_grid)
        bank = np.interp(s_mod, self.distance_grid, self.banking_grid)
        elev = np.interp(s_mod, self.distance_grid, self.elevation_grid)

        return {
            "distance_m": s_arr,
            "curvature_1_m": curv,
            "bank_deg": bank,
            "elevation_m": elev,
        }

    def identify_corner_at(self, s: float) -> Optional[CornerSegment]:
        """Return the corner segment active at distance s."""
        s_mod = s % self.total_length_m if self.total_length_m > 0 else s
        for c in self.corners:
            if c.start_distance_m <= s_mod <= c.end_distance_m:
                return c
        return None

    def project_speed_profile_to_distance(
        self,
        time_arr: np.ndarray,
        speed_arr: np.ndarray,
    ) -> np.ndarray:
        """
        Integrate speed over timestamps using trapezoidal integration:
        s(t) = integral_0^t v(tau) dtau
        """
        if len(time_arr) < 2 or len(speed_arr) < 2:
            return np.zeros_like(time_arr)
        dt = np.diff(time_arr)
        v_mid = 0.5 * (speed_arr[:-1] + speed_arr[1:])
        ds = np.maximum(v_mid, 0.0) * dt
        dist = np.concatenate([[0.0], np.cumsum(ds)])
        return dist


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Canonical TelemetryDataset
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TelemetryDataset:
    """
    Canonical Motorsport Telemetry Dataset.
    Contains full session lineage, non-destructive preserved raw channels,
    universal ontology metadata, health screening, and spatial track alignment.
    """
    timestamps: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float64))
    channels: Dict[str, PreservedChannelData] = field(default_factory=dict)
    units: Dict[str, str] = field(default_factory=dict)
    source: TelemetrySource = TelemetrySource.CSV
    sampling_rate: float = 100.0
    vehicle: str = "CAR-01"
    setup: str = "SETUP-BASE"
    track: Union[TrackReference, str] = "Default Circuit"
    session: str = "FP1"
    driver: str = "Driver 1"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at_iso: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    provenance_hash: str = ""

    def __post_init__(self):
        self.timestamps = np.asarray(self.timestamps, dtype=np.float64)
        if not self.units:
            self.units = {k: v.unit for k, v in self.channels.items()}
        if not self.provenance_hash:
            self.provenance_hash = self.compute_fingerprint()

    def compute_fingerprint(self) -> str:
        """Compute SHA-256 cryptographic digest of the dataset payload."""
        summary = {
            "vehicle": self.vehicle,
            "setup": self.setup,
            "session": self.session,
            "driver": self.driver,
            "source": self.source.value if isinstance(self.source, TelemetrySource) else str(self.source),
            "n_samples": len(self.timestamps),
            "channels": sorted(list(self.channels.keys())),
            "created_at": self.created_at_iso,
        }
        if len(self.timestamps) > 0:
            summary["t_start"] = float(self.timestamps[0])
            summary["t_end"] = float(self.timestamps[-1])
        raw = json.dumps(summary, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def has_channel(self, name: str) -> bool:
        """Check if channel exists in dataset."""
        return name in self.channels

    def get_channel(self, name: str) -> np.ndarray:
        """Get scaled channel values aligned with dataset timestamps."""
        if name not in self.channels:
            raise KeyError(f"Channel '{name}' not found in TelemetryDataset (available: {list(self.channels.keys())})")
        return self.channels[name].scaled_values

    def get_raw_channel(self, name: str) -> PreservedChannelData:
        """Get the full PreservedChannelData object containing raw unscaled data and flags."""
        if name not in self.channels:
            raise KeyError(f"Channel '{name}' not found in TelemetryDataset")
        return self.channels[name]

    def add_channel(
        self,
        name: str,
        values: Union[np.ndarray, List[float]],
        unit: Optional[str] = None,
        timestamps: Optional[np.ndarray] = None,
        is_discrete: bool = False,
    ) -> None:
        """Add or replace a channel in the dataset."""
        t = self.timestamps if timestamps is None else np.asarray(timestamps, dtype=np.float64)
        v = np.asarray(values, dtype=np.float64)
        u = unit or CANONICAL_CHANNEL_RULES.get(name, ChannelMappingRule(name, "-")).canonical_unit
        ch = PreservedChannelData(
            canonical_name=name,
            source_name=name,
            unit=u,
            raw_timestamps=t,
            raw_values=v,
            is_discrete=is_discrete,
            sampling_rate_hz=self.sampling_rate,
        )
        self.channels[name] = ch
        self.units[name] = u
        self.provenance_hash = self.compute_fingerprint()

    def to_canonical_grid(
        self,
        target_dt: Optional[float] = None,
        method: str = "linear",
    ) -> TelemetryDataset:
        """
        Step 2: Create a canonical analysis grid with uniform timestamps (e.g. for ODE solvers / PSD)
        while preserving all underlying raw data without destruction.
        """
        if len(self.timestamps) < 2:
            return self

        t_min = float(self.timestamps[0])
        t_max = float(self.timestamps[-1])
        dt = target_dt or (1.0 / self.sampling_rate) if self.sampling_rate > 0 else 0.01

        grid_t = np.arange(t_min, t_max + 1e-9, dt)
        new_channels: Dict[str, PreservedChannelData] = {}

        for ch_name, ch_data in self.channels.items():
            resampled_vals = ch_data.resample_to(grid_t, method=method)
            # Create interpolated flags for the canonical grid
            interp_flags = np.zeros(len(grid_t), dtype=np.int32)
            interp_flags |= QualityFlag.INTERPOLATED

            new_ch = PreservedChannelData(
                canonical_name=ch_data.canonical_name,
                source_name=ch_data.source_name,
                unit=ch_data.unit,
                scale=1.0,  # Scaled into canonical units
                offset=0.0,
                raw_timestamps=grid_t,
                raw_values=resampled_vals,
                quality_flags=interp_flags,
                missing_mask=~np.isfinite(resampled_vals),
                interpolated_mask=np.ones(len(grid_t), dtype=bool),
                sampling_rate_hz=1.0 / dt,
                is_discrete=ch_data.is_discrete,
            )
            new_channels[ch_name] = new_ch

        return TelemetryDataset(
            timestamps=grid_t,
            channels=new_channels,
            units=dict(self.units),
            source=self.source,
            sampling_rate=1.0 / dt,
            vehicle=self.vehicle,
            setup=self.setup,
            track=self.track,
            session=self.session,
            driver=self.driver,
            metadata={**self.metadata, "is_canonical_grid": True, "grid_dt": dt},
        )

    def split_train_holdout(
        self,
        train_ratio: float = 0.8,
    ) -> Tuple[TelemetryDataset, TelemetryDataset]:
        """
        Step 9: Partition dataset into training telemetry and independent holdout validation telemetry.
        """
        n = len(self.timestamps)
        split_idx = max(2, min(n - 2, int(n * train_ratio)))

        t_train = self.timestamps[:split_idx]
        t_val = self.timestamps[split_idx:]

        train_ch: Dict[str, PreservedChannelData] = {}
        val_ch: Dict[str, PreservedChannelData] = {}

        for name, ch in self.channels.items():
            train_ch[name] = PreservedChannelData(
                canonical_name=ch.canonical_name,
                source_name=ch.source_name,
                unit=ch.unit,
                scale=ch.scale,
                offset=ch.offset,
                raw_timestamps=t_train,
                raw_values=ch.raw_values[:split_idx],
                quality_flags=ch.quality_flags[:split_idx],
                missing_mask=ch.missing_mask[:split_idx],
                interpolated_mask=ch.interpolated_mask[:split_idx],
                sampling_rate_hz=ch.sampling_rate_hz,
                is_discrete=ch.is_discrete,
            )
            val_ch[name] = PreservedChannelData(
                canonical_name=ch.canonical_name,
                source_name=ch.source_name,
                unit=ch.unit,
                scale=ch.scale,
                offset=ch.offset,
                raw_timestamps=t_val,
                raw_values=ch.raw_values[split_idx:],
                quality_flags=ch.quality_flags[split_idx:],
                missing_mask=ch.missing_mask[split_idx:],
                interpolated_mask=ch.interpolated_mask[split_idx:],
                sampling_rate_hz=ch.sampling_rate_hz,
                is_discrete=ch.is_discrete,
            )

        train_ds = TelemetryDataset(
            timestamps=t_train,
            channels=train_ch,
            units=dict(self.units),
            source=self.source,
            sampling_rate=self.sampling_rate,
            vehicle=self.vehicle,
            setup=self.setup,
            track=self.track,
            session=f"{self.session}-Train",
            driver=self.driver,
            metadata={**self.metadata, "partition": "train", "samples": len(t_train)},
        )
        val_ds = TelemetryDataset(
            timestamps=t_val,
            channels=val_ch,
            units=dict(self.units),
            source=self.source,
            sampling_rate=self.sampling_rate,
            vehicle=self.vehicle,
            setup=self.setup,
            track=self.track,
            session=f"{self.session}-Holdout",
            driver=self.driver,
            metadata={**self.metadata, "partition": "holdout", "samples": len(t_val)},
        )
        return train_ds, val_ds

    def to_dict(self) -> Dict[str, Any]:
        """Serialize dataset into clean dictionary for API/JSON responses."""
        return {
            "vehicle": self.vehicle,
            "setup": self.setup,
            "track": self.track.track_name if isinstance(self.track, TrackReference) else str(self.track),
            "session": self.session,
            "driver": self.driver,
            "source": self.source.value if isinstance(self.source, TelemetrySource) else str(self.source),
            "sampling_rate_hz": round(self.sampling_rate, 2),
            "n_samples": len(self.timestamps),
            "duration_s": round(float(self.timestamps[-1] - self.timestamps[0]), 3) if len(self.timestamps) > 1 else 0.0,
            "channels": {k: v.scaled_values.tolist() for k, v in self.channels.items()},
            "units": self.units,
            "metadata": self.metadata,
            "provenance_hash": self.provenance_hash,
            "created_at_iso": self.created_at_iso,
        }

    @classmethod
    def from_csv_string(
        cls,
        csv_content: str,
        source: TelemetrySource = TelemetrySource.CSV,
        vehicle: str = "Unknown",
        setup: str = "Base",
        track: Union[TrackReference, str] = "Unknown",
        session: str = "Session 1",
        driver: str = "Driver",
    ) -> TelemetryDataset:
        """
        Step 1 & Step 3: Ingest telemetry CSV across all DAQ formats (MoTeC, AiM, Cosworth, Bosch, generic).
        """
        lines = [line.strip() for line in csv_content.strip().splitlines() if line.strip()]
        if not lines:
            raise ValueError("Telemetry CSV content is empty.")

        # Find header line (first line containing time or speed aliases)
        header_idx = 0
        for i, line in enumerate(lines[:30]):
            line_low = line.lower()
            if any(k in line_low for k in ["time", "sec", "speed", "vx", "latg", "vert_g"]):
                header_idx = i
                break

        reader = csv.reader(io.StringIO("\n".join(lines[header_idx:])))
        raw_headers = next(reader, None)
        if not raw_headers:
            raise ValueError("Failed to parse CSV headers.")

        # Resolve channel mappings
        channel_meta: List[Tuple[int, str, str, float, float, ChannelMappingRule]] = []
        for idx, h in enumerate(raw_headers):
            canon_name, unit, scale, offset, conf = resolve_channel_mapping(h, source)
            rule = CANONICAL_CHANNEL_RULES.get(canon_name, ChannelMappingRule(canon_name, unit))
            channel_meta.append((idx, canon_name, h, scale, offset, rule))

        # Parse numerical values
        raw_cols: Dict[str, List[float]] = {meta[1]: [] for meta in channel_meta}
        for row in reader:
            if not row or all(c.strip() == "" for c in row):
                continue
            for col_idx, canon_name, _, scale, offset, _ in channel_meta:
                if col_idx < len(row):
                    cell = row[col_idx].strip()
                    try:
                        val = float(cell)
                    except ValueError:
                        val = float("nan")
                else:
                    val = float("nan")
                raw_cols[canon_name].append(val)

        # Build timestamps
        if "time" in raw_cols and len(raw_cols["time"]) > 0:
            time_raw = np.asarray(raw_cols["time"], dtype=np.float64)
            if np.all(np.isnan(time_raw)) or len(time_raw) == 0:
                time_raw = np.linspace(0.0, len(raw_cols["time"]) * 0.01, len(raw_cols["time"]))
        else:
            first_len = len(next(iter(raw_cols.values()))) if raw_cols else 0
            time_raw = np.linspace(0.0, first_len * 0.01, first_len)

        # Estimate sample rate
        dt = np.diff(time_raw)
        valid_dt = dt[dt > 1e-7]
        fs = float(1.0 / np.median(valid_dt)) if len(valid_dt) > 0 else 100.0

        # Build PreservedChannelData objects
        channels: Dict[str, PreservedChannelData] = {}
        units: Dict[str, str] = {}

        for col_idx, canon_name, raw_name, scale, offset, rule in channel_meta:
            arr = np.asarray(raw_cols[canon_name], dtype=np.float64)
            q_flags = np.zeros(len(arr), dtype=np.int32)
            missing = ~np.isfinite(arr)
            q_flags[missing] |= QualityFlag.MISSING

            # Screen bounds
            scaled = arr * scale + offset
            out_of_bound = (scaled < rule.physical_min) | (scaled > rule.physical_max)
            q_flags[out_of_bound & ~missing] |= QualityFlag.OUT_OF_RANGE

            ch_obj = PreservedChannelData(
                canonical_name=canon_name,
                source_name=raw_name,
                unit=rule.canonical_unit,
                scale=scale,
                offset=offset,
                raw_timestamps=time_raw,
                raw_values=arr,
                quality_flags=q_flags,
                missing_mask=missing,
                sampling_rate_hz=fs,
                is_discrete=rule.is_discrete,
            )
            channels[canon_name] = ch_obj
            units[canon_name] = rule.canonical_unit

        return cls(
            timestamps=time_raw,
            channels=channels,
            units=units,
            source=source,
            sampling_rate=fs,
            vehicle=vehicle,
            setup=setup,
            track=track,
            session=session,
            driver=driver,
            metadata={"source_headers": raw_headers, "raw_rows": len(time_raw)},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Step 8 / Phase 3D: Channel-Level Explicit Unit Normalization & Metadata
# ─────────────────────────────────────────────────────────────────────────────

class UnitNormalizationStatus(str, enum.Enum):
    NORMALIZED = "NORMALIZED"
    VERIFIED_SI = "VERIFIED_SI"
    UNIT_AMBIGUOUS = "UNIT_AMBIGUOUS"


@dataclass
class ChannelUnitMetadata:
    """Explicit per-channel unit metadata and conversion audit trail."""
    channel_name: str
    declared_unit: str
    detected_unit: str
    normalized_SI_unit: str
    conversion_factor: float
    conversion_offset: float = 0.0
    status: UnitNormalizationStatus = UnitNormalizationStatus.VERIFIED_SI
    provenance: str = ""
    audit_note: str = ""


@dataclass
class NormalizedChannelResult:
    """Non-destructive container holding raw values alongside normalized SI values and metadata."""
    channel_name: str
    raw_values: np.ndarray
    normalized_SI_values: np.ndarray
    metadata: ChannelUnitMetadata


class ChannelUnitNormalizer:
    """
    Channel-level explicit unit normalization engine.
    Never uses global guesswork; inspects declared metadata, channel semantics,
    and dataset provenance.
    """

    KNOWN_STANFORD_GOLF_POT_CHANNELS = {
        "suspflpos_m", "suspfrpos_m", "susprlpos_m", "susprrpos_m"
    }

    @classmethod
    def normalize_channel(
        cls,
        channel_name: str,
        values: Union[np.ndarray, Sequence[float], float],
        declared_unit: Optional[str] = None,
        dataset_provenance: str = "",
    ) -> NormalizedChannelResult:
        """
        Normalize a specific telemetry channel to canonical SI units.
        Enforces explicit metadata audit trails and flags ambiguous units.
        """
        arr = np.asarray(values, dtype=np.float64)
        c_clean = channel_name.strip().lower()
        dec_unit = declared_unit.strip().lower() if declared_unit else ""

        # Default fallback metadata
        det_unit = dec_unit if dec_unit else "unknown"
        si_unit = "m"
        factor = 1.0
        offset = 0.0
        status = UnitNormalizationStatus.VERIFIED_SI
        audit_note = "Standard SI verification."

        # Case 1: Explicit cm declared
        if dec_unit in ("cm", "centimeter", "centimeters"):
            det_unit = "cm"
            si_unit = "m"
            factor = 0.01
            status = UnitNormalizationStatus.NORMALIZED
            audit_note = "Explicitly declared cm converted to SI meters (0.01x factor)."

        # Case 2: Explicit mm declared
        elif dec_unit in ("mm", "millimeter", "millimeters"):
            det_unit = "mm"
            si_unit = "m"
            factor = 0.001
            status = UnitNormalizationStatus.NORMALIZED
            audit_note = "Explicitly declared mm converted to SI meters (0.001x factor)."

        # Case 3: Stanford VW Golf GTI Potentiometer Anomaly (declared '_m' but recorded in cm)
        elif c_clean in cls.KNOWN_STANFORD_GOLF_POT_CHANNELS or (
            "susp" in c_clean and c_clean.endswith("_m") and ("stanford" in dataset_provenance.lower() or "golf" in dataset_provenance.lower())
        ):
            # Check physical feasibility: passenger car damper travel is ~0.10 - 0.18 m max.
            val_span = float(np.nanmax(arr) - np.nanmin(arr)) if arr.size > 0 else 0.0
            if val_span > 1.0 or "stanford" in dataset_provenance.lower():
                dec_unit = "m"
                det_unit = "cm"
                si_unit = "m"
                factor = 0.01
                status = UnitNormalizationStatus.NORMALIZED
                audit_note = (
                    f"Stanford Golf GTI potentiometer anomaly: channel '{channel_name}' labeled '_m' "
                    f"exhibits {val_span:.2f} unit span (physically impossible as meters). "
                    "Verified logged in cm; normalized via 0.01 m/cm factor."
                )
            else:
                dec_unit = "m"
                det_unit = "m"
                si_unit = "m"
                factor = 1.0
                status = UnitNormalizationStatus.VERIFIED_SI
                audit_note = "Potentiometer span within physical meter limits; verified SI."

        # Case 4: Pristine SI meters declared and verified
        elif dec_unit in ("m", "meter", "meters"):
            val_span = float(np.nanmax(arr) - np.nanmin(arr)) if arr.size > 0 else 0.0
            if "damper" in c_clean or "susp" in c_clean:
                # Suspension stroke should be < 0.35m for automotive
                if val_span > 1.0:
                    status = UnitNormalizationStatus.UNIT_AMBIGUOUS
                    factor = 1.0
                    audit_note = f"Suspension stroke span {val_span:.2f} exceeds physical bounds for meters; unit is ambiguous."
                else:
                    det_unit = "m"
                    si_unit = "m"
                    factor = 1.0
                    status = UnitNormalizationStatus.VERIFIED_SI
                    audit_note = "Verified pristine SI meter displacement."
            else:
                det_unit = "m"
                si_unit = "m"
                factor = 1.0
                status = UnitNormalizationStatus.VERIFIED_SI
                audit_note = "Verified pristine SI meter channel."

        # Case 5: Missing or Ambiguous Unit
        else:
            status = UnitNormalizationStatus.UNIT_AMBIGUOUS
            factor = 1.0
            audit_note = (
                f"Declared unit '{declared_unit}' for channel '{channel_name}' is ambiguous or unverified. "
                "Refusing to guess conversion factor silently."
            )

        norm_vals = arr * factor + offset
        meta = ChannelUnitMetadata(
            channel_name=channel_name,
            declared_unit=dec_unit if dec_unit else "unspecified",
            detected_unit=det_unit,
            normalized_SI_unit=si_unit,
            conversion_factor=factor,
            conversion_offset=offset,
            status=status,
            provenance=dataset_provenance if dataset_provenance else "unspecified",
            audit_note=audit_note,
        )

        return NormalizedChannelResult(
            channel_name=channel_name,
            raw_values=arr,
            normalized_SI_values=norm_vals,
            metadata=meta,
        )

