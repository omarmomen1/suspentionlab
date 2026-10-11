# SUSPENSIONLAB PRO — PHASE 3D CONTROLLED CHANGE LOG

**Phase**: Phase 3D Controlled Empirical Physics Correction
**Governance Mode**: ISOLATED, TRACEABLE, REVERSIBLE
**Git Commit Baseline**: `fbe3d045762d8c216922630ca5c3b0da1d589a31`

---

## Change Ledger

### Change 1: Channel-Level Telemetry Unit Normalization
- **Target File**: `src/suspensionlab/physics/telemetry_dataset.py`
- **Description**: Added ChannelUnitNormalizer, detecting centimeter potentiometer channels and converting to SI meters with explicit audit logs.
- **Reversibility**: Parameter flags toggle each feature cleanly back to rigid / nominal baseline defaults.

### Change 2: Grade-Decoupled Chassis Suspension Pitch
- **Target File**: `src/suspensionlab/physics/dynamic_lap_sim.py`
- **Description**: Decoupled suspension pitch theta_susp = (zf - zr)/Lwb from track grade contamination in theta_imu.
- **Reversibility**: Parameter flags toggle each feature cleanly back to rigid / nominal baseline defaults.

### Change 3: Endogenous Steering Compliance
- **Target File**: `src/suspensionlab/physics/dynamic_lap_sim.py`
- **Description**: Added linear compliance k_delta = 0.000451 rad/(m/s^2) driven strictly by endogenous lateral acceleration u * r.
- **Reversibility**: Parameter flags toggle each feature cleanly back to rigid / nominal baseline defaults.

### Change 4: Configurable Brake Actuator / Pressure Mapping
- **Target File**: `src/suspensionlab/physics/dynamic_lap_sim.py`
- **Description**: Replaced hardcoded 40-bar lockup with BrakeActuatorMap, separating pressure, demand, clamping torque, and tractive force.
- **Reversibility**: Parameter flags toggle each feature cleanly back to rigid / nominal baseline defaults.

### Change 5: Tire Calibration Architecture & Governance
- **Target File**: `src/suspensionlab/physics/dynamic_lap_sim.py`
- **Description**: Implemented TireCalibrationRecord and apply_tire_calibration() with cryptographic SHA-256 lineage, preventing global constant baking.
- **Reversibility**: Parameter flags toggle each feature cleanly back to rigid / nominal baseline defaults.
