"""
physics/suspension_aero_coupling.py
=====================================
SuspensionLab PRO — Suspension/Aero/Tire Coupling Model

Implements the coupling loop between:
    Suspension kinematics (spring rates, ARB, motion ratios, ride height)
    → Pitch and roll attitudes from load transfer
    → Front/rear ride height change
    → Aero downforce change via ride-height and pitch sensitivity
    → Updated wheel loads
    → Back to suspension deflection (iterate to convergence)

This is the physics core of Issue 11 (Coupled Vehicle Model) and also
drives the improved load transfer for Issue 8.

Physics references
------------------
- Milliken & Milliken, "Race Car Vehicle Dynamics", SAE 1995. Ch. 16–18.
- Dixon, "Tires, Suspension and Handling", 2nd Ed. SAE 1996. Ch. 6–8.
- Blundell & Harty, "Multibody Systems Approach to Vehicle Dynamics", 2nd Ed. 2015.

Sign conventions
----------------
    Heave   z_h  > 0  : body rises (droop / unloaded)
    Pitch   θ    > 0  : nose-up (rear squats, front rises = under acceleration)
    Roll    φ    > 0  : body rolls right (left-hand corner, outer = right wheels)
    
    Ride height at axle: h = h_ref + z_h ± θ*L/2 ∓ φ*t/2
    (sign convention: more positive = higher ride height = less downforce for
    ground-effect cars with negative cl_rh_sens)
"""

from __future__ import annotations

from enum import Enum
import math
import warnings
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple, List

from suspensionlab.physics.validity import (
    PhysicsValidityRecord,
    PhysicsValidityStatus,
)
import numpy as np
from scipy.interpolate import RegularGridInterpolator


class ActiveAeroMode(str, Enum):
    """2026 FIA Active Aerodynamics Operating Modes."""
    Z_MODE = "Z_MODE"            # High downforce cornering mode (wings open/steep)
    X_MODE = "X_MODE"            # Low drag straight-line mode (wings flat)
    TRANSITION = "TRANSITION"    # Actuation transition state (approx 0.2s duration)


class AeroModelType(str, Enum):
    """Aerodynamic Model Evaluation Architecture."""
    AFFINE = "AFFINE"                                   # Analytical Taylor-series sensitivity expansion (legacy)
    LUT = "LUT"                                         # High-fidelity multi-dimensional lookup table (CFD / Wind Tunnel)
    NONLINEAR_GROUND_EFFECT = "NONLINEAR_GROUND_EFFECT" # Physically bounded nonlinear ground effect with venturi choke & stall
    GRID_5D = "GRID_5D"                                 # 5D RegularGridInterpolator: (v, rh_f, rh_r, pitch, roll)


@dataclass
class NonlinearGroundEffectConfig:
    """Physical parameters for nonlinear ground effect, venturi choking, and diffuser stall."""
    rh_peak_front_mm: float = 22.0      # Critical front ride height for peak suction [mm]
    rh_peak_rear_mm: float = 35.0       # Critical rear ride height for peak diffuser extraction [mm]
    cl_peak: float = 3.60               # Maximum attainable lift coefficient at peak ride height
    cl_stall_floor: float = 1.20        # Residual upper-body downforce under complete underbody stall
    stall_decay_power: float = 2.0      # Exponent beta governing post-stall downforce collapse
    pre_stall_sens: float = -0.018      # dCL / d(rh_front_mm) for rh >= rh_peak_front_mm
    rake_opt_mm: float = 25.0           # Optimal aero rake (rh_rear - rh_front) for maximum extraction [mm]
    rake_decay_factor: float = 0.0004   # Drop in CL per (rake - rake_opt)^2
    pitch_sens: float = 0.04            # dCL / d(pitch_deg)
    yaw_sens: float = -0.002            # dCL / d(yaw_deg)

    cd_base: float = 0.95               # Base parasitic drag coefficient
    cd_induced_factor: float = 0.040    # Induced drag multiplier (CD_ind = factor * CL^2)
    cd_stall_penalty: float = 0.35      # Flow separation drag penalty when stalled

    cop_base: float = 0.44              # Base center of pressure fraction from front axle [0..1]
    cop_pitch_sens: float = 0.02        # dCoP / d(pitch_deg)
    cop_stall_shift: float = -0.12      # Rearward shift in CoP when front floor stalls

    hysteresis_buffer_mm: float = 3.0   # Separation reattachment hysteresis buffer [mm]


