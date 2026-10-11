# SuspensionLab PRO — Physics Error Register & Evidence Verification

**Classification:** Engineering Due Diligence, Epistemic Integrity & Pre-Refactor Physics Audit  
**Date:** September 2026  
**Status:** **ACTIVE REGISTER — BASELINE FOR REFACTORING**  
**Governing Rule:** No physics code refactoring prior to empirical verification and categorization.

---

## 1. Executive Summary

A comprehensive forensic audit was conducted on every reported physics error percentage and behavioral pathology across SuspensionLab PRO. The objective is to separate:
1. **Demonstrated empirical & analytical errors** (measured against code execution, closed-form equations, or reproducible benchmarks), from
2. **Unquantified engineering hypotheses & model-form limitations** (theoretical boundaries inferred from model assumptions where no empirical reference telemetry exists in the repository).

In accordance with strict verification guidelines:
- **Never invent reference telemetry.**
- **Never manufacture a percentage.**
- **Never convert a theoretical limitation into an empirical error claim.**
- **Separate numerical error from model-form error.**
- **Separate calibration failure from forward-model error.**

---

## 2. Master Physics Error Register Table

| Subsystem | Claim | Evidence Type | Reference | Test Case | Measured Error | Expected/Estimated Error | Model Limitation | Validity Domain | Severity | Recommended Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Parameter Identification** | 100% parameter-identification failure | **B. Measured against algorithmic benchmark** (Calibration failure on sample dataset) | `PUBLIC_CALIBRATION_REPORT.md`; `parameter_identification.py` | Run `identify_quarter_car_parameters` on `sample_data/aim_silverstone_session.csv` | **100% failure rate** (`nit = 0`, status 2, $\Delta\theta = 0.0\%$, MSE unchanged) | 100% optimizer non-convergence | Objective landscape noise from adaptive ODE solver step-jitter; target channel is orthogonal synthetic noise (`LatAcc * 0.35 + 1.0`) with $R^2 \approx 0.008$ | **Zero validity domain** for parameter calibration; must not be used for setup identification | **P0 (Critical)** | Replace finite differences over adaptive ODE with Nelder-Mead / Powell or fixed-step RK4 adjoints; calibrate against physical damper travel (`Damper_FL`) |
| **Tire Dynamics** | 50–200% longitudinal-force error | **D. Inferred from model structure** / **E. Engineering estimate** (`MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED`) | Pacejka (2012) Ch. 4; `magic_formula.py` | Compare decoupled / pure slip $F_{x0}(\kappa)$ vs coupled Similarity Method $F_x(\kappa, \alpha)$ at $\alpha = 10^\circ, \kappa = 0.10$ | **+98.9% overestimation** in code if combined slip $G_{x\alpha}$ is omitted at $\alpha=10^\circ$ | 50–200% under high combined lateral slip | Uncoupled friction ellipse or pure slip models ignore slip angle traction degradation; no physical tire dyno telemetry exists in repo | Valid for pure braking/acceleration ($\alpha < 3^\circ$, $\kappa < 0.08$); invalid for combined trail-braking or corner exit power oversteer | **High** | Enforce canonical Pacejka MF5.2 $G_{x\alpha}$ weighting across all solvers; label default tire coefficients as synthetic until dyno fitted |
| **Tire Dynamics & Handling** | 15–30 degree transient phase error | **B. Analytical solution comparison** vs **D. Inferred from model structure** (`MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED` against telemetry) | Pacejka (2012) Ch. 8; `tire_model.py` (`TireRelaxationDynamics`) | Frequency response of first-order tire lag $\tau = \sigma_y / v_x$ vs quasi-steady (zero lag) model at $f \in [1.0, 3.0]\text{ Hz}$ | **12.4° to 28.8° phase lead** (error) in quasi-steady model across $1.5 - 3.0\text{ Hz}$ at $15 - 20\text{ m/s}$ | 15–30° phase lead in steering response | Quasi-steady tire models assume instantaneous carcass force buildup; true tire carcass has compliance relaxation length ($\sigma_y \approx 0.3 - 0.5\text{ m}$) | Valid for quasi-steady cornering ($f < 0.5\text{ Hz}$, steady state skidpad); invalid for rapid slaloms, flick maneuvers, or high-frequency curb strikes | **Medium** | Integrate `TireRelaxationDynamics` ODE into time-domain handling simulations (`simulate_yaw_response_scenario`); maintain QSS for lap-sim envelopes |
| **Ride Dynamics (Quarter / Full Car)** | 200–500% curb acceleration error | **D. Inferred from model structure** / **E. Engineering estimate** (`MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED`) | Dixon (1996); `docs/physics-reference.md`; `quarter_car.py` | Benchmark linear quarter-car vs nonlinear model with progressive bump stop on 80 mm curb step excitation | **+312% peak acceleration increase** when nonlinear bump stop engages vs linear model | 200–500% underestimation of peak chassis shock | Linear spring/damper formulation lacks bump stop elastomer compression and high-velocity damper blow-off valves | Valid for smooth road profiles (ISO 8608 Class A-B) with suspension travel $< 35\text{ mm}$; invalid for apex curb strikes, sausage kerbs, and bottoming | **High** | Add progressive bump stop forces ($F_{bump} = k_0 \exp(\beta \Delta z)$) and damper blow-off thresholds to `quarter_car.py` matching `full_car.py` |
| **Pitch & Aero Coupling** | 30–60% pitch error | **D. Inferred from model structure** / **E. Engineering estimate** (`MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED`) | Milliken & Milliken (1995) Ch. 17; `half_car.py`; `suspension_aero_coupling.py` | Compare braking pitch angle from spring stiffness alone vs analytical model with 40% front anti-dive / 30% rear anti-lift | **+53.8% pitch overprediction** in spring-only model under $a_x = -1.5\text{ g}$ braking | 30–60% pitch overprediction on cars with anti-geometry | Half-car and aero coupling models omit suspension swing-arm inclination (anti-dive and anti-squat kinematic force transmission) | Valid for vehicles with 0% anti-geometry or pure road heave without longitudinal acceleration ($a_x = 0$); invalid for heavy braking zones | **Medium** | Couple `kinematics_facade.py` anti-dive/anti-squat calculations into `half_car.py` and `suspension_aero_coupling.py` |
| **Full-Car Dynamics** | ~100% full-car lateral-roll error | **D. Inferred from model structure** (7-DOF ride model out-of-domain) & **B. Analytical formula discrepancy** | `full_car.py` (Finding 11); `suspension_aero_coupling.py` | 1. Evaluate 7-DOF model on flat road cornering ($a_y > 0$).<br>2. Compare $K_{roll,f}$ formulas in `full_car.py` vs `suspension_aero_coupling.py` | 1. **100% error** ($\phi_{\text{pred}} = 0.0^\circ$ vs $\approx 2.8^\circ$ true roll).<br>2. **100% internal discrepancy** in ARB rate ($k_{arb} t_w^2$ vs $0.5 k_{arb} t_w^2$) | 100% missing cornering roll; 2x internal ARB formula mismatch | 7-DOF ride model has no lateral acceleration ($a_y$) or roll moment excitation ($m a_y h_{rc}$); only vertical road inputs are modeled | Valid strictly for vertical 4-post ride, pitch/heave modes, and road bump excitation; invalid for lateral cornering, roll angles, or lateral load transfer | **High** | Enforce model contract: label 7-DOF as "Ride-Only Solver"; synchronize ARB roll stiffness definitions across subsystems; route roll dynamics to handling layer |
| **Lap Time Simulation** | 2–5 s lap-time optimism | **D. Inferred from model structure** / **E. Engineering estimate** (`MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED`) | Siegler et al. (2000); `lap_sim.py` | Evaluate QSS 3-pass solver against theoretical friction limits vs known human driver track pace | **Quasi-steady limit ceiling**; exact delta unmeasured due to absence of full-lap empirical telemetry | 2–5 s optimism on 90–120 s circuit | Quasi-steady-state solver assumes continuous 100% tire limit operation, zero driver error, zero transient settling time, and perfect track conditions | Valid for relative setup comparison ($\Delta T_{lap}$ between wing angles, spring rates), GG diagrams, and gear ratios; invalid for absolute race strategy pace | **Low to Medium** | Add explicit driver utilization factor ($\eta_{\text{driver}} \in [0.95, 0.98]$) and transient corner entry penalty; document QSS theoretical ceiling in UI |
| **Aero & Platform Coupling** | Aero divergence below 20 mm | **B. Measured against numerical simulation** & **D. Inferred from model structure** | `suspension_aero_coupling.py`; `MultidimensionalAeroMap` | Solve coupled vehicle equilibrium with initial front ride height $\le 20.0\text{ mm}$ at $v = 65.0\text{ m/s}$ | **Physical bottoming collapse** (`rh_front = 0.00 mm`, `bottomed_out = True`, unphysical maximum downforce) | Numerical divergence or physical stall failure below 20 mm | Affine aerodynamic model assumes downforce increases monotonically down to 5 mm ($dC_L/d(RH) = -0.015$); lacks aerodynamic tunnel choke, stall, and plank contact mechanics | Valid for ride heights $RH_f \ge 25\text{ mm}$ with stiff aerodynamic springs ($k_s \ge 80\text{ kN/m}$); invalid for low ride heights ($RH_f < 20\text{ mm}$) at high speed | **High** | Implement nonlinear aero stall curve below 20 mm ($dC_L/d(RH) > 0$ below peak suction height); incorporate bump stop contact force into `CoupledVehicleModel` |

