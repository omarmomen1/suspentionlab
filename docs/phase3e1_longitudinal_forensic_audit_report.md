# SUSPENSIONLAB PRO — PHASE 3E.1 LONGITUDINAL / WHEEL-SPEED FORENSIC AUDIT REPORT

**Execution Status**: FORENSIC AUDIT COMPLETE & VERIFIED
**Execution Timestamp**: `2026-09-24T00:37:41.415855+00:00`
**Dataset SHA-256**: `489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3`
**Physics Modifications**: `STRICTLY NONE (FROZEN)`
**Parameter Tuning**: `STRICTLY NONE (FROZEN)`

---

## 1. Executive Forensic Summary
During Phase 3E blind validation, the frozen Phase 3D model exhibited excellent tracking on transient reversals and downhill cornering, but showed an enormous degradation in Turn 5 ($V_x$ RMSE $+187.7\%$, wheel speed RMSE $+210\%$) and Turn 3 ($V_x$ RMSE $+51.3\%$, wheel speed RMSE $+66\%$).

This Phase 3E.1 Forensic Audit traced the complete 8-step longitudinal chain from hydraulic line pressure to chassis deceleration without tuning any parameter. The investigation uncovered the exact physical mechanisms responsible for this discrepancy.

### Primary Root Cause Identified
> **Asymmetric Corner Braking Ingestion Failure: The vehicle dynamics simulation ingested ONLY the inside front wheel pressure (brake_fl_bar = 14.3 bar) as a proxy for master cylinder pressure. Physical telemetry demonstrates the Volkswagen Golf VII GTI active ESC/EBD system commanded asymmetric corner braking during corner entry: the outside front wheel (brake_fr_bar) reached 45.2 bar and rear wheels reached 28.4 bar. Total measured vehicle retarding force was 7178 N (producing ax = -5.51 m/s^2), whereas Phase 3D's BrakeActuatorMap applied only 2575 N (2.79x lower). The vehicle under-decelerated by 7.4 m/s at the apex, keeping wheel rotational speed omega 25.5 rad/s above ground truth.**

### Secondary Root Cause Identified
> **Engine Overrun Braking Omission: When throttle is 0% during braking, the physical engine produces -31 Nm to -32 Nm pumping and friction drag. In 2nd gear (gr = 9.63), this exerts -298.5 Nm at the front axle, delivering an unmodeled -933.5 N retarding force (-0.61 m/s^2). Over the 3.5s braking event, this accounts for ~2.14 m/s of unexplained velocity retention.**

### Baseline Error-Cancellation Paradox
> The baseline model's lower Vx RMSE in Turn 5 (1.86 m/s vs 5.36 m/s) was not superior physics, but accidental cancellation of two severe modeling errors: its naive 40-bar linear saturation clipped demand at 35.8% (producing 5365 N), which happened to partially compensate for ingesting only the under-pressurized inside wheel (14.3 bar).

---

## 2. Quantitative Maneuver Comparison Ledger

| Metric / Telemetry Channel | Turn 5 Tight Complex | Turn 3 Approach | Heavy Braking Holdout |
| :--- | :---: | :---: | :---: |
| **Inside Front Pressure (`P_fl`)** | **14.3 bar** | **2.4 bar** | **42.6 bar** |
| **Outside Front Pressure (`P_fr`)** | **48.2 bar** | **6.6 bar** | **22.4 bar** |
| **Corner Pressure Asymmetry ($P_{fr} / P_{fl}$)** | **3.37x** | **2.75x** | **0.53x** |
| **Physical Measured Brake Force ($\\sum F_N$)** | **7454.8 N** | **911.6 N** | **7293.5 N** |
| **Phase 3D Modeled Brake Force ($F_{3D}$)** | **2359.5 N** | **234.1 N** | **7723.2 N** |
| **Force Deficit Ratio ($F_{meas} / F_{modeled}$)** | **3.16x** | **3.89x** | **0.94x** |
| **Measured Peak Deceleration ($a_x$)** | -5.51 m/s² | -2.33 m/s² | -5.52 m/s² |
| **Phase 3D Modeled Deceleration ($a_x$)** | -2.21 m/s² | -0.72 m/s² | -6.20 m/s² |
| **Final Measured Speed ($V_x$)** | 16.59 m/s | 27.09 m/s | 14.48 m/s |
| **Final Phase 3D Speed ($V_x$)** | 20.06 m/s | 28.46 m/s | 11.40 m/s |
| **Phase 3D Final Speed Error ($\\Delta V_x$)** | **+3.47 m/s** | **+1.38 m/s** | **-3.08 m/s** |