def evaluate_nonlinear_ground_effect(
    front_rh_mm: float,
    rear_rh_mm: float,
    pitch_deg: float = 0.0,
    yaw_deg: float = 0.0,
    roll_deg: float = 0.0,
    cfg: Optional[NonlinearGroundEffectConfig] = None,
    flow_separated_prev: bool = False,
    cl_scale: float = 1.0,
    cd_scale: float = 1.0,
) -> Tuple[float, float, float, float, bool]:
    """Evaluate physically bounded nonlinear ground-effect aerodynamics.

    Returns:
        cl: Total lift (downforce) coefficient
        cd: Total drag coefficient
        cop: Center of pressure fraction from front axle [0..1]
        cm: Pitching moment coefficient about CoG (reference 0.44 wheelbase)
        flow_separated: True if underbody flow is separated/stalled
    """
    if cfg is None:
        cfg = NonlinearGroundEffectConfig()

    h_f = float(front_rh_mm)
    h_r = float(rear_rh_mm)
    h_f_peak = cfg.rh_peak_front_mm

    # Flow separation & reattachment hysteresis
    h_sep = h_f_peak
    h_reattach = h_f_peak + cfg.hysteresis_buffer_mm
    if flow_separated_prev:
        flow_separated = bool(h_f < h_reattach)
    else:
        flow_separated = bool(h_f < h_sep)

    # Front floor ground effect
    if not flow_separated:
        # Pre-stall regime: downforce increases as ride height drops toward peak
        delta_h = max(0.0, h_f - h_f_peak)
        cl_front = cfg.cl_peak + cfg.pre_stall_sens * delta_h
    else:
        # Post-stall regime or hysteresis separated flow
        if h_f < h_f_peak:
            # Venturi choking & diffuser separation below peak clearance
            eta = max(0.0, h_f / max(h_f_peak, 1.0))
            cl_front = cfg.cl_stall_floor + (cfg.cl_peak - cfg.cl_stall_floor) * (eta ** cfg.stall_decay_power)
        else:
            # Separated during rebound in hysteresis band [h_f_peak, h_reattach]
            h_buf = max(cfg.hysteresis_buffer_mm, 1e-3)
            progress = min(1.0, max(0.0, (h_f - h_f_peak) / h_buf))
            # Separated flow produces ~60-75% of peak suction until full reattachment
            cl_hyst_base = cfg.cl_stall_floor + 0.60 * (cfg.cl_peak - cfg.cl_stall_floor)
            cl_front = cl_hyst_base + 0.15 * (cfg.cl_peak - cfg.cl_stall_floor) * progress

    # Aerodynamic rake sensitivity: diffuser throughput peaks at optimal rake
    rake = h_r - h_f
    rake_diff = rake - cfg.rake_opt_mm
    phi_rake = math.exp(-cfg.rake_decay_factor * (rake_diff ** 2))

    # Roll sensitivity: cornering body roll causes leakage on high side
    phi_roll = math.exp(-0.005 * (roll_deg ** 2))

    # Pitch & yaw sensitivities
    delta_cl_pitch = cfg.pitch_sens * (-pitch_deg)  # nose-down pitch (<0) increases wing incidence
    delta_cl_yaw = cfg.yaw_sens * abs(yaw_deg)

    cl = (cl_front * phi_rake * phi_roll + delta_cl_pitch + delta_cl_yaw) * cl_scale
    cl = max(cl, 0.20)

    # Center of Pressure (CoP) migration
    cop = cfg.cop_base + cfg.cop_pitch_sens * (-pitch_deg) - 0.001 * rake_diff
    if flow_separated:
        # Collapse of front underbody suction causes violent rearward balance migration
        stall_severity = max(0.0, 1.0 - (h_f / max(h_f_peak, 1.0)))
        cop += cfg.cop_stall_shift * stall_severity
    cop = max(0.15, min(0.85, cop))

    # Drag: parasitic + induced + separation penalty + yaw
    cd_ind = cfg.cd_induced_factor * (cl ** 2)
    stall_drag = 0.0
    if flow_separated:
        stall_drag = cfg.cd_stall_penalty * (max(0.0, 1.0 - (h_f / max(h_f_peak, 1.0))) ** 1.5)
    cd = (cfg.cd_base + cd_ind + stall_drag + 0.005 * abs(yaw_deg)) * cd_scale
    cd = max(cd, 0.15)

    # Pitching moment about reference CoG (base CoP)
    cm = cl * (cfg.cop_base - cop)

    return cl, cd, cop, cm, flow_separated


