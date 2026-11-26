"""
physics/magic_formula.py
========================
SuspensionLab PRO — Pacejka Magic Formula Tire Model (MF 5.2 Canonical)

Implements the canonical Pacejka Magic Formula tire model with:
  - Correct MF 5.2 pure-slip formulations (longitudinal and lateral)
  - Similarity Method combined-slip (Gxα, Gyκ weighting functions)
  - Pneumatic trail & residual torque for self-aligning moment Mz
  - Full load sensitivity on all coefficients (dfz degressive friction)
  - Camber thrust and curvature effects via standard Pacejka coefficients
  - Horizontal and vertical shifts (ply steer, conicity)
  - Documented inflation pressure and thermodynamic grip scaling
  - Fast approximation labeling (FAST_APPROXIMATION)
  - Numba JIT compilation for all critical evaluation paths

References
----------
- Pacejka, H.B. "Tire and Vehicle Dynamics", 3rd Ed., Elsevier 2012.
  Chapter 4: Semi-Empirical Tire Models.
- Bakker, E., Nyborg, L. & Pacejka, H.B. "Tyre Modelling for Use in
  Vehicle Dynamics Studies", SAE 870421, 1987.
- ISO 15037-1:2006, Road vehicles — Vehicle dynamics test methods.

Formulation Equations
---------------------
1. Normalized Normal Load:
   dfz = (Fz - Fz0) / Fz0

2. Pure Longitudinal Force Fx0(κ):
   Shx = pHx1 + pHx2 · dfz
   κx = κ + Shx
   μx = (pDx1 + pDx2 · dfz) · (1 - pDx3 · γ²) · λ_μ(p, T)
   Dx = μx · Fz
   Kx = Fz · (pKx1 + pKx2 · dfz) · exp(pKx3 · dfz) · λ_K(p)
   Bx = Kx / (pCx1 · Dx + ε)
   Ex = (pEx1 + pEx2 · dfz + pEx3 · dfz²) · (1 - pEx4 · sgn(κx))
   Svx = Fz · (pVx1 + pVx2 · dfz)
   Fx0 = Dx · sin(pCx1 · arctan(Bx · κx - Ex · (Bx · κx - arctan(Bx · κx)))) + Svx

3. Pure Lateral Force Fy0(α, γ):
   Shy = pHy1 + pHy2 · dfz + pHy3 · γ
   αy = α + Shy
   μy = (pDy1 + pDy2 · dfz) · (1 - pDy3 · γ²) · λ_μ(p, T)
   Dy = μy · Fz
   Ky = pKy1 · Fz0 · sin(2 · arctan(Fz / (pKy2 · Fz0 + ε))) · (1 - pKy3 · |γ|) · λ_K(p)
   By = Ky / (pCy1 · Dy + ε)
   Ey = (pEy1 + pEy2 · dfz) · (1 - (pEy3 + pEy4 · γ) · sgn(αy))
   Svy = Fz · (pVy1 + pVy2 · dfz + (pVy3 + pVy4 · dfz) · γ)
   Fy0 = Dy · sin(pCy1 · arctan(By · αy - Ey · (By · αy - arctan(By · αy)))) + Svy

4. Aligning Moment Mz0(α, γ, Fz):
   t(α, γ, Fz) = Dt · cos(Ct · arctan(Bt · αt - Et · (Bt · αt - arctan(Bt · αt)))) · cos(α)
   Mzr(α, γ, Fz) = Dr · cos(Cr · arctan(Br · αr))
   Mz0 = -t · Fy0' + Mzr

5. Combined Slip (Similarity Method):
   Gxα = cos(rCx1 · arctan(Bxα · (α + rHx1))) / cos(rCx1 · arctan(Bxα · rHx1))
   where Bxα = rBx1 · cos(arctan(rBx2 · κ))
   Gyκ = cos(rCy1 · arctan(Byκ · (κ + rHy1))) / cos(rCy1 · arctan(Byκ · rHy1))
   where Byκ = rBy1 · cos(arctan(rBy2 · α))
   Fx = Fx0 · Gxα
   Fy = Fy0 · Gyκ
   Mz = -t · Fy + Mzr · Gyκ
"""

