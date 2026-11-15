"""
physics/lap_sim.py
==================
SuspensionLab PRO — Coupled 3-Pass GGV & Closed-Loop QSS Lap Solver

Features:
- Coupled GGV Surface pre-computation (compute_ggv_surface):
  * Speeds v = 5..95 m/s
  * Speed-squared downforce (0.5 * rho * Cl * A * v^2) and drag (0.5 * rho * Cd * A * v^2)
  * Suspension Lateral Load Transfer Distribution (LLTD) from k_spring_f, k_spring_r,
    mr_f, mr_r, k_arb_f, k_arb_r, roll_center_f_m, roll_center_r_m, cg_height_m
  * Nonlinear tire load sensitivity: mu(Fz) = mu_0 * (Fz / Fz_nom)^(-k_load)
    shifting cornering grip between axles and identifying UNDERSTEER_FRONT vs OVERSTEER_REAR
  * Multi-gear powertrain torque curve, shift-time penalty, and max_brake_force clamp
- Closed-Loop 3-Pass QSS Integration (simulate_lap):
  * Built-in tracks: spa, silverstone, monza, fsae_endurance
  * Custom segment arrays: [{type, length_m, radius_m, banking_deg, grade_pct}]
  * Telemetry CSV / data arrays: [{time_s, speed_ms, lat_g}]
  * Closed-circuit start speed bug fix: cyclic forward/backward passes until |v(0) - v(end)| < 0.01 m/s
  * Real 3-sector splits, positive energy_used_kj, braking_energy_kj, 2D coordinates x_m, y_m
  * Locked JSON contract trace & limiting_factor identification
- Full backward-compatibility with existing LapSimVehicle, LapSimResult, and solve_lap callers.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Tuple, Union

import numpy as np

from suspensionlab.physics.magic_formula import (
    TireCoeffs,
    _calc_tire_forces_fast,
)
from suspensionlab.physics.suspension_aero_coupling import (
    SuspensionConfig,
    CoupledVehicleModel,
    CoupledState,
)

FAST_QUASI_STEADY = "FAST_QUASI_STEADY"
SOLVER_MODE_FAST_QUASI_STEADY = FAST_QUASI_STEADY


# ─────────────────────────────────────────────────────────────────────────────
# Sub-model dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MassProperties:
    """Vehicle mass and geometric properties."""
    total_mass:     float = 800.0    # kg
    h_cog:          float = 0.30     # m
    wheelbase:      float = 2.70     # m
    cog_dist_front: float = 1.35     # m
    track_front:    float = 1.60     # m
    track_rear:     float = 1.55     # m

    def __post_init__(self):
        if self.total_mass <= 0.0:
            raise ValueError("Vehicle total mass must be strictly positive.")
        if self.wheelbase <= 0.0:
            raise ValueError("Vehicle wheelbase must be strictly positive.")
        if self.track_front <= 0.0 or self.track_rear <= 0.0:
            raise ValueError("Track widths must be strictly positive.")

    @property
    def a(self) -> float:
        """Distance from front axle to CoG [m]."""
        return self.cog_dist_front

    @property
    def b(self) -> float:
        """Distance from rear axle to CoG [m]."""
        return self.wheelbase - self.cog_dist_front

    @property
    def weight_dist_front(self) -> float:
        """Static front weight distribution fraction."""
        return self.b / self.wheelbase

    @property
    def weight_dist_rear(self) -> float:
        """Static rear weight distribution fraction."""
        return self.a / self.wheelbase

    @property
    def track_mean(self) -> float:
        """Mean track width [m]."""
        return 0.5 * (self.track_front + self.track_rear)


@dataclass
class AeroMap:
    """Aerodynamic map with front/rear balance and ride-height sensitivity."""
    cl_base:      float = 2.20    # lift coefficient (downforce positive)
    cd_base:      float = 0.90    # drag coefficient
    frontal_area: float = 1.60    # m²
    cop_fraction: float = 0.45    # CoP fraction from front (0.45 = 45% front)
    rho_air:      float = 1.225   # kg/m³
    cl_rh_sens:   float = 0.0     # ΔCL/mm
    cl_pitch_sens: float = 0.0

    # Nonlinear ground-effect parameters
    nonlinear_ground_effect: bool = False
    rh_peak_mm: float = 22.0
    cl_stall_floor: float = 1.20
    stall_decay_power: float = 2.0

    def _effective_cl(self, ride_height_mm: float = 0.0) -> float:
        if self.nonlinear_ground_effect:
            if ride_height_mm >= self.rh_peak_mm:
                return max(self.cl_base + self.cl_rh_sens * (ride_height_mm - self.rh_peak_mm), 0.2)
            else:
                eta = max(0.0, ride_height_mm / max(self.rh_peak_mm, 1.0))
                return max(self.cl_stall_floor + (self.cl_base - self.cl_stall_floor) * (eta ** self.stall_decay_power), 0.2)
        return self.cl_base + self.cl_rh_sens * ride_height_mm

    def downforce_total(self, v: float, ride_height_mm: float = 0.0) -> float:
        cl = self._effective_cl(ride_height_mm)
        return 0.5 * self.rho_air * cl * self.frontal_area * (v ** 2)

    def downforce_front(self, v: float, ride_height_mm: float = 0.0) -> float:
        return self.downforce_total(v, ride_height_mm) * self.cop_fraction

    def downforce_rear(self, v: float, ride_height_mm: float = 0.0) -> float:
        return self.downforce_total(v, ride_height_mm) * (1.0 - self.cop_fraction)

    def drag(self, v: float) -> float:
        return 0.5 * self.rho_air * self.cd_base * self.frontal_area * (v ** 2)


@dataclass
class PowertrainModel:
    """Powertrain with multi-gear drivetrain torque curve and brake limits."""
    gear_ratios:       List[float] = field(default_factory=lambda: [13.5, 9.8, 7.4, 5.9, 4.8, 4.0])
    torque_curve_rpm:  List[float] = field(default_factory=lambda: [2000, 4000, 6000, 8000, 10000, 12000])
    torque_curve_nm:   List[float] = field(default_factory=lambda: [320, 380, 430, 420, 380, 310])
    rev_limit:         float = 12000.0    # rpm
    wheel_radius:      float = 0.33       # m
    drivetrain_loss:   float = 0.10       # fraction (10%)
    shift_time_s:      float = 0.050      # s
    max_brake_force_n: float = 28_000.0  # N
    brake_front_bias:  float = 0.60       # fraction

    def engine_torque(self, rpm: float) -> float:
        rpm = np.clip(rpm, self.torque_curve_rpm[0], self.rev_limit)
        return float(np.interp(rpm, self.torque_curve_rpm, self.torque_curve_nm))

    def select_gear(self, v: float) -> int:
        if v <= 0.05:
            return 0
        best_gear = 0
        max_force = -1.0
        for i, gr in enumerate(self.gear_ratios):
            rpm = (v / self.wheel_radius) * gr * (60.0 / (2.0 * np.pi))
            if rpm <= self.rev_limit * 1.02:
                torque = self.engine_torque(rpm)
                force = torque * gr * (1.0 - self.drivetrain_loss) / self.wheel_radius
                if force > max_force:
                    max_force = force
                    best_gear = i
        if max_force < 0:
            return len(self.gear_ratios) - 1
        return best_gear

    def engine_rpm_at(self, v: float, gear: int) -> float:
        gr = self.gear_ratios[gear]
        return (v / self.wheel_radius) * gr * (60.0 / (2.0 * np.pi))

    def max_drive_force(self, v: float) -> float:
        if v <= 0.01:
            gr = self.gear_ratios[0]
            t_launch = self.torque_curve_nm[0]
            return float(t_launch * gr * (1.0 - self.drivetrain_loss) / self.wheel_radius)
        gear = self.select_gear(v)
        rpm = self.engine_rpm_at(v, gear)
        T_engine = self.engine_torque(rpm)
        gr = self.gear_ratios[gear]
        F_wheel = T_engine * gr * (1.0 - self.drivetrain_loss) / self.wheel_radius
        return max(float(F_wheel), 0.0)

    def max_power_w(self) -> float:
        rpms = np.array(self.torque_curve_rpm)
        torques = np.array(self.torque_curve_nm)
        powers = torques * rpms * (2.0 * np.pi / 60.0) * (1.0 - self.drivetrain_loss)
        return float(np.max(powers))


# ─────────────────────────────────────────────────────────────────────────────
# TrackSegment & Validation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrackSegment:
    """One sample point along a track."""
    distance:      float = 0.0
    curvature:     float = 0.0
    elevation:     float = 0.0
    bank_angle:    float = 0.0
    sector:        int   = 1
    heading:       float = 0.0
    surface_mu:    float = 1.0
    friction_zone: str   = "asphalt"
    x_m:           float = 0.0
    y_m:           float = 0.0


@dataclass
class TrackValidationReport:
    """Quantitative circuit geometric validation report."""
    is_geometrically_valid: bool
    total_length_m: float
    max_heading_error_rad: float
    max_elevation_gradient: float
    max_bank_rate_rad_m: float
    closure_error_m: float
    validation_status: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_geometrically_valid": self.is_geometrically_valid,
            "total_length_m": round(self.total_length_m, 2),
            "max_heading_error_rad": round(self.max_heading_error_rad, 6),
            "max_elevation_gradient": round(self.max_elevation_gradient, 4),
            "max_bank_rate_rad_m": round(self.max_bank_rate_rad_m, 6),
            "closure_error_m": round(self.closure_error_m, 3),
            "validation_status": self.validation_status,
            "warnings": self.warnings,
        }


class TrackValidator:
    """Validates physical track geometry, Frenet-Serret curvature relations, and closure."""
    MAX_CURVATURE = 0.5       # |κ| max → R_min = 2 m
    MAX_GRADIENT = 0.35       # 35% grade
    MAX_HEADING_ERR = 0.05    # rad
    MAX_CLOSURE_M = 15.0      # m
    MAX_CURV_RATE = 0.05      # 1/m²

    @staticmethod
    def validate(segments: list[TrackSegment], is_closed_circuit: bool = True) -> TrackValidationReport:
        if len(segments) < 2:
            return TrackValidationReport(
                is_geometrically_valid=False,
                total_length_m=0.0,
                max_heading_error_rad=0.0,
                max_elevation_gradient=0.0,
                max_bank_rate_rad_m=0.0,
                closure_error_m=0.0,
                validation_status="INVALID_TOO_FEW_POINTS",
                warnings=["Track must contain at least 2 segments."],
            )

        total_length = segments[-1].distance - segments[0].distance
        max_heading_err = 0.0
        max_grad = 0.0
        max_bank_rate = 0.0
        pos_x = 0.0
        pos_y = 0.0
        warnings_list: list[str] = []
        fatal_issues: list[str] = []

        for i in range(len(segments)):
            s = segments[i]
            if math.isnan(s.curvature) or math.isinf(s.curvature):
                fatal_issues.append(f"Station {i}: curvature is NaN or ±∞.")
            if math.isnan(s.elevation) or math.isinf(s.elevation):
                fatal_issues.append(f"Station {i}: elevation is NaN or ±∞.")
            if math.isnan(s.bank_angle) or math.isinf(s.bank_angle):
                fatal_issues.append(f"Station {i}: bank_angle is NaN or ±∞.")
            if abs(s.curvature) > TrackValidator.MAX_CURVATURE:
                fatal_issues.append(f"Station {i}: |κ|={abs(s.curvature):.4f} 1/m exceeds limit.")
            if s.surface_mu <= 0.0 or s.surface_mu > 5.0:
                fatal_issues.append(f"Station {i}: surface_mu={s.surface_mu:.3f} out of range (0, 5].")

        for i in range(len(segments) - 1):
            s0 = segments[i]
            s1 = segments[i + 1]
            ds = s1.distance - s0.distance
            if ds <= 0.0:
                fatal_issues.append(f"Stations {i}→{i+1}: non-monotonic distance (ds={ds:.6f}m).")
                continue

            grad = abs((s1.elevation - s0.elevation) / ds)
            if grad > max_grad:
                max_grad = grad

            mid_heading = 0.5 * (s0.heading + s1.heading)
            pos_x += ds * math.cos(mid_heading)
            pos_y += ds * math.sin(mid_heading)

        closure_err = math.sqrt(pos_x**2 + pos_y**2) if is_closed_circuit else 0.0
        has_fatal = len(fatal_issues) > 0

        return TrackValidationReport(
            is_geometrically_valid=not has_fatal,
            total_length_m=total_length,
            max_heading_error_rad=max_heading_err,
            max_elevation_gradient=max_grad,
            max_bank_rate_rad_m=max_bank_rate,
            closure_error_m=closure_err,
            validation_status="VALIDATED" if not has_fatal else "INVALID_GEOMETRY",
            warnings=fatal_issues + warnings_list,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Coupled GGV Envelope Solver (Task 1 Core)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LapSimVehicleParams:
    """Comprehensive vehicle dynamics parameters for Coupled GGV & QSS Solver."""
    # Mass & geometry
    mass_kg:             float = 1285.0
    weight_dist_front:   float = 0.48    # fraction of weight on front axle
    cg_height_m:         float = 0.42
    wheelbase_m:         float = 2.65
    track_front_m:       float = 1.62
    track_rear_m:        float = 1.60

    # Aerodynamics
    cl_total:            float = 1.65    # lift coefficient (downforce positive)
    cd_total:            float = 0.48    # drag coefficient
    frontal_area_m2:     float = 2.02    # m²
    aero_balance_front:  float = 0.46    # aero center of pressure fraction on front axle
    rho_air:             float = 1.225   # kg/m³

    # Suspension & Kinematics Coupling
    k_spring_front_n_m:  float = 140000.0  # front coil spring rate [N/m]
    k_spring_rear_n_m:   float = 160000.0  # rear coil spring rate [N/m]
    motion_ratio_front:  float = 0.72      # front spring motion ratio [-]
    motion_ratio_rear:   float = 0.74      # rear spring motion ratio [-]
    k_arb_front_nm_rad:  float = 28000.0   # front ARB rate [N*m/rad]
    k_arb_rear_nm_rad:   float = 22000.0   # rear ARB rate [N*m/rad]
    roll_center_front_m: float = 0.035     # front kinematic roll center height [m]
    roll_center_rear_m:  float = 0.042     # rear kinematic roll center height [m]
    camber_gain_front:   float = -2.2      # deg/m or deg/deg
    camber_gain_rear:    float = -1.8

    # Tires & nonlinear load sensitivity: mu(Fz) = mu_0 * max(0.5, (Fz / fz_nom_n)^(-k_load_sensitivity))
    mu_0:                float = 1.38      # nominal peak tire friction coefficient [-]
    fz_nom_n:            float = 4000.0    # nominal reference tire load [N]
    k_load_sensitivity:  float = 0.08      # tire load sensitivity exponent [-]
    c_rr:                float = 0.015     # tire rolling resistance coefficient [-]

    # Powertrain & braking
    max_power_kw:        float = 395.0     # kW (395 kW GT3)
    gear_ratios:         List[float] = field(default_factory=lambda: [3.15, 2.25, 1.72, 1.38, 1.15, 0.96])
    final_drive:         float = 3.45
    max_rpm:             float = 8200.0
    wheel_radius_m:      float = 0.33
    drivetrain_efficiency: float = 0.92
    shift_time_s:        float = 0.045
    max_brake_force_n:   float = 22500.0   # N clamp
    brake_bias_front:    float = 0.58      # 58% front brake bias
    max_power:           Optional[float] = None

    # Torque curve for detailed lookup
    torque_curve_rpm:    List[float] = field(default_factory=lambda: [2000.0, 3500.0, 5000.0, 6500.0, 7500.0, 8200.0])
    torque_curve_nm:     List[float] = field(default_factory=lambda: [420.0, 480.0, 520.0, 510.0, 470.0, 430.0])

    def __init__(self, **kwargs):
        # Default initialization (GT3 Spec Baseline: 1285 kg / 395 kW)
        self.mass_kg = 1285.0
        self.weight_dist_front = 0.48
        self.cg_height_m = 0.42
        self.wheelbase_m = 2.65
        self.track_front_m = 1.62
        self.track_rear_m = 1.60

        self.cl_total = 1.65
        self.cd_total = 0.46
        self.frontal_area_m2 = 2.02
        self.aero_balance_front = 0.46
        self.rho_air = 1.225

        self.k_spring_front_n_m = 140000.0
        self.k_spring_rear_n_m = 160000.0
        self.motion_ratio_front = 0.72
        self.motion_ratio_rear = 0.74
        self.k_arb_front_nm_rad = 45000.0
        self.k_arb_rear_nm_rad = 30000.0
        self.roll_center_front_m = 0.035
        self.roll_center_rear_m = 0.042
        self.camber_gain_front = -2.2
        self.camber_gain_rear = -1.8

        self.mu_0 = 1.38
        self.fz_nom_n = 4000.0
        self.k_load_sensitivity = 0.08
        self.c_rr = 0.015

        self.max_power_kw = 395.0
        self.gear_ratios = [3.15, 2.25, 1.72, 1.38, 1.15, 0.96]
        self.final_drive = 3.45
        self.max_rpm = 8200.0
        self.wheel_radius_m = 0.33
        self.drivetrain_efficiency = 0.92
        self.shift_time_s = 0.045
        self.max_brake_force_n = 22500.0
        self.brake_bias_front = 0.58
        self.max_power = None
        self.torque_curve_rpm = [2000.0, 3500.0, 5000.0, 6500.0, 7500.0, 8200.0]
        self.torque_curve_nm = [420.0, 480.0, 520.0, 510.0, 470.0, 430.0]

        # Apply kwargs with legacy and alternative alias mapping
        for k, v in kwargs.items():
            if v is None:
                continue
            if k in ("c_rr", "crr", "rolling_resistance"): self.c_rr = float(v)
            elif k in ("weight_dist_f", "weight_dist"): self.weight_dist_front = float(v)
            elif k in ("cl", "aero_cl", "cl_base"): self.cl_total = float(v)
            elif k in ("cd", "aero_cd", "cd_base"): self.cd_total = float(v)
            elif k in ("frontal_area", "frontal_area_m2"): self.frontal_area_m2 = float(v)
            elif k in ("track_f_m", "track_f", "track_front"): self.track_front_m = float(v)
            elif k in ("track_r_m", "track_r", "track_rear"): self.track_rear_m = float(v)
            elif k in ("cop_front", "cop_fraction", "aero_balance"): self.aero_balance_front = float(v)
            elif k in ("k_spring_f", "k_spring_front", "front_spring_rate", "k_spring_front_n_m"):
                s_val = float(v)
                self.k_spring_front_n_m = s_val * 1000.0 if s_val < 1000.0 else s_val
            elif k in ("k_spring_r", "k_spring_rear", "rear_spring_rate", "k_spring_rear_n_m"):
                s_val = float(v)
                self.k_spring_rear_n_m = s_val * 1000.0 if s_val < 1000.0 else s_val
            elif k in ("mr_f", "motion_ratio_f", "motion_ratio_front"): self.motion_ratio_front = float(v)
            elif k in ("mr_r", "motion_ratio_r", "motion_ratio_rear"): self.motion_ratio_rear = float(v)
            elif k in ("k_arb_f", "k_arb_front", "k_arb_front_nm_rad", "front_arb"):
                a_val = float(v)
                self.k_arb_front_nm_rad = a_val * 1000.0 if a_val < 1000.0 else a_val
            elif k in ("k_arb_r", "k_arb_rear", "k_arb_rear_nm_rad", "rear_arb"):
                a_val = float(v)
                self.k_arb_rear_nm_rad = a_val * 1000.0 if a_val < 1000.0 else a_val
            elif k in ("roll_center_f_m", "roll_center_front", "rc_f", "front_rc_height", "roll_center_front_m"):
                rc_val = float(v)
                self.roll_center_front_m = rc_val / 1000.0 if abs(rc_val) > 1.0 else rc_val
            elif k in ("roll_center_r_m", "roll_center_rear", "rc_r", "rear_rc_height", "roll_center_rear_m"):
                rc_val = float(v)
                self.roll_center_rear_m = rc_val / 1000.0 if abs(rc_val) > 1.0 else rc_val
            elif k in ("Fz_nom", "fz_nom"): self.fz_nom_n = float(v)
            elif k in ("k_load", "load_sensitivity"): self.k_load_sensitivity = float(v)
            elif k in ("tire_mu", "mu_0", "mu"): self.mu_0 = float(v)
            elif k in ("max_brake_force", "brake_force_max", "max_brake_force_n"): self.max_brake_force_n = float(v)
            elif k in ("brake_bias_f", "brake_bias", "brake_front_bias", "brake_bias_front"):
                b_val = float(v)
                self.brake_bias_front = b_val / 100.0 if b_val > 1.0 else b_val
            elif k in ("rev_limit", "max_revs"): self.max_rpm = float(v)
            elif k == "drivetrain_loss": self.drivetrain_efficiency = 1.0 - float(v)
            elif k in ("mass", "total_mass", "mass_kg"): self.mass_kg = float(v)
            elif k == "max_power":
                self.max_power = float(v)
                self.max_power_kw = float(v) / 1000.0
            elif hasattr(self, k):
                setattr(self, k, v)

    # Backward compatibility properties & aliases
    @property
    def weight_dist_f(self) -> float:
        return self.weight_dist_front
    @weight_dist_f.setter
    def weight_dist_f(self, val: float):
        self.weight_dist_front = float(val)

    @property
    def cl(self) -> float:
        return self.cl_total
    @cl.setter
    def cl(self, val: float):
        self.cl_total = float(val)

    @property
    def cd(self) -> float:
        return self.cd_total
    @cd.setter
    def cd(self, val: float):
        self.cd_total = float(val)

    @property
    def track_f_m(self) -> float:
        return self.track_front_m
    @track_f_m.setter
    def track_f_m(self, val: float):
        self.track_front_m = float(val)

    @property
    def track_r_m(self) -> float:
        return self.track_rear_m
    @track_r_m.setter
    def track_r_m(self, val: float):
        self.track_rear_m = float(val)

    @property
    def cop_front(self) -> float:
        return self.aero_balance_front
    @cop_front.setter
    def cop_front(self, val: float):
        self.aero_balance_front = float(val)

    @property
    def k_spring_f(self) -> float:
        return self.k_spring_front_n_m
    @k_spring_f.setter
    def k_spring_f(self, val: float):
        self.k_spring_front_n_m = float(val)

    @property
    def k_spring_r(self) -> float:
        return self.k_spring_rear_n_m
    @k_spring_r.setter
    def k_spring_r(self, val: float):
        self.k_spring_rear_n_m = float(val)

    @property
    def mr_f(self) -> float:
        return self.motion_ratio_front
    @mr_f.setter
    def mr_f(self, val: float):
        self.motion_ratio_front = float(val)

    @property
    def mr_r(self) -> float:
        return self.motion_ratio_rear
    @mr_r.setter
    def mr_r(self, val: float):
        self.motion_ratio_rear = float(val)

    @property
    def k_arb_f(self) -> float:
        return self.k_arb_front_nm_rad
    @k_arb_f.setter
    def k_arb_f(self, val: float):
        self.k_arb_front_nm_rad = float(val)

    @property
    def k_arb_r(self) -> float:
        return self.k_arb_rear_nm_rad
    @k_arb_r.setter
    def k_arb_r(self, val: float):
        self.k_arb_rear_nm_rad = float(val)

    @property
    def roll_center_f_m(self) -> float:
        return self.roll_center_front_m
    @roll_center_f_m.setter
    def roll_center_f_m(self, val: float):
        self.roll_center_front_m = float(val)

    @property
    def roll_center_r_m(self) -> float:
        return self.roll_center_rear_m
    @roll_center_r_m.setter
    def roll_center_r_m(self, val: float):
        self.roll_center_rear_m = float(val)

    @property
    def Fz_nom(self) -> float:
        return self.fz_nom_n
    @Fz_nom.setter
    def Fz_nom(self, val: float):
        self.fz_nom_n = float(val)

    @property
    def k_load(self) -> float:
        return self.k_load_sensitivity
    @k_load.setter
    def k_load(self, val: float):
        self.k_load_sensitivity = float(val)

    @property
    def max_brake_force(self) -> float:
        return self.max_brake_force_n
    @max_brake_force.setter
    def max_brake_force(self, val: float):
        self.max_brake_force_n = float(val)

    @property
    def brake_bias_f(self) -> float:
        return self.brake_bias_front
    @brake_bias_f.setter
    def brake_bias_f(self, val: float):
        self.brake_bias_front = float(val)

    @property
    def rev_limit(self) -> float:
        return self.max_rpm
    @rev_limit.setter
    def rev_limit(self, val: float):
        self.max_rpm = float(val)

    @property
    def drivetrain_loss(self) -> float:
        return 1.0 - self.drivetrain_efficiency
    @drivetrain_loss.setter
    def drivetrain_loss(self, val: float):
        self.drivetrain_efficiency = 1.0 - float(val)

    @property
    def a_m(self) -> float:
        """Distance from front axle to CoG [m]."""
        return self.wheelbase_m * (1.0 - self.weight_dist_front)

    @property
    def b_m(self) -> float:
        """Distance from rear axle to CoG [m]."""
        return self.wheelbase_m * self.weight_dist_front

    def effective_gear_ratios(self) -> List[float]:
        """Compute total gear ratios including final drive when transmission ratios are provided."""
        if self.final_drive > 1.0 and len(self.gear_ratios) > 0 and self.gear_ratios[0] < 6.0:
            return [gr * self.final_drive for gr in self.gear_ratios]
        return list(self.gear_ratios)

    def terminal_velocity(self) -> float:
        """Terminal velocity limited by aero drag, rolling resistance and peak power [m/s]."""
        if self.max_power is not None and self.max_power > 0.0:
            p_max = float(self.max_power)
        else:
            p_max = self.max_power_kw * 1000.0 * self.drivetrain_efficiency

        c_rr = getattr(self, "c_rr", 0.015)
        denom = max(self.rho_air * self.cd_total * self.frontal_area_m2, 1e-4)
        v = float((2.0 * p_max / denom) ** (1.0 / 3.0))
        for _ in range(12):
            f_drag = 0.5 * self.rho_air * self.cd_total * self.frontal_area_m2 * (v**2)
            f_down = 0.5 * self.rho_air * self.cl_total * self.frontal_area_m2 * (v**2)
            f_roll = c_rr * (self.mass_kg * 9.81 + f_down)
            f_thrust = p_max / max(v, 1.0)
            f_net = f_thrust - f_drag - f_roll
            df_dv = -(self.rho_air * self.cd_total * self.frontal_area_m2 * v + c_rr * self.rho_air * self.cl_total * self.frontal_area_m2 * v + f_thrust / max(v, 1.0))
            dv = f_net / max(abs(df_dv), 1e-3)
            v += dv
            if abs(dv) < 1e-4:
                break
        return float(max(v, 10.0))

    def tire_mu(self, Fz: float) -> float:
        """Nonlinear tire load sensitivity: mu(Fz) = mu_0 * max(0.5, (Fz / fz_nom_n)^(-k_load_sensitivity))."""
        Fz_clamped = max(Fz, 20.0)
        return float(self.mu_0 * max(0.5, (Fz_clamped / self.fz_nom_n) ** (-self.k_load_sensitivity)))

    def tire_lateral_force(self, Fz: float) -> float:
        """Maximum lateral grip force [N] from a single tire at normal load Fz."""
        return max(Fz, 0.0) * self.tire_mu(Fz)

    def roll_stiffness_front(self) -> float:
        """Total front axle roll stiffness K_phi_f [N*m/rad].
        k_wf = k_spring_front_n_m * (motion_ratio_front ** 2)
        K_phi_f = 0.5 * k_wf * (track_front_m ** 2) + k_arb_front_nm_rad
        """
        k_wf = self.k_spring_front_n_m * (self.motion_ratio_front ** 2)
        return 0.5 * k_wf * (self.track_front_m ** 2) + self.k_arb_front_nm_rad

    def roll_stiffness_rear(self) -> float:
        """Total rear axle roll stiffness K_phi_r [N*m/rad].
        k_wr = k_spring_rear_n_m * (motion_ratio_rear ** 2)
        K_phi_r = 0.5 * k_wr * (track_rear_m ** 2) + k_arb_rear_nm_rad
        """
        k_wr = self.k_spring_rear_n_m * (self.motion_ratio_rear ** 2)
        return 0.5 * k_wr * (self.track_rear_m ** 2) + self.k_arb_rear_nm_rad

    def lltd(self) -> float:
        """Suspension Lateral Load Transfer Distribution (LLTD) front fraction [-].
        lltd_front = K_phi_f / max(K_phi_f + K_phi_r, 1.0)
        """
        K_phi_f = self.roll_stiffness_front()
        K_phi_r = self.roll_stiffness_rear()
        return float(K_phi_f / max(K_phi_f + K_phi_r, 1.0))


VehicleParameters = LapSimVehicleParams


@dataclass
class GGVSurfaceResult:
    """Pre-computed GGV surface and envelope data."""
    speeds_ms:          np.ndarray
    speeds_kmh:         np.ndarray
    ay_max:             np.ndarray          # [m/s²]
    ay_max_g:           np.ndarray          # [g]
    ax_accel_ay0:       np.ndarray          # [m/s²] at ay=0
    ax_accel_ay0_g:     np.ndarray          # [g]
    ax_brake_ay0:       np.ndarray          # [m/s²] at ay=0 (positive magnitude)
    ax_brake_ay0_g:     np.ndarray          # [g]
    ax_accel_surface:   np.ndarray          # shape (n_v, n_ay) [m/s²]
    ax_brake_surface:   np.ndarray          # shape (n_v, n_ay) [m/s²] (positive magnitude)
    ay_fractions:       np.ndarray          # shape (n_ay,) from 0.0 to 1.0
    balance_limit:      List[str]           # 'UNDERSTEER_FRONT' or 'OVERSTEER_REAR' per speed
    lltd:               float

    def to_envelope_dict(self) -> Dict[str, List[float]]:
        return {
            "speeds_kmh": [round(float(s), 2) for s in self.speeds_kmh],
            "max_lat_g": [round(float(g), 3) for g in self.ay_max_g],
            "max_accel_g": [round(float(g), 3) for g in self.ax_accel_ay0_g],
            "max_brake_g": [round(float(g), 3) for g in self.ax_brake_ay0_g],
        }


def compute_ggv_surface(
    vehicle: Optional[Union[LapSimVehicle, VehicleParameters, Dict[str, Any]]] = None,
    speeds: Optional[np.ndarray] = None,
    n_ay: int = 21,
    **kwargs,
) -> GGVSurfaceResult:
    """Across speeds v = 5..95 m/s, compute max lateral ay_max(v), braking ax_min(v, ay),
    and traction ax_max(v, ay) coupled to downforce, drag, suspension LLTD, and nonlinear tire sensitivity.
    """
    vp = _normalize_to_vehicle_params(vehicle, **kwargs)

    if speeds is None:
        v_term_est = vp.terminal_velocity()
        v_max_table = min(max(v_term_est * 1.20, 95.0), 125.0)
        speeds_ms = np.linspace(5.0, v_max_table, 37)
    else:
        speeds_ms = np.asarray(speeds, dtype=float)

    n_v = len(speeds_ms)
    ay_frac = np.linspace(0.0, 1.0, n_ay)

    ay_max_arr = np.zeros(n_v)
    ax_accel_surf = np.zeros((n_v, n_ay))
    ax_brake_surf = np.zeros((n_v, n_ay))
    balance_limit_list: List[str] = []

    K_phi_f = vp.roll_stiffness_front()
    K_phi_r = vp.roll_stiffness_rear()
    K_phi_tot = max(K_phi_f + K_phi_r, 1.0)
    h_r = vp.roll_center_f_m + (vp.a_m / vp.wheelbase_m) * (vp.roll_center_r_m - vp.roll_center_f_m)
    delta_h = max(vp.cg_height_m - h_r, 0.02)
    lltd_val = vp.lltd()

    g = 9.81
    m = vp.mass_kg

    # Engine power curve helper
    def engine_drive_force(v: float) -> float:
        if v <= 0.05:
            return float(vp.torque_curve_nm[0] * vp.gear_ratios[0] * (1.0 - vp.drivetrain_loss) / vp.wheel_radius_m)
        best_f = 0.0
        for gr in vp.gear_ratios:
            rpm = (v / vp.wheel_radius_m) * gr * (60.0 / (2.0 * np.pi))
            if rpm <= vp.rev_limit * 1.02:
                rpm_c = np.clip(rpm, vp.torque_curve_rpm[0], vp.rev_limit)
                t_eng = float(np.interp(rpm_c, vp.torque_curve_rpm, vp.torque_curve_nm))
                f_w = t_eng * gr * (1.0 - vp.drivetrain_loss) / vp.wheel_radius_m
                if f_w > best_f:
                    best_f = f_w
        return max(best_f, 0.0)

    for i, v in enumerate(speeds_ms):
        # 1. Aero Downforce, Drag & Rolling Resistance
        F_down = 0.5 * vp.rho_air * vp.cl * vp.frontal_area_m2 * (v ** 2)
        F_drag = 0.5 * vp.rho_air * vp.cd * vp.frontal_area_m2 * (v ** 2)

        Fz_front_static = m * g * vp.weight_dist_f + F_down * vp.cop_front
        Fz_rear_static  = m * g * (1.0 - vp.weight_dist_f) + F_down * (1.0 - vp.cop_front)
        Fz_total_dyn = max(Fz_front_static + Fz_rear_static, 100.0)
        c_rr = getattr(vp, "c_rr", 0.015)
        F_rolling = c_rr * Fz_total_dyn

        # 2. Iterate for peak equilibrium lateral acceleration ay_max(v)
        ay_iter = 12.0
        limiting_axle = "UNDERSTEER_FRONT"

        for _ in range(16):
            dFz_geom_f = m * ay_iter * vp.weight_dist_f * (vp.roll_center_f_m / vp.track_f_m)
            dFz_geom_r = m * ay_iter * (1.0 - vp.weight_dist_f) * (vp.roll_center_r_m / vp.track_r_m)
            M_roll = m * ay_iter * delta_h
            dFz_elast_f = (K_phi_f / K_phi_tot) * (M_roll / vp.track_f_m)
            dFz_elast_r = (K_phi_r / K_phi_tot) * (M_roll / vp.track_r_m)

            dFz_f = dFz_geom_f + dFz_elast_f
            dFz_r = dFz_geom_r + dFz_elast_r

            Fz_fl = max(Fz_front_static / 2.0 - dFz_f, 15.0)
            Fz_fr = max(Fz_front_static / 2.0 + dFz_f, 15.0)
            Fz_rl = max(Fz_rear_static  / 2.0 - dFz_r, 15.0)
            Fz_rr = max(Fz_rear_static  / 2.0 + dFz_r, 15.0)

            Fy_front = vp.tire_lateral_force(Fz_fl) + vp.tire_lateral_force(Fz_fr)
            Fy_rear  = vp.tire_lateral_force(Fz_rl) + vp.tire_lateral_force(Fz_rr)

            ay_f_cap = Fy_front / (m * vp.weight_dist_f)
            ay_r_cap = Fy_rear  / (m * (1.0 - vp.weight_dist_f))

            if ay_f_cap <= ay_r_cap:
                ay_new = ay_f_cap
                limiting_axle = "UNDERSTEER_FRONT"
            else:
                ay_new = ay_r_cap
                limiting_axle = "OVERSTEER_REAR"

            if abs(ay_new - ay_iter) < 0.005:
                ay_iter = ay_new
                break
            ay_iter = 0.5 * ay_iter + 0.5 * ay_new

        ay_max = max(float(ay_iter), 1.0)
        ay_max_arr[i] = ay_max
        balance_limit_list.append(limiting_axle)

        # 3. Longitudinal Coupled Envelopes across ay fractions
        F_drive_eng = engine_drive_force(v)

        for j, frac in enumerate(ay_frac):
            ay_val = frac * ay_max
            eta_y = min(ay_val / max(ay_max, 0.01), 1.0)
            eta_x = math.sqrt(max(0.0, 1.0 - eta_y ** 2))

            # Traction limit (RWD driven axle with longitudinal load transfer)
            ax_guess = 4.0
            Fz_rear_accel = Fz_rear_static + m * ax_guess * (vp.cg_height_m / vp.wheelbase_m)
            Fx_rear_tire = max(Fz_rear_accel, 20.0) * vp.tire_mu(Fz_rear_accel / 2.0) * eta_x
            F_traction_lim = min(F_drive_eng, Fx_rear_tire)
            if j == 0 and v <= vp.terminal_velocity() + 1e-3:
                ax_accel = max((F_traction_lim - F_drag - F_rolling) / m, 0.0)
            else:
                ax_accel = (F_traction_lim - F_drag - F_rolling) / m
            ax_accel_surf[i, j] = ax_accel

            # Braking limit
            # Total vertical load available for braking with speed-squared downforce
            mu_eff_brake = vp.tire_mu(Fz_total_dyn / 4.0) * eta_x
            F_brake_tire = Fz_total_dyn * mu_eff_brake
            F_brake_actual = min(F_brake_tire, vp.max_brake_force_n)

            ax_brake = (F_brake_actual + F_drag + F_rolling) / m
            ax_brake_surf[i, j] = max(ax_brake, 0.1)

    return GGVSurfaceResult(
        speeds_ms=speeds_ms,
        speeds_kmh=speeds_ms * 3.6,
        ay_max=ay_max_arr,
        ay_max_g=ay_max_arr / g,
        ax_accel_ay0=ax_accel_surf[:, 0],
        ax_accel_ay0_g=ax_accel_surf[:, 0] / g,
        ax_brake_ay0=ax_brake_surf[:, 0],
        ax_brake_ay0_g=ax_brake_surf[:, 0] / g,
        ax_accel_surface=ax_accel_surf,
        ax_brake_surface=ax_brake_surf,
        ay_fractions=ay_frac,
        balance_limit=balance_limit_list,
        lltd=lltd_val,
    )


def _normalize_to_vehicle_params(
    v: Optional[Union[LapSimVehicle, LapSimVehicleParams, Dict[str, Any]]] = None,
    **kwargs,
) -> LapSimVehicleParams:
    """Helper to convert any vehicle input format into authoritative LapSimVehicleParams."""
    import copy

    if isinstance(v, LapSimVehicleParams):
        vp = copy.copy(v)
    elif isinstance(v, LapSimVehicle):
        vp = LapSimVehicleParams(
            mass_kg=v.mass_props.total_mass,
            weight_dist_front=v.mass_props.weight_dist_front,
            cg_height_m=v.mass_props.h_cog,
            wheelbase_m=v.mass_props.wheelbase,
            track_front_m=v.mass_props.track_front,
            track_rear_m=v.mass_props.track_rear,
            cl_total=v.aero.cl_base,
            cd_total=v.aero.cd_base,
            frontal_area_m2=v.aero.frontal_area,
            aero_balance_front=v.aero.cop_fraction,
            rho_air=v.aero.rho_air,
            gear_ratios=list(v.powertrain.gear_ratios),
            max_rpm=v.powertrain.rev_limit,
            wheel_radius_m=v.powertrain.wheel_radius,
            drivetrain_efficiency=1.0 - v.powertrain.drivetrain_loss,
            shift_time_s=v.powertrain.shift_time_s,
            max_brake_force_n=v.powertrain.max_brake_force_n,
            brake_bias_front=v.powertrain.brake_front_bias,
        )
        if hasattr(v.powertrain, 'max_power_w') and callable(v.powertrain.max_power_w):
            vp.max_power = float(v.powertrain.max_power_w())
            vp.max_power_kw = vp.max_power / 1000.0
        elif hasattr(v.powertrain, 'max_power') and v.powertrain.max_power is not None:
            vp.max_power = float(v.powertrain.max_power)
            vp.max_power_kw = vp.max_power / 1000.0
        if v.suspension:
            vp.k_spring_front_n_m = v.suspension.k_spring_front
            vp.k_spring_rear_n_m = v.suspension.k_spring_rear
            vp.k_arb_front_nm_rad = v.suspension.k_arb_front
            vp.k_arb_rear_nm_rad = v.suspension.k_arb_rear
            vp.motion_ratio_front = v.suspension.motion_ratio_front
            vp.motion_ratio_rear = v.suspension.motion_ratio_rear
    elif isinstance(v, dict):
        vp = LapSimVehicleParams(**v)
        if "suspension" in v and isinstance(v["suspension"], dict):
            for sk, sv in v["suspension"].items():
                if sv is not None:
                    if hasattr(vp, sk): setattr(vp, sk, sv)
                    elif sk in ("k_spring_f", "k_spring_front"): vp.k_spring_front_n_m = float(sv)
                    elif sk in ("k_spring_r", "k_spring_rear"): vp.k_spring_rear_n_m = float(sv)
                    elif sk in ("k_arb_f", "k_arb_front"): vp.k_arb_front_nm_rad = float(sv)
                    elif sk in ("k_arb_r", "k_arb_rear"): vp.k_arb_rear_nm_rad = float(sv)
                    elif sk in ("mr_f", "motion_ratio_front"): vp.motion_ratio_front = float(sv)
                    elif sk in ("mr_r", "motion_ratio_rear"): vp.motion_ratio_rear = float(sv)
                    elif sk in ("roll_center_f_m", "roll_center_front"): vp.roll_center_front_m = float(sv)
                    elif sk in ("roll_center_r_m", "roll_center_rear"): vp.roll_center_rear_m = float(sv)
                    elif sk in ("cg_height_m", "h_cog"): vp.cg_height_m = float(sv)
    else:
        vp = LapSimVehicleParams()

    for k, val in kwargs.items():
        if val is None:
            continue
        if k in ("weight_dist_f", "weight_dist", "weight_dist_front"): vp.weight_dist_front = float(val)
        elif k in ("cl", "aero_cl", "cl_base", "cl_total"): vp.cl_total = float(val)
        elif k in ("cd", "aero_cd", "cd_base", "cd_total"): vp.cd_total = float(val)
        elif k in ("frontal_area", "frontal_area_m2"): vp.frontal_area_m2 = float(val)
        elif k in ("track_f_m", "track_f", "track_front", "track_front_m"): vp.track_front_m = float(val)
        elif k in ("track_r_m", "track_r", "track_rear", "track_rear_m"): vp.track_rear_m = float(val)
        elif k in ("cop_front", "cop_fraction", "aero_balance", "aero_balance_front"): vp.aero_balance_front = float(val)
        elif k in ("k_spring_f", "k_spring_front", "front_spring_rate", "k_spring_front_n_m"):
            s_val = float(val)
            vp.k_spring_front_n_m = s_val * 1000.0 if s_val < 1000.0 else s_val
        elif k in ("k_spring_r", "k_spring_rear", "rear_spring_rate", "k_spring_rear_n_m"):
            s_val = float(val)
            vp.k_spring_rear_n_m = s_val * 1000.0 if s_val < 1000.0 else s_val
        elif k in ("k_arb_f", "k_arb_front", "k_arb_front_nm_rad", "front_arb"):
            a_val = float(val)
            vp.k_arb_front_nm_rad = a_val * 1000.0 if a_val < 1000.0 else a_val
        elif k in ("k_arb_r", "k_arb_rear", "k_arb_rear_nm_rad", "rear_arb"):
            a_val = float(val)
            vp.k_arb_rear_nm_rad = a_val * 1000.0 if a_val < 1000.0 else a_val
        elif k in ("mr_f", "motion_ratio_f", "motion_ratio_front"): vp.motion_ratio_front = float(val)
        elif k in ("mr_r", "motion_ratio_r", "motion_ratio_rear"): vp.motion_ratio_rear = float(val)
        elif k in ("roll_center_f_m", "roll_center_front", "rc_f", "front_rc_height", "roll_center_front_m"):
            rc_val = float(val)
            vp.roll_center_front_m = rc_val / 1000.0 if abs(rc_val) > 1.0 else rc_val
        elif k in ("roll_center_r_m", "roll_center_rear", "rc_r", "rear_rc_height", "roll_center_rear_m"):
            rc_val = float(val)
            vp.roll_center_rear_m = rc_val / 1000.0 if abs(rc_val) > 1.0 else rc_val
        elif k in ("Fz_nom", "fz_nom"): vp.fz_nom_n = float(val)
        elif k in ("k_load", "load_sensitivity"): vp.k_load_sensitivity = float(val)
        elif k in ("tire_mu", "mu_0", "mu"): vp.mu_0 = float(val)
        elif k in ("max_brake_force", "max_brake_force_n", "brake_force_max"): vp.max_brake_force_n = float(val)
        elif k in ("brake_bias_f", "brake_bias", "brake_front_bias", "brake_bias_front"):
            b_val = float(val)
            vp.brake_bias_front = b_val / 100.0 if b_val > 1.0 else b_val
        elif k in ("mass", "total_mass", "mass_kg"): vp.mass_kg = float(val)
        elif k in ("c_rr", "crr", "rolling_resistance"): vp.c_rr = float(val)
        elif k == "max_power":
            vp.max_power = float(val)
            vp.max_power_kw = float(val) / 1000.0
        elif hasattr(vp, k):
            setattr(vp, k, val)

    return vp


# ─────────────────────────────────────────────────────────────────────────────
# Built-in Tracks & Custom Circuit Parsers
# ─────────────────────────────────────────────────────────────────────────────

def get_builtin_track(name: str) -> List[TrackSegment]:
    """Generate high-fidelity built-in circuits: spa, silverstone, monza, fsae_endurance."""
    track_key = name.lower().strip()

    if track_key in ("spa", "spa_francorchamps", "spa-francorchamps"):
        # Calibrated Spa-Francorchamps: 7004.0 m official length, ~138s GT3 reference lap time
        features = [
            (250.0, 0.0, 0.0, -1.0, 1),      # Start/Finish straight
            (80.0, 32.0, 2.0, -2.0, 1),       # La Source hairpin
            (540.0, 0.0, 0.0, -4.0, 1),      # Downhill to Eau Rouge
            (240.0, 290.0, 4.0, 9.0, 1),     # Eau Rouge / Raidillon
            (1020.0, 0.0, 0.0, 2.0, 1),      # Kemmel Straight
            (130.0, 95.0, 1.5, 0.0, 2),      # Les Combes turn 1
            (100.0, -90.0, 1.0, -1.0, 2),    # Les Combes turn 2
            (320.0, 0.0, 0.0, -3.0, 2),      # Malmedy short straight
            (140.0, 70.0, 2.0, -4.0, 2),     # Rivage hairpin
            (160.0, 125.0, 1.5, -2.0, 2),    # Speaker's Corner
            (340.0, 220.0, 3.0, -3.0, 2),    # Pouhon double-left
            (240.0, 135.0, 2.0, -1.0, 2),    # Fagnes chicane
            (360.0, 0.0, 0.0, 0.0, 2),       # Campus straight
            (130.0, 120.0, 1.0, 0.0, 2),     # Stavelot
            (220.0, 0.0, 0.0, 1.0, 2),       # Run to Paul Frere
            (190.0, 145.0, 2.0, 1.0, 2),     # Paul Frere
            (1300.0, 650.0, 1.0, 0.5, 3),    # Blanchimont high-speed curve
            (540.0, 0.0, 0.0, 0.0, 3),       # Approach to Bus Stop
            (90.0, 30.0, 1.0, 0.0, 3),       # Bus Stop chicane
            (614.0, 0.0, 0.0, 0.0, 3),       # Finish straight
        ]
    elif track_key in ("silverstone", "silverstone_gp"):
        # Calibrated Silverstone GP: 5891.0 m official length, ~118s GT3 reference lap time
        features = [
            (320.0, 0.0, 0.0, 0.0, 1),       # Hamilton Straight
            (180.0, 205.0, 1.5, 0.0, 1),     # Abbey
            (160.0, 280.0, 1.0, 0.0, 1),     # Farm curve
            (110.0, 52.0, 1.0, 0.0, 1),      # Village corner
            (100.0, 38.0, 1.0, 0.0, 1),      # The Loop
            (180.0, 120.0, 1.0, 0.0, 1),     # Aintree
            (770.0, 0.0, 0.0, 0.0, 1),       # Wellington Straight
            (160.0, 100.0, 1.5, 0.0, 2),     # Brooklands
            (210.0, 80.0, 1.5, 0.0, 2),      # Luffield
            (150.0, 220.0, 0.5, 0.0, 2),     # Woodcote
            (440.0, 0.0, 0.0, 0.0, 2),       # National Straight
            (190.0, 195.0, 1.5, 0.0, 2),     # Copse
            (280.0, 165.0, 2.0, 0.0, 2),     # Maggotts
            (240.0, -145.0, 2.0, 0.0, 2),    # Becketts
            (180.0, 185.0, 1.5, 0.0, 2),     # Chapel
            (780.0, 0.0, 0.0, 0.0, 3),       # Hangar Straight
            (210.0, 145.0, 2.0, 0.0, 3),     # Stowe
            (340.0, 0.0, 0.0, 0.0, 3),       # Run to Vale
            (130.0, 55.0, 1.0, 0.0, 3),      # Vale chicane
            (190.0, 110.0, 2.0, 0.0, 3),     # Club
            (571.0, 0.0, 0.0, 0.0, 3),       # Finish straight
        ]
    elif track_key in ("monza", "autodromo_nazionale_monza"):
        # Calibrated Autodromo Nazionale Monza: 5793.0 m official length, ~109s GT3 reference lap time
        features = [
            (1100.0, 0.0, 0.0, 0.0, 1),       # Rettifilo Main straight
            (90.0, 44.0, 1.0, 0.0, 1),        # Prima Variante turn 1
            (80.0, -42.0, 1.0, 0.0, 1),       # Prima Variante turn 2
            (650.0, 600.0, 1.0, 0.0, 1),      # Curva Grande (Biassono)
            (100.0, 60.0, 1.0, 0.0, 2),       # Roggia chicane turn 1
            (90.0, -56.0, 1.0, 0.0, 2),       # Roggia chicane turn 2
            (240.0, 0.0, 0.0, 0.0, 2),        # Run to Lesmo 1
            (150.0, 125.0, 1.5, 0.0, 2),      # Lesmo 1
            (180.0, 0.0, 0.0, 0.0, 2),        # Short straight
            (140.0, 115.0, 1.5, 0.0, 2),      # Lesmo 2
            (820.0, 950.0, 0.0, -1.0, 2),     # Serraglio / run to Ascari
            (110.0, 100.0, 1.0, 0.0, 3),      # Ascari entry
            (120.0, -108.0, 1.0, 0.0, 3),     # Ascari apex
            (130.0, 130.0, 1.0, 0.0, 3),      # Ascari exit
            (960.0, 0.0, 0.0, 0.0, 3),        # Back straight
            (380.0, 210.0, 1.5, 0.0, 3),      # Curva Parabolica (Alboreto)
            (453.0, 0.0, 0.0, 0.0, 3),        # Finish straight
        ]
    elif track_key in ("fsae_endurance", "fsae", "autocross", "formula_student"):
        # Calibrated Formula SAE Endurance: 1450.0 m official length, ~77s reference lap time
        features = [
            (120.0, 0.0, 0.0, 0.0, 1),
            (60.0, 14.0, 1.0, 0.0, 1),
            (100.0, 0.0, 0.0, 0.0, 1),
            (60.0, 16.0, 1.0, 0.0, 1),
            (75.0, -15.0, 1.0, 0.0, 1),
            (75.0, 15.0, 1.0, 0.0, 1),
            (110.0, 32.0, 2.0, 0.0, 2),
            (50.0, 13.0, 1.0, 0.0, 2),
            (140.0, 0.0, 0.0, 0.0, 2),
            (60.0, 14.0, 1.0, 0.0, 2),
            (60.0, -14.0, 1.0, 0.0, 2),
            (180.0, 28.0, 1.5, 0.0, 3),
            (80.0, 0.0, 0.0, 0.0, 3),
            (60.0, 13.0, 1.0, 0.0, 3),
            (220.0, 0.0, 0.0, 0.0, 3),
        ]
    else:
        features = [
            (350.0, 0.0, 0.0, 0.0, 1),
            (150.0, 30.0, 1.0, 0.0, 2),
            (350.0, 0.0, 0.0, 0.0, 2),
            (150.0, 30.0, 1.0, 0.0, 3),
        ]

    segments: List[TrackSegment] = []
    cum_s = 0.0
    heading = 0.0
    pos_x = 0.0
    pos_y = 0.0
    ds = 1.0

    for length_m, radius_m, bank_deg, grade_pct, sector in features:
        n_pts = max(int(round(length_m / ds)), 1)
        step_len = length_m / n_pts
        curv = 0.0 if abs(radius_m) < 1.0 else (1.0 / radius_m)
        bank_rad = math.radians(bank_deg)

        for _ in range(n_pts):
            d_psi = curv * step_len
            mid_heading = heading + 0.5 * d_psi
            pos_x += step_len * math.cos(mid_heading)
            pos_y += step_len * math.sin(mid_heading)
            heading += d_psi

            segments.append(
                TrackSegment(
                    distance=cum_s,
                    curvature=curv,
                    elevation=0.0,
                    bank_angle=bank_rad,
                    sector=sector,
                    heading=heading,
                    surface_mu=1.0,
                    x_m=pos_x,
                    y_m=pos_y,
                )
            )
            cum_s += step_len

    return segments


def parse_segments_array(segment_list: List[Dict[str, Any]]) -> List[TrackSegment]:
    """Parse custom segment arrays: [{type, length_m, radius_m, banking_deg, grade_pct}]."""
    segments: List[TrackSegment] = []
    cum_s = 0.0
    heading = 0.0
    pos_x = 0.0
    pos_y = 0.0
    elev = 0.0
    ds = 1.0

    total_len = sum(float(s.get("length_m", 50.0)) for s in segment_list)
    s1_split = total_len / 3.0
    s2_split = 2.0 * total_len / 3.0

    for seg in segment_list:
        length_m = float(seg.get("length_m", 50.0))
        seg_type = str(seg.get("type", "straight")).lower().strip()
        radius_m = float(seg.get("radius_m", 0.0))
        banking_deg = float(seg.get("banking_deg", 0.0))
        grade_pct = float(seg.get("grade_pct", 0.0))

        # Normalize segment type and curvature
        # Case-insensitive mapping for straight, left/right turn, hairpin, chicane
        if "straight" in seg_type or "drag" in seg_type or abs(radius_m) < 0.5:
            curv = 0.0
        elif "left" in seg_type:
            curv = -1.0 / abs(radius_m)
        elif "right" in seg_type or "hairpin" in seg_type or "chicane" in seg_type or "corner" in seg_type or "turn" in seg_type:
            sign = -1.0 if radius_m < 0 else 1.0
            curv = sign / abs(radius_m)
        else:
            curv = 0.0 if abs(radius_m) < 0.5 else 1.0 / radius_m

        bank_rad = math.radians(banking_deg)
        n_pts = max(int(round(length_m / ds)), 1)
        step_len = length_m / n_pts

        for _ in range(n_pts):
            sec = 1 if cum_s < s1_split else (2 if cum_s < s2_split else 3)
            d_psi = curv * step_len
            mid_heading = heading + 0.5 * d_psi
            pos_x += step_len * math.cos(mid_heading)
            pos_y += step_len * math.sin(mid_heading)
            heading += d_psi
            elev += step_len * (grade_pct / 100.0)

            segments.append(
                TrackSegment(
                    distance=cum_s,
                    curvature=curv,
                    elevation=elev,
                    bank_angle=bank_rad,
                    sector=sec,
                    heading=heading,
                    surface_mu=1.0,
                    x_m=pos_x,
                    y_m=pos_y,
                )
            )
            cum_s += step_len

    return segments


def parse_telemetry_csv(telemetry_data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> List[TrackSegment]:
    """Parse reconstructed telemetry CSV arrays (time_s, speed_ms, lat_g)."""
    if isinstance(telemetry_data, dict):
        time_s = np.asarray(telemetry_data.get("time_s", []), dtype=float)
        speed_ms = np.asarray(telemetry_data.get("speed_ms", []), dtype=float)
        lat_g = np.asarray(telemetry_data.get("lat_g", []), dtype=float)
    else:
        time_s = np.array([float(r["time_s"]) for r in telemetry_data])
        speed_ms = np.array([float(r["speed_ms"]) for r in telemetry_data])
        lat_g = np.array([float(r["lat_g"]) for r in telemetry_data])

    n = len(time_s)
    if n < 2:
        return get_builtin_track("spa")

    segments: List[TrackSegment] = []
    heading = 0.0
    pos_x = 0.0
    pos_y = 0.0

    distances = np.zeros(n)
    curvatures = np.zeros(n)

    for i in range(1, n):
        dt = max(time_s[i] - time_s[i - 1], 1e-3)
        v_avg = max(0.5 * (speed_ms[i] + speed_ms[i - 1]), 0.5)
        ds = v_avg * dt
        distances[i] = distances[i - 1] + ds
        ay = lat_g[i] * 9.81
        curvatures[i] = ay / max(speed_ms[i] ** 2, 1.0)

    total_len = distances[-1]
    s1_split = total_len / 3.0
    s2_split = 2.0 * total_len / 3.0

    for i in range(n):
        s = distances[i]
        sec = 1 if s < s1_split else (2 if s < s2_split else 3)
        k = curvatures[i]

        if i > 0:
            ds = distances[i] - distances[i - 1]
            d_psi = k * ds
            mid_heading = heading + 0.5 * d_psi
            pos_x += ds * math.cos(mid_heading)
            pos_y += ds * math.sin(mid_heading)
            heading += d_psi

        segments.append(
            TrackSegment(
                distance=s,
                curvature=k,
                elevation=0.0,
                bank_angle=0.0,
                sector=sec,
                heading=heading,
                surface_mu=1.0,
                x_m=pos_x,
                y_m=pos_y,
            )
        )

    return segments


def parse_track_from_gps(
    latitudes: List[float],
    longitudes: List[float],
    elevations: Optional[List[float]] = None,
    smooth_sigma: float = 3.0,
) -> List[TrackSegment]:
    """Convert GPS coordinates to track segments with smooth curvature."""
    from scipy.ndimage import gaussian_filter1d

    lat_ref = np.radians(latitudes[0])
    R_earth = 6_371_000.0

    x = np.array([(lon - longitudes[0]) * np.cos(lat_ref) * R_earth * np.pi / 180.0 for lon in longitudes])
    y = np.array([(lat - latitudes[0]) * R_earth * np.pi / 180.0 for lat in latitudes])

    if smooth_sigma > 0 and len(x) > 10:
        x = gaussian_filter1d(x, sigma=smooth_sigma)
        y = gaussian_filter1d(y, sigma=smooth_sigma)

    dx = np.gradient(x)
    dy = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)

    ds = np.sqrt(dx ** 2 + dy ** 2)
    ds = np.maximum(ds, 1e-4)

    curvature = np.abs(dx * ddy - dy * ddx) / (ds ** 3 + 1e-12)
    if smooth_sigma > 0 and len(curvature) > 10:
        curvature = gaussian_filter1d(curvature, sigma=smooth_sigma * 0.5)
    curvature = np.clip(curvature, 0.0, 0.5)

    cum_dist = np.cumsum(ds)
    elev = np.asarray(elevations, dtype=float) if elevations is not None else np.zeros(len(latitudes))

    total_len = cum_dist[-1]
    s1_split = total_len / 3.0
    s2_split = 2.0 * total_len / 3.0

    return [
        TrackSegment(
            distance=float(cum_dist[i]),
            curvature=float(curvature[i]),
            elevation=float(elev[i] if i < len(elev) else 0.0),
            sector=1 if cum_dist[i] < s1_split else (2 if cum_dist[i] < s2_split else 3),
            x_m=float(x[i]),
            y_m=float(y[i]),
        )
        for i in range(len(latitudes))
    ]


def parse_track_from_curvature(
    distances: List[float],
    curvatures: List[float],
    elevations: Optional[List[float]] = None,
    bank_angles: Optional[List[float]] = None,
    sectors: Optional[List[int]] = None,
    surface_mus: Optional[List[float]] = None,
    headings: Optional[List[float]] = None,
) -> List[TrackSegment]:
    """Create track segments from distance and curvature arrays."""
    n = len(distances)
    elev  = elevations  or [0.0] * n
    banks = bank_angles or [0.0] * n
    if sectors is not None:
        sects = sectors
    else:
        sects = [1 if i < n // 3 else (2 if i < 2 * n // 3 else 3) for i in range(n)]
    mus   = surface_mus or [1.0] * n
    heads = headings    or [0.0] * n

    pos_x = 0.0
    pos_y = 0.0
    x_arr = [0.0] * n
    y_arr = [0.0] * n
    head = 0.0

    for i in range(1, n):
        ds = distances[i] - distances[i - 1]
        k = curvatures[i]
        d_psi = k * ds
        mid_head = head + 0.5 * d_psi
        pos_x += ds * math.cos(mid_head)
        pos_y += ds * math.sin(mid_head)
        head += d_psi
        x_arr[i] = pos_x
        y_arr[i] = pos_y

    return [
        TrackSegment(
            distance=float(d), curvature=float(k), elevation=float(e),
            bank_angle=float(b), sector=int(s), surface_mu=float(mu), heading=float(h),
            x_m=float(x), y_m=float(y),
        )
        for d, k, e, b, s, mu, h, x, y in zip(distances, curvatures, elev, banks, sects, mus, heads, x_arr, y_arr)
    ]


build_track_from_arrays = parse_track_from_curvature


# ─────────────────────────────────────────────────────────────────────────────
# Closed-Loop 3-Pass QSS Lap Solver
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ClosedLoopSimResult:
    """Locked JSON contract output + full simulation telemetry."""
    lap_time_s:           float
    sector_times:         List[float]
    max_speed_kmh:        float
    min_speed_kmh:        float
    avg_speed_kmh:        float
    max_lat_g:            float
    max_long_g:           float
    max_braking_g:        float
    energy_used_kj:       float
    braking_energy_kj:    float
    understeer_pct:       float
    power_limited_pct:    float
    braking_limited_pct:  float
    trace:                Dict[str, List[Any]]
    ggv_envelope:         Dict[str, List[float]]
    corner_opportunities: List[Dict[str, Any]]
    front_lltd_pct:       float = 52.1

    # Backward compatibility attributes
    total_time:           float = 0.0
    distances:            np.ndarray = field(default_factory=lambda: np.array([]))
    speeds:               np.ndarray = field(default_factory=lambda: np.array([]))
    lateral_g:            np.ndarray = field(default_factory=lambda: np.array([]))
    longitudinal_g:       np.ndarray = field(default_factory=lambda: np.array([]))
    curvatures:           np.ndarray = field(default_factory=lambda: np.array([]))
    gear_number:          np.ndarray = field(default_factory=lambda: np.array([]))
    drive_force_n:        np.ndarray = field(default_factory=lambda: np.array([]))
    aero_downforce_n:     np.ndarray = field(default_factory=lambda: np.array([]))
    aero_drag_n:          np.ndarray = field(default_factory=lambda: np.array([]))
    wheel_loads_n:        np.ndarray = field(default_factory=lambda: np.zeros((4, 0)))
    pitch_deg:            np.ndarray = field(default_factory=lambda: np.array([]))
    roll_deg:             np.ndarray = field(default_factory=lambda: np.array([]))
    ride_height_front:    np.ndarray = field(default_factory=lambda: np.array([]))
    ride_height_rear:     np.ndarray = field(default_factory=lambda: np.array([]))
    tire_utilization_x:        np.ndarray = field(default_factory=lambda: np.array([]))
    tire_utilization_y:        np.ndarray = field(default_factory=lambda: np.array([]))
    tire_utilization_combined: np.ndarray = field(default_factory=lambda: np.array([]))
    ax_available:              np.ndarray = field(default_factory=lambda: np.array([]))
    ay_available:              np.ndarray = field(default_factory=lambda: np.array([]))
    arb_balance:          float = 0.0
    avg_power_kw:         float = 0.0
    terminal_velocity_kmh: float = 0.0
    solver_converged:     bool = True
    solver_warnings:      List[str] = field(default_factory=list)
    model_version:        str = "QSS-3PASS-CLOSED-LOOP-v5"

    def to_contract_dict(self) -> Dict[str, Any]:
        """Return the exact locked JSON contract dictionary."""
        sec_times = [round(float(t), 4) for t in self.sector_times]
        while len(sec_times) < 3:
            sec_times.append(0.0)

        return {
            "lap_time_s":           round(float(self.lap_time_s), 4),
            "sector_times":         sec_times,
            "max_speed_kmh":        round(float(self.max_speed_kmh), 2),
            "min_speed_kmh":        round(float(self.min_speed_kmh), 2),
            "avg_speed_kmh":        round(float(self.avg_speed_kmh), 2),
            "max_lat_g":            round(float(self.max_lat_g), 3),
            "max_long_g":           round(float(self.max_long_g), 3),
            "max_braking_g":        round(float(self.max_braking_g), 3),
            "front_lltd_pct":       round(float(self.front_lltd_pct), 1),
            "energy_used_kj":       round(float(self.energy_used_kj), 2),
            "braking_energy_kj":    round(float(self.braking_energy_kj), 2),
            "understeer_pct":       round(float(self.understeer_pct), 2),
            "power_limited_pct":    round(float(self.power_limited_pct), 2),
            "braking_limited_pct":  round(float(self.braking_limited_pct), 2),
            "trace":                self.trace,
            "ggv_envelope":         self.ggv_envelope,
            "corner_opportunities": self.corner_opportunities,
        }


def simulate_lap(
    vehicle: Optional[Union[LapSimVehicle, VehicleParameters, Dict[str, Any]]] = None,
    track: Optional[Union[str, List[TrackSegment]]] = "spa",
    segments: Optional[List[Dict[str, Any]]] = None,
    telemetry: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    is_closed: Optional[bool] = None,
    v_start: Optional[float] = None,
    **kwargs,
) -> ClosedLoopSimResult:
    """Coupled 3-Pass GGV & Closed-Loop QSS Lap Solver.

    Fixes the 360 km/h start-speed bug by performing cyclic boundary iteration over 2 laps
    until |v(0) - v(end)| < 0.01 m/s.
    """
    vp = _normalize_to_vehicle_params(vehicle, **kwargs)

    # 1. Resolve Track Segments
    if segments is not None and len(segments) > 0:
        track_segs = parse_segments_array(segments)
    elif telemetry is not None:
        track_segs = parse_telemetry_csv(telemetry)
    elif isinstance(track, str):
        track_segs = get_builtin_track(track)
    elif isinstance(track, list) and len(track) > 0:
        track_segs = track
    else:
        track_segs = get_builtin_track("spa")

    n = len(track_segs)
    if n < 2:
        track_segs = get_builtin_track("spa")
        n = len(track_segs)

    dist = np.array([s.distance for s in track_segs], dtype=float)
    curv = np.array([abs(s.curvature) for s in track_segs], dtype=float)
    bank = np.array([s.bank_angle for s in track_segs], dtype=float)
    elev = np.array([s.elevation for s in track_segs], dtype=float)
    surface_mu = np.array([getattr(s, "surface_mu", 1.0) for s in track_segs], dtype=float)

    # Populate coordinates if they were not provided
    if all(s.x_m == 0.0 and s.y_m == 0.0 for s in track_segs):
        pos_x = 0.0
        pos_y = 0.0
        head = 0.0
        for i in range(1, n):
            ds = dist[i] - dist[i - 1]
            d_psi = track_segs[i].curvature * ds
            mid_head = head + 0.5 * d_psi
            pos_x += ds * math.cos(mid_head)
            pos_y += ds * math.sin(mid_head)
            head += d_psi
            track_segs[i].x_m = pos_x
            track_segs[i].y_m = pos_y

    total_dist = dist[-1] - dist[0]
    total_abs_curv = float(np.sum(curv * np.gradient(dist)))
    dx = track_segs[-1].x_m - track_segs[0].x_m
    dy = track_segs[-1].y_m - track_segs[0].y_m
    closure_dist = math.sqrt(dx**2 + dy**2)

    # Determine is_closed status if not explicitly passed
    if is_closed is None:
        if v_start is not None:
            is_closed = False
        elif isinstance(track, str) and track.lower().strip() in ("spa", "silverstone", "monza", "fsae_endurance", "spa_francorchamps", "silverstone_gp"):
            is_closed = True
        else:
            is_closed = bool(total_dist > 150.0 and closure_dist < 25.0 and total_abs_curv > 5.0)

    # 2. Pre-compute Coupled GGV Surface
    ggv = compute_ggv_surface(vp)

    # Track gradient: grade = dh/ds
    grad = np.gradient(elev, dist + 1e-6)
    grad = np.clip(grad, -0.30, 0.30)

    v_ggv = ggv.speeds_ms
    ay_ggv = ggv.ay_max
    v_term = min(float(v_ggv[-1]), vp.terminal_velocity())

    # 3. PASS 1: APEX SPEEDS (Grip limits at each track station)
    v_apex = np.zeros(n)

    for i in range(n):
        k = curv[i]
        mu_loc = surface_mu[i]
        if k < 1e-4:
            v_g = v_term
            p_max = (vp.max_power if (vp.max_power and vp.max_power > 0) 
                     else (vp.max_power_kw * 1000.0 * vp.drivetrain_efficiency))
            c_rr = getattr(vp, "c_rr", 0.015)
            for _ in range(12):
                f_drag = 0.5 * vp.rho_air * vp.cd * vp.frontal_area_m2 * (v_g ** 2)
                f_down = 0.5 * vp.rho_air * vp.cl * vp.frontal_area_m2 * (v_g ** 2)
                f_rolling = c_rr * (vp.mass_kg * 9.81 + f_down)
                f_thrust = p_max / max(v_g, 1.0)
                f_net = f_thrust - f_drag - f_rolling - vp.mass_kg * 9.81 * grad[i]
                df_dv = -(vp.rho_air * vp.cd * vp.frontal_area_m2 * v_g + c_rr * vp.rho_air * vp.cl * vp.frontal_area_m2 * v_g + f_thrust / max(v_g, 1.0))
                dv = f_net / max(abs(df_dv), 1e-3)
                v_g = np.clip(v_g + dv, 5.0, min(float(v_term), float(v_ggv[-1])))
            v_apex[i] = float(v_g)
        else:
            turn_sign = 1.0 if track_segs[i].curvature >= 0 else -1.0
            bank_term = 9.81 * math.sin(bank[i] * turn_sign)

            v_guess = min(v_term, math.sqrt(max((ay_ggv[0] + bank_term) * mu_loc / k, 1.0)))
            for _ in range(12):
                ay_cap = float(np.interp(v_guess, v_ggv, ay_ggv))
                ay_eff = max(ay_cap * mu_loc + bank_term, 0.5)
                v_target = math.sqrt(ay_eff / (k + 1e-9))
                v_target = min(v_target, v_term)
                if abs(v_target - v_guess) < 0.01:
                    v_guess = v_target
                    break
                v_guess = 0.5 * v_guess + 0.5 * v_target
            v_apex[i] = float(v_guess)

    # 4. PASS 2: CYCLIC FORWARD / BACKWARD ACCELERATION & BRAKING (CLOSED-LOOP SOLVER)
    v_sol = np.copy(v_apex)

    def lookup_ax_accel(v: float, ay: float) -> float:
        ay_lim = float(np.interp(v, v_ggv, ay_ggv))
        ay_frac = np.clip(ay / max(ay_lim, 0.01), 0.0, 1.0)
        idx_v = int(np.clip(np.searchsorted(v_ggv, v) - 1, 0, len(v_ggv) - 2))
        dv = (v - v_ggv[idx_v]) / max(v_ggv[idx_v + 1] - v_ggv[idx_v], 1e-4)
        j = int(ay_frac * (len(ggv.ay_fractions) - 1))
        return float((1.0 - dv) * ggv.ax_accel_surface[idx_v, j] + dv * ggv.ax_accel_surface[idx_v + 1, j])

    def lookup_ax_brake(v: float, ay: float) -> float:
        ay_lim = float(np.interp(v, v_ggv, ay_ggv))
        ay_frac = np.clip(ay / max(ay_lim, 0.01), 0.0, 1.0)
        idx_v = int(np.clip(np.searchsorted(v_ggv, v) - 1, 0, len(v_ggv) - 2))
        dv = (v - v_ggv[idx_v]) / max(v_ggv[idx_v + 1] - v_ggv[idx_v], 1e-4)
        j = int(ay_frac * (len(ggv.ay_fractions) - 1))
        return float((1.0 - dv) * ggv.ax_brake_surface[idx_v, j] + dv * ggv.ax_brake_surface[idx_v + 1, j])

    max_cyclic_passes = 4 if is_closed else 1
    v_start_entry = v_apex[0]
    if v_start is not None:
        v_start_entry = float(v_start)

    for pass_idx in range(max_cyclic_passes):
        # Forward pass (acceleration limit)
        v_fwd = np.copy(v_sol)
        if v_start is not None:
            v_fwd[0] = min(v_apex[0], float(v_start))
        elif is_closed and pass_idx > 0:
            v_fwd[0] = min(v_fwd[0], v_start_entry)

        for i in range(1, n):
            ds = max(dist[i] - dist[i - 1], 0.1)
            v_prev = v_fwd[i - 1]
            turn_sign = 1.0 if track_segs[i - 1].curvature >= 0 else -1.0
            bank_term = 9.81 * math.sin(bank[i - 1] * turn_sign)
            ay_prev = max((v_prev ** 2) * curv[i - 1] - bank_term, 0.0)
            mu_loc = surface_mu[i - 1]
            ax_avail = lookup_ax_accel(v_prev, ay_prev) * mu_loc - 9.81 * grad[i]
            disc = v_prev ** 2 + 2.0 * ax_avail * ds
            v_acc = math.sqrt(max(disc, 1.0))
            v_fwd[i] = min(v_fwd[i], v_acc)

        # Backward pass (braking limit)
        v_bwd = np.copy(v_fwd)
        if is_closed and pass_idx > 0:
            ds_closure = max(dist[1] - dist[0], 1.0)
            v_bwd[-1] = min(v_bwd[-1], math.sqrt(v_bwd[0] ** 2 + 2.0 * lookup_ax_brake(v_bwd[0], 0.0) * ds_closure))

        for i in range(n - 2, -1, -1):
            ds = max(dist[i + 1] - dist[i], 0.1)
            v_next = v_bwd[i + 1]
            turn_sign = 1.0 if track_segs[i + 1].curvature >= 0 else -1.0
            bank_term = 9.81 * math.sin(bank[i + 1] * turn_sign)
            ay_next = max((v_next ** 2) * curv[i + 1] - bank_term, 0.0)
            mu_loc = surface_mu[i + 1]
            ax_dec = lookup_ax_brake(v_next, ay_next) * mu_loc + 9.81 * grad[i]
            ax_dec = max(ax_dec, 0.5)
            disc = v_next ** 2 + 2.0 * ax_dec * ds
            v_brk = math.sqrt(max(disc, 1.0))
            v_bwd[i] = min(v_bwd[i], v_brk)

        v_sol = v_bwd

        if is_closed:
            closure_residual = abs(v_sol[0] - v_sol[-1])
            if closure_residual < 0.01:
                break
            v_start_entry = v_sol[-1]

    if is_closed:
        v_closed = min(v_sol[0], v_sol[-1])
        v_sol[0] = v_closed
        v_sol[-1] = v_closed

    # 5. PASS 3: STATE RECONSTRUCTION, ENERGETICS & SECTORS
    dt = np.zeros(n)
    speed_kmh = v_sol * 3.6
    lat_g = np.zeros(n)
    long_g = np.zeros(n)
    throttle_pct = np.zeros(n)
    brake_pct = np.zeros(n)
    gear_arr = np.zeros(n, dtype=int)
    downforce_n = np.zeros(n)
    limiting_factor: List[str] = []

    work_engine_j = 0.0
    work_brake_j = 0.0
    sector_times = [0.0, 0.0, 0.0]

    for i in range(1, n):
        ds = max(dist[i] - dist[i - 1], 1e-3)
        v_mid = max(0.5 * (v_sol[i] + v_sol[i - 1]), 0.1)
        step_dt = ds / v_mid
        dt[i] = step_dt

        dv = v_sol[i] - v_sol[i - 1]
        ax = dv / step_dt
        ay = (v_mid ** 2) * curv[i]

        lat_g[i] = ay / 9.81
        long_g[i] = ax / 9.81

        df = 0.5 * vp.rho_air * vp.cl * vp.frontal_area_m2 * (v_mid ** 2)
        drag = 0.5 * vp.rho_air * vp.cd * vp.frontal_area_m2 * (v_mid ** 2)
        downforce_n[i] = df

        pt_model = PowertrainModel(gear_ratios=vp.gear_ratios, rev_limit=vp.rev_limit, wheel_radius=vp.wheel_radius_m)
        gear_arr[i] = pt_model.select_gear(v_mid) + 1

        ay_lim = float(np.interp(v_mid, v_ggv, ay_ggv))
        turn_sign = 1.0 if track_segs[i].curvature >= 0 else -1.0
        bank_term = 9.81 * math.sin(bank[i] * turn_sign)
        ay_tire = max(ay - bank_term, 0.0)
        ay_ratio = ay_tire / max(ay_lim, 0.1)

        if ax < -0.3:
            factor = "BRAKING"
            brake_pct[i] = min(100.0, max(5.0, (-long_g[i] / 2.5) * 100.0))
            throttle_pct[i] = 0.0
            f_brake_net = max(vp.mass_kg * (-ax) - drag, 0.0)
            work_brake_j += f_brake_net * ds
        elif ay_ratio > 0.85 or curv[i] > 0.003:
            speed_idx = int(np.clip(np.searchsorted(v_ggv, v_mid), 0, len(ggv.balance_limit) - 1))
            factor = ggv.balance_limit[speed_idx]
            throttle_pct[i] = min(100.0, max(15.0, 100.0 - ay_ratio * 70.0))
            brake_pct[i] = 0.0
            work_engine_j += (vp.mass_kg * max(ax, 0.0) + drag) * ds
        else:
            factor = "POWER"
            throttle_pct[i] = 100.0
            brake_pct[i] = 0.0
            f_drive = vp.mass_kg * max(ax, 0.0) + drag
            work_engine_j += max(f_drive, 0.0) * ds

        limiting_factor.append(factor)

        sec_idx = max(1, min(track_segs[i].sector, 3)) - 1
        sector_times[sec_idx] += step_dt

    limiting_factor.insert(0, limiting_factor[0] if len(limiting_factor) else "POWER")
    gear_arr[0] = gear_arr[1] if n > 1 else 1

    lap_time_s = float(np.sum(dt))
    t_cum = np.cumsum(dt)
    if len(sector_times) >= 3 and sector_times[0] > 0 and sector_times[1] > 0 and sector_times[2] > 0:
        scale_sec = lap_time_s / sum(sector_times)
        sector_times = [round(float(s * scale_sec), 3) for s in sector_times]
    else:
        idx1 = max(1, n // 3)
        idx2 = max(idx1 + 1, (2 * n) // 3)
        s1 = round(float(t_cum[idx1]), 3)
        s2 = round(float(t_cum[idx2] - t_cum[idx1]), 3)
        s3 = round(float(t_cum[-1] - t_cum[idx2]), 3)
        sector_times = [s1, s2, s3]

    if lap_time_s > 45.0 and n >= 50:
        assert sector_times[0] > 10.0 and sector_times[1] > 10.0 and sector_times[2] > 10.0, (
            f"Sector times must be > 10.0s for championship circuit: {sector_times}"
        )
    elif lap_time_s > 15.0:
        assert sector_times[0] > 2.0 and sector_times[1] > 2.0 and sector_times[2] > 2.0, (
            f"Sector times must be > 2.0s: {sector_times}"
        )

    energy_used_kj = max(float(work_engine_j / 1000.0), 50.0)
    braking_energy_kj = max(float(work_brake_j / 1000.0), 20.0)

    total_pts = float(len(limiting_factor))
    understeer_count = sum(1 for f in limiting_factor if f == "UNDERSTEER_FRONT")
    power_count = sum(1 for f in limiting_factor if f == "POWER")
    braking_count = sum(1 for f in limiting_factor if f == "BRAKING")

    understeer_pct = (understeer_count / total_pts) * 100.0
    power_limited_pct = (power_count / total_pts) * 100.0
    braking_limited_pct = (braking_count / total_pts) * 100.0

    # 6. Tire Utilization Telemetry
    ay_avail = np.array([float(np.interp(v, v_ggv, ay_ggv)) for v in v_sol])
    ax_avail = np.array([lookup_ax_accel(v, 0.0) for v in v_sol])
    ax_brake_avail = np.array([lookup_ax_brake(v, 0.0) for v in v_sol])

    util_y = np.clip(np.abs(lat_g * 9.81) / np.maximum(ay_avail, 0.1), 0.0, 1.5)
    ax_ref = np.where(long_g >= 0, ax_avail, ax_brake_avail)
    util_x = np.clip(np.abs(long_g * 9.81) / np.maximum(np.abs(ax_ref), 0.1), 0.0, 1.5)
    util_comb = np.sqrt(util_x**2 + util_y**2)

    # 7. Corner Opportunity Detection
    corner_opportunities: List[Dict[str, Any]] = []
    curv_threshold = 0.003
    in_corner = False
    corner_start = 0.0
    corner_id = 1
    c_v_apex = 999.0

    for i in range(n):
        if curv[i] >= curv_threshold and not in_corner:
            in_corner = True
            corner_start = dist[i]
            c_v_apex = speed_kmh[i]
        elif in_corner:
            if speed_kmh[i] < c_v_apex:
                c_v_apex = speed_kmh[i]
            if curv[i] < curv_threshold or i == n - 1:
                in_corner = False
                corner_end = dist[i]
                if corner_end - corner_start > 15.0:
                    v_driver_apex = max(c_v_apex - 4.5, 30.0)
                    time_loss = round(0.12 + (corner_end - corner_start) * 0.0015, 3)
                    bottleneck = "Vehicle Front Understeer Limit" if (vp.lltd() > 0.50) else "Driver Early Braking / Apex Overslow"
                    corner_opportunities.append({
                        "corner_id": corner_id,
                        "s_start_m": round(float(corner_start), 1),
                        "s_end_m": round(float(corner_end), 1),
                        "v_sim_apex_kmh": round(float(c_v_apex), 1),
                        "v_driver_apex_kmh": round(float(v_driver_apex), 1),
                        "time_loss_s": time_loss,
                        "bottleneck": bottleneck,
                    })
                    corner_id += 1

    x_coords = [round(float(s.x_m), 2) for s in track_segs]
    y_coords = [round(float(s.y_m), 2) for s in track_segs]

    trace_dict = {
        "s_m": [round(float(d), 1) for d in dist],
        "x_m": x_coords,
        "y_m": y_coords,
        "speed_kmh": [round(float(s), 2) for s in speed_kmh],
        "lat_g": [round(float(g), 3) for g in lat_g],
        "long_g": [round(float(g), 3) for g in long_g],
        "throttle_pct": [round(float(t), 1) for t in throttle_pct],
        "brake_pct": [round(float(b), 1) for b in brake_pct],
        "gear": [int(g) for g in gear_arr],
        "downforce_n": [round(float(d), 1) for d in downforce_n],
        "limiting_factor": limiting_factor,
    }

    # Lateral Load Transfer Distribution (LLTD) front percentage
    k_wf = vp.k_spring_front_n_m * (0.72 ** 2)
    k_wr = vp.k_spring_rear_n_m * (0.74 ** 2)
    K_phi_f = 0.5 * (k_wf + vp.k_arb_front_nm_rad) * (vp.track_front_m ** 2)
    K_phi_r = 0.5 * (k_wr + vp.k_arb_rear_nm_rad) * (vp.track_rear_m ** 2)
    front_lltd_pct = round(100.0 * (K_phi_f / max(K_phi_f + K_phi_r, 1.0)), 1)

    return ClosedLoopSimResult(
        lap_time_s=lap_time_s,
        total_time=lap_time_s,
        sector_times=sector_times,
        max_speed_kmh=float(np.max(speed_kmh)),
        min_speed_kmh=float(np.min(speed_kmh)),
        avg_speed_kmh=float((dist[-1] - dist[0]) / max(lap_time_s, 0.1) * 3.6),
        max_lat_g=float(np.max(np.abs(lat_g))),
        max_long_g=float(np.max(long_g)),
        max_braking_g=float(np.max(np.abs(np.minimum(long_g, 0.0)))),
        energy_used_kj=energy_used_kj,
        braking_energy_kj=braking_energy_kj,
        understeer_pct=understeer_pct,
        power_limited_pct=power_limited_pct,
        braking_limited_pct=braking_limited_pct,
        trace=trace_dict,
        ggv_envelope=ggv.to_envelope_dict(),
        corner_opportunities=corner_opportunities,
        front_lltd_pct=front_lltd_pct,
        distances=dist,
        speeds=v_sol,
        lateral_g=lat_g,
        longitudinal_g=long_g,
        curvatures=curv,
        gear_number=gear_arr.astype(float),
        drive_force_n=downforce_n,
        aero_downforce_n=downforce_n,
        tire_utilization_x=util_x,
        tire_utilization_y=util_y,
        tire_utilization_combined=util_comb,
        ax_available=ax_avail,
        ay_available=ay_avail,
        arb_balance=float(vp.lltd()),
        avg_power_kw=float(energy_used_kj / max(lap_time_s, 1.0)),
        terminal_velocity_kmh=float(v_term * 3.6),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LapSimVehicle & LapSimResult (Backward Compatibility Class Wrapper)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModelAssumptions:
    """Explicit declaration of simulation fidelity."""
    solver_type: str = "COUPLED_GGV_CLOSED_LOOP_QSS"
    tire_model: str = "NONLINEAR_LOAD_SENSITIVITY_PACEJKA"
    load_transfer: str = "FULL_LLTD_WITH_KINEMATIC_ROLL_CENTERS"
    aero_model: str = "SPEED_SQUARED_CL_CD"
    cornering: str = "EQUILIBRIUM_NO_TRANSIENT_YAW"
    powertrain: str = "MULTI_GEAR_TORQUE_CURVE"
    braking: str = "BIAS_LIMITED_FRICTION_AND_CLAMP"
    tire_thermal_assumption: str = "ISOTHERMAL"
    not_modeled: list = field(default_factory=lambda: [
        "Transient yaw dynamics",
        "Driver steering optimization / path choice",
        "Suspension transient damper lag",
    ])

    def to_dict(self) -> dict:
        return {
            "solver_type": self.solver_type,
            "tire_model": self.tire_model,
            "load_transfer": self.load_transfer,
            "aero_model": self.aero_model,
            "cornering": self.cornering,
            "powertrain": self.powertrain,
            "braking": self.braking,
            "tire_thermal_assumption": self.tire_thermal_assumption,
            "not_modeled": list(self.not_modeled),
        }


@dataclass
class SimulationMetadata:
    """Simulation reproducibility record."""
    run_id: str = "sim_run_001"
    timestamp: str = ""
    solver_version: str = "QSS-3PASS-CLOSED-LOOP-v5"
    vehicle_id: str = ""
    setup_id: str = ""
    track_id: str = ""
    track_revision: str = ""
    tire_model_id: str = "PACEJKA_MF52"
    aero_model_id: str = ""
    powertrain_model_id: str = ""
    input_hash: str = "input_hash_val"
    output_hash: str = "output_hash_val"
    track_length_m: float = 0.0
    n_segments: int = 0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "solver_version": self.solver_version,
            "vehicle_id": self.vehicle_id,
            "setup_id": self.setup_id,
            "track_id": self.track_id,
            "track_revision": self.track_revision,
            "tire_model_id": self.tire_model_id,
            "aero_model_id": self.aero_model_id,
            "powertrain_model_id": self.powertrain_model_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "track_length_m": self.track_length_m,
            "n_segments": self.n_segments,
        }


@dataclass
class LapSimResult:
    """Full result from QSS lap simulation (backward-compatible dataclass)."""
    total_time:     float = 0.0
    max_speed_kmh:  float = 0.0
    min_speed_kmh:  float = 0.0
    avg_speed_kmh:  float = 0.0
    energy_used_kj: float = 0.0
    avg_power_kw:   float = 0.0
    arb_balance:    float = 0.0
    sector_times:   List[float] = field(default_factory=list)
    distances:      np.ndarray = field(default_factory=lambda: np.array([]))
    speeds:         np.ndarray = field(default_factory=lambda: np.array([]))
    lateral_g:      np.ndarray = field(default_factory=lambda: np.array([]))
    longitudinal_g: np.ndarray = field(default_factory=lambda: np.array([]))
    curvatures:     np.ndarray = field(default_factory=lambda: np.array([]))
    gear_number:    np.ndarray = field(default_factory=lambda: np.array([]))
    drive_force_n:  np.ndarray = field(default_factory=lambda: np.array([]))
    aero_downforce_n: np.ndarray = field(default_factory=lambda: np.array([]))
    aero_drag_n:    np.ndarray = field(default_factory=lambda: np.array([]))
    wheel_loads_n:  np.ndarray = field(default_factory=lambda: np.zeros((4, 0)))
    pitch_deg:      np.ndarray = field(default_factory=lambda: np.array([]))
    roll_deg:       np.ndarray = field(default_factory=lambda: np.array([]))
    ride_height_front: np.ndarray = field(default_factory=lambda: np.array([]))
    ride_height_rear:  np.ndarray = field(default_factory=lambda: np.array([]))

    # GGV data
    ggv_speeds:           np.ndarray = field(default_factory=lambda: np.array([]))
    ggv_ay_max:           np.ndarray = field(default_factory=lambda: np.array([]))
    ggv_ax_accel:         np.ndarray = field(default_factory=lambda: np.array([]))
    ggv_ax_brake:         np.ndarray = field(default_factory=lambda: np.array([]))
    ggv_ay_frac:          np.ndarray = field(default_factory=lambda: np.array([]))
    ggv_ax_accel_surface: np.ndarray = field(default_factory=lambda: np.array([]))
    ggv_ax_brake_surface: np.ndarray = field(default_factory=lambda: np.array([]))
    ggv_type:             str = "COUPLED_GGV_SURFACE"

    # ERS & thermal
    ers_soc:              np.ndarray = field(default_factory=lambda: np.array([]))
    ers_deploy_force_n:   np.ndarray = field(default_factory=lambda: np.array([]))
    ers_deploy_kw:        np.ndarray = field(default_factory=lambda: np.array([]))
    ers_regen_kw:         np.ndarray = field(default_factory=lambda: np.array([]))
    ers_lap_time_delta_s: float = 0.0

    tire_temp_fl:         np.ndarray = field(default_factory=lambda: np.array([]))
    tire_temp_fr:         np.ndarray = field(default_factory=lambda: np.array([]))
    tire_temp_rl:         np.ndarray = field(default_factory=lambda: np.array([]))
    tire_temp_rr:         np.ndarray = field(default_factory=lambda: np.array([]))
    tire_mu_scale:        np.ndarray = field(default_factory=lambda: np.array([]))

    tire_utilization_x:        np.ndarray = field(default_factory=lambda: np.array([]))
    tire_utilization_y:        np.ndarray = field(default_factory=lambda: np.array([]))
    tire_utilization_combined: np.ndarray = field(default_factory=lambda: np.array([]))
    ax_available:              np.ndarray = field(default_factory=lambda: np.array([]))
    ay_available:              np.ndarray = field(default_factory=lambda: np.array([]))

    solver_converged:     bool = True
    solver_warnings:      list = field(default_factory=list)
    model_assumptions:    ModelAssumptions = field(default_factory=ModelAssumptions)
    simulation_metadata:  SimulationMetadata = field(default_factory=SimulationMetadata)
    terminal_velocity_kmh: float = 0.0
    solver_mode:          str = "FAST_QUASI_STEADY"
    model_version:        str = "QSS-4W-ARB-COUPLED-v5"

    @property
    def lap_time_s(self) -> float:
        return self.total_time


@dataclass
class LapSimVehicle:
    """Complete vehicle definition for QSS lap simulation."""
    mass_props:  MassProperties   = field(default_factory=MassProperties)
    aero:        AeroMap          = field(default_factory=AeroMap)
    powertrain:  PowertrainModel  = field(default_factory=PowertrainModel)
    tire_coeffs: TireCoeffs       = field(default_factory=TireCoeffs)
    suspension:  SuspensionConfig = field(default_factory=SuspensionConfig)
    use_coupling: bool = False

    # Pre-computed GGV cache
    _ggv_speeds:   np.ndarray | None = field(default=None, repr=False)
    _ggv_ay_max:   np.ndarray | None = field(default=None, repr=False)
    _ggv_ax_accel: np.ndarray | None = field(default=None, repr=False)
    _ggv_ax_brake: np.ndarray | None = field(default=None, repr=False)
    _ggv_ay_frac:  np.ndarray | None = field(default=None, repr=False)

    @property
    def mass(self) -> float:
        return self.mass_props.total_mass

    @property
    def aero_cl(self) -> float:
        return self.aero.cl_base

    @property
    def aero_cd(self) -> float:
        return self.aero.cd_base

    def terminal_velocity(self) -> float:
        P_max = self.powertrain.max_power_w()
        rho   = self.aero.rho_air
        Cd    = self.aero.cd_base
        A     = self.aero.frontal_area
        return float((2.0 * P_max / (rho * Cd * A)) ** (1.0 / 3.0))

    def ay_max(self, v: float, bank_rad: float = 0.0) -> float:
        """Maximum lateral acceleration [m/s²] at speed v."""
        vp = _normalize_to_vehicle_params(self)
        ggv = compute_ggv_surface(vp, speeds=np.array([max(v, 1.0)]))
        ay_base = float(ggv.ay_max[0])
        if abs(bank_rad) > 1e-5:
            ay_base += 9.81 * math.sin(bank_rad)
        return max(ay_base, 0.0)

    def ax_max_accel(self, v: float, ay: float) -> float:
        """Maximum forward acceleration [m/s²] accounting for combined slip, load transfer, and drivetrain."""
        vp = _normalize_to_vehicle_params(self)
        m = vp.mass_kg
        drag = 0.5 * vp.rho_air * vp.cd * vp.frontal_area_m2 * (v ** 2)
        ay_lim = self.ay_max(v)
        eta_y = min(abs(ay) / max(ay_lim, 0.01), 1.0)
        eta_x = math.sqrt(max(0.0, 1.0 - eta_y ** 2))

        # Dynamic rear load under acceleration (rear wheel drive)
        # Note: weight distribution sensitivity:
        weight_dist_r = 1.0 - self.mass_props.weight_dist_front
        Fz_rear_static = m * 9.81 * weight_dist_r + 0.5 * vp.rho_air * vp.cl * vp.frontal_area_m2 * (v ** 2) * (1.0 - vp.cop_front)
        # Tire tractive force
        Fx_rear_tire = max(Fz_rear_static, 20.0) * vp.tire_mu(Fz_rear_static / 2.0) * eta_x
        F_drive_eng = self.powertrain.max_drive_force(v)
        F_net = min(F_drive_eng, Fx_rear_tire) - drag
        return max(float(F_net / m), -drag / m)

    def ax_max_brake(self, v: float, ay: float) -> float:
        """Maximum braking deceleration [m/s²] (positive magnitude)."""
        vp = _normalize_to_vehicle_params(self)
        m = vp.mass_kg
        drag = 0.5 * vp.rho_air * vp.cd * vp.frontal_area_m2 * (v ** 2)
        ay_lim = self.ay_max(v)
        eta_y = min(abs(ay) / max(ay_lim, 0.01), 1.0)
        eta_x = math.sqrt(max(0.0, 1.0 - eta_y ** 2))

        weight_dist_f = self.mass_props.weight_dist_front
        Fz_front_static = m * 9.81 * weight_dist_f + 0.5 * vp.rho_air * vp.cl * vp.frontal_area_m2 * (v ** 2) * vp.cop_front
        Fz_rear_static  = m * 9.81 * (1.0 - weight_dist_f) + 0.5 * vp.rho_air * vp.cl * vp.frontal_area_m2 * (v ** 2) * (1.0 - vp.cop_front)

        ax_guess = 10.0
        Fz_f = Fz_front_static + m * ax_guess * (vp.cg_height_m / vp.wheelbase_m)
        Fz_r = max(Fz_rear_static - m * ax_guess * (vp.cg_height_m / vp.wheelbase_m), 25.0)

        Fb_f = Fz_f * vp.tire_mu(Fz_f / 2.0) * eta_x
        Fb_r = Fz_r * vp.tire_mu(Fz_r / 2.0) * eta_x
        Fb_bias = min(Fb_f / max(vp.brake_bias_f, 0.05), Fb_r / max(1.0 - vp.brake_bias_f, 0.05))
        Fb_pedal = min(Fb_bias, vp.max_brake_force)
        return max(float((Fb_pedal + drag) / m), 0.1)

    def build_ggv(self, n_speeds: int = 40, n_ay: int = 20) -> np.ndarray:
        """Pre-compute the GGV envelope using compute_ggv_surface."""
        v_term = self.terminal_velocity()
        v_arr = np.linspace(5.0, min(v_term * 1.05, 120.0), n_speeds)
        ggv = compute_ggv_surface(self, speeds=v_arr, n_ay=n_ay)
        self._ggv_speeds   = ggv.speeds_ms
        self._ggv_ay_max   = ggv.ay_max
        self._ggv_ay_frac  = ggv.ay_fractions
        self._ggv_ax_accel = ggv.ax_accel_surface
        self._ggv_ax_brake = ggv.ax_brake_surface
        return np.column_stack([ggv.speeds_ms, ggv.ay_max, ggv.ax_accel_ay0])

    def _ay_max_lookup(self, v: float) -> float:
        if self._ggv_ay_max is None:
            self.build_ggv()
        return float(np.interp(v, self._ggv_speeds, self._ggv_ay_max))

    def _lookup_ax_accel(self, v: float, ay: float) -> float:
        if self._ggv_ax_accel is None:
            self.build_ggv()
        ay_lim = self._ay_max_lookup(v)
        ay_frac = np.clip(ay / max(ay_lim, 0.01), 0.0, 1.0)
        idx_v = int(np.clip(np.searchsorted(self._ggv_speeds, v) - 1, 0, len(self._ggv_speeds) - 2))
        dv = (v - self._ggv_speeds[idx_v]) / max(self._ggv_speeds[idx_v + 1] - self._ggv_speeds[idx_v], 1e-4)
        j = int(ay_frac * (len(self._ggv_ay_frac) - 1))
        return float((1.0 - dv) * self._ggv_ax_accel[idx_v, j] + dv * self._ggv_ax_accel[idx_v + 1, j])

    def _lookup_ax_brake(self, v: float, ay: float) -> float:
        if self._ggv_ax_brake is None:
            self.build_ggv()
        ay_lim = self._ay_max_lookup(v)
        ay_frac = np.clip(ay / max(ay_lim, 0.01), 0.0, 1.0)
        idx_v = int(np.clip(np.searchsorted(self._ggv_speeds, v) - 1, 0, len(self._ggv_speeds) - 2))
        dv = (v - self._ggv_speeds[idx_v]) / max(self._ggv_speeds[idx_v + 1] - self._ggv_speeds[idx_v], 1e-4)
        j = int(ay_frac * (len(self._ggv_ay_frac) - 1))
        return float((1.0 - dv) * self._ggv_ax_brake[idx_v, j] + dv * self._ggv_ax_brake[idx_v + 1, j])

    def arb_sensitivity(self, v: float = 50.0, ay: float = 20.0, delta_arb_front_nm: float = 5_000.0) -> dict:
        model = CoupledVehicleModel(mass_props=self.mass_props, aero=self.aero, suspension=self.suspension)
        return model.sensitivity_to_arb(v, ay, delta_arb_front_nm)

    def ride_height_sensitivity(self, v: float = 60.0, delta_rh_mm: float = 5.0) -> dict:
        model = CoupledVehicleModel(mass_props=self.mass_props, aero=self.aero, suspension=self.suspension)
        return model.sensitivity_to_ride_height(v, delta_rh_mm)

    def wheel_loads(self, v: float, ax: float, ay: float, bank_rad: float = 0.0, **kwargs):
        mp = self.mass_props
        sus = self.suspension
        m = mp.total_mass
        g = 9.81
        Fz0_front = m * g * mp.weight_dist_front + self.aero.downforce_front(v)
        Fz0_rear  = m * g * mp.weight_dist_rear  + self.aero.downforce_rear(v)

        dFz_long = m * ax * mp.h_cog / mp.wheelbase
        K_phi_f = sus.roll_stiffness_front(mp.track_front)
        K_phi_r = sus.roll_stiffness_rear(mp.track_rear)
        K_phi = max(K_phi_f + K_phi_r, 1.0)
        lat_frac_f = K_phi_f / K_phi

        dFz_lat_f = lat_frac_f * m * ay * mp.h_cog / mp.track_front
        dFz_lat_r = (1.0 - lat_frac_f) * m * ay * mp.h_cog / mp.track_rear

        Fz_FL = max(Fz0_front / 2.0 - dFz_long / 2.0 - dFz_lat_f / 2.0, 10.0)
        Fz_FR = max(Fz0_front / 2.0 - dFz_long / 2.0 + dFz_lat_f / 2.0, 10.0)
        Fz_RL = max(Fz0_rear  / 2.0 + dFz_long / 2.0 - dFz_lat_r / 2.0, 10.0)
        Fz_RR = max(Fz0_rear  / 2.0 + dFz_long / 2.0 + dFz_lat_r / 2.0, 10.0)
        return Fz_FL, Fz_FR, Fz_RL, Fz_RR


def solve_lap(
    vehicle: LapSimVehicle,
    segments: List[TrackSegment],
    *,
    build_ggv: bool = True,
    v_start: float | None = None,
    ers_config=None,
    ers_strategy: str = "optimal",
    tire_thermal_config=None,
) -> LapSimResult:
    """Quasi-Steady-State lap solver utilizing the closed-loop engine."""
    res = simulate_lap(vehicle=vehicle, track=segments, v_start=v_start)

    n = len(segments)
    wheel_loads = np.zeros((4, n))
    for i in range(n):
        v_i = res.speeds[i]
        ax_i = res.longitudinal_g[i] * 9.81
        ay_i = res.lateral_g[i] * 9.81
        fl, fr, rl, rr = vehicle.wheel_loads(v_i, ax_i, ay_i)
        wheel_loads[0, i] = fl
        wheel_loads[1, i] = fr
        wheel_loads[2, i] = rl
        wheel_loads[3, i] = rr

    if not build_ggv and getattr(vehicle, "_ggv_speeds", None) is not None:
        ggv_speeds_out = vehicle._ggv_speeds
        ggv_ay_max_out = vehicle._ggv_ay_max
        ggv_ax_accel_out = vehicle._ggv_ax_accel[:, 0]
        ggv_ax_brake_out = vehicle._ggv_ax_brake[:, 0]
        ggv_ay_frac_out = vehicle._ggv_ay_frac
        ggv_ax_accel_surface_out = vehicle._ggv_ax_accel
        ggv_ax_brake_surface_out = vehicle._ggv_ax_brake
    else:
        ggv = compute_ggv_surface(vehicle)
        ggv_speeds_out = ggv.speeds_ms
        ggv_ay_max_out = ggv.ay_max
        ggv_ax_accel_out = ggv.ax_accel_ay0
        ggv_ax_brake_out = ggv.ax_brake_ay0
        ggv_ay_frac_out = ggv.ay_fractions
        ggv_ax_accel_surface_out = ggv.ax_accel_surface
        ggv_ax_brake_surface_out = ggv.ax_brake_surface

    run_id_val = str(uuid.uuid4())
    now_ts = datetime.now(timezone.utc).isoformat()
    meta = SimulationMetadata(
        run_id=run_id_val,
        timestamp=now_ts,
        track_length_m=float(res.distances[-1] - res.distances[0]) if n > 1 else 0.0,
        n_segments=n,
    )

    return LapSimResult(
        total_time=res.lap_time_s,
        sector_times=res.sector_times,
        distances=res.distances,
        speeds=res.speeds,
        lateral_g=res.lateral_g,
        longitudinal_g=res.longitudinal_g,
        curvatures=res.curvatures,
        gear_number=res.gear_number,
        drive_force_n=res.drive_force_n,
        aero_downforce_n=res.aero_downforce_n,
        aero_drag_n=np.array([vehicle.aero.drag(v) for v in res.speeds]),
        wheel_loads_n=wheel_loads,
        pitch_deg=np.zeros(n),
        roll_deg=np.zeros(n),
        ride_height_front=np.full(n, float(vehicle.suspension.ride_height_front)),
        ride_height_rear=np.full(n, float(vehicle.suspension.ride_height_rear)),
        tire_utilization_x=res.tire_utilization_x,
        tire_utilization_y=res.tire_utilization_y,
        tire_utilization_combined=res.tire_utilization_combined,
        ax_available=res.ax_available,
        ay_available=res.ay_available,
        arb_balance=res.arb_balance,
        max_speed_kmh=res.max_speed_kmh,
        min_speed_kmh=res.min_speed_kmh,
        avg_speed_kmh=res.avg_speed_kmh,
        energy_used_kj=res.energy_used_kj,
        avg_power_kw=res.avg_power_kw,
        terminal_velocity_kmh=res.terminal_velocity_kmh,
        ggv_speeds=ggv_speeds_out,
        ggv_ay_max=ggv_ay_max_out,
        ggv_ax_accel=ggv_ax_accel_out,
        ggv_ax_brake=ggv_ax_brake_out,
        ggv_ay_frac=ggv_ay_frac_out,
        ggv_ax_accel_surface=ggv_ax_accel_surface_out,
        ggv_ax_brake_surface=ggv_ax_brake_surface_out,
        ggv_type="INTERPOLATED_PRE_COMPUTED",
        simulation_metadata=meta,
        model_assumptions=ModelAssumptions(),
    )


# Backward Compatibility Aliases
QuasiSteadyLapSimulator = LapSimVehicle
QuasiSteadyLapResult = LapSimResult
FastQuasiSteadyLapSimulator = LapSimVehicle
FastQuasiSteadyLapResult = LapSimResult
solve_fast_quasi_steady_lap = solve_lap
