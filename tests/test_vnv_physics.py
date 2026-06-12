import numpy as np
import pytest
from scipy.integrate import solve_ivp

from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    run_quarter_car_analysis,
    compute_frequency_response,
    compute_modal_properties,
    _quarter_car_ode
)

from suspensionlab.physics.full_car import (
    FullCarParams,
    FourCornerRoadProfile,
    run_full_car_analysis
)

from suspensionlab.physics.half_car import (
    HalfCarParams,
    simulate_time_response as sim_hc
)

from suspensionlab.physics.handling_model import (
    HandlingParams,
    simulate_maneuver
)

class TestQuarterCarVnV:
    def test_steady_state_step_response(self):
        """
        Verify that a step input to the road profile results in a steady-state
        where both sprung and unsprung masses track the road perfectly.
        """
        p = QuarterCarParams()
        profile = RoadProfile(profile_type="step", amplitude=0.05, duration=10.0)
        res = run_quarter_car_analysis(p, profile)
        
        # Check final values
        final_z_s = res.z_s[-1]
        final_z_u = res.z_u[-1]
        
        np.testing.assert_allclose(final_z_s, 0.05, atol=1e-3)
        np.testing.assert_allclose(final_z_u, 0.05, atol=1e-3)
        
        # Check velocities and accelerations approach 0
        np.testing.assert_allclose(res.dz_s[-1], 0.0, atol=1e-3)
        np.testing.assert_allclose(res.dz_u[-1], 0.0, atol=1e-3)
        np.testing.assert_allclose(res.ddz_s[-1], 0.0, atol=1e-3)
        
        # Suspension travel approaches 0
        np.testing.assert_allclose(res.susp_travel[-1], 0.0, atol=1e-3)

    def test_dc_transmissibility(self):
        """
        Verify that at f -> 0, the transmissibility magnitude |Zs/Zr| and |Zu/Zr| approaches 1.0.
        """
        p = QuarterCarParams()
        res = compute_frequency_response(p, f_min=0.001, f_max=1.0, n_points=10)
        
        np.testing.assert_allclose(res["transmissibility_body"][0], 1.0, atol=1e-3)
        np.testing.assert_allclose(res["transmissibility_wheel"][0], 1.0, atol=1e-3)

    def test_undamped_natural_frequencies(self):
        """
        Verify the eigenvalue solution for natural frequencies matches analytical formulas 
        when damping is zero.
        """
        p = QuarterCarParams(c=0.0, c_t=0.0)
        
        # Analytical formulas for the coupled 2-DOF system (roots of characteristic equation)
        a = 1.0
        b = (p.k_w / p.m_s) + ((p.k_w + p.k_t) / p.m_u)
        c = (p.k_w * p.k_t) / (p.m_s * p.m_u)
        
        w2_1 = (b - np.sqrt(b**2 - 4*c)) / 2.0
        w2_2 = (b + np.sqrt(b**2 - 4*c)) / 2.0
        
        omega_n_s_expected = np.sqrt(w2_1)
        omega_n_u_expected = np.sqrt(w2_2)
        
        res = compute_modal_properties(p)
        
        np.testing.assert_allclose(res["omega_n_s"], omega_n_s_expected, atol=1e-5)
        np.testing.assert_allclose(res["omega_n_u"], omega_n_u_expected, atol=1e-5)

    @pytest.mark.parametrize("initial_z", [0.05, 0.1, 0.2])
    def test_energy_conservation(self, initial_z):
        """Verify that total mechanical energy is conserved in free undamped vibration."""
        p_qc = QuarterCarParams(c=0, c_t=0)
        def zr_zero(t): return np.zeros_like(t)
        def dzr_zero(t): return np.zeros_like(t)
        
        x0 = [initial_z, 0.0, 0.0, 0.0]
        sol = solve_ivp(
            fun=_quarter_car_ode,
            t_span=(0, 10.0),
            y0=x0,
            args=(p_qc, zr_zero, dzr_zero),
            method="RK45",
            t_eval=np.linspace(0, 10.0, 1000),
            rtol=1e-8, atol=1e-10
        )
        z_s, dz_s, z_u, dz_u = sol.y
        KE = 0.5 * p_qc.m_s * dz_s**2 + 0.5 * p_qc.m_u * dz_u**2
        PE = 0.5 * p_qc.k_w * (z_s - z_u)**2 + 0.5 * p_qc.k_t * z_u**2
        E_total = KE + PE
        
        e_drift = np.max(E_total) - np.min(E_total)
        assert e_drift < 1e-3

    def test_momentum_conservation(self):
        """Verify that total momentum is conserved for a free-floating state."""
        p_float = QuarterCarParams(k_s=0, c=0, k_t=0, c_t=0)
        def zr_zero(t): return np.zeros_like(t)
        def dzr_zero(t): return np.zeros_like(t)
        
        x0_mom = [0.0, 2.0, 0.0, 0.0] # v_s = 2.0 m/s
        sol_mom = solve_ivp(
            fun=_quarter_car_ode, t_span=(0, 2.0), y0=x0_mom,
            args=(p_float, zr_zero, dzr_zero), method="RK45",
            t_eval=np.linspace(0, 2.0, 100), rtol=1e-8, atol=1e-10
        )
        P_total = p_float.m_s * sol_mom.y[1] + p_float.m_u * sol_mom.y[3]
        p_drift = np.max(P_total) - np.min(P_total)
        assert p_drift < 1e-5


