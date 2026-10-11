# SuspensionLab PRO — Phase 3H.1 Validation Status
## Authoritative Epistemic Ledger & Gate Status

---

### 1. Epistemic Classification of Candidate Contributors

| Candidate Cause | Epistemic Classification | Quantitative Impact |
| :--- | :---: | :--- |
| **Gear Clamping Discrepancy** | **`PRIMARY_CONTRIBUTOR`** | 6th gear (4.20) forced vs 3rd gear (5.6426); correcting ratio in CF_B2 drops RMSE from 4.482 to 2.767 m/s (-38.3%). |
| **Synthetic Torque Curve Error** | **`SECONDARY_CONTRIBUTOR`** | Crankshaft torque error is 15.3% (73.1 Nm vs 86.28 Nm); compounds at the axle. |
| **Aerodynamic Drag Road Load** | **`PRIMARY_CONTRIBUTOR`** | CF_D (Zero Aero) reduces RMSE by 2.117 m/s (-47.2%); consumes 144.6 kJ retarding work. |
| **Road Grade Gravity Road Load** | **`PRIMARY_CONTRIBUTOR`** | CF_F (Zero Grade) reduces RMSE by 1.694 m/s (-37.8%); extracts 126.2 kJ retarding work. |
| **Lateral Scrub & Coriolis** | **`MINOR_CONTRIBUTOR`** | Body-frame kinematic coupling accounts for 37.0 kJ (11.6%) of chassis deceleration. |
| **Rolling Resistance** | **`NOT_SUPPORTED`** | Inactive (0.0 N) in baseline FWD model; produces 0.000 m/s delta in CF_E. |
| **CAN Bus Raw `GearRatio` Semantics** | **`UNIDENTIFIABLE`** | Raw value 13.585 is 2.4076x physical ratio; raw unit unidentifiable without CAN DBC documentation. |

---

### 2. Gate Status
**PHASE 3H.1 GATE VERDICT: `PASS WITH FINDINGS`**

- Gear semantics resolved: Physical ratio is $5.6426$ (3rd Gear).
- Engine torque provenance resolved: Synthetic model $T \approx 360\text{ Nm} \times \text{throttle}$ verified with $15.3\%$ error envelope.
- Power balance independently calculated: Axle power under-delivered by $19.03\text{ kW}$ ($47.5\%$).
- All 9 counterfactuals evaluated and reproducible with zero production physics changes.
