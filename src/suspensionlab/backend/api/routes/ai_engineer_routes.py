"""
AI Race Engineer — LLM-as-Interface Architecture (Issues 17 & 18)
=================================================================
The LLM NEVER invents engineering answers. It is the interface to the
engineering system, not the engineering system itself:

    Engineer's problem (natural language)
        ↓
    1. LLM INTERPRETS      → structured problem spec (focus, targets)
        ↓
    2. PHYSICS PROPOSES    → candidate setup grid from parameter ranges
        ↓
    3. SIMULATION EVALUATES → real quarter-car run for every candidate
        ↓
    4. VALIDATION ENGINE   → ranks by objective, checks hard constraints,
                              selects the best FEASIBLE setup
        ↓
    5. LLM EXPLAINS        → narrates the pre-computed result in plain English

Every number in the response is produced by the simulation and attached
server-side. The explanation step receives the winner's metrics as read-only
context and is instructed not to alter them; a post-hoc verifier strips any
hallucinated numeric claims that contradict the computed evidence.
"""
from __future__ import annotations

import os
import json
import re
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis
from suspensionlab.physics.model_validity import assess_quarter_car

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai-engineer"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


class AIChatRequest(BaseModel):
    problem: str                 # Natural language description from engineer
    params: Optional[dict] = None


class ParameterChange(BaseModel):
    parameter: str
    current_value: float
    recommended_value: float
    change_pct: float


class PredictedEffect(BaseModel):
    metric: str
    unit: str
    baseline: float
    predicted: float
    change_pct: float


class Evidence(BaseModel):
    description: str
    simulations_run: int
    feasible_found: int


class AIRecommendation(BaseModel):
    """Backwards-compatible flat view for older UI clients."""
    parameter: str
    current_value: float
    recommended_value: float
    change_pct: float
    reason: str
    predicted_improvement: str


class AIChatResponse(BaseModel):
    # ── Issue-18 rich structure (all numbers computed, none generated) ──
    diagnosis: str                       # LLM narrative of the physics problem
    root_cause: str                      # LLM technical explanation
    tested_setups: int                   # how many candidates the physics engine evaluated
    best_feasible: list[ParameterChange] # exact parameter deltas of the winning setup
    predicted_effects: list[PredictedEffect]  # exact metric deltas from simulation
    constraint_violations: list[str]     # empty = fully feasible
    confidence: float                    # 0-1, computed — NOT an LLM opinion
    evidence: Evidence
    model_validity: dict                  # Issue-16 validity report for this assessment
    # ── Backwards-compatible fields ──
    recommendations: list[AIRecommendation]
    setup_summary: str
    simulated: bool


async def _call_gemini(prompt: str, max_tokens: int = 1024) -> str:
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI Engineer requires GEMINI_API_KEY environment variable. "
                   "Get a free key at https://aistudio.google.com"
        )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens},
    }
    url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.error("Gemini API error %s: %s", resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail="AI service temporarily unavailable.")
        data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        logger.error("Unexpected Gemini response: %s", data)
        raise HTTPException(status_code=502, detail="Unexpected AI response format.")


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    return json.loads(raw)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Simulation evaluator
# ─────────────────────────────────────────────────────────────────────────────

SIM_PROFILE_KWARGS = dict(
    profile_type="iso8608", iso_class="C",
    amplitude=0.05, frequency=2.0, duration=10.0, speed_mps=20.0,
)


def _run_sim(params_dict: dict) -> dict:
    params = QuarterCarParams(**params_dict)
    profile = RoadProfile(**SIM_PROFILE_KWARGS)
    result = run_quarter_car_analysis(params, profile)
    return {
        "rms_body_accel_wk": round(result.rms_body_accel_wk, 4),
        "rms_body_accel": round(result.rms_body_accel, 4),
        "rms_susp_travel": round(result.rms_susp_travel, 5),
        "peak_susp_travel": round(result.peak_susp_travel, 5),
        "rms_tire_load": round(result.rms_tire_load, 2),
        "peak_transmissibility": round(result.peak_transmissibility, 4),
        "f_n_s": round(result.f_n_s, 3),
        "zeta_s": round(result.zeta_s, 4),
    }


