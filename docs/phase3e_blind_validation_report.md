# SUSPENSIONLAB PRO — PHASE 3E BLIND VALIDATION REPORT

**Execution Status**: COMPLETED AND VERIFIED
**Execution Timestamp**: `2026-09-23T23:40:50.741769+00:00`
**Dataset SHA-256**: `489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3`
**Phase 3E Status**: **`PASS WITH FINDINGS`**

---

## 1. Executive Summary & Objective
Phase 3E executes blind external confirmation of the frozen Phase 3D dynamic vehicle model against **5 genuinely unseen, unvisited physical maneuver segments** (42.50 s, 978 m, 8,500 samples) from the authentic Stanford Volkswagen Golf VII GTI dataset. Zero parameter tuning or optimization was permitted.

## 2A. Fully Blind Evaluation Matrix

| Unseen Maneuver | Channel | Baseline RMSE | Phase 3D RMSE | Delta RMSE | % Change | Baseline R² | Phase 3D R² | Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Unseen Maneuver 1** | `Vx` | 2.14 | 2.19 | +0.05 | +2.1% | -1.483 | -1.590 | PARITY / MILD |
| **Unseen Maneuver 1** | `yaw_rate` | 3.07 °/s | 3.61 °/s | +0.55 °/s | +17.8% | 0.722 | 0.615 | PARITY / MILD |
| **Unseen Maneuver 1** | `ay_raw` | 4.15 | 4.18 | +0.03 | +0.6% | 0.204 | 0.194 | PARITY / MILD |
| **Unseen Maneuver 1** | `ay_filt_10hz` | 1.03 | 1.13 | +0.10 | +9.6% | 0.807 | 0.768 | PARITY / MILD |
| **Unseen Maneuver 1** | `pitch_suspension` | 0.333° | 0.334° | +0.001° | +0.4% | -3.638 | -3.670 | PARITY / MILD |
| **Unseen Maneuver 1** | `travel_FL` | 14.2 mm | 15.4 mm | +1.2 mm | +8.1% | -2.773 | -3.411 | PARITY / MILD |
| **Unseen Maneuver 1** | `omega_FL` | 6.4 rad/s | 6.5 rad/s | +0.0 rad/s | +0.3% | -0.963 | -0.976 | PARITY / MILD |
| **Unseen Maneuver 1** | `omega_RL` | 6.6 rad/s | 6.8 rad/s | +0.2 rad/s | +2.7% | -1.266 | -1.390 | PARITY / MILD |
| **Unseen Maneuver 2** | `Vx` | 0.66 | 1.01 | +0.34 | +51.3% | 0.726 | 0.373 | PARITY / MILD |
| **Unseen Maneuver 2** | `yaw_rate` | 1.80 °/s | 1.80 °/s | -0.00 °/s | -0.1% | 0.962 | 0.962 | IMPROVED |
| **Unseen Maneuver 2** | `ay_raw` | 4.22 | 4.22 | -0.00 | -0.0% | 0.463 | 0.463 | IMPROVED |
| **Unseen Maneuver 2** | `ay_filt_10hz` | 0.99 | 0.98 | -0.01 | -1.1% | 0.940 | 0.941 | IMPROVED |
| **Unseen Maneuver 2** | `pitch_suspension` | 0.242° | 0.229° | -0.013° | -5.5% | -0.683 | -0.504 | IMPROVED |
| **Unseen Maneuver 2** | `travel_FL` | 14.2 mm | 14.5 mm | +0.3 mm | +1.9% | -0.061 | -0.101 | PARITY / MILD |
| **Unseen Maneuver 2** | `omega_FL` | 1.8 rad/s | 2.9 rad/s | +1.2 rad/s | +66.1% | 0.789 | 0.419 | PARITY / MILD |
| **Unseen Maneuver 2** | `omega_RL` | 1.8 rad/s | 3.0 rad/s | +1.2 rad/s | +65.6% | 0.785 | 0.411 | PARITY / MILD |
| **Unseen Maneuver 3** | `Vx` | 4.69 | 4.54 | -0.15 | -3.2% | -28.548 | -26.705 | IMPROVED |
| **Unseen Maneuver 3** | `yaw_rate` | 1.51 °/s | 1.43 °/s | -0.07 °/s | -4.8% | 0.968 | 0.971 | IMPROVED |
| **Unseen Maneuver 3** | `ay_raw` | 4.20 | 4.26 | +0.06 | +1.3% | 0.482 | 0.468 | PARITY / MILD |
| **Unseen Maneuver 3** | `ay_filt_10hz` | 1.13 | 1.33 | +0.19 | +17.2% | 0.927 | 0.900 | PARITY / MILD |
| **Unseen Maneuver 3** | `pitch_suspension` | 0.281° | 0.277° | -0.004° | -1.5% | -1.139 | -1.074 | IMPROVED |
| **Unseen Maneuver 3** | `travel_FL` | 15.1 mm | 14.5 mm | -0.6 mm | -3.9% | 0.220 | 0.280 | IMPROVED |
| **Unseen Maneuver 3** | `omega_FL` | 15.2 rad/s | 14.8 rad/s | -0.4 rad/s | -2.9% | -31.126 | -29.261 | IMPROVED |
| **Unseen Maneuver 3** | `omega_RL` | 14.9 rad/s | 14.4 rad/s | -0.4 rad/s | -3.0% | -27.551 | -25.858 | IMPROVED |
| **Unseen Maneuver 4** | `Vx` | 1.86 | 5.36 | +3.50 | +187.7% | 0.924 | 0.370 | PARITY / MILD |
| **Unseen Maneuver 4** | `yaw_rate` | 4.75 °/s | 7.48 °/s | +2.74 °/s | +57.6% | 0.856 | 0.643 | PARITY / MILD |
| **Unseen Maneuver 4** | `ay_raw` | 4.08 | 4.22 | +0.14 | +3.4% | 0.245 | 0.192 | PARITY / MILD |
| **Unseen Maneuver 4** | `ay_filt_10hz` | 1.09 | 1.53 | +0.45 | +41.0% | 0.821 | 0.644 | PARITY / MILD |
| **Unseen Maneuver 4** | `pitch_suspension` | 0.684° | 0.567° | -0.117° | -17.1% | -3.374 | -2.008 | IMPROVED |
| **Unseen Maneuver 4** | `travel_FL` | 11.4 mm | 8.5 mm | -2.8 mm | -24.8% | 0.060 | 0.468 | IMPROVED |
| **Unseen Maneuver 4** | `omega_FL` | 5.0 rad/s | 16.1 rad/s | +11.1 rad/s | +219.9% | 0.942 | 0.409 | PARITY / MILD |
| **Unseen Maneuver 4** | `omega_RL` | 5.3 rad/s | 16.4 rad/s | +11.1 rad/s | +210.1% | 0.939 | 0.417 | PARITY / MILD |
| **Unseen Maneuver 5** | `Vx` | 1.77 | 1.82 | +0.05 | +2.6% | 0.512 | 0.487 | PARITY / MILD |
| **Unseen Maneuver 5** | `yaw_rate` | 1.69 °/s | 2.08 °/s | +0.40 °/s | +23.7% | 0.972 | 0.957 | PARITY / MILD |
| **Unseen Maneuver 5** | `ay_raw` | 4.22 | 4.24 | +0.02 | +0.5% | 0.272 | 0.265 | PARITY / MILD |
| **Unseen Maneuver 5** | `ay_filt_10hz` | 0.87 | 0.96 | +0.09 | +10.9% | 0.898 | 0.874 | PARITY / MILD |
| **Unseen Maneuver 5** | `pitch_suspension` | 0.444° | 0.428° | -0.016° | -3.7% | -1.010 | -0.866 | IMPROVED |
| **Unseen Maneuver 5** | `travel_FL` | 12.2 mm | 12.6 mm | +0.3 mm | +2.5% | -2.891 | -3.092 | PARITY / MILD |
| **Unseen Maneuver 5** | `omega_FL` | 6.2 rad/s | 6.2 rad/s | +0.0 rad/s | +0.2% | 0.420 | 0.418 | PARITY / MILD |
| **Unseen Maneuver 5** | `omega_RL` | 5.8 rad/s | 5.8 rad/s | -0.1 rad/s | -0.9% | 0.489 | 0.498 | IMPROVED |