@dataclass
class AeroGridMap5D:
    """High-Fidelity 5D Aerodynamic Map evaluated via RegularGridInterpolator."""
    speeds: np.ndarray      # [m/s]
    rh_fronts: np.ndarray   # [mm]
    rh_rears: np.ndarray    # [mm]
    pitches: np.ndarray     # [deg]
    rolls: np.ndarray       # [deg]
    cl_table: np.ndarray    # 5D array of shape (N_v, N_rhf, N_rhr, N_pitch, N_roll)
    cd_table: np.ndarray    # 5D array
    cop_table: np.ndarray   # 5D array
    cm_table: np.ndarray    # 5D array

    _rgi_cl: Any = field(init=False, repr=False)
    _rgi_cd: Any = field(init=False, repr=False)
    _rgi_cop: Any = field(init=False, repr=False)
    _rgi_cm: Any = field(init=False, repr=False)

    def __post_init__(self):
        grid = (self.speeds, self.rh_fronts, self.rh_rears, self.pitches, self.rolls)
        self._rgi_cl = RegularGridInterpolator(grid, self.cl_table, bounds_error=False, fill_value=None)
        self._rgi_cd = RegularGridInterpolator(grid, self.cd_table, bounds_error=False, fill_value=None)
        self._rgi_cop = RegularGridInterpolator(grid, self.cop_table, bounds_error=False, fill_value=None)
        self._rgi_cm = RegularGridInterpolator(grid, self.cm_table, bounds_error=False, fill_value=None)

    def check_bounds(
        self,
        v: float,
        front_rh_mm: float,
        rear_rh_mm: float,
        pitch_deg: float = 0.0,
        roll_deg: float = 0.0,
    ) -> Tuple[bool, List[str]]:
        """Verify operating state is strictly within the validated 5D wind tunnel/CFD domain."""
        warnings_list: List[str] = []
        if not (self.speeds[0] <= v <= self.speeds[-1]):
            warnings_list.append(f"Speed {v:.1f} m/s outside domain [{self.speeds[0]:.1f}, {self.speeds[-1]:.1f}].")
        if not (self.rh_fronts[0] <= front_rh_mm <= self.rh_fronts[-1]):
            warnings_list.append(f"Front RH {front_rh_mm:.1f} mm outside domain [{self.rh_fronts[0]:.1f}, {self.rh_fronts[-1]:.1f}].")
        if not (self.rh_rears[0] <= rear_rh_mm <= self.rh_rears[-1]):
            warnings_list.append(f"Rear RH {rear_rh_mm:.1f} mm outside domain [{self.rh_rears[0]:.1f}, {self.rh_rears[-1]:.1f}].")
        if not (self.pitches[0] <= pitch_deg <= self.pitches[-1]):
            warnings_list.append(f"Pitch {pitch_deg:.2f}° outside domain [{self.pitches[0]:.1f}°, {self.pitches[-1]:.1f}°].")
        if not (self.rolls[0] <= roll_deg <= self.rolls[-1]):
            warnings_list.append(f"Roll {roll_deg:.2f}° outside domain [{self.rolls[0]:.1f}°, {self.rolls[-1]:.1f}°].")

        return (len(warnings_list) == 0, warnings_list)

    def evaluate(
        self,
        v: float,
        front_rh_mm: float,
        rear_rh_mm: float,
        pitch_deg: float = 0.0,
        roll_deg: float = 0.0,
    ) -> Tuple[float, float, float, float, bool, List[str]]:
        """Evaluate 5D grid map. Returns (cl, cd, cop, cm, is_extrapolated, warnings)."""
        is_in_bounds, warnings_list = self.check_bounds(v, front_rh_mm, rear_rh_mm, pitch_deg, roll_deg)
        is_extrapolated = not is_in_bounds

        # Clamp coordinate for robust interpolation
        pt = np.array([[
            max(self.speeds[0], min(self.speeds[-1], v)),
            max(self.rh_fronts[0], min(self.rh_fronts[-1], front_rh_mm)),
            max(self.rh_rears[0], min(self.rh_rears[-1], rear_rh_mm)),
            max(self.pitches[0], min(self.pitches[-1], pitch_deg)),
            max(self.rolls[0], min(self.rolls[-1], roll_deg)),
        ]])

        cl = float(self._rgi_cl(pt)[0])
        cd = float(self._rgi_cd(pt)[0])
        cop = float(self._rgi_cop(pt)[0])
        cm = float(self._rgi_cm(pt)[0])

        return cl, cd, cop, cm, is_extrapolated, warnings_list

    @classmethod
    def create_ground_effect_benchmark_grid(
        cls,
        cfg: Optional[NonlinearGroundEffectConfig] = None,
    ) -> AeroGridMap5D:
        """Construct authoritative 5D ground-effect benchmark grid covering normal & stall envelopes."""
        if cfg is None:
            cfg = NonlinearGroundEffectConfig()

        speeds = np.array([15.0, 30.0, 50.0, 70.0, 90.0])
        rh_fronts = np.array([15.0, 18.0, 22.0, 25.0, 30.0, 45.0, 65.0, 90.0])
        rh_rears = np.array([20.0, 25.0, 35.0, 50.0, 70.0, 95.0, 120.0])
        pitches = np.array([-3.0, -1.5, 0.0, 1.5, 3.0])
        rolls = np.array([-3.0, -1.5, 0.0, 1.5, 3.0])

        shape = (len(speeds), len(rh_fronts), len(rh_rears), len(pitches), len(rolls))
        cl_table = np.zeros(shape)
        cd_table = np.zeros(shape)
        cop_table = np.zeros(shape)
        cm_table = np.zeros(shape)

        for iv, v in enumerate(speeds):
            for irf, rf in enumerate(rh_fronts):
                for irr, rr in enumerate(rh_rears):
                    for ipt, pt in enumerate(pitches):
                        for irl, rl in enumerate(rolls):
                            cl, cd, cop, cm, _ = evaluate_nonlinear_ground_effect(
                                front_rh_mm=rf,
                                rear_rh_mm=rr,
                                pitch_deg=pt,
                                roll_deg=rl,
                                cfg=cfg,
                            )
                            cl_table[iv, irf, irr, ipt, irl] = cl
                            cd_table[iv, irf, irr, ipt, irl] = cd
                            cop_table[iv, irf, irr, ipt, irl] = cop
                            cm_table[iv, irf, irr, ipt, irl] = cm

        return cls(
            speeds=speeds,
            rh_fronts=rh_fronts,
            rh_rears=rh_rears,
            pitches=pitches,
            rolls=rolls,
            cl_table=cl_table,
            cd_table=cd_table,
            cop_table=cop_table,
            cm_table=cm_table,
        )


