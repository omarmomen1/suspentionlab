"""
physics/vehicle_presets.py
==========================
SuspensionLab PRO — Canonical Vehicle Specifications and Unified Presets

Provides standardized, physically unified vehicle presets (compact hatchback,
GT3 touring sports car, Formula SAE open-wheeler) with consistent parameters
across Quarter-Car, Half-Car, Full-Car, and Non-Linear Handling dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from suspensionlab.physics.quarter_car import QuarterCarParams
from suspensionlab.physics.half_car import HalfCarParams
from suspensionlab.physics.full_car import FullCarParams
from suspensionlab.physics.handling_model import HandlingParams


@dataclass
class CanonicalVehicleSpec:
    """Unified vehicle parameters defining geometry, mass distribution, springs, and dampers."""
    name: str
    description: str

    # Mass & Inertias
    m_s: float          # Total sprung mass [kg]
    m_uf: float         # Front unsprung mass per corner [kg]
    m_ur: float         # Rear unsprung mass per corner [kg]
    I_x: float          # Chassis roll inertia [kg*m^2]
    I_y: float          # Chassis pitch inertia [kg*m^2]
    I_z: float          # Vehicle yaw inertia [kg*m^2]

    # Wheelbase & Weight Distribution
    L: float            # Wheelbase [m]
    a: float            # CG to front axle [m]
    b: float            # CG to rear axle [m]
    tw_f: float         # Front track width [m]
    tw_r: float         # Rear track width [m]
    h_cg_s: float       # Sprung mass CG height [m]
    h_cg_u: float = 0.30 # Unsprung mass CG height [m]

    # Suspension Rates
    k_sf: float = 30000.0   # Front spring rate at spring [N/m]
    k_sr: float = 35000.0   # Rear spring rate at spring [N/m]
    c_f: float = 2500.0     # Front damper rate [Ns/m]
    c_r: float = 2800.0     # Rear damper rate [Ns/m]
    MR_f: float = 0.85      # Front motion ratio (spring travel / wheel travel) [-]
    MR_r: float = 0.85      # Rear motion ratio [-]

    # Anti-Roll Bars (Wheel rate)
    k_arb_f: float = 15000.0  # Front ARB stiffness at wheel [N/m]
    k_arb_r: float = 8000.0   # Rear ARB stiffness at wheel [N/m]

    # Tires
    k_tf: float = 220000.0    # Front tire vertical rate [N/m]
    k_tr: float = 220000.0    # Rear tire vertical rate [N/m]

    @property
    def total_mass(self) -> float:
        """Total vehicle mass [kg]."""
        return self.m_s + 2.0 * self.m_uf + 2.0 * self.m_ur

    @property
    def front_weight_dist(self) -> float:
        """Fraction of mass on front axle [-]."""
        return self.b / self.L

    def to_quarter_car_params(self, corner: str = "fl") -> QuarterCarParams:
        """Extract equivalent 2-DOF quarter-car parameters for front or rear corner."""
        is_front = corner.lower() in ("fl", "fr", "front", "f")
        m_s_corner = self.m_s * (self.b / (2.0 * self.L)) if is_front else self.m_s * (self.a / (2.0 * self.L))
        m_u_corner = self.m_uf if is_front else self.m_ur
        k_s_corner = self.k_sf if is_front else self.k_sr
        c_corner   = self.c_f  if is_front else self.c_r
        mr_corner  = self.MR_f if is_front else self.MR_r
        k_t_corner = self.k_tf if is_front else self.k_tr

        return QuarterCarParams(
            m_s=m_s_corner,
            m_u=m_u_corner,
            k_s=k_s_corner,
            c=c_corner,
            k_t=k_t_corner,
            MR=mr_corner,
        )

    def to_half_car_params(self) -> HalfCarParams:
        """Extract equivalent 4-DOF half-car pitch plane parameters."""
        k_wf = self.k_sf * (self.MR_f ** 2)
        k_wr = self.k_sr * (self.MR_r ** 2)
        c_wf = self.c_f * (self.MR_f ** 2)
        c_wr = self.c_r * (self.MR_r ** 2)

        return HalfCarParams(
            m_s=self.m_s,
            I_y=self.I_y,
            m_uf=2.0 * self.m_uf,
            m_ur=2.0 * self.m_ur,
            k_sf=k_wf,
            k_sr=k_wr,
            c_f=c_wf,
            c_r=c_wr,
            k_tf=2.0 * self.k_tf,
            k_tr=2.0 * self.k_tr,
            L=self.L,
            a=self.a,
            b=self.b,
        )

    def to_full_car_params(self, speed_mps: float = 20.0) -> FullCarParams:
        """Extract equivalent 7-DOF full-car parameters."""
        return FullCarParams(
            m_s=self.m_s,
            I_x=self.I_x,
            I_y=self.I_y,
            m_uf=self.m_uf,
            m_ur=self.m_ur,
            k_sf=self.k_sf,
            k_sr=self.k_sr,
            c_f=self.c_f,
            c_r=self.c_r,
            k_arb_f=self.k_arb_f,
            k_arb_r=self.k_arb_r,
            k_tf=self.k_tf,
            k_tr=self.k_tr,
            L=self.L,
            a=self.a,
            b=self.b,
            tw_f=self.tw_f,
            tw_r=self.tw_r,
            speed_mps=speed_mps,
            MR_f=self.MR_f,
            MR_r=self.MR_r,
        )

    def to_handling_params(self) -> HandlingParams:
        """Extract equivalent non-linear handling model parameters."""
        # Roll stiffness: K_phi = 0.5 * k_arb_wheel * (tw^2)
        k_phi_arb_f = 0.5 * self.k_arb_f * (self.tw_f ** 2)
        k_phi_arb_r = 0.5 * self.k_arb_r * (self.tw_r ** 2)

        return HandlingParams(
            m=self.total_mass,
            m_s=self.m_s,
            m_uf=2.0 * self.m_uf,
            m_ur=2.0 * self.m_ur,
            I_z=self.I_z,
            a=self.a,
            b=self.b,
            tw_f=self.tw_f,
            tw_r=self.tw_r,
            h_cg_s=self.h_cg_s,
            h_cg_uf=self.h_cg_u,
            h_cg_ur=self.h_cg_u,
            K_spring_f=self.k_sf * (self.MR_f ** 2),
            K_spring_r=self.k_sr * (self.MR_r ** 2),
            K_arb_f=k_phi_arb_f,
            K_arb_r=k_phi_arb_r,
            C_damper_f=self.c_f * (self.MR_f ** 2),
            C_damper_r=self.c_r * (self.MR_r ** 2),
        )


CANONICAL_PRESETS: Dict[str, CanonicalVehicleSpec] = {
    "compact_hatchback": CanonicalVehicleSpec(
        name="Compact Hatchback",
        description="Everyday C-segment passenger hatchback with balanced comfort/handling compromise.",
        m_s=1150.0,
        m_uf=40.0,
        m_ur=35.0,
        I_x=420.0,
        I_y=1750.0,
        I_z=1950.0,
        L=2.60,
        a=1.15,
        b=1.45,
        tw_f=1.54,
        tw_r=1.52,
        h_cg_s=0.52,
        k_sf=28000.0,
        k_sr=32000.0,
        c_f=2200.0,
        c_r=2400.0,
        MR_f=0.85,
        MR_r=0.80,
        k_tf=220000.0,
        k_tr=220000.0,
        k_arb_f=15000.0,
        k_arb_r=8000.0,
    ),
    "gt3_touring": CanonicalVehicleSpec(
        name="GT3 Touring",
        description="High-downforce GT3 sports race car with stiff springs, low CG, and high grip.",
        m_s=1250.0,
        m_uf=45.0,
        m_ur=48.0,
        I_x=480.0,
        I_y=1900.0,
        I_z=2100.0,
        L=2.50,
        a=1.20,
        b=1.30,
        tw_f=1.65,
        tw_r=1.62,
        h_cg_s=0.38,
        k_sf=90000.0,
        k_sr=120000.0,
        c_f=4500.0,
        c_r=5500.0,
        MR_f=0.78,
        MR_r=0.75,
        k_tf=280000.0,
        k_tr=300000.0,
        k_arb_f=45000.0,
        k_arb_r=30000.0,
    ),
    "formula_sae": CanonicalVehicleSpec(
        name="Formula SAE",
        description="Ultra-lightweight open-wheel competition race car with direct pullrod/pushrod suspension.",
        m_s=200.0,
        m_uf=9.0,
        m_ur=10.0,
        I_x=35.0,
        I_y=110.0,
        I_z=125.0,
        L=1.55,
        a=0.75,
        b=0.80,
        tw_f=1.20,
        tw_r=1.18,
        h_cg_s=0.28,
        k_sf=35000.0,
        k_sr=40000.0,
        c_f=1800.0,
        c_r=2000.0,
        MR_f=0.95,
        MR_r=0.95,
        k_tf=110000.0,
        k_tr=110000.0,
        k_arb_f=12000.0,
        k_arb_r=8000.0,
    ),
}


def get_canonical_preset(name: str) -> CanonicalVehicleSpec:
    """Retrieve canonical vehicle specification by preset name."""
    clean_name = name.lower().replace("-", "_").replace(" ", "_")
    if clean_name in CANONICAL_PRESETS:
        return CANONICAL_PRESETS[clean_name]
    raise KeyError(f"Unknown preset '{name}'. Choose from: {list(CANONICAL_PRESETS.keys())}")
