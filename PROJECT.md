# Project: ApexSim Wave 2 Physics, Calibration, Validation, Interop & AI Services Remediation

## Architecture
- **Physics Core (`src/suspensionlab/physics/`)**: Quarter car, damper models, active suspension, load transfer dynamics, full car 7-DOF/14-DOF, kinematics, yaw dynamics, Magic Formula 5.2 tire dynamics, TIR parser, quasi-steady & dynamic closed-loop lap simulator.
- **Validation & Calibration (`src/suspensionlab/validation/`, `src/suspensionlab/physics/`)**: Signed Nash-Sutcliffe Efficiency (NSE) residual engine, telemetry parameter identification, holdout data hash sequestration, model validity.
- **Interop & CAE Adapters (`src/suspensionlab/interop/`, `src/suspensionlab/runners/`)**: MSC Adams export & external CAE runner, MATLAB/Simulink state-space export, PAC2002 TIR tire adapter.
- **Analytics, Optimization & AI Services (`src/suspensionlab/analytics/`, `src/suspensionlab/services/`, `src/suspensionlab/backend/`)**: Setup intelligence, COBYLA optimization honesty, transfer function Bode plots, race engineer heuristics/event metrics, Pareto front non-dominated sorting, physics-facing routes and unified background workers.
- **Mirroring & Target Test Suite**: `backend_vercel/src/suspensionlab/` parity and comprehensive pytest suite covering all remediation items.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | S1 Damper & Contact | `damper_model.py:383` MR^2 scaling, `active_quarter_car.py:48-50` unilateral contact, `quarter_car.py:786,1006` C1 bump-stop continuation & NaN on ODE failure, `load_transfer_dynamics.py:226-233` axle load redistribution, `full_car.py:405` comment & `kinematics.py:579,690` forward diff index 0 | M1 | Survey 1 |
| 2 | S2/S8 Yaw & Tires | `yaw_dynamics.py:148-153,204-210` neutral/critical speed & yaw rate denom, `magic_formula.py:239,440,455` qDz9/qBz10 arrays & qBz3 fix, `tir_parser.py:195-248` missing parameter export, `vnv/framework.py:300-309` TIRE-COMB-005 <=1.00% fix & genuine solver checks | M2 | Survey 2 |
| 3 | S2/S8 Lap Sim Physics | `lap_sim.py:2263` potential & kinetic energy balance inclusion, short track guard, fix 4 failing tests (mass monotonicity fz_nom_n constant 4000N, recommended setup, sector sum exact float & straight decay clamp), ARB units & ISO 8855 sign harmonization | M2 | Survey 2 |
| 4 | S3 Calibration & Validation | Signed Nash-Sutcliffe Efficiency in `residual_engine.py:258-268` & `residual_analysis.py:169-180`, `parameter_identification.py:461-487` explicit road input `z_r`, `holdout.py:86-99,251-263` `arr.tobytes()` hashing & sequestration verification | M3 | Survey 3 |
| 5 | S3 Interop & CAE | Adams part IDs (`PART/2`, `PART/3`) / spring-damper parsing / unilateral contact in `external_cae_solver.py:143-146`, MATLAB/Simulink row 4 negation in `matlab_simulink.py:150,156`, PAC2002 16-coeff ingestion & dimensionless pKy1/pKx1 in `tir_tire.py:109,172` | M3 | Survey 3 |
| 6 | S3 Analytics & Optimization Honesty | `setup_intelligence.py:259` remove fake demo branch, `optimizer.py:109` COBYLA sol.success honesty, `model_validity.py:92` c >= 0 check, `advanced_plots.py:60` frequency TF magnitudes, heuristic metrics clarity, `pareto_optimizer.py:170` None guard | M3 | Survey 3 |
| 7 | S4 Routes & Workers | `routes/simulate/full_car.py:33` & `workers/unified_worker.py:284` pass damper curves & convert lateral accel m/s2 to g, `routes/optimize.py:314` pass road speed/iso_class, `ai_race_engineer_service.py:91` error propagation & kinematics pulling, `routes/ai_engineer_routes.py:506` caller params & standard classifications, `routes/simulate/handling.py:332` vehicle ID, `workers/unified_worker.py:314,352` payload param parsing | M1 | Survey 1 |
| 8 | Vercel Mirror & Test Matrix Verification | Sync `src/suspensionlab/` -> `backend_vercel/src/suspensionlab/`, execute 10 pytest test suites with 0 failures, commit on master | M4 | Parent Dispatch |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Squad 1 & Squad 4 Implementation | Physics Ride/Contact + Backend Routes & Workers (`damper_model.py`, `active_quarter_car.py`, `quarter_car.py`, `load_transfer_dynamics.py`, `full_car.py`, `kinematics.py`, `routes/simulate/full_car.py`, `workers/unified_worker.py`, `routes/optimize.py`, `services/ai_race_engineer_service.py`, `routes/ai_engineer_routes.py`, `routes/simulate/handling.py`) | none | COMPLETED |
| 2 | Squad 2, 8 & Squad 3 Implementation | Physics Yaw, Tires, Lap Sim + Calibration, Validation, Interop & Honesty (`yaw_dynamics.py`, `magic_formula.py`, `tir_parser.py`, `vnv/framework.py`, `lap_sim.py`, `residual_engine.py`, `residual_analysis.py`, `parameter_identification.py`, `holdout.py`, `adams.py`, `external_cae_solver.py`, `matlab_simulink.py`, `tir_tire.py`, `setup_intelligence.py`, `optimizer.py`, `model_validity.py`, `advanced_plots.py`, `race_engineer.py`, `telemetry_events.py`, `decision_engine.py`, `monte_carlo.py`, `pareto_optimizer.py`) | none | COMPLETED |
| 3 | Verification Wave | Reviewers (2), Challengers (2), Forensic Auditor (1) parallel evaluation | M1, M2 | COMPLETED |
| 4 | Mirror, Test Matrix & Master Commit | Mirror to `backend_vercel/`, execute 10 pytests, master git commit | M3 | COMPLETED |

