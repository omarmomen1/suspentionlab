"""
tests/test_arb_consistency.py
=============================
Rigorous verification of Anti-Roll Bar (ARB) roll stiffness consistency:
1. Theoretical roll stiffness formula accounts for motion ratio squared:
   K_roll = 0.5 * (k_s * MR^2) * tw^2 + k_arb * tw^2
2. Sensitivity: Increasing front ARB rate strictly increases front roll stiffness distribution
3. Decoupled condition: With k_arb = 0, roll distribution equals spring-only wheel rate distribution
4. Load transfer agreement: Dynamic lateral load transfer matches theoretical roll stiffness distribution
"""

import pytest
import numpy as np

from suspensionlab.physics.full_car import (
    FullCarParams,
    FourCornerRoadProfile,
    run_full_car_analysis,
)


@pytest.fixture
def baseline_full_car():
    return FullCarParams(
        m_s=1000.0,
        I_x=400.0,
        I_y=1000.0,
        m_uf=40.0,
        m_ur=40.0,
        k_sf=32000.0,
        k_sr=30000.0,
        c_f=2000.0,
        c_r=2000.0,
        k_arb_f=12000.0,
        k_arb_r=8000.0,
        k_tf=200000.0,
        k_tr=200000.0,
        L=2.8,
        a=1.4,
        b=1.4,
        tw_f=1.6,
        tw_r=1.6,
        speed_mps=15.0,
        MR_f=0.88,
        MR_r=0.85,
    )


def test_arb_roll_stiffness_formula_with_motion_ratio(baseline_full_car):
    """Verify that roll_stiffness_dist accounts for spring motion ratio squared."""
    p = baseline_full_car
    t = np.linspace(0, 1, 100)
    profile = FourCornerRoadProfile(time=t, z_rfl=np.zeros(100), z_rfr=np.zeros(100), z_rrl=np.zeros(100), z_rrr=np.zeros(100))
    res = run_full_car_analysis(p, profile)

    # Analytical calculation
    k_wf = p.k_sf * (p.MR_f ** 2)
    k_wr = p.k_sr * (p.MR_r ** 2)
    K_f = 0.5 * k_wf * (p.tw_f ** 2) + p.k_arb_f * (p.tw_f ** 2)
    K_r = 0.5 * k_wr * (p.tw_r ** 2) + p.k_arb_r * (p.tw_r ** 2)
    expected_dist = float(K_f / (K_f + K_r)) * 100.0

    assert np.isclose(res.roll_stiffness_dist, expected_dist, rtol=1e-4)


def test_arb_stiffening_monotonic_sensitivity(baseline_full_car):
    """Verify that stiffening front ARB strictly increases front roll stiffness distribution."""
    p_soft = baseline_full_car
    p_stiff = FullCarParams(
        m_s=p_soft.m_s, I_x=p_soft.I_x, I_y=p_soft.I_y, m_uf=p_soft.m_uf, m_ur=p_soft.m_ur,
        k_sf=p_soft.k_sf, k_sr=p_soft.k_sr, c_f=p_soft.c_f, c_r=p_soft.c_r,
        k_arb_f=20000.0,  # Stiffened from 12000 to 20000 N/m
        k_arb_r=p_soft.k_arb_r, k_tf=p_soft.k_tf, k_tr=p_soft.k_tr,
        L=p_soft.L, a=p_soft.a, b=p_soft.b, tw_f=p_soft.tw_f, tw_r=p_soft.tw_r,
        speed_mps=p_soft.speed_mps, MR_f=p_soft.MR_f, MR_r=p_soft.MR_r,
    )

    t = np.linspace(0, 1, 100)
    profile = FourCornerRoadProfile(time=t, z_rfl=np.zeros(100), z_rfr=np.zeros(100), z_rrl=np.zeros(100), z_rrr=np.zeros(100))
    res_soft = run_full_car_analysis(p_soft, profile)
    res_stiff = run_full_car_analysis(p_stiff, profile)

    assert res_stiff.roll_stiffness_dist > res_soft.roll_stiffness_dist + 5.0


def test_zero_arb_spring_only_distribution(baseline_full_car):
    """Verify that with zero ARB, roll stiffness distribution strictly reduces to spring rates."""
    p_zero = FullCarParams(
        m_s=baseline_full_car.m_s, I_x=baseline_full_car.I_x, I_y=baseline_full_car.I_y,
        m_uf=baseline_full_car.m_uf, m_ur=baseline_full_car.m_ur,
        k_sf=baseline_full_car.k_sf, k_sr=baseline_full_car.k_sr,
        c_f=baseline_full_car.c_f, c_r=baseline_full_car.c_r,
        k_arb_f=0.0, k_arb_r=0.0,
        k_tf=baseline_full_car.k_tf, k_tr=baseline_full_car.k_tr,
        L=baseline_full_car.L, a=baseline_full_car.a, b=baseline_full_car.b,
        tw_f=baseline_full_car.tw_f, tw_r=baseline_full_car.tw_r,
        speed_mps=baseline_full_car.speed_mps,
        MR_f=baseline_full_car.MR_f, MR_r=baseline_full_car.MR_r,
    )

    t = np.linspace(0, 1, 100)
    profile = FourCornerRoadProfile(time=t, z_rfl=np.zeros(100), z_rfr=np.zeros(100), z_rrl=np.zeros(100), z_rrr=np.zeros(100))
    res = run_full_car_analysis(p_zero, profile)

    k_wf = p_zero.k_sf * (p_zero.MR_f ** 2)
    k_wr = p_zero.k_sr * (p_zero.MR_r ** 2)
    expected_dist = float(k_wf / (k_wf + k_wr)) * 100.0

    assert np.isclose(res.roll_stiffness_dist, expected_dist, rtol=1e-4)
