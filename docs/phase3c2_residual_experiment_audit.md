# SuspensionLab PRO — Phase 3C.2 Residual Experiment Integrity Audit Report

## 1. Fine Tire Stiffness Sweep (Objective vs. $s_{tire}$ Curves)

**Audit Conclusion**: EMPIRICAL AUDIT VERDICT: s_tire = 1.3161 is NOT a universal physical optimum. Turn 4 Sweeper optimal is s_tire = 1.16 (RMSE: 1.68 deg/s vs 1.72 deg/s at 1.3161). Turn 3 Hairpin optimal is s_tire = 1.00 (RMSE: 2.38 deg/s vs 2.54 deg/s at 1.3161). Turn 1 Calibration prefers lower stiffness (s_tire = 0.84). 1.3161 was an early joint calibration point from Turn 1 rather than a globally supported physical parameter.

| Maneuver | Optimal $s_{tire}$ | Min Yaw RMSE | Best $R^2$ | Baseline $s_{tire}=1.3161$ RMSE | Baseline $1.3161$ $R^2$ |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Turn1_Calibration** | **0.84** | **2.07°/s** | **0.9806** | 2.51°/s | 0.9716 |
| **Turn1_Holdout** | **0.80** | **1.40°/s** | **0.4783** | 2.81°/s | -1.0986 |
| **Turn4_Sweeper** | **1.16** | **1.68°/s** | **0.9509** | 1.72°/s | 0.9486 |
| **Turn3_Hairpin** | **1.00** | **2.38°/s** | **0.9545** | 2.54°/s | 0.9483 |

### Objective Curve Data Points:
| $s_{tire}$ | Turn 1 Cal RMSE | Turn 1 Cal $R^2$ | Turn 4 Sweeper RMSE | Turn 4 $R^2$ | Turn 3 Hairpin RMSE | Turn 3 $R^2$ |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0.8000 | 2.08°/s | 0.9804 | 2.00°/s | 0.9299 | 2.48°/s | 0.9506 |
| 0.8800 | 2.08°/s | 0.9805 | 1.86°/s | 0.9396 | 2.41°/s | 0.9534 |
| 0.9600 | 2.11°/s | 0.9798 | 1.76°/s | 0.9458 | 2.38°/s | 0.9545 |
| 1.0400 | 2.18°/s | 0.9786 | 1.70°/s | 0.9493 | 2.39°/s | 0.9543 |
| 1.1200 | 2.26°/s | 0.9769 | 1.68°/s | 0.9508 | 2.41°/s | 0.9533 |
| 1.2000 | 2.36°/s | 0.9749 | 1.68°/s | 0.9507 | 2.46°/s | 0.9516 |
| 1.2800 | 2.46°/s | 0.9727 | 1.70°/s | 0.9495 | 2.51°/s | 0.9494 |
| 1.3200 | 2.51°/s | 0.9715 | 1.72°/s | 0.9485 | 2.54°/s | 0.9482 |
| 1.4000 | 2.62°/s | 0.9691 | 1.76°/s | 0.9459 | 2.60°/s | 0.9456 |
| 1.4800 | 2.72°/s | 0.9665 | 1.81°/s | 0.9428 | 2.67°/s | 0.9428 |
| 1.5600 | 2.83°/s | 0.9639 | 1.87°/s | 0.9392 | 2.74°/s | 0.9399 |
| 1.6400 | 2.93°/s | 0.9613 | 1.93°/s | 0.9352 | 2.81°/s | 0.9369 |
| 1.7200 | 3.03°/s | 0.9587 | 1.99°/s | 0.9310 | 2.87°/s | 0.9339 |
| 1.8000 | 3.12°/s | 0.9560 | 2.05°/s | 0.9265 | 2.94°/s | 0.9308 |

---

## 2. Brake Chain Physical Trace & Contradiction Resolution

### CONTRADICTION RESOLUTION: The Phase 3C report claimed the model 'under-decelerated' because track pad friction was underestimated. This claim was scientifically false and conceptually inverted. The simulation pedal mapping 'act_brk = min(P_bar / 40, 1.0)' saturated at 40 bar, demanding full emergency braking torque (4,800 Nm, equivalent to -10.01 m/s^2 or -1.02g). However, physical telemetry shows Norbert only pulled -5.52 m/s^2 (-0.56g). The simulation therefore MASSIVELY OVER-DECELERATED, bringing simulated speed down to 2.5 m/s while the real car remained at 14.5 m/s. Reducing torque to 0.8x (and 0.57x) improved Vx error because it lowered the excessive simulated deceleration closer to the true measured 0.56g physical decel. The actual defect is an over-aggressive pedal mapping gain that assumes 40 bar is 100% clamping capacity, whereas standard automotive ABS thresholds occur at 80–100 bar.

### Quantitative Brake Chain Trace:
- **Peak Measured Brake Line Pressure**: `42.6 bar`
- **Peak Measured Physical Deceleration ($a_x$)**: `-5.52 m/s^2` (-0.56g)
- **Simulation Pedal Demand ($act\_brk = \min(P / 40, 1.0)$)**: `1.00` (100% full emergency saturation)
- **Simulation Demanded Tractive Brake Force**: `15009.4 N`
- **Simulation Expected Deceleration**: `-9.81 m/s^2` (-1.02g)
- **Over-Deceleration Discrepancy Ratio**: **`1.78x`** the actual physical deceleration pulled by the car!

### Multiplier Evaluation Results:
| Multiplier | Max Braking Torque | Final Predicted $V_x$ | Measured Final $V_x$ | $V_x$ RMSE |
| :--- | :--- | :--- | :--- | :--- |
| **`multiplier_1.00`** | 4800 Nm | **3.0 m/s** | 14.5 m/s | **6.87 m/s** |
| **`multiplier_0.80`** | 3840 Nm | **7.5 m/s** | 14.5 m/s | **4.21 m/s** |
| **`multiplier_0.57`** | 2736 Nm | **12.6 m/s** | 14.5 m/s | **1.18 m/s** |

---

## 3. Steering Compliance Before/After Numerical Verification

| Maneuver | Baseline $k_\delta=0.0$ RMSE | Calibrated $k_\delta=0.000451$ RMSE | RMSE Delta | Baseline Peak Error | Calibrated Peak Error | Peak Reduction |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Turn 1 Dynamic Corner Entry** | 2.619°/s | **2.399°/s** | **-0.221°/s** | 6.916°/s | **6.155°/s** | **11.0%** |
| **Turn 1 Holdout Steering Reversal** | 2.812°/s | **2.105°/s** | **-0.708°/s** | 6.074°/s | **5.486°/s** | **9.7%** |
| **Turn 4 High-Speed Left Sweeper** | 1.716°/s | **1.610°/s** | **-0.106°/s** | 5.193°/s | **5.250°/s** | **-1.1%** |
| **Turn 3 Hairpin Complex** | 2.539°/s | **2.331°/s** | **-0.207°/s** | 6.328°/s | **6.467°/s** | **-2.2%** |
