# SuspensionLab PRO — Phase 3H.2 Gear Kinematics & Inference
## Dataset-Wide Kinematic Ratio Verification & Status Classification

---

### 1. Kinematic Ratio Derivation
The instantaneous transmission ratio is derived from fundamental kinematic principles:
$$N = \frac{\omega_{\text{engine}}}{\omega_{\text{driven\_wheel}}}$$

- Configured candidate ratios for Volkswagen Golf VII GTI DQ250:
  - Gear 1: $14.6703$ (Gearbox $3.4615 \times$ FD $4.2381$)
  - Gear 2: $8.6881$ (Gearbox $2.0500 \times$ FD $4.2381$)
  - Gear 3: $5.6427$ (Gearbox $1.3314 \times$ FD $4.2381$)
  - Gear 4: $4.0920$ (Gearbox $0.9655 \times$ FD $4.2381$)
  - Gear 5: $3.3213$ (Gearbox $1.0323 \times$ FD $3.2174$)
  - Gear 6: $3.0028$ (Gearbox $0.9333 \times$ FD $3.2174$)

---

### 2. Full-Dataset Validation Results (22,304 Samples)
- **Total Locked Clutch Samples**: **91.6\%** of entire lap.
- **Gear Breakdown**:
  - Gear 1: 1668 samples (locked mean residual: 0.0312)
  - Gear 2: 3305 samples (locked mean residual: 0.0156)
  - Gear 3: 12791 samples (locked mean residual: 0.0048)
  - Gear 4: 2776 samples (locked mean residual: 0.0397)
  - Gear 5: 152 samples (locked mean residual: 0.0435)
  - Gear 6: 1612 samples (locked mean residual: 0.0042)

**Epistemic Rule**: Raw CAN `GearRatio` is strictly treated as opaque metadata; never used as an index into gear arrays.
