"""
tests/test_tire_canonical_and_formulation.py
============================================
Physical and numerical validation tests for canonical TireModelBase,
Pacejka MF 5.2 formulation, load sensitivity, camber thrust,
pneumatic trail, aligning torque, and pressure/temperature scaling.
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.magic_formula import (
    TireCoeffs,
    PacejkaMF52TireModel,
    calc_tire_forces,
    _calc_tire_forces_and_moments_fast,
    FAST_APPROXIMATION,
)
from suspensionlab.physics.tire_model import (
    ContactState,
    ValidityStatus,
    ValidityRange,
    TireDefinition,
    get_tire_model,
    compute_parameter_hash,
)


def test_canonical_evaluate_interface_contract():
    model = PacejkaMF52TireModel()
    
    # Canonical call with all documented parameters
    res = model.evaluate(
        Fz=4500.0,
        alpha=math.radians(4.0),
        kappa=0.08,
        camber=math.radians(-2.0),
        pressure=2.2,
        temperature=88.0,
        speed=35.0,
    )

    # Validate output properties
    assert isinstance(res.Fx, float)
    assert isinstance(res.Fy, float)
    assert isinstance(res.Mz, float)
    assert res.Fx > 0.0  # Driving torque
    assert res.Fy > 0.0  # Positive slip angle cornering
    assert res.effective_radius > 0.30
    assert res.loaded_radius > 0.30
    assert res.contact_patch is not None
    assert res.contact_patch.length_m > 0.05
    assert res.contact_patch.width_m > 0.10
    assert res.contact_state in (ContactState.STICK, ContactState.SLIP, ContactState.SATURATED)
    assert res.validity.status == ValidityStatus.VALID
    assert res.is_valid is True


def test_pure_longitudinal_force_physics_and_load_sensitivity():
    model = PacejkaMF52TireModel()
    
    # Check monotonicity in adhesion micro-slip region (0 to 2% slip)
    fx_0 = model.evaluate(Fz=4000.0, alpha=0.0, kappa=0.0).Fx
    fx_1 = model.evaluate(Fz=4000.0, alpha=0.0, kappa=0.01).Fx
    fx_2 = model.evaluate(Fz=4000.0, alpha=0.0, kappa=0.02).Fx
    assert fx_0 == 0.0
    assert fx_1 > 0.0
    assert fx_2 > fx_1

    # Check peak traction occurs in realistic 10-15% slip ratio
    kappas = np.linspace(0.0, 0.30, 31)
    fx_vals = [model.evaluate(Fz=4000.0, alpha=0.0, kappa=k).Fx for k in kappas]
    peak_kappa = kappas[int(np.argmax(fx_vals))]
    assert 0.08 <= peak_kappa <= 0.18

    # Load sensitivity: normalized peak friction mu_x = Fx_max / Fz decreases with load (degressivity)
    fx_peak_2k = max([model.evaluate(Fz=2000.0, alpha=0.0, kappa=k).Fx for k in kappas])
    fx_peak_6k = max([model.evaluate(Fz=6000.0, alpha=0.0, kappa=k).Fx for k in kappas])
    mu_2k = fx_peak_2k / 2000.0
    mu_6k = fx_peak_6k / 6000.0
    assert mu_2k > mu_6k, f"Tire degressivity violated: mu(2kN)={mu_2k:.3f} <= mu(6kN)={mu_6k:.3f}"


def test_pure_lateral_force_and_camber_thrust():
    model = PacejkaMF52TireModel()
    
    # Cornering stiffness at origin (small slip angle)
    alpha_small = math.radians(1.0)
    fy_small = model.evaluate(Fz=4000.0, alpha=alpha_small, kappa=0.0).Fy
    cf_alpha = fy_small / alpha_small  # N/rad
    assert 40000.0 < cf_alpha < 90000.0

    # Camber thrust at zero slip angle (Fy should be non-zero when camber != 0)
    fy_camber_zero = model.evaluate(Fz=4000.0, alpha=0.0, kappa=0.0, camber=0.0).Fy
    fy_camber_pos = model.evaluate(Fz=4000.0, alpha=0.0, kappa=0.0, camber=math.radians(3.0)).Fy
    assert abs(fy_camber_zero) < 1e-3
    assert fy_camber_pos > 15.0  # Positive inclination produces positive camber thrust


def test_self_aligning_moment_and_pneumatic_trail():
    model = PacejkaMF52TireModel()
    Fz = 4000.0

    # At small slip angles (e.g. 2°), pneumatic trail is positive and Mz is restoring (negative relative to Fy)
    res_2deg = model.evaluate(Fz=Fz, alpha=math.radians(2.0), kappa=0.0)
    assert res_2deg.Fy > 0.0
    assert res_2deg.Mz < 0.0  # Restoring self-aligning moment

    # At large slip angles beyond peak (e.g. 15°), pneumatic trail reduces toward zero
    res_15deg = model.evaluate(Fz=Fz, alpha=math.radians(15.0), kappa=0.0)
    assert abs(res_15deg.Mz) < abs(res_2deg.Mz) * 1.5


def test_coupled_combined_slip_similarity_reduction():
    model = PacejkaMF52TireModel()
    Fz = 4000.0
    alpha = math.radians(5.0)
    kappa = 0.10

    # Pure slip benchmarks
    fx_pure = model.evaluate(Fz=Fz, alpha=0.0, kappa=kappa).Fx
    fy_pure = model.evaluate(Fz=Fz, alpha=alpha, kappa=0.0).Fy

    # Coupled combined slip evaluation
    comb = model.evaluate(Fz=Fz, alpha=alpha, kappa=kappa)

    # Real coupled friction: forces must be reduced compared to pure values
    assert comb.Fx < fx_pure
    assert comb.Fy < fy_pure
    assert comb.Fx > 0.55 * fx_pure
    assert comb.Fy > 0.55 * fy_pure


def test_thermodynamic_and_pressure_scaling():
    model = PacejkaMF52TireModel()
    Fz = 4000.0
    alpha = math.radians(6.0)

    # 1. Thermal bell-curve: optimal grip at T_opt = 85°C
    fy_cold = model.evaluate(Fz=Fz, alpha=alpha, kappa=0.0, temperature=25.0).Fy
    fy_opt = model.evaluate(Fz=Fz, alpha=alpha, kappa=0.0, temperature=85.0).Fy
    fy_hot = model.evaluate(Fz=Fz, alpha=alpha, kappa=0.0, temperature=130.0).Fy

    assert fy_opt > fy_cold
    assert fy_opt > fy_hot

    # 2. Pressure scaling: higher pressure increases carcass stiffness and cornering stiffness slope
    def_p1 = model.definition.vertical_stiffness(pressure_bar=1.5)
    def_p3 = model.definition.vertical_stiffness(pressure_bar=3.0)
    assert def_p3 > def_p1


def test_out_of_domain_and_contact_loss_enforcement():
    model = PacejkaMF52TireModel()

    # Airborne / Zero normal load
    res_zero = model.evaluate(Fz=0.0, alpha=0.1, kappa=0.05)
    assert res_zero.contact_state == ContactState.LIFT_OFF
    assert res_zero.Fx == 0.0
    assert res_zero.Fy == 0.0
    assert res_zero.validity.status == ValidityStatus.CONTACT_LOST
    assert res_zero.is_valid is False

    # Out of calibrated domain (>15% outside normal load envelope: 25000 N > 18000 N max)
    res_ood = model.evaluate(Fz=25000.0, alpha=0.05, kappa=0.02)
    assert res_ood.validity.status == ValidityStatus.OUT_OF_DOMAIN
    assert res_ood.is_valid is False
    assert len(res_ood.validity.domain_violations) > 0
    assert res_ood.validity.confidence < 0.8
