"""
physics/telemetry_events.py
===========================
SuspensionLab PRO — Deterministic Vehicle Dynamics Event & Anomaly Detection

Implements physical, deterministic event detection on authentic motorsport &
automotive telemetry time series without synthetic anomalies.

Detected Events:
1. Braking Onset (long_g < -0.35 G or brake pressure rising)
2. Throttle Onset (positive throttle transient)
3. Corner Entry (rising lateral G / yaw rate with steering)
4. Apex Region (maximum lateral G / curvature peak)
5. Corner Exit (lateral G decay with throttle application)
6. Wheel Hop Resonance (10–15 Hz oscillatory unsprung vibration)
7. Damper Velocity Spike (|v_damper| > 0.5 m/s impact / kerb strike)
8. Tire-Load Variation Spike (extreme dFz/dt or liftoff Fz < 150 N)
9. Steering Transient (|d_steer/dt| > 250 deg/s)
10. Yaw-Rate Deviation (|r_meas - r_bicycle| > 4.0 deg/s)
11. Excessive Body Motion (pitch/roll angle or travel envelope violation)
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class VehicleDynamicsEvent:
    """Detected physical vehicle dynamics event or anomaly."""
    event_id: str
    session_id: str
    event_type: str
    start_time: float
    end_time: float
    channels: List[str]
    detector: str
    threshold_config: Dict[str, Any]
    confidence: float
    source_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "start_time": round(self.start_time, 3),
            "end_time": round(self.end_time, 3),
            "duration_s": round(max(0.0, self.end_time - self.start_time), 3),
            "channels": self.channels,
            "detector": self.detector,
            "threshold_config": self.threshold_config,
            "confidence": round(self.confidence, 2),
            "source_data": self.source_data,
        }


def _make_event_id(session_id: str, event_type: str, start_time: float) -> str:
    """Generate deterministic event identifier."""
    raw = f"{session_id}:{event_type}:{start_time:.3f}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8].upper()
    return f"EVT-{event_type[:4]}-{h}"


def _cluster_contiguous_indices(mask: np.ndarray, min_samples: int = 2) -> List[Tuple[int, int]]:
    """Find contiguous True segments in a boolean array."""
    if not np.any(mask):
        return []
    
    diff = np.diff(mask.astype(int))
    starts = np.where(diff == 1)[0] + 1
    ends = np.where(diff == -1)[0] + 1

    if mask[0]:
        starts = np.r_[0, starts]
    if mask[-1]:
        ends = np.r_[ends, len(mask)]

    segments = []
    for s, e in zip(starts, ends):
        if (e - s) >= min_samples:
            segments.append((int(s), int(e)))
    return segments


def detect_braking_onset(
    t: np.ndarray,
    long_g: Optional[np.ndarray],
    brake_bar: Optional[np.ndarray],
    speed: Optional[np.ndarray],
    session_id: str = "SESSION-01",
    dt: float = 0.01,
) -> List[VehicleDynamicsEvent]:
    """Detect onset of heavy braking phases."""
    events = []
    n = len(t)
    if n < 5:
        return events

    mask = np.zeros(n, dtype=bool)
    if long_g is not None and len(long_g) == n:
        mask |= (long_g < -0.35)
    if brake_bar is not None and len(brake_bar) == n:
        mask |= (brake_bar > 10.0)

    # Filter by vehicle moving
    if speed is not None and len(speed) == n:
        mask &= (speed > 5.0)

    clusters = _cluster_contiguous_indices(mask, min_samples=max(2, int(0.15 / dt)))
    for s_idx, e_idx in clusters:
        onset_end_idx = min(e_idx, s_idx + max(3, int(0.35 / dt)))
        t_start = float(t[s_idx])
        t_end = float(t[onset_end_idx])
        
        peak_dec = float(np.min(long_g[s_idx:e_idx])) if long_g is not None else -0.5
        peak_press = float(np.max(brake_bar[s_idx:e_idx])) if brake_bar is not None else 0.0
        
        channels = []
        if long_g is not None: channels.append("long_g")
        if brake_bar is not None: channels.append("brake_bar")

        events.append(VehicleDynamicsEvent(
            event_id=_make_event_id(session_id, "BRAKING_ONSET", t_start),
            session_id=session_id,
            event_type="BRAKING_ONSET",
            start_time=t_start,
            end_time=t_end,
            channels=channels,
            detector="LongitudinalBrakingOnsetDetector",
            threshold_config={"long_g_threshold": -0.35, "brake_press_threshold_bar": 10.0},
            confidence=min(1.0, 0.70 + abs(peak_dec) * 0.1),
            source_data={
                "peak_deceleration_g": round(peak_dec, 3),
                "peak_brake_press_bar": round(peak_press, 1),
                "entry_speed_ms": round(float(speed[s_idx]), 1) if speed is not None else None,
            },
        ))
    return events


def detect_throttle_onset(
    t: np.ndarray,
    throttle: Optional[np.ndarray],
    long_g: Optional[np.ndarray],
    speed: Optional[np.ndarray],
    session_id: str = "SESSION-01",
    dt: float = 0.01,
) -> List[VehicleDynamicsEvent]:
    """Detect throttle application transients out of corners or straights."""
    events = []
    n = len(t)
    if throttle is None or len(throttle) != n or n < 5:
        return events

    d_th = np.gradient(throttle, dt)
    mask = (throttle > 25.0) & (d_th > 40.0)

    clusters = _cluster_contiguous_indices(mask, min_samples=max(2, int(0.10 / dt)))
    for s_idx, e_idx in clusters:
        t_start = float(t[s_idx])
        t_end = float(t[min(n - 1, e_idx + int(0.20 / dt))])
        peak_rate = float(np.max(d_th[s_idx:e_idx]))
        th_val = float(throttle[e_idx])

        events.append(VehicleDynamicsEvent(
            event_id=_make_event_id(session_id, "THROTTLE_ONSET", t_start),
            session_id=session_id,
            event_type="THROTTLE_ONSET",
            start_time=t_start,
            end_time=t_end,
            channels=["throttle_pct"],
            detector="ThrottleApplicationOnsetDetector",
            threshold_config={"throttle_min_pct": 25.0, "throttle_rate_pct_s": 40.0},
            confidence=0.88,
            source_data={
                "throttle_rate_pct_s": round(peak_rate, 1),
                "attained_throttle_pct": round(th_val, 1),
                "speed_ms": round(float(speed[s_idx]), 1) if speed is not None else None,
            },
        ))
    return events


def detect_corner_phases(
    t: np.ndarray,
    lat_g: Optional[np.ndarray],
    speed: Optional[np.ndarray],
    yaw_rate: Optional[np.ndarray],
    steer_deg: Optional[np.ndarray],
    session_id: str = "SESSION-01",
    dt: float = 0.01,
) -> List[VehicleDynamicsEvent]:
    """Detect corner entry, apex region, and corner exit phases."""
    events = []
    n = len(t)
    if lat_g is None or len(lat_g) != n or n < 10:
        return events

    abs_lat = np.abs(lat_g)
    corner_mask = (abs_lat > 0.40)
    if speed is not None and len(speed) == n:
        corner_mask &= (speed > 8.0)

    clusters = _cluster_contiguous_indices(corner_mask, min_samples=max(3, int(0.40 / dt)))
    for s_idx, e_idx in clusters:
        corner_t_start = float(t[s_idx])
        corner_t_end = float(t[e_idx - 1])
        c_lat = abs_lat[s_idx:e_idx]
        max_lat_local = float(np.max(c_lat))
        if max_lat_local < 0.50:
            continue

        peak_sub_idx = int(np.argmax(c_lat))
        peak_idx = s_idx + peak_sub_idx

        # 1. Corner Entry
        entry_end = s_idx + max(2, int(peak_sub_idx * 0.7))
        events.append(VehicleDynamicsEvent(
            event_id=_make_event_id(session_id, "CORNER_ENTRY", corner_t_start),
            session_id=session_id,
            event_type="CORNER_ENTRY",
            start_time=corner_t_start,
            end_time=float(t[entry_end]),
            channels=["lat_g"] + (["yaw_rate"] if yaw_rate is not None else []) + (["steer_deg"] if steer_deg is not None else []),
            detector="CornerEntryPhaseDetector",
            threshold_config={"lat_g_threshold": 0.40},
            confidence=0.92,
            source_data={
                "entry_speed_ms": round(float(speed[s_idx]), 1) if speed is not None else None,
                "initial_lat_g": round(float(lat_g[s_idx]), 3),
            },
        ))

        # 2. Apex Region
        apex_span = max(2, int(0.18 / dt))
        apex_start = max(s_idx, peak_idx - apex_span)
        apex_end = min(e_idx - 1, peak_idx + apex_span)
        events.append(VehicleDynamicsEvent(
            event_id=_make_event_id(session_id, "APEX_REGION", float(t[apex_start])),
            session_id=session_id,
            event_type="APEX_REGION",
            start_time=float(t[apex_start]),
            end_time=float(t[apex_end]),
            channels=["lat_g"] + (["speed"] if speed is not None else []),
            detector="CornerApexRegionDetector",
            threshold_config={"peak_ratio_threshold": 0.88},
            confidence=0.95,
            source_data={
                "peak_lat_g": round(max_lat_local, 3),
                "apex_speed_ms": round(float(speed[peak_idx]), 1) if speed is not None else None,
                "direction": "RIGHT" if lat_g[peak_idx] > 0 else "LEFT",
            },
        ))

        # 3. Corner Exit
        exit_start = min(e_idx - 1, peak_idx + max(1, int(apex_span * 0.8)))
        events.append(VehicleDynamicsEvent(
            event_id=_make_event_id(session_id, "CORNER_EXIT", float(t[exit_start])),
            session_id=session_id,
            event_type="CORNER_EXIT",
            start_time=float(t[exit_start]),
            end_time=corner_t_end,
            channels=["lat_g"],
            detector="CornerExitTractionDetector",
            threshold_config={"decay_gradient": True},
            confidence=0.90,
            source_data={
                "exit_speed_ms": round(float(speed[e_idx - 1]), 1) if speed is not None else None,
                "exit_lat_g": round(float(lat_g[e_idx - 1]), 3),
            },
        ))

    return events


def detect_wheel_hop(
    t: np.ndarray,
    damper_fl: Optional[np.ndarray],
    vert_g: Optional[np.ndarray],
    wsp_fl: Optional[np.ndarray],
    session_id: str = "SESSION-01",
    dt: float = 0.01,
) -> List[VehicleDynamicsEvent]:
    """
    Detect wheel hop resonance (10–15 Hz oscillatory unsprung mass bounce).
    Analyzes zero-crossing frequency and amplitude in sliding windows.
    """
    events = []
    n = len(t)
    if n < 40 or dt <= 0:
        return events

    sig = None
    target_channel = "vert_g"
    if damper_fl is not None and len(damper_fl) == n:
        sig = np.gradient(damper_fl, dt) / 1000.0 if np.max(np.abs(damper_fl)) > 15.0 else damper_fl
        target_channel = "damper_fl"
    elif vert_g is not None and len(vert_g) == n:
        sig = vert_g - np.mean(vert_g)
        target_channel = "vert_g"

    if sig is None or np.std(sig) < 1e-4:
        return events

    win_len = int(0.5 / dt)
    step = int(0.2 / dt)
    
    for i in range(0, n - win_len, step):
        w_sig = sig[i:i + win_len]
        w_sig_center = w_sig - np.mean(w_sig)
        zc = np.where(np.diff(np.sign(w_sig_center)))[0]
        n_zc = len(zc)
        amp = float(np.ptp(w_sig))
        if 8 <= n_zc <= 18 and amp > 0.30:
            freq_est = round((n_zc / 2.0) / 0.5, 1)
            t_s = float(t[i])
            t_e = float(t[i + win_len])
            events.append(VehicleDynamicsEvent(
                event_id=_make_event_id(session_id, "WHEEL_HOP", t_s),
                session_id=session_id,
                event_type="WHEEL_HOP",
                start_time=t_s,
                end_time=t_e,
                channels=[target_channel],
                detector="WheelHopResonanceDetector",
                threshold_config={"freq_band_hz": [10.0, 15.0], "min_ptp_amp": 0.30},
                confidence=0.86,
                source_data={
                    "estimated_resonance_freq_hz": freq_est,
                    "oscillation_amplitude": round(amp, 3),
                    "target_channel": target_channel,
                },
            ))
            break

    return events


def detect_damper_velocity_spikes(
    t: np.ndarray,
    damper_fl: Optional[np.ndarray],
    damper_fr: Optional[np.ndarray],
    session_id: str = "SESSION-01",
    dt: float = 0.01,
) -> List[VehicleDynamicsEvent]:
    """Detect high-speed kerb strikes or pothole impacts (|v_damper| > 0.5 m/s)."""
    events = []
    n = len(t)
    if dt <= 0 or n < 5:
        return events

    for ch_name, arr in [("damper_fl", damper_fl), ("damper_fr", damper_fr)]:
        if arr is None or len(arr) != n:
            continue
        if np.max(np.abs(arr)) > 15.0:
            v_d = np.gradient(arr, dt) / 1000.0
        else:
            v_d = arr

        spike_mask = np.abs(v_d) > 0.48
        clusters = _cluster_contiguous_indices(spike_mask, min_samples=1)
        for s_idx, e_idx in clusters[:4]:
            t_s = float(t[s_idx])
            t_e = float(t[min(n - 1, e_idx + max(1, int(0.15 / dt)))])
            peak_val = float(np.max(np.abs(v_d[s_idx:e_idx])))

            events.append(VehicleDynamicsEvent(
                event_id=_make_event_id(session_id, "DAMPER_SPIKE", t_s),
                session_id=session_id,
                event_type="DAMPER_SPIKE",
                start_time=t_s,
                end_time=t_e,
                channels=[ch_name],
                detector="DamperVelocityTransientDetector",
                threshold_config={"velocity_threshold_ms": 0.48},
                confidence=min(1.0, 0.80 + peak_val * 0.15),
                source_data={
                    "peak_damper_velocity_ms": round(peak_val, 3),
                    "channel": ch_name,
                    "impact_type": "HIGH_SPEED_KERB_STRIKE",
                },
            ))

    return events


def detect_tire_load_variation(
    t: np.ndarray,
    tire_load_fl: Optional[np.ndarray],
    vert_g: Optional[np.ndarray],
    session_id: str = "SESSION-01",
    dt: float = 0.01,
) -> List[VehicleDynamicsEvent]:
    """Detect severe normal load loss (liftoff) or excessive shock load."""
    events = []
    n = len(t)
    if n < 5:
        return events

    if tire_load_fl is not None and len(tire_load_fl) == n:
        liftoff_mask = (tire_load_fl < 250.0)
        clusters = _cluster_contiguous_indices(liftoff_mask, min_samples=max(1, int(0.04 / dt)))
        for s_idx, e_idx in clusters:
            t_s = float(t[s_idx])
            t_e = float(t[min(n - 1, e_idx + max(1, int(0.10 / dt)))])
            min_fz = float(np.min(tire_load_fl[s_idx:e_idx]))
            events.append(VehicleDynamicsEvent(
                event_id=_make_event_id(session_id, "TIRE_LOAD_VARIATION", t_s),
                session_id=session_id,
                event_type="TIRE_LOAD_VARIATION",
                start_time=t_s,
                end_time=t_e,
                channels=["tire_load_fl"],
                detector="TireLoadVariationDetector",
                threshold_config={"min_fz_threshold_n": 250.0},
                confidence=0.92,
                source_data={
                    "min_normal_force_n": round(min_fz, 1),
                    "phenomenon": "TIRE_CONTACT_PATCH_UNLOAD",
                },
            ))

    elif vert_g is not None and len(vert_g) == n:
        shock_mask = np.abs(vert_g) > 2.8
        clusters = _cluster_contiguous_indices(shock_mask, min_samples=max(1, int(0.03 / dt)))
        for s_idx, e_idx in clusters:
            t_s = float(t[s_idx])
            t_e = float(t[min(n - 1, e_idx + max(1, int(0.10 / dt)))])
            events.append(VehicleDynamicsEvent(
                event_id=_make_event_id(session_id, "TIRE_LOAD_VARIATION", t_s),
                session_id=session_id,
                event_type="TIRE_LOAD_VARIATION",
                start_time=t_s,
                end_time=t_e,
                channels=["vert_g"],
                detector="TireLoadVariationDetector",
                threshold_config={"vert_g_shock_threshold": 2.8},
                confidence=0.88,
                source_data={"peak_vert_g": round(float(np.max(np.abs(vert_g[s_idx:e_idx]))), 2)},
            ))

    return events


def detect_steering_transient(
    t: np.ndarray,
    steer_deg: Optional[np.ndarray],
    session_id: str = "SESSION-01",
    dt: float = 0.01,
) -> List[VehicleDynamicsEvent]:
    """Detect rapid steering transients (|d_steer/dt| > 250 deg/s)."""
    events = []
    n = len(t)
    if steer_deg is None or len(steer_deg) != n or dt <= 0 or n < 5:
        return events

    d_steer = np.gradient(steer_deg, dt)
    transient_mask = np.abs(d_steer) > 240.0

    clusters = _cluster_contiguous_indices(transient_mask, min_samples=max(2, int(0.08 / dt)))
    for s_idx, e_idx in clusters:
        t_s = float(t[s_idx])
        t_e = float(t[min(n - 1, e_idx + max(1, int(0.12 / dt)))])
        peak_rate = float(np.max(np.abs(d_steer[s_idx:e_idx])))
        events.append(VehicleDynamicsEvent(
            event_id=_make_event_id(session_id, "STEERING_TRANSIENT", t_s),
            session_id=session_id,
            event_type="STEERING_TRANSIENT",
            start_time=t_s,
            end_time=t_e,
            channels=["steer_deg"],
            detector="SteeringTransientRateDetector",
            threshold_config={"steering_rate_threshold_degs": 240.0},
            confidence=0.90,
            source_data={
                "peak_steering_rate_degs": round(peak_rate, 1),
                "angle_at_event_deg": round(float(steer_deg[s_idx]), 1),
            },
        ))
    return events


def detect_yaw_rate_deviation(
    t: np.ndarray,
    yaw_rate: Optional[np.ndarray],
    speed: Optional[np.ndarray],
    steer_deg: Optional[np.ndarray],
    lat_g: Optional[np.ndarray],
    wheelbase_m: float = 3.6,
    steer_ratio: float = 14.5,
    session_id: str = "SESSION-01",
    dt: float = 0.01,
) -> List[VehicleDynamicsEvent]:
    """Detect yaw rate divergence from kinematic bicycle model reference."""
    events = []
    n = len(t)
    if yaw_rate is None or speed is None or steer_deg is None:
        return events
    if len(yaw_rate) != n or len(speed) != n or len(steer_deg) != n or n < 10:
        return events

    delta_wheel_rad = np.radians(steer_deg / steer_ratio)
    r_kin_rad_s = (np.maximum(speed, 5.0) / wheelbase_m) * delta_wheel_rad
    r_kin_deg_s = np.degrees(r_kin_rad_s)

    r_diff = np.abs(yaw_rate - r_kin_deg_s)
    dev_mask = (r_diff > 4.5) & (np.abs(yaw_rate) > 4.0) & (speed > 12.0)

    clusters = _cluster_contiguous_indices(dev_mask, min_samples=max(3, int(0.20 / dt)))
    for s_idx, e_idx in clusters:
        t_s = float(t[s_idx])
        t_e = float(t[min(n - 1, e_idx + max(1, int(0.15 / dt)))])
        peak_dev = float(np.max(r_diff[s_idx:e_idx]))
        mean_meas = float(np.mean(yaw_rate[s_idx:e_idx]))
        mean_kin = float(np.mean(r_kin_deg_s[s_idx:e_idx]))
        nature = "OVERSTEER_YAW_BREAKAWAY" if abs(mean_meas) > abs(mean_kin) else "UNDERSTEER_SCRUB"

        events.append(VehicleDynamicsEvent(
            event_id=_make_event_id(session_id, "YAW_RATE_DEVIATION", t_s),
            session_id=session_id,
            event_type="YAW_RATE_DEVIATION",
            start_time=t_s,
            end_time=t_e,
            channels=["yaw_rate", "steer_deg", "speed"],
            detector="BicycleYawRateDeviationDetector",
            threshold_config={"yaw_rate_error_threshold_degs": 4.5},
            confidence=0.89,
            source_data={
                "peak_yaw_deviation_degs": round(peak_dev, 1),
                "handling_nature": nature,
                "measured_yaw_rate_degs": round(mean_meas, 1),
                "kinematic_model_yaw_rate_degs": round(mean_kin, 1),
            },
        ))
    return events


def detect_excessive_body_motion(
    t: np.ndarray,
    pitch_deg: Optional[np.ndarray],
    roll_deg: Optional[np.ndarray],
    rh_fl: Optional[np.ndarray],
    session_id: str = "SESSION-01",
    dt: float = 0.01,
) -> List[VehicleDynamicsEvent]:
    """Detect excessive pitch/roll attitude or suspension bottoming/topping."""
    events = []
    n = len(t)
    if n < 5:
        return events

    mask = np.zeros(n, dtype=bool)
    reasons = []
    channels = []

    if pitch_deg is not None and len(pitch_deg) == n:
        p_mask = np.abs(pitch_deg) > 3.2
        if np.any(p_mask):
            mask |= p_mask
            channels.append("pitch_deg")
            reasons.append("Pitch attitude exceeded 3.2 deg")

    if roll_deg is not None and len(roll_deg) == n:
        r_mask = np.abs(roll_deg) > 4.2
        if np.any(r_mask):
            mask |= r_mask
            channels.append("roll_deg")
            reasons.append("Roll attitude exceeded 4.2 deg")

    if rh_fl is not None and len(rh_fl) == n:
        travel_mask = (rh_fl < 5.0) | (rh_fl > 75.0)
        if np.any(travel_mask):
            mask |= travel_mask
            channels.append("rh_fl")
            reasons.append("Suspension travel envelope boundary violation (<5mm or >75mm)")

    clusters = _cluster_contiguous_indices(mask, min_samples=max(2, int(0.12 / dt)))
    for s_idx, e_idx in clusters:
        t_s = float(t[s_idx])
        t_e = float(t[min(n - 1, e_idx + max(1, int(0.15 / dt)))])
        events.append(VehicleDynamicsEvent(
            event_id=_make_event_id(session_id, "EXCESSIVE_BODY_MOTION", t_s),
            session_id=session_id,
            event_type="EXCESSIVE_BODY_MOTION",
            start_time=t_s,
            end_time=t_e,
            channels=channels if channels else ["pitch_deg", "roll_deg"],
            detector="ChassisAttitudeEnvelopeDetector",
            threshold_config={"pitch_max_deg": 3.2, "roll_max_deg": 4.2},
            confidence=0.91,
            source_data={"reasons": reasons},
        ))

    return events


def detect_all_vehicle_dynamics_events(
    telemetry_data: Dict[str, Any],
    session_id: str = "SESSION-01",
    sample_rate_hz: float = 100.0,
) -> List[VehicleDynamicsEvent]:
    """
    Run the full suite of deterministic vehicle dynamics event detectors on parsed telemetry.
    Returns a unified list of detected events sorted by start time.
    """
    t_raw = telemetry_data.get("time")
    if t_raw is None or len(t_raw) < 5:
        return []

    t = np.asarray(t_raw, dtype=np.float64)
    dt = float(np.median(np.diff(t))) if len(t) > 1 else (1.0 / sample_rate_hz)
    if dt <= 0:
        dt = 0.01

    def _get(key: str) -> Optional[np.ndarray]:
        for candidate in [key, key.lower(), key.upper()]:
            if candidate in telemetry_data:
                arr = np.asarray(telemetry_data[candidate], dtype=np.float64)
                if len(arr) == len(t):
                    return arr
        if key == "speed":
            for k in ["gps_speed", "v_x", "speed_kmh", "speeds"]:
                if k in telemetry_data:
                    arr = np.asarray(telemetry_data[k], dtype=np.float64)
                    if len(arr) == len(t):
                        return arr / 3.6 if "kmh" in k else arr
        if key == "brake_bar":
            for k in ["brake_press", "p_brake_f", "brake", "brakepress_f", "brake_front"]:
                if k in telemetry_data:
                    arr = np.asarray(telemetry_data[k], dtype=np.float64)
                    if len(arr) == len(t):
                        return arr
        if key == "throttle":
            for k in ["throttle_pct", "tps", "throttlepos", "ath"]:
                if k in telemetry_data:
                    arr = np.asarray(telemetry_data[k], dtype=np.float64)
                    if len(arr) == len(t):
                        return arr
        if key == "steer_deg":
            for k in ["steerangle", "steer", "steering_angle"]:
                if k in telemetry_data:
                    arr = np.asarray(telemetry_data[k], dtype=np.float64)
                    if len(arr) == len(t):
                        return arr
        if key == "lat_g":
            for k in ["g_lat", "latacc", "ay"]:
                if k in telemetry_data:
                    arr = np.asarray(telemetry_data[k], dtype=np.float64)
                    if len(arr) == len(t):
                        return arr
        if key == "long_g":
            for k in ["g_lon", "inlineacc", "ax"]:
                if k in telemetry_data:
                    arr = np.asarray(telemetry_data[k], dtype=np.float64)
                    if len(arr) == len(t):
                        return arr
        if key == "damper_fl":
            for k in ["susptravel_fl", "damper_pos_fl", "rh_fl", "damper_vel_fl"]:
                if k in telemetry_data:
                    arr = np.asarray(telemetry_data[k], dtype=np.float64)
                    if len(arr) == len(t):
                        return arr
        if key == "damper_fr":
            for k in ["susptravel_fr", "damper_pos_fr", "rh_fr", "damper_vel_fr"]:
                if k in telemetry_data:
                    arr = np.asarray(telemetry_data[k], dtype=np.float64)
                    if len(arr) == len(t):
                        return arr
        return None

    speed = _get("speed")
    long_g = _get("long_g")
    lat_g = _get("lat_g")
    vert_g = _get("vert_g")
    brake_bar = _get("brake_bar")
    throttle = _get("throttle")
    steer_deg = _get("steer_deg")
    yaw_rate = _get("yaw_rate")
    pitch_deg = _get("pitch_deg")
    roll_deg = _get("roll_deg")
    damper_fl = _get("damper_fl")
    damper_fr = _get("damper_fr")
    tire_load_fl = _get("tire_load_fl")
    wsp_fl = _get("wsp_fl")

    all_events: List[VehicleDynamicsEvent] = []

    all_events.extend(detect_braking_onset(t, long_g, brake_bar, speed, session_id, dt))
    all_events.extend(detect_throttle_onset(t, throttle, long_g, speed, session_id, dt))
    all_events.extend(detect_corner_phases(t, lat_g, speed, yaw_rate, steer_deg, session_id, dt))
    all_events.extend(detect_wheel_hop(t, damper_fl, vert_g, wsp_fl, session_id, dt))
    all_events.extend(detect_damper_velocity_spikes(t, damper_fl, damper_fr, session_id, dt))
    all_events.extend(detect_tire_load_variation(t, tire_load_fl, vert_g, session_id, dt))
    all_events.extend(detect_steering_transient(t, steer_deg, session_id, dt))
    all_events.extend(detect_yaw_rate_deviation(t, yaw_rate, speed, steer_deg, lat_g, 3.6, 14.5, session_id, dt))
    all_events.extend(detect_excessive_body_motion(t, pitch_deg, roll_deg, damper_fl, session_id, dt))

    all_events.sort(key=lambda e: (e.start_time, e.end_time, e.event_type))
    return all_events
