# SuspensionLab PRO — Phase 3H.2.1 Audit Report
## Driveline Data Provenance Audit

### Channel-by-Channel Provenance Matrix:
| Parameter | ACTUATOR_REPLAY Path A | POWERTRAIN_PREDICTION Path B | Physical Transducer Present? |
| :--- | :---: | :---: | :---: |
| **Engine Torque** | `MEASURED` | `MODEL_SUPPORTED` / `EXTRAPOLATED` | Yes (CAN Crankshaft Strain Gauge) |
| **Engine RPM** | `MEASURED` | `DERIVED` (Algebraic Kinematic) | Yes (Crankshaft Hall Sensor) |
| **Wheel RPM** | `MEASURED` | `MODEL_SUPPORTED` (14-DOF Dyn) | Yes (ABS Tone Ring) |
| **Gear Index** | `INFERRED` | `INFERRED` | No (Inferred from Kinematics) |
| **Total Transmission Ratio** | `INFERRED` | `INFERRED` | No (Inferred from DQ250 Candidates) |
| **Drivetrain Efficiency** | `MODEL_SUPPORTED` (eta = 0.90) | `MODEL_SUPPORTED` (eta = 0.90) | Assumed Physical Parameter |
| **Axle Torque** | **`INFERRED`** | **`INFERRED`** | **No (Zero Axle Transducers)** |
| **Tractive Force** | **`INFERRED`** | **`INFERRED`** | **No** |
| **Engine Power** | `DERIVED` | `DERIVED` | Computed ($T \cdot \omega$) |
| **Axle Power** | **`INFERRED`** | **`INFERRED`** | Computed ($T_{axle} \cdot \omega$) |

**Verdict**: **`PROVENANCE_INTEGRITY_CERTIFIED`**
