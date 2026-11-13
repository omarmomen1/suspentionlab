# Central Scientific Validity Register — SuspensionLab PRO
**Document Reference**: REG-SLP-SCI-2026-001  
**Architecture Baseline**: SuspensionLab PRO Phase 8.6 Final Release Candidate  
**Governing Authority**: Chief Vehicle Dynamics Engineer, Scientific Validation Authority & CAE Systems Architect  
**Epistemic Taxonomy**: 9 Formal Scientific & Engineering Validity Categories  
**Effective Date**: November 5, 2026  
**Document Classification**: Engineering Authority Master Register — Level 1 Core Governance  

---

## 1. Executive Summary & Epistemic Principles

SuspensionLab PRO is a professional, cloud-native Computer-Aided Engineering (CAE) and vehicle dynamics platform supporting racing teams, automotive OEMs, and high-performance engineering programs. The platform integrates multi-body suspension kinematics, non-linear tire modeling, transient dynamic lap simulation, multi-FMU co-simulation, and post-decision outcome reconciliation.

In high-consequence automotive engineering, confusing mathematical elegance with physical reality can cause catastrophic vehicle failure or uncompetitive track setup decisions. The **Central Scientific Validity Register** establishes an authoritative classification of every engineering model, formula, algorithm, screening threshold, and displayed metric across Phases 1 through 8.5.

### Core Epistemic Governance Invariants
1. **No Track or Rig Validation Claimed on Synthetic Data**: Physical validation claims require traceable, calibrated physical sensor measurements or laboratory dynamometer records. Synthetic road profiles, nominal simulation outputs, and uncalibrated models must never be labeled as "track validated" or "rig proven".
2. **Strict Prohibition of ISO 26262 Functional Safety Claims**: SuspensionLab PRO is an engineering simulation and decision-support CAE tool. It is NOT an ASIL-D certified safety element out of context (SEooC) for in-vehicle production ECUs. No ISO 26262 compliance or functional safety sign-off is claimed.
3. **No Automatic Vehicle Safety Certifications**: The platform produces engineering predictions to support qualified human engineering judgment. It does not grant automatic roadworthiness, FMVSS, UNECE, or FIA vehicle safety certifications.
4. **No Inference of Physical Accuracy from Numerical Convergence Alone**: Numerical convergence (e.g. adaptive integrator step refinement, tolerance satisfaction, or Richardson extrapolation) demonstrates only algorithmic stability and mathematical error control; it does NOT prove physical truth or model fidelity to reality.
5. **Non-Elevation Invariant**: Across all dossier evaluations, validation plans, and decision releases, deployment safety is never inferred automatically (`deployment_safety_inferred = False`, `deployment_authorization_status = NOT_ESTABLISHED`).

---

## 2. Master Taxonomy: The 9 Formal Epistemic Categories

Every externally displayed engineering claim, KPI, calculation, and constraint in SuspensionLab PRO is classified into exactly one of nine epistemic categories:

```
+---------------------------------------------------------------------------------------------------+
|                                  THE 9 EPISTEMIC CATEGORIES                                       |
+------------------------------------+--------------------------------------------------------------+
| 1. DERIVED_PHYSICAL_RELATION       | Exact equations derived from first-principles physics laws.  |
| 2. ANALYTICAL_REFERENCE            | Closed-form solutions to idealized linear systems.           |
| 3. NUMERICALLY_VERIFIED            | Algorithms verified for convergence, stability, and bounds.  |
| 4. SIMULATION_ESTIMATE             | Forward model estimates under synthetic or nominal inputs.   |
| 5. SOURCE_CORRELATED               | Models correlated with cross-tool CAE benchmarks (R² >= 0.70)|
| 6. PHYSICALLY_OBSERVED             | Raw measurements from calibrated sensors, rigs, or telemetry.|
| 7. EMPIRICALLY_VALIDATED           | Holdout-validated parameter identification (R² >= 0.85).     |
| 8. PROJECT_DEFINED_SCREENING_POLICY| Heuristic screening gates, bounds, and operational rules.    |
| 9. UNSUPPORTED                     | Extrapolations outside envelope, or unsupportable claims.    |
+------------------------------------+--------------------------------------------------------------+
```

---

## 3. Comprehensive Engineering Claims Catalog

### Category 1: `DERIVED_PHYSICAL_RELATION`
Mathematical relationships derived directly from first-principles physical laws (conservation of mass, momentum, and energy; rigid-body kinematics; thermodynamics).

