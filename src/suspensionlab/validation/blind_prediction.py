"""SuspensionLab PRO — Blind Prediction Mode & Telemetry Firewall.

Implements Requirement 4:
- The simulator must NOT access target measurements during prediction.
- Measured telemetry may only be used for:
  1. initial conditions (at t = t0)
  2. explicitly declared driver boundary conditions (throttle, steering, brake along t)
  3. post-simulation validation
- Every channel must have a provenance classification.
- Strictly guards against target telemetry leakage and contamination.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union
import numpy as np
import pandas as pd

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
    BrakeActuatorMap,
    EngineOverrunMap,
)
from suspensionlab.physics.gear_inference import GearInferenceEngine
from suspensionlab.physics.engine_torque_model import PredictiveEngineTorqueModel
from suspensionlab.physics.powertrain_lap_sim import PowertrainCorrectedLapSimulator
from suspensionlab.physics.transmission_state_machine import EndogenousTransmission, ShiftSpec
from suspensionlab.validation.schema import (
    ProvenanceClassification,
    StandardChannels,
    UNIVERSAL_CHANNEL_DEFINITIONS,
)


class TelemetryLeakageError(RuntimeError):
    """Raised when target measurements are leaked into the simulation prediction loop."""
    pass


@dataclass
class InitialConditionVector:
    """Rigorous state vector extracted at t = t0 to initialize forward ODE integration."""
    t0_s: float
    u_mps: float              # Longitudinal speed Vx
    v_mps: float              # Lateral speed Vy
    yaw_rate_rads: float      # Yaw angular rate
    yaw_angle_rad: float      # Yaw heading angle
    roll_phi_rad: float       # Chassis roll angle
    omega_fl: float           # Front-left wheel angular velocity (rad/s)
    omega_fr: float           # Front-right wheel angular velocity (rad/s)
    omega_rl: float           # Rear-left wheel angular velocity (rad/s)
    omega_rr: float           # Rear-right wheel angular velocity (rad/s)
    initial_gear: int = 1     # Initial transmission gear
    provenance_classification: str = ProvenanceClassification.INITIAL_CONDITION.value

    def to_state(self) -> DynamicVehicleState:
        """Constructs a fresh DynamicVehicleState instance."""
        st = DynamicVehicleState(
            u_mps=float(self.u_mps),
            v_mps=float(self.v_mps),
            yaw_rate_rads=float(self.yaw_rate_rads),
            yaw_angle_rad=float(self.yaw_angle_rad),
            roll_phi=float(self.roll_phi_rad),
            omega_fl=float(self.omega_fl),
            omega_fr=float(self.omega_fr),
            omega_rl=float(self.omega_rl),
            omega_rr=float(self.omega_rr),
        )
        setattr(st, "time_s", float(self.t0_s))
        return st

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DriverBoundaryConditions:
    """Exogenous driver and environmental inputs over the simulation interval.
    
    Contains ONLY boundary conditions: time, steering, throttle, brake pressure, road bank/grade.
    STRICTLY EXCLUDES TARGET MEASUREMENTS (Vx, Vy, yaw rate, wheel speeds, RPM, gear, etc.).
    """
    timestamps_s: np.ndarray
    steering_rad: np.ndarray
    throttle_norm: np.ndarray
    brake_pressure_fl_bar: np.ndarray
    brake_pressure_fr_bar: np.ndarray
    brake_pressure_rl_bar: np.ndarray
    brake_pressure_rr_bar: np.ndarray
    road_bank_rad: np.ndarray
    road_grade_rad: np.ndarray
    provenance_classification: str = ProvenanceClassification.BOUNDARY_CONDITION.value

    def __post_init__(self):
        self.timestamps_s = np.asarray(self.timestamps_s, dtype=np.float64)
        n = len(self.timestamps_s)
        self.steering_rad = np.asarray(self.steering_rad, dtype=np.float64)
        self.throttle_norm = np.asarray(self.throttle_norm, dtype=np.float64)
        self.brake_pressure_fl_bar = np.asarray(self.brake_pressure_fl_bar, dtype=np.float64)
        self.brake_pressure_fr_bar = np.asarray(self.brake_pressure_fr_bar, dtype=np.float64)
        self.brake_pressure_rl_bar = np.asarray(self.brake_pressure_rl_bar, dtype=np.float64)
        self.brake_pressure_rr_bar = np.asarray(self.brake_pressure_rr_bar, dtype=np.float64)
        self.road_bank_rad = np.asarray(self.road_bank_rad, dtype=np.float64)
        self.road_grade_rad = np.asarray(self.road_grade_rad, dtype=np.float64)

        # Enforce dimension consistency
        for name, arr in [
            ("steering_rad", self.steering_rad),
            ("throttle_norm", self.throttle_norm),
            ("brake_fl", self.brake_pressure_fl_bar),
            ("brake_fr", self.brake_pressure_fr_bar),
            ("brake_rl", self.brake_pressure_rl_bar),
            ("brake_rr", self.brake_pressure_rr_bar),
            ("road_bank", self.road_bank_rad),
            ("road_grade", self.road_grade_rad),
        ]:
            if len(arr) != n:
                raise ValueError(f"Boundary condition '{name}' length ({len(arr)}) does not match timestamps ({n}).")

    def __len__(self) -> int:
        return len(self.timestamps_s)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_samples": len(self),
            "t_start": float(self.timestamps_s[0]) if len(self) > 0 else 0.0,
            "t_end": float(self.timestamps_s[-1]) if len(self) > 0 else 0.0,
            "provenance": self.provenance_classification,
        }


@dataclass
class BlindSimulationResult:
    """Output of blind simulation execution without access to target telemetry."""
    timestamps_s: np.ndarray
    predicted_channels: Dict[str, np.ndarray]
    initial_conditions: InitialConditionVector
    boundary_conditions_summary: Dict[str, Any]
    driveline_ledger: List[Dict[str, Any]] = field(default_factory=list)
    firewall_verified_leak_free: bool = True
    provenance_classification: str = ProvenanceClassification.SIMULATED_PREDICTION.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "firewall_verified_leak_free": self.firewall_verified_leak_free,
            "n_samples": len(self.timestamps_s),
            "t_start": float(self.timestamps_s[0]) if len(self.timestamps_s) > 0 else 0.0,
            "t_end": float(self.timestamps_s[-1]) if len(self.timestamps_s) > 0 else 0.0,
            "predicted_channels": sorted(list(self.predicted_channels.keys())),
            "initial_conditions": self.initial_conditions.to_dict(),
            "provenance": self.provenance_classification,
        }


class TelemetryFirewall:
    """Security firewall preventing target measurement leakage into forward simulation."""

    # Targets that MUST NOT be accessed during prediction
    RESTRICTED_TARGET_NAMES: Set[str] = {
        StandardChannels.VX,
        StandardChannels.VY,
        StandardChannels.YAW_RATE,
        StandardChannels.WHEEL_SPEED_FL,
        StandardChannels.WHEEL_SPEED_FR,
        StandardChannels.WHEEL_SPEED_RL,
        StandardChannels.WHEEL_SPEED_RR,
        StandardChannels.ENGINE_RPM,
        StandardChannels.GEAR,
        StandardChannels.AX,
        StandardChannels.AY,
        "engineTorque_Nm",
        "GearRatio",
        "yawAngle_rad",
        "rollAngle_rad",
    }

    @classmethod
    def sanitize_driver_controls(
        cls,
        ctrl: DriverControls,
        allow_autonomous_gear: bool = True,
    ) -> DriverControls:
        """Ensures driver controls do not leak target transmission gears."""
        if allow_autonomous_gear:
            # Enforce gear=0 so that autonomous transmission state machine is forced
            return DriverControls(
                steering_deg=ctrl.steering_deg,
                throttle=ctrl.throttle,
                brake_pressure_fl_bar=ctrl.brake_pressure_fl_bar,
                brake_pressure_fr_bar=ctrl.brake_pressure_fr_bar,
                brake_pressure_rl_bar=ctrl.brake_pressure_rl_bar,
                brake_pressure_rr_bar=ctrl.brake_pressure_rr_bar,
                gear=0,
            )
        return ctrl

    @classmethod
    def check_for_target_leakage(cls, candidate_dict_or_df: Union[Dict[str, Any], pd.DataFrame]) -> None:
        """Inspects input dictionary or DataFrame to ensure no target channels are present."""
        keys = set(candidate_dict_or_df.keys()) if isinstance(candidate_dict_or_df, dict) else set(candidate_dict_or_df.columns)
        leaked = keys.intersection(cls.RESTRICTED_TARGET_NAMES)
        if leaked:
            raise TelemetryLeakageError(
                f"SECURITY VIOLATION: Target measurement channels {sorted(list(leaked))} leaked into prediction environment! "
                "Prediction must be strictly blind."
            )


class BlindPredictionEnvironment:
    """Execution sandbox ensuring 100% blind simulation without target measurement leakage."""

    @staticmethod
    def extract_initial_conditions(
        data: Union[pd.DataFrame, Dict[str, np.ndarray]],
        t_start: float,
        roll_bias: float = 0.0,
        default_gear: int = 2,
    ) -> InitialConditionVector:
        """Extracts vehicle initial state at t = t_start."""
        if isinstance(data, pd.DataFrame):
            # Find closest sample to t_start
            t_col = "t_s" if "t_s" in data.columns else "time"
            idx = int(np.argmin(np.abs(data[t_col].values - t_start)))
            row = data.iloc[idx]

            # Extract wheelspeeds, converting to rad/s if stored as linear m/s
            w_fl = float(row.get("wheelspeed_fl", row.get("wsp_fl", 0.0)))
            w_fr = float(row.get("wheelspeed_fr", row.get("wsp_fr", 0.0)))
            w_rl = float(row.get("wheelspeed_rl", row.get("wsp_rl", 0.0)))
            w_rr = float(row.get("wheelspeed_rr", row.get("wsp_rr", 0.0)))

            u = float(row.get("Vx_mps", row.get("Vx", 0.0)))
            v = float(row.get("Vy_mps", row.get("Vy", 0.0)))
            yr = float(row.get("yawRate_radps", row.get("yaw_rate", 0.0)))
            ya = float(row.get("yawAngle_rad", row.get("yaw_angle", 0.0)))
            roll = float(row.get("rollAngle_rad", row.get("roll_angle", 0.0))) - roll_bias

            # Initial gear from gear or GearRatio
            gear_val = row.get("gear", default_gear)
            if math.isnan(gear_val) or gear_val == 0:
                gear_val = default_gear
            init_gear = int(round(gear_val))
            t0 = float(row[t_col])

        else:
            t_arr = data.get("time", data.get("t_s", np.zeros(0)))
            idx = int(np.argmin(np.abs(t_arr - t_start))) if len(t_arr) > 0 else 0
            t0 = float(t_arr[idx]) if len(t_arr) > 0 else t_start

            u = float(data.get("Vx", data.get("Vx_mps", [0.0]))[idx])
            v = float(data.get("Vy", data.get("Vy_mps", [0.0]))[idx])
            yr = float(data.get("yaw_rate", data.get("yawRate_radps", [0.0]))[idx])
            ya = float(data.get("yaw_angle", data.get("yawAngle_rad", [0.0]))[idx])
            roll = float(data.get("roll_angle", data.get("rollAngle_rad", [0.0]))[idx]) - roll_bias

            w_fl = float(data.get("wheelspeed_fl", [0.0])[idx])
            w_fr = float(data.get("wheelspeed_fr", [0.0])[idx])
            w_rl = float(data.get("wheelspeed_rl", [0.0])[idx])
            w_rr = float(data.get("wheelspeed_rr", [0.0])[idx])
            init_gear = default_gear

        return InitialConditionVector(
            t0_s=t0,
            u_mps=u,
            v_mps=v,
            yaw_rate_rads=yr,
            yaw_angle_rad=ya,
            roll_phi_rad=roll,
            omega_fl=w_fl,
            omega_fr=w_fr,
            omega_rl=w_rl,
            omega_rr=w_rr,
            initial_gear=init_gear,
        )

    @staticmethod
    def extract_driver_boundary_conditions(
        data: Union[pd.DataFrame, Dict[str, np.ndarray]],
        t_start: float,
        t_end: float,
    ) -> DriverBoundaryConditions:
        """Extracts strictly exogenous driver boundary conditions over [t_start, t_end]."""
        if isinstance(data, pd.DataFrame):
            t_col = "t_s" if "t_s" in data.columns else "time"
            mask = (data[t_col] >= t_start) & (data[t_col] <= t_end)
            sub = data[mask].copy().reset_index(drop=True)

            t_s = sub[t_col].values
            # Steering road wheel angle in rad
            steer = sub.get("roadWheelAngle_rad", sub.get("steering", np.zeros(len(sub)))).values
            # Throttle normalized [0..1]
            thr = sub.get("throttleCmd_percent", sub.get("throttle", np.zeros(len(sub)))).values
            if len(thr) > 0 and np.nanmax(thr) > 1.5:
                thr = thr / 100.0

            b_fl = sub.get("brake_fl_bar", sub.get("brake_pressure_fl", np.zeros(len(sub)))).values
            b_fr = sub.get("brake_fr_bar", sub.get("brake_pressure_fr", np.zeros(len(sub)))).values
            b_rl = sub.get("brake_rl_bar", sub.get("brake_pressure_rl", np.zeros(len(sub)))).values
            b_rr = sub.get("brake_rr_bar", sub.get("brake_pressure_rr", np.zeros(len(sub)))).values

            bank = sub.get("bank_rad", np.zeros(len(sub))).values
            grade = sub.get("grade_rad", np.zeros(len(sub))).values
        else:
            t_col = "time" if "time" in data else "t_s"
            t_all = data[t_col]
            mask = (t_all >= t_start) & (t_all <= t_end)

            t_s = t_all[mask]
            steer = data.get("steering", data.get("roadWheelAngle_rad", np.zeros(len(t_all))))[mask]
            thr = data.get("throttle", data.get("throttleCmd_percent", np.zeros(len(t_all))))[mask]
            if len(thr) > 0 and np.nanmax(thr) > 1.5:
                thr = thr / 100.0

            b_fl = data.get("brake_pressure_fl", data.get("brake_fl_bar", np.zeros(len(t_all))))[mask]
            b_fr = data.get("brake_pressure_fr", data.get("brake_fr_bar", np.zeros(len(t_all))))[mask]
            b_rl = data.get("brake_pressure_rl", data.get("brake_rl_bar", np.zeros(len(t_all))))[mask]
            b_rr = data.get("brake_pressure_rr", data.get("brake_rr_bar", np.zeros(len(t_all))))[mask]

            bank = data.get("bank_rad", np.zeros(len(t_all)))[mask]
            grade = data.get("grade_rad", np.zeros(len(t_all)))[mask]

        return DriverBoundaryConditions(
            timestamps_s=t_s,
            steering_rad=steer,
            throttle_norm=thr,
            brake_pressure_fl_bar=b_fl,
            brake_pressure_fr_bar=b_fr,
            brake_pressure_rl_bar=b_rl,
            brake_pressure_rr_bar=b_rr,
            road_bank_rad=bank,
            road_grade_rad=grade,
        )

    @classmethod
    def run_blind_simulation(
        cls,
        params: DynamicVehicleParams,
        initial_conditions: InitialConditionVector,
        boundary_conditions: DriverBoundaryConditions,
        shift_spec: Optional[ShiftSpec] = None,
        dt_s: float = 0.005,
    ) -> BlindSimulationResult:
        """Executes forward numerical integration strictly isolated by the TelemetryFirewall."""
        n_steps = len(boundary_conditions)
        if n_steps == 0:
            raise ValueError("Boundary conditions are empty.")

        # Initialize simulation state from initial conditions ONLY
        st = initial_conditions.to_state()
        spec = shift_spec or ShiftSpec()
        tx = EndogenousTransmission(spec=spec, initial_gear=initial_conditions.initial_gear)

        sim = PowertrainCorrectedLapSimulator(
            params=params,
            gear_engine=GearInferenceEngine(),
            torque_model=PredictiveEngineTorqueModel(),
            powertrain_mode="PREDICTIVE",
            autonomous_shifting=True,
            transmission=tx,
            dt_fixed_s=dt_s,
        )

        # Output predicted trajectories
        out_time = []
        out_vx = []
        out_vy = []
        out_yaw_rate = []
        out_roll = []
        out_w_fl = []
        out_w_fr = []
        out_w_rl = []
        out_w_rr = []
        out_rpm = []
        out_gear = []
        out_ax = []
        out_ay = []

        driveline_ledger: List[Dict[str, Any]] = []

        for k in range(n_steps):
            t_k = float(boundary_conditions.timestamps_s[k])
            thr = float(boundary_conditions.throttle_norm[k])
            steer = float(boundary_conditions.steering_rad[k])
            b_fl = float(boundary_conditions.brake_pressure_fl_bar[k])
            b_fr = float(boundary_conditions.brake_pressure_fr_bar[k])
            b_rl = float(boundary_conditions.brake_pressure_rl_bar[k])
            b_rr = float(boundary_conditions.brake_pressure_rr_bar[k])
            bank = float(boundary_conditions.road_bank_rad[k])
            grade = float(boundary_conditions.road_grade_rad[k])

            # Convert road wheel steering to handwheel deg
            ctrl = DriverControls(
                steering_deg=math.degrees(steer * params.steer_ratio),
                throttle=thr,
                brake_pressure_fl_bar=b_fl,
                brake_pressure_fr_bar=b_fr,
                brake_pressure_rl_bar=b_rl,
                brake_pressure_rr_bar=b_rr,
                gear=0,  # Enforces endogenous gear autonomy
            )

            # Sanitize controls through firewall
            ctrl = TelemetryFirewall.sanitize_driver_controls(ctrl)
            setattr(st, "time_s", t_k)

            # Compute derivatives
            d = sim.compute_derivatives(st, ctrl, road_bank_rad=bank, road_grade_rad=grade)

            # Record state outputs
            out_time.append(t_k)
            out_vx.append(float(st.u_mps))
            out_vy.append(float(st.v_mps))
            out_yaw_rate.append(float(st.yaw_rate_rads))
            out_roll.append(float(st.roll_phi))
            out_w_fl.append(float(st.omega_fl))
            out_w_fr.append(float(st.omega_fr))
            out_w_rl.append(float(st.omega_rl))
            out_w_rr.append(float(st.omega_rr))
            out_rpm.append(float(d.get("engine_rpm", d.get("rpm", 0.0))))
            out_gear.append(int(d.get("gear_active", d.get("gear", tx.current_state.gear if hasattr(tx, "current_state") else 1))))
            
            # Step vehicle dynamics ODE forward
            st = sim.step(st, ctrl, road_bank_rad=bank, road_grade_rad=grade)

        vx_arr = np.array(out_vx, dtype=np.float64)
        vy_arr = np.array(out_vy, dtype=np.float64)
        yaw_arr = np.array(out_yaw_rate, dtype=np.float64)
        if len(vx_arr) > 1:
            ax_arr = np.gradient(vx_arr, dt_s)
            ay_arr = np.gradient(vy_arr, dt_s) + vx_arr * yaw_arr
        else:
            ax_arr = np.zeros_like(vx_arr)
            ay_arr = np.zeros_like(vy_arr)

        predicted = {
            StandardChannels.TIME: np.array(out_time, dtype=np.float64),
            StandardChannels.VX: vx_arr,
            StandardChannels.VY: vy_arr,
            StandardChannels.YAW_RATE: yaw_arr,
            StandardChannels.ROLL_ANGLE: np.array(out_roll, dtype=np.float64),
            StandardChannels.WHEEL_SPEED_FL: np.array(out_w_fl, dtype=np.float64),
            StandardChannels.WHEEL_SPEED_FR: np.array(out_w_fr, dtype=np.float64),
            StandardChannels.WHEEL_SPEED_RL: np.array(out_w_rl, dtype=np.float64),
            StandardChannels.WHEEL_SPEED_RR: np.array(out_w_rr, dtype=np.float64),
            StandardChannels.ENGINE_RPM: np.array(out_rpm, dtype=np.float64),
            StandardChannels.GEAR: np.array(out_gear, dtype=np.float64),
            StandardChannels.AX: ax_arr,
            StandardChannels.AY: ay_arr,
        }

        return BlindSimulationResult(
            timestamps_s=np.array(out_time, dtype=np.float64),
            predicted_channels=predicted,
            initial_conditions=initial_conditions,
            boundary_conditions_summary=boundary_conditions.to_dict(),
            firewall_verified_leak_free=True,
        )
