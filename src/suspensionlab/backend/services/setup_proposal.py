"""
backend/services/setup_proposal.py
===================================
Setup Proposal engine (Issue 50) — the end-to-end engineering decision step.

    Engineer: "Why is the car unstable in T9?"
        ↓
    Twin calibrated params (from telemetry identification)
        ↓
    Candidate search across the feasible setup space
        ↓
    Simulation evaluates every candidate
        ↓
    Validation engine ranks + constraint-checks
        ↓
    Immutable SETUP PROPOSAL artifact → engineer approves / rejects / exports

Deterministic and physics-grounded: every number in a proposal comes from a
simulation of the twin's own calibrated parameters. No LLM participates in
producing numbers.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.models.setup_proposal import SetupProposal
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin
from suspensionlab.backend.core.compute_governance import bounded_run

logger = logging.getLogger(__name__)

# Candidate multipliers per parameter — the searched setup space.
SEARCH_SPACE: dict[str, list[float]] = {
    "k_s": [0.85, 0.925, 1.0, 1.075, 1.15],
    "c":   [0.80, 0.90, 1.0, 1.10, 1.20],
}

from suspensionlab.physics.pareto_optimizer import DEFAULT_MAX_SUSP_TRAVEL_MM

# Hard validation limits.
CONSTRAINTS = {
    "peak_susp_travel_max": DEFAULT_MAX_SUSP_TRAVEL_MM / 1000.0,     # m (80 mm, shared)
    "zeta_s_range": (0.15, 0.60),
}

SIM_PROFILE_KWARGS = dict(
    profile_type="iso8608", iso_class="C",
    amplitude=0.05, frequency=2.0, duration=10.0, speed_mps=20.0,
)

EFFECT_SPECS = [
    ("Ride Comfort (ISO Wk RMS)", "m/s²", "rms_body_accel_wk"),
    ("Body Acceleration RMS", "m/s²", "rms_body_accel"),
    ("Suspension Travel RMS", "m", "rms_susp_travel"),
    ("Tire Load Variation RMS", "N", "rms_tire_load"),
    ("Peak Transmissibility", "-", "peak_transmissibility"),
]


def classify_focus(problem: str) -> str:
    """Keyword-based focus classification — deterministic, no LLM."""
    p = problem.lower()
    if any(k in p for k in ("comfort", "harsh", "harshness", "ride quality", "bumpy", "jarring")):
        return "comfort"
    if any(k in p for k in ("grip", "traction", "slip", "saturation")):
        return "grip"
    if any(k in p for k in ("unstable", "instability", "handling", "balance", "entry", "exit", "mid-corner")):
        return "handling"
    return "balanced"


def _objective(focus: str, m: dict) -> float:
    """Lower is better."""
    if focus == "comfort":
        return m.get("rms_body_accel_wk", 1e9)
    if focus in ("grip", "handling"):
        return m.get("rms_tire_load", 1e9) / 1000.0 + 10.0 * max(0.0, m.get("peak_susp_travel", 0.0) - 0.06)
    return (0.5 * m.get("rms_body_accel_wk", 1e9)
            + 0.3 * m.get("rms_tire_load", 1e9) / 1000.0
            + 0.2 * m.get("rms_susp_travel", 1e9) * 10.0)


def _run_sim(params_dict: dict) -> dict:
    from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis
    params = QuarterCarParams(**params_dict)
    profile = RoadProfile(**SIM_PROFILE_KWARGS)
    r = run_quarter_car_analysis(params, profile)
    return {
        "rms_body_accel_wk": round(r.rms_body_accel_wk, 4),
        "rms_body_accel": round(r.rms_body_accel, 4),
        "rms_susp_travel": round(r.rms_susp_travel, 5),
        "peak_susp_travel": round(r.peak_susp_travel, 5),
        "rms_tire_load": round(r.rms_tire_load, 2),
        "peak_transmissibility": round(r.peak_transmissibility, 4),
        "zeta_s": (None if r.zeta_s is None else round(r.zeta_s, 4)),
    }


def _violations(m: dict) -> list[str]:
    v = []
    if m["peak_susp_travel"] > CONSTRAINTS["peak_susp_travel_max"]:
        v.append(f"Peak suspension travel {m['peak_susp_travel']*1000:.1f} mm exceeds "
                 f"{CONSTRAINTS['peak_susp_travel_max']*1000:.0f} mm limit.")
    lo, hi = CONSTRAINTS["zeta_s_range"]
    if m["zeta_s"] is None:
        # Overdamped (real poles): ratio undefined and above the allowed range.
        v.append(f"Damping ratio undefined (overdamped, real poles); outside [{lo}, {hi}].")
    elif not (lo <= m["zeta_s"] <= hi):
        v.append(f"Damping ratio ζ={m['zeta_s']:.2f} outside [{lo}, {hi}].")
    return v


async def generate_proposal(
    db: AsyncSession,
    twin: VehicleTwin,
    problem: str,
    user_id: str,
    team_id: Optional[str] = None,
) -> SetupProposal:
    """
    Full #50 pipeline on the twin's CALIBRATED parameters:
      search → simulate → validate → rank → persist immutable proposal.
    """
    # Prevent commit-expiry from invalidating the twin across the multi-commit
    # proposal sequence on a shared request session.
    db.sync_session.expire_on_commit = False

    base = twin.calibrated_params or twin.base_params
    focus = classify_focus(problem)

    # Baseline
    baseline = await bounded_run(_run_sim, base, model="quarter_car")

    # ── Candidate generation ───────────────────────────────────────────────
    candidates: list[dict] = []
    for param, mults in SEARCH_SPACE.items():
        if param not in base:
            continue
        for mult in mults:
            cand = {**base, param: base[param] * mult}
            if cand != base:
                candidates.append(cand)
    # Focus-biased combos
    if focus == "comfort":
        candidates += [{**base, "k_s": base["k_s"] * 0.9, "c": base["c"] * 0.9}]
    elif focus in ("grip", "handling"):
        candidates += [{**base, "c": base["c"] * 1.12, "k_s": base["k_s"] * 1.05}]

    tested = len(candidates)
    feasible: list[tuple[dict, dict]] = []
    for cand in candidates:
        try:
            m = await bounded_run(_run_sim, cand, model="quarter_car")
        except Exception:
            continue
        if not _violations(m):
            feasible.append((cand, m))

    simulated = bool(feasible)
    if simulated:
        best_params, best_metrics = min(feasible, key=lambda pm: _objective(focus, pm[1]))
    else:
        best_params, best_metrics = dict(base), baseline

    violations = _violations(best_metrics)

    def pct(new: float, old: float) -> Optional[float]:
        return round(100.0 * (new - old) / abs(old), 2) if abs(old) > 1e-12 else None

    param_changes = [
        {
            "parameter": k,
            "current": round(float(base[k]), 3),
            "recommended": round(float(best_params[k]), 3),
            "change_pct": pct(best_params[k], base[k]),
        }
        for k in base if isinstance(base.get(k), (int, float))
        and isinstance(best_params.get(k), (int, float))
        and abs(best_params[k] - base[k]) > 1e-9
    ]

    predicted_effects = [
        {
            "metric": label, "unit": unit,
            "baseline": baseline[key], "predicted": best_metrics[key],
            "change_pct": pct(best_metrics[key], baseline[key]),
            "improved": (pct(best_metrics[key], baseline[key]) or 0) < 0,
        }
        for label, unit, key in EFFECT_SPECS
        if key in baseline and key in best_metrics
    ]

    # Confidence: improvement margin + feasibility ratio
    if simulated and param_changes:
        obj_best = _objective(focus, best_metrics)
        obj_base = _objective(focus, baseline)
        better = obj_base > obj_best
        margin = abs(pct(obj_best, obj_base)) or 0.0
        confidence = round(min(0.95, 0.5 + (0.3 if better else 0.0) + min(0.15, margin / 100)), 2)
    else:
        confidence = 0.3

    # Compute SHA-256 canonical hash of proposal recommendation
    from suspensionlab.backend.security.audit import canonical_hash
    prop_payload = {
        "recommended_params": best_params,
        "param_changes": param_changes,
        "predicted_effects": predicted_effects,
    }
    proposal_hash = canonical_hash(prop_payload)

    proposal = SetupProposal(
        twin_id=twin.id,
        user_id=__import__("uuid").UUID(user_id),
        team_id=__import__("uuid").UUID(team_id) if team_id else None,
        problem=problem[:4000],
        focus=focus,
        baseline_params=dict(base),
        tested_setups=tested,
        feasible_found=len(feasible),
        recommended_params=best_params,
        param_changes=param_changes,
        predicted_effects=predicted_effects,
        constraint_violations=violations,
        confidence=confidence,
        proposal_hash=proposal_hash,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)

    logger.info("Setup proposal %s created for %s/%s (%d tested, %d feasible)",
                proposal.id, twin.car_ref, twin.setup_ref, tested, len(feasible))
    return proposal


def proposal_to_dict(p: SetupProposal) -> dict:
    return {
        "id": str(p.id),
        "twin_id": str(p.twin_id),
        "problem": p.problem,
        "focus": p.focus,
        "tested_setups": p.tested_setups,
        "feasible_found": p.feasible_found,
        "recommended_params": p.recommended_params,
        "param_changes": p.param_changes,
        "predicted_effects": p.predicted_effects,
        "constraint_violations": p.constraint_violations or [],
        "confidence": p.confidence,
        "status": p.status,
        "proposal_hash": p.proposal_hash,
        "approved_by_user_id": str(p.approved_by_user_id) if p.approved_by_user_id else None,
        "approved_by_role": p.approved_by_role,
        "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        "approval_signature": p.approval_signature,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }

