"""
physics/decision_engine.py
==========================
SuspensionLab PRO — Decision Consistency Engine

Unifies numerical optimization (L-BFGS-B) with heuristic engineering diagnostics.
Acts as the single source of truth for UI setup recommendations.
"""

from typing import Dict, Any
from suspensionlab.physics.quarter_car import QuarterCarResult

def _calculate_confidence(result: QuarterCarResult, opt_success: bool, status: str, params: Any = None) -> tuple[int, str]:
    """Computes a 0-100% confidence score based on physical compliance and heuristics."""
    if not opt_success:
        return 0, "Solver Failed to Converge"

    score = 100.0

    # 1. Hardware Architecture Penalty (The "Solid Axle" Rule)
    fn_ratio = getattr(result, "f_n_u", 0.0) / getattr(result, "f_n_s", 1e-9)
    mass_ratio = getattr(params, "m_u", 0.0) / getattr(params, "m_s", 1e-9) if params else 0.0
    
    if fn_ratio < 3.5 or mass_ratio > 0.4:
        score -= 40.0  # Massive penalty for fundamentally flawed hardware

    # 2. Heuristic Penalty
    if status == "CONFLICT":
        score -= 20.0

    # 3. Damping Sanity Penalty (Target ζ ≈ 0.35 to 0.45)
    zeta = getattr(result, "zeta_s", 0.0)
    if zeta < 0.25:
        score -= (0.25 - zeta) * 100.0  # Heavy penalty for severe underdamping
    elif zeta > 0.65:
        score -= (zeta - 0.65) * 50.0   # Moderate penalty for overdamping

    # 4. Travel Compliance Penalty (Target < 50mm)
    peak_travel_mm = getattr(result, "peak_susp_travel", 0.0) * 1000.0
    if peak_travel_mm > 50.0:
        score -= (peak_travel_mm - 50.0) * 0.5

    # 5. Transmissibility Penalty (Target < 2.0x amplification)
    pk_tx = getattr(result, "peak_transmissibility", 2.0)
    if pk_tx > 2.0:
        score -= (pk_tx - 2.0) * 10.0

    # Bound the score
    final_score = int(max(0, min(100, round(score))))

    # Assign Label
    if final_score >= 90:
        label = "Engineering Consensus"
    elif final_score >= 70:
        label = "Acceptable Compromise"
    else:
        label = "Solver/Reality Disagreement"

    return final_score, label


def generate_setup_verdict(result: QuarterCarResult, optimizer_output: Dict[str, Any], params: Any = None) -> Dict[str, Any]:
    opt_success = optimizer_output.get("success", False)
    
    if not opt_success:
        verdict = {
            "status": "FAILED",
            "headline": "OPTIMIZATION FAILED",
            "message": "The solver could not converge on a valid setup within the given constraints.",
            "action": "Relax maximum travel constraints or adjust objective weights."
        }
        score, label = _calculate_confidence(result, opt_success, verdict["status"], params)
        verdict.update({"score": score, "score_label": label})
        return verdict

    new_zeta = getattr(result, "zeta_s", None)
    if new_zeta is None:
        new_zeta = getattr(result, "metrics", {}).get("zeta_s", 0.0)
    peak_travel_mm = getattr(result, "peak_susp_travel", 0.0) * 1000.0
    fn_ratio = getattr(result, "f_n_u", 0.0) / getattr(result, "f_n_s", 1e-9)
    mass_ratio = getattr(params, "m_u", 0.0) / getattr(params, "m_s", 1e-9) if params else 0.0

    # Determine Base Status & Messages
    if mass_ratio > 0.4 or fn_ratio < 3.5:
        verdict = {
            "status": "CONFLICT",
            "headline": "CONFLICT DETECTED: HARDWARE ARCHITECTURE FLAW",
            "message": f"Optimizer forced a numerical solution, but the hardware is compromised. Unsprung mass ratio is extreme (m_u/m_s = {mass_ratio:.2f}) or modal separation is critically tight ({fn_ratio:.2f}x).",
            "action": "Reject setup. You are in solid-axle territory. You cannot fix this with damping alone. Physically reduce unsprung mass or significantly stiffen tire rate."
        }
    elif new_zeta > 0.65:
        verdict = {
            "status": "CONFLICT",
            "headline": "CONFLICT DETECTED: NUMERICAL VS. HEURISTIC",
            "message": "Optimization improved comfort numerically, but setup exceeds traditional damping guidelines.",
            "action": "Likely tradeoff between resonance suppression and sharp-input harshness. Accept for aero-platform stability; override and soften for road compliance."
        }
    elif new_zeta < 0.25:
        verdict = {
            "status": "CONFLICT",
            "headline": "CONFLICT DETECTED: ISOLATION VS. STABILITY",
            "message": f"Optimizer minimized RMS acceleration by dropping damping dangerously low (ζ = {new_zeta:.2f}).",
            "action": "Override solver. Increase rebound damping manually to maintain safe chassis control over crests."
        }
    elif peak_travel_mm > 75.0:
        verdict = {
            "status": "CONFLICT",
            "headline": "CONFLICT DETECTED: VIRTUAL VS. PHYSICAL LIMITS",
            "message": f"Optimizer achieved objective, but peak travel ({peak_travel_mm:.1f} mm) will likely strike physical bump stops.",
            "action": "Reject setup. Re-run optimizer with a stricter 'Max Allowed Travel' constraint."
        }
    else:
        verdict = {
            "status": "ALIGNED",
            "headline": "SETUP VERIFIED: UNIFIED AGREEMENT",
            "message": "Mathematical optimization perfectly aligns with established engineering heuristics.",
            "action": "Apply setup confidently. No conflicting diagnostics detected."
        }

    # Append Score (Now properly passing params!)
    score, label = _calculate_confidence(result, opt_success, verdict["status"], params)
    verdict.update({"score": score, "score_label": label})
    
    return verdict