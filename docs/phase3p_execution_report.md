# Phase 3P — Governed Execution & Engineering Report

**Protocol ID**: `PREREG-P3P-01`  
**Protocol Version**: `1.0.0-frozen`  
**Protocol Hash**: `a66f2242629f20f4355312cf84a4d81bf49c14b53bdbea9d60515bdd12317f45`  
**Execution Timestamp**: `2026-10-04T00:33:35.539679+00:00`  
**Final Classification**: **`HYPOTHESIS_NOT_SUPPORTED`**  

---

## 1. Executive Summary

Phase 3P was executed fail-closed under frozen pre-registration governance.
The target mechanism `DynamicVehicleParams.tire_relaxation_length_y_m` ($\sigma_{y0}$) was calibrated on the Fit Window (`Turn_4_Entry`, `11200..12199`, $N=1,000$).
The optimal candidate parameter was frozen at:
$$\sigma_{y0}^* = 0.497\text{ m}$$
(Baseline reference: $0.250\text{ m}$).

Following candidate freeze, holdout evaluations were conducted on unexposed Category A partitions:
- **Temporal Holdout (`Turn_4_Exit`, N=700)**: Evaluated for **`TEMPORAL_IMPROVEMENT`**.
  - Baseline RMSE: `0.023743\text{ rad/s}`
  - Candidate RMSE: `0.023357\text{ rad/s}`
  - $\Delta\text{RMSE}$: `-0.000387\text{ rad/s}` (`-1.63%`)
  - 95% Bootstrap CI: `[-0.001191, 0.000529]\text{ rad/s}`
  - Improvement Verdict: **`HYPOTHESIS_NOT_SUPPORTED`** (Passed: `False`)
  - Diagnostic Non-Inferiority: Passed (`True`, margin `0.001187\text{ rad/s}`)
- **Sustained Holdout (`Turn_4_Apex`, N=1,000)**: Evaluated for **`NON_INFERIORITY`**.
  - Baseline RMSE: `0.029164\text{ rad/s}`
  - Candidate RMSE: `0.029348\text{ rad/s}`
  - $\Delta\text{RMSE}$: `0.000184\text{ rad/s}` (`+0.63%`)
  - 95% Bootstrap CI: `[-0.000141, 0.000557]\text{ rad/s}`
  - Non-Inferiority Verdict: **`SUSTAINED_NON_INFERIORITY_ESTABLISHED`** (Passed: `True`, margin `0.001458\text{ rad/s}`)

---

## 2. Fit Diagnostic
- Relative Fit Improvement: `-3.233%`
- Exploratory Adequacy Classification: **`PASS`**
- Note: Fit diagnostic carries 0 evidential weight in final decision.

---

## 3. Secondary Engineering Constraints
- **Lateral Acceleration ($a_y$)**: Fit `+0.21%`, Temp `+0.28%`, Sustained `+0.15%` ($\le +5.0\%$) $\to$ **Passed** (`True`)
- **Roll Angle ($\phi$)**: Fit `+0.09%`, Temp `+0.09%`, Sustained `-0.10%` ($\le +5.0\%$) $\to$ **Passed** (`True`)
- **Sideslip Angle ($\beta$)**: Max Observed `0.0644\text{ rad}` ($5.73^\circ$ threshold) $\to$ **Passed** (`True`)
- **Dynamic Jounce ($z_{\text{jounce}}$)**: Max Observed `37.91\text{ mm}` ($55.0\text{ mm}$ threshold) $\to$ **Passed** (`True`)

---

## 4. Final Governed Verdict
**Verdict**: **`HYPOTHESIS_NOT_SUPPORTED`**  
**Actionability Demarcation**:
- `MODEL_PARAMETER_ACTIONABILITY = SUPPORTED_AS_MODEL_VARIABLE`
- `PHYSICAL_TRACK_ACTIONABILITY = BLOCKED / NOT_YET_MAPPED`
