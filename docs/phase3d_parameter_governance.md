# SUSPENSIONLAB PRO — PHASE 3D PARAMETER GOVERNANCE & PROVENANCE REGISTRY

**Registry Status**: IMMUTABLE & CRYPTOGRAPHICALLY SECURED
**Timestamp**: `2026-09-22T02:06:48.680389+00:00`
**Dataset SHA-256**: `489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3`

---

## Calibrated Parameter Registry

| Parameter | Nominal Default | Calibrated Value | Calibration Maneuver | Cryptographic SHA-256 Hash | Governance Policy |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **pKy1 (Pacejka Cornering Stiffness)** | `15.0` | `17.4` | Turn 4 High-Speed Sweeper (Phase 3C.2 fine sweep) | `32459d7f3daf01e6...` | Setup-level parameter; never hardcoded in global physics equations. |
| **steering_compliance_rad_per_mps2 (k_delta)** | `0.0` | `0.000451` | Turn 1 Dynamic Reversal | `ab88210d3db715da...` | Purely endogenous formulation (u * r); zero external telemetry injection. |
| **brake_actuator_map** | `Linear 40 bar clip` | `Configurable Map` | Controlled Heavy Braking Segment | `dca0a3f53ff61e08...` | Separates line pressure, demand, clamping torque, and tractive force. |

## Governance Principles Enforced
1. **Setup-Level Isolation**: Calibrated values reside in setup profiles; global solver equations never hardcode calibration numbers.
2. **Default Parity**: When initialized without arguments, vehicle parameters strictly evaluate uncalibrated nominal physics.
3. **Cryptographic Lineage**: Every calibration record contains SHA-256 hashes binding parameters directly to source datasets.