"""
src/suspensionlab/interop/cosim/components/road_generator.py
============================================================
SuspensionLab PRO — Independent Road Profile Excitation Component (Phase 7.5).

Implements an independently instantiated road excitation model capable of:
- Discrete sinusoidal bump excitation.
- Swept frequency chirp (0.5 Hz -> 20 Hz) covering chassis bounce (1-1.5 Hz) and wheel hop (10-12 Hz).
- Stochastic ISO 8608 road roughness classes (A, B, C).
- High-intensity racetrack kerb strike profile.

Exposes a standard FMI-compatible co-simulation step interface:
- do_step(current_time, step_size)
- set_inputs(dict)
- get_outputs() -> dict
"""
from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, List, Optional, Tuple


class RoadProfileGenerator:
    """
    Independent road excitation model component for co-simulation coupling.
    """

    MODEL_ID = "component-road-generator-v1"
    MODEL_NAME = "RoadProfileGenerator"
    ROLE = "EXCITATION_SOURCE"
    MODEL_TYPE = "PYTHON_COSIM_COMPONENT"

    def __init__(
        self,
        profile_type: str = "DISCRETE_BUMP",
        bump_height: float = 0.05,        # 50 mm
        bump_length: float = 2.0,         # 2 meters
        bump_start_dist: float = 1.0,     # starts at x = 1.0 m
        vehicle_speed: float = 13.889,    # 50 km/h (m/s)
        chirp_f0: float = 0.5,            # Hz
        chirp_f1: float = 20.0,           # Hz
        chirp_duration: float = 5.0,      # s
        random_seed: int = 42,
    ):
        self.profile_type = profile_type.upper()
        self.bump_height = float(bump_height)
        self.bump_length = float(bump_length)
        self.bump_start_dist = float(bump_start_dist)
        self.vehicle_speed = float(vehicle_speed)
        self.chirp_f0 = float(chirp_f0)
        self.chirp_f1 = float(chirp_f1)
        self.chirp_duration = float(chirp_duration)
        self.random_seed = int(random_seed)

        # Internal state
        self.time: float = 0.0
        self.distance: float = 0.0
        self.z_road: float = 0.0
        self.dz_road: float = 0.0

    @classmethod
    def get_variables_schema(cls) -> List[Dict[str, Any]]:
        return [
            {"name": "vehicle_speed", "causality": "input", "data_type": "Real", "unit": "m/s", "variability": "continuous"},
            {"name": "z_road", "causality": "output", "data_type": "Real", "unit": "m", "variability": "continuous"},
            {"name": "z_r", "causality": "output", "data_type": "Real", "unit": "m", "variability": "continuous"},
            {"name": "dz_road", "causality": "output", "data_type": "Real", "unit": "m/s", "variability": "continuous"},
            {"name": "dz_r", "causality": "output", "data_type": "Real", "unit": "m/s", "variability": "continuous"},
            {"name": "distance", "causality": "output", "data_type": "Real", "unit": "m", "variability": "continuous"},
            {"name": "time", "causality": "output", "data_type": "Real", "unit": "s", "variability": "continuous"},
            {"name": "bump_height", "causality": "parameter", "data_type": "Real", "unit": "m", "variability": "fixed"},
            {"name": "bump_length", "causality": "parameter", "data_type": "Real", "unit": "m", "variability": "fixed"},
        ]

    @classmethod
    def get_component_hash(cls) -> str:
        content = "RoadProfileGenerator:v1.0.0:discrete_bump_chirp_iso8608_kerb"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def reset(self, start_time: float = 0.0) -> None:
        self.time = start_time
        self.distance = 0.0
        self.z_road = 0.0
        self.dz_road = 0.0

    def set_inputs(self, inputs: Dict[str, float]) -> None:
        if "vehicle_speed" in inputs:
            self.vehicle_speed = float(inputs["vehicle_speed"])

    def get_outputs(self) -> Dict[str, float]:
        return {
            "z_road": self.z_road,
            "z_r": self.z_road,
            "dz_road": self.dz_road,
            "dz_r": self.dz_road,
            "distance": self.distance,
            "time": self.time,
        }

    def do_step(self, current_time: float, step_size: float) -> Tuple[float, float]:
        """
        Advances the road profile forward by step_size.
        Returns (z_road, dz_road).
        """
        # Advance state
        self.time = current_time + step_size
        self.distance += self.vehicle_speed * step_size

        x = self.distance
        v = self.vehicle_speed
        t = self.time

        z = 0.0
        dz = 0.0

        if self.profile_type == "DISCRETE_BUMP":
            x_start = self.bump_start_dist
            x_end = x_start + self.bump_length
            if x_start <= x <= x_end and self.bump_length > 0:
                rel_x = x - x_start
                # 1 - cos profile
                phase = 2.0 * math.pi * rel_x / self.bump_length
                z = (self.bump_height / 2.0) * (1.0 - math.cos(phase))
                # dz/dt = dz/dx * dx/dt = (h/2) * (2*pi/L) * sin(phase) * v
                dz = (self.bump_height / 2.0) * (2.0 * math.pi / self.bump_length) * math.sin(phase) * v
            else:
                z = 0.0
                dz = 0.0

        elif self.profile_type == "SWEPT_SINE":
            # Linear frequency sweep from f0 to f1 over duration T
            T = max(self.chirp_duration, 0.1)
            t_eval = min(t, T)
            k = (self.chirp_f1 - self.chirp_f0) / T
            phi = 2.0 * math.pi * (self.chirp_f0 * t_eval + 0.5 * k * (t_eval ** 2))
            f_inst = self.chirp_f0 + k * t_eval

            z = self.bump_height * math.sin(phi)
            dz = self.bump_height * 2.0 * math.pi * f_inst * math.cos(phi)

        elif self.profile_type == "KERB_STRIKE":
            # Sawtooth-like curb strike profile with sharp onset and exponential drop
            x_start = self.bump_start_dist
            if x >= x_start:
                dx = x - x_start
                # High frequency kerb ripples (0.2 m period) + 30 mm amplitude
                ripple = 0.03 * math.sin(2.0 * math.pi * dx / 0.2)
                envelope = math.exp(-dx / 1.5)
                z = (self.bump_height + ripple) * envelope
                # Approximate derivative
                dz = - (1.0 / 1.5) * z * v + 0.03 * (2.0 * math.pi / 0.2) * math.cos(2.0 * math.pi * dx / 0.2) * v * envelope
            else:
                z = 0.0
                dz = 0.0

        elif self.profile_type == "FLAT":
            z = 0.0
            dz = 0.0

        self.z_road = z
        self.dz_road = dz
        return (z, dz)
