# SuspensionLab PRO — Phase 3O Governed Experiment Execution Report

**Protocol ID**: `PREREG-P3O-01`  
**Protocol Version**: `1.0.1-frozen`  
**Protocol SHA-256**: `d8ce0ab97d437a20cb6a12972e922dd8a4a5b7539eecb94bc85ca4d789c44750`  
**Dataset SHA-256**: `489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3`  
**Execution Timestamp**: `2026-10-03T22:24:40.186773+00:00`  
**Final Classification**: **`EFFECT_UNRESOLVED`**  
**Prediction Status**: **`PREDICTION_UNRESOLVED_DUE_TO_CROSS_MANEUVER_GENERALIZATION_FAILURE`**  
**Physical Track Actionability**: **`BLOCKED / NOT_YET_MAPPED`**  

---

## 1. Executive Summary

Phase 3O evaluated the hypothesis that optimizing the Pacejka contact-patch lateral cornering stiffness scaling parameter (`params.tire_calibration.s_tire`) on authentic Volkswagen Golf VII GTI telemetry during Turn 1 Complex entry ($t \in [14.000, 18.800)\text{ s}$) would achieve non-inferior tracking during corner exit ($t \in [18.805, 23.000)\text{ s}$) and generalize to an independent sustained carousel ($t \in [24.000, 30.000)\text{ s}$).

### Key Findings
1. **Fit Partition Calibration**:
   - Baseline RMSE (`SETUP-P3O-BASE`, $s_{\text{tire}} = 1.000$): **0.038175 rad/s**
   - Optimal Candidate (`SETUP-P3O-CAL`, $s_{\text{tire}}^* = 0.864$): **0.037007 rad/s**
   - Relative Improvement: **-3.06%** (Passed Fit Gate threshold $\le -3.00\%$)
2. **Temporal Holdout (Turn 1 Exit Unwinding)**:
   - Baseline RMSE: **0.034299 rad/s**
   - Candidate RMSE: **0.027812 rad/s**
   - Delta RMSE: **-0.006487 rad/s (-18.91%)**
   - Authoritative 95% Paired Moving Block Bootstrap CI: **[-0.008175, -0.004332] rad/s**
   - Empirical Bootstrap Tail: **0/1000 bootstrap replicates supported the opposing direction (empirical bootstrap tail proportion < 0.001)**
   - Non-Inferiority Margin (+5%): **+0.001715 rad/s**
   - Verdict: **NON_INFERIORITY_ESTABLISHED** (CI upper bound $\le$ margin)
3. **Cross-Maneuver Blind Holdout (Turn 2 Carousel)**:
   - Baseline RMSE: **0.059211 rad/s**
   - Candidate RMSE: **0.065441 rad/s**
   - Delta RMSE: **+0.006230 rad/s (+10.52%)**
   - Authoritative 95% Paired Moving Block Bootstrap CI: **[+0.005505, +0.006948] rad/s**
   - Empirical Bootstrap Tail: **1000/1000 bootstrap replicates supported the degradation direction (0/1000 replicates showed improvement, empirical bootstrap tail proportion < 0.001 for improvement)**
   - Verdict: **GENERALIZATION_NOT_ESTABLISHED** (CI strictly positive in degradation direction)
4. **Secondary Metrics**:
   - Sideslip Boundary ($|\beta| \le 0.100\text{ rad}$): Peak observed $|\beta| = 0.0799\text{ rad} (4.58^\circ) \implies$ **PASSED**
   - Dynamic Jounce ($z_{\text{jounce}} \le 55.0\text{ mm}$): Peak observed $z_{\text{jounce}} = 88.55\text{ mm} \implies$ **FAILED** under sustained 1.14 G carousel roll.
     - **MODEL RESULT**: Candidate exceeds the pre-registered dynamic jounce boundary ($88.55\text{ mm} > 55.0\text{ mm}$).
     - **PHYSICAL CLAIM**: No claim is made that the real vehicle physically reaches $88.55\text{ mm}$ unless directly measured by physical suspension travel transducers.

---

## 2. Gate Decision Summary

| Gate / Decision Boundary | Pre-Registered Metric | Threshold / Rule | Observed Value | Gate Result |
| :--- | :--- | :--- | :--- | :--- |
| **Fit Gate** | Relative Yaw RMSE Improvement | $\le -3.0\%$ | **-3.06%** | **PASSED** |
| **Temporal Non-Inferiority** | 95% Bootstrap CI Upper Bound | $\le +0.001715\text{ rad/s}$ | **-0.004332\text{ rad/s}** (0/1000 in opposing tail) | **PASSED** |
| **Cross-Maneuver Generalization** | 95% Bootstrap CI Upper Bound | $< 0.0000\text{ rad/s}$ | **+0.006948\text{ rad/s}** (0/1000 showing improvement) | **FAILED** |
| **Secondary: Lateral Accel** | Relative Degradation | $\le +5.0\%$ | **Max -0.30%** | **PASSED** |
| **Secondary: Roll Angle** | Relative Degradation | $\le +5.0\%$ | **Max -2.61%** | **PASSED** |
| **Secondary: Sideslip Boundary** | Peak Absolute Sideslip $|\beta|$ | $\le 0.100\text{ rad } (5.7296^\circ)$ | **0.0799\text{ rad } (4.58^\circ)** | **PASSED** |
| **Secondary: Dynamic Jounce** | Peak Dynamic Front Travel | $\le 55.0\text{ mm}$ | **88.55\text{ mm}** (Model Result; no physical claim) | **FAILED** |

---

## 3. Epistemic Demarcation & Synthesis

* **MEASURED**: Oxford RT3000 RTK-GNSS/IMU raw states (`yawRate_radps`, `ayCG_mps2`, `wheelspeed_fl..rr`).
* **SIMULATED**: Fixed-step RK4 trajectories ($dt = 0.001\text{ s}$, 22 dynamic states).
* **IDENTIFIABLE**: $s_{\text{tire}}$ is conditionally identifiable on transient entry only under frozen camber, toe, and inertia.
* **ESTIMATED**: $s_{\text{tire}}^* = 0.864$ minimizes transient entry yaw residual.
* **INFERRED**: Within the frozen simulation model, reducing $s_{\text{tire}}$ is consistent with attenuating the simulated transient yaw-response buildup during Turn 1 entry. (This is an inferential model interpretation, not an independently measured physical transfer-function fact.)
* **PREDICTED**: Fails in sustained high-G carousel cornering due to steady-state understeer gradient starvation.

---

## 4. Final Classification

$$\mathbf{EFFECT\_UNRESOLVED}$$

**Reason**: Cross-maneuver generalization was not established on Turn 2 Carousel (Delta RMSE degradation +10.52%, 95% bootstrap CI [+0.005505, +0.006948] rad/s strictly excludes improvement, with 0/1000 bootstrap replicates showing improvement) and sustained 1.14 G lateral acceleration induced dynamic suspension jounce of 88.55 mm exceeding the 55.0 mm bump-stop clearance threshold in the model.
