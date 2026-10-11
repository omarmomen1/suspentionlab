# SuspensionLab PRO — Telemetry Calibration Audit & Diagnostic Report

**Document Classification:** Engineering Due Diligence & Technical Integrity Audit  
**Repository:** `omarmomen1/quarter-car-dashboard` / SuspensionLab PRO  
**Datasets Analyzed:**  
1. `sample_data/aim_silverstone_session.csv` (AiM Sports CSV format)  
2. `sample_data/motec_spa_session.csv` (MoTeC CSV format)  
**Status:** **WITHHELD FROM EXTERNAL PUBLICATION — CALIBRATION NON-CONVERGENCE IDENTIFIED**

---

## 1. Executive Summary & Audit Finding

During technical review of the automated calibration pipeline, an internal inconsistency was identified:
The reported "calibrated" vehicle parameters were identical to the initial guess priors to five significant figures ($0.0\%$ relative change), while claiming high statistical identifiability ($t > 27.0$) and low holdout RMSE.

A deep forensic trace of `scripts/compute_calibration_results.py` and `src/suspensionlab/physics/parameter_identification.py` confirmed that **the optimizer did not converge or fit the parameters**. It aborted at iteration 0 (`nit = 0`) due to objective landscape pathologies, and the reporting pipeline inadvertently packaged the prior values and prior-evaluated Fisher curvature as an empirical fit.

This document formally records the root causes, the underlying data reality, and the exact steps required before any calibration claim can be made externally.

---

## 2. Root Cause Analysis

### Finding 1: L-BFGS-B Optimizer Aborted at Iteration 0 (`nit: 0`)
Running `scipy.optimize.minimize(..., method="L-BFGS-B")` on the forward ODE objective yields:
```
OptimizationResult:
  message: ABNORMAL: 
  success: False
   status: 2
      fun: 3.535946590166676
        x: [ 3.500e+04, 2.200e+03, 2.200e+05, 8.500e-01 ]
      nit: 0
      jac: [-1.082e+04, 3.470e+03, -3.477e+03, 9.194e+01]
     nfev: 105
     njev: 21
```
* **Discretization Noise from Adaptive ODE Solver:** The objective calls `solve_ivp(LSODA/RK45)` inside each loss evaluation. Numerical finite-difference perturbations ($\Delta p = 10^{-4} p$) across an adaptive-step ODE solver suffer from step-adaptation jitter. The numerical gradient is noisy, preventing the L-BFGS line search from finding a valid descent step.
* **Fallback Behavior:** Because the line search failed (`status: 2`), the optimizer returned `x0` unmodified. The code's fallback safeguard (`if mse_final_train > mse_initial: p_opt = p0`) ensured the nominal vector was retained.

### Finding 2: "Silverstone" and "Spa" Are Identical Mock Datasets
A direct bit-for-bit comparison between `sample_data/aim_silverstone_session.csv` and `sample_data/motec_spa_session.csv` reveals:
```
Max absolute difference (Damper_FL vs SuspTravel_FL): 0.000 mm
Max absolute difference (GPS_Speed vs Speed):          0.000 km/h
Max absolute difference (LatAcc vs G_Lat):             0.000 G
```
The two CSV files are not distinct track tests from the UK and Belgium; they are two alternative export header formats of the **exact same synthetic chassis simulation session** created to test DAQ ingestion parsers in the web cockpit.

### Finding 3: Orthogonal Target Signal Synthesis
In `compute_calibration_results.py`:
```python
# Synthesizing a target vertical channel from lateral acceleration:
'vert_g': df_aim['LatAcc'].values * 0.35 + 1.0
```
* `df['LatAcc'] * 0.35 + 1.0` has a static DC offset of $\approx 1.0\text{ G}$ and dynamics driven purely by cornering radius.
* `simulate_quarter_car_response` computes vertical sprung mass heave acceleration $\ddot{z}_s$ in $\text{m/s}^2$ driven by road profile displacement, with a zero mean.
* There is no physical correlation ($R^2 \approx 0.008$) between lateral cornering forces and vertical road heave. No combination of spring stiffness ($k_s$) or damping ($c$) can fit an orthogonal signal with a $1\text{g}$ offset.

