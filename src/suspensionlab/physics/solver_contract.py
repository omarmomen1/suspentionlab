"""
physics/solver_contract.py
==========================
SuspensionLab PRO — Numerical Solver Contracts & Diagnostics

Declares explicit numerical solver choices, integration tolerances,
step-size limits, stiffness handling, and convergence criteria across all physics domains.

Design Principles:
- Every solver selection has a documented engineering justification.
- Stiff systems (e.g. anti-dive kinematics, non-linear damper blow-off, tire relaxation lengths)
  explicitly mandate stiff implicit solvers (BDF / Radau) rather than explicit Runge-Kutta.
- Diagnostics (step count, function evaluations, LU factorizations, truncation error) are recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional


@dataclass(frozen=True)
class NumericalSolverContract:
    """Explicit contract and execution criteria for a numerical simulation solver."""
    model_family: str
    primary_solver: str
    fallback_solver: Optional[str]
    stiffness_regime: Literal["Non-Stiff", "Stiff", "Algebraic-Differential (DAE)", "Nonlinear Kinematic"]
    justification: str
    rtol: float
    atol: float
    max_step_s: float
    event_detection: bool
    failure_criteria: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


SOLVER_CONTRACTS: Dict[str, NumericalSolverContract] = {
    "quarter_car": NumericalSolverContract(
        model_family="quarter_car",
        primary_solver="RK45",
        fallback_solver="BDF",
        stiffness_regime="Non-Stiff",
        justification="Linear/mildly non-linear 2-DOF system with moderate damping ratios (0.2–0.8). Explicit Runge-Kutta 4(5) offers optimal execution speed; automatically falls back to implicit BDF if stiff bump stops or hydraulic hydraulic lock occur.",
        rtol=1e-6,
        atol=1e-8,
        max_step_s=0.001,
        event_detection=True,
        failure_criteria="Local truncation error exceeds atol + rtol*|y| over 5 consecutive step-halvings.",
    ),

    "half_car": NumericalSolverContract(
        model_family="half_car",
        primary_solver="BDF",
        fallback_solver="Radau",
        stiffness_regime="Stiff",
        justification="Wheelbase transport delay creates high-frequency phase shift between front and rear axles. Implicit Backward Differentiation Formulas (BDF, orders 1–5) provide A-stability and prevent numerical instability during rapid curb strikes.",
        rtol=1e-6,
        atol=1e-8,
        max_step_s=0.0005,
        event_detection=True,
        failure_criteria="Newton corrector fails to converge within 10 iterations per step.",
    ),

    "full_car": NumericalSolverContract(
        model_family="full_car",
        primary_solver="BDF",
        fallback_solver="Radau",
        stiffness_regime="Stiff",
        justification="7-DOF system with stiff anti-roll bars, asymmetric progressive damping, and high tire vertical stiffness (k_t >> k_s). Requires implicit stiff integrator with analytic or finite-difference Jacobian factorization.",
        rtol=1e-6,
        atol=1e-8,
        max_step_s=0.0005,
        event_detection=True,
        failure_criteria="Singular Jacobian or residual norm stagnation.",
    ),

    "kinematics": NumericalSolverContract(
        model_family="kinematics",
        primary_solver="Newton-Raphson Continuation",
        fallback_solver="Damped Trust-Region Newton",
        stiffness_regime="Nonlinear Kinematic",
        justification="Multibody spherical/revolute constraint equations solved along a continuous travel curve. Warm-started continuation from previous travel state provides rapid 2–5 iteration convergence with ColPivHouseholderQR rank protection.",
        rtol=1e-8,
        atol=1e-8,
        max_step_s=1.0,  # mm travel step
        event_detection=False,
        failure_criteria="QR rank deficiency (singular Jacobian), state out of domain (dx > 1e3), or max iterations reached.",
    ),

    "handling": NumericalSolverContract(
        model_family="handling",
        primary_solver="BDF",
        fallback_solver="LSODA",
        stiffness_regime="Stiff",
        justification="Relaxation length ODEs for tire forces and quasi-static load transfer relaxation introduce small time constants (tau ~ 0.05s) alongside slower yaw body dynamics (tau ~ 0.5s). Stiff BDF integration prevents artificial algebraic loops.",
        rtol=1e-6,
        atol=1e-8,
        max_step_s=0.002,
        event_detection=True,
        failure_criteria="Tire contact lost or state divergence.",
    ),

    "lap_sim": NumericalSolverContract(
        model_family="lap_sim",
        primary_solver="Forward-Backward GGV Envelope Integration",
        fallback_solver="Iterative Bisection Apex Solver",
        stiffness_regime="Non-Stiff",
        justification="Quasi-steady-state multi-point envelope solver with 4-wheel load transfer, combined-slip Pacejka tires, 4D aero coupling, engine torque curve, and 2026 ERS energy management.",
        rtol=1e-5,
        atol=1e-6,
        max_step_s=0.01,
        event_detection=True,
        failure_criteria="Apex speed solver divergence or non-physical negative velocity.",
    ),

    "fast_quasi_steady": NumericalSolverContract(
        model_family="fast_quasi_steady",
        primary_solver="Forward-Backward GGV Envelope Integration",
        fallback_solver="Iterative Bisection Apex Solver",
        stiffness_regime="Non-Stiff",
        justification="Fast quasi-steady-state solver (FAST_QUASI_STEADY) utilizing precomputed GGV envelopes and forward-backward velocity propagation.",
        rtol=1e-5,
        atol=1e-6,
        max_step_s=0.01,
        event_detection=True,
        failure_criteria="Apex speed solver divergence or non-physical negative velocity.",
    ),

    "dynamic_lap_sim": NumericalSolverContract(
        model_family="dynamic_lap_sim",
        primary_solver="Fixed-Step RK4 (1 kHz)",
        fallback_solver="Adaptive RK45 / BDF",
        stiffness_regime="Stiff",
        justification="High-fidelity 14-DOF transient multi-body vehicle dynamics ODE solver resolving planar translation/yaw, 7-DOF ride/pitch/roll, 4 unsprung corner vertical hops, 4 wheel spins, Pacejka MF 5.2 tire forces, aero ride-height coupling, powertrain gearbox shifts, and 2026 ERS thermodynamics.",
        rtol=1e-6,
        atol=1e-8,
        max_step_s=0.001,
        event_detection=True,
        failure_criteria="Wheel hop resonance divergence, numerical blowup, or state NaN.",
    ),

    "dynamic_transient_14dof": NumericalSolverContract(
        model_family="dynamic_transient_14dof",
        primary_solver="Fixed-Step RK4 (1 kHz)",
        fallback_solver="Adaptive RK45 / BDF",
        stiffness_regime="Stiff",
        justification="Canonical 14-DOF transient multi-body vehicle dynamics ODE solver.",
        rtol=1e-6,
        atol=1e-8,
        max_step_s=0.001,
        event_detection=True,
        failure_criteria="Wheel hop resonance divergence, numerical blowup, or state NaN.",
    ),
}


def get_solver_contract(model_family: str) -> NumericalSolverContract:
    """Retrieve the documented solver contract for any physics model."""
    if model_family not in SOLVER_CONTRACTS:
        available = ", ".join(sorted(SOLVER_CONTRACTS.keys()))
        raise KeyError(f"Unknown solver contract '{model_family}'. Available: {available}")
    return SOLVER_CONTRACTS[model_family]
