# SuspensionLab PRO — Phase 3F.1 Low-Pressure Map Audit
**Evaluation Timestamp:** 2026-09-26 02:25:36 UTC  
**Investigated Variants:** CF_C (Phase 3D Frozen Map: 15 bar -> 0.18) vs. CF_D (Refined Map: 15 bar -> 0.25)

---

## 1. Trade-Off Analysis: Transient RMSE vs. Exit Speed Bias

| Variant | Turn 5 $V_x$ RMSE | Turn 5 Final Speed Error | Peak Velocity Error | Cross-Sector Generalization |
| :--- | :---: | :---: | :---: | :--- |
| **CF_C (Production Map)** | `$2.487\text{ m/s}$` | **`$-0.066\text{ m/s}$` (Zero Bias)** | `$4.42\text{ m/s}$` | **PARITY / IMPROVED on all 5 sectors** |
| **CF_D (Refined Low-P)** | **`$1.518\text{ m/s}$`** | `$+\mathbf{1.054}\text{ m/s}$ (Biased)** | `$2.81\text{ m/s}$` | Over-brakes trail-braking exits |

### Findings:
1. **Transient Curve Fit vs Physical Integrity**:
   CF_D forces greater brake torque at $10-15\text{ bar}$, which matches the initial Turn 5 deceleration dip well (reducing RMSE to $1.518\text{ m/s}$). However, during trail-braking corner exit, it continues to over-retard the vehicle, introducing a **$+1.054\text{ m/s}$ exit speed deficit**.
2. **Evaluation Contamination**:
   The $0.25$ breakpoint in CF_D was selected specifically by calculating the demand at $14.3\text{ bar}$ in Turn 5 telemetry. This represents direct **evaluation contamination**.

### Architectural Decision:
> **CF_C IS PRESERVED AS THE SOLE PRODUCTION BASELINE.**  
> CF_D is rejected and classified as `NOT_GENERALIZED`. No post-hoc breakpoint adjustments will be accepted without independent calibration training sets.