import os
_FASTMATH = os.environ.get('SUSPENSIONLAB_FASTMATH', '1') == '1'

import math
import numpy as np
from dataclasses import dataclass, field
try:
    from numba import njit
except ImportError:
    def njit(*args, **kwargs):
        def decorator(f):
            return f
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator
from typing import Any, Dict, List, Optional, Tuple, Union

from suspensionlab.physics.tire_model import (
    TireModelBase,
    TireForces,
    TireEvaluationResult,
    ContactState,
    ValidityRange,
    ValidityStatus,
    ValidityDomainResult,
    ContactPatchGeometry,
    TireDefinition,
    TireModelMetadata,
    compute_parameter_hash,
)

# Explicit constant identifying fast approximations
FAST_APPROXIMATION = "FAST_APPROXIMATION"
HIGH_FIDELITY = "HIGH_FIDELITY"


# ─────────────────────────────────────────────────────────────────────────────
# Coefficient dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TireCoeffs:
    """Pacejka MF 5.2 tire coefficients.

    Naming convention follows Pacejka standard:
      p<D|C|E|K|H|V><x|y><1..4>  — pure slip forces
      q<B|C|D|E|H|V><z><1..10>  — aligning moment & pneumatic trail
      r<B|C|H><x|y><1..3>        — combined slip (Similarity Method)
      p<P><x|y><1..4>            — inflation pressure scaling

    Attributes
    ----------
    Fz0 : float
        Nominal (rated) tire load [N].
    """
    # ── Nominal load & geometry ───────────────────────────────────────────
    Fz0: float = 4000.0    # [N] Nominal normal load
    p0_bar: float = 2.0    # [bar] Nominal inflation pressure

    # ── Lateral (Pure slip) ───────────────────────────────────────────────
    pCy1: float = 1.30     # Shape factor Cy
    pDy1: float = 1.05     # Peak friction μy at Fz0
    pDy2: float = -0.10    # Load variation of μy
    pDy3: float = 0.05     # Camber variation of μy
    pEy1: float = -0.50    # Curvature factor Ey at Fz0
    pEy2: float = -0.10    # Load variation of Ey
    pEy3: float = 0.0      # Camber variation of Ey (linear)
    pEy4: float = 0.0      # Camber variation of Ey (squared)
    pKy1: float = 15.0     # Cornering stiffness Ky max
    pKy2: float = 2.0      # Load at which Ky reaches max
    pKy3: float = 0.02     # Camber variation of Ky
    pHy1: float = 0.0      # Horizontal shift Shy at Fz0
    pHy2: float = 0.0      # Load variation of Shy
    pHy3: float = 0.0      # Camber-induced Shy (ply steer)
    pVy1: float = 0.0      # Vertical shift Svy at Fz0
    pVy2: float = 0.0      # Load variation of Svy
    pVy3: float = 0.08     # Camber-induced Svy (camber thrust)
    pVy4: float = 0.02     # Camber-induced Svy (load-dependent)

    # ── Longitudinal (Pure slip) ──────────────────────────────────────────
    pCx1: float = 1.60     # Shape factor Cx
    pDx1: float = 1.10     # Peak friction μx at Fz0
    pDx2: float = -0.10    # Load variation of μx
    pDx3: float = 0.0      # Camber variation of μx
    pEx1: float = 0.30     # Curvature factor Ex at Fz0
    pEx2: float = 0.0      # Load variation of Ex
    pEx3: float = 0.0      # Load variation of Ex (squared)
    pEx4: float = 0.0      # Slip-sign sensitivity of Ex
    pKx1: float = 22.0     # Slip stiffness Kx at Fz0
    pKx2: float = 0.4      # Load variation of Kx
    pKx3: float = 0.4      # Exponential load variation of Kx
    pHx1: float = 0.0      # Horizontal shift Shx at Fz0
    pHx2: float = 0.0      # Load variation of Shx
    pVx1: float = 0.0      # Vertical shift Svx at Fz0
    pVx2: float = 0.0      # Load variation of Svx

    # ── Combined slip — Similarity Method ─────────────────────────────────
    rBx1: float = 10.0     # Slope factor for Gxα
    rBx2: float = 8.0      # Kappa influence on Gxα slope
    rCx1: float = 1.0      # Shape factor for Gxα
    rBy1: float = 10.0     # Slope factor for Gyκ
    rBy2: float = 8.0      # Alpha influence on Gyκ slope
    rCy1: float = 1.0      # Shape factor for Gyκ
    rHx1: float = 0.0      # Shift in Gxα
    rHy1: float = 0.0      # Shift in Gyκ
    camber_stiffness_rad: float = 0.85
    f_nomin: float = 4000.0
    lambda_mux: float = 1.0
    lambda_muy: float = 1.0
    lambda_ky: float = 1.0

    # ── Aligning Moment & Pneumatic Trail ─────────────────────────────────
    qBz1: float = 9.0      # Trail slope factor
    qBz2: float = -2.0     # Load variation of trail slope
    qBz3: float = 0.0      # Camber variation of trail slope
    qCz1: float = 1.15     # Shape factor for trail
    qDz1: float = 0.035    # Peak pneumatic trail [m] at Fz0
    qDz2: float = -0.005   # Load variation of trail
    qDz3: float = 0.0      # Camber variation of trail
    qDz4: float = 0.0      # Camber squared variation of trail
    qEz1: float = -1.5     # Trail curvature factor
    qEz2: float = 0.0      # Load variation of trail curvature
    qEz3: float = 0.0      # Camber variation of trail curvature
    qEz4: float = 0.0      # Sign-dependent variation of trail curvature
    qHz1: float = 0.0      # Horizontal shift of trail
    qHz2: float = 0.0      # Load variation of trail shift
    qHz3: float = 0.0      # Camber-induced trail shift
    qHz4: float = 0.0      # Camber load-induced trail shift

    # Residual moment parameters
    qDz6: float = 0.0      # Peak residual moment [N·m] at Fz0
    qDz7: float = 0.0      # Load variation of residual moment
    qDz8: float = 0.05     # Camber variation of residual moment
    qDz9: float = 0.02     # Camber load-variation of residual moment
    qBz9: float = 12.0     # Slope factor of residual moment
    qBz10: float = 0.0     # Load variation of residual slope

    # ── Pressure Sensitivity ──────────────────────────────────────────────
    pPx1: float = -0.06    # Pressure variation of μx
    pPx2: float = 0.18     # Pressure variation of Kx
    pPy1: float = -0.06    # Pressure variation of μy
    pPy2: float = 0.18     # Pressure variation of Ky

    def to_array(self) -> np.ndarray:
        """Serialize all coefficients to a contiguous float64 array for Numba JIT.

        Length: 70 coefficients.
        """
        return np.array([
            # Nominal load & pressure [0..1]
            self.Fz0, self.p0_bar,
            # Lateral pure slip (18 coefficients) [2..19]
            self.pCy1, self.pDy1, self.pDy2, self.pDy3,
            self.pEy1, self.pEy2, self.pEy3, self.pEy4,
            self.pKy1, self.pKy2, self.pKy3,
            self.pHy1, self.pHy2, self.pHy3,
            self.pVy1, self.pVy2, self.pVy3, self.pVy4,
            # Longitudinal pure slip (15 coefficients) [20..34]
            self.pCx1, self.pDx1, self.pDx2, self.pDx3,
            self.pEx1, self.pEx2, self.pEx3, self.pEx4,
            self.pKx1, self.pKx2, self.pKx3,
            self.pHx1, self.pHx2,
            self.pVx1, self.pVx2,
            # Combined slip (8 coefficients) [35..42]
            self.rBx1, self.rBx2, self.rCx1,
            self.rBy1, self.rBy2, self.rCy1,
            self.rHx1, self.rHy1,
            # Aligning moment / trail (14 coefficients) [43..56]
            self.qBz1, self.qBz2, self.qBz3, self.qCz1,
            self.qDz1, self.qDz2, self.qDz3, self.qDz4,
            self.qEz1, self.qEz2, self.qEz3, self.qEz4,
            self.qHz1, self.qHz2,
            # Residual moment (6 coefficients) [57..62]
            self.qDz6, self.qDz7, self.qDz8, self.qDz9, self.qBz9, self.qBz10,
            # Scaling & pressure factors (7 coefficients) [63..69]
            self.lambda_mux, self.lambda_muy, self.lambda_ky,
            self.pPx1, self.pPx2, self.pPy1, self.pPy2,
        ], dtype=np.float64)