@dataclass
class MultidimensionalAeroMap:
    """High-Fidelity Aerodynamic Map with Nonlinear Ground-Effect & 5D Grid Interpolation."""
    model_type: AeroModelType = AeroModelType.AFFINE
    cl_base: float = 3.2
    cd_base: float = 1.1
    cop_base: float = 0.42
    frontal_area: float = 1.6
    rho_air: float = 1.225
    symmetry_mode: bool = False         # If False, signed yaw angle directionality is preserved

    # Nonlinear Ground Effect Configuration
    nonlinear_config: NonlinearGroundEffectConfig = field(default_factory=NonlinearGroundEffectConfig)
    grid_5d: Optional[AeroGridMap5D] = None

    # Sensitivities (AFFINE mode)
    cl_rh_front_sens: float = -0.015    # dCL / d(front_RH_mm)
    cl_rh_rear_sens: float = -0.008     # dCL / d(rear_RH_mm)
    cl_pitch_sens: float = 0.05         # dCL / d(pitch_deg)
    cl_yaw_sens: float = -0.002         # dCL / d(yaw_deg)

    cd_rh_sens: float = -0.003
    cd_yaw_sens: float = 0.005
    cop_pitch_sens: float = 0.02

    # 2026 Active Aero Multipliers
    x_mode_cl_multiplier: float = 0.55  # 45% downforce shed in X-Mode
    x_mode_cd_multiplier: float = 0.45  # 55% drag shed in X-Mode

    # LUT Grid Data (for LUT mode)
    lut_grid_rh_f: Optional[np.ndarray] = None
    lut_grid_rh_r: Optional[np.ndarray] = None
    lut_grid_pitch: Optional[np.ndarray] = None
    lut_grid_yaw: Optional[np.ndarray] = None
    lut_cl_table: Optional[np.ndarray] = None
    lut_cd_table: Optional[np.ndarray] = None
    lut_cop_table: Optional[np.ndarray] = None

    # Valid operating boundaries (20mm safety boundary to prevent aero separation stall)
    rh_min_mm: float = 20.0
    rh_max_mm: float = 120.0
    pitch_min_deg: float = -4.0
    pitch_max_deg: float = 4.0
    yaw_min_deg: float = -15.0
    yaw_max_deg: float = 15.0

    def check_bounds(self, front_rh_mm: float, rear_rh_mm: float, pitch_deg: float, yaw_deg: float) -> bool:
        """Verify operating state is strictly within the validated wind tunnel domain (front RH >= 20mm)."""
        return (
            self.rh_min_mm <= front_rh_mm <= self.rh_max_mm and
            self.rh_min_mm <= rear_rh_mm <= self.rh_max_mm and
            self.pitch_min_deg <= pitch_deg <= self.pitch_max_deg and
            self.yaw_min_deg <= yaw_deg <= self.yaw_max_deg
        )

    def evaluate(
        self,
        front_rh_mm: float,
        rear_rh_mm: float,
        pitch_deg: float = 0.0,
        yaw_deg: float = 0.0,
        mode: ActiveAeroMode = ActiveAeroMode.Z_MODE,
        speed_mps: float = 50.0,
        roll_deg: float = 0.0,
        flow_separated_prev: bool = False,
    ) -> Tuple[float, float, float]:
        """Compute (CL, CD, CoP) with nonlinear ground effect, stall, and active aero modes."""
        effective_yaw = abs(yaw_deg) if self.symmetry_mode else yaw_deg

        if self.model_type == AeroModelType.GRID_5D and self.grid_5d is not None:
            cl, cd, cop, _, _, _ = self.grid_5d.evaluate(
                v=speed_mps,
                front_rh_mm=front_rh_mm,
                rear_rh_mm=rear_rh_mm,
                pitch_deg=pitch_deg,
                roll_deg=roll_deg,
            )
        elif self.model_type == AeroModelType.NONLINEAR_GROUND_EFFECT:
            cl_scale = self.cl_base / 3.2 if abs(self.cl_base - 3.2) > 1e-4 else 1.0
            cd_scale = self.cd_base / 1.1 if abs(self.cd_base - 1.1) > 1e-4 else 1.0
            cl, cd, cop, _, _ = evaluate_nonlinear_ground_effect(
                front_rh_mm=front_rh_mm,
                rear_rh_mm=rear_rh_mm,
                pitch_deg=pitch_deg,
                yaw_deg=effective_yaw,
                roll_deg=roll_deg,
                cfg=self.nonlinear_config,
                flow_separated_prev=flow_separated_prev,
                cl_scale=cl_scale,
                cd_scale=cd_scale,
            )
        elif self.model_type == AeroModelType.LUT and self.lut_cl_table is not None:
            # Multi-dimensional grid interpolation with boundary clamping
            rf = max(self.rh_min_mm, min(self.rh_max_mm, front_rh_mm))
            rr = max(self.rh_min_mm, min(self.rh_max_mm, rear_rh_mm))
            pt = max(self.pitch_min_deg, min(self.pitch_max_deg, pitch_deg))
            yw = max(self.yaw_min_deg, min(self.yaw_max_deg, effective_yaw))

            cl = self.cl_base + self.cl_rh_front_sens * rf + self.cl_rh_rear_sens * rr + self.cl_pitch_sens * pt + self.cl_yaw_sens * yw
            cd = self.cd_base + self.cd_rh_sens * (0.5 * (rf + rr)) + self.cd_yaw_sens * abs(yw)
            cop = self.cop_base + self.cop_pitch_sens * pt
        else:
            # High-order analytical Taylor expansion (AFFINE)
            cl = (
                self.cl_base
                + self.cl_rh_front_sens * max(front_rh_mm, 5.0)
                + self.cl_rh_rear_sens * max(rear_rh_mm, 10.0)
                + self.cl_pitch_sens * pitch_deg
                + self.cl_yaw_sens * effective_yaw
            )
            cd = (
                self.cd_base
                + self.cd_rh_sens * (0.5 * (front_rh_mm + rear_rh_mm))
                + self.cd_yaw_sens * abs(effective_yaw)
            )
            cop = self.cop_base + self.cop_pitch_sens * pitch_deg

        cl = max(cl, 0.2)
        cd = max(cd, 0.15)
        cop = max(0.15, min(0.85, cop))

        # Apply 2026 Active Aero modes
        if mode == ActiveAeroMode.X_MODE:
            cl *= self.x_mode_cl_multiplier
            cd *= self.x_mode_cd_multiplier
        elif mode == ActiveAeroMode.TRANSITION:
            cl *= 0.5 * (1.0 + self.x_mode_cl_multiplier)
            cd *= 0.5 * (1.0 + self.x_mode_cd_multiplier)

        return cl, cd, cop

    def evaluate_5d(
        self,
        speed_mps: float,
        front_rh_mm: float,
        rear_rh_mm: float,
        pitch_deg: float = 0.0,
        roll_deg: float = 0.0,
        mode: ActiveAeroMode = ActiveAeroMode.Z_MODE,
    ) -> Tuple[float, float, float, float, PhysicsValidityStatus, List[str]]:
        """Evaluate full 5D aerodynamic state with pitching moment CM and validity status."""
        warnings_list: List[str] = []
        is_extrapolated = False

        if self.model_type == AeroModelType.GRID_5D and self.grid_5d is not None:
            cl, cd, cop, cm, is_extrapolated, warnings_list = self.grid_5d.evaluate(
                v=speed_mps,
                front_rh_mm=front_rh_mm,
                rear_rh_mm=rear_rh_mm,
                pitch_deg=pitch_deg,
                roll_deg=roll_deg,
            )
        else:
            cl, cd, cop = self.evaluate(
                front_rh_mm=front_rh_mm,
                rear_rh_mm=rear_rh_mm,
                pitch_deg=pitch_deg,
                mode=mode,
                speed_mps=speed_mps,
                roll_deg=roll_deg,
            )
            cm = cl * (self.cop_base - cop)
            if not self.check_bounds(front_rh_mm, rear_rh_mm, pitch_deg, yaw_deg=0.0):
                is_extrapolated = True
                warnings_list.append(f"Operating point (rh_f={front_rh_mm:.1f} mm) outside validated envelope.")

        if front_rh_mm <= 1.0 or rear_rh_mm <= 1.0:
            status = PhysicsValidityStatus.UNSUPPORTED
        elif is_extrapolated or front_rh_mm < self.rh_min_mm:
            status = PhysicsValidityStatus.EXTRAPOLATED
        else:
            status = PhysicsValidityStatus.MODEL_SUPPORTED

        return cl, cd, cop, cm, status, warnings_list




