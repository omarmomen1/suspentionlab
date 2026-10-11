# SuspensionLab PRO — Phase 3H Longitudinal Forensic Report
## Root-Cause Deconstruction of High-Speed S-Curves Velocity Discrepancy

**Audit Mandate**: Audit Only. No physics modifications. No parameter tuning.

---

### 1. Executive Summary & Defect Reproduction

During Phase 3G.1, the High-Speed S-Curves ($t \in [54.0, 63.0]\text{ s}$) exhibited:
- **$V_x\text{ RMSE} = 4.4821\text{ m/s}$** (target $\approx 4.5\text{ m/s}$)
- **Exit Speed Error ($V_{x, meas} - V_{x, sim}) = +7.3330\text{ m/s}$** (target $\approx +7.37\text{ m/s}$)
- Measured Brake Pressure = $0.0000\text{ bar}$
- Predicted Brake Pressure = $0.0000\text{ bar}$

#### The Physical Mystery:
- **Measured Real Car**: Enters at **$27.28\text{ m/s}$**, accelerates under throttle ($20.7\%$ avg), and exits at **$30.33\text{ m/s}$** ($+3.06\text{ m/s}$ gain).
- **Simulated Car**: Enters at **$27.28\text{ m/s}$**, decelerates continuously, and exits at **$23.00\text{ m/s}$** ($-4.28\text{ m/s}$ loss).

---

### 2. Multi-Factor Quantitative Force Decomposition

The continuous longitudinal force balance on the chassis is governed by:
$$m \cdot \left(\frac{du}{dt} - r \cdot v\right) = \sum F_{x, \text{tires}} - F_{\text{drag}} + F_{\text{grade}}$$

| Longitudinal Term | Mean Force | Total Work Over 9.0s | Cumulative $\Delta V_x$ Effect | Contributor Status |
| :--- | :---: | :---: | :---: | :--- |
| **Powertrain Axle Drive Torque** | $+839.3\text{ N}$ (sim) vs $+3298.5\text{ N}$ (meas) | $+191.3\text{ kJ}$ | Under-delivers by $-8.18\text{ m/s}$ | **`PRIMARY CONTRIBUTOR`** |
| **Aerodynamic Drag ($F_{\text{drag}}$)** | $-637.2\text{ N}$ | $-144.6\text{ kJ}$ | $-3.75\text{ m/s}$ | **`PRIMARY CONTRIBUTOR`** |
| **Road Grade Gravity ($F_{\text{grade}}$)** | $-563.4\text{ N}$ ($+3.83\%$ uphill) | $-126.2\text{ kJ}$ | $-3.38\text{ m/s}$ | **`PRIMARY CONTRIBUTOR`** |
| **Lateral Scrub & Coriolis ($m \cdot u \cdot r \cdot v$)** | $-161.2\text{ N}$ | $-37.0\text{ kJ}$ | $-0.95\text{ m/s}$ | **`MINOR CONTRIBUTOR`** |
| **Rolling Resistance ($F_{\text{rr}}$)** | $0.0\text{ N}$ (sim) | $0.0\text{ kJ}$ | $0.00\text{ m/s}$ | **`NOT SUPPORTED`** |

---

### 3. Diagnostic Counterfactual Ranking

| Counterfactual Case | Description | $V_x$ RMSE | Exit Speed Error | $\Delta\text{RMSE}$ vs Baseline | Energy Error |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **CF_A** | **Frozen Baseline** | **$4.4821\text{ m/s}$** | **$+7.3330\text{ m/s}$** | **$0.000\text{ m/s}$** | **$1.475\text{ MJ}$** |
| **CF_B1** | Measured $T_{eng}$ (Nominal $gr=4.2$) | $3.7947\text{ m/s}$ | $+6.5338\text{ m/s}$ | $-0.687\text{ m/s}$ | $1.206\text{ MJ}$ |
| **CF_B2** | Measured $T_{eng}$ (True $gr=13.585$) | $3.9915\text{ m/s}$ | $-4.5097\text{ m/s}$ | $-0.491\text{ m/s}$ | $1.647\text{ MJ}$ |
| **CF_C** | Zero Engine Torque | $7.9255\text{ m/s}$ | $+12.9394\text{ m/s}$ | $+3.443\text{ m/s}$ | $2.430\text{ MJ}$ |
| **CF_D** | Zero Aero Drag | $2.3649\text{ m/s}$ | $+3.8765\text{ m/s}$ | **$-2.117\text{ m/s}$** | $0.819\text{ MJ}$ |
| **CF_E** | Zero Rolling Resistance | $4.4821\text{ m/s}$ | $+7.3330\text{ m/s}$ | $0.000\text{ m/s}$ | $1.475\text{ MJ}$ |
| **CF_F** | Zero Grade | $2.7881\text{ m/s}$ | $+4.5761\text{ m/s}$ | **$-1.694\text{ m/s}$** | $0.972\text{ MJ}$ |

---

### 4. Forensic Determination
1. The error does **NOT** stem from braking.
2. The error stems from a **three-way compound interaction**:
   - The simulator transmission ratio clamps to $gr = 4.2$ instead of the measured total ratio $13.585$, starving axle torque to $268.4\text{ Nm}$ ($839.3\text{ N}$ tractive force).
   - The vehicle faces a steep **$+3.83\%$ uphill road grade** extracting $-563.4\text{ N}$ of continuous gravity retarding force.
   - The vehicle faces **$-637.2\text{ N}$ of aerodynamic drag** at $28\text{ m/s}$.
   - Because $839.3\text{ N} < (563.4\text{ N} + 637.2\text{ N} = 1200.6\text{ N})$, the simulated car has negative net acceleration and slows down by $-4.28\text{ m/s}$, while the real car produced enough tractive force ($3298.5\text{ N}$) to accelerate uphill.
