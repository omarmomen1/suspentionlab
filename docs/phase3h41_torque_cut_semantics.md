# Phase 3H.4.1 — Torque-Cut Semantics & Algebraic Disambiguation Report

**Status:** RATIFIED  
**Algebraic Identity:** $T_{\text{clutch\_1}} + T_{\text{clutch\_2}} \equiv T_{\text{engine\_after\_cut}}$  

---

## 1. Disambiguated Variable Definitions

1. **`T_engine_raw`**: Peak available combustion envelope torque as a function of throttle, RPM, and gear prior to transmission torque-cut intervention.
2. **`T_engine_after_cut`**: Net mechanical engine crankshaft torque exiting the flywheel after applying the transmission shift controller torque multiplier:
   \[
   T_{\text{engine\_after\_cut}} = T_{\text{engine\_raw}} \times \mu_{\text{torque}}
   \]
3. **`T_clutch_1`**: Instantaneous torque transmitted through Clutch Pack 1 (odd gears 1, 3, 5).
4. **`T_clutch_2`**: Instantaneous torque transmitted through Clutch Pack 2 (even gears 2, 4, 6).

---

## 2. Algebraic Proof of Torque Sum

\[
T_{\text{clutch\_1}} + T_{\text{clutch\_2}} = T_{\text{engine\_after\_cut}} \ne T_{\text{engine\_raw}}
\]

- **Maximum Discrepancy vs $T_{\text{engine\_after\_cut}}$:** **0.000000 Nm** (Exact identity).
- **Maximum Discrepancy vs $T_{\text{engine\_raw}}$:** **257.4 Nm** (During torque cut).
- **Prohibited Identifiers:** The ambiguous identifier `Tcrank` is formally deprecated. In the codebase, `torque_engine_crank_nm` represents $T_{\text{engine\_after\_cut}}$.