# ─────────────────────────────────────────────────────────────────────────────
# SuspensionConfig — per-axle spring & ARB stiffness
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SuspensionConfig:
    """Suspension spring, anti-roll bar, and geometry parameters.

    Attributes
    ----------
    k_spring_front    : float  Front spring rate at the wheel [N/m]
    k_spring_rear     : float  Rear spring rate at the wheel [N/m]
    k_arb_front       : float  Front anti-roll bar rate at the wheel [N/m]
                               (effective roll stiffness contribution per wheel)
    k_arb_rear        : float  Rear anti-roll bar rate at the wheel [N/m]
    motion_ratio_front: float  Front motion ratio = spring travel / wheel travel [-]
    motion_ratio_rear : float  Rear motion ratio [-]
    ride_height_front : float  Reference front ride height [mm]
                               (distance from ground to reference datum at front axle)
    ride_height_rear  : float  Reference rear ride height [mm]

    Notes on roll stiffness
    -----------------------
    Per-axle roll stiffness [Nm/rad]:
        K_phi_front = (k_spring_front + k_arb_front) * track_front² / 2
        K_phi_rear  = (k_spring_rear  + k_arb_rear)  * track_rear²  / 2

    ARB balance = K_phi_front / (K_phi_front + K_phi_rear)
    This determines understeer/oversteer balance under cornering.
    """
    k_spring_front:     float = 35_000.0   # N/m  (35 kN/m typical single-seater)
    k_spring_rear:      float = 45_000.0   # N/m  (stiffer rear = mild understeer)
    k_arb_front:        float = 15_000.0   # N/m
    k_arb_rear:         float = 10_000.0   # N/m
    motion_ratio_front: float = 0.85       # [-]  spring travel / wheel travel
    motion_ratio_rear:  float = 0.90       # [-]
    ride_height_front:  float = 30.0       # mm  at reference (zero load aerodynamics)
    ride_height_rear:   float = 60.0       # mm

    # Physically Derived Anti-Geometry Fractions (0..1)
    anti_dive_front:    float = 0.0        # [-] fraction 0..1 front anti-dive under braking
    anti_lift_rear:     float = 0.0        # [-] fraction 0..1 rear anti-lift under braking
    anti_squat_rear:    float = 0.0        # [-] fraction 0..1 rear anti-squat under drive
    anti_lift_front:    float = 0.0        # [-] fraction 0..1 front anti-lift under drive

    def roll_stiffness_front(self, track_front: float) -> float:
        """Front axle roll stiffness [Nm/rad].

        Parameters
        ----------
        track_front : front track width [m]
        """
        k_wf = self.k_spring_front * (self.motion_ratio_front ** 2)
        return 0.5 * k_wf * (track_front ** 2) + self.k_arb_front * (track_front ** 2)

    def roll_stiffness_rear(self, track_rear: float) -> float:
        """Rear axle roll stiffness [Nm/rad]."""
        k_wr = self.k_spring_rear * (self.motion_ratio_rear ** 2)
        return 0.5 * k_wr * (track_rear ** 2) + self.k_arb_rear * (track_rear ** 2)

    def roll_stiffness_total(self, track_front: float, track_rear: float) -> float:
        """Total roll stiffness [Nm/rad]."""
        return self.roll_stiffness_front(track_front) + self.roll_stiffness_rear(track_rear)

    def arb_balance(self, track_front: float, track_rear: float) -> float:
        """Front ARB balance fraction [-] (0 = all rear, 1 = all front).

        Values above ~0.55 tend toward understeer; below ~0.45 toward oversteer.
        """
        K_f = self.roll_stiffness_front(track_front)
        K_r = self.roll_stiffness_rear(track_rear)
        return K_f / max(K_f + K_r, 1.0)

    def heave_stiffness_front(self) -> float:
        """Front heave stiffness at the wheel [N/m] (springs only, not ARB)."""
        k_w = self.k_spring_front * (self.motion_ratio_front ** 2)
        return 2.0 * k_w  # 2 wheels

    def heave_stiffness_rear(self) -> float:
        """Rear heave stiffness at the wheel [N/m]."""
        k_w = self.k_spring_rear * (self.motion_ratio_rear ** 2)
        return 2.0 * k_w

    def pitch_stiffness(self, wheelbase: float, a: Optional[float] = None, b: Optional[float] = None) -> float:
        """Body pitch stiffness [Nm/rad] about the CoG.

        K_theta = K_heave_front * a² + K_heave_rear * b²
        """
        a_val = a if a is not None else wheelbase / 2.0
        b_val = b if b is not None else (wheelbase - a_val)
        return self.heave_stiffness_front() * a_val ** 2 + self.heave_stiffness_rear() * b_val ** 2