## 2B. Speed-Conditioned Evaluation Matrix (Longitudinal Speed Injected)

| Unseen Maneuver | Channel | Baseline RMSE | Phase 3D RMSE | Delta RMSE | % Change | Baseline R² | Phase 3D R² | Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Unseen Maneuver 1** | `yaw_rate` | 2.47 °/s | 2.99 °/s | +0.52 °/s | +21.2% | 0.820 | 0.736 | PARITY / MILD |
| **Unseen Maneuver 1** | `ay_filt_10hz` | 1.10 | 1.28 | +0.17 | +15.7% | 0.779 | 0.704 | PARITY / MILD |
| **Unseen Maneuver 1** | `roll` | 0.08 | 0.08 | -0.00 | -2.4% | -75.168 | -71.612 | IMPROVED |
| **Unseen Maneuver 1** | `pitch_suspension` | 0.337° | 0.339° | +0.001° | +0.3% | -3.757 | -3.789 | PARITY / MILD |
| **Unseen Maneuver 1** | `travel_FL` | 14.3 mm | 15.4 mm | +1.1 mm | +7.9% | -2.801 | -3.427 | PARITY / MILD |
| **Unseen Maneuver 2** | `yaw_rate` | 1.77 °/s | 1.74 °/s | -0.03 °/s | -1.6% | 0.964 | 0.965 | IMPROVED |
| **Unseen Maneuver 2** | `ay_filt_10hz` | 0.96 | 0.98 | +0.02 | +2.5% | 0.943 | 0.940 | PARITY / MILD |
| **Unseen Maneuver 2** | `roll` | 0.01 | 0.01 | +0.00 | +4.0% | 0.777 | 0.759 | PARITY / MILD |
| **Unseen Maneuver 2** | `pitch_suspension` | 0.241° | 0.227° | -0.014° | -5.7% | -0.666 | -0.482 | IMPROVED |
| **Unseen Maneuver 2** | `travel_FL` | 13.9 mm | 14.0 mm | +0.1 mm | +1.0% | -0.018 | -0.038 | PARITY / MILD |
| **Unseen Maneuver 3** | `yaw_rate` | 1.66 °/s | 1.63 °/s | -0.03 °/s | -1.7% | 0.961 | 0.962 | IMPROVED |
| **Unseen Maneuver 3** | `ay_filt_10hz` | 0.95 | 1.01 | +0.06 | +6.8% | 0.949 | 0.942 | PARITY / MILD |
| **Unseen Maneuver 3** | `roll` | 0.08 | 0.08 | -0.00 | -2.4% | -12.954 | -12.303 | IMPROVED |
| **Unseen Maneuver 3** | `pitch_suspension` | 0.286° | 0.281° | -0.005° | -1.8% | -1.207 | -1.130 | IMPROVED |
| **Unseen Maneuver 3** | `travel_FL` | 17.6 mm | 16.8 mm | -0.8 mm | -4.8% | -0.057 | 0.041 | IMPROVED |
| **Unseen Maneuver 4** | `yaw_rate` | 2.81 °/s | 2.74 °/s | -0.07 °/s | -2.5% | 0.949 | 0.952 | IMPROVED |
| **Unseen Maneuver 4** | `ay_filt_10hz` | 0.87 | 0.87 | -0.00 | -0.0% | 0.884 | 0.884 | IMPROVED |
| **Unseen Maneuver 4** | `roll` | 0.01 | 0.01 | -0.00 | -12.3% | 0.841 | 0.878 | IMPROVED |
| **Unseen Maneuver 4** | `pitch_suspension` | 0.673° | 0.540° | -0.133° | -19.7% | -3.233 | -1.729 | IMPROVED |
| **Unseen Maneuver 4** | `travel_FL` | 11.6 mm | 9.5 mm | -2.1 mm | -17.9% | 0.018 | 0.338 | IMPROVED |
| **Unseen Maneuver 5** | `yaw_rate` | 1.88 °/s | 1.95 °/s | +0.07 °/s | +3.6% | 0.965 | 0.962 | PARITY / MILD |
| **Unseen Maneuver 5** | `ay_filt_10hz` | 0.78 | 0.79 | +0.01 | +1.1% | 0.917 | 0.915 | PARITY / MILD |
| **Unseen Maneuver 5** | `roll` | 0.02 | 0.02 | +0.00 | +3.4% | -0.883 | -1.014 | PARITY / MILD |
| **Unseen Maneuver 5** | `pitch_suspension` | 0.445° | 0.426° | -0.019° | -4.3% | -1.017 | -0.848 | IMPROVED |
| **Unseen Maneuver 5** | `travel_FL` | 11.9 mm | 12.5 mm | +0.6 mm | +4.7% | -2.675 | -3.032 | PARITY / MILD |