# ─────────────────────────────────────────────────────────────────────────────
# Core Numba-JIT functions
# ─────────────────────────────────────────────────────────────────────────────

@njit(cache=True)
def _magic_formula_base(x: float, B: float, C: float, D: float, E: float) -> float:
    """Core Pacejka equation: Y = D · sin(C · arctan(B·x - E·(B·x - arctan(B·x))))"""
    E = min(E, 0.999)
    Bx = B * x
    return D * np.sin(C * np.arctan(Bx - E * (Bx - np.arctan(Bx))))


@njit(cache=True)
def _calc_tire_forces_fast(
    Fz: float,
    alpha_rad: float,
    kappa: float,
    camber_rad: float,
    coeffs: np.ndarray,
    pressure_bar: float = 2.0,
    T_c: float = 85.0,
) -> Tuple[float, float]:
    """JIT-compiled MF 5.2 tire force evaluation with thermodynamic & inflation pressure scaling.

    Returns (Fx, Fy) [N].
    """
    if not (np.isfinite(Fz) and np.isfinite(alpha_rad) and np.isfinite(kappa) and np.isfinite(camber_rad)) or Fz <= 0.0:
        return 0.0, 0.0

    Fz = min(Fz, 100000.0)

    # ── Unpack coefficients ───────────────────────────────────────────────
    Fz0 = coeffs[0]
    p0_bar = coeffs[1] if coeffs[1] > 0.0 else 2.0
    if Fz0 <= 0.0:
        Fz0 = 4000.0

    # Lateral pure slip
    pCy1 = coeffs[2]
    pDy1 = coeffs[3];  pDy2 = coeffs[4];  pDy3 = coeffs[5]
    pEy1 = coeffs[6];  pEy2 = coeffs[7];  pEy3 = coeffs[8];  pEy4 = coeffs[9]
    pKy1 = coeffs[10]; pKy2 = coeffs[11]; pKy3 = coeffs[12]
    pHy1 = coeffs[13]; pHy2 = coeffs[14]; pHy3 = coeffs[15]
    pVy1 = coeffs[16]; pVy2 = coeffs[17]; pVy3 = coeffs[18]; pVy4 = coeffs[19]

    # Longitudinal pure slip
    pCx1 = coeffs[20]
    pDx1 = coeffs[21]; pDx2 = coeffs[22]; pDx3 = coeffs[23]
    pEx1 = coeffs[24]; pEx2 = coeffs[25]; pEx3 = coeffs[26]; pEx4 = coeffs[27]
    pKx1 = coeffs[28]; pKx2 = coeffs[29]; pKx3 = coeffs[30]
    pHx1 = coeffs[31]; pHx2 = coeffs[32]
    pVx1 = coeffs[33]; pVx2 = coeffs[34]

    # Combined slip (Similarity Method)
    rBx1 = coeffs[35]; rBx2 = coeffs[36]; rCx1 = coeffs[37]
    rBy1 = coeffs[38]; rBy2 = coeffs[39]; rCy1 = coeffs[40]
    rHx1 = coeffs[41]; rHy1 = coeffs[42]

    # ── Scaling & Pressure Unpack with Backward-Compatible Guard ─────────
    if len(coeffs) >= 70:
        lambda_mux = coeffs[63]
        lambda_muy = coeffs[64]
        lambda_ky  = coeffs[65]
        pPx1 = coeffs[66]; pPx2 = coeffs[67]
        pPy1 = coeffs[68]; pPy2 = coeffs[69]
    elif len(coeffs) >= 68:
        lambda_mux = coeffs[61]
        lambda_muy = coeffs[62]
        lambda_ky  = coeffs[63]
        pPx1 = coeffs[64]; pPx2 = coeffs[65]
        pPy1 = coeffs[66]; pPy2 = coeffs[67]
    else:
        lambda_mux = 1.0
        lambda_muy = 1.0
        lambda_ky  = 1.0
        pPx1 = -0.06; pPx2 = 0.18
        pPy1 = -0.06; pPy2 = 0.18

    # ── Thermodynamic & Inflation Pressure Scaling ────────────────────────
    delta_T = T_c - 85.0
    mu_thermal = max(0.55, 1.0 - 0.00015 * (delta_T ** 2))

    dp = (pressure_bar - p0_bar) / p0_bar
    mu_press_x = max(0.60, 1.0 + pPx1 * dp)
    k_press_x  = max(0.60, 1.0 + pPx2 * dp)
    mu_press_y = max(0.60, 1.0 + pPy1 * dp)
    k_press_y  = max(0.60, 1.0 + pPy2 * dp)

    lambda_mu_x = mu_thermal * mu_press_x * lambda_mux
    lambda_k_x  = k_press_x
    lambda_mu_y = mu_thermal * mu_press_y * lambda_muy
    lambda_k_y  = k_press_y * lambda_ky

    # Normalized load variation
    dfz = (Fz - Fz0) / Fz0
    gamma = camber_rad

    # ── 1. Pure Longitudinal Force Fx0(κ) ─────────────────────────────────
    Shx = pHx1 + pHx2 * dfz
    kappa_x = kappa + Shx

    mu_x = (pDx1 + pDx2 * dfz) * (1.0 - pDx3 * gamma * gamma) * lambda_mu_x
    mu_x = max(mu_x, 0.0)
    Dx = mu_x * Fz

    Kx = Fz * (pKx1 + pKx2 * dfz) * np.exp(pKx3 * dfz) * lambda_k_x
    Cx = pCx1
    Bx = Kx / (Cx * Dx + 1e-6)

    Ex = (pEx1 + pEx2 * dfz + pEx3 * dfz * dfz) * (1.0 - pEx4 * np.sign(kappa_x))
    Ex = min(Ex, 0.999)

    Svx = Fz * (pVx1 + pVx2 * dfz)
    Fx0 = _magic_formula_base(kappa_x, Bx, Cx, Dx, Ex) + Svx

    # ── 2. Pure Lateral Force Fy0(α) ──────────────────────────────────────
    Shy = pHy1 + pHy2 * dfz + pHy3 * gamma
    alpha_y = alpha_rad + Shy

    mu_y = (pDy1 + pDy2 * dfz) * (1.0 - pDy3 * gamma * gamma) * lambda_mu_y
    mu_y = max(mu_y, 0.0)
    Dy = mu_y * Fz

    # Wave 5A fix: standard MF 5.2 / PAC2002 .tir files store PKY1 with a
    # NEGATIVE sign (e.g. PKY1 = -15.0) because of the tyre-axis lateral-force
    # sign convention. Cornering stiffness magnitude must not flip sign:
    # normalise with abs(pKy1) so standard .tir uploads yield positive Ky
    # instead of collapsing lateral grip (measured: 0.033 G at 89.8 deg
    # sideslip in production testing before this fix).
    Ky = abs(pKy1) * Fz0 * np.sin(2.0 * np.arctan(Fz / (pKy2 * Fz0 + 1e-6))) * (1.0 - pKy3 * abs(gamma)) * lambda_k_y
    Cy = pCy1
    By = Ky / (Cy * Dy + 1e-6)

    Ey = (pEy1 + pEy2 * dfz) * (1.0 - (pEy3 + pEy4 * gamma) * np.sign(alpha_y))
    Ey = min(Ey, 0.999)

    Svy = Fz * (pVy1 + pVy2 * dfz + (pVy3 + pVy4 * dfz) * gamma)
    Fy0 = _magic_formula_base(alpha_y, By, Cy, Dy, Ey) + Svy

    # ── 3. Combined Slip (Similarity Method) ──────────────────────────────
    alpha_s = alpha_rad + rHx1
    kappa_s = kappa + rHy1

    Bxalpha = rBx1 * np.cos(np.arctan(rBx2 * kappa))
    num_gxa = np.cos(rCx1 * np.arctan(Bxalpha * alpha_s))
    den_gxa = np.cos(rCx1 * np.arctan(Bxalpha * rHx1))
    Gxalpha = 1.0 if abs(den_gxa) < 1e-10 else num_gxa / den_gxa
    Gxalpha = max(0.0, min(1.0, Gxalpha))

    Bykappa = rBy1 * np.cos(np.arctan(rBy2 * alpha_rad))
    num_gyk = np.cos(rCy1 * np.arctan(Bykappa * kappa_s))
    den_gyk = np.cos(rCy1 * np.arctan(Bykappa * rHy1))
    Gykappa = 1.0 if abs(den_gyk) < 1e-10 else num_gyk / den_gyk
    Gykappa = max(0.0, min(1.0, Gykappa))

    Fx = Fx0 * Gxalpha
    Fy = Fy0 * Gykappa

    # Friction ellipse saturation guard
    mu_peak = max(abs(mu_x), abs(mu_y))
    F_max = mu_peak * Fz
    F_tot = np.hypot(Fx, Fy)
    if F_max > 0.0 and F_tot > F_max:
        scale = F_max / F_tot
        Fx *= scale
        Fy *= scale

    return Fx, Fy


