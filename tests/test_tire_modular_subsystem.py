"""
tests/test_tire_modular_subsystem.py
====================================
Comprehensive tests for the modular TireModel subsystem, reference curves,
contact state detection, dynamic tire radius, and boundary warnings.
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.magic_formula import (
    TireCoeffs,
    PacejkaMF52TireModel,
    calc_tire_forces,
)
from suspensionlab.physics.tire_model import (
    ContactState,
    TireDefinition,
    ValidityRange,
    get_tire_model,
    compute_parameter_hash,
)


def test_tire_definition_radius_vs_load():
    td = TireDefinition(
        unloaded_radius=0.330,
        nominal_pressure_bar=2.0,
        vertical_stiffness_k_t=250_000.0,
    )
    # Zero load: radius equals unloaded radius
    assert td.loaded_radius(0.0) == 0.330
    assert td.effective_radius(0.0) == 0.330

    # Under 5000 N load
    r_l = td.loaded_radius(5000.0, pressure_bar=2.0)
    # Deflection = 5000 / 250000 = 0.02 m = 20 mm -> R_l = 310 mm
    assert math.isclose(r_l, 0.310, abs_tol=1e-3)

    # Dynamic radius function R = f(Fz, p, T, kappa)
    r_dyn = td.radius_vs_load(5000.0, pressure_bar=2.0, T_c=80.0, kappa=0.05)
    assert 0.310 <= r_dyn <= 0.335


def test_contact_loss_when_fz_zero_or_negative():
    model = PacejkaMF52TireModel()
    
    # 1. Zero normal load
    res_zero = model.evaluate(Fz=0.0, alpha_rad=0.1, kappa=0.05)
    assert res_zero.contact_state == ContactState.LOST
    assert res_zero.forces.Fx == 0.0
    assert res_zero.forces.Fy == 0.0
    assert len(res_zero.warnings) > 0
    assert "CONTACT LOST" in res_zero.warnings[0]

    # 2. Negative normal load (airborne)
    res_neg = model.evaluate(Fz=-500.0, alpha_rad=0.1, kappa=0.05)
    assert res_neg.contact_state == ContactState.LOST
    assert res_neg.forces.Fx == 0.0
    assert res_neg.forces.Fy == 0.0


def test_boundary_operating_warnings():
    model = PacejkaMF52TireModel()
    
    # Exceeding slip angle and temperature limits
    res = model.evaluate(
        Fz=4000.0,
        alpha_rad=math.radians(25.0), # 25° > 17° limit
        kappa=0.0,
        T_c=145.0, # 145°C > 130°C limit
        pressure_bar=4.2 # 4.2 bar > 3.5 bar limit
    )
    assert len(res.warnings) >= 3
    warn_text = " ".join(res.warnings)
    assert "Slip angle outside calibrated range" in warn_text
    assert "Tire overheating warning" in warn_text
    assert "Inflation pressure" in warn_text


def test_reference_pure_and_combined_curves():
    model = PacejkaMF52TireModel()
    Fz = 4000.0

    # 1. Pure longitudinal curve Fx(kappa, Fz)
    kappas = np.linspace(-0.25, 0.25, 25)
    fx_vals = [model.calc_forces(Fz, 0.0, k).Fx for k in kappas]
    # Check peak is reached around 10-15% slip
    max_fx = max(fx_vals)
    assert 4000.0 < max_fx < 5000.0
    assert fx_vals[0] < 0 and fx_vals[-1] > 0

    # 2. Pure lateral curve Fy(alpha, Fz)
    alphas = np.linspace(-math.radians(15.0), math.radians(15.0), 25)
    fy_vals = [model.calc_forces(Fz, a, 0.0).Fy for a in alphas]
    max_fy = max(fy_vals)
    assert 3000.0 < max_fy < 4500.0
    assert fy_vals[0] < 0 and fy_vals[-1] > 0

    # 3. Combined slip coupling: Fx(kappa, alpha, Fz) & Fy(kappa, alpha, Fz)
    fx_pure = model.calc_forces(Fz, 0.0, 0.1).Fx
    fy_pure = model.calc_forces(Fz, math.radians(6.0), 0.0).Fy

    comb = model.calc_forces(Fz, math.radians(6.0), 0.1)
    # Both forces must be reduced due to friction coupling (Similarity Method)
    assert comb.Fx < fx_pure
    assert comb.Fy < fy_pure
    assert comb.Fx > 0.6 * fx_pure
    assert comb.Fy > 0.6 * fy_pure