class TestHalfCarVnV:
    def test_geometric_constraints(self):
        """Verify that inconsistent wheelbase configurations raise ValueErrors."""
        with pytest.raises(ValueError):
            HalfCarParams(a=1.0, b=1.0, L=3.0)
            
    @pytest.mark.parametrize("speed_mps", [10.0, 20.0, 30.0])
    def test_wheelbase_delay(self, speed_mps):
        """Verify that rear wheel correctly follows front wheel with delay L/v."""
        p_hc = HalfCarParams(speed_mps=speed_mps, a=1.5, b=1.5, L=3.0)
        prof_hc = RoadProfile(profile_type="step", amplitude=0.1, duration=2.0)
        res_hc = sim_hc(p_hc, prof_hc)
        
        delay = p_hc.L / speed_mps
        t_front_hits = 0.5
        t_rear_hits = 0.5 + delay
        
        t_arr = res_hc["time"]
        
        z_rf_front_hit = np.interp(t_front_hits + 0.01, t_arr, res_hc["z_rf"])
        assert z_rf_front_hit > 0.05
        
        z_rr_rear_hit = np.interp(t_rear_hits + 0.01, t_arr, res_hc["z_rr"])
        assert z_rr_rear_hit > 0.05
        
        z_rr_before = np.interp(t_rear_hits - 0.01, t_arr, res_hc["z_rr"])
        assert z_rr_before < 0.01