@njit(cache=True)
def _calc_tire_forces_and_moments_fast(
    Fz: float,
    alpha_rad: float,
    kappa: float,
    camber_rad: float,
    coeffs: np.ndarray,
    pressure_bar: float = 2.0,
    T_c: float = 85.0,
) -> Tuple[float, float, float, float]:
    if not (np.isfinite(Fz) and np.isfinite(alpha_rad) and np.isfinite(kappa) and np.isfinite(camber_rad)) or Fz <= 0.0:
        return 0.0, 0.0, 0.0, 0.0

    Fx, Fy = _calc_tire_forces_fast(
        Fz, alpha_rad, kappa, camber_rad, coeffs, pressure_bar, T_c
    )

    Fz0 = coeffs[0] if coeffs[0] > 0.0 else 4000.0
    dfz = (Fz - Fz0) / Fz0
    gamma = camber_rad

    # Unpack trail parameters
    if len(coeffs) >= 56:
        qBz1 = coeffs[43]; qBz2 = coeffs[44]; qBz3 = coeffs[45]; qCz1 = coeffs[46]
        qDz1 = coeffs[47]; qDz2 = coeffs[48]; qDz3 = coeffs[49]; qDz4 = coeffs[50]
        qEz1 = coeffs[51]; qEz2 = coeffs[52]; qEz3 = coeffs[53]; qEz4 = coeffs[54]
        qHz1 = coeffs[55]
    else:
        qBz1 = 9.0; qBz2 = -2.0; qBz3 = 0.0; qCz1 = 1.15
        qDz1 = 0.035; qDz2 = -0.005; qDz3 = 0.0; qDz4 = 0.0
        qEz1 = -1.5; qEz2 = 0.0; qEz3 = 0.0; qEz4 = 0.0
        qHz1 = 0.0

    # Trail calculation t(alpha_t)
    alpha_t = alpha_rad + qHz1
    Bt = (qBz1 + qBz2 * dfz) * (1.0 + qBz3 * abs(gamma))
    Ct = qCz1
    Dt = Fz * (qDz1 + qDz2 * dfz) * (1.0 + qDz3 * gamma + qDz4 * gamma * gamma) / Fz0
    Et = (qEz1 + qEz2 * dfz + qEz3 * dfz * dfz) * (1.0 + qEz4 * np.sign(alpha_t))
    Et = min(Et, 0.999)

    Bt_alpha = Bt * alpha_t
    t_trail = Dt * np.cos(Ct * np.arctan(Bt_alpha - Et * (Bt_alpha - np.arctan(Bt_alpha)))) * np.cos(alpha_rad)

    # Residual moment Mzr
    if len(coeffs) >= 63:
        qDz6 = coeffs[57]; qDz7 = coeffs[58]; qDz8 = coeffs[59]; qDz9 = coeffs[60]
        qBz9 = coeffs[61]; qBz10 = coeffs[62]
    elif len(coeffs) >= 61:
        qDz6 = coeffs[57]; qDz7 = coeffs[58]; qDz8 = coeffs[59]; qBz9 = coeffs[60]
        qDz9 = 0.02; qBz10 = 0.0
    else:
        qDz6 = 0.0; qDz7 = 0.0; qDz8 = 0.05; qDz9 = 0.02
        qBz9 = 12.0; qBz10 = 0.0

    Dr = Fz * (qDz6 + qDz7 * dfz + (qDz8 + qDz9 * dfz) * gamma)
    Br = qBz9 + qBz10 * dfz
    Cr = 1.0
    Mzr = Dr * np.cos(Cr * np.arctan(Br * (alpha_rad + qHz1)))

    # Self-aligning torque Mz = -t * Fy + Mzr
    Mz = -float(t_trail * Fy) + float(Mzr)

    return Fx, Fy, Mz, t_trail


