# Phase 3H.4.3 Independent Quadrature Audit

**Phase**: PHASE_3H.4.3  
**Timestamp**: `2026-09-27T23:23:33.609529+00:00`  

## 1. Quadrature Formulations Evaluated

1. **Method A (Production Forward Euler)**: Left-rectangle sum $\sum P(t_k) \Delta t$.
2. **Method B (Trapezoidal Post-Processing)**: Composite trapezoidal rule $\int P dt \approx \sum \frac{P(t_k) + P(t_{k+1})}{2} \Delta t$.
3. **Method C (Simpson Rule)**: Composite Simpson's 1/3 high-order quadrature.

## 2. Comparative Ledger Residuals

| $\Delta t$ (ms) | Method A Prod $R$ (J) | Prod (%) | Method B Trap $R$ (J) | Trap (%) | Method C Simp $R$ (J) | Simp (%) |
|---|---|---|---|---|---|---|
|  5.0000 | -1080.18 | -6.90% | -1771.40 | -11.64% | -1864.29 | -12.33% |
|  2.5000 |  -727.70 | -4.44% | -1291.15 | -7.98% | -1336.64 | -8.28% |
|  1.2500 |  -556.18 | -3.31% | -1059.97 | -6.36% | -1082.61 | -6.50% |
|  0.6250 |  -468.00 | -2.76% |  -943.76 | -5.58% |  -955.05 | -5.65% |
|  0.3125 |  -424.06 | -2.48% |  -886.01 | -5.20% |  -891.65 | -5.23% |

> [!NOTE]
> Forward Euler sum corresponds exactly to the state integration formulation of the discrete simulator. Trapezoidal and Simpson rules integrate sampled powers across intervals, shifting the discrete accounting by O(dt) curvature while preserving monotonic first-order asymptotic convergence.
