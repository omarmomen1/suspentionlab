# Phase 3H.4.1 — Transition-Event Resolution Analysis

**Status:** RATIFIED  
**Simulation $\Delta t$:** $0.005\text{ s}$ ($200\text{ Hz}$)  

---

## 1. Quantization vs Discrepancy Breakdown

- **Simulation Step ($\Delta t$):** $5.0\text{ ms}$
- **Discrete-State Event Resolution:** $5.0\text{ ms}$
- **Maximum Event-Time Quantization Error:** $\pm 2.5\text{ ms}$ (worst-case $5.0\text{ ms}$)
- **Observed Physical Shift Trigger Discrepancy:** $40.0\text{ ms}$
- **Ratio (Discrepancy / Quantization):** **$8.0\times$**

$$\text{Discrepancy} = 40.0\text{ ms} \gg \Delta t_{\text{quantization}} = 5.0\text{ ms}$$

**Conclusion:** The shift trigger error is fundamentally physical, stemming from calibration thresholds and driver anticipation, not numerical quantization.
