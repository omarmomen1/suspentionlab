"""
tests/test_physics_domain_admissibility.py
==========================================
Verification of Physics Domain Admissibility & Parameter Classification Matrix:
1. Zero spring stiffness rejected with mathematical justification (singular stiffness matrix).
2. Zero tire vertical stiffness rejected with justification (carcass collapse / decoupling).
3. Zero damping accepted as VALID_BUT_EXTREME (undamped oscillator).
4. Negative damping rejected as PHYSICALLY_INVALID (2nd law violation / energy injection).
5. Zero/negative tire radius rejected as PHYSICALLY_INVALID & NUMERICALLY_INVALID.
6. Wheelbase geometric inconsistency (L != a + b) rejected as PHYSICALLY_INVALID.
7. Negative normal load clamped to zero (unilateral ground contact, tarmac cannot pull tension).
8. Zero normal load evaluated safely as CONTACT_LOST (wheel liftoff / airborne).
9. Extreme slip angles (alpha = 45 deg) and extreme speeds (v = 120 m/s) evaluate smoothly without NaN.
10. Full coverage across registered models in domain admissibility registry.
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.domain_admissibility import (
    PHYSICS_PARAMETER_REGISTRY,
    AdmissibilityClass,
    validate_admissibility,
)
from suspensionlab.physics.quarter_car import QuarterCarParams
from suspensionlab.physics.half_car import HalfCarParams
from suspensionlab.physics.full_car import FullCarParams
from suspensionlab.physics.handling_model import HandlingParams
from suspensionlab.physics.tire_model import TireDefinition, get_tire_model
from suspensionlab.physics.dynamic_lap_sim import DynamicVehicleParams


def test_registry_contains_all_core_models():
    """Verify registry covers quarter car, half car, full car, tire, kinematics, and speed."""
    assert "quarter_car.k_s" in PHYSICS_PARAMETER_REGISTRY
    assert "quarter_car.k_t" in PHYSICS_PARAMETER_REGISTRY
    assert "quarter_car.c" in PHYSICS_PARAMETER_REGISTRY
    assert "geometry.wheelbase_L" in PHYSICS_PARAMETER_REGISTRY
    assert "geometry.track_width" in PHYSICS_PARAMETER_REGISTRY
    assert "tire.unloaded_radius" in PHYSICS_PARAMETER_REGISTRY
    assert "tire.normal_load_Fz" in PHYSICS_PARAMETER_REGISTRY
    assert "tire.slip_angle_alpha" in PHYSICS_PARAMETER_REGISTRY
    assert "aero.speed_mps" in PHYSICS_PARAMETER_REGISTRY


def test_zero_and_subcritical_spring_stiffness_rejected():
    """k_s = 0 or < 1000 N/m must be rejected with mathematical justification."""
    # Test registry classification
    cls_zero, msg_zero = validate_admissibility("quarter_car.k_s", 0.0)
    assert cls_zero == AdmissibilityClass.PHYSICALLY_INVALID
    assert "singular stiffness matrix" in msg_zero.lower() or "lower bound" in msg_zero.lower()

    # Test QuarterCarParams model rejection
    with pytest.raises(ValueError, match="at least 1,000 N/m"):
        QuarterCarParams(k_s=0.0)

    with pytest.raises(ValueError, match="at least 1,000 N/m"):
        QuarterCarParams(k_s=500.0)


def test_zero_and_subcritical_tire_stiffness_rejected():
    """k_t = 0 or < 10,000 N/m must be rejected with justification."""
    cls_zero, _ = validate_admissibility("quarter_car.k_t", 0.0)
    assert cls_zero == AdmissibilityClass.PHYSICALLY_INVALID

    with pytest.raises(ValueError, match="at least 10,000 N/m"):
        QuarterCarParams(k_t=0.0)

    with pytest.raises(ValueError, match="at least 10,000 N/m"):
        QuarterCarParams(k_t=5000.0)


def test_zero_damping_admissible_as_extreme_and_negative_damping_rejected():
    """c = 0 is VALID_BUT_EXTREME; negative damping c < 0 is PHYSICALLY_INVALID."""
    # Classification check
    cls_zero, _ = validate_admissibility("quarter_car.c", 0.0)
    assert cls_zero == AdmissibilityClass.VALID_BUT_EXTREME

    cls_neg, msg_neg = validate_admissibility("quarter_car.c", -100.0)
    assert cls_neg == AdmissibilityClass.PHYSICALLY_INVALID

    # Negative damping rejected by model
    with pytest.raises(ValueError, match="non-negative"):
        QuarterCarParams(c=-50.0)

    # c = 0 allowed by model (undamped oscillator)
    undamped = QuarterCarParams(c=0.0)
    assert undamped.c == 0.0
    from suspensionlab.physics.quarter_car import build_state_space
    A, B = build_state_space(undamped)
    assert A.shape == (4, 4)
    # Undamped system has purely imaginary eigenvalues (zero real part, no energy dissipation)
    eigs = np.linalg.eigvals(A)
    assert np.all(np.abs(np.real(eigs)) < 1e-10)


def test_zero_and_negative_tire_radius_rejected():
    """Tire unloaded radius R0 <= 0 must be rejected."""
    cls_zero, _ = validate_admissibility("tire.unloaded_radius", 0.0)
    assert cls_zero == AdmissibilityClass.PHYSICALLY_INVALID

    with pytest.raises(ValueError, match="strictly positive"):
        TireDefinition(unloaded_radius=0.0)

    with pytest.raises(ValueError, match="strictly positive"):
        TireDefinition(unloaded_radius=-0.3)


def test_wheelbase_geometric_inconsistency_rejected():
    """Wheelbase L != a + b must be rejected in HalfCar, FullCar, and DynamicVehicle."""
    # Half car inconsistency
    with pytest.raises(ValueError, match="inconsistent"):
        HalfCarParams(a=1.2, b=1.4, L=3.5)  # Expected 2.6, got 3.5

    # Full car inconsistency
    with pytest.raises(ValueError, match="inconsistent"):
        FullCarParams(
            m_s=600.0, I_x=250.0, I_y=900.0, m_uf=40.0, m_ur=40.0,
            k_sf=35000.0, k_sr=40000.0, c_f=2500.0, c_r=2800.0,
            k_arb_f=10000.0, k_arb_r=8000.0, k_tf=200000.0, k_tr=200000.0,
            L=3.5, a=1.2, b=1.4, tw_f=1.6, tw_r=1.6, speed_mps=30.0
        )

    # Dynamic vehicle inconsistency
    with pytest.raises(ValueError, match="does not match"):
        DynamicVehicleParams(wheelbase_m=4.0, a_m=1.3, b_m=1.4)


def test_negative_normal_load_clamped_unilateral_contact():
    """Pacejka model under negative normal load must clamp to 0 and report CONTACT_LOST without crashing."""
    tire = get_tire_model("mf52")
    res = tire.evaluate(Fz=-500.0, alpha=0.05, kappa=0.02)
    assert res.forces.Fx == 0.0
    assert res.forces.Fy == 0.0
    assert res.forces.Mz == 0.0
    assert res.is_valid is False
    assert any("contact lost" in w.lower() for w in res.warnings)


def test_zero_normal_load_liftoff_handled_safely():
    """Normal load Fz = 0 (wheel airborne) produces zero forces and reports CONTACT_LOST."""
    tire = get_tire_model("mf52")
    res = tire.evaluate(Fz=0.0, alpha=0.1, kappa=0.0)
    assert res.forces.Fx == 0.0
    assert res.forces.Fy == 0.0
    assert res.forces.Mz == 0.0
    assert res.is_valid is False


def test_extreme_slip_and_speed_evaluate_smoothly():
    """Extreme slip angles (e.g. 45 deg) and high speeds (120 m/s) evaluate without NaN."""
    tire = get_tire_model("mf52")
    res = tire.evaluate(Fz=4000.0, alpha=math.radians(45.0), kappa=0.5, speed=120.0)
    assert not math.isnan(res.forces.Fy)
    assert not math.isnan(res.forces.Fx)
    assert not math.isinf(res.forces.Fy)
    assert res.forces.Fy != 0.0
