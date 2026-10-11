# Phase 3H.4.3 Richardson Extrapolation Analysis

**Phase**: PHASE_3H.4.3  
**Timestamp**: `2026-09-27T23:23:33.609529+00:00`  

## 1. Triplet Extrapolation Formulation

For discrete residual $R(\Delta t)$, the observed order of convergence across step-doubling triplets is:
$$p = \log_2 \left( \frac{R(2\Delta t) - R(\Delta t)}{R(\Delta t) - R(\Delta t / 2)} \right)$$

and the estimated continuum limit is:
$$R_0 = R(\Delta t) + \frac{R(\Delta t) - R(2\Delta t)}{2^p - 1}$$

## 2. Successive Triplet Results

| Triplet | Grid Rates $\Delta t$ (ms) | $R_{\text{coarse}}$ (J) | $R_{\text{med}}$ (J) | $R_{\text{fine}}$ (J) | Observed Order $p$ | Asymptotic Residual $R_0$ (J) |
|---|---|---|---|---|---|---|
| `Triplet_1_5.00_2.50_1.25ms` | 5.00 / 2.50 / 1.2500 | -1080.18 | -727.70 | -556.18 | **1.0391** | **-393.59** |
| `Triplet_2_2.50_1.25_0.625ms` | 2.50 / 1.25 / 0.6250 | -727.70 | -556.18 | -468.00 | **0.9600** | **-374.72** |
| `Triplet_3_1.25_0.625_0.3125ms` | 1.25 / 0.62 / 0.3125 | -556.18 | -468.00 | -424.06 | **1.0047** | **-380.39** |

## 3. Asymptotic Synthesis

- **Mean Convergence Order**: $p = 1.0012$ (Classification: `STRICT_FIRST_ORDER_O_DT`)
- **Mean Asymptotic Continuum Residual**: $R_0 = -382.90\text{ J}$ (-2.45% of input work)
- **Continuum Limit Zero**: `False`

> [!IMPORTANT]
> The numerical discretization truncation error contracts with p = 1.001 toward an asymptotic continuum residual of -380.39 J. In compliance with Phase 3H.4.3 Rule 6, the continuum limit is explicitly certified as NON-ZERO in the frozen baseline physics model.
