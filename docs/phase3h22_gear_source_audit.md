# SuspensionLab PRO — Phase 3H.2.2 Audit Report
## Path-B Discrete Gear Source Identification & Trace

### Source Hierarchy Trace:
1. `DriverControls(..., gear=meta['gear_expected'])` provides the maneuver-level boundary gear index.
2. In `PowertrainCorrectedLapSimulator.compute_derivatives`:
   ```python
   rpm_eval = self.current_meas_rpm if self.use_measured_rpm else max(p.idle_rpm, (omega_drive * 5.6427 * (60.0 / (2.0 * math.pi))))
   gear_res = self.gear_engine.infer_gear(engine_rpm=rpm_eval, driven_wheel_speed_radps=omega_drive)
   active_gear = gear_res.inferred_gear
   gr = gear_res.matched_nominal_ratio
   ```
3. When `use_measured_rpm=False` (Path B), `infer_gear` computes:
   $$\frac{\omega_{\text{eng}}}{\omega_{\text{drive}}} = \frac{\omega_{\text{drive}} \cdot 5.6427}{\omega_{\text{drive}}} \equiv 5.6427$$
   matching candidate ratio candidate 3 ($5.6427$).

### Classification:
- **Authoritative Classification**: **`PRECOMPUTED_BOUNDARY`**
- **Excluded Classifications**:
  - `ENDOGENOUS_PREDICTION`: Rejected because the system lacks a dynamic shift-scheduling state machine.
  - `MEASURED_REPLAY`: Rejected because measured CAN channels are strictly bypassed.

**Verdict**: **`SOURCE_CLASSIFICATION_CERTIFIED`**
