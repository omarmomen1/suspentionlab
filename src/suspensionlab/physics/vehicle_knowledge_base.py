"""
physics/vehicle_knowledge_base.py
=================================
SuspensionLab PRO — Calibrated Vehicle Knowledge Base & Institutional Moat

Accumulates empirical vehicle behavior, session calibrations, track-specific bias corrections,
and setup lineages over thousands of racing kilometers.

The Proprietary Moat:
---------------------
Generic vehicle dynamic simulators model idealized textbook cars.
SuspensionLab captures the idiosyncratic behavior of the team's *actual* physical chassis:
- Real-world aero elastic deflection biases
- Damper hysteresis and temperature degradation signatures
- Compliance and bush deflection offsets
- Driver-specific pitch/roll sensitivity preferences
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionCalibrationRecord:
    """Historical telemetry session calibration and model discrepancy record."""
    session_id: str
    track_id: str                     # e.g. "Silverstone-GP"
    chassis_serial: str               # e.g. "SF26-Chassis-02"
    timestamp_iso: str
    telemetry_samples_count: int
    mean_model_residual_mm: float
    setup_parameters: Dict[str, float]
    learned_empirical_offsets: Dict[str, float]  # e.g. {"aero_cop_bias": -0.015, "rear_compliance_mm_per_kn": 0.42}


@dataclass
class VehicleKnowledgeBase:
    """Accumulated proprietary engineering knowledge base for a specific vehicle chassis."""
    team_id: str
    chassis_serial: str
    total_telemetry_points_analyzed: int = 0
    total_sessions_recorded: int = 0
    calibration_history: List[SessionCalibrationRecord] = field(default_factory=list)
    track_biases: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def record_session(
        self,
        session_id: str,
        track_id: str,
        telemetry_samples: int,
        mean_residual_mm: float,
        setup_params: Dict[str, float],
        learned_offsets: Dict[str, float],
    ) -> None:
        """Record and integrate a new track session into the knowledge base."""
        rec = SessionCalibrationRecord(
            session_id=session_id,
            track_id=track_id,
            chassis_serial=self.chassis_serial,
            timestamp_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            telemetry_samples_count=telemetry_samples,
            mean_model_residual_mm=mean_residual_mm,
            setup_parameters=setup_params,
            learned_empirical_offsets=learned_offsets,
        )
        self.calibration_history.append(rec)
        self.total_sessions_recorded += 1
        self.total_telemetry_points_analyzed += telemetry_samples

        # Update running track bias estimate
        if track_id not in self.track_biases:
            self.track_biases[track_id] = {}
        for k, v in learned_offsets.items():
            prev = self.track_biases[track_id].get(k, v)
            self.track_biases[track_id][k] = 0.7 * prev + 0.3 * v  # Exponential moving average

    def get_track_calibrated_offsets(self, track_id: str) -> Dict[str, float]:
        """Retrieve learned empirical offsets tailored to a specific circuit."""
        return self.track_biases.get(track_id, {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_id": self.team_id,
            "chassis_serial": self.chassis_serial,
            "total_telemetry_points": self.total_telemetry_points_analyzed,
            "total_sessions": self.total_sessions_recorded,
            "track_biases": self.track_biases,
        }
