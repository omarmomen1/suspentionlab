"""
AI Race Engineer — Natural Language Suspension Tuning Assistant
Uses Google Gemini Flash (free tier) to interpret engineer problems,
runs real physics simulations, and returns actionable setup recommendations.
No cost: Gemini Flash free tier = 1500 requests/day.
"""
from __future__ import annotations
import os
import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import httpx

from suspensionlab.physics.quarter_car import QuarterCarParams, RoadProfile, run_quarter_car_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai-engineer"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


class AIChatRequest(BaseModel):
    problem: str  # Natural language description from engineer
    params: Optional[dict] = None  # Current simulation params (optional context)


class AIRecommendation(BaseModel):
    parameter: str
    current_value: float
    recommended_value: float
    change_pct: float
    reason: str
    predicted_improvement: str


class AIChatResponse(BaseModel):
    diagnosis: str
    root_cause: str
    recommendations: list[AIRecommendation]
    setup_summary: str
    confidence: str  # "High" | "Medium" | "Low"
    simulated: bool  # Whether we ran actual physics simulations


async def _call_gemini(prompt: str) -> str:
    """Call Gemini Flash API. Returns raw text response."""
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI Engineer requires GEMINI_API_KEY environment variable. Get a free key at https://aistudio.google.com"
        )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
        }
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
    except (KeyError, IndexError) as e:
        logger.error("Unexpected Gemini response: %s", data)
        raise HTTPException(status_code=502, detail="Unexpected AI response format.")


def _run_sim(params_dict: dict) -> dict:
    """Run a quarter-car simulation synchronously (called via asyncio.to_thread)."""
    params = QuarterCarParams(**params_dict)
    profile = RoadProfile(profile_type="iso8608", iso_class="C", amplitude=0.05, frequency=2.0, duration=10.0, speed_mps=20.0)
    result = run_quarter_car_analysis(params, profile)
    return {
        "rms_body_accel": round(result.rms_body_accel, 4),
        "rms_body_accel_wk": round(result.rms_body_accel_wk, 4),
        "rms_susp_travel": round(result.rms_susp_travel, 5),
        "rms_tire_load": round(result.rms_tire_load, 2),
        "peak_susp_travel": round(result.peak_susp_travel, 5),
        "peak_transmissibility": round(result.peak_transmissibility, 4),
        "f_n_s": round(result.f_n_s, 3),
        "zeta_s": round(result.zeta_s, 4),
    }


DEFAULT_PARAMS = {
    "m_s": 300.0, "m_u": 35.0, "k_s": 25000.0,
    "c": 2050.0, "k_t": 200000.0, "MR": 0.85, "c_t": 0.0
}

# Reasonable variation ranges per parameter
PARAM_VARIATIONS = {
    "k_s": [0.75, 0.875, 1.0, 1.125, 1.25],   # ±25% spring rate
    "c":   [0.70, 0.85,  1.0, 1.15,  1.30],   # ±30% damping
    "MR":  [0.80, 0.90,  1.0, 1.05,  1.10],   # ±10% motion ratio
    "k_t": [0.85, 0.925, 1.0, 1.075, 1.15],   # ±15% tire stiffness
}


async def _run_parameter_sweep(base_params: dict) -> dict:
    """Run physics simulations across parameter variations. Returns comparison table."""
    baseline = await asyncio.to_thread(_run_sim, base_params)
    sweep_results = {"baseline": baseline, "variations": {}}

    for param_name, multipliers in PARAM_VARIATIONS.items():
        if param_name not in base_params:
            continue
        param_results = []
        for mult in multipliers:
            varied = {**base_params, param_name: base_params[param_name] * mult}
            try:
                result = await asyncio.to_thread(_run_sim, varied)
                param_results.append({
                    "multiplier": mult,
                    "value": round(base_params[param_name] * mult, 2),
                    "result": result
                })
            except Exception:
                pass
        sweep_results["variations"][param_name] = param_results

    return sweep_results