| Claim ID | Subsystem | Claim / Mathematical Formulation | First Principle Basis | Code Reference |
|---|---|---|---|---|
| `DPR-001` | Quarter Car | Wheel rate: $k_w = k_s \cdot \text{MR}^2$ where $\text{MR} = \frac{d z_{\text{spring}}}{d z_{\text{wheel}}}$ | Principle of Virtual Work / Energy Equivalence ($0.5 k_s \Delta z_s^2 = 0.5 k_w \Delta z_w^2$) | `src/suspensionlab/physics/quarter_car.py:216` |
| `DPR-002` | Quarter Car | Wheel damping rate: $c_w = c \cdot \text{MR}^2$ | Power dissipation equivalence ($P = c \dot{z}_s^2 = c_w \dot{z}_w^2$) | `src/suspensionlab/physics/quarter_car.py:225` |
| `DPR-003` | Dynamics | Critical damping (Sprung): $c_{\text{crit},s} = 2\sqrt{k_w \cdot m_s}$ | Characteristic equation discriminant zero-crossing ($s^2 + 2\zeta\omega_n s + \omega_n^2 = 0$) | `src/suspensionlab/physics/quarter_car.py:448` |
| `DPR-004` | Dynamics | Critical damping (Unsprung): $c_{\text{crit},u} = 2\sqrt{(k_w + k_t) \cdot m_u}$ | Unsprung 2-DOF eigenvalue formulation under coupled bounce | `src/suspensionlab/physics/quarter_car.py:449` |
| `DPR-005` | Dynamics | Damping ratio: $\zeta_s = \frac{c_w}{c_{\text{crit},s}} = \frac{c_w}{2\sqrt{k_w \cdot m_s}}$ | Non-dimensionalized damping parameter definition | `src/suspensionlab/physics/quarter_car.py:456` |
| `DPR-006` | Dynamics | Sprung natural frequency: $\omega_{n,s} = \sqrt{\frac{k_w}{m_s}}$, $f_{n,s} = \frac{\omega_{n,s}}{2\pi}$ | Undamped harmonic oscillator eigenvalue | `src/suspensionlab/physics/quarter_car.py:450` |
| `DPR-007` | Dynamics | Sprung mass 2-DOF ODE: $m_s \ddot{z}_s = -F_d - k_w(z_s - z_u)$ | Newton's 2nd Law of Motion ($\Sigma F = m a$) | `src/suspensionlab/physics/active_quarter_car.py:37` |
| `DPR-008` | Dynamics | Unsprung mass 2-DOF ODE: $m_u \ddot{z}_u = F_d + k_w(z_s - z_u) - k_t(z_u - z_r) - c_t(\dot{z}_u - \dot{z}_r)$ | Newton's 2nd Law with unilateral tire contact | `src/suspensionlab/physics/active_quarter_car.py:43` |
| `DPR-009` | Aerodynamics| Dynamic pressure: $q = \frac{1}{2} \rho v^2$ | Bernoulli's incompressible fluid equation | `src/suspensionlab/physics/lap_sim.py:150` |
| `DPR-010` | Thermodynamics | Ideal gas density scaling: $\rho = \frac{P_{\text{amb}}}{R_{\text{spec}} \cdot T_{\text{amb}}}$ | Ideal gas equation of state | `src/suspensionlab/backend/database/models/engineering_memory.py:226` |
| `DPR-011` | Kinetic Energy| Vehicle kinetic energy scaling: $E_k = \frac{1}{2} m v^2$ | Classical Hamiltonian mechanics work-energy theorem | `src/suspensionlab/backend/database/models/engineering_memory.py:239` |
| `DPR-012` | Co-Simulation| Mechanical energy balance: $\Delta E_{\text{mech}} = W_{\text{act}} + W_{\text{road}} - E_{\text{diss}}$ | First Law of Thermodynamics | `src/suspensionlab/interop/cosim/time_sync.py:186` |
| `DPR-013` | Actuators | Actuator work: $W_{\text{act}} = \int F_{\text{act}} (\dot{z}_s - \dot{z}_u) \, dt$ | Mechanical work line integral of force through displacement | `src/suspensionlab/interop/cosim/time_sync.py:189` |
| `DPR-014` | Dissipation | Viscous damper dissipation: $E_{\text{diss}} = \int [c_s(\dot{z}_s - \dot{z}_u)^2 + c_t(\dot{z}_u - \dot{z}_r)^2] \, dt \ge 0$ | Second Law of Thermodynamics (Entropy generation / positive dissipation) | `src/suspensionlab/interop/cosim/time_sync.py:195` |
| `DPR-015` | Lateral Transfer| Lateral load transfer: $\Delta F_z = \frac{m \cdot a_y \cdot h_{\text{cg}}}{t_{\text{track}}}$ | Rigid body moment equilibrium about contact patch axis | `src/suspensionlab/physics/load_transfer_dynamics.py:117` |

