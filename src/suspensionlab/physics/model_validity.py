"""
physics/model_validity.py
=========================
SuspensionLab PRO — Model Validity & Confidence Engine

Every simulation result carries an honest statement of how much the engineer
should trust it. This module computes a 0-100 confidence score plus a
human-readable checklist of what was validated, what is missing, and what is
outright unsupported by the current model.

Design principles
-----------------
* Never pretend all simulations are equally trustworthy.
* Checks are weighted: a missing damper dyno curve costs more than a missing
  optional telemetry correlation.
* The score is deterministic given the same inputs — no hidden randomness.
* Each check explains itself so the UI can render "why 82%?".

Usage
-----
    report = assess_quarter_car(params_dict, has_damper_curve=False)
    report.score        # 82.0
    report.band         # "High" | "Medium" | "Low"
    report.checks       # list of ValidityCheck(label, status, detail, weight)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

CheckStatus = Literal["pass", "warn", "fail"]


@dataclass
class ValidityCheck:
    """One line in the MODEL VALIDITY checklist."""
    label:   str
    status:  CheckStatus
    detail:  str
    weight:  float = 1.0   # relative importance (0-1]; used for score weighting

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "status": self.status,
                "detail": self.detail, "weight": self.weight}


@dataclass
class ModelValidityReport:
    """Aggregated validity assessment for one simulation run."""
    model:    str = "quarter_car"
    score:    float = 0.0                 # 0-100
    band:     Literal["High", "Medium", "Low"] = "Low"
    checks:   list[ValidityCheck] = field(default_factory=list)
    summary:  str = ""

    def finalize(self) -> "ModelValidityReport":
        """Compute weighted score and band from the check list."""
        if not self.checks:
            self.score = 0.0
            self.band = "Low"
            return self
        total_w = sum(c.weight for c in self.checks)
        earned = sum(
            c.weight * {"pass": 1.0, "warn": 0.5, "fail": 0.0}[c.status]
            for c in self.checks
        )
        self.score = round(100.0 * earned / total_w, 1) if total_w > 0 else 0.0
        self.band = "High" if self.score >= 80 else ("Medium" if self.score >= 55 else "Low")
        n_pass = sum(1 for c in self.checks if c.status == "pass")
        n_warn = sum(1 for c in self.checks if c.status == "warn")
        n_fail = sum(1 for c in self.checks if c.status == "fail")
        self.summary = (f"{n_pass} validated, {n_warn} warnings, {n_fail} unsupported. "
                        f"Interpret results with {self.band.lower()} confidence.")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "score": self.score,
            "band": self.band,
            "summary": self.summary,
            "checks": [c.to_dict() for c in self.checks],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Quarter-car / half-car ride model assessment
# ─────────────────────────────────────────────────────────────────────────────

def _check_parameter_ranges(params: dict[str, float]) -> ValidityCheck:
    """Validate masses/stiffness/damping against physically sensible ranges."""
    ranges = {
        "m_s": (50.0, 2000.0, "sprung mass [kg]"),
        "m_u": (10.0, 300.0, "unsprung mass [kg]"),
        "k_s": (5_000.0, 500_000.0, "spring rate [N/m]"),
        "c":   (0.0, 50_000.0, "damping coefficient [Ns/m]"),
        "k_t": (50_000.0, 1_500_000.0, "tire vertical stiffness [N/m]"),
        "MR":  (0.3, 1.5, "motion ratio [-]"),
    }
    problems: list[str] = []
    checked = 0
    for key, (lo, hi, desc) in ranges.items():
        if key not in params or params[key] is None:
            continue
        checked += 1
        v = float(params[key])
        if not (lo <= v <= hi):
            problems.append(f"{key}={v:g} outside {desc} range [{lo:g}, {hi:g}]")
    if checked == 0:
        return ValidityCheck("Vehicle parameters validated", "warn",
                             "No parameters supplied — defaults assumed.", 1.0)
    if problems:
        return ValidityCheck("Vehicle parameters validated", "fail",
                             "; ".join(problems), 1.0)
    return ValidityCheck("Vehicle parameters validated", "pass",
                         f"All {checked} parameters within physical ranges.", 1.0)


def _check_damper_data(params: dict[str, Any]) -> ValidityCheck:
    has_split = params.get("damper_curve_v_comp") and params.get("damper_curve_f_comp")
    has_unified = params.get("damper_curve_v") and params.get("damper_curve_f")
    if has_split or has_unified:
        return ValidityCheck("Damper dyno data", "pass",
                             "Nonlinear damper curve supplied; frequency domain uses "
                             "energy-equivalent linearisation.", 1.0)
    return ValidityCheck("Damper dyno data", "warn",
                         "No dyno curve — constant linear damping c assumed. "
                         "Compression/rebound asymmetry is not captured.", 1.0)


def _check_tire_damping(params: dict[str, float]) -> ValidityCheck:
    c_t = float(params.get("c_t") or 0.0)
    if c_t > 0:
        return ValidityCheck("Tire damping model", "pass",
                             f"Tire damping c_t={c_t:g} Ns/m included.", 0.5)
    return ValidityCheck("Tire damping model", "warn",
                         "Tire structural damping not specified (c_t=0); "
                         "wheel-hop resonance may be over-predicted.", 0.5)


def _check_telemetry_correlation(correlation: Optional[float]) -> ValidityCheck:
    if correlation is None:
        return ValidityCheck("Telemetry correlation", "warn",
                             "No telemetry uploaded — model is uncorrelated with a real car.", 1.0)
    pct = correlation * 100.0
    if pct >= 85:
        return ValidityCheck("Telemetry correlation", "pass",
                             f"Model-to-telemetry correlation: {pct:.0f}%.", 1.0)
    if pct >= 60:
        return ValidityCheck("Telemetry correlation", "warn",
                             f"Model-to-telemetry correlation: {pct:.0f}% — calibration recommended.", 1.0)
    return ValidityCheck("Telemetry correlation", "fail",
                         f"Model-to-telemetry correlation: {pct:.0f}% — model does not "
                         f"represent this vehicle.", 1.0)


def assess_quarter_car(
    params: dict[str, Any],
    telemetry_correlation: Optional[float] = None,
) -> ModelValidityReport:
    """Assess how trustworthy a quarter/half-car ride simulation is."""
    report = ModelValidityReport(model="quarter_car")
    report.checks.append(_check_parameter_ranges(params))
    report.checks.append(_check_damper_data(params))
    report.checks.append(_check_tire_damping(params))
    report.checks.append(_check_telemetry_correlation(telemetry_correlation))
    report.checks.append(ValidityCheck(
        "Nonlinear kinematics", "fail",
        "Ride model uses constant motion ratio — no camber/roll-center migration "
        "with travel. Run the Kinematics module for geometry effects.", 0.5,
    ))
    return report.finalize()


# ─────────────────────────────────────────────────────────────────────────────
# Lap-sim assessment
# ─────────────────────────────────────────────────────────────────────────────

def assess_lap_sim(
    vehicle_params: dict[str, Any],
    telemetry_correlation: Optional[float] = None,
) -> ModelValidityReport:
    """Assess the quasi-steady-state lap simulator's trustworthiness."""
    report = ModelValidityReport(model="lap_sim")

    # Aero map
    cl = vehicle_params.get("cl") or vehicle_params.get("cl_a")
    if cl:
        report.checks.append(ValidityCheck(
            "Aero map", "pass",
            "Downforce/drag map present (ride-height sensitive).", 1.0))
    else:
        report.checks.append(ValidityCheck(
            "Aero map", "warn",
            "No aero map — grip levels on fast corners will be under-predicted.", 1.0))

    # Tire model
    report.checks.append(ValidityCheck(
        "Tire model", "pass",
        "Pacejka Magic Formula with combined-slip GGV envelope.", 1.0))

    # Tire thermal
    if vehicle_params.get("tire_thermal"):
        report.checks.append(ValidityCheck(
            "Tire temperature", "pass", "Thermal model active — µ scaled by temperature.", 0.5))
    else:
        report.checks.append(ValidityCheck(
            "Tire temperature", "warn",
            "No thermal model — cold/warm-up effects on grip are ignored.", 0.5))

    # Powertrain
    if vehicle_params.get("powertrain"):
        report.checks.append(ValidityCheck(
            "Powertrain", "pass", "Gearbox + torque curve model active.", 0.5))
    else:
        report.checks.append(ValidityCheck(
            "Powertrain", "fail", "No powertrain model — straight-line speeds unreliable.", 0.5))

    # Transient behaviour
    report.checks.append(ValidityCheck(
        "Transient dynamics", "warn",
        "Quasi-steady-state solver — combined entry/exit transients, "
        "differential and brake bias effects are not modelled.", 1.0))

    report.checks.append(_check_telemetry_correlation(telemetry_correlation))
    return report.finalize()