@njit(cache=True)
def calc_tire_forces_vectorized(
    Fz_arr: np.ndarray,
    alpha_arr: np.ndarray,
    kappa_arr: np.ndarray,
    camber_arr: np.ndarray,
    coeffs: np.ndarray,
    out_Fx: np.ndarray,
    out_Fy: np.ndarray
):
    """Zero-copy vectorized bulk processing over arrays."""
    for i in range(len(Fz_arr)):
        out_Fx[i], out_Fy[i] = _calc_tire_forces_fast(
            Fz_arr[i], alpha_arr[i], kappa_arr[i], camber_arr[i], coeffs
        )


def calc_tire_forces(
    Fz: float,
    alpha_rad: float,
    kappa: float,
    camber_rad: float = 0.0,
    coeffs: Optional[TireCoeffs] = None,
    pressure_bar: float = 2.0,
    T_c: float = 85.0,
) -> Tuple[float, float]:
    """Canonical function wrapper returning (Fx, Fy) [N]."""
    if not (math.isfinite(Fz) and math.isfinite(alpha_rad) and math.isfinite(kappa) and math.isfinite(camber_rad)) or Fz <= 0.0:
        return 0.0, 0.0

    if coeffs is None:
        coeffs = TireCoeffs()
    return _calc_tire_forces_fast(
        Fz, alpha_rad, kappa, camber_rad, coeffs.to_array(), pressure_bar, T_c
    )


