# SuspensionLab PRO — Phase 3C.1 Calibration Provenance Audit

| Parameter | Description | Initial | Identified | Method | Classification | Epistemic Governance |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`s_tire`** | Tire Cornering Stiffness Scaling Multiplier (Magic Formula pKy1) | 1.0 | **1.3161** | Bounded scalar optimization (SciPy minimize_scalar) | **`IDENTIFIED_MODEL_CALIBRATION`** | Must NOT be described as a directly measured tire stiffness property; Norbert test tires were not tested on a laboratory flat-track machine. |
| **`s_susp`** | Chassis Roll Stiffness Scaling Multiplier | 1.0 | **0.9807** | Bounded scalar optimization | **`IDENTIFIED_MODEL_CALIBRATION`** | Identified from transient roll angle; physical four-post rig data absent in repository. |
| **`k_delta`** | Steering Linkage Compliance Coefficient | 0.0 | **0.000451** | Linear regression of steering residual against ay | **`IDENTIFIED_MODEL_CALIBRATION`** | Must NOT be labeled as measured steering compliance; K&C rig compliance curves absent. |
| **`phi_bias`** | IMU Zero Roll Mounting Tilt Bias | 0.0 | **-0.0293** | Mean offset computation | **`IDENTIFIED_SENSOR_BIAS`** | Represents physical sensor mounting tilt relative to chassis body datum. |
| **`Rw`** | Dynamic Free-Rolling Tire Radius | 0.315 | **0.3198** | Mean kinematic ratio | **`KINEMATICALLY_DERIVED_MEASUREMENT`** | Matches 225/40R18 nominal tire spec (0.321 m nominal radius with 1.2 mm vertical carcass deflection). |
| **`z0_FL, z0_FR, z0_RL`** | Static Suspension Potentiometer Zero Datums | [0.0, 0.0, 0.0] | **[9.78072, 10.08356, 7.9036]** | Static mean sample | **`IDENTIFIED_SENSOR_DATUM`** | Represents raw physical potentiometer voltages mapped to centimeters at static ride height. |
