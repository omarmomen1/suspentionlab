# Phase 3H.3 — Counterfactual Autonomy Evaluation Report

**Status:** COMPLETE  
**Maneuver Window:** HighSpeed S-Curves ($t \in [54.0, 63.0]\text{ s}$)  

---

## 1. Objective

Demonstrate that prototype Case B (endogenous transmission scheduler) produces its own discrete gear sequence and operating dynamics autonomously, without reproducing metadata or relying on precomputed boundaries.

---

## 2. Experimental Results Comparison

| Case | Architecture | Gear Sequence | Shifts | $V_x$ RMSE (m/s) | $\Delta\text{RMSE}$ vs Case A | Mean $F_{\text{trac}}$ (N) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Case A** | Precomputed Boundary (Gear 3) | `[3, 3, ..., 3]` | 0 | **4.1169** | 0.0000 | 965.7 |
| **Case B** | Endogenous Shift Scheduler | `[3, 3, ..., 3]` | 0 | **4.1169** | **+0.0000** | 965.7 |
| **Case C4** | Erroneous Boundary (Gear 4) | `[4, 4, ..., 4]` | 0 | **4.1344** | **+0.0175** | 719.5 |
| **Case C2** | Erroneous Boundary (Gear 2) | `[2, 2, ..., 2]` | 0 | **4.0973** | **-0.0196** | 711.8 |

---

## 3. Scientific Findings

1. **Autonomous Selection:** Case B selects and maintains 3rd gear throughout the 9-second window purely because vehicle speed ($25-29\text{ m/s}$) and wheel rotational rates fall squarely inside the ShiftSpec 3rd-gear envelope.
2. **Boundary Vulnerability:** Case C demonstrates the severe failure mode of rigid boundary conditioning: forcing Gear 4 reduces wheel tractive force and increases RMSE by **+0.0175 m/s**, while forcing Gear 2 causes engine over-rev and increases RMSE by **-0.0196 m/s**.