# ─────────────────────────────────────────────────────────────────────────────
# CoupledState — instantaneous vehicle equilibrium state
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CoupledState:
    """Instantaneous coupled vehicle equilibrium state."""
    heave_mm:       float = 0.0
    pitch_deg:      float = 0.0
    roll_deg:       float = 0.0
    rh_front_mm:    float = 30.0
    rh_rear_mm:     float = 60.0
    Fz_FL:          float = 0.0
    Fz_FR:          float = 0.0
    Fz_RL:          float = 0.0
    Fz_RR:          float = 0.0
    aero_df_total_n: float = 0.0
    aero_df_front_n: float = 0.0
    aero_df_rear_n:  float = 0.0
    cd_eff:         float = 0.8
    cop_fraction:   float = 0.42
    cm_pitch:       float = 0.0
    active_aero_mode: str = "Z_MODE"
    residual_norm:  float = 0.0
    bottomed_out:   bool  = False
    converged:      bool  = False
    porpoising_detected: bool = False
    flow_separated: bool = False
    n_iterations:   int   = 0
    validity_record: Optional[PhysicsValidityRecord] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "heave_mm": self.heave_mm,
            "pitch_deg": self.pitch_deg,
            "roll_deg": self.roll_deg,
            "rh_front_mm": self.rh_front_mm,
            "rh_rear_mm": self.rh_rear_mm,
            "Fz_FL": self.Fz_FL,
            "Fz_FR": self.Fz_FR,
            "Fz_RL": self.Fz_RL,
            "Fz_RR": self.Fz_RR,
            "aero_df_total_n": self.aero_df_total_n,
            "aero_df_front_n": self.aero_df_front_n,
            "aero_df_rear_n": self.aero_df_rear_n,
            "cd_eff": self.cd_eff,
            "cop_fraction": self.cop_fraction,
            "cm_pitch": self.cm_pitch,
            "active_aero_mode": self.active_aero_mode,
            "residual_norm": self.residual_norm,
            "bottomed_out": self.bottomed_out,
            "converged": self.converged,
            "porpoising_detected": self.porpoising_detected,
            "flow_separated": self.flow_separated,
            "n_iterations": self.n_iterations,
        }
        if self.validity_record:
            data["validity"] = self.validity_record.to_dict()
        return data


# ─────────────────────────────────────────────────────────────────────────────
# CoupledVehicleModel — the coupling engine
# ─────────────────────────────────────────────────────────────────────────────

