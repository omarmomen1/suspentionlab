"""
tests/test_tire_combined_slip_and_tir.py
========================================
Independent test suite for Pacejka MF 5.2 combined-slip weighting, friction ellipse
saturation bounds, NaN handling, and .tir parser functionality.
"""

import pytest
import numpy as np

from suspensionlab.physics.magic_formula import (
    TireCoeffs,
    calc_tire_forces,
    calc_tire_forces_3d,
)
from suspensionlab.physics.tir_parser import parse_tir_file, export_tir_file


def test_combined_slip_small_angle_preservation():
    """
    Verify that at small combined slips (kappa = 0.01, alpha = 0.01 rad),
    Pacejka cosine weighting keeps Fx and Fy within <= 5% of pure-slip forces,
    avoiding severe drops from radial slip approximations.
    """
    coeffs = TireCoeffs()
    Fz = 4000.0

    Fx_pure, _ = calc_tire_forces(Fz, alpha_rad=0.0, kappa=0.01, coeffs=coeffs)
    _, Fy_pure = calc_tire_forces(Fz, alpha_rad=0.01, kappa=0.0, coeffs=coeffs)
    Fx_comb, Fy_comb = calc_tire_forces(Fz, alpha_rad=0.01, kappa=0.01, coeffs=coeffs)

    drop_x_pct = (Fx_pure - Fx_comb) / Fx_pure * 100.0
    drop_y_pct = (Fy_pure - Fy_comb) / Fy_pure * 100.0

    assert drop_x_pct <= 5.0, f"Fx drop {drop_x_pct:.2f}% exceeds 5% tolerance"
    assert drop_y_pct <= 5.0, f"Fy drop {drop_y_pct:.2f}% exceeds 5% tolerance"
    assert drop_x_pct >= 0.0, "Combined slip should not generate higher force than pure slip"
    assert drop_y_pct >= 0.0, "Combined slip should not generate higher force than pure slip"


def test_friction_ellipse_bound():
    """Verify that combined vector force sqrt(Fx^2 + Fy^2) never exceeds 1.02 * mu_peak * Fz."""
    coeffs = TireCoeffs()
    Fz = 4000.0
    mu_peak = max(abs(coeffs.pDx1), abs(coeffs.pDy1))
    f_max_theoretical = mu_peak * Fz

    for kappa in [0.02, 0.05, 0.10, 0.20, 0.50]:
        for alpha in [0.02, 0.05, 0.10, 0.20, 0.35]:
            fx, fy = calc_tire_forces(Fz, alpha_rad=alpha, kappa=kappa, coeffs=coeffs)
            f_tot = np.hypot(fx, fy)
            assert f_tot <= 1.02 * f_max_theoretical, (
                f"Tire force {f_tot:.1f} N exceeds friction ellipse bound {f_max_theoretical:.1f} N "
                f"at kappa={kappa}, alpha={alpha}"
            )


def test_force_sign_symmetry():
    """Verify anti-symmetry: Fx(-kappa) = -Fx(kappa) and Fy(-alpha) = -Fy(alpha)."""
    coeffs = TireCoeffs()
    Fz = 4000.0

    fx1, fy1 = calc_tire_forces(Fz, alpha_rad=0.05, kappa=0.05, coeffs=coeffs)
    fx2, fy2 = calc_tire_forces(Fz, alpha_rad=-0.05, kappa=-0.05, coeffs=coeffs)

    assert abs(fx1 + fx2) < 1.0, f"Longitudinal force asymmetry: fx1={fx1}, fx2={fx2}"
    assert abs(fy1 + fy2) < 1.0, f"Lateral force asymmetry: fy1={fy1}, fy2={fy2}"


def test_nan_and_inf_graceful_handling():
    """Verify that NaN, infinite, or non-physical negative normal loads return (0.0, 0.0)."""
    assert calc_tire_forces(np.nan, 0.05, 0.05) == (0.0, 0.0)
    assert calc_tire_forces(4000.0, np.nan, 0.05) == (0.0, 0.0)
    assert calc_tire_forces(4000.0, 0.05, np.nan) == (0.0, 0.0)
    assert calc_tire_forces(4000.0, 0.05, 0.05, camber_rad=np.nan) == (0.0, 0.0)
    assert calc_tire_forces(np.inf, 0.05, 0.05) == (0.0, 0.0)
    assert calc_tire_forces(-500.0, 0.05, 0.05) == (0.0, 0.0)
    assert calc_tire_forces_3d(np.nan, 0.05, 0.05) == (0.0, 0.0, 0.0)


def test_tir_file_parser_and_exporter():
    """Verify parsing and round-tripping of standard .tir file with canonical MF 5.2 parameters."""
    sample_tir = """
! Sample Tyre Property File
[MDI_HEADER]
FILE_TYPE = 'tir'
FILE_VERSION = 3.0

[VERTICAL]
FNOMIN = 4250.0

[LONGITUDINAL_COEFFICIENTS]
PCX1 = 1.62
PDX1 = 1.18
PDX2 = -0.09
PKX1 = 23.5
RBX1 = 12.8
LMUX = 0.98

[LATERAL_COEFFICIENTS]
PCY1 = 1.35
PDY1 = 1.08
PDY2 = -0.11
PKY1 = 16.2
RBY1 = 11.2
LMUY = 0.95
LKY = 1.02
"""
    coeffs = parse_tir_file(sample_tir)

    assert coeffs.Fz0 == 4250.0
    assert coeffs.f_nomin == 4250.0
    assert coeffs.pCx1 == 1.62
    assert coeffs.pDx1 == 1.18
    assert coeffs.pDx2 == -0.09
    assert coeffs.pKx1 == 23.5
    assert coeffs.rBx1 == 12.8
    assert getattr(coeffs, "lambda_mux", 1.0) == 0.98
    assert coeffs.pCy1 == 1.35
    assert coeffs.pDy1 == 1.08
    assert coeffs.rBy1 == 11.2
    assert hasattr(coeffs, "camber_stiffness_rad")

    exported = export_tir_file(coeffs)
    assert "FNOMIN                   = 4250.0" in exported
    assert "PDX1                     = 1.18000" in exported