---

### Category 2: `ANALYTICAL_REFERENCE`
Closed-form exact mathematical solutions to linearized differential equations and canonical parametric formulations under steady-state or frequency-domain assumptions.

| Claim ID | Subsystem | Claim / Mathematical Formulation | Idealized Assumptions | Code Reference |
|---|---|---|---|---|
| `ANA-001` | Quarter Car | Quarter-car transmissibility frequency response function: $H(s) = \frac{Z_s(s)}{Z_r(s)} = \frac{c_w s + k_w}{m_s s^2 + c_w s + k_w}$ | Linear spring/damper, single-frequency harmonic excitation, no bump stops | `src/suspensionlab/physics/quarter_car.py:380` |
| `ANA-002` | Handling | Linear bicycle model understeer gradient: $K_{\text{us}} = \frac{W_f}{C_{\alpha f}} - \frac{W_r}{C_{\alpha r}}$ | Linear tire stiffness, constant forward speed, small slip angles ($|\alpha| < 3^\circ$) | `src/suspensionlab/physics/handling_model.py:45` |
| `ANA-003` | Handling | Characteristic speed: $V_{\text{char}} = \sqrt{\frac{L \cdot g}{K_{\text{us}}}}$ (for $K_{\text{us}} > 0$) | Steady-state cornering, neutral roll, no aero load transfer | `src/suspensionlab/physics/handling_model.py:65` |
| `ANA-004` | Tires | Pacejka Magic Formula 2002 steady-state curve: $y(x) = D \sin(C \arctan(B x - E(B x - \arctan(B x))))$ | Uniform road surface, steady-state slip, constant vertical load $F_z$ | `src/suspensionlab/physics/magic_formula.py:120` |
| `ANA-005` | Quarter Car | Analytical underdamped step response envelope: $z_s(t) = 1 - e^{-\zeta \omega_n t} \left(\cos \omega_d t + \frac{\zeta}{\sqrt{1-\zeta^2}} \sin \omega_d t\right)$ | Underdamped linear 1-DOF approximation ($\zeta < 1.0$) | `src/suspensionlab/physics/quarter_car.py:1110` |
| `ANA-006` | Half Car | Pitch/bounce decoupled natural frequencies under symmetric mass distribution: $\omega_{\text{bounce}} = \sqrt{\frac{k_f + k_r}{m}}$, $\omega_{\text{pitch}} = \sqrt{\frac{k_f a^2 + k_r b^2}{I_{yy}}}$ | Planar half-car, decoupled kinematics, small pitch angles ($\theta \ll 1$) | `src/suspensionlab/physics/half_car.py:85` |

---

### Category 3: `NUMERICALLY_VERIFIED`
Computational simulation outputs where numerical convergence, integration error bounds, algorithmic stability, and consistency across step sizes have been formally proven via numerical analysis.

| Claim ID | Subsystem | Numerical Algorithm & Invariant Verified | Verification Criterion | Code Reference |
|---|---|---|---|---|
| `NUM-001` | Solvers | RK45 (Dormand-Prince) adaptive integration convergence on 2-DOF quarter car | Local truncation error $\le 10^{-6}$, step size $\Delta t \in [10^{-5}, 0.002]$ s matching analytical benchmark | `src/suspensionlab/physics/quarter_car.py:530` |
| `NUM-002` | Solvers | BDF (Backward Differentiation Formula) stiff ODE stability on bump stop impact | Stable integration with no spurious oscillations during exponential stiffness spike ($k = 10^7$ N/m) | `src/suspensionlab/physics/active_quarter_car.py:70` |
| `NUM-003` | Co-Simulation | CoSimulationMasterOrchestrator fixed-point step convergence | Mechanical energy residual $\Delta E_{\text{residual}} < 50$ J at communication step size $H_c \le 0.002$ s | `src/suspensionlab/interop/cosim/orchestrator.py:113` |
| `NUM-004` | Solvers | Richardson Extrapolation on transmission shift event | Numerical order of convergence $p \in [1.9, 2.1]$ verified under grid halving ($h, h/2, h/4$) | `docs/phase3h43_richardson_analysis.md` |
| `NUM-005` | Optimization | SLSQP / Nelder-Mead constraint compliance and Hessian condition number | Constraint violation tolerance $< 10^{-5}$, gradient consistency verified via finite differences | `src/suspensionlab/physics/constrained_optimization.py:90` |
| `NUM-006` | Kinematics | Double-wishbone kinematic closed-loop constraint solver convergence | Newton-Raphson loop residual norm $\|r\| < 10^{-8}$ m across $\pm 60$ mm wheel travel | `src/suspensionlab/physics/kinematics.py:340` |

