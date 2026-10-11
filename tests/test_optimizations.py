"""
tests/test_optimizations.py
===========================
Verification of full-car monte carlo, stribeck friction, and bump stops.
"""
import pytest
import numpy as np
from unittest.mock import patch
from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, simulate_time_response
from suspensionlab.physics.half_car import HalfCarParams, simulate_time_response as sim_hc
from suspensionlab.physics.full_car import FullCarParams
from suspensionlab.physics.monte_carlo import run_monte_carlo_sweep

def test_quarter_car():
    with pytest.raises(ValueError):
        QuarterCarParams(stribeck_fs=10.0, stribeck_fc=20.0)

    with pytest.raises(ValueError):
        QuarterCarParams(stribeck_vs=0.0)

    p = QuarterCarParams(bump_stop_rate=500000.0, bump_stop_jounce=0.01, stribeck_fs=100.0, stribeck_fc=50.0)
    rp = RoadProfile(profile_type="iso8608", duration=2.0)
    res = simulate_time_response(p, rp)
    assert res is not None
    assert len(res["time"]) > 0

def test_half_car():
    p = HalfCarParams(stribeck_fs_f=100.0, stribeck_fc_f=50.0, stribeck_fs_r=100.0, stribeck_fc_r=50.0)
    rp = RoadProfile(profile_type="step", amplitude=0.1, duration=1.0)
    res = sim_hc(p, rp)
    assert res is not None
    assert len(res["time"]) > 0

def test_monte_carlo():
    import gc
    gc.collect()
    num_runs = 2
    y0_batch = np.zeros((num_runs, 14))
    t_eval = np.linspace(0, 1, 100)
    y_out_batch = np.zeros((num_runs, 100, 14))
    
    params = FullCarParams(
        m_s=1200.0, I_x=300.0, I_y=1200.0, m_uf=40.0, m_ur=40.0,
        k_sf=30000.0, k_sr=35000.0, c_f=3000.0, c_r=3500.0,
        k_arb_f=10000.0, k_arb_r=5000.0, k_tf=250000.0, k_tr=250000.0,
        L=2.6, a=1.2, b=1.4, tw_f=1.6, tw_r=1.6, speed_mps=20.0
    )
    p_arr = params.to_array()
    params_batch = np.array([p_arr, p_arr])
    
    G_TIME = t_eval
    G_U = np.zeros((100, 4))
    
    with patch("os.cpu_count", return_value=2):
        run_monte_carlo_sweep(y0_batch, t_eval, y_out_batch, G_TIME, G_U, params_batch)
    assert not np.isnan(y_out_batch).any()
