"""
suspensionlab.telemetry.protocol
================================
SuspensionLab Telemetry Protocol v1 (SLTP v1).

Compact, high-frequency binary streaming protocol designed for motorsport
DAQ and Digital Twin integration at >= 100 Hz per corner.
"""

from __future__ import annotations

import enum
import json
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


MAGIC_HEADER = b"SLT1"
PROTOCOL_VERSION = 1


class ChannelId(enum.IntEnum):
    """Canonical DAQ telemetry channel identifiers."""
    UNKNOWN = 0
    SPEED_MS = 1
    LAT_G = 2
    LONG_G = 3
    VERT_G = 4
    STEER_RAD = 5
    SUSP_TRAVEL_FL = 6
    SUSP_TRAVEL_FR = 7
    SUSP_TRAVEL_RL = 8
    SUSP_TRAVEL_RR = 9
    BRAKE_PRESS_F = 10
    THROTTLE_POS = 11
    ENGINE_RPM = 12
    YAW_RATE = 13


# Reverse lookup and string name aliases for convenience
CHANNEL_NAME_TO_ID: Dict[str, ChannelId] = {
    "speed": ChannelId.SPEED_MS,
    "speed_ms": ChannelId.SPEED_MS,
    "lat_g": ChannelId.LAT_G,
    "g_lat": ChannelId.LAT_G,
    "long_g": ChannelId.LONG_G,
    "g_lon": ChannelId.LONG_G,
    "vert_g": ChannelId.VERT_G,
    "steer_rad": ChannelId.STEER_RAD,
    "steerangle": ChannelId.STEER_RAD,
    "susp_travel_fl": ChannelId.SUSP_TRAVEL_FL,
    "susptravel_fl": ChannelId.SUSP_TRAVEL_FL,
    "susp_travel_fr": ChannelId.SUSP_TRAVEL_FR,
    "susptravel_fr": ChannelId.SUSP_TRAVEL_FR,
    "susp_travel_rl": ChannelId.SUSP_TRAVEL_RL,
    "susptravel_rl": ChannelId.SUSP_TRAVEL_RL,
    "susp_travel_rr": ChannelId.SUSP_TRAVEL_RR,
    "susptravel_rr": ChannelId.SUSP_TRAVEL_RR,
    "brake_press_f": ChannelId.BRAKE_PRESS_F,
    "brakepress_f": ChannelId.BRAKE_PRESS_F,
    "throttle_pos": ChannelId.THROTTLE_POS,
    "throttlepos": ChannelId.THROTTLE_POS,
    "engine_rpm": ChannelId.ENGINE_RPM,
    "enginerpm": ChannelId.ENGINE_RPM,
    "yaw_rate": ChannelId.YAW_RATE,
}

ID_TO_CHANNEL_NAME: Dict[ChannelId, str] = {
    ChannelId.SPEED_MS: "speed_ms",
    ChannelId.LAT_G: "lat_g",
    ChannelId.LONG_G: "long_g",
    ChannelId.VERT_G: "vert_g",
    ChannelId.STEER_RAD: "steer_rad",
    ChannelId.SUSP_TRAVEL_FL: "susp_travel_fl",
    ChannelId.SUSP_TRAVEL_FR: "susp_travel_fr",
    ChannelId.SUSP_TRAVEL_RL: "susp_travel_rl",
    ChannelId.SUSP_TRAVEL_RR: "susp_travel_rr",
    ChannelId.BRAKE_PRESS_F: "brake_press_f",
    ChannelId.THROTTLE_POS: "throttle_pos",
    ChannelId.ENGINE_RPM: "engine_rpm",
    ChannelId.YAW_RATE: "yaw_rate",
}


class QualityCode(enum.IntEnum):
    """Telemetry sample quality status."""
    GOOD = 0
    DEGRADED = 1
    BAD = 2
    OUT_OF_RANGE = 3


class GripStatusCode(enum.IntEnum):
    """Digital Twin vehicle grip state."""
    UNKNOWN = 0
    OPTIMAL = 1
    UNDER_UTILISING = 2
    EXCEEDING_LIMIT = 3


GRIP_CODE_TO_STR = {
    GripStatusCode.UNKNOWN: "Calibrating",
    GripStatusCode.OPTIMAL: "Optimal",
    GripStatusCode.UNDER_UTILISING: "Under-utilising front grip",
    GripStatusCode.EXCEEDING_LIMIT: "Exceeding model limit — sliding / transient",
}

STR_TO_GRIP_CODE = {v: k for k, v in GRIP_CODE_TO_STR.items()}


@dataclass
class ChannelSample:
    channel_id: ChannelId
    value: float
    quality: QualityCode = QualityCode.GOOD


@dataclass
class DigitalTwinState:
    theoretical_max_lat_g: float = 0.0
    actual_lat_g: float = 0.0
    divergence_pct: float = 0.0
    grip_status: GripStatusCode = GripStatusCode.UNKNOWN


