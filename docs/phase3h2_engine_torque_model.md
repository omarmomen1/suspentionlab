# SuspensionLab PRO — Phase 3H.2 Engine Torque Model
## Calibration on Turn 5 Discovery Window, Bounded Response & Overrun

---

### 1. Calibration Protocol
- **Calibration Set**: Turn 5 Tight Complex ($t \in [74.0, 83.0]\text{ s}$).
- **Untouched Validation Sets**: HighSpeed S-Curves, Turn 2, Turn 3, Turn 9-10.
- **Governed Formulation**:
  $$T_{\text{eng}}(\text{thr}, \text{RPM}) = \begin{cases}
  T_{\text{overrun}}(\text{RPM}) \cdot (1 - \text{thr} / \text{thr}_{\text{cutoff}}) & \text{if } \text{thr} \le \text{thr}_{\text{cutoff}} \\
  T_{\text{wot}}(\text{RPM}) \cdot \left(\frac{\text{thr} - \text{thr}_{\text{cutoff}}}{1 - \text{thr}_{\text{cutoff}}}\right)^\gamma & \text{if } \text{thr} > \text{thr}_{\text{cutoff}}
  \end{cases}$$

---

### 2. Calibration Metrics
- Turn 5 Measured Mean Torque: **47.7\text{ Nm}**
- Turn 5 Predictive Mean Torque: **19.6\text{ Nm}**
- Turn 5 Predictive RMSE: **58.5\text{ Nm}** vs Synthetic RMSE: **55.1\text{ Nm}**