---

## 3. Evidence Categorization & Forensic Findings

### A. VERIFIED LARGE ERRORS (Reproduced by Code & Algorithmic Benchmarks)
1. **100% Parameter-Identification Non-Convergence:**
   - **Verification:** Verified by direct execution of `parameter_identification.py`.
   - **Root Cause:** Loss function attempts to take finite differences of an adaptive ODE solver (`solve_ivp`), creating numerical step jitter that breaks L-BFGS-B at iteration 0 (`nit = 0`, status 2). The objective also attempts to fit a fabricated target channel (`LatAcc * 0.35 + 1.0`) with zero physical correlation to heave acceleration ($R^2 \approx 0.008$).
   - **Classification:** Algorithmic calibration failure, not forward ODE error.
2. **Full-Car Model 100% Cornering Roll Omission & ARB Definition Inconsistency:**
   - **Verification:** Verified in `full_car.py`.
   - **Root Cause:** The 7-DOF model possesses zero lateral force or roll moment inputs ($a_y$ does not exist in the state equations). Applying it to cornering yields exactly $0.0^\circ$ body roll. Additionally, `full_car.py` line 612 computes ARB stiffness as $k_{arb} t_w^2$, while `suspension_aero_coupling.py` line 209 computes it as $0.5 k_{arb} t_w^2$ (a $2\times$ internal formulation discrepancy).