@router.post("/chat", response_model=AIChatResponse)
async def ai_race_engineer_chat(req: AIChatRequest):
    """
    AI Race Engineer endpoint.
    1. Parses the engineer's natural language problem.
    2. Runs real physics simulations across parameter variations.
    3. Uses Gemini to interpret results and generate specific recommendations.
    """
    # Use provided params or defaults
    base_params = DEFAULT_PARAMS.copy()
    if req.params:
        for k in DEFAULT_PARAMS:
            if k in req.params and req.params[k] is not None:
                try:
                    base_params[k] = float(req.params[k])
                except (TypeError, ValueError):
                    pass

    # Step 1: Run the physics sweep
    try:
        sweep = await _run_parameter_sweep(base_params)
        simulated = True
    except Exception as e:
        logger.warning("Physics sweep failed: %s", e)
        sweep = {}
        simulated = False

    # Step 2: Build the AI prompt with real simulation data
    params_desc = json.dumps(base_params, indent=2)
    sweep_desc = json.dumps(sweep, indent=2) if sweep else "(simulation unavailable)"

    prompt = f"""You are an expert vehicle dynamics engineer and AI race engineer assistant for SuspensionLab, a professional suspension simulation platform.

An engineer has described the following problem:
---
{req.problem}
---

Current suspension parameters:
{params_desc}

I have already run real physics simulations across parameter variations. Here are the results:
{sweep_desc}

Based on the engineer's problem and the ACTUAL simulation data above, provide a structured analysis.
Your response MUST be valid JSON in exactly this format:
{{
  "diagnosis": "One sentence describing what is wrong with the suspension",
  "root_cause": "Technical explanation of the physics root cause",
  "recommendations": [
    {{
      "parameter": "k_s",
      "current_value": 25000,
      "recommended_value": 20000,
      "change_pct": -20.0,
      "reason": "Why this specific change helps based on simulation data",
      "predicted_improvement": "e.g. Reduces body acceleration by 18%, improves comfort rating"
    }}
  ],
  "setup_summary": "A 2-3 sentence plain English summary of the recommended setup changes and expected outcome",
  "confidence": "High"
}}

Rules:
- Base ALL recommendations on the actual simulation data provided above
- Only recommend parameters where the simulation data shows genuine improvement
- Be specific with numbers — use exact values from the simulation sweep
- Confidence should be High if simulation data strongly supports the recommendation, Medium if the improvement is marginal, Low if the data is inconclusive
- Return ONLY the JSON object, no other text"""

    raw = await _call_gemini(prompt)

    # Clean up response — Gemini sometimes wraps JSON in markdown
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    import re
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if json_match:
        raw = json_match.group(0)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Gemini returned invalid JSON: %s\nRaw: %s", e, raw)
        raise HTTPException(status_code=502, detail="AI returned invalid response. Please try again.")

    # Validate and build response
    recommendations = [
        AIRecommendation(**r) for r in parsed.get("recommendations", [])[:5]  # Max 5
    ]

    return AIChatResponse(
        diagnosis=parsed.get("diagnosis", ""),
        root_cause=parsed.get("root_cause", ""),
        recommendations=recommendations,
        setup_summary=parsed.get("setup_summary", ""),
        confidence=parsed.get("confidence", "Medium"),
        simulated=simulated,
    )


@router.get("/health")
async def ai_health():
    """Check if AI Engineer is configured."""
    return {
        "configured": bool(GEMINI_API_KEY),
        "model": "gemini-1.5-flash",
        "cost": "free",
        "message": "Ready" if GEMINI_API_KEY else "Set GEMINI_API_KEY to activate AI Engineer"
    }

class OptimizeSetupRequest(BaseModel):
    goal: str
    current_params: dict

class OptimizeSetupResponse(BaseModel):
    m_s: float
    m_u: float
    k_s: float
    c: float
    k_t: float
    MR: float
    c_t: float
    explanation: str

@router.post("/optimize-setup", response_model=OptimizeSetupResponse)
async def optimize_setup(req: OptimizeSetupRequest):
    """
    Magic Wand endpoint: Takes the current suspension parameters and a user's natural language goal.
    Returns the exact numerical parameters to achieve that goal in a strict JSON format.
    """
    params_str = json.dumps(req.current_params, indent=2)
    prompt = f"""You are an expert vehicle dynamics optimization AI for SuspensionLab.
The engineer wants to achieve the following goal:
"{req.goal}"

Here are the current quarter-car suspension parameters:
{params_str}

Based on the goal, calculate the mathematically optimal new parameters. 
You must return your answer as a STRICT JSON object matching exactly this schema, with no markdown formatting, no code blocks, just raw JSON:
{{
  "m_s": float,
  "m_u": float,
  "k_s": float,
  "c": float,
  "k_t": float,
  "MR": float,
  "c_t": float,
  "explanation": "A 1-sentence explanation of why these specific changes satisfy the goal."
}}
"""
    raw_response = await _call_gemini(prompt)
    
    cleaned = raw_response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        return OptimizeSetupResponse(
            m_s=float(data.get("m_s", req.current_params.get("m_s", 300.0))),
            m_u=float(data.get("m_u", req.current_params.get("m_u", 35.0))),
            k_s=float(data.get("k_s", req.current_params.get("k_s", 25000.0))),
            c=float(data.get("c", req.current_params.get("c", 2050.0))),
            k_t=float(data.get("k_t", req.current_params.get("k_t", 200000.0))),
            MR=float(data.get("MR", req.current_params.get("MR", 0.85))),
            c_t=float(data.get("c_t", req.current_params.get("c_t", 0.0))),
            explanation=data.get("explanation", "Optimized parameters generated.")
        )
    except Exception as e:
        logger.error("Failed to parse Gemini JSON: %s. Raw: %s", e, raw_response)
        raise HTTPException(status_code=500, detail="AI failed to generate valid numerical parameters.")
