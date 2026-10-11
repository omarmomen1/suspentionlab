"""
physics/tire_model.py
=====================
SuspensionLab PRO — Modular Tire Subsystem & Engineering Contracts

Provides the canonical tire architecture, standard output types, validity envelopes,
parameter hashing, dynamic tire radius geometry, first-order relaxation dynamics,
multi-axis lookup table models, and model registry.

Architecture:
TireModelBase
│
├── Pure longitudinal (Pacejka / LUT)
├── Pure lateral (Pacejka / LUT)
├── Aligning moment Mz (Pneumatic trail + residual torque)
├── Combined slip (Similarity Method Gxα / Gyκ)
├── Load sensitivity (dfz degressive friction)
├── Camber (gamma thrust & curvature effects)
├── Pressure (pressure-dependent contact stiffness, patch geometry & radius)
├── Temperature (thermal friction modulation)
├── Relaxation length (dynamic lag ODEs via TireRelaxationDynamics)
├── Vertical stiffness (kt(p))
├── Contact state (STICK/ATTACHED, SLIP/SLIPPING, SATURATED, LIFT_OFF/LOST)
├── Contact patch geometry (Length, Width, Area, Deflection)
├── Lookup table support (TireLUTModel with multi-axis interpolation)
└── Validity domain (explicit operating boundaries, confidence & OUT_OF_DOMAIN tagging)

Model Versions:
- MF52-v2.1: Pacejka 5.2 with Similarity Method combined-slip and full Mz
- MF94-v1: Classic Pacejka 1994 pure + friction ellipse (FAST_APPROXIMATION)
- CustomLUT-v1: Multi-axis test bench lookup table with domain enforcement
"""

from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Contact State & Validity Enums
# ─────────────────────────────────────────────────────────────────────────────

class ContactState(str, Enum):
    """Instantaneous contact patch physical state."""
    STICK = "ATTACHED"         # Linear elastic adhesion region (micro-slip)
    ATTACHED = "ATTACHED"      # Alias for STICK
    SLIP = "SLIPPING"          # Nonlinear transition / sliding region
    SLIPPING = "SLIPPING"      # Alias for SLIP
    SATURATED = "SATURATED"    # Peak friction capability reached
    LIFT_OFF = "LOST"          # Wheel airborne / normal load Fz <= 0
    LOST = "LOST"              # Alias for LIFT_OFF


class ValidityStatus(str, Enum):
    """Validation classification for evaluated tire operating point."""
    VALID = "VALID"                              # Operating strictly within calibrated domain
    EXTRAPOLATED_CAUTION = "EXTRAPOLATED_CAUTION"# Mild extrapolation near boundary (100-115% of envelope)
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"              # Substantial excursion outside calibrated domain
    CONTACT_LOST = "CONTACT_LOST"                # Normal load non-positive (Fz <= 0)


# ─────────────────────────────────────────────────────────────────────────────
# Contact Patch Geometry & Forces
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ContactPatchGeometry:
    """Calculated instantaneous contact patch dimensions and adhesion boundaries."""
    deflection_m: float = 0.0          # Vertical carcass deflection delta [m]
    length_m: float = 0.0              # Contact patch longitudinal length 2*a [m]
    width_m: float = 0.0               # Contact patch lateral width 2*b [m]
    area_m2: float = 0.0               # Contact patch surface area [m²]
    adhesion_limit_kappa: float = 0.02 # Longitudinal micro-slip limit [-]
    adhesion_limit_alpha_rad: float = 0.03 # Lateral micro-slip limit [rad] (~1.7°)

    def to_dict(self) -> Dict[str, float]:
        return {
            "deflection_mm": round(self.deflection_m * 1000.0, 2),
            "length_mm": round(self.length_m * 1000.0, 2),
            "width_mm": round(self.width_m * 1000.0, 2),
            "area_cm2": round(self.area_m2 * 10000.0, 2),
            "adhesion_limit_kappa": round(self.adhesion_limit_kappa, 4),
            "adhesion_limit_alpha_deg": round(math.degrees(self.adhesion_limit_alpha_rad), 2),
        }


@dataclass
class TireForces:
    """Standard output for a single tire force and moment evaluation."""
    Fx: float = 0.0            # Longitudinal force [N] (positive = driving)
    Fy: float = 0.0            # Lateral force [N] (positive = cornering in +Y)
    Mz: float = 0.0            # Self-aligning moment [N·m] (positive = restoring)
    Mx: float = 0.0            # Overturning moment [N·m]
    My: float = 0.0            # Rolling resistance moment [N·m]


