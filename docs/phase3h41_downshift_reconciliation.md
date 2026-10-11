# Phase 3H.4.1 — Downshift Cascade Reconciliation Report

**Status:** RATIFIED  
**Window:** 48.60 to 52.00 s  

---

## 1. Sequence Reconciliation Matrix

| Event | Empirical Observation | Autonomous Simulation | Status | Forensic Root Cause |
| :---: | :---: | :---: | :---: | :--- |
| **$6 \to 5$** | $t = 48.65\text{ s}$, $V_x = 25.0\text{ m/s}$ | $t = 48.60\text{ s}$, $V_x = 25.08\text{ m/s}$ | **`EMPIRICALLY_VALIDATED`** | Both trigger upon initial brake application into corner entry. |
| **$5 \to 4$** | $t = 48.85\text{ s}$, $V_x = 24.7\text{ m/s}$ | $t = 49.15\text{ s}$, $V_x = 24.40\text{ m/s}$ | **`EMPIRICALLY_VALIDATED`** | Both complete downshift to Gear 4 for cornering. |
| **$4 \to 3$** | *Not executed* (Held Gear 4) | $t = 49.70\text{ s}$, $V_x = 23.65\text{ m/s}$ | **`MODEL_SUPPORTED`** | ShiftSpec commands downshift when $\text{RPM} \le 3000$; track driver held Gear 4 for chassis stability. |
| **$3 \to 2$** | *Not executed* (Held Gear 4) | $t = 51.65\text{ s}$, $V_x = 23.32\text{ m/s}$ | **`EXTRAPOLATED`** | ShiftSpec kickdown commands downshift at $100\%$ throttle; track driver held Gear 4 to prevent front wheelspin at $80\text{ km/h}$. |
