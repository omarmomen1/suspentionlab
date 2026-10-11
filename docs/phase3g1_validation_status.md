# SuspensionLab PRO — Phase 3G.1 Validation Status
## Authoritative Epistemic Ledger & Gate Recommendation

---

### 1. Pressure Perturbation Sensitivity Summary

| Delta Pressure ($\Delta P$) | Mean Velocity Shift ($\Delta V_x$) | $V_x$ Sensitivity | Mean Yaw Shift ($|\Delta r|$) | Mean Wheel Shift ($\Delta \omega$) |
| :---: | :---: | :---: | :---: | :---: |
| **$-5.0\text{ bar}$** | $+1.584\text{ m/s}$ | $-0.3169\text{ (m/s)/bar}$ | $0.0171\text{ rad/s}$ | $+5.087\text{ rad/s}$ |
| **$-2.0\text{ bar}$** | $+0.702\text{ m/s}$ | $-0.3509\text{ (m/s)/bar}$ | $0.0078\text{ rad/s}$ | $+2.252\text{ rad/s}$ |
| **$-1.0\text{ bar}$** | $+0.360\text{ m/s}$ | $-0.3598\text{ (m/s)/bar}$ | $0.0040\text{ rad/s}$ | $+1.154\text{ rad/s}$ |
| **$+1.0\text{ bar}$** | $-0.366\text{ m/s}$ | $-0.3665\text{ (m/s)/bar}$ | $0.0042\text{ rad/s}$ | $-1.174\text{ rad/s}$ |
| **$+2.0\text{ bar}$** | $-0.732\text{ m/s}$ | $-0.3661\text{ (m/s)/bar}$ | $0.0085\text{ rad/s}$ | $-2.344\text{ rad/s}$ |
| **$+5.0\text{ bar}$** | $-1.823\text{ m/s}$ | $-0.3646\text{ (m/s)/bar}$ | $0.0215\text{ rad/s}$ | $-5.818\text{ rad/s}$ |

Longitudinal deceleration sensitivity is linear: **$\frac{\partial V_x}{\partial P} \approx -0.365\text{ (m/s)/bar}$**.

---

### 2. Epistemic Ledger

- **Target Leakage**: Proved zero ($\frac{\partial P_{pred}}{\partial P_{meas}} \equiv 0.000000$).
- **Regime Audit**: Turn 3 confirmed on unseen data; Turn 5 designated discovery/calibration; HighSpeed S-Curves unbraked drift decoupled.
- **State-Conditioning**: Verified that Full-Forward prediction operates with identical stability and accuracy to state-conditioned mode.

---

### 3. Gate Status

**PHASE 3G.1 STATUS: `PASS WITH FINDINGS`**