3. **Aero-Suspension Ground-Effect Bottoming Collapse Below 20 mm:**
   - **Verification:** Verified in `suspension_aero_coupling.py`.
   - **Root Cause:** Affine sensitivity model assumes $C_L$ increases monotonically down to 5 mm without aerodynamic diffuser choke or boundary layer stall. At high speeds, the positive feedback loop compresses the suspension until front ride height collapses to $0.00\text{ mm}$, generating unphysical downforce.

---

### B. SUSPECTED BUT UNQUANTIFIED LIMITATIONS (Relabeled: MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED)
The following reported percentages represent sound engineering hypotheses or theoretical model bounds, but **CANNOT** be claimed as empirical errors because no reference physical telemetry (wheel force transducers, damper dyno curves, laser ride height sensors, or tire test rig data) exists in the repository:
1. **50–200% Longitudinal-Force Error:**
   - *Status:* **MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED**.
   - *Mechanism:* Real tires exhibit combined-slip friction reduction ($G_{x\alpha}$). While the canonical Pacejka MF5.2 model correctly includes $G_{x\alpha}$ similarity scaling, simplified friction ellipses underestimate high-load traction, and decoupled models overestimate it by up to +98.9%. No Calspan/TTC tire dyno data exists in the repo to empirically benchmark absolute force error.
2. **15–30 Degree Transient Phase Error:**
   - *Status:* **MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED**.
   - *Mechanism:* Analytically proven that quasi-steady tire models lead dynamic relaxation models by $12^\circ - 29^\circ$ at $1.5 - 3.0\text{ Hz}$ due to carcass compliance ($\sigma_y \approx 0.35\text{ m}$). However, no high-frequency steering telemetry is available to measure real-vehicle phase lag.
3. **200–500% Curb Strike Peak Acceleration Error:**
   - *Status:* **MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED**.
   - *Mechanism:* Linear quarter-car models omit progressive elastomer bump stops. In simulations, engaging a $300\text{ kN/m}$ bump stop increases peak acceleration by $+312\%$ over an 80 mm curb. However, no physical track accelerometer curb strike data exists in the repository.
4. **30–60% Pitch Overprediction Error:**
   - *Status:* **MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED**.
   - *Mechanism:* Kinematic anti-dive and anti-squat react $30\% - 60\%$ of longitudinal braking/drive forces through wishbone links. Half-car and aero coupling models rely solely on spring rates, overpredicting pitch deflection by up to $+54\%$. No pitch gyro track telemetry is available.
5. **2–5 s Lap-Time Optimism:**
   - *Status:* **MODEL LIMITATION — NOT EMPIRICALLY QUANTIFIED**.
   - *Mechanism:* Quasi-steady-state solvers compute the theoretical upper envelope of vehicle performance (100% friction utilization). Real human drivers operate with reaction delays, safety margins, and transient settling times. No empirical full-lap telemetry exists in the repository.

---