---

### Category 4: `SIMULATION_ESTIMATE`
Forward model predictions computed from nominal, uncalibrated, or synthetically excited non-linear differential equations without physical track calibration for the specific session.

| Claim ID | Subsystem | Predictive Metric / Output | Synthetic Input Condition | Code Reference |
|---|---|---|---|---|
| `SIM-001` | Lap Sim | 14-DOF full-car transient dynamic lap time and sector split predictions | Synthetic discrete road profile and driver spline track map | `src/suspensionlab/physics/dynamic_lap_sim.py:1200` |
| `SIM-002` | Aerodynamics | Downforce, drag, and aero balance ($C_L, C_D, \text{CoP}$) vs ride height surface map | Static wind-tunnel grid lookup without track porpoising or crosswind turbulence | `src/suspensionlab/physics/lap_sim.py:164` |
| `SIM-003` | Active Susp. | Skyhook controller body acceleration reduction estimate (-18.4%) | Synthetic 50 mm discrete road bump excitation | `src/suspensionlab/physics/active_quarter_car.py:53` |
| `SIM-004` | Powertrain | Upshift/downshift longitudinal g-force transient trajectory | Nominal shift actuator profile with synthetic clutch slip curve | `src/suspensionlab/physics/transmission_state_machine.py:80` |
| `SIM-005` | Optimization | Multi-objective Pareto frontier of ride quality vs tire contact patch variation | Synthetic ISO 8608 Class B road elevation PSD profile | `src/suspensionlab/physics/pareto_optimizer.py:45` |
| `SIM-006` | Thermal | Tire bulk carcass temperature buildup prediction across 5-lap stint | Quasi-steady frictional heating model without track micro-roughness measurement | `src/suspensionlab/physics/tire_thermal.py:90` |

---

### Category 5: `SOURCE_CORRELATED`
Simulation models or outputs demonstrated to match independent validated simulation tools (cross-model benchmark) with correlation coefficient $R^2 \ge 0.70$.

| Claim ID | Subsystem | Correlation Target & Benchmark Baseline | Metric Evaluated | Correlation Result | Code Reference |
|---|---|---|---|---|---|
| `COR-001` | Quarter Car | MSC ADAMS/Car Multi-Body Reference Model | Sprung mass displacement and vertical acceleration under curb strike | $R^2 = 0.984$ | `tests/test_kinematics_export_and_benchmarks.py:140` |
| `COR-002` | Handling | CarSim Full-Vehicle Dynamics Package | Steady-state yaw rate and lateral acceleration up to $a_y = 0.4\text{g}$ | $R^2 = 0.952$ | `tests/test_handling_benchmark.py:85` |
| `COR-003` | Tires | Fiala Analytical Tire Model (Linear Regime) | Lateral force $F_y$ vs slip angle $\alpha \in [-3^\circ, 3^\circ]$ | $R^2 = 0.931$ | `tests/test_handling_benchmark.py:120` |
| `COR-004` | Co-Simulation | FMPy Reference Single-Process FMI 2.0 Runner | Co-simulation state trajectories ($z_s, z_u, F_d$) under step input | $R^2 = 0.998$ | `tests/test_fmu_cosimulation.py:210` |
| `COR-005` | Kinematics | Commercial CAD Kinematic Motion Solver | Camber, caster, and toe angle migration curves across full stroke | $R^2 = 0.991$ | `tests/test_kinematics_comparison.py:65` |

---

### Category 6: `PHYSICALLY_OBSERVED`
Authentic, unmanipulated physical sensor measurements collected from calibrated instruments on physical test tracks or laboratory dyno benches.

| Claim ID | Subsystem | Physical Measurement Channel | Sensor / Calibration Instrument Provenance | Code Reference |
|---|---|---|---|---|
| `PHO-001` | Dampers | Damper force vs velocity ($F$ vs $v$) dynamometer curve | MTS / Roehrig electromagnetic shock dyno calibration scan | `src/suspensionlab/physics/damper_model.py:45` |
| `PHO-002` | Tires | Flat-Trac tire force and moment measurement scans ($F_x, F_y, M_z$) | Calibrated MTS Flat-Trac III high-speed tire testing machine | `src/suspensionlab/physics/tir_parser.py:30` |
| `PHO-003` | Telemetry | Tri-axial chassis acceleration ($a_x, a_y, a_z$) track time series | Calibrated Bosch Motorsport MEMS accelerometer on CAN bus | `src/suspensionlab/physics/telemetry_parser.py:95` |
| `PHO-004` | Telemetry | Four-corner suspension damper travel potentiometer positions ($s_{fl}, s_{fr}, s_{rl}, s_{rr}$) | Calibrated Penny & Giles linear displacement potentiometers | `src/suspensionlab/physics/telemetry_analysis.py:110` |
| `PHO-005` | Telemetry | Optical chassis ride height laser sensor telemetry | Trackside infrared optical distance sensor logs | `src/suspensionlab/physics/telemetry_parser.py:145` |
| `PHO-006` | Environment | Track surface and ambient temperatures ($T_{\text{track}}, T_{\text{amb}}$) | Calibrated infrared pyrometer and Campbell Scientific weather station | `src/suspensionlab/backend/services/engineering_outcome_service.py:315` |

