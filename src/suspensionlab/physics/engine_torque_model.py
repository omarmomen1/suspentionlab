"""SuspensionLab PRO — Phase 3H.2 Engine Torque Model & Driveline Accounting.

Provides:
1. Strict separation between Actuator Replay (measured boundary input) and Predictive Model.
2. Calibrated 2D predictive engine torque model f(RPM, throttle).
3. Full driveline power and force ledger accounting from engine to contact patch.
4. Rigorous epistemic provenance labeling across all derived quantities.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class DrivelineLedgerRecord:
    """Rigorous force and power accounting across all drivetrain stages.
    
    Epistemic Rule: Axle torque, wheel torque, tractive force, and axle power
    are reconstructed from engine state, ratio, and efficiency. They are strictly
    labeled INFERRED or DERIVED, NEVER MEASURED.
    """
    time_s: float
    # Engine stage
    engine_torque_nm: float
    engine_speed_rpm: float
    engine_angular_speed_radps: float
    engine_power_w: float
    engine_torque_provenance: str          # BOUNDARY_REPLAY, MODEL_SUPPORTED, or DERIVED

    # Transmission stage
    gear: int
    gearbox_ratio: float
    final_drive_ratio: float
    total_ratio: float
    drivetrain_efficiency: float

    # Driven axle stage (INFERRED)
    axle_torque_nm: float                  # T_axle = T_eng * N_total * eta
    axle_angular_speed_radps: float
    axle_power_w: float                    # P_axle = T_axle * omega_axle = eta * P_eng
    wheel_torque_fl_nm: float
    wheel_torque_fr_nm: float

    # Contact patch stage (INFERRED)
    dynamic_rolling_radius_m: float
    tractive_force_n: float                # F_tractive = T_axle / R_eff
    vehicle_speed_mps: float
    tractive_power_w: float                # P_tractive = F_tractive * V_x

    # Epistemic classification labels
    axle_torque_classification: str = "INFERRED"
    tractive_force_classification: str = "INFERRED"
    axle_power_classification: str = "INFERRED"


class EngineTorqueModel(ABC):
    """Abstract base class for engine torque generation."""

    @abstractmethod
    def compute_torque(
        self,
        throttle: float,
        engine_rpm: float,
        gear: int = 1
    ) -> float:
        """Compute crankshaft engine torque [Nm]."""
        pass

    @property
    @abstractmethod
    def epistemic_classification(self) -> str:
        """Epistemic classification of the torque output."""
        pass


class SyntheticEngineTorqueModel(EngineTorqueModel):
    """Legacy synthetic engine torque model: T = 360 * throttle.
    
    Subject to RPM rev limit and idle bounds.
    Epistemic status: DERIVED (simplified engineering scalar).
    """

    def __init__(
        self,
        max_torque_nm: float = 360.0,
        idle_rpm: float = 2000.0,
        rev_limit_rpm: float = 13500.0
    ):
        self.max_torque_nm = max_torque_nm
        self.idle_rpm = idle_rpm
        self.rev_limit_rpm = rev_limit_rpm

    def compute_torque(
        self,
        throttle: float,
        engine_rpm: float,
        gear: int = 1
    ) -> float:
        thr = float(np.clip(throttle, 0.0, 1.0))
        rpm = float(engine_rpm)
        if rpm > self.rev_limit_rpm:
            return 0.0
        return float(thr * self.max_torque_nm)

    @property
    def epistemic_classification(self) -> str:
        return "DERIVED"


class ActuatorReplayEngineTorque(EngineTorqueModel):
    """Boundary Actuator Replay engine torque model.
    
    Replays measured CAN bus engine torque directly as an empirical boundary condition.
    Epistemic status: BOUNDARY_REPLAY (measured ECU/CAN quantity).
    """

    def __init__(self, default_torque_nm: float = 0.0):
        self.current_torque_nm = default_torque_nm

    def set_measured_torque(self, torque_nm: float) -> None:
        self.current_torque_nm = float(torque_nm)

    def compute_torque(
        self,
        throttle: float,
        engine_rpm: float,
        gear: int = 1
    ) -> float:
        return self.current_torque_nm

    @property
    def epistemic_classification(self) -> str:
        return "BOUNDARY_REPLAY"


@dataclass
class PredictiveEngineTorqueConfig:
    """Configuration for empirical 2D predictive engine torque model.
    
    Calibrated strictly on designated training/discovery temporal intervals
    (e.g., Turn 5 Tight Complex). Never calibrated on blind validation intervals.
    """
    rpm_breakpoints: List[float] = field(default_factory=lambda: [1000.0, 2000.0, 3000.0, 4000.0, 5000.0, 6000.0, 6800.0])
    torque_full_load_nm: List[float] = field(default_factory=lambda: [180.0, 350.0, 370.0, 365.0, 350.0, 300.0, 240.0])
    torque_overrun_nm: List[float] = field(default_factory=lambda: [0.0, -15.0, -28.0, -31.4, -30.0, -25.0, -20.0])
    throttle_pedal_exponent: float = 1.05  # Progressive throttle pedal mapping
    throttle_overrun_threshold: float = 0.03 # Cutoff throttle fraction below which overrun drag applies
    rev_limit_rpm: float = 6800.0
    idle_rpm: float = 1000.0
    calibration_source: str = "Turn 5 Tight Complex Discovery Window (t in [74.0, 83.0] s)"


class PredictiveEngineTorqueModel(EngineTorqueModel):
    """Physically bounded 2D predictive engine torque model f(RPM, throttle).
    
    Features:
    1. Continuous torque response bounded by full-load WOT curve and closed-throttle overrun.
    2. Overrun cutoff below throttle_overrun_threshold.
    3. Strictly monotonic throttle response preventing unbounded polynomial extrapolation.
    4. Epistemic status: MODEL_SUPPORTED / INFERRED.
    """

    def __init__(self, config: Optional[PredictiveEngineTorqueConfig] = None):
        self.config = config or PredictiveEngineTorqueConfig()

    def compute_torque(
        self,
        throttle: float,
        engine_rpm: float,
        gear: int = 1
    ) -> float:
        thr = float(np.clip(throttle, 0.0, 1.0))
        rpm = float(max(engine_rpm, 0.0))

        if rpm > self.config.rev_limit_rpm:
            return 0.0

        rpm_arr = np.array(self.config.rpm_breakpoints)
        t_max_arr = np.array(self.config.torque_full_load_nm)
        t_drag_arr = np.array(self.config.torque_overrun_nm)

        t_wot = float(np.interp(rpm, rpm_arr, t_max_arr))
        t_overrun = float(np.interp(rpm, rpm_arr, t_drag_arr))

        if thr <= self.config.throttle_overrun_threshold:
            # Overrun deceleration regime
            ramp = thr / self.config.throttle_overrun_threshold
            return float(t_overrun * (1.0 - ramp))
        else:
            # Combustion driving regime
            eff_thr = (thr - self.config.throttle_overrun_threshold) / (1.0 - self.config.throttle_overrun_threshold)
            shaped_thr = float(eff_thr ** self.config.throttle_pedal_exponent)
            return float(shaped_thr * t_wot)

    @property
    def epistemic_classification(self) -> str:
        return "MODEL_SUPPORTED"


class DrivelineAccounting:
    """Computes comprehensive driveline accounting and generates audit ledger records."""

    def __init__(self, drivetrain_efficiency: float = 0.90):
        self.drivetrain_efficiency = drivetrain_efficiency

    def record_step(
        self,
        time_s: float,
        engine_torque_nm: float,
        engine_rpm: float,
        gear: int,
        gearbox_ratio: float,
        final_drive_ratio: float,
        dynamic_rolling_radius_m: float,
        vehicle_speed_mps: float,
        torque_provenance: str = "MODEL_SUPPORTED"
    ) -> DrivelineLedgerRecord:
        """Create an authoritative ledger record for a single integration step."""
        omega_eng = engine_rpm * (2.0 * math.pi / 60.0)
        p_eng = engine_torque_nm * omega_eng
        total_ratio = gearbox_ratio * final_drive_ratio
        omega_axle = omega_eng / max(total_ratio, 0.01)

        # Inferred axle torque and power
        t_axle = engine_torque_nm * total_ratio * self.drivetrain_efficiency
        p_axle = t_axle * omega_axle

        # Inferred tractive force and power
        r_eff = max(dynamic_rolling_radius_m, 0.1)
        f_tractive = t_axle / r_eff
        p_tractive = f_tractive * vehicle_speed_mps

        return DrivelineLedgerRecord(
            time_s=float(time_s),
            engine_torque_nm=float(engine_torque_nm),
            engine_speed_rpm=float(engine_rpm),
            engine_angular_speed_radps=float(omega_eng),
            engine_power_w=float(p_eng),
            engine_torque_provenance=torque_provenance,
            gear=int(gear),
            gearbox_ratio=float(gearbox_ratio),
            final_drive_ratio=float(final_drive_ratio),
            total_ratio=float(total_ratio),
            drivetrain_efficiency=float(self.drivetrain_efficiency),
            axle_torque_nm=float(t_axle),
            axle_angular_speed_radps=float(omega_axle),
            axle_power_w=float(p_axle),
            wheel_torque_fl_nm=float(0.5 * t_axle),
            wheel_torque_fr_nm=float(0.5 * t_axle),
            dynamic_rolling_radius_m=float(r_eff),
            tractive_force_n=float(f_tractive),
            vehicle_speed_mps=float(vehicle_speed_mps),
            tractive_power_w=float(p_tractive),
            axle_torque_classification="INFERRED",
            tractive_force_classification="INFERRED",
            axle_power_classification="INFERRED",
        )
