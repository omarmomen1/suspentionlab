"""
suspensionlab.telemetry.gateway
===============================
High-Throughput Telemetry Ingestion Gateway & Digital Twin Engine.

Validates raw DAQ / replay feeds:
- Timestamp monotonicity & jitter
- Physical sensor boundaries & quality flags
- Sequence loss, duplicate, and reordering tracking
- Real-time Pacejka QSS Digital Twin evaluation (ay_max / g)
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any

from suspensionlab.physics.lap_sim import LapSimVehicle
from suspensionlab.telemetry.protocol import (
    ChannelId,
    ChannelSample,
    DigitalTwinState,
    GripStatusCode,
    QualityCode,
    SLTPFrame,
    CHANNEL_NAME_TO_ID,
)

logger = logging.getLogger(__name__)

STANDARD_GRAVITY = 9.80665

# Physical sensor limit guards
CHANNEL_LIMITS: Dict[ChannelId, Tuple[float, float]] = {
    ChannelId.SPEED_MS: (0.0, 125.0),          # up to 450 km/h
    ChannelId.LAT_G: (-6.5, 6.5),              # F1 aero max ~6g
    ChannelId.LONG_G: (-6.5, 6.5),             # Heavy braking ~5.5g
    ChannelId.VERT_G: (-4.0, 8.0),             # Kerbs / bumps
    ChannelId.STEER_RAD: (-6.28, 6.28),        # +/- 360 deg
    ChannelId.SUSP_TRAVEL_FL: (-50.0, 150.0),  # mm
    ChannelId.SUSP_TRAVEL_FR: (-50.0, 150.0),
    ChannelId.SUSP_TRAVEL_RL: (-50.0, 150.0),
    ChannelId.SUSP_TRAVEL_RR: (-50.0, 150.0),
    ChannelId.BRAKE_PRESS_F: (0.0, 250.0),     # bar
    ChannelId.THROTTLE_POS: (0.0, 100.0),      # %
    ChannelId.ENGINE_RPM: (0.0, 20000.0),      # rpm
    ChannelId.YAW_RATE: (-180.0, 180.0),       # deg/s
}


@dataclass
class IngestionStats:
    total_received: int = 0
    total_valid: int = 0
    dropped_packets: int = 0
    duplicate_packets: int = 0
    out_of_order_packets: int = 0
    boundary_violations: int = 0
    last_timestamp: float = 0.0
    last_sequence: int = 0
    rate_hz: float = 0.0
    _last_rate_calc_time: float = field(default_factory=time.monotonic)
    _rate_frame_counter: int = 0


class TelemetryIngestionGateway:
    """Production ingestion gateway validating DAQ stream and attaching Digital Twin state."""

    def __init__(self, vehicle: Optional[LapSimVehicle] = None):
        self.vehicle = vehicle or LapSimVehicle()
        self.stats_by_session: Dict[str, IngestionStats] = {}
        self.seen_sequences_by_session: Dict[str, set[int]] = {}
        self._ay_max_cache: Dict[float, float] = {}

        # Engineering traceability metadata (Rule 12)
        self.metadata = {
            "model_version": "2.4.0",
            "solver": "Pacejka-MF5.2-QSS-ay_max",
            "backend": "FastAPI-AsyncEngine",
            "parameter_version": "PRO-AeroV2",
            "software_build": "2026.3-PRO",
        }

    def _get_stats(self, session_id: str) -> IngestionStats:
        if session_id not in self.stats_by_session:
            self.stats_by_session[session_id] = IngestionStats()
            self.seen_sequences_by_session[session_id] = set()
        return self.stats_by_session[session_id]

    def validate_and_process(
        self,
        raw_frame: SLTPFrame | Dict[str, Any],
        org_id: str = "org-default",
        session_id: str = "sess-default",
    ) -> SLTPFrame:
        """
        Validate incoming raw telemetry frame, check continuity, and compute
        real-time Digital Twin physical grip limit.
        """
        stats = self._get_stats(session_id)
        seen_seqs = self.seen_sequences_by_session[session_id]
        stats.total_received += 1

        # Calculate live ingestion rate
        now = time.monotonic()
        stats._rate_frame_counter += 1
        dt_rate = now - stats._last_rate_calc_time
        if dt_rate >= 0.5:
            stats.rate_hz = round(stats._rate_frame_counter / dt_rate, 1)
            stats._rate_frame_counter = 0
            stats._last_rate_calc_time = now

        # Convert dict input to SLTPFrame if needed
        if isinstance(raw_frame, dict):
            frame = self._dict_to_sltp(raw_frame, org_id, session_id, stats)
        else:
            frame = raw_frame

        seq = frame.sequence_number
        ts = frame.timestamp

        # 1. Sequence Loss & Order Tracking
        if stats.last_sequence > 0:
            if seq in seen_seqs:
                stats.duplicate_packets += 1
            elif seq < stats.last_sequence:
                stats.out_of_order_packets += 1
            elif seq > stats.last_sequence + 1:
                dropped = seq - (stats.last_sequence + 1)
                stats.dropped_packets += dropped

        seen_seqs.add(seq)
        # Limit memory of seen sequence set
        if len(seen_seqs) > 10000:
            min_keep = max(0, seq - 5000)
            seen_seqs.intersection_update(s for s in seen_seqs if s >= min_keep)

        if seq > stats.last_sequence:
            stats.last_sequence = seq

        # 2. Timestamp Monotonicity Check
        is_jitter = False
        if stats.last_timestamp > 0.0:
            dt = ts - stats.last_timestamp
            if dt <= 0.0 or dt > 2.0:
                is_jitter = True

        stats.last_timestamp = ts

        # 3. Channel Range Validation & Quality Tagging
        validated_samples: list[ChannelSample] = []
        speed_ms = 0.0
        actual_lat_g = 0.0

        for sample in frame.samples:
            cid = sample.channel_id
            val = sample.value
            quality = QualityCode.GOOD

            if is_jitter:
                quality = QualityCode.DEGRADED

            if cid in CHANNEL_LIMITS:
                vmin, vmax = CHANNEL_LIMITS[cid]
                if val < vmin or val > vmax:
                    stats.boundary_violations += 1
                    quality = QualityCode.OUT_OF_RANGE
                    # Clamp or preserve according to non-destructive preservation
                    val = max(vmin, min(vmax, val))

            if cid == ChannelId.SPEED_MS:
                speed_ms = val
            elif cid == ChannelId.LAT_G:
                actual_lat_g = val

            validated_samples.append(ChannelSample(cid, val, quality))

        # 4. Real Digital Twin Physics Limit Calculation
        twin_state = self._evaluate_digital_twin(speed_ms, actual_lat_g)

        stats.total_valid += 1

        return SLTPFrame(
            sequence_number=seq,
            timestamp=ts,
            org_id=frame.org_id or org_id,
            session_id=frame.session_id or session_id,
            samples=validated_samples,
            twin=twin_state,
        )

    def _evaluate_digital_twin(self, speed_ms: float, actual_lat_g: float) -> DigitalTwinState:
        """
        Computes maximum lateral capability using real Pacejka QSS solver on LapSimVehicle.
        Formula: theoretical_max_lat_g = vehicle.ay_max(v) / 9.80665.
        Uses high-performance speed-binning cache (0.5 m/s bins) for real-time >= 100 Hz throughput.
        """
        v = max(1.0, float(speed_ms))
        v_bin = round(v * 2.0) / 2.0
        if v_bin not in self._ay_max_cache:
            try:
                ay_max_si = self.vehicle.ay_max(v_bin, bank_rad=0.0)
                self._ay_max_cache[v_bin] = max(0.1, ay_max_si / STANDARD_GRAVITY)
            except Exception as exc:
                logger.warning("Digital Twin ay_max solver exception: %s", exc)
                self._ay_max_cache[v_bin] = 1.2

        theoretical_max_lat_g = self._ay_max_cache[v_bin]

        measured_abs_lat_g = abs(actual_lat_g)
        divergence = 0.0
        if theoretical_max_lat_g > 1e-4:
            divergence = ((theoretical_max_lat_g - measured_abs_lat_g) / theoretical_max_lat_g) * 100.0

        if divergence > 15.0:
            grip_code = GripStatusCode.UNDER_UTILISING
        elif divergence < -5.0:
            grip_code = GripStatusCode.EXCEEDING_LIMIT
        else:
            grip_code = GripStatusCode.OPTIMAL

        return DigitalTwinState(
            theoretical_max_lat_g=round(theoretical_max_lat_g, 3),
            actual_lat_g=round(measured_abs_lat_g, 3),
            divergence_pct=round(divergence, 1),
            grip_status=grip_code,
        )

    def _dict_to_sltp(
        self,
        data: Dict[str, Any],
        org_id: str,
        session_id: str,
        stats: IngestionStats,
    ) -> SLTPFrame:
        seq = int(data.get("seq", data.get("sequence_number", stats.last_sequence + 1)))
        ts = float(data.get("ts", data.get("timestamp", time.time())))
        frame_org = str(data.get("org_id", org_id))
        frame_sess = str(data.get("session_id", session_id))

        samples: list[ChannelSample] = []

        # Check for direct 'channels' subdict or top-level keys
        channels_source = data.get("channels", data)
        for key, val in channels_source.items():
            if not isinstance(val, (int, float)):
                continue
            norm_key = key.lower().strip()
            cid = CHANNEL_NAME_TO_ID.get(norm_key, ChannelId.UNKNOWN)
            if cid != ChannelId.UNKNOWN:
                samples.append(ChannelSample(cid, float(val), QualityCode.GOOD))

        # Check direct top-level keys if not in channels
        if "speed_ms" in data and not any(s.channel_id == ChannelId.SPEED_MS for s in samples):
            samples.append(ChannelSample(ChannelId.SPEED_MS, float(data["speed_ms"])))
        if "lat_g" in data and not any(s.channel_id == ChannelId.LAT_G for s in samples):
            samples.append(ChannelSample(ChannelId.LAT_G, float(data["lat_g"])))
        if "long_g" in data and not any(s.channel_id == ChannelId.LONG_G for s in samples):
            samples.append(ChannelSample(ChannelId.LONG_G, float(data["long_g"])))
        if "steer_rad" in data and not any(s.channel_id == ChannelId.STEER_RAD for s in samples):
            samples.append(ChannelSample(ChannelId.STEER_RAD, float(data["steer_rad"])))

        return SLTPFrame(
            sequence_number=seq,
            timestamp=ts,
            org_id=frame_org,
            session_id=frame_sess,
            samples=samples,
        )

    def get_stats(self, session_id: str) -> Dict[str, Any]:
        stats = self._get_stats(session_id)
        return {
            "session_id": session_id,
            "total_received": stats.total_received,
            "total_valid": stats.total_valid,
            "dropped_packets": stats.dropped_packets,
            "duplicate_packets": stats.duplicate_packets,
            "out_of_order_packets": stats.out_of_order_packets,
            "boundary_violations": stats.boundary_violations,
            "current_rate_hz": stats.rate_hz,
            "last_sequence": stats.last_sequence,
            "metadata": self.metadata,
        }