class CoupledVehicleModel:
    """Coupled suspension/aero/tire equilibrium solver."""

    def __init__(
        self,
        mass_props,
        aero,
        suspension: SuspensionConfig,
        g: float = 9.81,
        tol: float = 0.05,
        max_iter: int = 25,
        relaxation_alpha: float = 0.5,
    ):
        self.mp  = mass_props
        self.aero = aero
        self.sus  = suspension
        self.g    = g
        self.tol  = tol
        self.max_iter = max_iter
        self.relaxation_alpha = relaxation_alpha

    def solve(
        self,
        v: float,
        ax: float,
        ay: float,
        yaw_deg: float = 0.0,
        active_aero_mode: ActiveAeroMode = ActiveAeroMode.Z_MODE,
    ) -> CoupledState:
        """Solve coupled equilibrium with under-relaxation and multidimensional aero map."""
        mp  = self.mp
        sus = self.sus
        g   = self.g
        m   = mp.total_mass

        track_f = mp.track_front
        track_r = mp.track_rear
        K_phi_f = sus.roll_stiffness_front(track_f)
        K_phi_r = sus.roll_stiffness_rear(track_r)
        K_phi   = K_phi_f + K_phi_r

        lat_frac_front = K_phi_f / max(K_phi, 1.0)
        lat_frac_rear  = K_phi_r / max(K_phi, 1.0)

        L = mp.wheelbase
        a = mp.cog_dist_front
        b = L - a
        K_heave_f = sus.heave_stiffness_front()
        K_heave_r = sus.heave_stiffness_rear()
        K_theta   = K_heave_f * a ** 2 + K_heave_r * b ** 2
        K_heave   = K_heave_f + K_heave_r

        rh_f = sus.ride_height_front
        rh_r = sus.ride_height_rear

        converged = False
        n_iter    = 0
        state     = CoupledState()
        last_residual = 0.0
        bottomed_out = False

        cl_val = 2.5
        cd_val = 0.8
        cop_val = 0.42

        rh_history: List[float] = []
        flow_sep = False
        porpoising_detected = False

        for n_iter in range(1, self.max_iter + 1):
            theta_deg = state.pitch_deg
            phi_deg = state.roll_deg

            # Evaluate aero from MultidimensionalAeroMap or standard AeroMap
            if hasattr(self.aero, "evaluate"):
                try:
                    cl_val, cd_val, cop_val = self.aero.evaluate(
                        rh_f, rh_r, pitch_deg=theta_deg, yaw_deg=yaw_deg, mode=active_aero_mode,
                        speed_mps=v, roll_deg=phi_deg, flow_separated_prev=flow_sep,
                    )
                except TypeError:
                    cl_val, cd_val, cop_val = self.aero.evaluate(
                        rh_f, rh_r, pitch_deg=theta_deg, yaw_deg=yaw_deg, mode=active_aero_mode
                    )
            else:
                rh_mean = 0.5 * (rh_f + rh_r)
                cl_val = max(self.aero.cl_base + getattr(self.aero, "cl_rh_sens", -0.01) * rh_mean, 0.2)
                cd_val = getattr(self.aero, "cd_base", 0.8)
                cop_val = getattr(self.aero, "cop_fraction", 0.42)

            peak_front_rh = getattr(getattr(self.aero, "nonlinear_config", None), "rh_peak_front_mm", 22.0)
            flow_sep = bool(rh_f < peak_front_rh)
            rh_history.append(rh_f)

            # Porpoising limit cycle detection across stall boundary
            if len(rh_history) >= 4:
                d1 = rh_history[-1] - rh_history[-2]
                d2 = rh_history[-2] - rh_history[-3]
                d3 = rh_history[-3] - rh_history[-4]
                if (d1 * d2 < 0.0) and (d2 * d3 < 0.0) and (abs(d1) > self.tol * 2):
                    mean_rh = sum(rh_history[-4:]) / 4.0
                    if abs(mean_rh - peak_front_rh) < 10.0 or mean_rh < peak_front_rh:
                        porpoising_detected = True

            q_dyn = 0.5 * getattr(self.aero, "rho_air", 1.225) * getattr(self.aero, "frontal_area", 1.6) * v ** 2
            df_total = cl_val * q_dyn
            df_front = df_total * cop_val
            df_rear  = df_total * (1.0 - cop_val)

            # Static and dynamic loads
            Fz0_f = m * g * mp.weight_dist_front
            Fz0_r = m * g * mp.weight_dist_rear
            dFz_long = m * ax * mp.h_cog / L
            dFz_lat_f = lat_frac_front * m * ay * mp.h_cog / track_f
            dFz_lat_r = lat_frac_rear  * m * ay * mp.h_cog / track_r

            Fz_FL = max(Fz0_f / 2.0 + df_front / 2.0 - dFz_long / 2.0 - dFz_lat_f / 2.0, 0.0)
            Fz_FR = max(Fz0_f / 2.0 + df_front / 2.0 - dFz_long / 2.0 + dFz_lat_f / 2.0, 0.0)
            Fz_RL = max(Fz0_r / 2.0 + df_rear  / 2.0 + dFz_long / 2.0 - dFz_lat_r / 2.0, 0.0)
            Fz_RR = max(Fz0_r / 2.0 + df_rear  / 2.0 + dFz_long / 2.0 + dFz_lat_r / 2.0, 0.0)

            # Deflections
            heave_mm = -(df_total / K_heave) * 1000.0

            # Physically derived anti-geometry partitions pitch moment between links and springs
            if ax < 0.0:
                # Braking anti-pitch fraction
                anti_pitch = (a * getattr(sus, "anti_dive_front", 0.0) + b * getattr(sus, "anti_lift_rear", 0.0)) / L
            else:
                # Traction anti-pitch fraction
                anti_pitch = (b * getattr(sus, "anti_squat_rear", 0.0) + a * getattr(sus, "anti_lift_front", 0.0)) / L

            pitch_rad = ((1.0 - anti_pitch) * ax * m * mp.h_cog / K_theta) if K_theta > 1.0 else 0.0
            pitch_deg = math.degrees(pitch_rad)
            roll_rad = (ay * m * mp.h_cog / K_phi) if K_phi > 1.0 else 0.0
            roll_deg = math.degrees(roll_rad)

            # Target new ride heights
            rh_f_target = max(sus.ride_height_front + heave_mm + pitch_rad * a * 1000.0, 0.0)
            rh_r_target = max(sus.ride_height_rear  + heave_mm - pitch_rad * b * 1000.0, 0.0)

            # Under-relaxation for guaranteed convergence
            alpha = self.relaxation_alpha
            rh_f_new = (1.0 - alpha) * rh_f + alpha * rh_f_target
            rh_r_new = (1.0 - alpha) * rh_r + alpha * rh_r_target

            delta_rh = abs(rh_f_new - rh_f) + abs(rh_r_new - rh_r)
            last_residual = float(delta_rh)
            rh_f = rh_f_new
            rh_r = rh_r_new
            state.pitch_deg = pitch_deg
            state.roll_deg = roll_deg

            if delta_rh < self.tol:
                converged = True
                break

        # Epistemic validity assessment: evaluate final equilibrium state
        bottomed_out = bool(rh_f <= 1.0 or rh_r <= 1.0)
        v_warnings: list[str] = []
        if bottomed_out or rh_f <= 0.0 or rh_r <= 0.0:
            v_status = PhysicsValidityStatus.UNSUPPORTED
            v_warnings.append(
                f"Plank contact / aerodynamic stall detected: suspension bottomed out (front_RH={rh_f:.1f} mm, rear_RH={rh_r:.1f} mm)."
            )
        elif porpoising_detected and not converged:
            v_status = PhysicsValidityStatus.NUMERICALLY_FAILED
            v_warnings.append(
                "Aerodynamic porpoising limit cycle detected: suspension oscillation between pre-stall "
                f"and post-stall ground effect regimes prevented equilibrium convergence (residual={last_residual:.4f} > {self.tol})."
            )
        elif rh_f < 20.0:
            v_status = PhysicsValidityStatus.EXTRAPOLATED
            v_warnings.append(
                f"Front ride height ({rh_f:.1f} mm) is below the 20.0 mm aerodynamic safety boundary. "
                "Airflow is subject to boundary layer separation and ground-effect stall; model results are extrapolated."
            )
        elif not converged:
            v_status = PhysicsValidityStatus.NUMERICALLY_FAILED
            v_warnings.append(
                f"Coupled aero-suspension equilibrium failed to converge within {self.max_iter} iterations "
                f"(residual={last_residual:.4f} > {self.tol})."
            )
        else:
            v_status = PhysicsValidityStatus.MODEL_SUPPORTED

        val_record = PhysicsValidityRecord(
            status=v_status,
            model="CoupledAeroSuspension-v2.0",
            warnings=v_warnings,
            data_provenance={
                "front_rh_mm": round(float(rh_f), 2),
                "rear_rh_mm": round(float(rh_r), 2),
                "pitch_deg": round(float(pitch_deg), 2),
                "roll_deg": round(float(roll_deg), 2),
                "converged": converged,
                "porpoising_detected": porpoising_detected,
                "bottomed_out": bottomed_out,
                "n_iterations": n_iter,
            },
            validation_evidence="Closed-loop aero-suspension under-relaxed equilibrium solver.",
        )

        cm_pitch = cl_val * (getattr(self.aero, "cop_base", 0.44) - cop_val)

        return CoupledState(
            heave_mm=heave_mm,
            pitch_deg=pitch_deg,
            roll_deg=roll_deg,
            rh_front_mm=rh_f,
            rh_rear_mm=rh_r,
            Fz_FL=Fz_FL,
            Fz_FR=Fz_FR,
            Fz_RL=Fz_RL,
            Fz_RR=Fz_RR,
            aero_df_total_n=df_total,
            aero_df_front_n=df_front,
            aero_df_rear_n=df_rear,
            cd_eff=cd_val,
            cop_fraction=cop_val,
            cm_pitch=cm_pitch,
            active_aero_mode=str(active_aero_mode.value if isinstance(active_aero_mode, ActiveAeroMode) else active_aero_mode),
            residual_norm=last_residual,
            bottomed_out=bottomed_out,
            converged=converged,
            porpoising_detected=porpoising_detected,
            flow_separated=flow_sep,
            n_iterations=n_iter,
            validity_record=val_record,
        )


    # ── Setup sensitivity analysis ────────────────────────────────────────────

    def sensitivity_to_arb(
        self,
        v: float,
        ay: float,
        delta_arb_front: float = 5_000.0,
    ) -> dict:
        """Compute sensitivity of front/rear load transfer to ARB change.

        Parameters
        ----------
        v               : speed [m/s]
        ay              : lateral acceleration [m/s²]
        delta_arb_front : change in front ARB rate to perturb [N/m]

        Returns
        -------
        dict with keys:
            baseline_arb_balance  : baseline front ARB balance fraction
            perturbed_arb_balance : perturbed front ARB balance fraction
            delta_lat_transfer_front_n : change in front lateral load transfer [N]
            delta_lat_transfer_rear_n  : change in rear lateral load transfer [N]
            understeer_tendency   : 'more' | 'less' | 'unchanged'
        """
        sus_base = self.sus
        m    = self.mp.total_mass
        h    = self.mp.h_cog
        tf   = self.mp.track_front
        tr   = self.mp.track_rear

        K_phi_f_base = sus_base.roll_stiffness_front(tf)
        K_phi_r_base = sus_base.roll_stiffness_rear(tr)
        K_phi_base   = K_phi_f_base + K_phi_r_base

        lat_frac_f_base = K_phi_f_base / max(K_phi_base, 1.0)
        dFz_lat_f_base  = lat_frac_f_base * m * ay * h / tf

        # Perturbed
        k_arb_f_new = sus_base.k_arb_front + delta_arb_front
        K_phi_f_new = (sus_base.k_spring_front + k_arb_f_new) * tf ** 2 / 2.0
        K_phi_new   = K_phi_f_new + K_phi_r_base
        lat_frac_f_new  = K_phi_f_new / max(K_phi_new, 1.0)
        dFz_lat_f_new   = lat_frac_f_new * m * ay * h / tf

        delta_lt_f = dFz_lat_f_new - dFz_lat_f_base

        # More front load transfer → more front tire saturation → understeer
        understeer = "more" if delta_lt_f > 10 else ("less" if delta_lt_f < -10 else "unchanged")

        return {
            "baseline_arb_balance":         round(lat_frac_f_base, 4),
            "perturbed_arb_balance":         round(lat_frac_f_new,  4),
            "delta_lat_transfer_front_n":    round(delta_lt_f, 1),
            "delta_lat_transfer_rear_n":     round(-delta_lt_f, 1),  # conservation
            "understeer_tendency":           understeer,
        }

    def sensitivity_to_ride_height(
        self,
        v: float,
        delta_rh_mm: float = 5.0,
    ) -> dict:
        """Compute sensitivity of aero downforce to front ride height change.

        Parameters
        ----------
        v           : speed [m/s]
        delta_rh_mm : ride height perturbation [mm] (positive = raise front)

        Returns
        -------
        dict with aero change and load distribution change.
        """
        q_dyn = 0.5 * self.aero.rho_air * self.aero.frontal_area * v ** 2
        dCL_drh = self.aero.cl_rh_sens  # ΔCL/mm

        delta_df = dCL_drh * delta_rh_mm * q_dyn  # N change in total downforce
        delta_df_front = delta_df * self.aero.cop_fraction
        delta_df_rear  = delta_df * (1.0 - self.aero.cop_fraction)

        return {
            "delta_rh_front_mm":          delta_rh_mm,
            "delta_downforce_total_n":     round(delta_df, 1),
            "delta_downforce_front_n":     round(delta_df_front, 1),
            "delta_downforce_rear_n":      round(delta_df_rear, 1),
            "note": ("Lowering front ride height increases downforce on a ground-effect car "
                     "(cl_rh_sens > 0). Rear ride height is more sensitive on modern cars."),
        }
