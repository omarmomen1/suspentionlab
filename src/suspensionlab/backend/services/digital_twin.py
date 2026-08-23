"""
backend/services/digital_twin.py
=================================
Digital Setup Twin service (Issues 40 & 41).

    REAL CAR → TELEMETRY → PARAMETER IDENTIFICATION → DIGITAL TWIN
                                ↓
              Diagnose / Simulate / Optimize → SETUP RECOMMENDATION

Parameter identification (sprung ride mode):
    1. Welch PSD of the measured vertical acceleration channel
    2. Dominant peak in the 0.5–5 Hz ride band → measured sprung frequency f_s
    3. Half-power bandwidth around that peak → measured damping ratio ζ
    4. Analytical inversion with known mass/motion-ratio:
           k_w = m_s · (2πf_s)²          k_s = k_w / MR²
           c_w = 2ζ √(k_w m_s)           c   = c_w / MR
    5. Confidence from peak prominence, sample count and sample rate.

Learning store (#41): every calibration appends a CalibrationObservation
(param deltas → measured responses, conditioned on operating state).
get_learnings() aggregates them into vehicle-specific sensitivity statements
that no competitor can copy — they only exist because THIS car was run on
THIS platform.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional

import numpy as np
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin, CalibrationObservation
from suspensionlab.backend.security.audit import canonical_hash

logger = logging.getLogger(__name__)

RIDE_BAND_HZ = (0.5, 5.0)
MIN_SAMPLES = 200


# ─────────────────────────────────────────────────────────────────────────────
# Parameter identification
# ─────────────────────────────────────────────────────────────────────────────

def identify_from_vertical_accel(
    time_s: list[float],
    vert_g: list[float],
    base_params: dict[str, float],
) -> dict[str, Any]:
    """
    Identify sprung-mode frequency & damping from a vertical-acceleration
    telemetry channel, then analytically invert to spring/damper parameters.

    Returns an identification report:
        {f_n_hz, zeta, identified_params{...}, deltas{...}, confidence,
         n_samples, sample_rate_hz, method}
    """
    t = np.asarray(time_s, dtype=float)
    a = np.asarray(vert_g, dtype=float) * 9.81  # g → m/s²
    n = min(len(t), len(a))
    t, a = t[:n], a[:n]

    # Drop non-finite samples (parsers may emit NaNs at resampling edges) —
    # a single NaN poisons the entire PSD.
    finite = np.isfinite(t) & np.isfinite(a)
    t, a = t[finite], a[finite]
    n = len(t)

    if n < MIN_SAMPLES:
        raise ValueError(f"Need ≥ {MIN_SAMPLES} samples of vertical acceleration; got {n}.")

    # Uniform sampling check / estimate
    dt = np.diff(t)
    dt_med = float(np.median(dt))
    if dt_med <= 0:
        raise ValueError("Timestamps must be strictly increasing.")
    fs = 1.0 / dt_med
    if fs < 2 * RIDE_BAND_HZ[1]:
        raise ValueError(f"Sample rate {fs:.1f} Hz too low for ride-band identification "
                         f"(need > {2 * RIDE_BAND_HZ[1]:.0f} Hz).")

    # Detrend and window
    a = a - np.mean(a)

    # ── Welch PSD ──────────────────────────────────────────────────────────
    # nperseg=1024 balances resolution (df≈0.1 Hz, enough bins across the
    # ~0.9 Hz half-power bandwidth) with segment averaging (variance reduction).
    from scipy.signal import welch
    seg = min(1024, n)
    freqs, psd = welch(a, fs=fs, nperseg=seg)

    # Ride band mask
    band = (freqs >= RIDE_BAND_HZ[0]) & (freqs <= RIDE_BAND_HZ[1])
    if not np.any(band):
        raise ValueError("No spectral content in the ride band (0.5–5 Hz).")

    bf, bp = freqs[band], psd[band]

    # Smooth the PSD with a ~0.3 Hz moving average before peak-picking:
    # a ζ≈0.3 ride resonance is only ~1.75× the noise floor, and raw
    # periodogram bins are exponentially distributed — unsmoothed argmax
    # locks onto noise spikes. The physical resonance bump (~1 Hz wide)
    # survives smoothing intact.
    df_bin = float(bf[1] - bf[0]) if len(bf) > 1 else 1.0
    smooth_bins = max(1, int(round(0.30 / df_bin)))
    kernel = np.ones(smooth_bins) / smooth_bins
    bp_s = np.convolve(bp, kernel, mode="same")

    peak_idx = int(np.argmax(bp_s))
    f_peak = float(bf[peak_idx])

    # Parabolic interpolation around the peak → sub-bin frequency accuracy
    # (one bin at df≈0.1 Hz is ~6% of a 1.5 Hz ride frequency).
    if 0 < peak_idx < len(bp_s) - 1:
        y0, y1, y2 = bp_s[peak_idx - 1], bp_s[peak_idx], bp_s[peak_idx + 1]
        denom = y0 - 2 * y1 + y2
        if abs(denom) > 1e-30:
            delta = 0.5 * (y0 - y2) / denom
            delta = min(max(delta, -0.5), 0.5)
            f_peak = float(bf[peak_idx] + delta * df_bin)

    # Peak prominence vs smoothed band median → confidence component
    prominence = float(bp_s[peak_idx] / max(np.median(bp_s), 1e-12))

    # ── SDOF acceleration-FRF fit → (f_n, ζ) ───────────────────────────────
    # vert_g is an ACCELERATION channel. With approximately white road input,
    # PSD_out(ω) = G·|H_acc(ω; f_n, ζ)|² where
    #   |H_acc(ω)| = ω² / √((ωn²−ω²)² + (2ζωnω)²)
    # We least-squares fit (log G, f_n, ζ) to log(PSD) over a window around
    # the coarse peak. Uses ALL bins → immune to single-bin ripple, and the
    # fit is the standard output-only modal analysis estimator.
    from scipy.optimize import least_squares

    win = (bf >= f_peak - 1.2) & (bf <= f_peak + 1.2)
    fw, pw = bf[win], bp[win]
    log_pw = np.log(np.maximum(pw, 1e-30))
    ww = 2 * math.pi * fw

    def _fit_residual(p):
        log_g, f_n, z = p
        wn = 2 * math.pi * f_n
        h2 = ww**4 / ((wn**2 - ww**2) ** 2 + (2 * z * wn * ww) ** 2 + 1e-30)
        return (log_g + np.log(h2)) - log_pw

    try:
        fit = least_squares(
            _fit_residual,
            x0=[math.log(max(bp_s[peak_idx], 1e-30)) - math.log(1e10), f_peak, 0.25],
            bounds=([-50.0, RIDE_BAND_HZ[0], 0.02], [50.0, RIDE_BAND_HZ[1], 0.95]),
        )
        f_n = float(fit.x[1])
        zeta = float(min(max(fit.x[2], 0.02), 0.95))
        fit_ok = bool(fit.success)
    except Exception:
        f_n, zeta, fit_ok = f_peak, 0.25, False

    # ── Analytical inversion ───────────────────────────────────────────────
    m_s = float(base_params.get("m_s", 300.0))
    MR = float(base_params.get("MR", 1.0)) or 1.0

    k_w = m_s * (2 * math.pi * f_n) ** 2
    k_s = k_w / MR**2
    identified: dict[str, float] = {"k_s": round(k_s, 1)}
    if zeta is not None:
        c_w = 2.0 * zeta * math.sqrt(k_w * m_s)
        identified["c"] = round(c_w / MR, 1)

    # Deltas vs current state
    deltas: dict[str, dict] = {}
    for key, new_val in identified.items():
        old_val = base_params.get(key)
        if isinstance(old_val, (int, float)) and abs(old_val) > 1e-9:
            dpct = round(100.0 * (new_val - old_val) / abs(old_val), 2)
            deltas[key] = {
                "before": round(float(old_val), 2),
                "after": new_val,
                "delta_pct": dpct,
            }

    # ── Confidence ─────────────────────────────────────────────────────────
    conf_prominence = min(1.0, math.log10(max(prominence, 1.0)) / 2.0)   # 100× peak → full marks
    conf_samples = min(1.0, n / 5000.0)
    conf_rate = min(1.0, fs / 100.0)
    conf_zeta = 1.0 if zeta is not None else 0.4
    confidence = round(0.4 * conf_prominence + 0.25 * conf_samples
                       + 0.15 * conf_rate + 0.2 * conf_zeta, 3)

    return {
        "method": "welch-psd + SDOF acceleration-FRF least-squares fit",
        "f_n_hz": round(f_n, 4),
        "f_peak_hz": round(f_peak, 4),
        "zeta": round(zeta, 4) if zeta is not None else None,
        "fit_converged": fit_ok,
        "peak_prominence": round(prominence, 1),
        "identified_params": identified,
        "deltas": deltas,
        "confidence": confidence,
        "n_samples": int(n),
        "sample_rate_hz": round(fs, 2),
    }


def identify_from_telemetry_csv(csv_content: str, base_params: dict) -> dict[str, Any]:
    """Parse a telemetry CSV and run identification on its vertical channel."""
    from suspensionlab.physics.telemetry_parser import parse_telemetry_csv
    data = parse_telemetry_csv(csv_content)
    t = data.get("time")
    vert = data.get("vert_g")
    if not t or not vert:
        raise ValueError(
            "Telemetry must contain a time column and a vertical acceleration "
            "channel (vert_g / heave accel) for ride identification."
        )
    return identify_from_vertical_accel(t, vert, base_params)


# ─────────────────────────────────────────────────────────────────────────────
# Twin CRUD + calibration + learning aggregation
# ─────────────────────────────────────────────────────────────────────────────

async def create_twin(db: AsyncSession, user_id: str, team_id: Optional[str],
                      car_ref: str, setup_ref: str, track_ref: Optional[str],
                      base_params: dict) -> VehicleTwin:
    import uuid as _uuid
    twin = VehicleTwin(
        car_ref=car_ref, setup_ref=setup_ref, track_ref=track_ref,
        user_id=_uuid.UUID(user_id),
        team_id=_uuid.UUID(team_id) if team_id else None,
        base_params=base_params,
    )
    db.add(twin)
    await db.commit()
    await db.refresh(twin)
    return twin


async def get_twin(db: AsyncSession, twin_id: str, user_id: str,
                   team_id: Optional[str] = None) -> VehicleTwin:
    import uuid as _uuid
    conditions = [VehicleTwin.user_id == _uuid.UUID(user_id)]
    if team_id:
        conditions.append(VehicleTwin.team_id == _uuid.UUID(team_id))
    result = await db.execute(
        select(VehicleTwin).where(
            VehicleTwin.id == _uuid.UUID(twin_id), *conditions
        )
    )
    twin = result.scalar_one_or_none()
    if twin is None:
        raise LookupError(f"Twin '{twin_id}' not found.")
    return twin


async def calibrate_twin(db: AsyncSession, twin: VehicleTwin,
                         telemetry_csv: str,
                         conditions: Optional[dict] = None) -> dict:
    """
    Run parameter identification against fresh telemetry, update the twin's
    calibrated state, and append a learning observation (#41).
    """
    # Prevent commit-expiry from invalidating the twin across multi-step
    # service sequences on a shared request session.
    db.sync_session.expire_on_commit = False

    current = twin.calibrated_params or twin.base_params
    report = identify_from_telemetry_csv(telemetry_csv, current)

    before_state = dict(current)
    calibrated = {**current, **report["identified_params"]}

    twin.calibrated_params = calibrated
    twin.last_identification = report
    twin.calibration_count = (twin.calibration_count or 0) + 1

    obs = CalibrationObservation(
        twin_id=twin.id,
        param_deltas=report["deltas"],
        responses={
            "f_n_hz": report["f_n_hz"],
            "zeta": report["zeta"],
        },
        conditions=conditions or {},
        n_samples=report["n_samples"],
        confidence=report["confidence"],
    )
    # Capture response data BEFORE commit — committing expires ORM instances
    # and lazy-loading them afterwards breaks inside async sessions.
    result = {
        "twin": f"{twin.car_ref}/{twin.setup_ref}",
        "calibration_count": twin.calibration_count,
        "identification": report,
        "calibrated_params": calibrated,
        "changed_from": before_state,
    }
    db.add(obs)
    await db.commit()

    logger.info("Twin %s calibrated (%d): %s",
                result["twin"], result["calibration_count"], report["identified_params"])
    return result


async def get_learnings(db: AsyncSession, twin: VehicleTwin) -> dict:
    """
    Aggregate CalibrationObservations into vehicle-specific intelligence (#41):
    per-parameter mean drift, response trend across calibrations, and
    human-readable learned statements.
    """
    result = await db.execute(
        select(CalibrationObservation)
        .where(CalibrationObservation.twin_id == twin.id)
        .order_by(desc(CalibrationObservation.created_at))
        .limit(200)
    )
    observations = list(result.scalars().all())

    if not observations:
        return {
            "twin": f"{twin.car_ref}/{twin.setup_ref}",
            "calibrations": 0,
            "learnings": [],
            "note": "No calibrations yet — calibrate against telemetry to start building vehicle-specific intelligence.",
        }

    # Per-parameter drift statistics
    param_stats: dict[str, list[float]] = {}
    for obs in observations:
        for key, d in (obs.param_deltas or {}).items():
            if isinstance(d, dict) and isinstance(d.get("delta_pct"), (int, float)):
                param_stats.setdefault(key, []).append(float(d["delta_pct"]))

    drift = [
        {
            "parameter": key,
            "calibrations": len(vals),
            "mean_delta_pct": round(sum(vals) / len(vals), 2),
            "min_delta_pct": round(min(vals), 2),
            "max_delta_pct": round(max(vals), 2),
        }
        for key, vals in sorted(param_stats.items())
    ]

    # Response trend (is the identified frequency converging?)
    freqs = [o.responses.get("f_n_hz") for o in reversed(observations)
             if isinstance(o.responses, dict)]
    trend = None
    if len(freqs) >= 2 and all(isinstance(f, (int, float)) for f in freqs):
        trend = {
            "first_f_n_hz": freqs[0],
            "latest_f_n_hz": freqs[-1],
            "converging": abs(freqs[-1] - freqs[-2]) < abs(freqs[1] - freqs[0]) if len(freqs) > 2 else None,
        }

    # Human-readable learned statements
    learnings = []
    for d in sorted(drift, key=lambda x: -abs(x["mean_delta_pct"])):
        direction = "softer" if d["mean_delta_pct"] < 0 else "stiffer"
        learnings.append(
            f"On this car, {d['parameter']} is consistently identified "
            f"{d['mean_delta_pct']:+.1f}% vs handbook ({direction}) across "
            f"{d['calibrations']} calibration(s) — the as-designed value appears "
            f"biased; trust the calibrated value."
        )
    if trend and trend.get("converging") is True:
        learnings.append(
            f"Identified ride frequency is converging ({trend['first_f_n_hz']} → "
            f"{trend['latest_f_n_hz']} Hz) — twin confidence increasing with each session."
        )

    avg_conf = sum(o.confidence for o in observations) / len(observations)
    total_samples = sum(o.n_samples for o in observations)

    return {
        "twin": f"{twin.car_ref}/{twin.setup_ref}",
        "calibrations": len(observations),
        "total_telemetry_samples": total_samples,
        "avg_confidence": round(avg_conf, 3),
        "parameter_drift": drift,
        "response_trend": trend,
        "learnings": learnings,
    }
