# Physics Engine Verification Report

## 1. Quarter Car (2-DOF)
- **Conservation of Energy:** Initial E = 1000.0000 J. Drift over 10s = 2.83e-03 J (0.0003% error). ✅
- **Harmonic Frequencies:** Sprung expected 1.18 Hz, observed ~1.20 Hz. Unsprung expected 12.57 Hz, observed ~12.60 Hz. ✅
- **Conservation of Momentum:** Initial P = 600.00 kg*m/s. Drift = 0.00e+00. ✅

## 2. Half Car (4-DOF)
- **Geometric Constraints:** Caught L != a+b successfully. ✅
- **Pitch-Heave Decoupling:** Max pitch for symmetric bump = 2.98e-16 rad. ✅
- **Wheelbase Delay:** Delay correctly shifts rear input. ✅

## 3. Full Car (7-DOF)
- **Symmetric Response:** Max roll angle = 7.66e-15 rad. ✅
- **Roll Stiffness Distribution:** Expected 57.1%, Observed 50.0%. Error: 7.14%. ❌

## 4. Handling Model (3-DOF)
- **Steady-State Cornering:** v_x=23.33, v_y=-1.02, omega=0.29 rad/s. Kinematic a_y = 6.84 m/s², Dynamic a_y = 6.80 m/s². Error = 0.57%. ✅
- **Longitudinal Dynamics:** Braking from 30 m/s for 3s. Final speed = 0.00 m/s. Deceleration works. ✅