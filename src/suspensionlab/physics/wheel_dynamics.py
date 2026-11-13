"""
physics/wheel_dynamics.py
=========================
SuspensionLab PRO — Rotational Wheel Dynamics & Longitudinal Slip Formulation.

Replaces algebraic pedal-slip heuristics with authentic torque-balance
rotational wheel dynamics:
    I_w * d(omega)/dt = T_drive - T_brake - F_x * R_w

and physically rigorous longitudinal slip ratio:
    kappa = (R_w * omega - V_x) / max(|V_x|, v_min)
with smooth low-speed regularization and non-reversing brake friction mechanics.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from suspensionlab.physics.validity import (
    PhysicsValidityRecord,
    PhysicsValidityStatus,
)


@dataclass
class WheelRotationalState:
    """Rotational angular velocity state for all four wheels (rad/s)."""
    omega_fl: float = 0.0
    omega_fr: float = 0.0
    omega_rl: float = 0.0
    omega_rr: float = 0.0

    def to_list(self) -> List[float]:
        return [self.omega_fl, self.omega_fr, self.omega_rl, self.omega_rr]

    def to_array(self) -> np.ndarray:
        return np.array(self.to_list(), dtype=np.float64)

    @classmethod
    def from_list(cls, values: Union[List[float], np.ndarray]) -> "WheelRotationalState":
        return cls(
            omega_fl=float(values[0]),
            omega_fr=float(values[1]),
            omega_rl=float(values[2]),
            omega_rr=float(values[3]),
        )

    @classmethod
    def from_vehicle_speed(cls, v_x: float, r_w: float) -> "WheelRotationalState":
        """Initialize steady-state rolling angular velocities matching longitudinal speed."""
        r_w_safe = max(float(r_w), 1e-4)
        omega_ss = float(v_x) / r_w_safe
        return cls(omega_fl=omega_ss, omega_fr=omega_ss, omega_rl=omega_ss, omega_rr=omega_ss)


def calc_longitudinal_slip(
    omega: float,
    v_x: float,
    r_w: float,
    v_min: float = 0.5,
    max_slip: float = 1.0,
) -> float:
    """
    Compute longitudinal wheel slip ratio kappa:
        kappa = (R_w * omega - V_x) / max(|V_x|, v_min)

    Sign convention (SAE / Pacejka standard):
    - Acceleration / Drive slip: kappa > 0 (wheel peripheral speed exceeds vehicle speed)
    - Braking slip: kappa < 0 (wheel peripheral speed is less than vehicle speed)
    - Full lockup: kappa = -1.0
    - Pure free roll: kappa = 0.0

    Near zero velocity (|V_x| < v_min), low-speed regularization prevents numerical singularity
    and division-by-zero, smoothly blending to zero slip when wheel and vehicle are stationary.
    """
    r_w_val = max(float(r_w), 1e-4)
    v_min_val = max(float(v_min), 1e-3)
    v_periph = float(omega) * r_w_val
    v_body = float(v_x)

    # Denominator with low-speed regularisation
    denom = max(abs(v_body), v_min_val)
    raw_slip = (v_periph - v_body) / denom

    # Smooth standstill attenuation: if both vehicle and wheel are near rest, slip vanishes
    standstill_speed = max(abs(v_body), abs(v_periph))
    if standstill_speed < v_min_val:
        scale = standstill_speed / v_min_val
        raw_slip = raw_slip * scale

    return float(np.clip(raw_slip, -abs(max_slip), abs(max_slip)))


def calc_wheel_torques(
    throttle: float,
    brake: float,
    drive_bias_f: float = 0.0,
    brake_bias_f: float = 0.60,
    max_drive_torque: float = 1500.0,
    max_brake_torque: float = 3000.0,
    wheel_speeds: Optional[Tuple[float, float, float, float]] = None,
    diff_config_f: Optional[Any] = None,
    diff_config_r: Optional[Any] = None,
) -> Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float]]:
    """
    Distribute drive and brake torques to all four wheels.
    Supports Open, Locked, Torsen (Torque Biased), and Salisbury (Clutch Pack) differentials.
    Returns:
        ((T_drive_fl, T_drive_fr, T_drive_rl, T_drive_rr),
         (T_brake_fl, T_brake_fr, T_brake_rl, T_brake_rr))
    """
    th = float(np.clip(throttle, 0.0, 1.0))
    br = float(np.clip(brake, 0.0, 1.0))
    d_f = float(np.clip(drive_bias_f, 0.0, 1.0))
    b_f = float(np.clip(brake_bias_f, 0.0, 1.0))

    t_drive_total = th * max(float(max_drive_torque), 0.0)
    t_brake_total = br * max(float(max_brake_torque), 0.0)

    # Front and rear axle splits
    t_drive_f_axle = t_drive_total * d_f
    t_drive_r_axle = t_drive_total * (1.0 - d_f)

    t_brake_f_axle = t_brake_total * b_f
    t_brake_r_axle = t_brake_total * (1.0 - b_f)

    # Drive torque distribution with optional differential biasing
    if diff_config_f is not None and wheel_speeds is not None:
        from suspensionlab.physics.dynamic_lap_sim import compute_axle_torque_split
        t_dr_fl, t_dr_fr, _ = compute_axle_torque_split(
            t_drive_f_axle, wheel_speeds[0], wheel_speeds[1], diff_config_f
        )
    else:
        t_dr_fl = 0.5 * t_drive_f_axle
        t_dr_fr = 0.5 * t_drive_f_axle

    if diff_config_r is not None and wheel_speeds is not None:
        from suspensionlab.physics.dynamic_lap_sim import compute_axle_torque_split
        t_dr_rl, t_dr_rr, _ = compute_axle_torque_split(
            t_drive_r_axle, wheel_speeds[2], wheel_speeds[3], diff_config_r
        )
    else:
        t_dr_rl = 0.5 * t_drive_r_axle
        t_dr_rr = 0.5 * t_drive_r_axle

    drive_torques = (
        float(t_dr_fl),
        float(t_dr_fr),
        float(t_dr_rl),
        float(t_dr_rr),
    )
    brake_torques = (
        0.5 * t_brake_f_axle,
        0.5 * t_brake_f_axle,
        0.5 * t_brake_r_axle,
        0.5 * t_brake_r_axle,
    )

    return drive_torques, brake_torques


def calc_wheel_acceleration(
    omega: float,
    T_drive: float,
    T_brake: float,
    F_x: float,
    r_w: float,
    I_w: float,
) -> float:
    """
    Compute wheel angular acceleration d(omega)/dt from rotational torque balance:
        I_w * d(omega)/dt = T_drive - T_brake_eff - F_x * R_w

    Enforces non-reversing dry friction brake mechanics:
    - Braking torque strictly opposes wheel rotation.
    - Brake friction cannot accelerate the wheel in reverse.
    - When wheel speed omega is near zero, static brake friction counteracts
      net drive/tire torque up to T_brake, maintaining wheel lockup / rest.
    """
    i_w_val = max(float(I_w), 1e-4)
    r_w_val = max(float(r_w), 1e-4)
    t_dr = float(T_drive)
    t_br = max(float(T_brake), 0.0)
    t_tire = float(F_x) * r_w_val

    omega_val = float(omega)
    deadband = 0.02  # rad/s threshold for static friction sticking

    if abs(omega_val) > deadband:
        # Kinetic friction opposes direction of rotation
        t_br_eff = t_br if omega_val > 0.0 else -t_br
        net_torque = t_dr - t_br_eff - t_tire
        return net_torque / i_w_val

    # Static friction regime near zero angular velocity
    t_net_driving = t_dr - t_tire
    if abs(t_net_driving) <= t_br:
        # Brake holds the wheel: static friction balances net torque, decaying residual speed
        return -omega_val / 0.01

    # Overcoming static brake breakaway torque
    t_br_eff = np.sign(t_net_driving) * t_br
    net_torque = t_net_driving - t_br_eff
    return net_torque / i_w_val


def integrate_wheel_rotations_step(
    omegas: Tuple[float, float, float, float],
    drive_torques: Tuple[float, float, float, float],
    brake_torques: Tuple[float, float, float, float],
    forces_x: Tuple[float, float, float, float],
    r_w: float,
    I_w: float,
) -> Tuple[float, float, float, float]:
    """
    Compute angular accelerations [d(omega)/dt] for [FL, FR, RL, RR].
    """
    d_omegas = tuple(
        calc_wheel_acceleration(
            omega=omegas[i],
            T_drive=drive_torques[i],
            T_brake=brake_torques[i],
            F_x=forces_x[i],
            r_w=r_w,
            I_w=I_w,
        )
        for i in range(4)
    )
    return d_omegas  # type: ignore


def evaluate_wheel_dynamics_validity(
    slips: Dict[str, float],
    omegas: Dict[str, float],
    v_x: float,
) -> PhysicsValidityRecord:
    """
    Evaluate epistemic validity of wheel rotational dynamics states.
    Detects lockup, extreme spin, or unphysical numerical behaviors.
    """
    warnings: List[str] = []
    status = PhysicsValidityStatus.MODEL_SUPPORTED

    any_lockup = any(s <= -0.98 for s in slips.values())
    any_spin = any(s >= 0.95 for s in slips.values())
    high_slip = any(abs(s) > 0.25 for s in slips.values())

    if any_lockup:
        warnings.append("Wheel lockup detected (kappa <= -0.98); tire operates in pure sliding regime.")
        status = PhysicsValidityStatus.EXTRAPOLATED
    elif any_spin:
        warnings.append("Excessive drive wheelspin detected (kappa >= 0.95).")
        status = PhysicsValidityStatus.EXTRAPOLATED
    elif high_slip:
        warnings.append("Tire longitudinal slip exceeds linear regime (|kappa| > 0.25).")
        status = PhysicsValidityStatus.CORRELATED
    else:
        status = PhysicsValidityStatus.MODEL_SUPPORTED

    return PhysicsValidityRecord(
        status=status,
        model="RotationalWheelDynamics-4Wheel-v1.0",
        warnings=warnings,
        data_provenance={
            "v_x": float(v_x),
            "slips": {k: round(v, 4) for k, v in slips.items()},
            "omegas": {k: round(v, 2) for k, v in omegas.items()},
        },
        validation_evidence="Rigorous torque-balance rotational dynamics with non-reversing brake mechanics.",
    )
