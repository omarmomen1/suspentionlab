"""
physics/setup_score.py
======================
SuspensionLab PRO — Setup Score (Tier A1).

A single 0–100 composite number describing how good a quarter-car setup is,
computed from the three metrics every damper engineer already balances:

    comfort  — lower sprung-mass RMS acceleration is better
    grip     — lower RMS tire-load variation is better
    control  — suspension travel used closer to (but not over) the working
               window is better; bottoming out is punished

Each component maps its metric through a smooth saturating curve calibrated
against typical passenger/track-car ranges, then the weighted sum is clamped.
The same function runs server-side (fleet percentile) and can run client-side
for previews — one implementation, no drift.

References
----------
- Milliken & Milliken, "Race Car Vehicle Dynamics", Ch. 16 (ride vs grip).
- ISO 2631-1 comfort weighting (simplified to RMS body accel here).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScoreComponents:
    comfort: float
    grip: float
    control: float


@dataclass
class SetupScore:
    score: float                      # 0–100 composite
    band: str                         # Poor | Fair | Good | Excellent
    components: ScoreComponents
    inputs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "band": self.band,
            "components": {
                "comfort": round(self.components.comfort, 1),
                "grip": round(self.components.grip, 1),
                "control": round(self.components.control, 1),
            },
            "inputs": self.inputs,
        }


def _saturating(value: float, bad_at: float, good_at: float) -> float:
    """
    Linear ramp from 0 (at `bad_at`) to 100 (at `good_at`), clamped.
    Works in both directions: pass (bad=5, good=0.5) when lower is better.
    """
    if bad_at == good_at:
        return 0.0
    t = (value - bad_at) / (good_at - bad_at)
    return max(0.0, min(1.0, t)) * 100.0


# Component weights — grip dominates because tire load variation is the
# single best proxy for lap-time potential in ride analysis.
_W_COMFORT, _W_GRIP, _W_CONTROL = 0.30, 0.45, 0.25


def compute_setup_score(
    rms_body_accel_ms2: float,
    rms_tire_load_var_n: float,
    peak_susp_travel_mm: float,
    static_load_per_corner_n: float = 3500.0,
    travel_window_mm: float = 60.0,
) -> SetupScore:
    """
    Compute the composite Setup Score.

    Parameters
    ----------
    rms_body_accel_ms2 :   Sprung-mass RMS acceleration [m/s²]. 0.5 is plush,
                           4+ is harsh.
    rms_tire_load_var_n :  RMS dynamic tire load [N]. ~10% of static load is
                           typical; >40% means the tire is leaving the road.
    peak_susp_travel_mm :  Peak suspension travel [mm]. Sweet spot is using
                           most of the window without hitting the bump stop.
    static_load_per_corner_n : Static vertical load per corner [N] — normalises
                           tire-load variation across vehicle weights.
    travel_window_mm :     Working travel window [mm] before bump stop engagement.
    """
    if rms_body_accel_ms2 < 0 or rms_tire_load_var_n < 0 or peak_susp_travel_mm < 0:
        raise ValueError("Metrics must be non-negative.")
    if static_load_per_corner_n <= 0 or travel_window_mm <= 0:
        raise ValueError("static_load_per_corner_n and travel_window_mm must be positive.")

    # Comfort: 0.5 m/s² → 100 pts, 5 m/s² → 0 pts
    comfort = _saturating(rms_body_accel_ms2, 5.0, 0.5)

    # Grip: tire-load variation as a fraction of static load.
    # 8% → 100 pts, 45% → 0 pts.
    load_ratio_pct = (rms_tire_load_var_n / static_load_per_corner_n) * 100.0
    grip = _saturating(load_ratio_pct, 45.0, 8.0)

    # Control: reward using the travel window, punish exceeding it.
    usage = peak_susp_travel_mm / travel_window_mm
    if usage <= 1.0:
        # 0% usage → 40 pts (passive/over-damped), ~85% usage → 100 pts
        control = 40.0 + 60.0 * min(usage / 0.85, 1.0)
    else:
        # Bottoming out: decay hard — 120% of window → ~20 pts
        control = max(0.0, 100.0 - (usage - 1.0) * 400.0)

    score = (_W_COMFORT * comfort) + (_W_GRIP * grip) + (_W_CONTROL * control)
    score = max(0.0, min(100.0, score))

    if score >= 80:
        band = "Excellent"
    elif score >= 60:
        band = "Good"
    elif score >= 35:
        band = "Fair"
    else:
        band = "Poor"

    return SetupScore(
        score=score,
        band=band,
        components=ScoreComponents(comfort=comfort, grip=grip, control=control),
        inputs={
            "rms_body_accel_ms2": rms_body_accel_ms2,
            "rms_tire_load_var_n": rms_tire_load_var_n,
            "peak_susp_travel_mm": peak_susp_travel_mm,
            "static_load_per_corner_n": static_load_per_corner_n,
            "travel_window_mm": travel_window_mm,
        },
    )