class TestFullCarVnV:
    @pytest.fixture
    def symmetric_full_car(self):
        return FullCarParams(
            m_s=1000.0, I_x=400.0, I_y=1000.0, m_uf=40.0, m_ur=40.0,
            k_sf=30000.0, k_sr=30000.0, c_f=2000.0, c_r=2000.0,
            k_arb_f=10000.0, k_arb_r=10000.0, k_tf=200000.0, k_tr=200000.0,
            L=3.0, a=1.5, b=1.5, tw_f=1.5, tw_r=1.5, speed_mps=10.0
        )

    def test_pure_heave_decoupling(self, symmetric_full_car):
        t = np.linspace(0, 5, 500)
        A_t = 0.05 * np.sin(2 * np.pi * 2 * t)
        profile = FourCornerRoadProfile(
            time=t, z_rfl=A_t, z_rfr=A_t, z_rrl=A_t, z_rrr=A_t
        )
        res = run_full_car_analysis(symmetric_full_car, profile)
        
        assert np.max(np.abs(res.z_s)) > 0.001
        np.testing.assert_allclose(res.theta, 0.0, atol=1e-7)
        np.testing.assert_allclose(res.phi, 0.0, atol=1e-7)

    def test_pure_pitch_decoupling(self, symmetric_full_car):
        t = np.linspace(0, 5, 500)
        A_t = 0.05 * np.sin(2 * np.pi * 2 * t)
        profile = FourCornerRoadProfile(
            time=t, z_rfl=A_t, z_rfr=A_t, z_rrl=-A_t, z_rrr=-A_t
        )
        res = run_full_car_analysis(symmetric_full_car, profile)
        
        assert np.max(np.abs(res.theta)) > 0.0001
        np.testing.assert_allclose(res.z_s, 0.0, atol=1e-7)
        np.testing.assert_allclose(res.phi, 0.0, atol=1e-7)

    def test_pure_roll_decoupling(self, symmetric_full_car):
        t = np.linspace(0, 5, 500)
        A_t = 0.05 * np.sin(2 * np.pi * 2 * t)
        profile = FourCornerRoadProfile(
            time=t, z_rfl=A_t, z_rrl=A_t, z_rfr=-A_t, z_rrr=-A_t
        )
        res = run_full_car_analysis(symmetric_full_car, profile)
        
        assert np.max(np.abs(res.phi)) > 0.0001
        np.testing.assert_allclose(res.z_s, 0.0, atol=1e-7)
        np.testing.assert_allclose(res.theta, 0.0, atol=1e-7)
        
    def test_roll_stiffness_distribution(self, symmetric_full_car):
        """Verify that lateral load transfer matches the analytical roll stiffness dist."""
        t = np.linspace(0, 5, 500)
        A_t = np.where(t > 1.0, 0.05, 0.0)
        profile = FourCornerRoadProfile(
            time=t, z_rfl=A_t, z_rfr=-A_t, z_rrl=A_t, z_rrr=-A_t
        )
        res = run_full_car_analysis(symmetric_full_car, profile)
        
        max_llt_f = np.max(np.abs(res.lateral_load_transfer_f))
        max_llt_r = np.max(np.abs(res.lateral_load_transfer_r))
        
        obs_roll_dist = (max_llt_f / (max_llt_f + max_llt_r)) * 100
        theo_roll_dist = res.roll_stiffness_dist
        np.testing.assert_allclose(obs_roll_dist, theo_roll_dist, atol=5.0)


class TestHandlingModelVnV:
    @pytest.mark.parametrize("steer_deg,speed", [(2.0, 20.0), (1.0, 30.0)])
    def test_steady_state_cornering(self, steer_deg, speed):
        """Verify Newton's 2nd Law for steady-state turning (ay = v * omega)."""
        p_hm = HandlingParams()
        res_hm = simulate_maneuver(
            p=p_hm,
            v_x_init=speed,
            steering_func=lambda t: np.radians(steer_deg),
            throttle_func=lambda t: 0.1,
            brake_func=lambda t: 0.0,
            duration=10.0,
            dt=0.05
        )
        
        idx = -1
        v_x_ss = res_hm["v_x"][idx]
        omega_ss = res_hm["yaw_rate"][idx]
        a_y_kinematic = v_x_ss * omega_ss
        a_y_dynamic = res_hm["a_y"][idx]
        
        if abs(a_y_kinematic) > 1.0:
            np.testing.assert_allclose(a_y_kinematic, a_y_dynamic, rtol=0.05)
        else:
            np.testing.assert_allclose(a_y_kinematic, a_y_dynamic, atol=0.1)

    def test_aerodynamic_drag(self):
        """Verify that at zero throttle, aerodynamic drag decelerates the vehicle."""
        p_hm = HandlingParams()
        res_hm = simulate_maneuver(
            p=p_hm,
            v_x_init=50.0,
            steering_func=lambda t: 0.0,
            throttle_func=lambda t: 0.0,
            brake_func=lambda t: 0.0,
            duration=5.0,
            dt=0.05
        )
        # Should slow down significantly from 50 m/s due to air resistance
        assert res_hm["v_x"][-1] < 48.0