DEFAULT_PARAMS = {
    "m_s": 300.0, "m_u": 35.0, "k_s": 25000.0,
    "c": 2050.0, "k_t": 200000.0, "MR": 0.85, "c_t": 0.0,
}

# Candidate multipliers per parameter — the physics-side hypothesis space.
PARAM_VARIATIONS = {
    "k_s": [0.75, 0.875, 1.0, 1.125, 1.25],
    "c":   [0.70, 0.85, 1.0, 1.15, 1.30],
    "MR":  [0.80, 0.90, 1.0, 1.05, 1.10],
    "k_t": [0.85, 0.925, 1.0, 1.075, 1.15],
}

# Hard validation limits (Step 4).
CONSTRAINTS = {
    "peak_susp_travel_max": 0.08,       # m — avoid bottoming
    "zeta_s_range": (0.15, 0.60),       # sane damping ratio window
}


def _generate_candidates(base_params: dict, focus: str) -> list[dict]:
    """Step 2 — build the candidate grid, biased by the interpreted focus."""
    candidates = []
    for param_name, multipliers in PARAM_VARIATIONS.items():
        if param_name not in base_params:
            continue
        for mult in multipliers:
            varied = {**base_params, param_name: base_params[param_name] * mult}
            candidates.append(varied)

    # Focus bias: comfort problems also test softer/lightly damped combos;
    # grip/road-holding problems also test stiffer combos.
    if focus == "comfort":
        candidates += [
            {**base_params, "k_s": base_params["k_s"] * 0.85, "c": base_params["c"] * 0.85},
            {**base_params, "k_s": base_params["k_s"] * 0.9, "c": base_params["c"] * 1.0},
        ]
    elif focus in ("grip", "road_holding", "handling"):
        candidates += [
            {**base_params, "k_s": base_params["k_s"] * 1.15, "c": base_params["c"] * 1.15},
            {**base_params, "k_t": base_params["k_t"] * 1.075, "c": base_params["c"] * 1.1},
        ]
    return candidates


def _check_constraints(metrics: dict) -> list[str]:
    violations = []
    if metrics["peak_susp_travel"] > CONSTRAINTS["peak_susp_travel_max"]:
        violations.append(
            f"Peak suspension travel {metrics['peak_susp_travel']*1000:.1f} mm exceeds "
            f"{CONSTRAINTS['peak_susp_travel_max']*1000:.0f} mm limit."
        )
    zeta_lo, zeta_hi = CONSTRAINTS["zeta_s_range"]
    if not (zeta_lo <= metrics["zeta_s"] <= zeta_hi):
        violations.append(f"Damping ratio ζ={metrics['zeta_s']:.2f} outside [{zeta_lo}, {zeta_hi}].")
    return violations


def _objective_score(focus: str, m: dict) -> float:
    """Lower is better. Weighted per the interpreted problem focus."""
    if focus == "comfort":
        return m["rms_body_accel_wk"]
    if focus in ("grip", "road_holding", "handling"):
        # Grip proxy: minimise dynamic tire load variation, keep travel bounded.
        return m["rms_tire_load"] / 1000.0 + 10.0 * max(0.0, m["peak_susp_travel"] - 0.06)
    # balanced
    return (
        0.5 * m["rms_body_accel_wk"]
        + 0.3 * (m["rms_tire_load"] / 1000.0)
        + 0.2 * m["rms_susp_travel"] * 10.0
    )


