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

def _magic_formula_base(kappa_or_alpha: float, B: float, C: float, D: float, E: float) -> float:
    """Core Pacejka equation."""
    # Ensure E does not cause undefined behavior
    E = min(E, 0.999) 
    Bx = B * kappa_or_alpha
    return D * np.sin(C * np.arctan(Bx - E * (Bx - np.arctan(Bx))))

def calc_tire_forces(
    Fz: float, 
    alpha_rad: float, 
    kappa: float, 
    camber_rad: float = 0.0,
    coeffs: TireCoeffs = TireCoeffs()
) -> tuple[float, float]:
    """
    Calculates combined longitudinal and lateral tire forces.
    
    Parameters:
    Fz : float
        Normal load on the tire (N)
    alpha_rad : float
        Slip angle (radians)
    kappa : float
        Longitudinal slip ratio (-1 to 1)
    camber_rad : float
        Camber angle (radians)
    coeffs : TireCoeffs
        Pacejka coefficients
        
    Returns:
    (Fx, Fy) : tuple[float, float]
        Longitudinal and lateral forces (N)
    """
    if Fz <= 0.0:
        return 0.0, 0.0

    # Nominal load Fz0 for scaling (assumed ~4000N for typical passenger car tire)
    Fz0 = 4000.0
    dfz = (Fz - Fz0) / Fz0

    # 1. Pure Longitudinal Force (Fx0)
    mu_x = coeffs.pDx1 * (1.0 - 0.05 * dfz) # Load sensitivity of friction
    Dx = mu_x * Fz
    Kx = Fz * (coeffs.pKx1 + coeffs.pKx2 * dfz) * np.exp(coeffs.pKx3 * dfz)
    Bx = Kx / (coeffs.pCx1 * Dx + 1e-6)
    
    Fx0 = _magic_formula_base(kappa, Bx, coeffs.pCx1, Dx, coeffs.pEx1)

    # 2. Pure Lateral Force (Fy0)
    mu_y = coeffs.pDy1 * (1.0 - 0.05 * dfz)
    Dy = mu_y * Fz
    # Camber thrust approximation
    gamma_thrust = Fz * np.sin(camber_rad) * 0.1 
    Dy = Dy - abs(gamma_thrust) # Reduce peak capability if heavily cambered
    
    # Cornering stiffness (simplified linear with load)
    Ky = Fz * coeffs.pKy1
    By = Ky / (coeffs.pCy1 * Dy + 1e-6)

    Fy0 = _magic_formula_base(alpha_rad, By, coeffs.pCy1, Dy, coeffs.pEy1)
    Fy0 += gamma_thrust

    # 3. Combined Slip Weighting (MF5.2 True Combined Slip)
    # Gxa: reduction of longitudinal force due to lateral slip
    # Gyk: reduction of lateral force due to longitudinal slip
    
    # Weighting functions
    Bxa = coeffs.rBx1
    Cxa = coeffs.rCx1
    Gxa = np.cos(Cxa * np.arctan(Bxa * alpha_rad))
    
    Byk = coeffs.rBy1
    Cyk = coeffs.rCy1
    Gyk = np.cos(Cyk * np.arctan(Byk * kappa))
    
    Fx = Fx0 * Gxa
    Fy = Fy0 * Gyk

    return Fx, Fy
