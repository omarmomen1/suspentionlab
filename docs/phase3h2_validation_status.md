# SuspensionLab PRO — Phase 3H.2 Validation Status
## Epistemic Provenance Matrix & Final Gate Status

---

### 1. Epistemic Classification Matrix

| Quantity / Model | Epistemic Classification | Physical Derivation / Empirical Provenance |
| :--- | :---: | :--- |
| **Measured Engine Torque** | **`BOUNDARY_REPLAY`** | CAN bus `engineTorque_Nm` recorded from engine control unit. |
| **ECU Reported Engine RPM** | **`CONFIRMED_FROM_SENSOR_KINEMATICS`** | Crankshaft optical/magnetic tooth counter on CAN bus. |
| **Inferred Transmission Gear** | **`CONFIRMED_FROM_SENSOR_KINEMATICS`** | Inferred from $\omega_{\text{eng}} / \omega_{\text{wheel}}$ matched to DQ250 ratios. |
| **Predictive Engine Torque Model** | **`MODEL_SUPPORTED`** | Calibrated on Turn 5 discovery set with bounded progressive envelope. |
| **Inferred Axle Torque** | **`INFERRED`** | $T_{\text{eng}} \cdot N_{\text{total}} \cdot \eta$ reconstructed with assumed $\eta = 0.90$. |
| **Inferred Tractive Force** | **`INFERRED`** | $T_{\text{axle}} / R_{\text{eff}}$ reconstructed with dynamic rolling radius. |
| **Assumed Drivetrain Efficiency** | **`DERIVED`** | Configurable baseline constant ($\eta = 0.90$). |
| **CAN Bus Raw `GearRatio`** | **`UNIDENTIFIABLE`** | Raw value ($13.585$) is $2.4076\times$ physical ratio; unidentifiable without CAN DBC. |

---

### 2. Final Gate Status
**PHASE 3H.2 GATE VERDICT: `PASS`**

1. Raw `GearRatio` is no longer used as a gear index.
2. Gear inference is validated across all 6 available forward gears (91.6% locked).
3. Torque prediction and measured-torque replay are strictly separated.
4. Power and torque provenance are epistemically labeled without false measurement claims.
5. Blind external maneuvers confirm stable forward integration without hidden calibration.
6. Zero regression across previously validated channels.