@dataclass
class ValidityDomainResult:
    """Detailed diagnostic result from operating point domain validation."""
    is_valid: bool = True
    status: ValidityStatus = ValidityStatus.VALID
    warnings: List[str] = field(default_factory=list)
    domain_violations: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)
    confidence: float = 1.0     # 1.0 = fully calibrated, degrades outside envelope

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "status": self.status.value,
            "warnings": self.warnings,
            "domain_violations": {
                k: {"actual": round(v[0], 3), "min": round(v[1], 3), "max": round(v[2], 3)}
                for k, v in self.domain_violations.items()
            },
            "confidence": round(self.confidence, 3),
        }


@dataclass
class TireEvaluationResult:
    """Complete evaluation output with force components, contact state, and diagnostic warnings."""
    forces: TireForces
    contact_state: ContactState
    warnings: List[str] = field(default_factory=list)
    metadata: Optional[TireModelMetadata] = None
    effective_radius: float = 0.330
    loaded_radius: float = 0.330
    contact_patch: Optional[ContactPatchGeometry] = None
    validity: Optional[ValidityDomainResult] = None
    thermal_state: Optional[Any] = None

    @property
    def Fx(self) -> float:
        """Longitudinal force [N]."""
        return self.forces.Fx

    @property
    def Fy(self) -> float:
        """Lateral force [N]."""
        return self.forces.Fy

    @property
    def Mz(self) -> float:
        """Self-aligning moment [N·m]."""
        return self.forces.Mz

    @property
    def is_valid(self) -> bool:
        """Operating point validity boolean."""
        if self.validity is not None:
            return self.validity.is_valid
        return len(self.warnings) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Validity Range & Envelope
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidityRange:
    """Declares the physical operating envelope where the tire model is calibrated and trustworthy."""
    Fz_min: float = 500.0       # [N]
    Fz_max: float = 18000.0     # [N]
    alpha_min: float = -0.30    # [rad] (~-17.2°)
    alpha_max: float = 0.30     # [rad] (~+17.2°)
    kappa_min: float = -0.30    # [-] (±30% slip ratio)
    kappa_max: float = 0.30     # [-]
    camber_min: float = -0.105  # [rad] (~-6.0°)
    camber_max: float = 0.105   # [rad] (~+6.0°)
    T_min: float = 20.0         # [°C]
    T_max: float = 130.0        # [°C]
    p_min_bar: float = 1.0      # [bar]
    p_max_bar: float = 3.5      # [bar]
    speed_min_ms: float = 0.0   # [m/s]
    speed_max_ms: float = 100.0 # [m/s] (~360 km/h)

    def check_operating_point(
        self,
        Fz: float,
        alpha_rad: float,
        kappa: float,
        camber_rad: float = 0.0,
        T_c: float = 80.0,
        p_bar: float = 2.0,
        speed_ms: float = 0.0,
    ) -> List[str]:
        """Perform automatic boundary checks and return human-readable warnings (backward compatible)."""
        res = self.check(Fz, alpha_rad, kappa, camber_rad, p_bar, T_c, speed_ms)
        return res.warnings

    def check(
        self,
        Fz: float,
        alpha_rad: float,
        kappa: float,
        camber_rad: float = 0.0,
        p_bar: float = 2.0,
        T_c: float = 80.0,
        speed_ms: float = 0.0,
    ) -> ValidityDomainResult:
        """Rigorous boundary evaluation returning a structured ValidityDomainResult."""
        warnings: List[str] = []
        violations: Dict[str, Tuple[float, float, float]] = {}
        confidence: float = 1.0
        # Numerical Safety Guard: Reject NaN / Inf values immediately
        for param_name, param_val in (
            ("Fz", Fz),
            ("alpha_rad", alpha_rad),
            ("kappa", kappa),
            ("camber_rad", camber_rad),
            ("p_bar", p_bar),
            ("T_c", T_c),
            ("speed_ms", speed_ms),
        ):
            if isinstance(param_val, (int, float)) and (math.isnan(param_val) or math.isinf(param_val)):
                warnings.append(f"NUMERICAL SAFETY VIOLATION: Parameter '{param_name}' is NaN or infinite ({param_val}).")
                violations[param_name] = (param_val, -1e9, 1e9)
                return ValidityDomainResult(
                    is_valid=False,
                    status=ValidityStatus.OUT_OF_DOMAIN,
                    warnings=warnings,
                    domain_violations=violations,
                    confidence=0.0,
                )

        if Fz <= 0.0:
            warnings.append(f"CONTACT LOST: Normal load Fz={Fz:.1f} N <= 0. Zero grip generated.")
            return ValidityDomainResult(
                is_valid=False,
                status=ValidityStatus.CONTACT_LOST,
                warnings=warnings,
                domain_violations={"Fz": (Fz, self.Fz_min, self.Fz_max)},
                confidence=0.0,
            )

        if Fz < self.Fz_min:
            warnings.append(f"Load under-range: Fz={Fz:.0f} N is below calibrated minimum ({self.Fz_min:.0f} N).")
            violations["Fz"] = (Fz, self.Fz_min, self.Fz_max)
            confidence *= max(0.2, Fz / self.Fz_min)
        elif Fz > self.Fz_max:
            warnings.append(f"Load over-range: Fz={Fz:.0f} N exceeds calibrated envelope ({self.Fz_max:.0f} N).")
            violations["Fz"] = (Fz, self.Fz_min, self.Fz_max)
            confidence *= max(0.2, self.Fz_max / Fz)

        if abs(alpha_rad) > self.alpha_max:
            deg = math.degrees(abs(alpha_rad))
            max_deg = math.degrees(self.alpha_max)
            warnings.append(f"Slip angle outside calibrated range: |alpha|={deg:.1f}° > {max_deg:.1f}°.")
            violations["alpha_rad"] = (alpha_rad, self.alpha_min, self.alpha_max)
            confidence *= max(0.3, self.alpha_max / abs(alpha_rad))

        if abs(kappa) > self.kappa_max:
            warnings.append(f"Slip ratio outside calibrated range: |kappa|={abs(kappa):.2f} > {self.kappa_max:.2f}.")
            violations["kappa"] = (kappa, self.kappa_min, self.kappa_max)
            confidence *= max(0.3, self.kappa_max / abs(kappa))

        if abs(camber_rad) > self.camber_max:
            deg = math.degrees(abs(camber_rad))
            max_deg = math.degrees(self.camber_max)
            warnings.append(f"Camber angle exceeds calibrated range: |gamma|={deg:.1f}° > {max_deg:.1f}°.")
            violations["camber_rad"] = (camber_rad, self.camber_min, self.camber_max)
            confidence *= max(0.4, self.camber_max / abs(camber_rad))

        if T_c < self.T_min:
            warnings.append(f"Tire cold warning: T={T_c:.1f}°C is below optimal operating window ({self.T_min:.0f}°C).")
            violations["T_c"] = (T_c, self.T_min, self.T_max)
            confidence *= 0.85
        elif T_c > self.T_max:
            warnings.append(f"Tire overheating warning: T={T_c:.1f}°C exceeds thermal degradation ceiling ({self.T_max:.0f}°C).")
            violations["T_c"] = (T_c, self.T_min, self.T_max)
            confidence *= 0.80

        if not (self.p_min_bar <= p_bar <= self.p_max_bar):
            warnings.append(f"Inflation pressure {p_bar:.2f} bar is outside calibrated range [{self.p_min_bar}, {self.p_max_bar}] bar.")
            violations["p_bar"] = (p_bar, self.p_min_bar, self.p_max_bar)
            confidence *= 0.85

        if speed_ms > self.speed_max_ms:
            warnings.append(f"Speed {speed_ms*3.6:.1f} km/h exceeds maximum rated tire speed {self.speed_max_ms*3.6:.0f} km/h.")
            violations["speed_ms"] = (speed_ms, self.speed_min_ms, self.speed_max_ms)
            confidence *= 0.75

        if len(violations) > 0:
            is_extreme = False
            for k, (val, vmin, vmax) in violations.items():
                span = vmax - vmin
                if val < vmin - 0.15 * span or val > vmax + 0.15 * span:
                    is_extreme = True
                    break
            status = ValidityStatus.OUT_OF_DOMAIN if is_extreme else ValidityStatus.EXTRAPOLATED_CAUTION
            is_valid = (status != ValidityStatus.OUT_OF_DOMAIN)
        else:
            status = ValidityStatus.VALID
            is_valid = True

        return ValidityDomainResult(
            is_valid=is_valid,
            status=status,
            warnings=warnings,
            domain_violations=violations,
            confidence=float(np.clip(confidence, 0.05, 1.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Fz": [self.Fz_min, self.Fz_max],
            "alpha_rad": [self.alpha_min, self.alpha_max],
            "kappa": [self.kappa_min, self.kappa_max],
            "camber_rad": [self.camber_min, self.camber_max],
            "T_degC": [self.T_min, self.T_max],
            "pressure_bar": [self.p_min_bar, self.p_max_bar],
            "speed_ms": [self.speed_min_ms, self.speed_max_ms],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Tire Radius & Geometry Definition
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TireDefinition:
    """Complete physical tire specification including structural, geometric, and stiffness properties.
    
    Replaces static hardcoded radius constants with state-dependent functions:
    R = f(Fz, pressure, T, kappa).
    """
    unloaded_radius: float = 0.330       # Unloaded outer radius R0 [m] (e.g. 330 mm)
    section_width: float = 0.245         # Nominal tire width W0 [m] (e.g. 245 mm)
    aspect_ratio: float = 0.40           # Aspect ratio [-] (e.g. /40)
    rim_diameter_inch: float = 18.0      # Wheel rim diameter [inch]
    nominal_pressure_bar: float = 2.0    # Reference inflation pressure p0 [bar]
    vertical_stiffness_k_t: float = 250_000.0  # Vertical carcass stiffness kt0 [N/m]
    relaxation_length_x: float = 0.25    # Longitudinal relaxation length sigma_x0 [m]
    relaxation_length_y: float = 0.35    # Lateral relaxation length sigma_y0 [m]

    def __post_init__(self) -> None:
        if math.isnan(self.unloaded_radius) or math.isinf(self.unloaded_radius) or self.unloaded_radius <= 0.08:
            raise ValueError(f"Tire unloaded radius must be strictly positive >= 0.08 m (got {self.unloaded_radius}).")
        if math.isnan(self.section_width) or self.section_width <= 0.02:
            raise ValueError(f"Tire section width must be strictly positive >= 0.02 m (got {self.section_width}).")
        if math.isnan(self.vertical_stiffness_k_t) or self.vertical_stiffness_k_t < 10000.0:
            raise ValueError(f"Tire carcass vertical stiffness must be >= 10,000 N/m (got {self.vertical_stiffness_k_t}).")
        if math.isnan(self.nominal_pressure_bar) or self.nominal_pressure_bar <= 0.2:
            raise ValueError(f"Tire nominal pressure must be >= 0.2 bar (got {self.nominal_pressure_bar}).")

    def vertical_stiffness(self, pressure_bar: float = 2.0) -> float:
        """Pressure-adjusted vertical tire stiffness [N/m].
        
        kt(p) = kt0 * (0.4 + 0.6 * (p / p0))
        """
        p_ratio = max(0.4, pressure_bar / max(0.5, self.nominal_pressure_bar))
        return float(self.vertical_stiffness_k_t * (0.4 + 0.6 * p_ratio))

    def loaded_radius(self, Fz: float, pressure_bar: float = 2.0) -> float:
        """Static loaded radius [m] under normal load Fz and inflation pressure.
        
        R_l = R_0 - F_z / k_t(p)
        """
        if Fz <= 0.0:
            return self.unloaded_radius
        kt = self.vertical_stiffness(pressure_bar)
        deflection = Fz / kt
        return float(max(0.15, self.unloaded_radius - deflection))

    def effective_radius(self, Fz: float, pressure_bar: float = 2.0, kappa: float = 0.0) -> float:
        """Effective rolling radius [m] used for vehicle speed and wheel rotational velocity kinematic coupling.
        
        R_eff = R_0 - (1 - lambda_eff) * (R_0 - R_l)
        """
        if Fz <= 0.0:
            return self.unloaded_radius
        r_l = self.loaded_radius(Fz, pressure_bar)
        delta = self.unloaded_radius - r_l
        lambda_eff = 0.33
        r_eff = self.unloaded_radius - (1.0 - lambda_eff) * delta
        r_eff *= (1.0 + 0.01 * kappa)
        return float(max(0.15, r_eff))

    def contact_patch_geometry(self, Fz: float, pressure_bar: float = 2.0) -> ContactPatchGeometry:
        """Compute contact patch geometry dimensions based on carcass deflection."""
        if Fz <= 0.0:
            return ContactPatchGeometry()

        kt = self.vertical_stiffness(pressure_bar)
        delta = max(0.0, Fz / kt)
        r0 = self.unloaded_radius

        r_diff = max(0.0, r0 - delta)
        length_m = 2.0 * math.sqrt(max(0.0, r0**2 - r_diff**2))

        p_ratio = max(0.5, pressure_bar / max(0.5, self.nominal_pressure_bar))
        width_m = self.section_width * min(1.0, (Fz / 4000.0) ** 0.25) / math.sqrt(p_ratio)
        area_m2 = length_m * width_m * 0.85

        adhesion_k = max(0.01, 0.03 / math.sqrt(p_ratio))
        adhesion_a = max(0.015, 0.045 / math.sqrt(p_ratio))

        return ContactPatchGeometry(
            deflection_m=delta,
            length_m=length_m,
            width_m=width_m,
            area_m2=area_m2,
            adhesion_limit_kappa=adhesion_k,
            adhesion_limit_alpha_rad=adhesion_a,
        )

    def relaxation_lengths(self, Fz: float, pressure_bar: float = 2.0) -> Tuple[float, float]:
        """Compute load- and pressure-dependent relaxation lengths (sigma_x, sigma_y) [m]."""
        if Fz <= 0.0:
            return self.relaxation_length_x, self.relaxation_length_y

        p_ratio = max(0.5, pressure_bar / max(0.5, self.nominal_pressure_bar))
        fz_ratio = max(0.2, min(4.0, Fz / 4000.0))

        scale = math.sqrt(fz_ratio) / (p_ratio ** 0.3)
        sig_x = float(np.clip(self.relaxation_length_x * scale, 0.05, 1.2))
        sig_y = float(np.clip(self.relaxation_length_y * scale, 0.08, 1.5))
        return sig_x, sig_y

    def radius_vs_load(
        self,
        Fz: float,
        pressure_bar: float = 2.0,
        T_c: float = 80.0,
        kappa: float = 0.0
    ) -> float:
        """Comprehensive dynamic tire radius function R = f(Fz, p, T, kappa)."""
        r_eff = self.effective_radius(Fz, pressure_bar, kappa)
        t_factor = 1.0 + 0.00002 * (T_c - 25.0)
        return float(r_eff * t_factor)

    def to_enveloping_config(
        self,
        mode: Any = "POINT_CONTACT",
        pressure_bar: Optional[float] = None,
        speed_mps: float = 20.0,
        **kwargs
    ) -> Any:
        """Create a TireEnvelopingConfig consistent with this canonical tire definition."""
        from suspensionlab.physics.tire_enveloping import (
            TireEnvelopingConfig,
            TireEnvelopingMode,
        )
        p_bar = self.nominal_pressure_bar if pressure_bar is None else pressure_bar
        return TireEnvelopingConfig(
            mode=mode,
            unloaded_radius=self.unloaded_radius,
            section_width=self.section_width,
            vertical_stiffness_k_t=self.vertical_stiffness_k_t,
            inflation_pressure_bar=p_bar,
            nominal_pressure_bar=self.nominal_pressure_bar,
            speed_mps=speed_mps,
            **kwargs
        )


# ─────────────────────────────────────────────────────────────────────────────
# First-Order Force Relaxation Dynamics
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TireRelaxationDynamics:
    """First-order force and slip relaxation state model:
    
    1. Dynamic Slip Formulation (Pacejka Carcass Deflection):
       sigma_x * d(kappa')/ds + kappa' = kappa_eq  ==>  (sigma_x / vx) * d(kappa')/dt + kappa' = kappa_eq
       sigma_y * d(alpha')/ds + alpha' = alpha_eq  ==>  (sigma_y / vx) * d(alpha')/dt + alpha' = alpha_eq
    
    2. Dynamic Force Formulation:
       sigma_x * dFx/ds + Fx = Fx_eq  ==>  (sigma_x / vx) * dFx/dt + Fx = Fx_eq
       sigma_y * dFy/ds + Fy = Fy_eq  ==>  (sigma_y / vx) * dFy/dt + Fy = Fy_eq
    
    Includes transport velocity regularisation to eliminate zero-speed singularities:
       v_trans = sqrt(v_x^2 + v_min^2)
       tau_x = sigma_x / v_trans
       tau_y = sigma_y / v_trans
    """
    Fx: float = 0.0             # Current dynamic longitudinal force [N]
    Fy: float = 0.0             # Current dynamic lateral force [N]
    alpha_prime: float = 0.0    # Dynamic relaxed lateral slip angle [rad]
    kappa_prime: float = 0.0    # Dynamic relaxed longitudinal slip ratio [-]
    v_min: float = 0.1          # Velocity floor regularisation [m/s]

    def reset(
        self,
        Fx: float = 0.0,
        Fy: float = 0.0,
        alpha_prime: float = 0.0,
        kappa_prime: float = 0.0,
    ) -> None:
        """Reset internal force and slip states."""
        self.Fx = float(Fx)
        self.Fy = float(Fy)
        self.alpha_prime = float(alpha_prime)
        self.kappa_prime = float(kappa_prime)

    @classmethod
    def get_time_constants(
        cls,
        v_x: float,
        sigma_x: float = 0.25,
        sigma_y: float = 0.35,
        v_min: float = 0.10,
    ) -> Tuple[float, float]:
        """Compute speed-dependent relaxation time constants tau_x and tau_y [s]."""
        v_trans = math.sqrt(v_x**2 + v_min**2)
        sig_x = max(0.01, sigma_x)
        sig_y = max(0.01, sigma_y)
        return sig_x / v_trans, sig_y / v_trans

    @staticmethod
    def calc_relaxation_lengths(
        Fz: float,
        Fz0: float = 4000.0,
        sigma_x0: float = 0.15,
        sigma_y0: float = 0.25,
        load_exp: float = 0.3,
    ) -> Tuple[float, float]:
        """Compute load-dependent relaxation lengths sigma_x and sigma_y [m].
        
        Tire carcass relaxation lengths grow with normal load (larger contact patch 2a):
        sigma(Fz) = sigma_0 * (Fz / Fz0)^load_exp
        """
        if Fz <= 0.0:
            return 0.01, 0.01
        scale = float((Fz / max(100.0, Fz0)) ** load_exp)
        sig_x = float(np.clip(sigma_x0 * scale, 0.05, 1.20))
        sig_y = float(np.clip(sigma_y0 * scale, 0.08, 1.50))
        return sig_x, sig_y

    def calc_derivatives(
        self,
        Fx_eq: float,
        Fy_eq: float,
        v_x: float,
        sigma_x: float = 0.25,
        sigma_y: float = 0.35,
    ) -> Tuple[float, float]:
        """Compute time derivatives (dFx/dt, dFy/dt) with transport velocity regularisation."""
        v_trans = math.sqrt(v_x**2 + self.v_min**2)
        sig_x = max(0.01, sigma_x)
        sig_y = max(0.01, sigma_y)

        dFx_dt = (Fx_eq - self.Fx) * (v_trans / sig_x)
        dFy_dt = (Fy_eq - self.Fy) * (v_trans / sig_y)
        return float(dFx_dt), float(dFy_dt)

    def calc_slip_derivatives(
        self,
        alpha_eq: float,
        kappa_eq: float,
        v_x: float,
        sigma_x: float = 0.25,
        sigma_y: float = 0.35,
    ) -> Tuple[float, float]:
        """Compute slip time derivatives (dalpha'/dt, dkappa'/dt) with transport velocity regularisation."""
        v_trans = math.sqrt(v_x**2 + self.v_min**2)
        sig_x = max(0.01, sigma_x)
        sig_y = max(0.01, sigma_y)

        dalpha_dt = (alpha_eq - self.alpha_prime) * (v_trans / sig_y)
        dkappa_dt = (kappa_eq - self.kappa_prime) * (v_trans / sig_x)
        return float(dalpha_dt), float(dkappa_dt)

    def step_time(
        self,
        Fx_eq: float,
        Fy_eq: float,
        v_x: float,
        dt: float,
        sigma_x: float = 0.25,
        sigma_y: float = 0.35,
    ) -> Tuple[float, float]:
        """Advance dynamic force state by dt seconds using exact exponential integration."""
        tau_x, tau_y = self.get_time_constants(v_x, sigma_x, sigma_y)

        decay_x = math.exp(-dt / tau_x)
        decay_y = math.exp(-dt / tau_y)

        self.Fx = float(Fx_eq + (self.Fx - Fx_eq) * decay_x)
        self.Fy = float(Fy_eq + (self.Fy - Fy_eq) * decay_y)
        return self.Fx, self.Fy

    def step_slip_time(
        self,
        alpha_eq: float,
        kappa_eq: float,
        v_x: float,
        dt: float,
        sigma_x: float = 0.25,
        sigma_y: float = 0.35,
    ) -> Tuple[float, float]:
        """Advance dynamic slip states by dt seconds using exact exponential integration."""
        tau_x, tau_y = self.get_time_constants(v_x, sigma_x, sigma_y)

        decay_x = math.exp(-dt / tau_x)
        decay_y = math.exp(-dt / tau_y)

        self.kappa_prime = float(kappa_eq + (self.kappa_prime - kappa_eq) * decay_x)
        self.alpha_prime = float(alpha_eq + (self.alpha_prime - alpha_eq) * decay_y)
        return self.alpha_prime, self.kappa_prime

    def step_distance(
        self,
        Fx_eq: float,
        Fy_eq: float,
        ds: float,
        sigma_x: float = 0.25,
        sigma_y: float = 0.35,
    ) -> Tuple[float, float]:
        """Advance dynamic force state by distance ds [m] using exact spatial integration."""
        sig_x = max(0.01, sigma_x)
        sig_y = max(0.01, sigma_y)

        decay_x = math.exp(-abs(ds) / sig_x)
        decay_y = math.exp(-abs(ds) / sig_y)

        self.Fx = float(Fx_eq + (self.Fx - Fx_eq) * decay_x)
        self.Fy = float(Fy_eq + (self.Fy - Fy_eq) * decay_y)
        return self.Fx, self.Fy


# ─────────────────────────────────────────────────────────────────────────────
# Metadata & Parameter Hashing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TireModelMetadata:
    """Traceability metadata attached to every tire model instance."""
    model_id: str = "mf52"
    model_version: str = "5.2.1"
    parameter_hash: str = ""
    validity_range: ValidityRange = field(default_factory=ValidityRange)
    tire_definition: TireDefinition = field(default_factory=TireDefinition)
    source: str = "Pacejka MF 5.2 Standard Parameter Set"
    solver: str = "Analytical Closed-Form / JIT"
    backend: str = "Numba-JIT / High-Fidelity"
    dataset_name: str = "Standard Reference Benchmark"
    known_limitations: List[str] = field(default_factory=lambda: [
        "Quasi-steady-state friction evaluation; high-frequency carcass acoustics (>50 Hz) omitted.",
        "Contact loss strictly enforced at Fz <= 0.",
        "Hydroplaning and wet-road film dynamics are not modeled."
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "parameter_hash": self.parameter_hash,
            "validity_range": self.validity_range.to_dict(),
            "source": self.source,
            "solver": self.solver,
            "backend": self.backend,
            "dataset_name": self.dataset_name,
            "known_limitations": self.known_limitations,
        }


def compute_parameter_hash(params: Any) -> str:
    """Compute a deterministic SHA-256 hash of a parameter set."""
    if hasattr(params, "to_array"):
        arr = params.to_array()
        return hashlib.sha256(arr.tobytes()).hexdigest()
    if hasattr(params, "__dict__"):
        obj = {k: v for k, v in vars(params).items() if not k.startswith("_")}
    elif isinstance(params, dict):
        obj = params
    else:
        obj = str(params)
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Abstract Tire Model Base
# ─────────────────────────────────────────────────────────────────────────────

class TireModelBase(ABC):
    """Canonical abstract base class for all professional engineering tire models."""

    @property
    @abstractmethod
    def metadata(self) -> TireModelMetadata:
        """Return model traceability metadata."""
        ...

    @property
    @abstractmethod
    def definition(self) -> TireDefinition:
        """Return tire geometry and structural definition."""
        ...

    @abstractmethod
    def evaluate(
        self,
        Fz: float,
        alpha: float = 0.0,
        kappa: float = 0.0,
        camber: float = 0.0,
        pressure: float = 2.0,
        temperature: float = 80.0,
        speed: float = 0.0,
        **kwargs,
    ) -> TireEvaluationResult:
        """Canonical evaluation interface with full state output and boundary diagnostics."""
        ...

    def calc_forces(
        self,
        Fz: float,
        alpha_rad: float = 0.0,
        kappa: float = 0.0,
        camber_rad: float = 0.0,
        **kwargs,
    ) -> TireForces:
        """High-speed force evaluation interface returning standard TireForces."""
        res = self.evaluate(Fz, alpha_rad, kappa, camber_rad, **kwargs)
        return res.forces


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Axis Tire Lookup Table (LUT) Model
# ─────────────────────────────────────────────────────────────────────────────

class TireLUTModel(TireModelBase):
    """Multi-axis gridded / tabular test-bench Lookup Table (LUT) Tire Model.
    
    Supports 2D/3D/4D interpolation over (Fz, alpha, kappa, camber, pressure, temperature).
    Strictly flags out-of-domain evaluation requests with OUT_OF_DOMAIN.
    """

    def __init__(
        self,
        Fz_grid: np.ndarray,
        alpha_grid: np.ndarray,
        kappa_grid: np.ndarray,
        Fx_table: np.ndarray,
        Fy_table: np.ndarray,
        Mz_table: Optional[np.ndarray] = None,
        definition: Optional[TireDefinition] = None,
        source: str = "Test Bench Multi-Axis Measurement Table",
    ):
        from scipy.interpolate import RegularGridInterpolator

        self.Fz_grid = np.asarray(Fz_grid, dtype=float)
        self.alpha_grid = np.asarray(alpha_grid, dtype=float)
        self.kappa_grid = np.asarray(kappa_grid, dtype=float)
        self.Fx_table = np.asarray(Fx_table, dtype=float)
        self.Fy_table = np.asarray(Fy_table, dtype=float)

        if Mz_table is not None:
            self.Mz_table = np.asarray(Mz_table, dtype=float)
        else:
            self.Mz_table = np.zeros_like(self.Fy_table)

        self._definition = definition or TireDefinition()
        self._val_range = ValidityRange(
            Fz_min=float(self.Fz_grid.min()),
            Fz_max=float(self.Fz_grid.max()),
            alpha_min=float(self.alpha_grid.min()),
            alpha_max=float(self.alpha_grid.max()),
            kappa_min=float(self.kappa_grid.min()),
            kappa_max=float(self.kappa_grid.max()),
        )

        points = (self.Fz_grid, self.alpha_grid, self.kappa_grid)
        self._interp_Fx = RegularGridInterpolator(points, self.Fx_table, bounds_error=False, fill_value=None)
        self._interp_Fy = RegularGridInterpolator(points, self.Fy_table, bounds_error=False, fill_value=None)
        self._interp_Mz = RegularGridInterpolator(points, self.Mz_table, bounds_error=False, fill_value=None)

        param_dict = {
            "Fz_grid": self.Fz_grid.tolist(),
            "alpha_grid": self.alpha_grid.tolist(),
            "kappa_grid": self.kappa_grid.tolist(),
        }
        self._metadata = TireModelMetadata(
            model_id="custom_lut",
            model_version="LUT-v1.0",
            parameter_hash=compute_parameter_hash(param_dict),
            validity_range=self._val_range,
            tire_definition=self._definition,
            source=source,
            solver="Multi-Dimensional Regular Spline Interpolation",
            backend="SciPy RegularGridInterpolator",
        )

    @property
    def metadata(self) -> TireModelMetadata:
        return self._metadata

    @property
    def definition(self) -> TireDefinition:
        return self._definition

    def evaluate(
        self,
        Fz: float,
        alpha: float = 0.0,
        kappa: float = 0.0,
        camber: float = 0.0,
        pressure: float = 2.0,
        temperature: float = 80.0,
        speed: float = 0.0,
        **kwargs,
    ) -> TireEvaluationResult:
        alpha_rad = kwargs.get("alpha_rad", alpha)
        camber_rad = kwargs.get("camber_rad", camber)
        p_bar = kwargs.get("pressure_bar", pressure)
        t_c = kwargs.get("T_c", temperature)
        v_speed = kwargs.get("v_x", speed)

        val_res = self._val_range.check(Fz, alpha_rad, kappa, camber_rad, p_bar, t_c, v_speed)

        if Fz <= 0.0:
            return TireEvaluationResult(
                forces=TireForces(Fx=0.0, Fy=0.0, Mz=0.0),
                contact_state=ContactState.LIFT_OFF,
                warnings=val_res.warnings,
                metadata=self._metadata,
                effective_radius=self._definition.unloaded_radius,
                loaded_radius=self._definition.unloaded_radius,
                validity=val_res,
            )

        fz_eval = float(np.clip(Fz, self.Fz_grid.min(), self.Fz_grid.max()))
        al_eval = float(np.clip(alpha_rad, self.alpha_grid.min(), self.alpha_grid.max()))
        ka_eval = float(np.clip(kappa, self.kappa_grid.min(), self.kappa_grid.max()))

        pt = np.array([[fz_eval, al_eval, ka_eval]])
        Fx = float(self._interp_Fx(pt)[0])
        Fy = float(self._interp_Fy(pt)[0])
        Mz = float(self._interp_Mz(pt)[0])

        if abs(camber_rad) > 1e-5:
            Fy += float(Fz * camber_rad * 0.08)

        r_l = self._definition.loaded_radius(Fz, p_bar)
        r_eff = self._definition.effective_radius(Fz, p_bar, kappa)
        cp_geom = self._definition.contact_patch_geometry(Fz, p_bar)

        combined_slip = math.sqrt(kappa**2 + alpha_rad**2)
        if combined_slip < cp_geom.adhesion_limit_kappa:
            state = ContactState.STICK
        elif combined_slip < 0.12:
            state = ContactState.SLIP
        else:
            state = ContactState.SATURATED

        return TireEvaluationResult(
            forces=TireForces(Fx=Fx, Fy=Fy, Mz=Mz),
            contact_state=state,
            warnings=val_res.warnings,
            metadata=self._metadata,
            effective_radius=r_eff,
            loaded_radius=r_l,
            contact_patch=cp_geom,
            validity=val_res,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

_TIRE_REGISTRY: Dict[str, type] = {}


def register_tire_model(model_id: str):
    """Decorator to register a TireModelBase subclass."""
    def decorator(cls):
        _TIRE_REGISTRY[model_id] = cls
        return cls
    return decorator


def get_tire_model(model_id: str = "mf52", **kwargs) -> TireModelBase:
    """Retrieve a registered tire model by ID."""
    if model_id not in _TIRE_REGISTRY:
        from suspensionlab.physics.magic_formula import PacejkaMF52TireModel
        _TIRE_REGISTRY["mf52"] = PacejkaMF52TireModel
        _TIRE_REGISTRY["pacejka"] = PacejkaMF52TireModel
        _TIRE_REGISTRY["lut"] = TireLUTModel

    if model_id not in _TIRE_REGISTRY:
        available = ", ".join(sorted(_TIRE_REGISTRY.keys()))
        raise KeyError(f"Unknown tire model '{model_id}'. Available: {available}")
    return _TIRE_REGISTRY[model_id](**kwargs)


def list_tire_models() -> List[str]:
    """Return all registered tire model IDs."""
    if "mf52" not in _TIRE_REGISTRY:
        from suspensionlab.physics.magic_formula import PacejkaMF52TireModel
        _TIRE_REGISTRY["mf52"] = PacejkaMF52TireModel
        _TIRE_REGISTRY["pacejka"] = PacejkaMF52TireModel
        _TIRE_REGISTRY["lut"] = TireLUTModel
    return sorted(_TIRE_REGISTRY.keys())
