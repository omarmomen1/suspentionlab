# SuspensionLab PRO — Phase 3F Multi-Corner Braking & Engine Overrun Architecture
**Document Version:** Phase 3F Production Physics Architecture  
**Release Date:** 2026-09-26 00:36:54 UTC  
**Applicability:** Dynamic Transient 14-DOF Lap Simulator (`src/suspensionlab/physics/dynamic_lap_sim.py`)

---

## 1. Architectural Motivation & Problem Definition
During the Phase 3E blind evaluation and Phase 3E.1 longitudinal forensic audit, severe longitudinal velocity ($V_x$) and wheel-speed discrepancies were observed in maneuvers with heavy deceleration and high lateral-load asymmetry:
- **Turn 5 Tight Complex**: $V_x$ RMSE increased by $+187.7\%$, and wheel-speed RMSE increased by $+210\%$. Modeled vehicle was carrying an excess $+5.36\text{ m/s}$ ($+19.3\text{ km/h}$) through the apex.
- **Turn 3 Approach**: $V_x$ RMSE increased by $+51.3\%$.

Forensic tracing revealed that the vehicle equations and tire models were not at fault. Rather, two critical physical inputs were mischaracterized:
1. **Asymmetric Hydraulic Braking Ingestion**: Active Electronic Stability Control (ESC) and Electronic Brakeforce Distribution (EBD) command differential pressures across the four wheels during corner entry. Ingesting only the inside-front caliper pressure ($P_{FL} = 14.3\text{ bar}$) while outside-front was $45.2\text{ bar}$ caused a $2.79\times$ under-prediction of total retarding force ($2,575.6\text{ N}$ modeled vs. $7,178.0\text{ N}$ physical).
2. **Engine Overrun Pumping Drag Omission**: At zero throttle during coastdown and threshold braking, engine internal friction and pumping work exert retarding torque ($-31.0\text{ Nm}$ measured at engine crankshaft, resulting in $-298.6\text{ Nm}$ at front driven axle in 2nd gear, $-933.8\text{ N}$ retarding tractive force, and $-0.61\text{ m/s}^2$ continuous deceleration).

---

## 2. Multi-Corner Hydraulic Braking Architecture

### A) Independent Four-Corner Ingestion
`DriverControls` now exposes independent physical pressure channels:
```python
@dataclass
class DriverControls:
    throttle: float = 0.0
    brake: float = 0.0
    steering_deg: float = 0.0
    gear: int = 1
    brake_pressure_bar: Optional[float] = None       # Backward compatible single channel
    brake_pressure_fl_bar: Optional[float] = None    # Inside/Left front caliper line pressure
    brake_pressure_fr_bar: Optional[float] = None    # Outside/Right front caliper line pressure
    brake_pressure_rl_bar: Optional[float] = None    # Inside/Left rear caliper line pressure
    brake_pressure_rr_bar: Optional[float] = None    # Outside/Right rear caliper line pressure
```

### B) Corner Torque Allocation & Caliper Clamping
Each caliper's clamping torque is governed by its dedicated line pressure and maximum mechanical corner torque rating:
$$T_{max, f} = T_{max} \times \frac{\text{bias}_{front}}{2} = 4800 \times \frac{0.62}{2} = 1488.0\text{ Nm}$$
$$T_{max, r} = T_{max} \times \frac{1.0 - \text{bias}_{front}}{2} = 4800 \times \frac{0.38}{2} = 912.0\text{ Nm}$$
$$\text{demand}_i = \operatorname{BrakeMap}(P_i)$$
$$T_{brk, i} = \text{demand}_i \times T_{max, i}$$
$$F_{brk, i} = \frac{T_{brk, i}}{R_w}$$

### C) Backward Compatibility Invariant
When all four line pressures are identical ($P_{fl} = P_{fr} = P_{rl} = P_{rr} = P$):
$$\sum T_{brk, i} = 2 \times 1488 \times d + 2 \times 912 \times d = 4800 \times d = T_{brk, baseline}$$
The model strictly preserves backward compatibility with symmetric single-channel inputs.

---

## 3. Governed Engine Overrun Drag Architecture

### A) Mathematical Formulation
The `EngineOverrunMap` produces negative shaft torque during throttle-off operation:
$$T_{overrun} = f(\text{RPM}) \times (1.0 - \operatorname{clip}(\text{throttle} / 0.05, 0, 1))$$

Governed torque schedule:
| Engine Speed (RPM) | Overrun Torque (Nm) | Physical Basis |
| :---: | :---: | :--- |
| $\le 800$ (Idle) | $0.0$ | Anti-stall fuel governor |
| $1200$ | $-10.0$ | Low-speed coastdown transition |
| $2000$ | $-28.0$ | Threshold overrun engagement |
| $3500$ | $-30.0$ | Mid-range compression/pumping work |
| $4500$ | $-31.4$ | Peak telemetry-observed retarding torque |
| $\ge 6000$ | $-15.0$ | High-RPM valve float & throttle bypass |

### B) Drivetrain Routing
For the Volkswagen Golf GTI (FWD configuration), overrun torque is delivered to the front driven wheels through transmission and differential:
$$T_{axle, overrun} = T_{overrun} \times \text{GR} \times \eta_{drivetrain}$$
$$T_{drive, fl} = T_{drive, fr} = 0.5 \times T_{axle, overrun}$$
$$T_{drive, rl} = T_{drive, rr} = 0.0$$

---

## 4. Integration into 14-DOF Wheel & Chassis Dynamics
In `compute_derivatives`, each corner's angular acceleration is updated with the independent brake and drive torques:
$$I_w \dot{\omega}_i = T_{drive, i} - T_{brk, i}\operatorname{sgn}(\omega_i) - R_w F_{x, i}^{contact} - b \omega_i$$
And chassis planar acceleration accounts for complete aerodynamic drag, grade resistance, and tire tractive forces:
$$m a_x = \sum F_{x, i} - F_{drag} - m g \sin(\theta_{grade})$$
