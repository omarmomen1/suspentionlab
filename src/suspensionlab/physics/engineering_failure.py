"""
physics/engineering_failure.py
==============================
SuspensionLab PRO — Structured Engineering Failure Reporting

Replaces generic "Simulation failed" exceptions with high-fidelity, actionable
engineering diagnostic reports containing exact physical context, failing state vectors,
violated physical constraints, and recommended engineering remediations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EngineeringFailureReport:
    """Structured engineering diagnostic report generated upon solver or physical constraint failure."""
    error_code: str                   # e.g. "ERR_TIRE_CONTACT_LOSS"
    time_s: float                     # e.g. 3.82
    subsystem: str                    # e.g. "TIRE_FRONT_LEFT"
    human_message: str                # e.g. "Simulation stopped at t = 3.82 s: FL tire lost contact with road."
    constraint_violated: str          # e.g. "minimum normal load Fz >= 0 N"
    failing_state: Dict[str, float] = field(default_factory=dict) # {"wheel_travel_mm": 42.3, "fz_n": 0.0}
    suggested_actions: List[str] = field(default_factory=list)

    def to_markdown_callout(self) -> str:
        """Render a structured alert callout for UI or CLI display."""
        actions_list = "\n".join([f"  - {act}" for act in self.suggested_actions])
        state_list = ", ".join([f"`{k} = {v:.2f}`" for k, v in self.failing_state.items()])

        return (
            f"### ⚠️ Engineering Simulation Failure: `{self.error_code}`\n"
            f"**Time**: `t = {self.time_s:.2f} s` | **Subsystem**: `{self.subsystem}`\n\n"
            f"> **Issue**: {self.human_message}\n\n"
            f"- **Constraint Violated**: `{self.constraint_violated}`\n"
            f"- **Last Valid Physical State**: {state_list if state_list else 'N/A'}\n\n"
            f"**Recommended Engineering Remediations**:\n"
            f"{actions_list}\n"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "time_s": round(self.time_s, 4),
            "subsystem": self.subsystem,
            "human_message": self.human_message,
            "constraint_violated": self.constraint_violated,
            "failing_state": self.failing_state,
            "suggested_actions": self.suggested_actions,
        }


def create_tire_liftoff_failure(time_s: float, corner: str = "FL", travel_mm: float = 42.3) -> EngineeringFailureReport:
    """Helper factory for tire contact loss failure."""
    return EngineeringFailureReport(
        error_code="ERR_TIRE_CONTACT_LOSS",
        time_s=time_s,
        subsystem=f"TIRE_{corner}",
        human_message=f"Simulation stopped at t = {time_s:.2f} s: {corner} tire lost physical contact with track surface.",
        constraint_violated="unilateral normal load constraint Fz >= 0 N",
        failing_state={"wheel_travel_mm": travel_mm, "normal_load_n": 0.0},
        suggested_actions=[
            "Increase available bump/droop travel by adjusting static ride height.",
            "Reduce high-speed rebound damping to allow wheel to track road undulations.",
            "Soften anti-roll bar to reduce lateral load transfer across axle.",
        ],
    )


def create_damper_bottoming_failure(time_s: float, corner: str = "RR", max_travel_mm: float = 55.0) -> EngineeringFailureReport:
    """Helper factory for damper stroke bottoming."""
    return EngineeringFailureReport(
        error_code="ERR_DAMPER_BOTTOMING",
        time_s=time_s,
        subsystem=f"DAMPER_{corner}",
        human_message=f"Simulation stopped at t = {time_s:.2f} s: {corner} damper reached metal-to-metal bump stop limit ({max_travel_mm:.1f} mm).",
        constraint_violated=f"damper stroke <= {max_travel_mm:.1f} mm",
        failing_state={"damper_deflection_mm": max_travel_mm, "bump_stop_force_n": 18500.0},
        suggested_actions=[
            "Increase primary wheel spring rate (kN/m) to support aerodynamic downforce.",
            "Install stiffer progressive bump rubbers to cushion final 10 mm of stroke.",
            "Raise static ride height to provide additional compression clearance.",
        ],
    )
