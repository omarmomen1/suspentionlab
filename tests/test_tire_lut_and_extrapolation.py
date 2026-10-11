"""
tests/test_tire_lut_and_extrapolation.py
========================================
Tests for Multi-axis Tire Lookup Table (TireLUTModel), interpolation accuracy,
boundary checking, and strict OUT_OF_DOMAIN domain enforcement.
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.tire_model import (
    TireLUTModel,
    TireDefinition,
    ContactState,
    ValidityStatus,
)


def test_tire_lut_model_gridded_evaluation():
    # Build synthetic test bench table
    Fz_grid = np.array([2000.0, 4000.0, 6000.0])
    alpha_grid = np.linspace(-0.20, 0.20, 9)
    kappa_grid = np.linspace(-0.20, 0.20, 9)

    # Simple synthetic force surface: Fx ~ Fz * sin(10*kappa), Fy ~ Fz * sin(10*alpha)
    Fx_table = np.zeros((3, 9, 9))
    Fy_table = np.zeros((3, 9, 9))
    Mz_table = np.zeros((3, 9, 9))

    for i, fz in enumerate(Fz_grid):
        for j, a in enumerate(alpha_grid):
            for k, ka in enumerate(kappa_grid):
                Fx_table[i, j, k] = fz * 1.1 * np.sin(np.arctan(12.0 * ka))
                Fy_table[i, j, k] = fz * 1.0 * np.sin(np.arctan(10.0 * a))
                Mz_table[i, j, k] = -0.03 * Fy_table[i, j, k]

    lut_model = TireLUTModel(
        Fz_grid=Fz_grid,
        alpha_grid=alpha_grid,
        kappa_grid=kappa_grid,
        Fx_table=Fx_table,
        Fy_table=Fy_table,
        Mz_table=Mz_table,
    )

    # 1. Exact grid point evaluation
    res_exact = lut_model.evaluate(Fz=4000.0, alpha=0.0, kappa=0.10)
    assert res_exact.Fx > 3000.0
    assert abs(res_exact.Fy) < 1.0
    assert res_exact.validity.status == ValidityStatus.VALID
    assert res_exact.is_valid is True

    # 2. Interpolated intermediate evaluation point
    res_interp = lut_model.evaluate(Fz=3000.0, alpha=0.05, kappa=0.05)
    assert res_interp.Fx > 0.0
    assert res_interp.Fy > 0.0
    assert res_interp.validity.status == ValidityStatus.VALID


def test_tire_lut_out_of_domain_enforcement():
    Fz_grid = np.array([2000.0, 4000.0])
    alpha_grid = np.array([-0.15, 0.0, 0.15])
    kappa_grid = np.array([-0.15, 0.0, 0.15])
    Fx_table = np.ones((2, 3, 3)) * 1000.0
    Fy_table = np.ones((2, 3, 3)) * 1000.0

    lut_model = TireLUTModel(
        Fz_grid=Fz_grid,
        alpha_grid=alpha_grid,
        kappa_grid=kappa_grid,
        Fx_table=Fx_table,
        Fy_table=Fy_table,
    )

    # Evaluation point significantly outside calibrated grid (Fz=9000 N > 4000 N max)
    res_ood = lut_model.evaluate(Fz=9000.0, alpha=0.0, kappa=0.0)
    assert res_ood.validity.status == ValidityStatus.OUT_OF_DOMAIN
    assert res_ood.is_valid is False
    assert len(res_ood.warnings) > 0
    assert "Load over-range" in " ".join(res_ood.warnings)
