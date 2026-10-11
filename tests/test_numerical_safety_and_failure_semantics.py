"""
tests/test_numerical_safety_and_failure_semantics.py
===================================================
Verification suite for Numerical Safety and Explicit Failure Semantics.

Validates:
1. Tire model numerical stability (NaN, Inf, extreme slip, negative/zero Fz).
2. Physical bounds enforcement:
   - ks >= 1000 N/m
   - kt >= 10000 N/m
   - mass > 0.1 kg
   - damping >= 0
3. Explicit 7-state solver contract:
   - COMPLETED_VALID
   - COMPLETED_WITH_WARNINGS
   - FAILED_NUMERICAL
   - FAILED_INPUT
   - FAILED_PHYSICS
   - CANCELLED
   - TIMEOUT
4. JobRecord check constraint matches the contract.
"""

import pytest
import math
import numpy as np
import uuid
from suspensionlab.physics.magic_formula import (
    calc_tire_forces,
    calc_tire_forces_3d,
    PacejkaMF52TireModel,
    TireCoeffs,
)
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile
from suspensionlab.physics.half_car import HalfCarParams
from suspensionlab.physics.full_car import FullCarParams
from suspensionlab.physics.handling_model import HandlingParams
from suspensionlab.backend.database.models.job import JobRecord


def _make_full_car_params(**overrides):
    base = {
        "m_s": 1500.0,
        "I_x": 400.0,
        "I_y": 2000.0,
        "m_uf": 40.0,
        "m_ur": 40.0,
        "k_sf": 25000.0,
        "k_sr": 30000.0,
        "c_f": 2000.0,
        "c_r": 2000.0,
        "k_arb_f": 10000.0,
        "k_arb_r": 5000.0,
        "k_tf": 250000.0,
        "k_tr": 250000.0,
        "L": 2.8,
        "a": 1.2,
        "b": 1.6,
        "tw_f": 1.5,
        "tw_r": 1.5,
        "speed_mps": 20.0,
    }
    base.update(overrides)
    return FullCarParams(**base)


def test_tire_model_extreme_slip_and_zero_normal_load():
    """Tire model must stay finite under zero/negative Fz and extreme slip angles."""
    coeffs = TireCoeffs()

    # Fz <= 0 must produce 0 forces without NaN
    fx, fy = calc_tire_forces(Fz=0.0, alpha_rad=0.1, kappa=0.1, coeffs=coeffs)
    assert fx == 0.0 and fy == 0.0

    fx, fy = calc_tire_forces(Fz=-500.0, alpha_rad=0.1, kappa=0.1, coeffs=coeffs)
    assert fx == 0.0 and fy == 0.0

    # Extreme slip angles (+- 90 deg = +- pi/2 rad)
    fx, fy = calc_tire_forces(Fz=4000.0, alpha_rad=np.pi / 2, kappa=0.0, coeffs=coeffs)
    assert math.isfinite(fx)
    assert math.isfinite(fy)

    fx, fy = calc_tire_forces(Fz=4000.0, alpha_rad=-np.pi / 2, kappa=0.0, coeffs=coeffs)
    assert math.isfinite(fx)
    assert math.isfinite(fy)


def test_tire_model_nan_inf_all_channels():
    """Tire model input NaN/Inf on any input channel must not escape or produce NaN output."""
    coeffs = TireCoeffs()
    model = PacejkaMF52TireModel(coeffs)

    channels = [
        {"kappa": float("nan"), "alpha_rad": 0.0, "Fz": 4000.0},
        {"kappa": 0.0, "alpha_rad": float("inf"), "Fz": 4000.0},
        {"kappa": 0.0, "alpha_rad": 0.0, "Fz": float("nan")},
        {"kappa": float("inf"), "alpha_rad": float("inf"), "Fz": float("inf")},
    ]

    for ch in channels:
        res = model.evaluate(**ch)
        assert math.isfinite(res.Fx)
        assert math.isfinite(res.Fy)
        assert math.isfinite(res.Mz)
        assert res.is_valid is False


def test_physical_bounds_quarter_car():
    """QuarterCarParams must reject sub-physical parameters and non-finite numbers."""
    with pytest.raises(ValueError):
        QuarterCarParams(k_s=999.0)
    with pytest.raises(ValueError):
        QuarterCarParams(k_t=9999.0)
    with pytest.raises(ValueError):
        QuarterCarParams(m_s=0.05)
    with pytest.raises(ValueError):
        QuarterCarParams(m_u=-5.0)
    with pytest.raises(ValueError):
        QuarterCarParams(c=-100.0)
    with pytest.raises(ValueError):
        QuarterCarParams(k_s=float("nan"))


def test_physical_bounds_half_car():
    """HalfCarParams must reject sub-physical parameters."""
    with pytest.raises(ValueError):
        HalfCarParams(k_sf=500.0)
    with pytest.raises(ValueError):
        HalfCarParams(k_sr=500.0)
    with pytest.raises(ValueError):
        HalfCarParams(k_tf=5000.0)
    with pytest.raises(ValueError):
        HalfCarParams(k_tr=5000.0)
    with pytest.raises(ValueError):
        HalfCarParams(m_s=0.0)
    with pytest.raises(ValueError):
        HalfCarParams(I_y=-10.0)


def test_physical_bounds_full_car():
    """FullCarParams must reject sub-physical parameters."""
    with pytest.raises(ValueError):
        _make_full_car_params(k_sf=800.0)
    with pytest.raises(ValueError):
        _make_full_car_params(k_sr=800.0)
    with pytest.raises(ValueError):
        _make_full_car_params(k_tf=8000.0)
    with pytest.raises(ValueError):
        _make_full_car_params(k_tr=8000.0)
    with pytest.raises(ValueError):
        _make_full_car_params(m_s=0.0)


def test_physical_bounds_handling_model():
    """HandlingParams must reject sub-physical parameters."""
    with pytest.raises(ValueError):
        HandlingParams(K_spring_f=500.0)
    with pytest.raises(ValueError):
        HandlingParams(K_spring_r=500.0)
    with pytest.raises(ValueError):
        HandlingParams(K_arb_f=-10.0)
    with pytest.raises(ValueError):
        HandlingParams(m=0.0)


def test_job_record_status_constraint_membership():
    """JobRecord check constraint must include all 7 explicit solver states."""
    allowed_statuses = [
        "COMPLETED_VALID",
        "COMPLETED_WITH_WARNINGS",
        "FAILED_NUMERICAL",
        "FAILED_INPUT",
        "FAILED_PHYSICS",
        "CANCELLED",
        "TIMEOUT",
    ]
    status_col = JobRecord.__table__.columns["status"]
    check_constraints = [c.sqltext.text for c in status_col.constraints if hasattr(c, "sqltext")]
    constraint_found = False
    for c_text in check_constraints:
        if "chk_job_status" in c_text or "status IN" in c_text:
            constraint_found = True
            for s in allowed_statuses:
                assert f"'{s}'" in c_text, f"Status {s} missing from JobRecord check constraint: {c_text}"

    assert constraint_found, "JobRecord status check constraint not found in table metadata"
