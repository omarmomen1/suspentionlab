"""
physics/brake_distribution.py
==============================
SuspensionLab PRO — Phase 3G Autonomous Brake Distribution Controller Model

Implements a deterministic, physics-based predictive brake-distribution layer
capable of estimating per-wheel hydraulic brake pressure targets (FL, FR, RL, RR)
from driver master demand and vehicle dynamic state.

EPIDEMIOLOGY & GOVERNANCE CONTRACT (Phase 3F.1 / Phase 3G):
-----------------------------------------------------------
1. MODE A: ACTUATOR_REPLAY
   Replays measured physical telemetry pressures (brake_fl_bar, brake_fr_bar,
   brake_rl_bar, brake_rr_bar). Used to validate suspension, tire, and chassis
   equations given true boundary actuator forces.

2. MODE B: BRAKE_DISTRIBUTION_PREDICTION
   Predicts corner hydraulic line pressures autonomously from driver master demand,
   dynamic normal load transfer, cornering asymmetry (CBC), and slip regulation (ABS).
   STRICT RULE: Mode B NEVER consumes measured corner pressures.

3. REPRESENTS A "Brake Distribution Controller Model", NOT an "OEM ESC/ABS Model".
   Inferred from vehicle-response physics and available telemetry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np


class BrakeDistributionMode(str, Enum):
    """Operational mode for brake pressure assignment."""
    ACTUATOR_REPLAY = "ACTUATOR_REPLAY"
    BRAKE_DISTRIBUTION_PREDICTION = "BRAKE_DISTRIBUTION_PREDICTION"


class BrakeDistributionMechanism(str, Enum):
    """Causal mechanism classification for corner pressure modulation."""
    BASELINE_BRAKE_BIAS = "BASELINE_BRAKE_BIAS"
    LEFT_RIGHT_LOAD_COMPENSATION = "LEFT_RIGHT_LOAD_COMPENSATION"
    YAW_STABILITY_INTERVENTION = "YAW_STABILITY_INTERVENTION"
    WHEEL_SLIP_INTERVENTION = "WHEEL_SLIP_INTERVENTION"
    UNIDENTIFIED = "UNIDENTIFIED"


@dataclass
class BrakeDistributionState:
    """Instantaneous output of the predictive brake distribution controller."""
    p_fl_bar: float = 0.0
    p_fr_bar: float = 0.0
    p_rl_bar: float = 0.0
    p_rr_bar: float = 0.0
    active_mechanism: BrakeDistributionMechanism = BrakeDistributionMechanism.BASELINE_BRAKE_BIAS
    front_bias: float = 0.614
    left_right_asymmetry_front_bar: float = 0.0
    left_right_asymmetry_rear_bar: float = 0.0
    induced_yaw_moment_nm: float = 0.0
    total_braking_force_n: float = 0.0
    fl_load_ratio: float = 1.0
    fr_load_ratio: float = 1.0
    rl_load_ratio: float = 1.0
    rr_load_ratio: float = 1.0
    abs_active: bool = False
    cbc_active: bool = False


@dataclass
class BrakeDistributionController:
    """Physics-based autonomous brake distribution model.
    
    Synthesizes four-corner brake pressures from driver master demand,
    static proportioning, dynamic normal load transfer (EBD),
    cornering yaw stabilization (CBC), and wheel slip regulation (ABS).
    """
    # Vehicle parameters (defaulted to Stanford VW Golf VII GTI baseline)
    mass_kg: float = 1530.0
    wheelbase_m: float = 2.63
    a_m: float = 1.05
    b_m: float = 1.58
    tw_f_m: float = 1.54
    tw_r_m: float = 1.52
    cg_height_m: float = 0.52
    wheel_radius_m: float = 0.3198
    
    # Hydraulic & proportioning parameters
    static_front_bias: float = 0.614          # Nominal front pressure fraction (empirical Golf baseline ~0.614)
    p_max_bar: float = 80.0                   # Nominal maximum line pressure [bar]
    p_min_bar: float = 0.0                    # Minimum line pressure [bar]
    dp_dt_max_barps: float = 400.0            # Hydraulic bandwidth / slew rate limit [bar/s]
    
    # Cornering Brake Control (CBC) yaw stabilization
    k_cbc_front: float = 0.02                 # Yaw error to differential front pressure gain [bar/(rad/s)]
    k_cbc_rear: float = 0.03                  # Yaw error to differential rear pressure gain [bar/(rad/s)]
    max_cbc_delta_bar: float = 6.0            # Maximum allowable CBC differential modulation [bar]
    
    # ABS Wheel Slip Regulation
    abs_slip_threshold: float = -0.12         # Slip threshold where ABS activates
    abs_recovery_gain: float = 2.5            # Pressure decay factor per excess slip
    
    # Internal state tracking for rate limiting
    _prev_p_fl: float = field(default=0.0, repr=False)
    _prev_p_fr: float = field(default=0.0, repr=False)
    _prev_p_rl: float = field(default=0.0, repr=False)
    _prev_p_rr: float = field(default=0.0, repr=False)

    def reset_internal_state(self):
        """Reset temporal state filters."""
        self._prev_p_fl = 0.0
        self._prev_p_fr = 0.0
        self._prev_p_rl = 0.0
        self._prev_p_rr = 0.0

    def predict_pressures(
        self,
        driver_demand_bar: float,
        steering_rad: float,
        vx_mps: float,
        yaw_rate_radps: float,
        ax_mps2: Optional[float] = None,
        ay_mps2: Optional[float] = None,
        wheel_speeds_radps: Optional[Tuple[float, float, float, float]] = None,
        dt: Optional[float] = None,
        apply_rate_limiting: bool = False,
    ) -> BrakeDistributionState:
        """Predict per-wheel hydraulic brake pressures from driver demand and dynamic state.
        
        CRITICAL GOVERNANCE INVARIANT:
        This method NEVER takes measured corner pressures as inputs.
        
        Args:
            driver_demand_bar: Total / master brake pressure demand [bar] (>= 0.0).
            steering_rad: Road wheel steer angle [rad] (+ = left turn).
            vx_mps: Forward longitudinal velocity [m/s].
            yaw_rate_radps: Chassis yaw rate [rad/s] (+ = counter-clockwise / left).
            ax_mps2: Longitudinal acceleration [m/s^2] (negative under braking).
            ay_mps2: Lateral acceleration [m/s^2] (+ = left turn).
            wheel_speeds_radps: Tuple of (omega_fl, omega_fr, omega_rl, omega_rr) [rad/s].
            dt: Optional time step duration [s].
            apply_rate_limiting: Whether to apply hydraulic slew rate limits.
            
        Returns:
            BrakeDistributionState with predicted corner pressures and telemetry metrics.
        """
        p_demand = max(0.0, float(driver_demand_bar))
        if p_demand < 1e-4:
            self._prev_p_fl = 0.0
            self._prev_p_fr = 0.0
            self._prev_p_rl = 0.0
            self._prev_p_rr = 0.0
            return BrakeDistributionState(
                active_mechanism=BrakeDistributionMechanism.BASELINE_BRAKE_BIAS,
                front_bias=self.static_front_bias,
            )

        # 1. Kinematic state estimation if accelerations not supplied
        vx = max(vx_mps, 0.5)
        ay = float(ay_mps2) if ay_mps2 is not None else float(vx * yaw_rate_radps)
        
        # If ax is not supplied, infer deceleration from driver brake demand
        if ax_mps2 is not None:
            ax = float(ax_mps2)
        else:
            # Approximate deceleration: 80 bar master pressure produces ~0.85 g deceleration
            ax = -float(np.clip((p_demand / 80.0) * 8.5, 0.0, 11.0))

        # 2. Dynamic Normal Load Transfer (EBD Foundation)
        g = 9.81
        m = self.mass_kg
        L = self.wheelbase_m
        h = self.cg_height_m
        b = self.b_m
        a = self.a_m
        tw_f = self.tw_f_m
        tw_r = self.tw_r_m

        Fz0_f = m * g * (b / L) / 2.0
        Fz0_r = m * g * (a / L) / 2.0

        dFz_long = (m * ax * h) / L  # Negative under braking -> reduces rear load, increases front load
        dFz_lat_f = (m * (b / L) * ay * h) / tw_f
        dFz_lat_r = (m * (a / L) * ay * h) / tw_r

        # Normal load per corner (enforce strictly positive normal contact load >= 50 N)
        Fz_fl = max(50.0, Fz0_f - dFz_long / 2.0 - dFz_lat_f)
        Fz_fr = max(50.0, Fz0_f - dFz_long / 2.0 + dFz_lat_f)
        Fz_rl = max(50.0, Fz0_r + dFz_long / 2.0 - dFz_lat_r)
        Fz_rr = max(50.0, Fz0_r + dFz_long / 2.0 + dFz_lat_r)

        # 3. Dynamic Normal Load Proportioning Factors
        # Total front axle load & rear axle load
        Fz_front = Fz_fl + Fz_fr
        Fz_rear = Fz_rl + Fz_rr

        k_fl = 2.0 * Fz_fl / max(Fz_front, 100.0)
        k_fr = 2.0 * Fz_fr / max(Fz_front, 100.0)
        k_rl = 2.0 * Fz_rl / max(Fz_rear, 100.0)
        k_rr = 2.0 * Fz_rr / max(Fz_rear, 100.0)

        # 4. Axle Baseline Allocation from Driver Demand
        # If all 4 corners have equal pressure P, p_demand = P.
        # Front axle pair receives 2 * beta * p_demand (so each front corner averages 2 * beta * p_demand).
        # Rear axle pair receives 2 * (1 - beta) * p_demand (so each rear corner averages 2 * (1 - beta) * p_demand).
        # Total sum across 4 wheels = 2 * (2*beta*P + 2*(1-beta)*P)/4 = P = p_demand.
        p_f_axle_mean = 2.0 * self.static_front_bias * p_demand
        p_r_axle_mean = 2.0 * (1.0 - self.static_front_bias) * p_demand

        # Raw load-compensated pressure targets
        target_fl = p_f_axle_mean * k_fl
        target_fr = p_f_axle_mean * k_fr
        target_rl = p_r_axle_mean * k_rl
        target_rr = p_r_axle_mean * k_rr

        # 5. Cornering Brake Control (CBC) Yaw Stabilization
        # Linear bicycle model reference yaw rate
        understeer_gradient = 0.0015 # [rad/(m/s^2)]
        r_target = (vx * steering_rad) / (L + understeer_gradient * (vx**2))
        yaw_rate_err = yaw_rate_radps - r_target

        cbc_active = False
        if abs(yaw_rate_err) > 0.05 and abs(ay) > 1.0:
            cbc_active = True
            # Oversteer (yaw_rate_err > 0): add outside front brake, reduce inside rear brake
            sgn_turn = 1.0 if ay > 0 else -1.0
            delta_cbc = np.clip(self.k_cbc_front * yaw_rate_err, -self.max_cbc_delta_bar, self.max_cbc_delta_bar)
            if sgn_turn > 0: # Left turn: FR is outside, FL is inside
                target_fr += delta_cbc
                target_fl -= delta_cbc
                target_rl += delta_cbc * 0.5
                target_rr -= delta_cbc * 0.5
            else: # Right turn: FL is outside, FR is inside
                target_fl -= delta_cbc
                target_fr += delta_cbc
                target_rr -= delta_cbc * 0.5
                target_rl += delta_cbc * 0.5

        # 6. ABS Wheel Slip Regulation
        abs_active = False
        if wheel_speeds_radps is not None and vx > 3.0:
            w_fl, w_fr, w_rl, w_rr = wheel_speeds_radps
            rw = self.wheel_radius_m
            
            # Kinematic longitudinal slip kappa_i = (Rw*omega - Vx) / Vx
            kappa_fl = (rw * w_fl - vx) / vx
            kappa_fr = (rw * w_fr - vx) / vx
            kappa_rl = (rw * w_rl - vx) / vx
            kappa_rr = (rw * w_rr - vx) / vx

            for corner, kappa, tgt_attr in [
                ("fl", kappa_fl, "target_fl"),
                ("fr", kappa_fr, "target_fr"),
                ("rl", kappa_rl, "target_rl"),
                ("rr", kappa_rr, "target_rr"),
            ]:
                if kappa < self.abs_slip_threshold:
                    abs_active = True
                    excess_slip = abs(kappa - self.abs_slip_threshold)
                    decay = max(0.2, 1.0 - self.abs_recovery_gain * excess_slip)
                    if tgt_attr == "target_fl":
                        target_fl *= decay
                    elif tgt_attr == "target_fr":
                        target_fr *= decay
                    elif tgt_attr == "target_rl":
                        target_rl *= decay
                    elif tgt_attr == "target_rr":
                        target_rr *= decay

        # 7. Actuator Bandwidth / Slew Rate Limiting (optional)
        if apply_rate_limiting and dt is not None and dt > 0.0:
            max_dp = self.dp_dt_max_barps * dt
            p_fl = float(np.clip(target_fl, self._prev_p_fl - max_dp, self._prev_p_fl + max_dp))
            p_fr = float(np.clip(target_fr, self._prev_p_fr - max_dp, self._prev_p_fr + max_dp))
            p_rl = float(np.clip(target_rl, self._prev_p_rl - max_dp, self._prev_p_rl + max_dp))
            p_rr = float(np.clip(target_rr, self._prev_p_rr - max_dp, self._prev_p_rr + max_dp))
        else:
            p_fl = float(target_fl)
            p_fr = float(target_fr)
            p_rl = float(target_rl)
            p_rr = float(target_rr)

        # Enforce physical bounds [p_min, p_max]
        p_fl = float(np.clip(p_fl, self.p_min_bar, self.p_max_bar))
        p_fr = float(np.clip(p_fr, self.p_min_bar, self.p_max_bar))
        p_rl = float(np.clip(p_rl, self.p_min_bar, self.p_max_bar))
        p_rr = float(np.clip(p_rr, self.p_min_bar, self.p_max_bar))

        self._prev_p_fl = p_fl
        self._prev_p_fr = p_fr
        self._prev_p_rl = p_rl
        self._prev_p_rr = p_rr

        # 8. Causal Mechanism Tagging
        asym_f = abs(p_fl - p_fr)
        asym_r = abs(p_rl - p_rr)
        total_p = p_fl + p_fr + p_rl + p_rr
        front_p = p_fl + p_fr
        f_bias = front_p / max(total_p, 1e-4)

        if abs_active:
            mechanism = BrakeDistributionMechanism.WHEEL_SLIP_INTERVENTION
        elif cbc_active:
            mechanism = BrakeDistributionMechanism.YAW_STABILITY_INTERVENTION
        elif asym_f > 0.5 or asym_r > 0.5:
            mechanism = BrakeDistributionMechanism.LEFT_RIGHT_LOAD_COMPENSATION
        elif total_p > 0.5:
            mechanism = BrakeDistributionMechanism.BASELINE_BRAKE_BIAS
        else:
            mechanism = BrakeDistributionMechanism.UNIDENTIFIED

        # 9. Induced Yaw Moment from Brake Asymmetry
        t_per_bar_f = 2400.0 / 80.0
        t_per_bar_r = 1200.0 / 80.0
        rw = self.wheel_radius_m

        fx_fl = (p_fl * t_per_bar_f) / rw
        fx_fr = (p_fr * t_per_bar_f) / rw
        fx_rl = (p_rl * t_per_bar_r) / rw
        fx_rr = (p_rr * t_per_bar_r) / rw

        total_fx = fx_fl + fx_fr + fx_rl + fx_rr
        delta_mz = (tw_f / 2.0) * (fx_fr - fx_fl) + (tw_r / 2.0) * (fx_rr - fx_rl)

        return BrakeDistributionState(
            p_fl_bar=p_fl,
            p_fr_bar=p_fr,
            p_rl_bar=p_rl,
            p_rr_bar=p_rr,
            active_mechanism=mechanism,
            front_bias=float(f_bias),
            left_right_asymmetry_front_bar=float(p_fl - p_fr),
            left_right_asymmetry_rear_bar=float(p_rl - p_rr),
            induced_yaw_moment_nm=float(delta_mz),
            total_braking_force_n=float(total_fx),
            fl_load_ratio=float(k_fl),
            fr_load_ratio=float(k_fr),
            rl_load_ratio=float(k_rl),
            rr_load_ratio=float(k_rr),
            abs_active=abs_active,
            cbc_active=cbc_active,
        )

    def evaluate_time_series(
        self,
        driver_demand_bar: np.ndarray,
        steering_rad: np.ndarray,
        vx_mps: np.ndarray,
        yaw_rate_radps: np.ndarray,
        ax_mps2: Optional[np.ndarray] = None,
        ay_mps2: Optional[np.ndarray] = None,
        wheel_speeds_radps: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = None,
        dt: float = 0.005,
        apply_rate_limiting: bool = True,
    ) -> Dict[str, np.ndarray]:
        """Process an entire time-series trajectory with temporal continuity."""
        self.reset_internal_state()
        n = len(driver_demand_bar)
        out = {
            "p_fl_bar": np.zeros(n),
            "p_fr_bar": np.zeros(n),
            "p_rl_bar": np.zeros(n),
            "p_rr_bar": np.zeros(n),
            "front_bias": np.zeros(n),
            "induced_yaw_moment_nm": np.zeros(n),
            "total_braking_force_n": np.zeros(n),
            "active_mechanism": [],
        }

        for i in range(n):
            ws = (
                (wheel_speeds_radps[0][i], wheel_speeds_radps[1][i], wheel_speeds_radps[2][i], wheel_speeds_radps[3][i])
                if wheel_speeds_radps is not None else None
            )
            ax_i = ax_mps2[i] if ax_mps2 is not None else None
            ay_i = ay_mps2[i] if ay_mps2 is not None else None
            
            st = self.predict_pressures(
                driver_demand_bar=float(driver_demand_bar[i]),
                steering_rad=float(steering_rad[i]),
                vx_mps=float(vx_mps[i]),
                yaw_rate_radps=float(yaw_rate_radps[i]),
                ax_mps2=ax_i,
                ay_mps2=ay_i,
                wheel_speeds_radps=ws,
                dt=dt,
                apply_rate_limiting=apply_rate_limiting,
            )
            out["p_fl_bar"][i] = st.p_fl_bar
            out["p_fr_bar"][i] = st.p_fr_bar
            out["p_rl_bar"][i] = st.p_rl_bar
            out["p_rr_bar"][i] = st.p_rr_bar
            out["front_bias"][i] = st.front_bias
            out["induced_yaw_moment_nm"][i] = st.induced_yaw_moment_nm
            out["total_braking_force_n"][i] = st.total_braking_force_n
            out["active_mechanism"].append(st.active_mechanism.value)

        return out
