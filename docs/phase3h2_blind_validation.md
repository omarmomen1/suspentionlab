# SuspensionLab PRO — Phase 3H.2 Blind Multi-Regime Validation
## Performance on Untouched Authentic Track Maneuvers

---

### 1. Blind Validation Results Table

| Maneuver | Epistemic Role | $V_x$ RMSE | Exit Error | Wheel Speed RMSE | Engine Speed RMSE | Yaw Rate RMSE | Epistemic Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **HighSpeed S-Curves** | Validation Set | **4.1226\text{ m/s}** | +6.7371\text{ m/s} | 13.31\text{ rad/s} | 718.1\text{ RPM} | 0.0258\text{ rad/s} | `MODEL_SUPPORTED` |
| **Turn 2 Complex** | Validation Set | **2.9799\text{ m/s}** | -2.4901\text{ m/s} | 8.79\text{ rad/s} | 468.6\text{ RPM} | 0.0725\text{ rad/s} | `MODEL_SUPPORTED` |
| **Turn 3 Approach** | External Confirmation | **0.7384\text{ m/s}** | -1.0704\text{ m/s} | 1.90\text{ rad/s} | 2136.2\text{ RPM} | 0.0312\text{ rad/s} | `CONFIRMED_ON_UNSEEN_DATA` |
| **Turn 5 Tight Complex** | Discovery Set | **5.9340\text{ m/s}** | -4.8100\text{ m/s} | 18.25\text{ rad/s} | 1007.9\text{ RPM} | 0.1393\text{ rad/s} | `DISCOVERY_CALIBRATION` |
| **Turn 9-10 Final Complex** | Validation Set | **1.9162\text{ m/s}** | -6.0106\text{ m/s} | 9.73\text{ rad/s} | 871.4\text{ RPM} | 0.0419\text{ rad/s} | `MODEL_SUPPORTED` |
