# SuspensionLab PRO — Phase 3H.1 Powertrain Integrity Report
## Gear-Ratio Provenance, Engine Torque Error Envelope & Tractive Deficit

**Audit Mandate**: Audit Only. Zero production physics modifications. Zero parameter tuning.

---

### 1. Actual Transmission Kinematics ($N_{\text{total}}$)

Direct calculation from measured CAN signals:
$$N_{\text{total, measured}} = \frac{\omega_{\text{engine}}}{\omega_{\text{wheel}}} = \frac{\text{engine\_rpm}}{\text{wheel\_rpm}} = \mathbf{5.6426} \pm 0.0164$$

- **Dynamic Rolling Radius**: $R_{\text{eff}} = \frac{V_x}{\omega_{\text{wheel}}} = \mathbf{0.3170\text{ m}}$ ($0.88\%$ carcass compression from nominal $0.3198\text{ m}$).
- **Vehicle Platform**: Volkswagen Golf VII GTI (DQ250 6-Speed DSG).
- **Physical Operating Gear**: **3rd Gear** (Gearbox ratio $1.331$, Final Drive $4.238$, Total ratio $5.641$).
- **Simulator Implementation**: Commanded gear index 13, clamped to **6th Gear** with ratio **$4.200$** (**$3.23\times$ discrepancy**).

---

### 2. Engine Torque Model Error Envelope

- **Synthetic Relationship**: $T_{\text{engine}} \approx 360\text{ Nm} \times \text{throttle}$ was confirmed active in `DynamicVehicleParams`.
- **Crankshaft Error**: Generates $73.1\text{ Nm}$ average vs $86.28\text{ Nm}$ measured on CAN ($15.3\%$ combustion torque deficit).
- **Axle Torque Deficit**:
  - Measured Physical Axle Torque: **$438.2\text{ Nm}$** ($86.28 \times 5.6426 \times 0.90$)
  - Simulated Axle Torque: **$276.3\text{ Nm}$** ($73.1 \times 4.200 \times 0.90$)
  - Deficit: **$161.9\text{ Nm}$** ($36.9\%$ under-delivery at the driven axle).
- **Tractive Force Impact**: $161.9\text{ Nm} / 0.317\text{ m} = \mathbf{510.7\text{ N}}$ of missing forward thrust over 9.0 seconds, explaining $\Delta V_x = \mathbf{3.00\text{ m/s}}$ of deceleration.
