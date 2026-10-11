# SuspensionLab PRO — Phase 3G Architecture Document
## Autonomous Brake Distribution Controller Model

**Phase**: 3G — Predictive Brake Distribution  
**Module**: `src/suspensionlab/physics/brake_distribution.py`  
**Classification**: `Brake Distribution Controller Model`  

---

### 1. Architectural Distinction: Mode A vs. Mode B

```
┌────────────────────────────────────────────────────────────────────────┐
│                        BRAKE OPERATING MODES                           │
├──────────────────────────────────┬─────────────────────────────────────┤
│ MODE A: ACTUATOR_REPLAY          │ MODE B: BRAKE_DISTRIBUTION_PREDICT  │
├──────────────────────────────────┼─────────────────────────────────────┤
│ Purpose: Validate chassis, tire, │ Purpose: Autonomously predict per-  │
│ suspension physics given true    │ wheel brake line pressures from     │
│ boundary actuator forces.        │ driver demand & vehicle state.      │
│                                  │                                     │
│ Inputs: Measured caliper readouts│ Inputs: Master brake demand, steer, │
│ (brake_fl_bar, brake_fr_bar,     │ Vx, yaw rate, lateral/longitudinal  │
│  brake_rl_bar, brake_rr_bar).    │ accelerations, wheel speeds.        │
│                                  │                                     │
│ Measured Pressure Leakage: YES   │ Measured Pressure Leakage: STRICTLY │
│ (By definition, boundary replay) │ ZERO (Provably isolated DAG).       │
└──────────────────────────────────┴─────────────────────────────────────┘
```

### 2. Causal Mathematical Formulation

The autonomous predictive model synthesizes corner hydraulic line pressures $[P_{FL}, P_{FR}, P_{RL}, P_{RR}]$ from first-principles mechanics:

1. **Static Axle Proportioning**:
   $$P_{f, axle} = \beta_{static} \cdot P_{demand}, \quad P_{r, axle} = (1 - \beta_{static}) \cdot P_{demand}$$
   where $\beta_{static} = 0.614$ (calibrated front bias for the VW Golf GTI).

2. **Dynamic Normal Load Transfer**:
   $$\Delta F_{z, long} = \frac{m \cdot a_x \cdot h_{cg}}{L}, \quad \Delta F_{z, lat, f} = \frac{m \cdot a_y \cdot h_{cg}}{t_f} \frac{b}{L}, \quad \Delta F_{z, lat, r} = \frac{m \cdot a_y \cdot h_{cg}}{t_r} \frac{a}{L}$$
   $$F_{z, fl} = F_{z0, f} - \frac{\Delta F_{z, long}}{2} - \Delta F_{z, lat, f}$$
   $$F_{z, fr} = F_{z0, f} - \frac{\Delta F_{z, long}}{2} + \Delta F_{z, lat, f}$$
   $$F_{z, rl} = F_{z0, r} + \frac{\Delta F_{z, long}}{2} - \Delta F_{z, lat, r}$$
   $$F_{z, rr} = F_{z0, r} + \frac{\Delta F_{z, long}}{2} + \Delta F_{z, lat, r}$$

3. **Corner Load Proportioning Factors**:
   $$k_{fl} = \frac{2 F_{z, fl}}{F_{z, fl} + F_{z, fr}}, \quad k_{fr} = \frac{2 F_{z, fr}}{F_{z, fl} + F_{z, fr}}$$
   $$k_{rl} = \frac{2 F_{z, rl}}{F_{z, rl} + F_{z, rr}}, \quad k_{rr} = \frac{2 F_{z, rr}}{F_{z, rl} + F_{z, rr}}$$
   *Property*: $k_L + k_R \equiv 2.0$, strictly conserving total axle braking demand.

4. **Cornering Brake Control (CBC)**:
   $$r_{target} = \frac{V_x \cdot \delta}{L + K_{us} V_x^2}, \quad e_r = r - r_{target}$$
   $$\Delta P_{cbc} = \operatorname{clip}(K_{cbc} \cdot e_r, -P_{cbc, max}, P_{cbc, max})$$

5. **ABS Slip Limiter**:
   $$\kappa_i = \frac{R_w \omega_i - V_{wx, i}}{\max(V_{wx, i}, 1.0)}$$
   $$\text{If } \kappa_i < \kappa_{crit}: \quad f_{abs, i} = \max(0.2, 1.0 - K_{abs} (|\kappa_i| - |\kappa_{crit}|))$$

6. **Actuator Slew Rate Limiting**:
   $$\left| \frac{dP_i}{dt} \right| \le \dot{P}_{max} = 400\text{ bar/s}, \quad P_i \in [0, 80]\text{ bar}$$
