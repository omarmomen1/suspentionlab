# SuspensionLab PRO — Phase 3H Powertrain Audit
## Engine Torque, Gearbox Scaling, and Drive Torque Transition Audit

---

### 1. Comparative Powertrain Telemetry

| Powertrain Channel | Physical Telemetry (CAN Bus) | Production Simulator Implementation | Status |
| :--- | :---: | :---: | :--- |
| **Throttle Demand** | Mean: $20.69\%$, Min: $4.20\%$, Max: $84.99\%$ | Mean: $20.69\%$, Min: $4.20\%$, Max: $84.99\%$ | Identical Ingestion |
| **Engine Speed (RPM)** | Mean: $4930.9\text{ RPM}$, Range: $[4682, 5166]$ | Simulated: Below $3600\text{ RPM}$ | Starved due to gear ratio |
| **Gear Ratio ($N_{total}$)** | Constant: **$13.585$** | Effective: **$4.200$** (clamped to 6th gear) | **3.23x Discrepancy** |
| **Engine Torque** | Mean: $86.28\text{ Nm}$, Peak: $354.0\text{ Nm}$ | Full curve: $\approx 360\text{ Nm} \times \text{thr} \approx 74.5\text{ Nm}$ | Synthetic formula curve |
| **Axle Drive Torque** | Mean: **$1054.9\text{ Nm}$** ($86.28 \times 13.585 \times 0.90$) | Mean: **$268.4\text{ Nm}$** | **74.6% Torque Under-Delivery** |

---

### 2. Core Forensic Question: Does the Simulator Apply Too Much Drive Torque?

**VERDICT: NO.**
The simulator applies **too little positive drive torque** during throttle transitions:
- Under-delivers axle drive torque by **$786.5\text{ Nm}$** ($74.6\%$ deficit).
- Under-delivers wheel tractive force by **$2459\text{ N}$**.
- In the real car, $1054.9\text{ Nm}$ of axle torque yields $+3298.5\text{ N}$ of forward thrust, effortlessly overcoming the $1200.6\text{ N}$ combined road load (aero + grade).
- In the simulator, $268.4\text{ Nm}$ yields only $+839.3\text{ N}$, resulting in continuous decelerating drag.
