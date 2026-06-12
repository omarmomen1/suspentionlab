"""
analytics/race_engineer.py
==========================
SuspensionLab PRO — Race Engineer Recommendation Engine

This module acts as an automated setup engineer. It ingests the raw 
QuarterCarResult simulation data and applies deterministic, rule-based 
diagnostics to output actionable tuning recommendations.

Architecture:
- Pure functions only.
- No UI or plotting dependencies.
- Extensible rule sets for continuous improvement.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any

# Assuming QuarterCarResult is available in your physics module.
# Adjust the import path if necessary based on your exact structure.
from suspensionlab.physics.quarter_car import QuarterCarResult


class Severity(Enum):
    INFO = "INFO"           # General setup notes, optimal conditions
    WARNING = "WARNING"     # Sub-optimal performance, worth investigating
    CRITICAL = "CRITICAL"   # Dangerous or highly detrimental setup behavior


@dataclass
class Recommendation:
    category: str
    diagnosis: str
    finding: str
    action: str
    severity: Severity
    confidence: float  # 0.0 to 1.0


@dataclass
class RaceEngineerReport:
    recommendations: List[Recommendation] = field(default_factory=list)
    
    @property
    def has_critical(self) -> bool:
        return any(r.severity == Severity.CRITICAL for r in self.recommendations)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the report for API or JSON export."""
        return {
            "critical_flags": self.has_critical,
            "recommendations": [
                {
                    "category": r.category,
                    "severity": r.severity.value,
                    "diagnosis": r.diagnosis,
                    "finding": r.finding,
                    "action": r.action,
                    "confidence": round(r.confidence, 2)
                }
                for r in self.recommendations
            ]
        }


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostic Rule Engines (Pure Functions)
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_damping(r: QuarterCarResult) -> List[Recommendation]:
    """Diagnoses the sprung mass damping ratio (zeta_s)."""
    recs = []
    
    if r.zeta_s < 0.20:
        recs.append(Recommendation(
            category="DAMPING",
            diagnosis="Critically Underdamped Suspension",
            finding=f"Damping ratio is severely low (ζ = {r.zeta_s:.3f}). High risk of uncontrolled oscillation.",
            action="Increase rebound damping significantly (approx. +40-50%).",
            severity=Severity.CRITICAL,
            confidence=0.95
        ))
    elif r.zeta_s < 0.28:
        recs.append(Recommendation(
            category="DAMPING",
            diagnosis="Underdamped Suspension",
            finding=f"Damping ratio is below the typical optimal window (ζ = {r.zeta_s:.3f}).",
            action="Increase rebound damping by 2-3 clicks or ~15%.",
            severity=Severity.WARNING,
            confidence=0.85
        ))
    elif r.zeta_s > 0.85:
        recs.append(Recommendation(
            category="DAMPING",
            diagnosis="Overdamped Suspension",
            finding=f"Damping ratio is too high (ζ = {r.zeta_s:.3f}). Suspension will feel harsh and 'pack down' over rapid bumps.",
            action="Decrease overall damping (especially compression) to return to ζ ≈ 0.4 - 0.6.",
            severity=Severity.WARNING,
            confidence=0.90
        ))
    else:
        recs.append(Recommendation(
            category="DAMPING",
            diagnosis="Optimal Damping",
            finding=f"Damping ratio (ζ = {r.zeta_s:.3f}) is within the target operating window.",
            action="No immediate damping changes required.",
            severity=Severity.INFO,
            confidence=0.98
        ))
        
    return recs


def _analyze_comfort_and_acceleration(r: QuarterCarResult) -> List[Recommendation]:
    """Diagnoses ride comfort based on RMS body acceleration (ISO 2631)."""
    recs = []
    
    if r.rms_body_accel_wk > 1.5:
        recs.append(Recommendation(
            category="RIDE COMFORT",
            diagnosis="Severe Ride Harshness",
            finding=f"RMS Body Acceleration ({r.rms_body_accel_wk:.2f} m/s²) exceeds ISO limits for comfort.",
            action="Soften spring rate (ks) and reduce high-speed compression damping.",
            severity=Severity.CRITICAL,
            confidence=0.95
        ))
    elif r.rms_body_accel_wk > 0.8:
        recs.append(Recommendation(
            category="RIDE COMFORT",
            diagnosis="Elevated Ride Harshness",
            finding=f"RMS Body Acceleration ({r.rms_body_accel_wk:.2f} m/s²) is slightly uncomfortable.",
            action="Consider a slight reduction in spring rate or softening compression damping if ride quality is prioritized over platform support.",
            severity=Severity.WARNING,
            confidence=0.80
        ))
        
    return recs


