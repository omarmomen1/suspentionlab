"""
physics/hil_interface.py
========================
SuspensionLab PRO — Real-Time Hardware-In-The-Loop (HIL) Execution & Deadline Monitor

Enforces deterministic real-time execution contracts for Driver-in-the-Loop (DIL)
and Hardware-in-the-Loop (HIL) simulator integration.

Primary Real-Time Metrics:
--------------------------
1. Worst-Case Execution Time (WCET): Maximum time taken by a single solver step.
2. Deadline Miss Rate: Fraction of solver steps exceeding the discrete time-step budget dt.
3. Execution Jitter: Standard deviation of solver cycle execution duration.
4. CAN / UDP Packet Serialization: Real-time telemetry broadcast.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class HILPerformanceProfile:
    """Statistical summary of real-time execution over an HIL simulation run."""
    total_steps: int
    dt_target_us: float               # Target step budget in microseconds (e.g. 1000 us for 1 kHz)
    wcet_us: float                    # Worst-Case Execution Time [us]
    mean_execution_us: float          # Average execution time [us]
    jitter_us: float                  # Execution time standard deviation [us]
    deadline_misses: int              # Number of times execution exceeded dt_target_us
    deadline_miss_rate_pct: float     # Percentage of steps missing deadline
    is_hard_realtime_compliant: bool  # True if miss rate <= 0.01% and WCET < 1.5 * dt_target

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_steps": self.total_steps,
            "dt_target_us": self.dt_target_us,
            "wcet_us": round(self.wcet_us, 2),
            "mean_execution_us": round(self.mean_execution_us, 2),
            "jitter_us": round(self.jitter_us, 2),
            "deadline_misses": self.deadline_misses,
            "deadline_miss_rate_pct": round(self.deadline_miss_rate_pct, 4),
            "is_hard_realtime_compliant": self.is_hard_realtime_compliant,
        }


@dataclass
class CANTelemetryFrame:
    """Standard 8-byte CAN telemetry frame serialization."""
    can_id: int                       # 11-bit or 29-bit CAN ID (e.g. 0x301 for FL damper)
    timestamp_us: int
    payload_bytes: bytes

    @classmethod
    def pack_corner_telemetry(
        cls,
        can_id: int,
        timestamp_us: int,
        travel_mm: float,
        velocity_mm_s: float,
        normal_load_n: float,
    ) -> CANTelemetryFrame:
        """Pack travel, velocity, and load into an 8-byte CAN payload."""
        # 16-bit travel (0.01 mm res), 16-bit velocity (0.1 mm/s res), 32-bit load (0.1 N res)
        t_raw = int(np.clip(travel_mm * 100.0, -32768, 32767))
        v_raw = int(np.clip(velocity_mm_s * 10.0, -32768, 32767))
        f_raw = int(np.clip(normal_load_n * 10.0, 0, 4294967295))
        payload = struct.pack(">hhI", t_raw, v_raw, f_raw)
        return cls(can_id=can_id, timestamp_us=timestamp_us, payload_bytes=payload)


class DeterministicHILRunner:
    """Deterministic step-by-step runner with real-time deadline monitoring."""

    def __init__(self, target_frequency_hz: float = 1000.0):
        self.dt_s = 1.0 / target_frequency_hz
        self.dt_us = self.dt_s * 1_000_000.0
        self.step_durations_us: List[float] = []

    def execute_session(
        self,
        step_fn: Callable[[float, float], Any],
        duration_s: float = 1.0,
    ) -> HILPerformanceProfile:
        """Run simulated real-time session and monitor execution deadlines."""
        total_steps = int(duration_s / self.dt_s)
        self.step_durations_us = []
        deadline_misses = 0

        # Warm up step to prime cache and JIT/allocators before timing
        try:
            step_fn(0.0, self.dt_s)
        except Exception:
            pass

        sim_time = 0.0
        for _ in range(total_steps):
            t_start = time.perf_counter_ns()
            
            # Execute one discrete physics step
            step_fn(sim_time, self.dt_s)
            
            t_end = time.perf_counter_ns()
            duration_us = (t_end - t_start) / 1000.0
            self.step_durations_us.append(duration_us)

            if duration_us > self.dt_us:
                deadline_misses += 1

            sim_time += self.dt_s

        durations = np.array(self.step_durations_us)
        wcet = float(np.max(durations)) if len(durations) > 0 else 0.0
        mean_dur = float(np.mean(durations)) if len(durations) > 0 else 0.0
        jitter = float(np.std(durations)) if len(durations) > 0 else 0.0
        miss_rate = (deadline_misses / max(total_steps, 1)) * 100.0
        compliant = (miss_rate <= 0.01) and (wcet <= self.dt_us * 1.5)

        return HILPerformanceProfile(
            total_steps=total_steps,
            dt_target_us=self.dt_us,
            wcet_us=wcet,
            mean_execution_us=mean_dur,
            jitter_us=jitter,
            deadline_misses=deadline_misses,
            deadline_miss_rate_pct=miss_rate,
            is_hard_realtime_compliant=compliant,
        )
