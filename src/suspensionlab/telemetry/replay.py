"""
suspensionlab.telemetry.replay
==============================
High-Frequency Telemetry Replay Engine.

Replays authentic recorded track sessions (e.g. MoTeC Spa 100 Hz session)
through the Ingestion Gateway and Streaming Hub with high-resolution
drift-corrected timing.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from suspensionlab.telemetry.gateway import TelemetryIngestionGateway
from suspensionlab.telemetry.hub import TelemetryHub, global_telemetry_hub
from suspensionlab.telemetry.protocol import (
    ChannelId,
    ChannelSample,
    QualityCode,
    SLTPFrame,
)

logger = logging.getLogger(__name__)


@dataclass
class ReplayStatus:
    is_running: bool = False
    session_id: str = ""
    org_id: str = ""
    current_index: int = 0
    total_samples: int = 0
    target_rate_hz: float = 100.0
    measured_rate_hz: float = 0.0
    elapsed_seconds: float = 0.0
    dataset_name: str = ""
    error: Optional[str] = None


class TelemetryReplayEngine:
    """Streams CSV telemetry datasets at calibrated 100 Hz rates."""

    def __init__(
        self,
        gateway: Optional[TelemetryIngestionGateway] = None,
        hub: Optional[TelemetryHub] = None,
    ):
        self.gateway = gateway or TelemetryIngestionGateway()
        self.hub = hub or global_telemetry_hub
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._status_by_session: Dict[str, ReplayStatus] = {}

    def get_status(self, session_id: str) -> ReplayStatus:
        if session_id not in self._status_by_session:
            return ReplayStatus(session_id=session_id)
        return self._status_by_session[session_id]

    async def start_replay(
        self,
        csv_path: str,
        session_id: str = "sess-live",
        org_id: str = "org-default",
        rate_hz: float = 100.0,
        loop_playback: bool = True,
    ) -> ReplayStatus:
        """Start streaming recorded telemetry file at specified rate."""
        await self.stop_replay(session_id)

        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Telemetry replay file not found: {csv_path}")

        # Bind session to organization in the hub
        self.hub.register_session_owner(session_id, org_id)

        status = ReplayStatus(
            is_running=True,
            session_id=session_id,
            org_id=org_id,
            target_rate_hz=rate_hz,
            dataset_name=os.path.basename(csv_path),
        )
        self._status_by_session[session_id] = status

        task = asyncio.create_task(
            self._replay_loop(csv_path, session_id, org_id, rate_hz, loop_playback)
        )
        self._active_tasks[session_id] = task
        return status

    async def stop_replay(self, session_id: str) -> None:
        """Halt replay task for a session."""
        task = self._active_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if session_id in self._status_by_session:
            self._status_by_session[session_id].is_running = False

    async def _replay_loop(
        self,
        csv_path: str,
        session_id: str,
        org_id: str,
        rate_hz: float,
        loop_playback: bool,
    ) -> None:
        status = self._status_by_session[session_id]
        interval_s = 1.0 / max(1.0, rate_hz)

        try:
            # Pre-parse CSV records into memory for zero I/O latency during 100 Hz stream
            records: List[Dict[str, float]] = []
            with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    parsed_row: Dict[str, float] = {}
                    for k, v in row.items():
                        if not k:
                            continue
                        clean_key = k.strip().lower()
                        try:
                            parsed_row[clean_key] = float(v.strip())
                        except (ValueError, TypeError):
                            continue
                    if parsed_row:
                        records.append(parsed_row)

            if not records:
                status.error = "No valid data rows in replay dataset"
                status.is_running = False
                return

            status.total_samples = len(records)
            seq = 1

            while True:
                start_mono = time.monotonic()
                frames_in_batch = 0
                batch_start_time = start_mono

                for idx, row in enumerate(records):
                    status.current_index = idx + 1
                    sim_time = row.get("time", idx * interval_s)

                    # Extract speed (MoTeC is km/h, convert to m/s)
                    raw_speed = row.get("speed", 0.0)
                    speed_ms = raw_speed / 3.6 if raw_speed > 0 else 0.0

                    # Extract steer (MoTeC is deg, convert to rad)
                    raw_steer = row.get("steerangle", row.get("steer_deg", 0.0))
                    steer_rad = raw_steer * (math.pi / 180.0)

                    lat_g = row.get("g_lat", row.get("lat_g", 0.0))
                    long_g = row.get("g_lon", row.get("long_g", 0.0))
                    vert_g = row.get("g_vert", row.get("vert_g", 0.0))

                    samples = [
                        ChannelSample(ChannelId.SPEED_MS, speed_ms, QualityCode.GOOD),
                        ChannelSample(ChannelId.LAT_G, lat_g, QualityCode.GOOD),
                        ChannelSample(ChannelId.LONG_G, long_g, QualityCode.GOOD),
                        ChannelSample(ChannelId.VERT_G, vert_g, QualityCode.GOOD),
                        ChannelSample(ChannelId.STEER_RAD, steer_rad, QualityCode.GOOD),
                        ChannelSample(ChannelId.SUSP_TRAVEL_FL, row.get("susptravel_fl", 0.0), QualityCode.GOOD),
                        ChannelSample(ChannelId.SUSP_TRAVEL_FR, row.get("susptravel_fr", 0.0), QualityCode.GOOD),
                        ChannelSample(ChannelId.SUSP_TRAVEL_RL, row.get("susptravel_rl", 0.0), QualityCode.GOOD),
                        ChannelSample(ChannelId.SUSP_TRAVEL_RR, row.get("susptravel_rr", 0.0), QualityCode.GOOD),
                        ChannelSample(ChannelId.BRAKE_PRESS_F, row.get("brakepress_f", 0.0), QualityCode.GOOD),
                        ChannelSample(ChannelId.THROTTLE_POS, row.get("throttlepos", 0.0), QualityCode.GOOD),
                        ChannelSample(ChannelId.ENGINE_RPM, row.get("enginerpm", 0.0), QualityCode.GOOD),
                    ]

                    raw_frame = SLTPFrame(
                        sequence_number=seq,
                        timestamp=sim_time,
                        org_id=org_id,
                        session_id=session_id,
                        samples=samples,
                    )
                    seq += 1

                    # Ingestion Gateway: validate, assign quality, compute Pacejka Digital Twin
                    processed_frame = self.gateway.validate_and_process(
                        raw_frame, org_id=org_id, session_id=session_id
                    )

                    # Multi-Tenant Streaming Hub: broadcast to authorized subscribers
                    await self.hub.broadcast_frame(processed_frame)

                    # High-precision monotonic drift-corrected sleep
                    frames_in_batch += 1
                    now = time.monotonic()
                    elapsed = now - batch_start_time
                    if elapsed >= 0.5:
                        status.measured_rate_hz = round(frames_in_batch / elapsed, 1)
                        status.elapsed_seconds = round(now - start_mono, 1)
                        frames_in_batch = 0
                        batch_start_time = now

                    target_wake = start_mono + (idx + 1) * interval_s
                    remaining = target_wake - time.monotonic()
                    if remaining > 0.0005:
                        await asyncio.sleep(remaining)
                    else:
                        await asyncio.sleep(0)

                if not loop_playback:
                    break

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Telemetry replay engine error: %s", exc, exc_info=True)
            status.error = str(exc)
        finally:
            status.is_running = False


# Global singleton replay engine
global_replay_engine = TelemetryReplayEngine()