## Interface Contracts
### Suspension Dynamics & Load Transfer
- Wheel rate vs spring rate: $k_{\text{wheel}} = k_{\text{spring}} \cdot MR^2$, $c_{\text{wheel}} = c_{\text{spring}} \cdot MR^2$.
- Unilateral contact: $F_z \ge 0$. Total normal load $\sum F_z = m g + F_{\text{aero}}$ preserved upon inside wheel lift-off by transferring excess to outside wheel.
- Bump-stop force: $C^1$-continuous tangent continuation for $\delta > 0.05\text{ m}$: $F_{\text{bs}}(\delta) = F_{\text{bs}}(0.05) + F'_{\text{bs}}(0.05) \cdot (\delta - 0.05)$.
- Motion ratio at heave index 0: Python reference solver sets `motion_ratio[0] = motion_ratio[1]` to match C++ native extension.

### Yaw Dynamics & Tire Slip
- Understeer gradient: $K_{\text{us,rad}} = \frac{m}{L} \left(\frac{b}{C_{\alpha,f}} - \frac{a}{C_{\alpha,r}}\right)$.
- Neutral steer speed: $v_{\text{neutral}} = \sqrt{\frac{L}{K_{\text{us,rad}}}}$ for $K_{\text{us,rad}} > 10^{-9}$.
- Critical speed: $v_{\text{crit}} = \sqrt{\frac{L}{-K_{\text{us,rad}}}}$ for $K_{\text{us,rad}} < -10^{-9}$.
- Equilibrium yaw rate: $r_{\text{ss}} = \frac{v \delta}{L + K_{\text{us,rad}} v^2}$.
- Magic Formula 5.2 combined slip: $r_{Bx1} = 10.0, r_{Bx2} = 8.0$ yielding $G_{x\alpha} = 0.78817 \approx 0.7882$ ($0.0038\%$ error vs benchmark $\le 1.00\%$).

### Lap Simulation & Energy Balance
- Closed-loop energy balance: $\Delta E_{\text{pot}} = m g (z_{\text{end}} - z_{\text{start}}) / 1000$, $\Delta E_{\text{kin}} = \frac{1}{2} m (v_{\text{end}}^2 - v_{\text{start}}^2) / 1000$ included in `energy_balance_error_pct`.
- Mass monotonicity: Tire nominal vertical load $F_{z,\text{nom}} = 4000.0$ N constant across vehicle mass sweeps (removing unphysical mass-penalty scaling).
- ARB roll stiffness: Wheel rate $k_{\text{arb,wheel}}$ [N/m] vs torsional roll stiffness $K_\phi$ [N·m/rad], $K_\phi = k_{\text{arb,diff}} \cdot t_w^2$.

### Calibration & Validation
- Nash-Sutcliffe Efficiency: $NSE = 1.0 - \frac{\text{MSE}(e)}{\max(\text{Var}(y), 10^{-12})}$ (true signed metric, no artificial $\max(0.0, \dots)$ clamping).
- Parameter identification: strictly requires explicit `"road_input"` or `"z_r"` channel; never equates suspension deflection with road elevation.
- Telemetry holdout: hashes byte buffer `np.ascontiguousarray(arr).tobytes()`.

## Code Layout
- Exclusive Worker 1 Files:
  * `src/suspensionlab/physics/damper_model.py`
  * `src/suspensionlab/physics/active_quarter_car.py`
  * `src/suspensionlab/physics/quarter_car.py`
  * `src/suspensionlab/physics/load_transfer_dynamics.py`
  * `src/suspensionlab/physics/full_car.py`
  * `src/suspensionlab/physics/kinematics.py`
  * `src/suspensionlab/backend/api/routes/simulate/full_car.py`
  * `src/suspensionlab/backend/workers/unified_worker.py`
  * `src/suspensionlab/backend/api/routes/optimize.py`
  * `src/suspensionlab/services/ai_race_engineer_service.py`
  * `src/suspensionlab/backend/api/routes/ai_engineer_routes.py`
  * `src/suspensionlab/backend/api/routes/simulate/handling.py`
- Exclusive Worker 2 Files:
  * `src/suspensionlab/physics/yaw_dynamics.py`
  * `src/suspensionlab/physics/magic_formula.py`
  * `src/suspensionlab/physics/tir_parser.py`
  * `src/suspensionlab/physics/vnv/framework.py`
  * `src/suspensionlab/physics/lap_sim.py`
  * `src/suspensionlab/validation/residual_engine.py`
  * `src/suspensionlab/physics/residual_analysis.py`
  * `src/suspensionlab/physics/parameter_identification.py`
  * `src/suspensionlab/validation/holdout.py`
  * `src/suspensionlab/interop/adapters/adams.py`
  * `src/suspensionlab/interop/runners/external_cae_solver.py`
  * `src/suspensionlab/interop/adapters/matlab_simulink.py`
  * `src/suspensionlab/interop/adapters/tir_tire.py`
  * `src/suspensionlab/physics/setup_intelligence.py`
  * `src/suspensionlab/physics/optimizer.py`
  * `src/suspensionlab/physics/model_validity.py`
  * `src/suspensionlab/visualization/advanced_plots.py`
  * `src/suspensionlab/analytics/race_engineer.py`
  * `src/suspensionlab/physics/telemetry_events.py`
  * `src/suspensionlab/physics/decision_engine.py`
  * `src/suspensionlab/physics/monte_carlo.py`
  * `src/suspensionlab/physics/pareto_optimizer.py`