### Finding 4: Spurious Confidence Intervals and Holdout Performance
* **Fisher Information ($J^T J$):** Because the optimizer returned $p_0$, the local Jacobian was evaluated at the nominal prior. Reporting $t = 31.0$ and tight confidence intervals was a mathematical artifact of evaluating local curvature at $p_0$, not empirical parameter identifiability.
* **Holdout RMSE:** The holdout window ($t = 40$ to $50\text{ s}$) happens to be a lower-acceleration straightaway in the synthetic drive cycle. The lower holdout RMSE was an accident of telemetry variance, not proof of model generalization.

---

## 3. Telemetry Channels & Raw Dataset Manifest

The two sample files in the repository have the following structure:

### Silverstone Format (`sample_data/aim_silverstone_session.csv`)
* **Rows:** 5,000 frames @ 100 Hz (50.0 s duration)
* **Headers:** `Time,GPS_Speed,LatAcc,InlineAcc,Damper_FL,Damper_FR,Damper_RL,Damper_RR,Brake_Front,Throttle`
* **First 3 Rows:**
  ```csv
  Time,GPS_Speed,LatAcc,InlineAcc,Damper_FL,Damper_FR,Damper_RL,Damper_RR,Brake_Front,Throttle
  0.0,180.0,0.0,-0.0,15.03,16.39,17.97,18.91,-0.0,50.0
  0.01,180.3,0.012,-0.007,17.3,17.23,19.12,19.77,0.0,50.3
  0.02,180.6,0.025,-0.014,17.69,17.56,20.64,19.84,0.0,50.6
  ```

### Spa Format (`sample_data/motec_spa_session.csv`)
* **Rows:** 5,000 frames @ 100 Hz (50.0 s duration)
* **Headers:** `Time,Distance,Speed,SteerAngle,G_Lat,G_Lon,SuspTravel_FL,SuspTravel_FR,SuspTravel_RL,SuspTravel_RR,BrakePress_F,ThrottlePos,EngineRPM`
* **First 3 Rows:**
  ```csv
  Time,Distance,Speed,SteerAngle,G_Lat,G_Lon,SuspTravel_FL,SuspTravel_FR,SuspTravel_RR,SuspTravel_RR,BrakePress_F,ThrottlePos,EngineRPM
  0.0,0.2,180.0,0.0,0.0,-0.0,15.03,16.39,17.97,18.91,-0.0,50.0,6687.0
  0.01,0.3,180.3,0.3,0.012,-0.007,17.3,17.23,19.12,19.77,0.0,50.3,6761.0
  0.02,0.5,180.6,0.61,0.025,-0.014,17.69,17.56,20.64,19.84,0.0,50.6,6667.0
  ```

---

## 4. Remediation Plan

To build a genuine empirical calibration that will withstand expert scrutiny:

1. **Target Real Channels with Direct Physical Observability:**
   Instead of attempting to fit an artificial vertical acceleration channel, calibrate against the **damper travel displacement channel** (`Damper_FL` / `SuspTravel_FL`), where the physical coupling between damper velocity and damper force is direct.
2. **Derivative-Free or Fixed-Step Integration:**
   Replace the finite-difference L-BFGS-B gradient over an adaptive solver with a derivative-free method (`Nelder-Mead`, `Powell`, or CMA-ES) or use a fixed-step Runge-Kutta integrator with analytic adjoint sensitivity equations.
3. **Genuine Track Telemetry Ingestion:**
   Clearly demarcate the mock sample files as synthetic parser test fixtures. Genuine vehicle validation requires actual logged vertical accelerometer channels ($z_{\text{acc}}$) and road lidar/profile data from real track sessions.
4. **Publish Only Converged Results:**
   Never publish parameter identification results where $\Delta \theta = 0.0\%$ or where the optimization status flag is non-zero.
