# SuspensionLab PRO — Phase 3H.2 Powertrain Architecture
## Modular Powertrain Separation, Driveline Stages & Provenance

---

### 1. Dual-Path Architecture
Phase 3H.2 establishes strict architectural decoupling between:
1. **ACTUATOR_REPLAY (Path A)**: Empirical evaluation replaying measured boundary inputs (CAN engine torque, corner brake pressures).
2. **POWERTRAIN_PREDICTION (Path B)**: Autonomous endogenous physical simulation where engine torque and transmission ratio are predicted from driver commands and chassis states.

```
DRIVER DEMANDS (throttle, steer)
      ↓
ENGINE TORQUE MODEL [Predictive / Replay / Synthetic]
      ↓
TRANSMISSION & GEAR INFERENCE [omega_eng / omega_wheel]
      ↓
DIFFERENTIAL & DRIVEN AXLE [T_axle = T_eng * N * eta]
      ↓
TIRE CONTACT PATCH [Fx = T_axle / R_eff]
      ↓
VEHICLE PLANAR EQUATIONS [du/dt, dv/dt, dr/dt]
```

---

### 2. Driveline Force and Power Flow
- Engine stage: $P_{\text{eng}} = T_{\text{eng}} \cdot \omega_{\text{eng}}$
- Gearbox stage: $T_{\text{gb}} = T_{\text{eng}} \cdot g_{\text{gear}}$
- Final Drive stage: $T_{\text{axle}} = T_{\text{gb}} \cdot f_{\text{fd}} \cdot \eta$ (**`INFERRED`**)
- Tractive Force stage: $F_x = T_{\text{axle}} / R_{\text{eff}}$ (**`INFERRED`**)
- Contact Power stage: $P_{\text{tractive}} = F_x \cdot V_x$ (**`INFERRED`**)
