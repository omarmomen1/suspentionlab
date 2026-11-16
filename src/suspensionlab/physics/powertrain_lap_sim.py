"""SuspensionLab PRO — Phase 3H.2 Powertrain Corrected Lap Simulator.

Implements controlled powertrain correction, gear-ratio inference, predictive
torque model execution, and actuator-replay modes without modifying or breaking
legacy production baselines.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
    DynamicTrackPoint,
    compute_axle_torque_split,
)
from suspensionlab.physics.gear_inference import (
    GearInferenceConfig,
    GearInferenceEngine,
    GearInferenceResult,
    GearEngagementStatus,
)
from suspensionlab.physics.engine_torque_model import (
    EngineTorqueModel,
    SyntheticEngineTorqueModel,
    PredictiveEngineTorqueModel,
    ActuatorReplayEngineTorque,
    DrivelineAccounting,
    DrivelineLedgerRecord,
)


class PowertrainCorrectedLapSimulator(DynamicLapSimulator):
    """Controlled simulation wrapper integrating gear inference and calibrated engine models."""

    def __init__(
        self,
        params: DynamicVehicleParams,
        gear_engine: Optional[GearInferenceEngine] = None,
        torque_model: Optional[EngineTorqueModel] = None,
        powertrain_mode: str = "PREDICTIVE", # "PREDICTIVE", "ACTUATOR_REPLAY", "SYNTHETIC"
        cf_mode: str = "BASELINE",           # CF_J, CF_K, CF_L, CF_M, CF_N, CF_O, CF_P, CF_Q
        zero_aero: bool = False,
        zero_grade: bool = False,
        use_measured_rpm: bool = False,
        autonomous_shifting: bool = False,
        transmission: Optional[Any] = None,
        **kwargs
    ):
        super().__init__(params=params, **kwargs)
        self.gear_engine = gear_engine or GearInferenceEngine()
        self.torque_model = torque_model or PredictiveEngineTorqueModel()
        self.powertrain_mode = powertrain_mode
        self.cf_mode = cf_mode
        self.zero_aero = zero_aero
        self.zero_grade = zero_grade
        self.use_measured_rpm = use_measured_rpm
        self.autonomous_shifting = autonomous_shifting
        self.transmission = transmission
        if self.autonomous_shifting and self.transmission is None:
            from suspensionlab.physics.transmission_state_machine import EndogenousTransmission
            self.transmission = EndogenousTransmission()

        self.current_meas_torque_nm: float = 0.0
        self.current_meas_rpm: float = 4000.0
        self.accounting = DrivelineAccounting(params.drivetrain_efficiency)
        self.ledger_history: List[DrivelineLedgerRecord] = []

    def set_boundary_actuators(self, torque_nm: float, rpm: float) -> None:
        """Update external actuator boundary values for replay modes."""
        self.current_meas_torque_nm = float(torque_nm)
        self.current_meas_rpm = float(rpm)
        if isinstance(self.torque_model, ActuatorReplayEngineTorque):
            self.torque_model.set_measured_torque(torque_nm)

    def compute_derivatives(
        self,
        st: DynamicVehicleState,
        ctrl: DriverControls,
        track_point: Optional[DynamicTrackPoint] = None,
        road_curvature: float = 0.0,
        road_bank_rad: float = 0.0,
        road_elevation_m: float = 0.0,
        road_grade_rad: float = 0.0,
    ) -> Dict[str, Any]:
        """Compute system state derivatives using physically corrected powertrain components."""
        p = self.params
        g = 9.81

        # Evaluate base derivatives
        derivs = super().compute_derivatives(
            st, ctrl, track_point, road_curvature, road_bank_rad, road_elevation_m, road_grade_rad
        )

        # Driven wheel angular velocity
        if p.drivetrain_layout == "FWD":
            omega_drive = max(0.5 * (st.omega_fl + st.omega_fr), 0.0)
        else:
            omega_drive = max(0.5 * (st.omega_rl + st.omega_rr), 0.0)

        # 1. Gear state and transmission ratio derivation
        if self.autonomous_shifting and self.transmission is not None:
            tx_st = self.transmission.current_state
            active_gear = tx_st.gear
            gr = self.transmission.get_ratio(active_gear)
            rpm_engine = tx_st.input_shaft_speed_radps * (60.0 / (2.0 * math.pi))
            act_thr = float(np.clip(ctrl.throttle, 0.0, 1.0))
            t_clutch_sum = tx_st.clutch1_torque_nm + tx_st.clutch2_torque_nm
            t_crank = t_clutch_sum
            t_provenance = "ENDOGENOUS_PREDICTION"
            t_drive_total = (t_clutch_sum * gr * p.drivetrain_efficiency)

            derivs["clutch1_torque_nm"] = tx_st.clutch1_torque_nm
            derivs["clutch2_torque_nm"] = tx_st.clutch2_torque_nm
            derivs["shift_state"] = tx_st.shift_state.value
            derivs["clutch_state"] = tx_st.clutch_state.value
        else:
            # Never use raw GearRatio channel as index. Use kinematic inference.
            rpm_eval = self.current_meas_rpm if self.use_measured_rpm else max(p.idle_rpm, (omega_drive * 5.6427 * (60.0 / (2.0 * math.pi))))
            gear_res = self.gear_engine.infer_gear(
                engine_rpm=rpm_eval,
                driven_wheel_speed_radps=omega_drive
            )
            active_gear = gear_res.inferred_gear
            gr = gear_res.matched_nominal_ratio

            # Determine effective engine speed
            rpm_engine = self.current_meas_rpm if self.use_measured_rpm else max(p.idle_rpm, (omega_drive * gr * (60.0 / (2.0 * math.pi))))

            # 2. Engine torque generation according to mode / counterfactual
            act_thr = float(np.clip(ctrl.throttle, 0.0, 1.0))
            shift_mult = 0.0 if st.shift_in_progress else 1.0

            if self.cf_mode == "CF_J":
                # Corrected gear inference + existing synthetic torque (360 * thr)
                t_crank = 360.0 * act_thr * shift_mult
                t_provenance = "DERIVED"
            elif self.cf_mode in ("CF_K", "CF_M"):
                # Corrected gear inference + measured-torque replay
                t_crank = self.current_meas_torque_nm * shift_mult
                t_provenance = "BOUNDARY_REPLAY"
            elif self.cf_mode in ("CF_L", "CF_N", "CF_O", "CF_P", "CF_Q") or self.powertrain_mode == "PREDICTIVE":
                # Corrected gear inference + predictive torque model f(RPM, throttle)
                t_crank = self.torque_model.compute_torque(act_thr, rpm_engine, gear=active_gear) * shift_mult
                t_provenance = "MODEL_SUPPORTED"
            elif self.powertrain_mode == "ACTUATOR_REPLAY":
                t_crank = self.current_meas_torque_nm * shift_mult
                t_provenance = "BOUNDARY_REPLAY"
            else:
                t_crank = 360.0 * act_thr * shift_mult
                t_provenance = "DERIVED"

            # 3. Axle torque and differential distribution
            t_drive_total = (t_crank * gr * p.drivetrain_efficiency)

        if p.drivetrain_layout == "FWD":
            t_drive_fl, t_drive_fr, mz_diff = compute_axle_torque_split(
                t_drive_total, st.omega_fl, st.omega_fr, p.diff_front
            )
            Rw = p.wheel_radius_m
            derivs["T_drive_fl"] = t_drive_fl
            derivs["T_drive_fr"] = t_drive_fr
            derivs["domega"][0] = (t_drive_fl - Rw * derivs["tire_forces_wheel"][0][0] - 0.05 * st.omega_fl) / p.I_w
            derivs["domega"][1] = (t_drive_fr - Rw * derivs["tire_forces_wheel"][1][0] - 0.05 * st.omega_fr) / p.I_w
        elif p.drivetrain_layout == "RWD":
            t_drive_rl, t_drive_rr, mz_diff = compute_axle_torque_split(
                t_drive_total, st.omega_rl, st.omega_rr, p.diff_rear
            )
            Rw = p.wheel_radius_m
            derivs["domega"][2] = (t_drive_rl - Rw * derivs["tire_forces_wheel"][2][0] - 0.05 * st.omega_rl) / p.I_w
            derivs["domega"][3] = (t_drive_rr - Rw * derivs["tire_forces_wheel"][3][0] - 0.05 * st.omega_rr) / p.I_w

        # 4. Diagnostics: Zero aero / zero grade adjustments
        if self.zero_aero or self.cf_mode == "CF_P":
            f_drag_orig = derivs["F_drag"]
            derivs["du"] += f_drag_orig / p.mass_kg
            derivs["F_drag"] = 0.0

        if self.zero_grade or self.cf_mode == "CF_Q":
            grade_eval = track_point.grade_angle_rad if track_point is not None else road_grade_rad
            f_grade_orig = -p.mass_kg * g * math.sin(grade_eval)
            derivs["du"] -= f_grade_orig / p.mass_kg
        derivs["engine_rpm"] = rpm_engine
        derivs["gear_active"] = active_gear
        derivs["transmission_ratio"] = gr
        derivs["torque_engine_crank_nm"] = t_crank
        derivs["torque_axle_nm"] = t_drive_total

        self._last_step_t_crank = t_crank
        self._last_step_rpm_engine = rpm_engine
        self._last_step_active_gear = active_gear
        self._last_step_gr = gr
        self._last_step_t_provenance = t_provenance

        return derivs

    def step(
        self,
        current_state: DynamicVehicleState,
        controls: DriverControls,
        track_point: Optional[DynamicTrackPoint] = None,
        road_curvature: float = 0.0,
        road_bank_rad: float = 0.0,
        road_elevation_m: float = 0.0,
        road_grade_rad: float = 0.0,
    ) -> DynamicVehicleState:
        """Advance simulation state by dt, advancing transmission state machine once per step."""
        if self.autonomous_shifting and self.transmission is not None:
            p = self.params
            if p.drivetrain_layout == "FWD":
                omega_drive = max(0.5 * (current_state.omega_fl + current_state.omega_fr), 0.0)
            else:
                omega_drive = max(0.5 * (current_state.omega_rl + current_state.omega_rr), 0.0)

            thr = float(np.clip(controls.throttle, 0.0, 1.0))
            brk = max(
                controls.brake_pressure_fl_bar,
                controls.brake_pressure_fr_bar,
                controls.brake_pressure_rl_bar,
                controls.brake_pressure_rr_bar,
            )
            t_now = getattr(current_state, "time_s", 0.0)
            ratio_nom = self.transmission.get_ratio()
            rpm_est = max(p.idle_rpm, (omega_drive * ratio_nom * (60.0 / (2.0 * math.pi))))
            t_demanded = self.torque_model.compute_torque(thr, rpm_est, gear=self.transmission.gear)

            self.transmission.step(
                sim_vx=current_state.u_mps,
                sim_omega_drive=omega_drive,
                throttle=thr,
                brake_bar=brk,
                demanded_engine_torque_nm=t_demanded,
                dt=self.dt_fixed_s,
                t_now=t_now,
            )

        next_state = super().step(
            current_state=current_state,
            controls=controls,
            track_point=track_point,
            road_curvature=road_curvature,
            road_bank_rad=road_bank_rad,
            road_elevation_m=road_elevation_m,
            road_grade_rad=road_grade_rad,
        )

        p = self.params
        if p.drivetrain_layout == "FWD":
            omega_drive = max(0.5 * (next_state.omega_fl + next_state.omega_fr), 0.0)
        else:
            omega_drive = max(0.5 * (next_state.omega_rl + next_state.omega_rr), 0.0)

        t_crank = getattr(self, "_last_step_t_crank", 0.0)
        rpm_engine = getattr(self, "_last_step_rpm_engine", 1000.0)
        active_gear = getattr(self, "_last_step_active_gear", 1)
        gr = getattr(self, "_last_step_gr", 1.0)
        t_provenance = getattr(self, "_last_step_t_provenance", "ENDOGENOUS_PREDICTION")

        r_eff = max(next_state.u_mps / max(omega_drive, 0.1), 0.315)
        fd_ratio = 4.2381 if active_gear <= 4 else 3.2174
        gb_ratio = gr / fd_ratio

        ledger_rec = self.accounting.record_step(
            time_s=getattr(next_state, "time_s", 0.0),
            engine_torque_nm=t_crank,
            engine_rpm=rpm_engine,
            gear=active_gear,
            gearbox_ratio=gb_ratio,
            final_drive_ratio=fd_ratio,
            dynamic_rolling_radius_m=r_eff,
            vehicle_speed_mps=next_state.u_mps,
            torque_provenance=t_provenance,
        )
        self.ledger_history.append(ledger_rec)

        return next_state