def _analyze_suspension_travel(r: QuarterCarResult) -> List[Recommendation]:
    """Diagnoses physical packaging limits based on suspension travel."""
    recs = []
    peak_travel_mm = r.peak_susp_travel * 1000.0
    
    if peak_travel_mm > 75.0:
        recs.append(Recommendation(
            category="PACKAGING",
            diagnosis="Excessive Suspension Travel (Bottoming Risk)",
            finding=f"Peak travel is very high ({peak_travel_mm:.1f} mm). High probability of striking bump stops.",
            action="Increase spring rate (ks), increase low-speed compression damping, or install progressive bump stops.",
            severity=Severity.CRITICAL,
            confidence=0.90
        ))
    elif peak_travel_mm < 15.0:
        recs.append(Recommendation(
            category="PACKAGING",
            diagnosis="Underutilized Suspension Stroke",
            finding=f"Peak travel is very low ({peak_travel_mm:.1f} mm). Suspension is overly stiff for this road profile.",
            action="Soften spring rate to improve mechanical grip and ride quality.",
            severity=Severity.WARNING,
            confidence=0.75
        ))
        
    return recs


def _analyze_modal_coupling(r: QuarterCarResult) -> List[Recommendation]:
    """Diagnoses wheel-hop and frequency overlap issues."""
    recs = []
    
    # Avoid division by zero
    if r.f_n_s <= 0:
        return recs
        
    ratio = r.f_n_u / r.f_n_s
    
    if ratio < 2.5:
        recs.append(Recommendation(
            category="DYNAMICS",
            diagnosis="Severe Modal Coupling (Wheel Hop Risk)",
            finding=f"Sprung/Unsprung frequency separation is poor (Ratio = {ratio:.2f}x). Sprung mass movements are driving unsprung mass resonance.",
            action="Reduce unsprung mass (lighter wheels/brakes) or increase tire stiffness (kt).",
            severity=Severity.CRITICAL,
            confidence=0.92
        ))
    elif ratio < 3.2:
        recs.append(Recommendation(
            category="DYNAMICS",
            diagnosis="Marginal Frequency Separation",
            finding=f"Frequency separation (Ratio = {ratio:.2f}x) is below the ideal >3.5x target.",
            action="Monitor wheel hop. Marginal gains possible by reducing unsprung mass.",
            severity=Severity.WARNING,
            confidence=0.85
        ))
        
    return recs


def _analyze_transmissibility(r: QuarterCarResult) -> List[Recommendation]:
    """Diagnoses frequency-domain transmissibility peaks."""
    recs = []
    
    if r.peak_transmissibility > 2.8:
        recs.append(Recommendation(
            category="FREQUENCY RESPONSE",
            diagnosis="High Resonance Amplification",
            finding=f"Peak transmissibility is {r.peak_transmissibility:.2f}x at {r.freq_at_peak_tx:.2f} Hz. Severe amplification at resonance.",
            action="Increase damping (c) to control the resonant peak.",
            severity=Severity.WARNING,
            confidence=0.88
        ))
        
    return recs

def _analyze_compound_issues(r: QuarterCarResult) -> List[Recommendation]:
    """Catches contradictions and combined physical phenomena."""
    recs = []
    peak_travel_mm = r.peak_susp_travel * 1000.0
    
    # Compound Rule 1: Bottoming Out Induced Harshness
    if r.rms_body_accel_wk > 1.5 and peak_travel_mm > 75.0:
        recs.append(Recommendation(
            category="SYSTEM CONFLICT",
            diagnosis="Bottoming-Induced Harshness",
            finding=f"Severe harshness ({r.rms_body_accel_wk:.2f} m/s²) combined with massive travel ({peak_travel_mm:.1f} mm). The harshness is caused by the suspension violently bottoming out, NOT by the springs being too stiff.",
            action="IGNORE standard comfort advice. Do NOT soften springs. You must stop the bottoming first: Increase spring rate (ks), increase high-speed compression damping, or install stiffer progressive bump stops.",
            severity=Severity.CRITICAL,
            confidence=0.98
        ))
        
    return recs

# ─────────────────────────────────────────────────────────────────────────────
# Main Engine Entry Point
# ─────────────────────────────────────────────────────────────────────────────
def generate_race_engineer_report(result: QuarterCarResult) -> RaceEngineerReport:
    """
    Ingests simulation results and runs diagnostic rule engines.
    Uses conflict resolution to suppress contradictory advice.
    """
    report = RaceEngineerReport()
    
    # 1. Run Compound Rules First
    compound_recs = _analyze_compound_issues(result)
    report.recommendations.extend(compound_recs)
    
    # Check if the specific "Bottoming-Induced Harshness" rule fired
    bottoming_conflict = any(r.diagnosis == "Bottoming-Induced Harshness" for r in compound_recs)
    
    # 2. Run universal rules
    report.recommendations.extend(_analyze_damping(result))
    report.recommendations.extend(_analyze_modal_coupling(result))
    report.recommendations.extend(_analyze_transmissibility(result))
    
    # 3. Conditionally run isolated rules (Suppress if there is a conflict)
    if not bottoming_conflict:
        report.recommendations.extend(_analyze_comfort_and_acceleration(result))
        report.recommendations.extend(_analyze_suspension_travel(result))
        
    # Sort recommendations by severity (CRITICAL first)
    severity_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
    report.recommendations.sort(key=lambda x: severity_order[x.severity])
    
    return report