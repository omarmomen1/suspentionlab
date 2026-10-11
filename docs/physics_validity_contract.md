# SuspensionLab PRO — Physics Validity & Provenance Contract

**Document Classification:** Architecture Specification & Scientific Integrity Contract  
**Version:** 3.0.0-Enterprise  
**Status:** **ACTIVE CONTRACT**

---

## 1. Executive Summary

This document formalizes the **Physics Validity & Provenance Contract** governing all mathematical solvers, multi-physics simulations, and empirical telemetry calibration pipelines in SuspensionLab PRO.

Every physics output object must carry an unambiguous statement of its epistemic validity, valid parameter domain, underlying assumptions, and data provenance.

### The Non-Silent Degradation Law
> **Fundamental Architectural Invariant:**  
> A downstream module **MUST NOT** silently convert `UNSUPPORTED`, `EXTRAPOLATED`, `NUMERICALLY_FAILED`, or `UNIDENTIFIABLE` input into `MODEL_SUPPORTED` or `EMPIRICALLY_VALIDATED` output. Any degraded upstream validity state must propagate through all downstream pipelines and display blocking engineering warnings.

---

## 2. The 8 Epistemic Validity States

| Validity State | Semantic Meaning | Required Evidence | Permitted Downstream Actions |
| :--- | :--- | :--- | :--- |
| `SIMULATION_ESTIMATE` | Theoretical forward physics prediction using nominal/uncalibrated parameters. | Numerical solver convergence (`residual < tol`). | Exploratory setup sweeps, DOE exploration. |
| `MODEL_SUPPORTED` | Operating strictly within calibrated boundaries and verified physics assumptions. | Parameter bounds check (`norm_min <= p <= norm_max`) and non-extrapolated kinematics. | Optimization target, automated tuning. |
| `CORRELATED` | Model outputs correlate with external reference data or independent simulation benchmarks ($R^2 \ge 0.70$). | Verified holdout validation or cross-model benchmark comparison. | Setup refinement, engineering reports. |
| `EMPIRICALLY_VALIDATED` | Verified against genuine physical vehicle sensors (accelerometers, strain gauges, damper pots). | Calibrated against authentic logged track telemetry with holdout verification ($R^2 \ge 0.85$). | Race strategy, sign-off for track execution. |
| `UNSUPPORTED` | Physical phenomenon or configuration is outside model mechanics (e.g. cornering roll in 7-DOF ride model). | Detected omission of necessary degrees of freedom or governing forces. | **BLOCKING:** Excluded from optimization and decisions. |
| `EXTRAPOLATED` | Input parameters operate beyond calibrated wind-tunnel or dyno bounds (e.g. front ride height $< 20\text{ mm}$). | Parameter bounds violation check. | **BLOCKING:** Display advisory/blocking warning; penalize in optimizer. |
| `NUMERICALLY_FAILED` | ODE non-convergence, singular matrix inversion, NaN/Inf detected, or line-search abort. | Solver status code $\ne 0$ or infinite residual norm. | **HALT:** Raise `MathConvergenceError`; reject run artifact. |
| `UNIDENTIFIABLE` | Logged telemetry lacks persistent dynamic excitation or observability to uniquely deduce parameters. | Fisher Information condition number $> 10^5$, flat signal ($\sigma < 10^{-4}$), or orthogonal target. | **RETAIN PRIORS:** Abort parameter updates; delta = 0.0%; confidence = 0.0. |

---

## 3. Metadata & Provenance Data Schema

Every simulation result is packaged with a `PhysicsValidityRecord`:

```json
{
  "status": "MODEL_SUPPORTED",
  "is_valid": true,
  "model": "CoupledVehicleModel-2026",
  "assumptions": [
    "Quasi-steady load transfer with 0.05s compliance relaxation delay",
    "Pacejka MF 5.2 Similarity Method combined slip",
    "Front ride height >= 20.0 mm (aerodynamic stall not modeled below 20 mm)"
  ],
  "valid_parameter_domain": {
    "ride_height_front_mm": [20.0, 100.0],
    "ride_height_rear_mm": [25.0, 120.0],
    "speed_mps": [5.0, 95.0]
  },
  "extrapolation_status": false,
  "validation_evidence": "Closed-loop equilibrium converged in 8 iterations (residual = 0.021 mm)",
  "data_provenance": {
    "software_build": "SuspensionLab-PRO-v3.0.0-enterprise",
    "parameter_hash": "a4f8c92b10de43e1",
    "session_id": "SES-SPA-2026-B819"
  },
  "warnings": [],
  "upstream_validity_state": "MODEL_SUPPORTED"
}
```

---

## 4. Subsystem Validity Domains

### 1. Parameter Identification (`parameter_identification.py`)
- **Valid Channel Sources:** Physical damper travel displacement (`Damper_FL`), suspension potentiometer logs, genuine accelerometers.
- **Forbidden Practices:** Fabricating synthetic vertical channels from lateral acceleration (`LatAcc * 0.35 + 1.0`).
- **Required Exit Status:** Must emit `IDENTIFIABLE`, `PARTIALLY_IDENTIFIABLE`, `UNIDENTIFIABLE`, or `CALIBRATION_FAILED`.

### 2. Longitudinal Wheel Dynamics (`wheel_dynamics.py` / `handling_model.py`)
- **Governing Law:** Wheel angular velocity must be dynamically integrated via torque equilibrium:
  $$I_w \frac{d\omega}{dt} = T_{\text{drive}} - T_{\text{brake}} - F_x R_w$$
- **Forbidden Practices:** Imposing slip ratio $\kappa$ directly from throttle/brake pedal percentages.
- **Singularity Protection:** $\kappa = \frac{R_w \omega - V_x}{\max(|V_x|, \epsilon)}$ with low-speed velocity blend.

### 3. Aerodynamic Platform Coupling (`suspension_aero_coupling.py`)
- **Hard Domain Boundary:** Minimum front ride height $RH_f \ge 20.0\text{ mm}$.
- **Boundary Violation:** If dynamic downforce squashes front ride height below $20\text{ mm}$, state is marked `EXTRAPOLATED` or `UNSUPPORTED`, `is_valid` is set to `False`, and a blocking warning is emitted to prevent optimizers from collapsing to unphysical zero-ride-height states.

### 4. 7-DOF Ride Model (`full_car.py`)
- **Scope Restriction:** Strictly a **7-DOF Vertical Ride Model** for 4-post shaker rigs and road elevation profiles.
- **Forbidden Claims:** Must not be marketed or utilized for lateral cornering roll angles or roll stiffness distribution under lateral acceleration $a_y$ (produces 100% error).

### 5. Quarter-Car Model (`quarter_car.py`)
- **Linear Domain:** Suspension travel within linear range ($\Delta z < 35\text{ mm}$).
- **Nonlinear Extension:** Progressive bump stops ($F_{bump} = k_0 (\exp(\beta \Delta z) - 1)$) must be configured when evaluating curb strikes or tall step obstacles.
