"""
physics/magic_formula.py
========================
SuspensionLab PRO — Pacejka Magic Formula Tire Model
Provides non-linear lateral and longitudinal tire forces.

Reference: Pacejka, H. B. "Tire and Vehicle Dynamics"
Formula structure: Y(x) = D * sin(C * arctan(B*x - E*(B*x - arctan(B*x))))
"""

import numpy as np
from dataclasses import dataclass
from numba import njit

@dataclass
class TireCoeffs:
    """
    Pacejka Magic Formula coefficients for a typical performance tire.
    B = Stiffness factor
    C = Shape factor
    D = Peak value
    E = Curvature factor
    """
    # Lateral (Pure slip)
    pCy1: float = 1.30   # Shape factor
    pDy1: float = 1.05   # Peak friction mu_y
    pEy1: float = -0.50  # Curvature
    pKy1: float = 15.0   # Cornering stiffness coeff
    pKy2: float = 2.0    # Load dependency of cornering stiffness

    # Longitudinal (Pure slip)
    pCx1: float = 1.60
    pDx1: float = 1.10
    pEx1: float = 0.30
    pKx1: float = 22.0
    pKx2: float = 0.4
    pKx3: float = 0.4

    # Combined slip (friction ellipse)
    rBx1: float = 10.0
    rBy1: float = 10.0
    rCx1: float = 1.0
    rCy1: float = 1.0

    def to_array(self) -> np.ndarray:
        """Serialize coefficients to a contiguous float64 array for Numba JIT."""
        return np.array([
            self.pCy1, self.pDy1, self.pEy1, self.pKy1, self.pKy2,
            self.pCx1, self.pDx1, self.pEx1, self.pKx1, self.pKx2, self.pKx3,
            self.rBx1, self.rBy1, self.rCx1, self.rCy1
        ], dtype=np.float64)

@njit(fastmath=True, cache=True)
def _magic_formula_base(kappa_or_alpha: float, B: float, C: float, D: float, E: float) -> float:
    """Core Pacejka equation."""
    # Ensure E does not cause undefined behavior
    E = min(E, 0.999) 
    Bx = B * kappa_or_alpha
    return D * np.sin(C * np.arctan(Bx - E * (Bx - np.arctan(Bx))))

@njit(fastmath=True, cache=True)
def _calc_tire_forces_fast(
    Fz: float, 
    alpha_rad: float, 
    kappa: float, 
    camber_rad: float,
    coeffs: np.ndarray
):
    """JIT-compiled pure scalar tire force evaluation."""
    if np.isnan(Fz) or np.isinf(Fz) or Fz <= 0.0:
        return 0.0, 0.0
    
    if np.isnan(alpha_rad) or np.isinf(alpha_rad) or np.isnan(kappa) or np.isinf(kappa):
        return 0.0, 0.0

    # Unpack flat array
    pCy1, pDy1, pEy1, pKy1, pKy2, pCx1, pDx1, pEx1, pKx1, pKx2, pKx3, rBx1, rBy1, rCx1, rCy1 = coeffs

    # Clamp Fz to prevent exponential overflow in load sensitivity
    Fz = min(Fz, 100000.0)

    # Nominal load Fz0 for scaling (assumed ~4000N for typical passenger car tire)
    Fz0 = 4000.0
    dfz = (Fz - Fz0) / Fz0

    # 1. Pure Longitudinal Force (Fx0)
    mu_x = pDx1 * (1.0 - 0.05 * dfz) # Load sensitivity of friction
    Dx = mu_x * Fz
    Kx = Fz * (pKx1 + pKx2 * dfz) * np.exp(pKx3 * dfz)
    Bx = Kx / (pCx1 * Dx + 1e-6)
    
    Fx0 = _magic_formula_base(kappa, Bx, pCx1, Dx, pEx1)

    # 2. Pure Lateral Force (Fy0)
    mu_y = pDy1 * (1.0 - 0.05 * dfz)
    Dy = mu_y * Fz
    # Camber thrust approximation
    gamma_thrust = Fz * np.sin(camber_rad) * 0.1 
    Dy = Dy - abs(gamma_thrust) # Reduce peak capability if heavily cambered
    
    Ky = pKy1 * Fz0 * np.sin(2.0 * np.arctan(Fz / (pKy2 * Fz0)))
    By = Ky / (pCy1 * Dy + 1e-6)

    Fy0 = _magic_formula_base(alpha_rad, By, pCy1, Dy, pEy1)
    Fy0 += gamma_thrust

    # 3. Combined Slip Weighting
    kappa_peak = 1.0 / (Bx + 1e-6) * np.tan(np.pi / (2.0 * pCx1)) if pCx1 > 0 else 0.1
    alpha_peak = 1.0 / (By + 1e-6) * np.tan(np.pi / (2.0 * pCy1)) if pCy1 > 0 else 0.1
    
    rho_x = kappa / (kappa_peak + 1e-6)
    rho_y = alpha_rad / (alpha_peak + 1e-6)
    rho = np.sqrt(rho_x**2 + rho_y**2)
    
    if rho > 1e-6:
        Fx = Fx0 * (abs(rho_x) / rho)
        Fy = Fy0 * (abs(rho_y) / rho)
    else:
        Fx = Fx0
        Fy = Fy0

    return Fx, Fy

@njit(fastmath=True, cache=True)
def calc_tire_forces_vectorized(
    Fz_arr: np.ndarray, 
    alpha_arr: np.ndarray, 
    kappa_arr: np.ndarray, 
    camber_arr: np.ndarray,
    coeffs: np.ndarray,
    out_Fx: np.ndarray,
    out_Fy: np.ndarray
):
    """Zero-copy vectorized bulk processing."""
    for i in range(len(Fz_arr)):
        out_Fx[i], out_Fy[i] = _calc_tire_forces_fast(
            Fz_arr[i], alpha_arr[i], kappa_arr[i], camber_arr[i], coeffs
        )

def calc_tire_forces(
    Fz: float, 
    alpha_rad: float, 
    kappa: float, 
    camber_rad: float = 0.0,
    coeffs: TireCoeffs = None
) -> tuple[float, float]:
    """
    Backwards-compatible wrapper.
    For maximum performance in loops, use _calc_tire_forces_fast directly
    with the serialized coefficients array.
    """
    if coeffs is None:
        coeffs = TireCoeffs()
    return _calc_tire_forces_fast(Fz, alpha_rad, kappa, camber_rad, coeffs.to_array())