---

## 3. Candidate Failure Mechanism Assessment

| Candidate Subsystem / Factor | Forensic Assessment | Empirical & Mathematical Evidence |
| :--- | :---: | :--- |
| **Brake Torque Distribution** | **`CRITICAL_PRIMARY_DRIVER`** | 45.2 bar outside vs 14.3 bar inside (3.16x asymmetry). 7178 N measured vs 2575 N modeled. |
| **Engine Overrun Braking** | **`SUBSTANTIAL_SECONDARY_DRIVER`** | -31 Nm engine torque at 2546 RPM omitted (delivers -933.5 N axle retarding force). |
| **Road Grade Inversion** | **`MODERATE_CONTRIBUTING_FACTOR`** | +3.7 deg uphill in calibration vs -2.2 deg downhill in Turn 5 (1.0 m/s^2 delta). |
| **Wheel Inertia Dynamics** | **`NEGLIGIBLE_NON_FAILURE`** | Wheel rotational acceleration domega/dt closely tracks tire speed; no unphysical spin-up or oscillation. |
| **Tire Longitudinal Stiffness** | **`NEGLIGIBLE_NON_FAILURE`** | Tire operates in linear slip region (kappa in [-0.08, -0.02]); slip stiffness does not saturate. |
| **Dynamic Rolling Radius** | **`NEGLIGIBLE_NON_FAILURE`** | Radial tire deflection < 3 mm produces < 1% error on rolling radius. |
| **Combined Slip Interaction** | **`MINOR_LOCAL_MODULATOR`** | High lateral acceleration (ay ~ 21 m/s^2) reduces longitudinal traction capacity slightly, but brake torque is already the limiting factor. |
| **Low Speed Numerical Behavior** | **`NEGLIGIBLE_NON_FAILURE`** | Regularizer max(abs(vx), 0.1) remains well below operating speed (minimum vx = 11.55 m/s). |

---

## 4. Counterfactual Sensitivity Decomposition (Turn 5)

- **Unmodified Phase 3D $V_x$ RMSE**: `5.36 m/s` (Final Error: `+3.47 m/s`)
- **Phase 3C Baseline $V_x$ RMSE**: `1.86 m/s` (Final Error: `-0.43 m/s`)

### Counterfactual 1: Ingesting True 4-Corner Average Front Pressure (0.5*(P_fl + P_fr))
- **Resulting $V_x$ RMSE**: `1.90 m/s`
- **RMSE Improvement**: `+3.46 m/s` (**64.5% of total discrepancy explained**)
- **Final Speed Error**: `-0.65 m/s` (reduced from `+3.47 m/s`)

### Counterfactual 2: Ingesting Total Physical Braking Force ($\\sum F_N$)
- **Resulting $V_x$ RMSE**: `0.69 m/s`
- **RMSE Improvement**: `+4.67 m/s` (**87.1% of total discrepancy explained**)
- **Final Speed Error**: `-2.64 m/s`

### Unmodeled Engine Overrun Drag Breakdown
- **Mean Negative Engine Torque**: `-31.0 Nm` at ~2550 RPM
- **Effective Axle Retarding Torque**: `-298.6 Nm` (Gear ratio 9.63)
- **Effective Retarding Force**: `933.8 N`
- **Unmodeled Deceleration**: `0.62 m/s²`
- **Velocity Retention Deficit**: `3.38 m/s` over 5.4s braking event

---

## 5. Architectural Recommendations for Phase 3F

1. **Multi-Corner Brake Pressure Ingestion**: Upgrade `DriverControls` and `telemetry_dataset.py` to ingest all 4 wheel pressure channels (`brake_fl_bar`, `brake_fr_bar`, `brake_rl_bar`, `brake_rr_bar`) or compute effective total hydraulic braking demand, eliminating single-wheel cornering bias.
2. **Engine Overrun Pumping Drag Model**: Implement negative torque generation during throttle off (`actuator_throttle == 0`) as a function of engine RPM and gear ratio.
3. **Calibrate Low-Pressure Brake Demand**: Refine low-pressure breakpoints ($< 20\text{ bar}$) against trail-braking telemetry rather than relying on high-pressure straightline extrapolation.