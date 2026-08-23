"""
backend/services/decision_layer.py
===================================
Layered Decision UI backend (Issue 36).

Engineers get answers in layers — never a wall of charts:

    Layer 1  DECISION   GOOD / WARNING / CRITICAL
    Layer 2  WHY        plain-language reasons ("Rear tire saturation")
    Layer 3  EVIDENCE   the specific metrics behind each reason
    Layer 4  RAW DATA   full plots (frontend renders from run payload)

build_decision(run) evaluates an immutable run artifact against engineering
thresholds and returns all four layers in one payload.
"""
from __future__ import annotations

from typing import Any, Literal

Verdict = Literal["GOOD", "WARNING", "CRITICAL"]

# metric key -> (label, unit, good_max, warn_max)   # values above good_max → WARNING, above warn_max → CRITICAL
UPPER_LIMITS: dict[str, tuple[str, str, float, float]] = {
    "peak_susp_travel":      ("Peak suspension travel", "mm", 50.0, 80.0),
    "peak_transmissibility": ("Peak transmissibility", "×", 2.0, 3.5),
}

# metric key -> (label, unit, good_min, good_max, warn_min, warn_max)  # window metrics
WINDOW_LIMITS: dict[str, tuple[str, str, float, float, float, float]] = {
    "zeta_s": ("Damping ratio ζ", "-", 0.25, 0.45, 0.15, 0.65),
}


def _scale(result: dict, key: str, factor: float = 1.0) -> float | None:
    v = result.get(key)
    return float(v) * factor if isinstance(v, (int, float)) else None


def build_decision(run) -> dict[str, Any]:
    """
    Evaluate a SimulationRun artifact and produce the layered decision payload.
    Deterministic: same artifact → same verdict.
    """
    result = run.result or {}
    checks: list[dict] = []
    worst: Verdict = "GOOD"

    def bump(v: Verdict):
        nonlocal worst
        order = {"GOOD": 0, "WARNING": 1, "CRITICAL": 2}
        if order[v] > order[worst]:
            worst = v

    # ── Upper-limit metrics ────────────────────────────────────────────────
    for key, (label, unit, good_max, warn_max) in UPPER_LIMITS.items():
        v = _scale(result, key, 1000.0 if unit == "mm" else 1.0)
        if v is None:
            continue
        if v <= good_max:
            status = "pass"
        elif v <= warn_max:
            status, verdict = "warn", "WARNING"
        else:
            status, verdict = "fail", "CRITICAL"
        if status != "pass":
            bump(verdict)
            checks.append({
                "key": key, "label": label, "value": round(v, 3), "unit": unit,
                "status": status,
                "why": (f"{label} is {v:.1f} {unit} — above the {good_max:g} {unit} "
                        f"target{' and beyond the ' + format(warn_max, 'g') + ' ' + unit + ' safety limit' if status == 'fail' else ''}."),
                "evidence": [key],
            })

    # ── Window metrics (damping ratio) ─────────────────────────────────────
    for key, (label, unit, g_lo, g_hi, w_lo, w_hi) in WINDOW_LIMITS.items():
        v = _scale(result, key)
        if v is None:
            continue
        if g_lo <= v <= g_hi:
            status = "pass"
            why = ""
        elif w_lo <= v <= w_hi:
            status, verdict = "warn", "WARNING"
            side = "under-damped" if v < g_lo else "over-damped"
            bump(verdict)
            why = f"{label} = {v:.2f} — {side} relative to the 0.25–0.45 target window."
        else:
            status, verdict = "fail", "CRITICAL"
            side = "severely under-damped" if v < w_lo else "severely over-damped"
            bump(verdict)
            why = f"{label} = {v:.2f} — {side}; handling/comfort behaviour unreliable."
        if status != "pass":
            checks.append({
                "key": key, "label": label, "value": round(v, 3), "unit": unit,
                "status": status, "why": why, "evidence": [key],
            })

    # ── Tire load variation (grip consistency proxy) ───────────────────────
    tl = _scale(result, "rms_tire_load")
    if tl is not None:
        if tl > 1500:
            bump("WARNING")
            checks.append({
                "key": "rms_tire_load", "label": "Tire load variation", "value": round(tl, 1),
                "unit": "N", "status": "warn",
                "why": f"Dynamic tire load variation {tl:.0f} N is high — grip consistency "
                       f"suffers; expect reduced cornering entry confidence.",
                "evidence": ["rms_tire_load"],
            })

    # ── Model validity feeds the verdict too (#16 integration) ────────────
    validity = run.model_validity or {}
    vscore = validity.get("score")
    if isinstance(vscore, (int, float)):
        if vscore < 55:
            bump("CRITICAL")
            checks.append({
                "key": "model_validity", "label": "Model validity", "value": vscore,
                "unit": "%", "status": "fail",
                "why": f"Model validity {vscore:.0f}% — results are conceptual only; "
                       f"do not base setup decisions on this run.",
                "evidence": [c["label"] for c in validity.get("checks", []) if c.get("status") == "fail"],
            })
        elif vscore < 80:
            bump("WARNING")
            checks.append({
                "key": "model_validity", "label": "Model validity", "value": vscore,
                "unit": "%", "status": "warn",
                "why": f"Model validity {vscore:.0f}% — directionally useful; validate changes on the car.",
                "evidence": [c["label"] for c in validity.get("checks", []) if c.get("status") == "warn"],
            })

    # ── Headline ───────────────────────────────────────────────────────────
    headlines = {
        "GOOD":     "Setup within engineering targets",
        "WARNING":  "Setup usable — review flagged items",
        "CRITICAL": "Setup has critical issues — do not ship",
    }
    # Layer-2 summary: primary reason = first failing check
    primary = next((c for c in checks if c["status"] == "fail"), None) or \
              next((c for c in checks if c["status"] == "warn"), None)

    return {
        "run": run.label,
        "verdict": worst,
        "headline": headlines[worst],
        "primary_reason": primary["why"] if primary else None,
        "layers": {
            "decision": {"verdict": worst, "headline": headlines[worst]},
            "why": [c["why"] for c in checks],
            "evidence": [
                {"label": c["label"], "key": c["key"], "value": c["value"],
                 "unit": c["unit"], "status": c["status"]}
                for c in checks
            ],
            "raw_data": {
                "available_metrics": sorted(
                    k for k, v in (run.result or {}).items()
                    if isinstance(v, (int, float))
                ),
                "params_hash": run.params_hash,
                "result_hash": run.result_hash,
                "note": "Full time-series plots render from the run payload (GET /runs/{label}).",
            },
        },
        "checks": checks,
    }