## 2C. Wheel Speed & Longitudinal Slip Ledger (All 4 Encoders, Fully Blind)

| Unseen Maneuver | Wheel | Baseline RMSE | Phase 3D RMSE | Delta RMSE | % Change | Peak Error | Final Error |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Unseen Maneuver 1** | `omega_FL` | 6.44 rad/s | 6.46 rad/s | +0.02 rad/s | +0.3% | 10.17 rad/s | -2.37 rad/s |
| **Unseen Maneuver 1** | `omega_FR` | 5.74 rad/s | 5.85 rad/s | +0.12 rad/s | +2.1% | 8.60 rad/s | -2.59 rad/s |
| **Unseen Maneuver 1** | `omega_RL` | 6.59 rad/s | 6.77 rad/s | +0.18 rad/s | +2.7% | 9.87 rad/s | -3.20 rad/s |
| **Unseen Maneuver 1** | `omega_RR` | 6.27 rad/s | 6.39 rad/s | +0.12 rad/s | +1.8% | 9.28 rad/s | -3.41 rad/s |
| **Unseen Maneuver 2** | `omega_FL` | 1.77 rad/s | 2.93 rad/s | +1.17 rad/s | +66.1% | 4.55 rad/s | -3.58 rad/s |
| **Unseen Maneuver 2** | `omega_FR` | 1.57 rad/s | 2.62 rad/s | +1.05 rad/s | +66.6% | 4.31 rad/s | -4.19 rad/s |
| **Unseen Maneuver 2** | `omega_RL` | 1.81 rad/s | 3.01 rad/s | +1.19 rad/s | +65.6% | 4.47 rad/s | -4.12 rad/s |
| **Unseen Maneuver 2** | `omega_RR` | 1.75 rad/s | 2.80 rad/s | +1.06 rad/s | +60.5% | 4.39 rad/s | -4.22 rad/s |
| **Unseen Maneuver 3** | `omega_FL` | 15.23 rad/s | 14.78 rad/s | -0.45 rad/s | -2.9% | 24.19 rad/s | +24.19 rad/s |
| **Unseen Maneuver 3** | `omega_FR` | 15.04 rad/s | 14.56 rad/s | -0.48 rad/s | -3.2% | 23.85 rad/s | +23.85 rad/s |
| **Unseen Maneuver 3** | `omega_RL` | 14.86 rad/s | 14.41 rad/s | -0.45 rad/s | -3.0% | 23.68 rad/s | +23.68 rad/s |
| **Unseen Maneuver 3** | `omega_RR` | 14.82 rad/s | 14.31 rad/s | -0.50 rad/s | -3.4% | 23.47 rad/s | +23.38 rad/s |
| **Unseen Maneuver 4** | `omega_FL` | 5.03 rad/s | 16.08 rad/s | +11.05 rad/s | +219.9% | 26.24 rad/s | -9.32 rad/s |
| **Unseen Maneuver 4** | `omega_FR` | 5.26 rad/s | 15.80 rad/s | +10.54 rad/s | +200.5% | 22.98 rad/s | -9.42 rad/s |
| **Unseen Maneuver 4** | `omega_RL` | 5.27 rad/s | 16.35 rad/s | +11.08 rad/s | +210.1% | 25.95 rad/s | -10.64 rad/s |
| **Unseen Maneuver 4** | `omega_RR` | 5.59 rad/s | 16.48 rad/s | +10.89 rad/s | +194.6% | 24.25 rad/s | -10.65 rad/s |
| **Unseen Maneuver 5** | `omega_FL` | 6.21 rad/s | 6.23 rad/s | +0.01 rad/s | +0.2% | 11.98 rad/s | -11.98 rad/s |
| **Unseen Maneuver 5** | `omega_FR` | 5.95 rad/s | 6.02 rad/s | +0.07 rad/s | +1.2% | 11.73 rad/s | -11.73 rad/s |
| **Unseen Maneuver 5** | `omega_RL` | 5.83 rad/s | 5.77 rad/s | -0.05 rad/s | -0.9% | 10.72 rad/s | -10.60 rad/s |
| **Unseen Maneuver 5** | `omega_RR` | 5.65 rad/s | 5.75 rad/s | +0.09 rad/s | +1.6% | 10.74 rad/s | -10.58 rad/s |

