# SUSPENSIONLAB PRO — PHASE 3C.1 VALIDATION INTEGRITY REPORT

## 1. Executive Result

**AUDIT VERDICT**: **`PASS WITH FINDINGS`**

- **Integrity Baseline**: Re-evaluated with **100% frozen physics equations**.
- **Evidence Cleanliness**: Input independence verified; zero hidden ground-truth feedback discovered in fully blind execution.
- **Findings Identified**: 3 major narrative claim contradictions detected where Phase 3C text over-generalized speed-conditioned cornering results to all fully blind maneuvers. All claims have been mechanically reconciled with numerical ground truth.
- **Phase 3D Gate**: **`AUTHORIZED`** for controlled physics experiments in Phase 3D under strict hypotheses.

---

## 2. Frozen Baseline Provenance

- **Git Commit SHA**: `fbe3d045762d8c216922630ca5c3b0da1d589a31` (Branch: `master`)
- **Physics Model Version**: `dynamic-transient-14dof-v3.2` (`src/suspensionlab/physics/dynamic_lap_sim.py`)
- **Dataset**: Stanford University Dynamic Design Lab — *Vehicle Dynamics Dataset for Highly Dynamic Automated Driving* (DOI: [10.25740/hh613qz0317](https://doi.org/10.25740/hh613qz0317))
- **Dataset SHA-256**: `489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3` (16,934,088 bytes)
- **Validation Script SHA-256**: `5177bcf1c36f797f3acda6c90fdcacce097b04f95d9ea6c69abce5f3d5a8d098`
- **Regression Test Baseline**: `11 passed in 25.37s` (`tests/test_real_vehicle_dynamics_and_lap_sim.py`)

---

## 3. Input Independence Result

Every simulated output was audited against potential ground-truth contamination:

| Output Quantity | Blind Mode | Conditioned Mode | Contaminated? | Scientific Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Yaw Rate ($r$)** | FULLY BLIND | PARTIALLY CONDITIONED | **NO** | Driven by steering & tire forces; $r_{meas}$ never injected during simulation. |
| **Chassis Roll ($\phi$)** | FULLY BLIND | PARTIALLY CONDITIONED | **NO** | $\phi_{meas}$ used only for $t=0$ mount tilt alignment; evolves via sprung roll moment. |
| **Suspension ($z_{FL..RL}$)**| FULLY BLIND | PARTIALLY CONDITIONED | **NO** | Measured potentiometer displacements never enter force equations or state updates. |
| **Wheel Speeds ($\omega_i$)**| FULLY BLIND | PARTIALLY CONDITIONED | **NO (in Blind)** | Evolves from wheel rotational torque balance ($I_w \dot{\omega} = T_d - T_b - F_x R_w$). |
| **Forward Speed ($V_x$)** | FULLY BLIND | DIRECTLY FORCED | **NO (in Blind)** | Mode 2 directly forces $u = V_{x,meas}$ at each step; correctly documented as Conditioned. |
| **Accelerations ($a_x, a_y$)**| FULLY BLIND | PARTIALLY CONDITIONED | **NO** | Kinematic accelerations derived from $\dot{u} - rv$ and $\dot{v} + ru$; IMU not injected. |
| **Trajectory ($E, N$)** | FULLY BLIND | PARTIALLY CONDITIONED | **NO** | Open-loop integration from initial coordinates; zero GPS position resets during replay. |

---

## 4. Claim Consistency Audit (Contradictions Reconciled)

The automated consistency audit discovered 3 narrative contradictions in Phase 3C:

1. **Yaw Rate Generalization Contradiction**:
   - *Phase 3C Claim*: $R^2 \ge 0.938$ across all 5 independent holdouts.
   - *Audit Finding*: $R^2 \ge 0.938$ occurred in **Speed-Conditioned mode** on cornering holdouts (Turn 4 $R^2 = 0.948$, Turn 3 $R^2 = 0.959$, Turn 1 calibrated $R^2 = 0.983$). In **Fully Blind mode**, Turn 1 reversal achieved $R^2 = 0.3957$ and Heavy Braking achieved $R^2 = 0.0599$.
   - *Resolution*: Epistemic validation is restricted to Speed-Conditioned cornering (70–110 km/h). Fully blind transient reversal is classified as `CORRELATED`.
2. **Open-Loop Trajectory Drift Contradiction**:
   - *Phase 3C Claim*: Open-loop drift $\le 6.2\%$ across all maneuvers.
   - *Audit Finding*: True for cornering maneuvers (Turn 1: 4.28%, Turn 4: 5.10%, Turn 3: 6.23%), but demonstrably false for Heavy Braking (25.27%) and Acceleration Launch (17.82%).
   - *Resolution*: Trajectory correlation is bounded strictly to cornering maneuvers up to 8.0 s. Longitudinal maneuvers are designated `DRIFT_SENSITIVE`.
3. **Roll Variance Normalization Contradiction**:
   - *Phase 3C Claim*: Roll $R^2 \ge 0.915$ across holdouts.
   - *Audit Finding*: In Fully Blind mode, Roll $R^2$ was negative on straightline braking and Turn 1 reversal due to near-zero denominator variance, despite strong correlation ($r = 0.90 - 0.98$).
   - *Resolution*: Classify roll dynamics as empirically validated in cornering where dynamic roll angle exceeds $1.0^\circ$.

---

## 5. Calibration Provenance

Parameters identified during Phase 3 are formally classified:
- **$s_{tire} = 1.3161$**: `IDENTIFIED_MODEL_CALIBRATION` (not measured tire stiffness; identified via residual minimization on Turn 1).
- **$s_{susp} = 0.9807$**: `IDENTIFIED_MODEL_CALIBRATION` (identified via roll angle residual minimization).
- **$k_\delta = 0.000451	ext{ rad}/(	ext{m/s}^2)$**: `IDENTIFIED_MODEL_CALIBRATION` (linear steering compliance).
- **$\phi_{bias} = -1.68^\circ$**: `IDENTIFIED_SENSOR_BIAS` (IMU body mounting tilt).
- **$R_w = 0.3198	ext{ m}$**: `KINEMATICALLY_DERIVED_MEASUREMENT` (derived from unpowered rear wheel speed ratio).
- **$z0_{FL}, z0_{FR}, z0_{RL}$**: `IDENTIFIED_SENSOR_DATUM` (static ride height potentiometers).

---

## 6. Residual Isolation Findings

Parameter perturbation experiments confirm the following physical relationships:
1. **Tire Cornering Stiffness**: Multipliers between 0.85 and 1.15 shift Turn 4 yaw rate RMSE from 1.68°/s to 1.83°/s. Nominal baseline with $s_{tire}=1.3161$ provides optimal global cornering fit.
2. **Brake Torque Scaling**: During heavy braking holdout, open-loop brake command over-decelerated the car ($V_x$ final = 3.4 m/s vs. 14.5 m/s measured). Reducing brake gain parameter to 0.80 improves $V_x$ tracking, identifying a clear calibration discrepancy in brake pad friction $\mu_{pad}$.
3. **Pitch Dynamics & Grade**: Suspension pitch $	heta_{susp} = (z_f - z_r)/L_{wb}$ correlates $r = 0.3959$ with braking deceleration, whereas inertial IMU pitch correlates $r = -0.2056$ due to up to 4.2° track elevation grade.

---

## 7. Required Phase 3D Changes (Evidence-Grounded Only)

Only changes justified by direct empirical evidence are approved for Phase 3D investigation:

1. **Telemetry Ingestion SI Scaling**:
   - *Hypothesis*: Mislabeled `suspFLpos_m` requires automatic $0.01	imes$ conversion.
   - *Evidence*: Values 6.0–14.4 cm represent physically impossible 8-meter stroke if interpreted as meters.
   - *Risk*: Zero risk of overfitting (pure unit correction).
2. **Chassis Pitch Grade-Decoupling**:
   - *Hypothesis*: State estimator must track chassis pitch via relative suspension displacement rather than inertial IMU pitch.
   - *Evidence*: IMU pitch is contaminated by up to 4.2° road grade.
   - *Success Criterion*: Suspension pitch correlates with longitudinal acceleration $r > 0.50$.
3. **Linear Steering Compliance Term**:
   - *Hypothesis*: Incorporate $\delta_{eff} = \delta_{rack} - k_\delta a_y$ in kinematics model.
   - *Evidence*: Corner-entry lateral acceleration is attenuated by $\sim 0.25^\circ/	ext{g}$.
   - *Success Criterion*: Corner entry yaw rate RMSE reduction on Turn 1.
4. **Brake Actuator Line-Pressure Mapping**:
   - *Hypothesis*: Non-linear brake torque curve accounting for pedal modulation vs. line pressure.
   - *Evidence*: Open-loop heavy braking $V_x$ over-decelerates under constant gain assumption.

---

## 8. Explicitly Unvalidated Quantities

The following quantities **cannot be claimed as empirically validated** because physical ground-truth sensors were not installed on Norbert:
1. **3-Axis Wheel Hub / Tire Forces ($F_x, F_y, F_z$)**: Requires wheel force transducers (e.g. Kistler RoaDyn).
2. **Rear-Right Suspension Displacement ($z_{RR}$)**: Sensor physically missing on vehicle.
3. **Direct Optical Tire Carcass Slip Angle ($lpha$)**: Requires body-mounted optical slip sensor (e.g. Correvit).
4. **Independent Optical Lap Timing Transponder Beacons**: Requires MyLaps / AMB track loop receiver channel.
5. **Suspension Link Bushing Reaction Force Transducers**: Required to isolate anti-dive force path from spring/damper compliance.
6. **Internal Damper Chamber Hydraulic Pressures**: Requires differential pressure transducers across damper chambers.

---

## 9. Phase 3D Gate Decision

```
==================================================
PHASE 3D AUTHORIZATION:
AUTHORIZED
==================================================
```

**Justification**: The Phase 3C evidence has been proven to be computationally clean, input-independent, and free of ground-truth contamination. The detected narrative contradictions have been fully reconciled with numerical ground truth, establishing an immutable, scientifically defensible baseline for Phase 3D physics development.
