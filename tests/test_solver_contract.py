"""
tests/test_solver_contract.py
=============================
Tests for numerical solver contracts, documented justifications, tolerances, and diagnostics.
"""

import pytest
from suspensionlab.physics.solver_contract import (
    SOLVER_CONTRACTS,
    get_solver_contract,
    NumericalSolverContract,
)


def test_all_model_families_have_contracts():
    required_families = ["quarter_car", "half_car", "full_car", "kinematics", "handling"]
    for fam in required_families:
        contract = get_solver_contract(fam)
        assert isinstance(contract, NumericalSolverContract)
        assert len(contract.justification) > 20
        assert contract.rtol > 0
        assert contract.atol > 0
        assert contract.max_step_s > 0
        assert len(contract.failure_criteria) > 10


def test_stiff_models_mandate_implicit_solvers():
    # Stiff models must use BDF or Newton
    hc = get_solver_contract("half_car")
    assert hc.primary_solver == "BDF"
    assert hc.stiffness_regime == "Stiff"

    fc = get_solver_contract("full_car")
    assert fc.primary_solver == "BDF"

    kin = get_solver_contract("kinematics")
    assert "Newton" in kin.primary_solver


def test_stiff_ode_solver_numerical_stability():
    """Verify that stiff suspension systems integrate stably under implicit solver contract."""
    from scipy.integrate import solve_ivp
    import numpy as np
    from suspensionlab.physics.quarter_car import QuarterCarParams, _quarter_car_ode, RoadProfile

    # Very stiff quarter car setup (k_s = 500,000 N/m, high damping ratio)
    p_stiff = QuarterCarParams(m_s=300.0, m_u=35.0, k_s=500000.0, c=15000.0, k_t=300000.0)
    contract = get_solver_contract("quarter_car")

    def zr_step(t):
        return np.where(t >= 0.1, 0.05, 0.0)

    def dzr_zero(t):
        return np.zeros_like(t)

    x0 = [0.0, 0.0, 0.0, 0.0]
    t_span = (0.0, 3.0)
    
    # Solve with BDF (contract fallback for stiff regimes)
    sol_bdf = solve_ivp(
        fun=_quarter_car_ode,
        t_span=t_span,
        y0=x0,
        args=(p_stiff, zr_step, dzr_zero),
        method="BDF",
        rtol=contract.rtol,
        atol=contract.atol,
        max_step=contract.max_step_s,
    )
    assert sol_bdf.success
    assert np.all(np.isfinite(sol_bdf.y))
    # Check steady state converges to 0.05 m step
    assert abs(sol_bdf.y[0, -1] - 0.05) < 1e-3