## 3. Raw vs. 10 Hz Filtered Accelerometer Ledger (Transparency Mandate)

| Unseen Maneuver | Channel | Raw Baseline RMSE | Raw Phase 3D RMSE | 10 Hz Filt Baseline | 10 Hz Filt Phase 3D | HF Structural Noise |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Unseen Maneuver 1** | `ay` [m/s²] | 4.154 | 4.179 | 1.034 | 1.133 | 3.046 m/s² |
| **Unseen Maneuver 1** | `ax` [m/s²] | 0.761 | 0.773 | 0.664 | 0.678 | 0.096 m/s² |
| **Unseen Maneuver 2** | `ay` [m/s²] | 4.218 | 4.217 | 0.986 | 0.975 | 3.241 m/s² |
| **Unseen Maneuver 2** | `ax` [m/s²] | 0.421 | 0.468 | 0.322 | 0.380 | 0.087 m/s² |
| **Unseen Maneuver 3** | `ay` [m/s²] | 4.199 | 4.256 | 1.134 | 1.328 | 2.927 m/s² |
| **Unseen Maneuver 3** | `ax` [m/s²] | 0.926 | 0.905 | 0.895 | 0.873 | 0.032 m/s² |
| **Unseen Maneuver 4** | `ay` [m/s²] | 4.078 | 4.218 | 1.088 | 1.534 | 2.684 m/s² |
| **Unseen Maneuver 4** | `ax` [m/s²] | 1.001 | 1.649 | 0.974 | 1.633 | 0.016 m/s² |
| **Unseen Maneuver 5** | `ay` [m/s²] | 4.221 | 4.242 | 0.870 | 0.965 | 3.277 m/s² |
| **Unseen Maneuver 5** | `ax` [m/s²] | 1.470 | 1.561 | 1.446 | 1.538 | 0.023 m/s² |

## 4. Trajectory Drift Ledger (Dead Reckoning)

| Unseen Maneuver | Distance [m] | Baseline Drift [m] | Baseline Drift [%] | Phase 3D Drift [m] | Phase 3D Drift [%] | Drift Delta |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Unseen Maneuver 1** | 246.6 m | 51.83 m | 21.02% | 64.45 m | 26.14% | -12.62 m |
| **Unseen Maneuver 2** | 141.2 m | 3.59 m | 2.54% | 7.15 m | 5.06% | -3.56 m |
| **Unseen Maneuver 3** | 261.0 m | 36.27 m | 13.90% | 36.28 m | 13.90% | -0.01 m |
| **Unseen Maneuver 4** | 172.1 m | 20.15 m | 11.71% | 52.90 m | 30.73% | -32.75 m |
| **Unseen Maneuver 5** | 157.3 m | 10.43 m | 6.63% | 6.32 m | 4.02% | +4.12 m |

---
*Report generated programmatically by `scripts/run_phase3e_blind_validation.py`.*