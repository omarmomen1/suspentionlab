# Phase 3H.3 — Authentic Shift Evidence Forensic Audit Report

**Status:** COMPLETE  
**Dataset:** `stanford_vw_golf_thunderhill_2023_11.csv` (SHA: `489adbf01d27da1c...`)  
**Sample Count:** 22304 rows @ 200 Hz (111.52 s)  

---

## 1. Executive Summary

A forensic reconstruction of the complete 111.52-second track dataset was conducted to identify all authentic transmission shift events, standing start launch, clutch slip intervals, shift durations, and torque cut transients.

---

## 2. Epistemic Classification of Observables

| Channel / Feature | Epistemic Label | Forensic Evidence |
| :--- | :--- | :--- |
| `engine_rpm` | **MEASURED** | Raw ECU sensor stream via CAN bus. |
| `wheelspeed_*` | **MEASURED** | Raw wheel hub ABS encoder pulse frequencies. |
| `engineTorque_Nm` | **MEASURED** | Raw ECU internal indicated torque CAN broadcast. |
| `throttleCmd_percent` | **MEASURED** | Raw accelerator pedal position sensor. |
| `brake_fl_bar` | **MEASURED** | Raw hydraulic brake caliper pressure transducer. |
| `Kinematic Ratio` | **KINEMATICALLY_INFERRED** | Reconstructed via $R = \text{RPM}_{\text{eng}} / \text{RPM}_{\text{wheel}}$. |
| `Discrete Gear` | **KINEMATICALLY_INFERRED** | Mapped from $R$ to manufacturer candidate ratios within 15% tolerance. |
| `Clutch Slip` | **KINEMATICALLY_INFERRED** | Departure of $R$ from nominal candidate ratios during launch and shifts. |
| `Shift Torque Cut` | **MODEL_SUPPORTED** | Measured ECU negative torque ($-72\text{ Nm}$) during $2 \to 3$ upshift lasting 95 ms. |
| `Downshift Blip` | **MODEL_SUPPORTED** | Measured ECU torque spike ($+132\text{ Nm}$) with 0% driver throttle into Turn 5. |
| `Clutch Clamping Force` | **UNIDENTIFIABLE** | Not recorded by production vehicle CAN stream. |
| `Clutch Torque Split` | **UNIDENTIFIABLE** | Individual clutch plate pressures $P_{C1}, P_{C2}$ are unobservable. |

---

## 3. Key Reconstructed Shift Events

### 3.1 Standing Start Launch (t = 0.00 to 7.08 s)
- Driver applies 34.0 bar brake pressure, holds throttle at 39%, engine revs to 1224 RPM.
- Brake release at $t = 7.08\text{ s}$ initiates clutch slip, accelerating vehicle into 1st gear.

### 3.2 Upshift 1 -> 2 (t = 8.35 s)
- Vehicle speed $V_x = 8.2\text{ m/s}$, throttle 100%, shift duration 170 ms.

### 3.3 Upshift 2 -> 3 with Torque Cut (t = 12.64 to 12.75 s)
- Prior to shift ($t = 12.63\text{ s}$): engine torque $+231\text{ Nm}$, RPM 6086, throttle 100%.
- Torque cut initiation ($t = 12.64\text{ s}$): torque drops to $+81\text{ Nm}$.
- Negative torque transient ($t = 12.65\text{ s}$ to $12.745\text{ s}$): torque drops to **$-72\text{ Nm}$** for **95 ms** to actively decelerate input shaft inertia from 6086 to 4540 RPM.
- Re-engagement ($t = 12.75\text{ s}$): torque returns to $+145\text{ Nm}$, re-accelerating in 3rd gear.

### 3.4 Turn 5 Braking Downshift Rev-Match (t = 77.80 s)
- Driver applies 13.1 bar brake pressure with 0% throttle.
- Downshift from 3rd to 2nd gear triggers an automatic ECU rev-match throttle blip, producing a **$+132\text{ Nm}$** torque pulse and raising engine speed from 2221 to 3006 RPM.