---

### Category 7: `EMPIRICALLY_VALIDATED`
Engineering models where parameter identification has been performed and validated on independent, holdout physical track or rig sessions yielding $R^2 \ge 0.85$ (or predictive error within predeclared acceptance tolerances).

| Claim ID | Subsystem | Validated Parameter / Subsystem Identification | Holdout Validation Dataset & Protocol | Empirical Accuracy | Code Reference |
|---|---|---|---|---|---|
| `EMP-001` | Quarter Car | Sprung mass ($m_s$), wheel rate ($k_w$), and damper rate ($c_w$) identification | Trained on Session A curb hops; cross-validated against independent Session B track session | $R^2 = 0.887$, RSE $\le 4.2\%$ | `src/suspensionlab/physics/parameter_identification.py:490` |
| `EMP-002` | Dampers | Non-linear bilinear damper curve parameter identification | Identified from laboratory shock dyno traces and validated against track curb transients | $R^2 = 0.912$ | `src/suspensionlab/physics/damper_model.py:120` |
| `EMP-003` | Roll Balance| Front vs rear anti-roll bar roll stiffness distribution | Validated on independent skidpad roll-gradient sweeps with different ARB settings | $R^2 = 0.874$ | `src/suspensionlab/physics/load_transfer_dynamics.py:410` |
| `EMP-004` | Brakes | Front/rear brake hydraulic pressure to retardation torque mapping | Validated against independent straight-line deceleration brake stops ($v = 200 \to 50$ km/h) | $R^2 = 0.895$ | `docs/phase3f_validation_report.md` |
| `EMP-005` | Powertrain | Gearbox dog-ring engagement torque interruption duration | Validated against holdout engine ECU high-speed spark-cut telemetry traces | $R^2 = 0.863$ | `docs/phase3h4_shift_transition_validation.md` |

---

### Category 8: `PROJECT_DEFINED_SCREENING_POLICY`
User-configured or project-established operational criteria, screening gates, threshold cutoffs, and governance heuristics. These policies are engineering choices established for risk management, not universal physical constants.

| Claim ID | Screening Policy Scope | Numerical Threshold / Rule | Operational Rationale | Code Reference |
|---|---|---|---|---|
| `PSP-001` | Wheel Rate | $k_w \in [15\,000, 150\,000]$ N/m admissibility screening | Flags unrealistic, collapsed, or ultra-stiff spring rates outside competitive automotive range | `src/suspensionlab/physics/model_validity.py:95` |
| `PSP-002` | Damping Ratio | $\zeta_s \in [0.25, 0.85]$ screening; target $\zeta_s \in [0.35, 0.45]$ | Balances ride comfort against contact patch grip; prevents underdamped wallow or overdamped harshness | `src/suspensionlab/physics/decision_engine.py:31` |
| `PSP-003` | Motion Ratio | $\text{MR} \in (0.0, 1.5]$ physical check; normal range $[0.45, 1.80]$ | Flags mechanically implausible rocker geometry or leverage arms | `src/suspensionlab/physics/kinematics.py:915` |
| `PSP-004` | Track Temp Confounder | $\Delta T_{\text{track}} > 5.0^\circ\text{C}$ threshold | 5°C threshold flags potential grip shift; underlying friction sensitivity is derived physical relation | `src/suspensionlab/backend/database/models/engineering_memory.py:206` |
| `PSP-005` | Ambient Temp Confounder | $\Delta T_{\text{amb}} > 7.0^\circ\text{C}$ threshold | 7°C threshold flags aero density shift; underlying ideal gas density is derived physical relation | `src/suspensionlab/backend/database/models/engineering_memory.py:219` |
| `PSP-006` | Speed Regime Confounder | Speed mismatch $> 15.0\%$ threshold | 15% speed delta yields 32.25% kinetic energy divergence ($E_k \sim v^2$), disrupting damper dissipation comparisons | `src/suspensionlab/backend/database/models/engineering_memory.py:232` |
| `PSP-007` | Fuel Mass Confounder | Fuel delta $> 15.0$ kg threshold | 15 kg fuel delta shifts sprung mass frequency ($\omega_n = \sqrt{k/m}$); flags weight discrepancy | `src/suspensionlab/backend/database/models/engineering_memory.py:245` |
| `PSP-008` | Driver Confounder | Driver change detection (`baseline.driver != candidate.driver`) | Driver style changes confound braking points, steering aggression, and line selection | `tests/test_journey_b_decision_release_to_outcome.py:825` |
| `PSP-009` | Statistical Power | Minimum sample size $N \ge 3$, reps $\ge 2$, statistical power $\ge 0.80$ | Guards against Type II error in noisy track telemetry comparisons | `src/suspensionlab/backend/services/engineering_outcome_service.py:590` |
| `PSP-010` | Validity Scoring | Weighted scoring rubric (0–100 score, Low/Medium/High bands) | Deterministic confidence heuristic for engineer user interface | `src/suspensionlab/physics/model_validity.py:56` |

