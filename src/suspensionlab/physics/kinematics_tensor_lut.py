"""
physics/kinematics_tensor_lut.py
================================
SuspensionLab PRO — Multidimensional Kinematics Tensor Lookup Table (LUT)

Implements full 4D (Heave x Roll x Steer x Pitch) suspension kinematics state space tensor:
    R[i, j, k, l, q]
where:
    i = heave index  [z_heave]
    j = roll index   [phi_roll]
    k = steer index  [delta_steer]
    l = pitch index  [theta_pitch]
    q = output channel index

Exposes high-speed multilinear interpolation with explicit out-of-domain boundary controls:
    result = lut.evaluate(heave_mm=12.5, roll_deg=2.2, steer_deg=4.5, pitch_deg=0.5, out_of_bounds="clamp")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from suspensionlab.physics.kinematics_facade import (
    KinematicsBackendFactory,
    _map_to_canonical_api_format,
    _normalize_to_mm,
)


CHANNEL_NAMES = [
    "camber_l_deg",
    "camber_r_deg",
    "toe_l_deg",
    "toe_r_deg",
    "caster_l_deg",
    "caster_r_deg",
    "kpi_l_deg",
    "kpi_r_deg",
    "roll_center_z_mm",
    "motion_ratio_l",
    "motion_ratio_r",
    "scrub_radius_l_mm",
    "scrub_radius_r_mm",
    "track_change_mm",
    "anti_dive_pct",
    "anti_squat_pct",
]


@dataclass
class KinematicsTensorLUT:
    """Multidimensional (Heave x Roll x Steer x Pitch) Suspension Kinematics Tensor LUT."""
    heave_grid_mm: np.ndarray       # 1D array of heave points [mm]
    roll_grid_deg: np.ndarray       # 1D array of roll points [deg]
    steer_grid_deg: np.ndarray      # 1D array of steer points [deg]
    pitch_grid_deg: np.ndarray      # 1D array of pitch points [deg]
    tensor_data: np.ndarray         # 5D array shape [N_heave, N_roll, N_steer, N_pitch, N_channels]
    channel_names: List[str] = field(default_factory=lambda: list(CHANNEL_NAMES))
    track_width_mm: float = 1600.0
    wheelbase_mm: float = 2600.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Construct RegularGridInterpolators for each output channel
        self._interpolators: Dict[str, RegularGridInterpolator] = {}
        for q, ch in enumerate(self.channel_names):
            grid_values = self.tensor_data[:, :, :, :, q]
            rgi = RegularGridInterpolator(
                (self.heave_grid_mm, self.roll_grid_deg, self.steer_grid_deg, self.pitch_grid_deg),
                grid_values,
                method="linear",
                bounds_error=False,
                fill_value=None,  # default linear extrapolation
            )
            self._interpolators[ch] = rgi

    def is_in_domain(self, heave_mm: float, roll_deg: float = 0.0, steer_deg: float = 0.0, pitch_deg: float = 0.0) -> bool:
        """Check if operating point lies strictly inside the generated LUT domain bounds."""
        in_h = self.heave_grid_mm[0] <= heave_mm <= self.heave_grid_mm[-1]
        in_r = self.roll_grid_deg[0] <= roll_deg <= self.roll_grid_deg[-1]
        in_s = self.steer_grid_deg[0] <= steer_deg <= self.steer_grid_deg[-1]
        in_p = self.pitch_grid_deg[0] <= pitch_deg <= self.pitch_grid_deg[-1]
        return bool(in_h and in_r and in_s and in_p)

    def evaluate(
        self,
        heave_mm: float,
        roll_deg: float = 0.0,
        steer_deg: float = 0.0,
        pitch_deg: float = 0.0,
        out_of_bounds: Literal["extrapolate", "clamp", "raise"] = "clamp",
    ) -> Dict[str, float]:
        """Evaluate full axle suspension kinematics at arbitrary (heave, roll, steer, pitch).

        Parameters
        ----------
        heave_mm : Ride height heave displacement [mm].
        roll_deg : Body roll angle [deg].
        steer_deg : Road wheel steer angle [deg].
        pitch_deg : Body pitch angle [deg].
        out_of_bounds : Policy when point is outside grid envelope ('clamp', 'extrapolate', 'raise').
        """
        in_domain = self.is_in_domain(heave_mm, roll_deg, steer_deg, pitch_deg)

        if not in_domain:
            if out_of_bounds == "raise":
                raise ValueError(
                    f"Operating point (heave={heave_mm}, roll={roll_deg}, steer={steer_deg}, pitch={pitch_deg}) "
                    f"is outside LUT domain [heave: {self.heave_grid_mm[0]}..{self.heave_grid_mm[-1]} mm, "
                    f"roll: {self.roll_grid_deg[0]}..{self.roll_grid_deg[-1]} deg]"
                )
            elif out_of_bounds == "clamp":
                heave_mm  = float(np.clip(heave_mm,  self.heave_grid_mm[0],  self.heave_grid_mm[-1]))
                roll_deg  = float(np.clip(roll_deg,  self.roll_grid_deg[0],  self.roll_grid_deg[-1]))
                steer_deg = float(np.clip(steer_deg, self.steer_grid_deg[0], self.steer_grid_deg[-1]))
                pitch_deg = float(np.clip(pitch_deg, self.pitch_grid_deg[0], self.pitch_grid_deg[-1]))

        pt = np.array([[heave_mm, roll_deg, steer_deg, pitch_deg]], dtype=np.float64)
        out: Dict[str, float] = {"in_domain": float(1.0 if in_domain else 0.0)}
        for ch, interp in self._interpolators.items():
            out[ch] = float(interp(pt)[0])
        return out

    def to_dict(self) -> Dict[str, Any]:
        """Convert tensor metadata and shape to serializable dictionary."""
        return {
            "heave_grid_mm": self.heave_grid_mm.tolist(),
            "roll_grid_deg": self.roll_grid_deg.tolist(),
            "steer_grid_deg": self.steer_grid_deg.tolist(),
            "pitch_grid_deg": self.pitch_grid_deg.tolist(),
            "tensor_shape": list(self.tensor_data.shape),
            "channels": self.channel_names,
            "track_width_mm": self.track_width_mm,
            "wheelbase_mm": self.wheelbase_mm,
            "metadata": self.metadata,
        }


def build_kinematics_tensor_lut(
    hardpoints: Dict[str, Any],
    heave_range_mm: Tuple[float, float] = (-60.0, 60.0),
    n_heave: int = 17,
    roll_range_deg: Tuple[float, float] = (-5.0, 5.0),
    n_roll: int = 11,
    steer_range_deg: Tuple[float, float] = (-15.0, 15.0),
    n_steer: int = 7,
    pitch_range_deg: Tuple[float, float] = (-2.0, 2.0),
    n_pitch: int = 3,
    track_width_mm: float = 1600.0,
    wheelbase_mm: float = 2600.0,
    topology: str = "double_wishbone",
    mode: str = "auto",
) -> KinematicsTensorLUT:
    """Generate a structured 4D Tensor LUT across (Heave x Roll x Steer x Pitch)."""
    heave_grid = np.linspace(heave_range_mm[0], heave_range_mm[1], n_heave, dtype=np.float64)
    roll_grid  = np.linspace(roll_range_deg[0], roll_range_deg[1], n_roll, dtype=np.float64)
    steer_grid = np.linspace(steer_range_deg[0], steer_range_deg[1], n_steer, dtype=np.float64)
    pitch_grid = np.linspace(pitch_range_deg[0], pitch_range_deg[1], n_pitch, dtype=np.float64)

    n_channels = len(CHANNEL_NAMES)
    tensor = np.zeros((n_heave, n_roll, n_steer, n_pitch, n_channels), dtype=np.float64)

    backend = KinematicsBackendFactory.create(mode=mode, topology=topology)
    half_track = 0.5 * track_width_mm
    half_wb    = 0.5 * wheelbase_mm

    for i, heave in enumerate(heave_grid):
        for j, roll in enumerate(roll_grid):
            roll_rad = np.radians(roll)
            for l_idx, pitch in enumerate(pitch_grid):
                pitch_rad = np.radians(pitch)
                
                # Left corner and right corner vertical displacements
                dz_left  = heave + half_track * np.sin(roll_rad) - half_wb * np.sin(pitch_rad)
                dz_right = heave - half_track * np.sin(roll_rad) - half_wb * np.sin(pitch_rad)

                for k, steer in enumerate(steer_grid):
                    # Solve left and right corners with steering
                    pt_left  = backend.solve_single(hardpoints, dz_left, roll_deg=roll, steer_deg=steer, pitch_deg=pitch)
                    pt_right = backend.solve_single(hardpoints, dz_right, roll_deg=-roll, steer_deg=steer, pitch_deg=pitch)

                    camber_l = pt_left.camber_deg
                    camber_r = pt_right.camber_deg
                    toe_l    = pt_left.toe_deg
                    toe_r    = pt_right.toe_deg
                    caster_l = pt_left.caster_deg
                    caster_r = pt_right.caster_deg
                    kpi_l    = pt_left.kpi_deg
                    kpi_r    = pt_right.kpi_deg

                    rc_z     = 0.5 * (pt_left.roll_center_height_mm + pt_right.roll_center_height_mm)
                    mr_l     = pt_left.motion_ratio
                    mr_r     = pt_right.motion_ratio
                    scrub_l  = pt_left.scrub_radius_mm
                    scrub_r  = pt_right.scrub_radius_mm
                    track_ch = pt_left.track_change_mm + pt_right.track_change_mm
                    anti_dive = 0.5 * (pt_left.anti_dive_pct + pt_right.anti_dive_pct)
                    anti_squat = 0.5 * (pt_left.anti_squat_pct + pt_right.anti_squat_pct)

                    tensor[i, j, k, l_idx, 0]  = camber_l
                    tensor[i, j, k, l_idx, 1]  = camber_r
                    tensor[i, j, k, l_idx, 2]  = toe_l
                    tensor[i, j, k, l_idx, 3]  = toe_r
                    tensor[i, j, k, l_idx, 4]  = caster_l
                    tensor[i, j, k, l_idx, 5]  = caster_r
                    tensor[i, j, k, l_idx, 6]  = kpi_l
                    tensor[i, j, k, l_idx, 7]  = kpi_r
                    tensor[i, j, k, l_idx, 8]  = rc_z
                    tensor[i, j, k, l_idx, 9]  = mr_l
                    tensor[i, j, k, l_idx, 10] = mr_r
                    tensor[i, j, k, l_idx, 11] = scrub_l
                    tensor[i, j, k, l_idx, 12] = scrub_r
                    tensor[i, j, k, l_idx, 13] = track_ch
                    tensor[i, j, k, l_idx, 14] = anti_dive
                    tensor[i, j, k, l_idx, 15] = anti_squat

    metadata = {
        "generator": "SuspensionLab Multidimensional Tensor Engine",
        "topology": topology,
        "grid_points": n_heave * n_roll * n_steer * n_pitch,
        "backend": backend.__class__.__name__,
    }

    return KinematicsTensorLUT(
        heave_grid_mm=heave_grid,
        roll_grid_deg=roll_grid,
        steer_grid_deg=steer_grid,
        pitch_grid_deg=pitch_grid,
        tensor_data=tensor,
        channel_names=list(CHANNEL_NAMES),
        track_width_mm=track_width_mm,
        wheelbase_mm=wheelbase_mm,
        metadata=metadata,
    )