@dataclass
class SLTPFrame:
    """Canonical telemetry frame in the SuspensionLab Telemetry Protocol."""
    sequence_number: int
    timestamp: float
    org_id: str
    session_id: str
    samples: List[ChannelSample] = field(default_factory=list)
    twin: Optional[DigitalTwinState] = None

    def get_sample_value(self, channel: ChannelId | str, default: float = 0.0) -> float:
        if isinstance(channel, str):
            cid = CHANNEL_NAME_TO_ID.get(channel.lower(), ChannelId.UNKNOWN)
        else:
            cid = channel
        for s in self.samples:
            if s.channel_id == cid:
                return s.value
        return default

    def pack(self) -> bytes:
        """Serialise frame to compact SLTP v1 binary wire format."""
        org_bytes = self.org_id.encode("utf-8")[:64]
        sess_bytes = self.session_id.encode("utf-8")[:64]
        num_samples = len(self.samples)

        # Header: magic(4s), seq(I), ts(d), org_len(B), org_bytes(s), sess_len(B), sess_bytes(s), num_samples(H)
        buf = bytearray()
        buf.extend(MAGIC_HEADER)
        buf.extend(struct.pack(">Id", self.sequence_number, float(self.timestamp)))
        buf.append(len(org_bytes))
        buf.extend(org_bytes)
        buf.append(len(sess_bytes))
        buf.extend(sess_bytes)
        buf.extend(struct.pack(">H", num_samples))

        # Samples: channel_id(H), value(f), quality(B) -> 7 bytes per sample
        for s in self.samples:
            buf.extend(struct.pack(">HfB", int(s.channel_id), float(s.value), int(s.quality)))

        # Digital Twin block: has_twin(B)
        if self.twin is not None:
            buf.append(1)
            buf.extend(struct.pack(
                ">fffB",
                float(self.twin.theoretical_max_lat_g),
                float(self.twin.actual_lat_g),
                float(self.twin.divergence_pct),
                int(self.twin.grip_status)
            ))
        else:
            buf.append(0)

        return bytes(buf)

    @classmethod
    def unpack(cls, data: bytes) -> SLTPFrame:
        """Deserialise frame from SLTP v1 binary wire format."""
        if len(data) < 20:
            raise ValueError(f"SLTP frame too small ({len(data)} bytes, min 20)")

        if data[:4] != MAGIC_HEADER:
            raise ValueError(f"Invalid magic header: {data[:4]!r} != {MAGIC_HEADER!r}")

        offset = 4
        seq, ts = struct.unpack_from(">Id", data, offset)
        offset += 12

        org_len = data[offset]
        offset += 1
        if offset + org_len > len(data):
            raise ValueError("Corrupt frame: org_id length overflow")
        org_id = data[offset:offset + org_len].decode("utf-8", errors="replace")
        offset += org_len

        sess_len = data[offset]
        offset += 1
        if offset + sess_len > len(data):
            raise ValueError("Corrupt frame: session_id length overflow")
        session_id = data[offset:offset + sess_len].decode("utf-8", errors="replace")
        offset += sess_len

        num_samples, = struct.unpack_from(">H", data, offset)
        offset += 2

        samples: List[ChannelSample] = []
        for _ in range(num_samples):
            if offset + 7 > len(data):
                raise ValueError("Corrupt frame: sample buffer underrun")
            cid, val, q = struct.unpack_from(">HfB", data, offset)
            offset += 7
            try:
                ch_enum = ChannelId(cid)
            except ValueError:
                ch_enum = ChannelId.UNKNOWN
            try:
                q_enum = QualityCode(q)
            except ValueError:
                q_enum = QualityCode.BAD
            samples.append(ChannelSample(ch_enum, val, q_enum))

        twin: Optional[DigitalTwinState] = None
        if offset < len(data):
            has_twin = data[offset]
            offset += 1
            if has_twin == 1 and offset + 13 <= len(data):
                t_max, a_lat, div_pct, g_status = struct.unpack_from(">fffB", data, offset)
                offset += 13
                try:
                    g_enum = GripStatusCode(g_status)
                except ValueError:
                    g_enum = GripStatusCode.UNKNOWN
                twin = DigitalTwinState(
                    theoretical_max_lat_g=round(t_max, 4),
                    actual_lat_g=round(a_lat, 4),
                    divergence_pct=round(div_pct, 2),
                    grip_status=g_enum,
                )

        return cls(
            sequence_number=seq,
            timestamp=ts,
            org_id=org_id,
            session_id=session_id,
            samples=samples,
            twin=twin,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serialisable dictionary."""
        samples_dict = {}
        for s in self.samples:
            name = ID_TO_CHANNEL_NAME.get(s.channel_id, f"ch_{int(s.channel_id)}")
            samples_dict[name] = s.value

        twin_dict = None
        if self.twin is not None:
            twin_dict = {
                "theoretical_max_lat_g": self.twin.theoretical_max_lat_g,
                "actual_lat_g": self.twin.actual_lat_g,
                "divergence_pct": self.twin.divergence_pct,
                "grip_status": GRIP_CODE_TO_STR.get(self.twin.grip_status, "Unknown"),
            }

        return {
            "type": "telemetry_frame",
            "seq": self.sequence_number,
            "ts": round(self.timestamp, 4),
            "org_id": self.org_id,
            "session_id": self.session_id,
            "channels": samples_dict,
            # Convenience flattened fields for live HUD
            "speed_ms": self.get_sample_value(ChannelId.SPEED_MS),
            "lat_g": self.get_sample_value(ChannelId.LAT_G),
            "long_g": self.get_sample_value(ChannelId.LONG_G),
            "steer_rad": self.get_sample_value(ChannelId.STEER_RAD),
            "susp_travel_fl": self.get_sample_value(ChannelId.SUSP_TRAVEL_FL),
            "susp_travel_fr": self.get_sample_value(ChannelId.SUSP_TRAVEL_FR),
            "susp_travel_rl": self.get_sample_value(ChannelId.SUSP_TRAVEL_RL),
            "susp_travel_rr": self.get_sample_value(ChannelId.SUSP_TRAVEL_RR),
            "twin": twin_dict,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