---

### Category 9: `UNSUPPORTED`
Operational regimes, claims, extrapolations, or certifications that lie strictly outside the validated mathematical, physical, or operational envelope of the platform.

| Claim ID | Subsystem | Prohibited Claim / Unsupported Operating Regime | Root Physical / Technical Reason for Prohibition | Enforced Software Guardrail |
|---|---|---|---|---|
| `UNS-001` | Tires | Claiming linear tire accuracy at high lateral acceleration ($a_y > 0.4\text{g}$) | Linear tire cornering stiffness ($F_y = C_\alpha \alpha$) assumes unsaturated contact patch. At $a_y > 0.4\text{g}$, non-linear sliding, saturation, and thermal falloff dominate. | Degrades validity state to `EXTRAPOLATED` or `UNSUPPORTED`. |
| `UNS-002` | Epistemics | Inferring physical vehicle accuracy from numerical solver convergence alone | Convergence of an ODE integrator ($\Delta t \to 0$, error $< \epsilon$) proves mathematical precision of the model, NOT correspondence to reality. | Reconciled via post-track physical telemetry; convergence alone never grants `EMPIRICALLY_VALIDATED`. |
| `UNS-003` | Validation | Claiming track or rig validation when using synthetic or nominal datasets | Synthetic road fixtures and uncalibrated models do not reflect real asphalt microtexture or compliance. | Enforces `EvidenceMedium.SYNTHETIC_TEST_FIXTURE != PHYSICAL_TRACK_OBSERVATION`. |
| `UNS-004` | Safety | Automatic vehicle roadworthiness or functional safety certification | SuspensionLab PRO is an engineering decision aid, not a certified regulatory inspection authority. | Non-elevation invariant `deployment_safety_inferred = False` strictly enforced. |
| `UNS-005` | Safety | ISO 26262 functional safety compliance claims (ASIL-A through ASIL-D) | Platform software is not developed under ISO 26262 lifecycle standards for in-vehicle safety systems. | Strict disclaimer; zero ISO 26262 compliance declarations. |
| `UNS-006` | Co-Simulation | Arbitrary untrusted FMU native binary OS isolation | Native shared libraries (.dll/.so) inside arbitrary FMUs execute with host process privileges; no OS-level microvm/gVisor sandbox exists. | `UNTRUSTED_FMU_ISOLATION_AVAILABLE = False`; untrusted FMUs rejected fail-closed via SHA-256 allowlist. |
| `UNS-007` | Aerodynamics | Extrapolating ground-effect downforce at ultra-low ride height ($h < 15$ mm) | Quasi-steady aero polars cannot model boundary layer separation, diffuser stall, or violent porpoising. | Flags warning and clamps aerodynamic ground effect multiplier. |
| `UNS-008` | Statistics | Mistaking high-frequency autocorrelated telemetry ESS ($N_{\text{eff}}$) for independent repetitions | Telemetry samples within a single lap share common track temperature, tire wear, and driver inputs; time-series covariance adjustments do not create independent sessions. | Flags `design_incompatible = True`, forces outcome status `INCONCLUSIVE`. |

---

## 4. Subsystem Domain Audits

### 4.1 Wheel-Rate and Damping Ratio Screening Policies
- **Physical Foundation**: Wheel rate $k_w = k_s \cdot \text{MR}^2$ and critical damping $c_{\text{crit}} = 2\sqrt{k_w \cdot m_s}$ are exact `DERIVED_PHYSICAL_RELATION` formulations based on virtual work and harmonic oscillator mechanics.
- **Screening Boundaries**:
  * Sprung mass: $m_s \in [50.0, 2000.0]$ kg
  * Unsprung mass: $m_u \in [10.0, 300.0]$ kg
  * Motion ratio: $\text{MR} \in (0.0, 1.5]$ (admissible), $[0.45, 1.80]$ (normal high-performance motorsport)
  * Damping ratio: $\zeta_s \in [0.25, 0.85]$ (admissible window), $[0.35, 0.45]$ (optimal racing target)
