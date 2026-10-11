# Phase 3H.3 — ShiftSpec Policy Architecture Design Document

**Status:** SPECIFICATION APPROVED  
**Classification:** PRODUCTION ARCHITECTURE DESIGN  

---

## 1. Architecture Principles

1. **No Tuned Tables:** The control law must not rely on maneuver-specific lookups (e.g. `gear_expected = 3`).
2. **State-Driven:** Decision rules evaluate only simulated forward dynamical states ($u, \omega_i$) and boundary driver controls ($\alpha, P_{\text{brake}}$).
3. **Dual-Clutch State Machine:** Explicit modeling of torque reduction, clutch handover, and speed synchronization.

---

## 2. ShiftSpec Mathematical Formulation

### 2.1 Upshift Threshold Law
$$\omega_{\text{eng}} \ge \omega_{\text{up}}(\alpha, g) = \omega_{\text{up,min}}(g) + \alpha \cdot \left[\omega_{\text{up,max}}(g) - \omega_{\text{up,min}}(g)\right]$$
- $\omega_{\text{up,min}} = 4200\text{ RPM}$ (part throttle, $\alpha = 0$)
- $\omega_{\text{up,max}} = 6000\text{ RPM}$ (wide open throttle, $\alpha = 1.0$)
- Condition: $P_{\text{brake}} < 5.0\text{ bar}$ AND $\text{shift\_state} == \text{IN\_GEAR}$ AND $t_{\text{lockout}} \le 0$.

### 2.2 Downshift Threshold Law
$$\omega_{\text{eng}} \le \omega_{\text{down}}(\alpha, P_{\text{brake}}, g) = \begin{cases} \omega_{\text{down,brake}} & \text{if } P_{\text{brake}} \ge 5.0\text{ bar} \\ \omega_{\text{down,coast}} & \text{if } P_{\text{brake}} < 5.0\text{ bar} \end{cases}$$
- $\omega_{\text{down,brake}} = 3000\text{ RPM}$ (aggressive engine braking into corners)
- $\omega_{\text{down,coast}} = 1800\text{ RPM}$ (cruising coastdown)
- Kickdown override: If $\alpha > 0.90$ and $\omega_{\text{target}} < 6500\text{ RPM}$, initiate downshift immediately.

### 2.3 Shift Phase State Machine

```
[ IN_GEAR ] ──(Threshold Crossed)──> [ TORQUE_CUT (40 ms) ]
                                             │
                                     (Timer >= 40 ms)
                                             ↓
[ IN_GEAR ] <──(Timer >= 40 ms)─── [ SPEED_SYNC (40 ms) ]
     ↑                                       ↑
     │                               (Timer >= 70 ms)
     │                                       │
     └───────── Lockout (400 ms) ── [ CLUTCH_HANDOVER (70 ms) ]
```

- Total Shift Duration: $40\text{ ms} + 70\text{ ms} + 40\text{ ms} = 150\text{ ms}$.
- Lockout Hysteresis: $400\text{ ms}$ prevents gear hunting.
