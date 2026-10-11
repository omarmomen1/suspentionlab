# SuspensionLab PRO — Phase 3G Validation Report
## Two-Path Validation: Pressure Prediction & Dynamic Vehicle Response

**Baseline Test Suite**: 104/104 Passing  
**Phase 3G Status**: `PASS WITH FINDINGS`  

---

### 1. Path 1: Standalone Pressure Prediction Results

| Maneuver | Partition Role | FL RMSE | FR RMSE | RL RMSE | RR RMSE | Total P Corr |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Turn 5 Tight Complex** | Discovery Set | 2.34 bar | 2.37 bar | 1.97 bar | 1.98 bar | 0.9986 |
| **Turn 3 Approach** | External Confirmation | **0.60 bar** | **0.79 bar** | **0.59 bar** | **0.62 bar** | **0.9625** |
| **Turn 9-10 Final Complex** | Validation Set | 1.18 bar | 1.37 bar | 0.71 bar | 0.81 bar | 0.9949 |

---

### 2. Path 2: Vehicle Dynamic Response (14-DOF Integration)

Feeding predicted corner pressures into the full vehicle model produces:

| Maneuver | Partition Role | Mode B $V_x$ RMSE | Mode B Exit Error | Yaw Rate RMSE | Avg Wheel Speed RMSE |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Turn 5 Tight Complex** | Discovery Set | **2.431 m/s** | **-0.067 m/s** | 0.0953 rad/s | 7.185 rad/s |
| **Turn 3 Approach** | External Confirmation | **0.587 m/s** | **-0.761 m/s** | 0.0332 rad/s | 1.507 rad/s |

### 3. Comparison with Previous Model Phases

| Metric | Phase 3D Baseline | Phase 3F Actuator Replay | Phase 3G Predictive Mode B |
| :--- | :---: | :---: | :---: |
| **Turn 5 $V_x$ RMSE** | 4.87 m/s | 2.49 m/s | **2.431 m/s** |
| **Turn 5 Final Speed Error** | +3.14 m/s | -0.066 m/s | **-0.067 m/s** |
| **Turn 3 $V_x$ RMSE** | 3.82 m/s | 2.36 m/s | **0.587 m/s** |
| **Brake Input Provenance** | Single Line Replay | 4-Corner Replay | **Autonomous Prediction** |
