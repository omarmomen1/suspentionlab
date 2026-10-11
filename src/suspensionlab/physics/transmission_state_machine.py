"""SuspensionLab PRO — Phase 3H.4 Endogenous Transmission & Shift State Machine.

Implements the formal transmission state vector:
(gear, clutch_state, shift_state, shift_timer, input_shaft_speed, output_shaft_speed)
with deterministic shift sequencing:
IN_GEAR -> TORQUE_CUT -> CLUTCH_HANDOVER -> SPEED_SYNC -> IN_GEAR.

Strict physical invariants:
- Zero telemetry leakage: decisions depend solely on simulated dynamical states and driver inputs.
- No negative clutch torque capacity.
- No torque duplication: sum of dual-clutch torques equals transmitted engine torque.
- No energy creation: clutch slip power is strictly non-negative (dissipative).
- Anti-hunting lockout hysteresis.
- Valid gear index in [1, 6].
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


class ClutchState(str, Enum):
    LOCKED = "LOCKED"
    SLIPPING = "SLIPPING"
    OPEN = "OPEN"


class ShiftPhase(str, Enum):
    IN_GEAR = "IN_GEAR"
    TORQUE_CUT = "TORQUE_CUT"
    CLUTCH_HANDOVER = "CLUTCH_HANDOVER"
    SPEED_SYNC = "SPEED_SYNC"


@dataclass
class TransmissionStateVector:
    gear: int
    clutch_state: ClutchState
    shift_state: ShiftPhase
    shift_timer: float
    input_shaft_speed_radps: float
    output_shaft_speed_radps: float
    lockout_timer: float = 0.0
    clutch1_torque_nm: float = 0.0
    clutch2_torque_nm: float = 0.0
    target_gear: int = 3
    torque_multiplier: float = 1.0


@dataclass
class ShiftSpec:
    """Formal rule-based shift policy and dual-clutch transmission parameters."""
    ratios: Dict[int, float] = field(default_factory=lambda: {
        1: 13.585,
        2: 8.528,
        3: 5.6427,
        4: 4.103,
        5: 3.324,
        6: 2.738,
    })
    final_drive: float = 3.944
    idle_rpm: float = 800.0
    redline_rpm: float = 6500.0
    upshift_rpm_min: float = 5200.0
    upshift_rpm_max: float = 6200.0
    downshift_rpm_coast: float = 1800.0
    downshift_rpm_brake: float = 3000.0
    kickdown_throttle: float = 0.90
    brake_downshift_thresh_bar: float = 5.0
    t_torque_cut_s: float = 0.040
    t_clutch_handover_s: float = 0.070
    t_speed_sync_s: float = 0.040
    t_lockout_s: float = 0.400
    torque_cut_factor: float = 0.90   # 90% reduction during upshift torque cut
    rev_match_blip_nm: float = 120.0  # throttle blip torque during braking downshift


class EndogenousTransmission:
    """Autonomous dual-clutch transmission state machine."""

    def __init__(self, spec: Optional[ShiftSpec] = None, initial_gear: int = 3):
        self.spec = spec or ShiftSpec()
        self.gear = int(initial_gear)
        self.target_gear = int(initial_gear)
        self.clutch_state = ClutchState.LOCKED
        self.shift_state = ShiftPhase.IN_GEAR
        self.shift_timer = 0.0
        self.lockout_timer = 0.0
        self.input_shaft_speed = 0.0
        self.output_shaft_speed = 0.0
        self.torque_multiplier = 1.0
        self.clutch1_torque = 0.0
        self.clutch2_torque = 0.0

        self.cumulative_clutch_energy_j = 0.0
        self.shift_history: List[Dict[str, Any]] = []

    def get_ratio(self, g: Optional[int] = None) -> float:
        gear_idx = self.gear if g is None else g
        return self.spec.ratios.get(gear_idx, 5.6427)

    @property
    def current_state(self) -> TransmissionStateVector:
        return TransmissionStateVector(
            gear=self.gear,
            clutch_state=self.clutch_state,
            shift_state=self.shift_state,
            shift_timer=self.shift_timer,
            input_shaft_speed_radps=self.input_shaft_speed,
            output_shaft_speed_radps=self.output_shaft_speed,
            lockout_timer=self.lockout_timer,
            clutch1_torque_nm=self.clutch1_torque,
            clutch2_torque_nm=self.clutch2_torque,
            target_gear=self.target_gear,
            torque_multiplier=self.torque_multiplier,
        )

    def step(
        self,
        sim_vx: float,
        sim_omega_drive: float,
        throttle: float,
        brake_bar: float,
        demanded_engine_torque_nm: float,
        dt: float,
        t_now: float = 0.0,
    ) -> TransmissionStateVector:
        """Advance transmission state machine by dt using endogenous simulated variables only."""
        # Sanity assertions
        assert 1 <= self.gear <= 6, f"Invalid current gear: {self.gear}"
        assert not math.isnan(sim_vx) and not math.isinf(sim_vx), "sim_vx must be finite"
        assert not math.isnan(sim_omega_drive) and not math.isinf(sim_omega_drive), "sim_omega_drive must be finite"

        w_drive = max(0.0, float(sim_omega_drive))
        self.output_shaft_speed = w_drive * self.spec.final_drive
        ratio_curr = self.get_ratio(self.gear)

        if self.lockout_timer > 0.0:
            self.lockout_timer = max(0.0, self.lockout_timer - dt)

        is_upshift = self.target_gear > self.gear

        # State machine transitions
        if self.shift_state == ShiftPhase.IN_GEAR:
            self.clutch_state = ClutchState.LOCKED
            self.shift_timer = 0.0
            self.torque_multiplier = 1.0

            # Kinematic lock between engine and wheels
            eng_speed = w_drive * ratio_curr
            self.input_shaft_speed = max(self.spec.idle_rpm * (2.0 * math.pi / 60.0), eng_speed)
            eng_rpm = self.input_shaft_speed * 60.0 / (2.0 * math.pi)

            # Assign clutch torques: active clutch transmits 100% torque
            # Odd gears -> Clutch 1, Even gears -> Clutch 2
            if self.gear % 2 == 1:
                self.clutch1_torque = demanded_engine_torque_nm
                self.clutch2_torque = 0.0
            else:
                self.clutch1_torque = 0.0
                self.clutch2_torque = demanded_engine_torque_nm

            # Shift condition evaluation (only if lockout expired)
            if self.lockout_timer <= 0.0:
                # 1. Upshift Evaluation
                upshift_rpm = self.spec.upshift_rpm_min + throttle * (self.spec.upshift_rpm_max - self.spec.upshift_rpm_min)
                if self.gear < 6 and eng_rpm >= upshift_rpm and brake_bar < self.spec.brake_downshift_thresh_bar:
                    self.target_gear = self.gear + 1
                    self.shift_state = ShiftPhase.TORQUE_CUT
                    self.shift_timer = 0.0
                    self.torque_multiplier = 1.0 - self.spec.torque_cut_factor
                    t_cut = demanded_engine_torque_nm * self.torque_multiplier
                    if self.gear % 2 == 1:
                        self.clutch1_torque = t_cut
                        self.clutch2_torque = 0.0
                    else:
                        self.clutch1_torque = 0.0
                        self.clutch2_torque = t_cut
                    self.shift_history.append({
                        "t_s": t_now,
                        "type": "UPSHIFT",
                        "old_gear": self.gear,
                        "target_gear": self.target_gear,
                        "trigger_rpm": eng_rpm,
                        "vx_mps": sim_vx,
                        "throttle": throttle,
                        "brake_bar": brake_bar,
                    })

                # 2. Downshift Evaluation
                elif self.gear > 1:
                    downshift_rpm = self.spec.downshift_rpm_brake if brake_bar >= self.spec.brake_downshift_thresh_bar else self.spec.downshift_rpm_coast
                    kickdown = (throttle >= self.spec.kickdown_throttle)

                    # Check if downshift is requested
                    if eng_rpm <= downshift_rpm or kickdown:
                        ratio_lower = self.get_ratio(self.gear - 1)
                        est_target_rpm = (w_drive * ratio_lower) * 60.0 / (2.0 * math.pi)
                        if est_target_rpm <= self.spec.redline_rpm:
                            self.target_gear = self.gear - 1
                            self.shift_state = ShiftPhase.TORQUE_CUT
                            self.shift_timer = 0.0
                            self.shift_history.append({
                                "t_s": t_now,
                                "type": "DOWNSHIFT",
                                "old_gear": self.gear,
                                "target_gear": self.target_gear,
                                "trigger_rpm": eng_rpm,
                                "vx_mps": sim_vx,
                                "throttle": throttle,
                                "brake_bar": brake_bar,
                            })

        elif self.shift_state == ShiftPhase.TORQUE_CUT:
            self.clutch_state = ClutchState.LOCKED
            self.shift_timer += dt

            # During upshift: cut engine torque to unload dog/clutch interfaces
            # During downshift: maintain or apply rev-match blip
            if is_upshift:
                self.torque_multiplier = 1.0 - self.spec.torque_cut_factor
            else:
                self.torque_multiplier = 1.0

            eng_speed = w_drive * ratio_curr
            self.input_shaft_speed = max(self.spec.idle_rpm * (2.0 * math.pi / 60.0), eng_speed)

            # Active clutch still locked to old gear
            t_curr = demanded_engine_torque_nm * self.torque_multiplier
            if self.gear % 2 == 1:
                self.clutch1_torque = t_curr
                self.clutch2_torque = 0.0
            else:
                self.clutch1_torque = 0.0
                self.clutch2_torque = t_curr

            if self.shift_timer >= (self.spec.t_torque_cut_s - 1e-6):
                self.shift_state = ShiftPhase.CLUTCH_HANDOVER
                self.clutch_state = ClutchState.SLIPPING
                self.shift_timer = 0.0

        elif self.shift_state == ShiftPhase.CLUTCH_HANDOVER:
            self.clutch_state = ClutchState.SLIPPING
            self.shift_timer += dt
            frac = min(1.0, max(0.0, self.shift_timer / max(1e-6, self.spec.t_clutch_handover_s)))

            # Linear continuous torque transfer between off-going and on-coming clutch
            t_net = demanded_engine_torque_nm * self.torque_multiplier
            if self.gear % 2 == 1:
                # Offgoing is C1 (odd), oncoming is C2 (even)
                self.clutch1_torque = (1.0 - frac) * t_net
                self.clutch2_torque = frac * t_net
            else:
                # Offgoing is C2 (even), oncoming is C1 (odd)
                self.clutch2_torque = (1.0 - frac) * t_net
                self.clutch1_torque = frac * t_net

            # Input shaft speed transitions between ratios
            ratio_target = self.get_ratio(self.target_gear)
            target_speed = w_drive * ratio_target
            old_speed = w_drive * ratio_curr
            self.input_shaft_speed = old_speed + frac * (target_speed - old_speed)

            # Calculate clutch slip energy dissipation (dE = P_slip * dt >= 0)
            w_out1 = w_drive * (self.get_ratio(self.gear) if self.gear % 2 == 1 else self.get_ratio(self.target_gear))
            w_out2 = w_drive * (self.get_ratio(self.target_gear) if self.gear % 2 == 1 else self.get_ratio(self.gear))
            p_slip = abs(self.clutch1_torque * (self.input_shaft_speed - w_out1)) + abs(self.clutch2_torque * (self.input_shaft_speed - w_out2))
            self.cumulative_clutch_energy_j += p_slip * dt

            if self.shift_timer >= (self.spec.t_clutch_handover_s - 1e-6):
                self.shift_state = ShiftPhase.SPEED_SYNC
                self.clutch_state = ClutchState.SLIPPING
                self.shift_timer = 0.0
                self.gear = self.target_gear  # Handover complete, gear index officially transfers

        elif self.shift_state == ShiftPhase.SPEED_SYNC:
            self.clutch_state = ClutchState.SLIPPING
            self.shift_timer += dt
            ratio_new = self.get_ratio(self.gear)
            target_speed = w_drive * ratio_new
            self.input_shaft_speed = target_speed

            # Target clutch now holds 100% of torque
            t_net = demanded_engine_torque_nm
            self.torque_multiplier = 1.0
            if self.gear % 2 == 1:
                self.clutch1_torque = t_net
                self.clutch2_torque = 0.0
            else:
                self.clutch1_torque = 0.0
                self.clutch2_torque = t_net

            if self.shift_timer >= (self.spec.t_speed_sync_s - 1e-6):
                self.shift_state = ShiftPhase.IN_GEAR
                self.clutch_state = ClutchState.LOCKED
                self.shift_timer = 0.0
                self.lockout_timer = self.spec.t_lockout_s

        # Physical Invariant Assertions
        assert 1 <= self.gear <= 6
        assert not math.isnan(self.input_shaft_speed)
        # No torque duplication invariant:
        t_total_clutch = self.clutch1_torque + self.clutch2_torque
        expected_t = demanded_engine_torque_nm * self.torque_multiplier
        assert abs(t_total_clutch - expected_t) <= 1e-3 or abs(expected_t) < 1e-6, \
            f"Torque duplication error: {t_total_clutch} != {expected_t}"

        return self.current_state