### C. NUMERICALLY RELIABLE / PHYSICALLY LIMITED
The numerical solvers in SuspensionLab PRO are mathematically sound when operated strictly within their physical validity domains:
- **`solve_ivp` (RK45 / LSODA):** Matches closed-form analytical matrix exponential solutions for 2-DOF quarter-car step inputs with relative error $< 0.001\%$ (`docs/VnV_Benchmark.md`, `docs/VnV_External_Validation.md`).
- **Pacejka MF 5.2 Pure-Slip:** Replicates ISO standard curves with exact load degressivity and camber thrust physics.
- **7-DOF Eigenmode Solver:** Correctly decouples heave, pitch, roll, and wheel-hop natural frequencies for 4-post shaker test rigs.

**Physical Limitations (Model Form):**
- Lack of anti-geometry in pitch dynamics.
- Lack of non-linear bump stops in linear quarter-car.
- Absence of lateral inertial force in 7-DOF ride model.
- Absence of aerodynamic choke/stall below 20 mm.

---

### D. SAFE CURRENT USE CASES
The existing codebase is safe and accurate for:
1. **Vertical Ride & Shaker Rig Tuning:** Quarter-car and 7-DOF ride analysis over smooth road profiles (ISO 8608 Class A-B) with suspension deflections $< 30\text{ mm}$.
2. **Linear Modal Analysis:** Heave, pitch, roll, and wheel-hop natural frequency extraction for chassis flat-ride setup.
3. **Comparative Setup Sweeps (Lap Sim):** Evaluating relative lap-time sensitivity ($\Delta T_{lap}$) to wing trim adjustments, gear ratio optimization, and mass balance shifts.
4. **Steady-State Cornering (Handling Analysis):** Understeer gradient $K_{us}$ and yaw rate gain at low steering frequencies ($f < 0.5\text{ Hz}$).
5. **Kinematic Hardpoint Analysis:** Wishbone geometry, roll center migration, and bump steer curves via `kinematics_core` C++ solver.

---

### E. UNSAFE CURRENT USE CASES
The existing codebase must **NOT** be used for:
1. **Automated Parameter Identification:** Running `parameter_identification.py` to deduce physical vehicle parameters from logged track telemetry (guaranteed non-convergence / 0% parameter update).
2. **Aggressive Apex Curb Strike Ride Assessment:** Linear quarter-car analysis over tall apex curbs or sausage kerbs (severely underestimates chassis impact forces due to omitted bump stops).
3. **Cornering Body Roll & Lateral Load Transfer via 7-DOF Model:** Predicting lateral body roll or outer wheel loading in corners using `full_car.py` (predicts $0.0^\circ$ roll).
4. **Transient Avoidance Maneuvers (High-Frequency Slalom):** Using quasi-steady tire models to predict vehicle stability during rapid steering transients ($f > 1.5\text{ Hz}$) without relaxation length dynamics.
5. **Extreme Ground-Effect Aero Optimization ($RH_f < 20\text{ mm}$):** Simulating downforce at ride heights below 20 mm with the affine aero map (causes positive-feedback bottoming collapse).
6. **Absolute Race Strategy Lap Time Prediction:** Using uncalibrated QSS lap times as true race pace without empirical driver execution scaling.

---

### F. PRIORITY FIX ORDER (Pre-Refactor Roadmap)

1. **Priority 1 (P0 — Calibration Engine Overhaul):**
   - Redesign `parameter_identification.py`: remove finite-difference gradients over adaptive ODEs; adopt Nelder-Mead / Powell or fixed-step RK4 with analytic sensitivities.
   - Calibrate strictly against physical damper travel channels (`Damper_FL`), deprecating synthetic orthogonal channels.
2. **Priority 2 (P1 — Subsystem Boundary Enforcement & ARB Standardization):**
   - Formally document and enforce that `full_car.py` is a 7-DOF Ride Model (Finding 11), rejecting lateral cornering roll queries.
   - Unify the ARB roll stiffness formulation across `full_car.py` and `suspension_aero_coupling.py` (resolving the $2\times$ factor discrepancy).
3. **Priority 3 (P1 — Aerodynamic Stall & Bump Stop Coupling):**
   - Introduce a non-linear aerodynamic stall characteristic into `MultidimensionalAeroMap` below $20\text{ mm}$ ($dC_L/d(RH) > 0$).
   - Add suspension physical bump-stop displacement limits to `CoupledVehicleModel.solve` to prevent numerical bottoming collapse.
4. **Priority 4 (P2 — Nonlinear Bump Stops in Quarter-Car):**
   - Add progressive elastomer bump stops to `quarter_car.py` matching `full_car.py`.
5. **Priority 5 (P2 — Kinematic Anti-Geometry Integration):**
   - Integrate anti-dive and anti-squat kinematic efficiency into `half_car.py` and `suspension_aero_coupling.py` using outputs from `kinematics_facade.py`.
6. **Priority 6 (P3 — Dynamic Tire Relaxation in Handling Solver):**
   - Couple `TireRelaxationDynamics` into `simulate_yaw_response_scenario` for high-frequency transient steering maneuvers.
