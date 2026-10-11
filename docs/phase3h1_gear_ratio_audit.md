# SuspensionLab PRO — Phase 3H.1 Gear-Ratio Forensic Audit
## Telemetry Channel Semantics, Ratio Decomposition & Shift State Timeline

---

### 1. Telemetry Channel `GearRatio` Provenance

- **Measured Channel Value**: Constantly $13.585$ throughout the entire 9.0s window.
- **Physical Kinematic Ratio**: $\omega_{\text{eng}} / \omega_{\text{wheel}} = 5.6426$.
- **The $2.40\times$ Quotient**:
  $$\frac{13.585}{5.6426} = \mathbf{2.4076}$$
- **Dataset-Wide Pattern**: Across all 5 forward gears, the raw `GearRatio` channel is scaled by $\approx 2.40\times$:
  - Gear 1: $35.074 / 2.40 \approx 14.6$
  - Gear 2: $21.242 / 2.40 \approx 8.85$
  - Gear 3: $13.585 / 2.40 \approx 5.66$
  - Gear 4: $9.633 / 2.40 \approx 4.01$
  - Gear 5: $7.163 / 2.40 \approx 2.98$
- **Epistemic Classification**: Raw CAN channel scaling is classified as **`MODEL_SUPPORTED` / `UNIDENTIFIABLE`** (without DBC file), while physical transmission ratio **$N_{\text{total}} = 5.6426$** is directly confirmed.

---

### 2. Timeline Verification ($t \in [54.0, 63.0]\text{ s}$)

| Time (s) | Measured Gear Channel | Physical Operating Gear | Simulator Effective Gear | Measured RPM | Simulated RPM | Inferred Ratio |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **54.0** | 13.585 | 3rd Gear | 6th Gear (4.20) | 4682 | 3490 | 5.641 |
| **56.0** | 13.585 | 3rd Gear | 6th Gear (4.20) | 4810 | 3580 | 5.643 |
| **58.5** | 13.585 | 3rd Gear | 6th Gear (4.20) | 4935 | 3670 | 5.642 |
| **61.0** | 13.585 | 3rd Gear | 6th Gear (4.20) | 5060 | 3760 | 5.644 |
| **63.0** | 13.585 | 3rd Gear | 6th Gear (4.20) | 5166 | 3840 | 5.642 |

- **Gear Shift Events**: Zero shift events. Clutch engaged 100% of duration.
