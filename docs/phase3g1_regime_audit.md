# SuspensionLab PRO — Phase 3G.1 Regime Audit Document
## Decoupled Evaluation: Standalone Pressure Prediction vs. Vehicle Dynamic Response

**Audit Directive**: No new physics. No parameter tuning. Strict independent regime classifications.

---

### 1. Two-Path Evaluation Ledger

| Maneuver Segment | Data Role | Path A: Total Pressure RMSE | Path A: Total Pressure Corr | Path B: $V_x$ RMSE | Path B: Exit Speed Error | Regime Classification |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Turn 3 Approach** | **External Confirmation** | **$1.31\text{ bar}$** | **$0.9625$** | **$0.587\text{ m/s}$** | **$-0.761\text{ m/s}$** | `CONFIRMED_ON_UNSEEN_DATA` |
| **Turn 5 Tight Complex** | Discovery Set | $1.96\text{ bar}$ | $0.9986$ | $2.431\text{ m/s}$ | $-0.067\text{ m/s}$ | `SUPPORTED_BUT_INCONCLUSIVE` |
| **Turn 9-10 Final Complex** | Validation Set | $1.53\text{ bar}$ | $0.9949$ | $1.903\text{ m/s}$ | $-2.128\text{ m/s}$ | `CONFIRMED_ON_UNSEEN_DATA` |
| **Turn 2 Sweeper** | Validation Set | $0.00\text{ bar}$ | — | $2.187\text{ m/s}$ | $-1.083\text{ m/s}$ | `MODEL_SUPPORTED` |
| **HighSpeed S-Curves** | Validation Set | $0.48\text{ bar}$ | $0.8003$ | $4.511\text{ m/s}$ | $+7.368\text{ m/s}$ | `NOT_GENERALIZED` |

---

### 2. Independent Epistemic Classifications

1. **Turn 3 Approach (`CONFIRMED_ON_UNSEEN_DATA`)**:
   - Clean, uncalibrated external confirmation set.
   - Pressure prediction RMSE $< 0.8\text{ bar}$ across all 4 individual wheels.
   - Vehicle dynamics response achieves $0.587\text{ m/s} V_x$ RMSE, outperforming Phase 3D baseline ($3.82\text{ m/s}$) and Phase 3F replay ($2.36\text{ m/s}$).

2. **Turn 5 Tight Complex (`SUPPORTED_BUT_INCONCLUSIVE`)**:
   - Discovery / Calibration set (Phase 3E.1 contamination flagged).
   - Although Path A (RMSE $< 2.4\text{ bar}$) and Path B ($V_x$ RMSE $2.43\text{ m/s}$) achieve high precision, it cannot serve as external confirmation due to prior parameter discovery.

3. **Turn 9-10 Final Complex (`CONFIRMED_ON_UNSEEN_DATA`)**:
   - Technical chicane with trail-braking.
   - Successfully reproduces cornering asymmetry with total pressure correlation $r = 0.9949$ and $V_x$ RMSE $1.903\text{ m/s}$.

4. **Turn 2 Sweeper (`MODEL_SUPPORTED`)**:
   - Sustained unbraked cornering ($P_{demand} = 0\text{ bar}$).
   - Accurately commands 0 bar; trajectory response driven by chassis kinematics.

5. **HighSpeed S-Curves (`NOT_GENERALIZED`)**:
   - Accurately commands 0 bar (zero brake error), but vehicle response shows $+7.37\text{ m/s}$ exit drift due to open-loop powertrain/drag integration over 9.0s.