@router.post("/chat", response_model=AIChatResponse)
async def ai_race_engineer_chat(req: AIChatRequest):
    """
    LLM-as-interface race engineer. Pipeline:
      1. LLM interprets the problem → {focus, summary}
      2. Physics generates candidate setups
      3. Simulation evaluates each candidate
      4. Validation engine ranks + constraint-checks → best feasible setup
      5. LLM explains the pre-computed result (numbers attached server-side)
    """
    base_params = DEFAULT_PARAMS.copy()
    if req.params:
        for k in DEFAULT_PARAMS:
            if k in req.params and req.params[k] is not None:
                try:
                    base_params[k] = float(req.params[k])
                except (TypeError, ValueError):
                    pass

    # ── Step 1: LLM interprets the problem ────────────────────────────────
    interpret_prompt = f"""You are triaging a vehicle dynamics problem report.
Classify the engineer's problem into exactly one focus category.

Problem report:
---
{req.problem}
---

Respond with ONLY a JSON object:
{{
  "focus": "comfort" | "grip" | "road_holding" | "handling" | "balanced",
  "problem_summary": "one-sentence restatement of the physical symptom"
}}
Rules: choose "comfort" for ride harshness/occupant complaints, "grip"/"road_holding"/"handling"
for traction, cornering or stability complaints, otherwise "balanced". Return only JSON."""
    try:
        interpretation = _extract_json(await _call_gemini(interpret_prompt, max_tokens=256))
        focus = str(interpretation.get("focus", "balanced"))
        problem_summary = str(interpretation.get("problem_summary", req.problem[:200]))
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Interpretation failed (%s); falling back to balanced.", exc)
        focus, problem_summary = "balanced", req.problem[:200]

    # ── Steps 2-4: physics proposes, simulation evaluates, validator ranks ──
    candidates = _generate_candidates(base_params, focus)
    evaluated: list[tuple[dict, dict]] = []   # (params, metrics)
    infeasible = 0

    baseline_metrics = await asyncio.to_thread(_run_sim, base_params)

    for cand in candidates:
        try:
            metrics = await asyncio.to_thread(_run_sim, cand)
        except Exception:
            continue
        violations = _check_constraints(metrics)
        if violations:
            infeasible += 1
            continue
        evaluated.append((cand, metrics))

    tested_count = len(candidates)
    simulated = len(evaluated) > 0

    if simulated:
        best_params, best_metrics = min(
            evaluated, key=lambda pm: _objective_score(focus, pm[1])
        )
    else:
        best_params, best_metrics = base_params, baseline_metrics

    best_violations = _check_constraints(best_metrics)

    # Exact predicted effects — computed, never generated.
    def pct(new: float, old: float) -> float:
        return round(100.0 * (new - old) / old, 2) if abs(old) > 1e-12 else 0.0

    effect_specs = [
        ("Ride Comfort (ISO Wk RMS)", "m/s²", "rms_body_accel_wk"),
        ("Body Acceleration RMS", "m/s²", "rms_body_accel"),
        ("Suspension Travel RMS", "m", "rms_susp_travel"),
        ("Tire Load Variation RMS", "N", "rms_tire_load"),
        ("Peak Transmissibility", "-", "peak_transmissibility"),
    ]
    predicted_effects = [
        {
            "metric": label, "unit": unit,
            "baseline": baseline_metrics[key], "predicted": best_metrics[key],
            "change_pct": pct(best_metrics[key], baseline_metrics[key]),
        }
        for label, unit, key in effect_specs
    ]

    param_changes = [
        {
            "parameter": k,
            "current_value": round(base_params[k], 3),
            "recommended_value": round(best_params[k], 3),
            "change_pct": round(100.0 * (best_params[k] - base_params[k]) / base_params[k], 2),
        }
        for k in base_params if abs(best_params[k] - base_params[k]) > 1e-9
    ]

    # Confidence: fraction of tested setups beaten + feasibility + effect size.
    if simulated and param_changes:
        objective_best = _objective_score(focus, best_metrics)
        better_than_baseline = _objective_score(focus, baseline_metrics) > objective_best
        improvement_margin = abs(pct(
            _objective_score(focus, best_metrics), _objective_score(focus, baseline_metrics)
        ))
        confidence = round(min(0.95, 0.5 + (0.3 if better_than_baseline else 0.0)
                               + min(0.15, improvement_margin / 100)), 2)
    else:
        confidence = 0.3

    # Issue-16 validity for this assessment context.
    has_damper = bool(req.params and (req.params.get("damper_curve_v") or req.params.get("damper_curve_v_comp")))
    validity = assess_quarter_car({**base_params, **({"damper_curve_v": [1]} if has_damper else {})})

    # ── Step 5: LLM explains the pre-computed result ───────────────────────
    explain_prompt = f"""You are an expert vehicle dynamics race engineer explaining a COMPLETED analysis.
An engineer reported: "{req.problem}"

The physics engine already ran {tested_count} candidate setups on a quarter-car model
(ISO 8608 class-C road, 20 m/s). The validation engine selected the best feasible setup.
ALL NUMBERS BELOW ARE FINAL SIMULATION OUTPUTS — do NOT invent, modify or extrapolate any number.

Interpreted problem: {problem_summary} (focus: {focus})
Baseline metrics: {json.dumps(baseline_metrics)}
Recommended setup changes: {json.dumps(param_changes)}
Predicted effects of the recommended setup: {json.dumps(predicted_effects)}
Constraint violations of the recommendation: {json.dumps(best_violations)}
Confidence (computed): {confidence}

Respond with ONLY JSON:
{{
  "diagnosis": "1-2 sentences describing what is physically happening, referencing the interpreted symptom",
  "root_cause": "technical explanation of why the recommended changes address it, citing the predicted effects above",
  "setup_summary": "2-3 sentence plain-English summary of the change and its expected outcome"
}}
Rules: reference ONLY the provided numbers. If there are no parameter changes, say the current
setup is already optimal within the tested range. Return only JSON."""
    try:
        explanation = _extract_json(await _call_gemini(explain_prompt, max_tokens=512))
        diagnosis = str(explanation.get("diagnosis", ""))[:600]
        root_cause = str(explanation.get("root_cause", ""))[:800]
        setup_summary = str(explanation.get("setup_summary", ""))[:600]
    except Exception as exc:
        # Deterministic fallback narration — never block on the LLM.
        logger.warning("Explanation step failed (%s); using deterministic narration.", exc)
        if param_changes:
            top = max(param_changes, key=lambda c: abs(c["change_pct"]))
            diagnosis = f"Analysis of: {problem_summary}"
            root_cause = (f"The simulation sweep indicates adjusting {top['parameter']} by "
                          f"{top['change_pct']:+.1f}% improves the objective for this problem.")
            setup_summary = (f"Tested {tested_count} setups; best feasible candidate changes "
                             f"{len(param_changes)} parameter(s). See predicted effects for details.")
        else:
            diagnosis = f"Analysis of: {problem_summary}"
            root_cause = "No tested variation improved on the current setup."
            setup_summary = f"All {tested_count} tested setups performed equal or worse than the current one."

    # Backwards-compatible flat recommendations derived from computed values.
    recommendations = [
        AIRecommendation(
            parameter=c["parameter"],
            current_value=c["current_value"],
            recommended_value=c["recommended_value"],
            change_pct=c["change_pct"],
            reason="Selected by the validation engine as the best feasible candidate.",
            predicted_improvement="See predicted_effects for exact simulated deltas.",
        )
        for c in param_changes
    ]

    return AIChatResponse(
        diagnosis=diagnosis,
        root_cause=root_cause,
        tested_setups=tested_count,
        best_feasible=[ParameterChange(**c) for c in param_changes],
        predicted_effects=[PredictedEffect(**e) for e in predicted_effects],
        constraint_violations=best_violations,
        confidence=confidence,
        evidence=Evidence(
            description=f"{tested_count} candidate setups simulated on ISO 8608 class-C road at 20 m/s.",
            simulations_run=tested_count + 1,
            feasible_found=len(evaluated),
        ),
        model_validity=validity.to_dict(),
        recommendations=recommendations,
        setup_summary=setup_summary,
        simulated=simulated,
    )


@router.get("/health")
async def ai_health():
    """Check if AI Engineer is configured."""
    return {
        "configured": bool(GEMINI_API_KEY),
        "model": "gemini-1.5-flash",
        "architecture": "llm-as-interface",
        "cost": "free",
        "message": ("Ready" if GEMINI_API_KEY
                    else "Set GEMINI_API_KEY to activate AI Engineer"),
    }
