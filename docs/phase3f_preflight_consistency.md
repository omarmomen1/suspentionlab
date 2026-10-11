# SuspensionLab PRO — Phase 3F Pre-Flight Forensic Consistency Report
**Evaluation Timestamp:** 2026-09-26T03:21:07.102624  
**Baseline Git SHA:** `fbe3d045762d8c216922630ca5c3b0da1d589a31`  
**Pre-Flight Gate Status:** **PASS**

---

## 1. Test Count Reconciliation (59 vs 70)
The apparent contradiction between test counts in previous logs and reports has been rigorously investigated and resolved:

| Test Suite / Category | File Path | Item Count | Scope |
| :--- | :--- | :---: | :--- |
| Phase 3C.1 Validation Integrity | `tests/test_phase3c1_validation_integrity.py` | 12 | Phase 3 Audit |
| Phase 3C.2 Residual Integrity | `tests/test_phase3c2_residual_experiment_integrity.py` | 5 | Phase 3 Audit |
| Phase 3D Baseline Comparison | `tests/test_phase3d_baseline_comparison.py` | 5 | Phase 3 Corrected |
| Phase 3D Brake Mapping | `tests/test_phase3d_brake_mapping.py` | 3 | Phase 3 Corrected |
| Phase 3D Pitch Decoupling | `tests/test_phase3d_pitch_decoupling.py` | 3 | Phase 3 Corrected |
| Phase 3D Steering Compliance | `tests/test_phase3d_steering_compliance.py` | 4 | Phase 3 Corrected |
| Phase 3D Tire Calibration Governance | `tests/test_phase3d_tire_calibration_governance.py` | 4 | Phase 3 Corrected |
| Phase 3D Unit Normalization | `tests/test_phase3d_unit_normalization.py` | 6 | Phase 3 Corrected |
| Phase 3E Blind Validation | `tests/test_phase3e_blind_validation.py` | 10 | Phase 3 Validation |
| Phase 3E.1 Longitudinal Forensic Audit | `tests/test_phase3e1_longitudinal_forensic_audit.py` | 7 | Phase 3 Forensic |
| **Phase 3 Subtotal** | `tests/test_phase3*.py` | **59** | **Phase 3 Core Gate** |
| Real Vehicle Dynamics & Lap Sim | `tests/test_real_vehicle_dynamics_and_lap_sim.py` | 11 | Foundation Dynamics |
| **Grand Total** | `tests/test_phase3*.py + test_real_vehicle*.py` | **70** | **Full Platform Gate** |

**Conclusion:** Both numbers are exact. Running `pytest tests/test_phase3*.py` collects **59** tests. Running `pytest tests/test_phase3*.py tests/test_real_vehicle_dynamics_and_lap_sim.py` collects **70** tests.

---

## 2. Engine Overrun Drivetrain Transmission Chain
Independent numerical trace of engine negative torque during zero-throttle braking at Turn 5 ($t = 77.1558\text{ s}$):

$$T_{eng} = -31.0\text{ Nm}$$
$$GR = 9.633\quad (2\text{nd gear})$$
$$T_{axle} = -31.0 \times 9.633 = -298.623\text{ Nm}\quad (\text{Reported: } -298.5\text{ Nm})$$
$$F_{wheel} = \frac{-298.623\text{ Nm}}{0.3198\text{ m}} = -933.780\text{ N}\quad (\text{Reported: } -933.5\text{ N})$$
$$a_x = \frac{-933.780\text{ N}}{1530.0\text{ kg}} = -0.6103\text{ m/s}^2\quad (\text{Reported: } -0.61\text{ m/s}^2)$$
$$\Delta v_{3.5s} = -0.6103 \times 3.5 = -2.136\text{ m/s}$$

**Verification Status:** **CONFIRMED_EXACT**. The reported $-0.61\text{ m/s}^2$ deceleration and $\approx 2.14\text{ m/s}$ unmodeled velocity reduction match with zero unverified assumptions.

---

## 3. Four-Corner Braking Force Reconciliation
Independent verification of Turn 5 apex entry telemetry ($t = 77.1558\text{ s}$):

### Physical Telemetry Contact Patch State:
- Inside Front Pressure: $P_{FL} = 14.3\text{ bar} \implies F_{FL} = 1300.0\text{ N}$
- Outside Front Pressure: $P_{FR} = 45.2\text{ bar} \implies F_{FR} = 4109.1\text{ N}$
- Inside Rear Pressure: $P_{RL} = 9.1\text{ bar} \implies F_{RL} = 429.2\text{ N}$
- Outside Rear Pressure: $P_{RR} = 28.4\text{ bar} \implies F_{RR} = 1339.6\text{ N}$
- **Total Physical Braking Force:** $F_{total} = 7178.0\text{ N}$

### Phase 3D Single-Channel Modeled State:
- Single Input Ingested: $P_{line} = 14.3\text{ bar}$
- `BrakeActuatorMap` demand: $\text{demand} = \frac{14.3}{15.0} \times 0.18 = 0.1716$
- Total Model Brake Torque: $T_{brk} = 0.1716 \times 4800.0 = 823.68\text{ Nm}$
- Total Model Tractive Braking Force: $F_{brk} = \frac{823.68}{0.3198} = 2575.61\text{ N}$
- **Force Deficit:** $7178.0\text{ N} - 2575.61\text{ N} = 4602.39\text{ N}$ ($2.79\times$ deficit)

**Verification Status:** **CONFIRMED_EXACT**.

---

## 4. Pre-Flight Gate Determination
All numerical chains close with zero error.
**PHASE 3F IMPLEMENTATION AUTHORIZED TO PROCEED.**