def calc_tire_forces_3d(
    Fz: float,
    alpha_rad: float,
    kappa: float,
    camber_rad: float = 0.0,
    coeffs: Optional[TireCoeffs] = None,
    pressure_bar: float = 2.0,
    T_c: float = 85.0,
) -> Tuple[float, float, float]:
    """Canonical function wrapper returning (Fx, Fy, Mz) [N, N, N·m]."""
    if not (math.isfinite(Fz) and math.isfinite(alpha_rad) and math.isfinite(kappa) and math.isfinite(camber_rad)) or Fz <= 0.0:
        return 0.0, 0.0, 0.0

    if coeffs is None:
        coeffs = TireCoeffs()
    Fx, Fy, Mz, _ = _calc_tire_forces_and_moments_fast(
        Fz, alpha_rad, kappa, camber_rad, coeffs.to_array(), pressure_bar, T_c
    )
    return Fx, Fy, Mz


class PacejkaMF52TireModel(TireModelBase):
    """Production Pacejka MF 5.2 Tire Model implementation adhering strictly to TireModelBase."""

    def __init__(
        self,
        coeffs: Optional[TireCoeffs] = None,
        definition: Optional[TireDefinition] = None,
        source: str = "Pacejka MF 5.2 Calibrated Parameter Set",
    ):
        self.coeffs = coeffs if coeffs is not None else TireCoeffs()
        self._definition = definition if definition is not None else TireDefinition()
        self._val_range = ValidityRange()
        self._metadata = TireModelMetadata(
            model_id="mf52",
            model_version="5.2.1-canonical",
            parameter_hash=compute_parameter_hash(self.coeffs),
            validity_range=self._val_range,
            tire_definition=self._definition,
            source=source,
            solver="Pacejka Analytical Closed-Form / Numba-JIT",
            backend="High-Fidelity Coupled Slip",
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
        """Canonical evaluation interface returning full TireEvaluationResult."""
        alpha_rad = kwargs.get("alpha_rad", alpha)
        camber_rad = kwargs.get("camber_rad", camber)
        p_bar = kwargs.get("pressure_bar", pressure)
        t_c = kwargs.get("T_c", temperature)
        v_speed = kwargs.get("v_x", speed)

        # Check for NaN / Inf inputs
        has_nan_inf = any(
            isinstance(v, (int, float)) and (math.isnan(v) or math.isinf(v))
            for v in (Fz, alpha_rad, kappa, camber_rad, p_bar, t_c, v_speed)
        )

        val_res = self._val_range.check(
            Fz, alpha_rad, kappa, camber_rad, p_bar, t_c, v_speed
        )

        if has_nan_inf or Fz <= 0.0:
            if has_nan_inf:
                val_res.is_valid = False
                val_res.status = ValidityStatus.OUT_OF_DOMAIN
                val_res.confidence = 0.0
                val_res.warnings.append("NUMERICAL SAFETY VIOLATION: Input contains NaN or Inf.")

            return TireEvaluationResult(
                forces=TireForces(Fx=0.0, Fy=0.0, Mz=0.0),
                contact_state=ContactState.LIFT_OFF,
                warnings=val_res.warnings,
                metadata=self._metadata,
                effective_radius=self._definition.unloaded_radius,
                loaded_radius=self._definition.unloaded_radius,
                validity=val_res,
            )

        # 3D force & moment evaluation via JIT core
        Fx, Fy, Mz, trail = _calc_tire_forces_and_moments_fast(
            Fz, alpha_rad, kappa, camber_rad, self.coeffs.to_array(),
            pressure_bar=p_bar, T_c=t_c
        )

        # Contact patch geometry and dynamic radii
        cp_geom = self._definition.contact_patch_geometry(Fz, p_bar)
        r_l = self._definition.loaded_radius(Fz, p_bar)
        r_eff = self._definition.effective_radius(Fz, p_bar, kappa)

        # Contact state assessment
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