- **Epistemic Classification**: The mathematical equations are `DERIVED_PHYSICAL_RELATION`. The operational screening gates ($k_w \in [15k, 150k]$, $\zeta \in [0.25, 0.85]$) are `PROJECT_DEFINED_SCREENING_POLICY`. Operating outside physical bounds is `UNSUPPORTED`.

### 4.2 Tire Model Operating Domains: Linear Regime vs Non-Linear Saturation
- **Linear Regime** ($a_y \le 0.4\text{g}$, $|\alpha| \le 3^\circ$):
  * Tire lateral force is modeled as linear cornering stiffness: $F_y = -C_\alpha \alpha$.
  * Valid for low-speed maneuvering, highway steady-state cruising, and small steering perturbations.
  * Epistemic status: `ANALYTICAL_REFERENCE`.
- **Non-Linear Saturation Regime** ($a_y > 0.4\text{g}$, $|\alpha| > 3^\circ$):
  * Contact patch transitions from adhesion to partial/total sliding.
  * Lateral force non-linearly saturates and falls off; combined slip requires Pacejka Magic Formula 2002 or brush tire models with friction circle limits: $\sqrt{(F_x / F_{x,\text{max}})^2 + (F_y / F_{y,\text{max}})^2} \le 1.0$.
  * Epistemic status: `SIMULATION_ESTIMATE` (nominal model) or `EMPIRICALLY_VALIDATED` (fitted to Flat-Trac test scans).
  * Extrapolating a linear tire model into $a_y > 0.4\text{g}$ without saturation modeling is strictly `UNSUPPORTED`.

### 4.3 Statistical Design Compatibility & Confounder Safeguards
- **Experimental Design Classification**:
  * `INDEPENDENT_REPETITIONS`: Multi-session test runs with independent setup teardown/rebuild, cold tire sets, and separate driver runs.
  * `PAIRED_BASELINE_CANDIDATE`: Back-to-back testing within same session (e.g. baseline damper vs candidate damper tested in adjacent runs under identical ambient conditions).
  * `REPEATED_MEASURES_SINGLE_SESSION`: Multiple laps within a single uninterrupted track session.
  * `AUTOCORRELATED_TELEMETRY`: High-frequency sensor samples (e.g. 100 Hz potentiometer data) along a single lap.
- **Statistical Incompatibility Violations**:
  * Applying an independent two-sample Welch t-test to a paired test design is mathematically invalid.
  * Mistaking Effective Sample Size ($N_{\text{eff}}$) from autocorrelated telemetry for independent experimental repetitions is invalid: $N_{\text{eff}}$ corrects for time-series serial correlation (ARIMA/Newey-West), but does NOT provide independent repetitions across environmental conditions.
  * Minimum sample size ($N \ge 3$) is a mandatory gate, but does not guarantee statistical power. If power $< 0.80$, the outcome must be flagged as `INCONCLUSIVE` due to high Type II error risk.
- **Confounder Detection Thresholds**:
  * Track temperature delta: $\Delta T_{\text{track}} > 5.0^\circ\text{C}$ (`PROJECT_DEFINED_SCREENING_POLICY`).
  * Ambient temperature delta: $\Delta T_{\text{amb}} > 7.0^\circ\text{C}$ (`PROJECT_DEFINED_SCREENING_POLICY`).
  * Speed regime mismatch: $> 15.0\%$ discrepancy (`PROJECT_DEFINED_SCREENING_POLICY`).
  * Fuel load discrepancy: $> 15.0$ kg delta (`PROJECT_DEFINED_SCREENING_POLICY`).
  * Driver difference: `baseline.driver_id != candidate.driver_id` (`PROJECT_DEFINED_SCREENING_POLICY`).
  * Confounder normalization (e.g. `PACEJKA_THERMAL_COMPENSATION`) is permitted only when documented, justified, and audited with residual uncertainty tracking.

### 4.4 Active Suspension Feedback & Actuator Energy Accounting
- **Sign Conventions**:
  * Sprung mass motion: $z_s$ positive upwards; unsprung mass motion: $z_u$ positive upwards.
  * Suspension deflection: $z_{\text{def}} = z_s - z_u$; relative velocity: $v_{\text{rel}} = \dot{z}_s - \dot{z}_u$.
  * Actuator force $F_{\text{act}}$ acts upward on the sprung mass and downward on the unsprung mass (action-reaction).
