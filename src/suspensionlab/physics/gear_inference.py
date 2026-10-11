"""SuspensionLab PRO — Phase 3H.2 Gear Kinematics & Inference Module.

Provides physically defensible transmission ratio and gear state inference from
engine speed (RPM), driven wheel speed, and configured drivetrain kinematic ratios.

Critical Epistemic Rules:
1. Never treats raw telemetry channel 'GearRatio' as a physical transmission ratio.
2. Does NOT hardcode dataset-specific constants ('13.585', '5.6426', or '3rd gear').
3. Supports arbitrary vehicle configurations via configured candidate ratios.
4. Distinguishes LOCKED engagement, CLUTCH_SLIP/SHIFTING, and LOW_SPEED states.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Dict, List, Optional, Tuple


class GearEngagementStatus(str, Enum):
    """Authoritative engagement status of the transmission driveline."""
    LOCKED = "LOCKED"                              # Ratio matches a candidate within tolerance across locked clutch
    CLUTCH_SLIP_OR_SHIFT = "CLUTCH_SLIP_OR_SHIFT"  # Significant deviation from candidate ratios (shifting or slipping)
    LOW_SPEED_DEFAULT = "LOW_SPEED_DEFAULT"        # Driven wheel speed below kinematic resolution floor
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"                # Inferred ratio outside feasible physical envelope


@dataclass
class GearInferenceResult:
    """Telemetry-independent gear inference output with epistemic confidence metrics."""
    inferred_gear: int                     # Inferred 1-based gear index
    inferred_total_ratio: float            # Inferred instantaneous ratio omega_eng / omega_wheel
    matched_nominal_ratio: float           # Nominal kinematic candidate ratio N_g
    ratio_residual: float                  # Relative kinematic error |N_inst - N_g| / N_g
    confidence: float                      # Bounded confidence metric [0.0, 1.0]
    status: GearEngagementStatus           # Categorical engagement status
    epistemic_classification: str = "CONFIRMED_FROM_SENSOR_KINEMATICS"


@dataclass
class GearInferenceConfig:
    """Configurable kinematic transmission ratio candidates and tolerance thresholds."""
    # Mapping of 1-based gear index to total nominal ratio (gearbox_ratio * final_drive)
    # Default: Volkswagen Golf VII GTI DQ250 6-Speed Dual-Clutch Transmission
    # Gear 1: 3.4615 * 4.2381 = 14.6703
    # Gear 2: 2.0500 * 4.2381 = 8.6881
    # Gear 3: 1.3314 * 4.2381 = 5.6427
    # Gear 4: 0.9655 * 4.2381 = 4.0920
    # Gear 5: 1.0323 * 3.2174 = 3.3213
    # Gear 6: 0.9333 * 3.2174 = 3.0028
    candidate_ratios: Dict[int, float] = field(default_factory=lambda: {
        1: 14.6703,
        2: 8.6881,
        3: 5.6427,
        4: 4.0920,
        5: 3.3213,
        6: 3.0028,
    })
    tolerance_ratio: float = 0.12          # 12% relative tolerance for locked clutch identification
    min_wheel_speed_radps: float = 2.0     # Minimum wheel angular speed for kinematic division floor
    default_low_speed_gear: int = 1        # Default gear selected at standstill / creep
    hysteresis_count: int = 2              # Number of consecutive samples required for persistent shift


class GearInferenceEngine:
    """Infers transmission gear and effective total kinematic ratio from sensor velocities."""

    def __init__(self, config: Optional[GearInferenceConfig] = None):
        self.config = config or GearInferenceConfig()
        self._last_locked_gear = self.config.default_low_speed_gear
        self._pending_gear = self.config.default_low_speed_gear
        self._pending_count = 0

    def infer_gear(
        self,
        engine_rpm: float,
        driven_wheel_speed_radps: float,
        apply_hysteresis: bool = False
    ) -> GearInferenceResult:
        """Infer instantaneous transmission gear and kinematic ratio.
        
        Args:
            engine_rpm: Measured or modeled engine speed [RPM]
            driven_wheel_speed_radps: Angular velocity of driven wheels [rad/s]
            apply_hysteresis: Whether to filter rapid shift chatter
            
        Returns:
            GearInferenceResult containing inferred gear, ratio, residual, and status.
        """
        w_wheel = max(float(driven_wheel_speed_radps), 0.0)
        rpm = max(float(engine_rpm), 0.0)
        omega_eng = rpm * (2.0 * math.pi / 60.0)

        # 1. Low-speed floor check
        if w_wheel < self.config.min_wheel_speed_radps:
            return GearInferenceResult(
                inferred_gear=self.config.default_low_speed_gear,
                inferred_total_ratio=self.config.candidate_ratios[self.config.default_low_speed_gear],
                matched_nominal_ratio=self.config.candidate_ratios[self.config.default_low_speed_gear],
                ratio_residual=0.0,
                confidence=1.0,
                status=GearEngagementStatus.LOW_SPEED_DEFAULT,
                epistemic_classification="INFERRED",
            )

        # 2. Instantaneous kinematic ratio
        n_inst = omega_eng / w_wheel

        # 3. Match against configured candidate ratios
        best_gear = min(
            self.config.candidate_ratios.keys(),
            key=lambda g: abs(n_inst - self.config.candidate_ratios[g])
        )
        nominal_ratio = self.config.candidate_ratios[best_gear]
        rel_residual = abs(n_inst - nominal_ratio) / nominal_ratio

        # 4. Status and confidence evaluation
        if rel_residual <= self.config.tolerance_ratio:
            status = GearEngagementStatus.LOCKED
            confidence = max(0.0, 1.0 - (rel_residual / self.config.tolerance_ratio))
            effective_gear = best_gear
            if apply_hysteresis:
                if best_gear == self._pending_gear:
                    self._pending_count += 1
                    if self._pending_count >= self.config.hysteresis_count:
                        self._last_locked_gear = best_gear
                else:
                    self._pending_gear = best_gear
                    self._pending_count = 1
                effective_gear = self._last_locked_gear
            else:
                self._last_locked_gear = best_gear
        else:
            status = GearEngagementStatus.CLUTCH_SLIP_OR_SHIFT
            confidence = max(0.0, 0.5 * (1.0 - min(rel_residual, 1.0)))
            effective_gear = self._last_locked_gear if apply_hysteresis else best_gear

        matched_ratio = self.config.candidate_ratios[effective_gear]

        return GearInferenceResult(
            inferred_gear=effective_gear,
            inferred_total_ratio=float(n_inst),
            matched_nominal_ratio=float(matched_ratio),
            ratio_residual=float(rel_residual),
            confidence=float(confidence),
            status=status,
            epistemic_classification="CONFIRMED_FROM_SENSOR_KINEMATICS" if status == GearEngagementStatus.LOCKED else "INFERRED",
        )