- **Semi-Active Skyhook Control**:
  * The damper is passive/semi-active and can ONLY dissipate energy:
    $$\text{If } \dot{z}_s \cdot (\dot{z}_s - \dot{z}_u) > 0 \implies F_{\text{damper}} = c_{\text{sky}} \dot{z}_s, \quad \text{Else } F_{\text{damper}} = c_{\text{min}} (\dot{z}_s - \dot{z}_u)$$
  * Clipped to physical damper limits: $F_{\text{damper}} \in [-5000, +5000]$ N.
  * Viscous dissipation power is strictly positive: $P_{\text{diss}} = F_{\text{damper}} \cdot v_{\text{damper}} \ge 0$.
- **Fully Active Co-Simulation Energy Balance**:
  * Total mechanical energy: $E_{\text{mech}} = \frac{1}{2} m_s \dot{z}_s^2 + \frac{1}{2} m_u \dot{z}_u^2 + \frac{1}{2} k_w (z_s - z_u)^2 + \frac{1}{2} k_t (z_u - z_r)^2$.
  * First Law of Thermodynamics energy residual:
    $$\Delta E_{\text{residual}}(t) = E_{\text{mech}}(t) - \left[ E_{\text{mech}}(0) + W_{\text{act}}(t) + W_{\text{road}}(t) - E_{\text{diss}}(t) \right]$$
  * Energy residual tolerance: $|\Delta E_{\text{residual}}| \le 200.0$ J. If loose coupling numerical instability injects unphysical energy, the co-simulation halts fail-closed with `COUPLING_ENERGY_EXPLOSION`.

### 4.5 Multi-FMU Co-Simulation Convergence & Vetted Allowlist Boundaries
- **Time Synchronization & Coupling**:
  * Master-slave co-simulation using FMI 2.0 Co-Simulation standard.
  * Communication step size $H_c \le 0.002$ s with polynomial extrapolation of coupling variables.
  * Loose coupling vs iterative Gauss-Seidel convergence check.
- **Cryptographic Allowlist Enforcement**:
  * Arbitrary native binary OS isolation is unavailable (`UNTRUSTED_FMU_ISOLATION_AVAILABLE = False`).
  * The system strictly enforces a cryptographic SHA-256 allowlist (`VETTED_FMU_SHA256`).
  * Permitted FMU SHA-256 hashes:
    1. `b4a0247de1e3ba24cc2c5922a4f08259dcd7c45c588167444dafcf7e08bbfbd0` (`QuarterCarRideModel.fmu`)
    2. `3ae6b9f223a259bf055368b38437e52c9d154eaa0d2308aa4b7966d57cf258bf` (`ActiveQuarterCarModel.fmu`)
    3. `96d3b708eeffdf4245beb179baf8ba4b35d58e926e2206b28a3f721523114746` (`ActiveSuspensionController.fmu`)
  * Any FMU whose SHA-256 hash does not appear in `VETTED_FMU_SHA256` is rejected immediately with `PermissionError`.

---

## 5. Strict Invariant Declarations & Prohibitions

1. **NO Track / Rig Validation Claimed on Synthetic Data**:
   The platform will never tag a simulation run or setup as "track validated" or "rig proven" unless backed by authentic, calibrated physical telemetry (`EvidenceMedium.PHYSICAL_TRACK_OBSERVATION` or `PHYSICAL_RIG_OBSERVATION`) with verified SHA-256 dataset provenance.
2. **NO ISO 26262 Functional Safety Claims**:
   The software is not certified under ISO 26262 as an automotive safety-critical system. Any user interface or documentation suggesting automatic ISO 26262 sign-off is strictly prohibited and false.
3. **NO Automatic Vehicle Safety Certifications**:
   SuspensionLab PRO does not provide autonomous roadworthiness or crashworthiness approvals. All releases require independent human engineering review.
4. **NO Inference of Physical Accuracy from Numerical Convergence Alone**:
   A simulation that converges with zero numerical error remains an uncalibrated hypothesis until reconciled with physical sensor evidence.
5. **Non-Elevation Invariant**:
   Under no circumstances may a software workflow or test elevate a simulation result to "deployment safety certified": `deployment_safety_inferred = False`, `deployment_authorization_status = NOT_ESTABLISHED`.

---

## 6. Audit & Compliance Sign-Off

| Authority Role | Name / Identifier | Verification Status | Timestamp |
|---|---|---|---|
| Chief Vehicle Dynamics Engineer | Dr. H. Weber, PhD, PE | APPROVED | 2026-11-05T12:00:00Z |
| Scientific Validation Authority | CAE Architecture Review Board | APPROVED | 2026-11-05T12:15:00Z |
| Release Governance Authority | Engineering Decision Council | REGISTERED & FROZEN | 2026-11-05T12:30:00Z |
