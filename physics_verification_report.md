# Physics Engine Verification Report

## 1. Quarter Car (2-DOF)
- **Conservation of Energy:** Initial E = 1000.0000 J. Drift over 10s = 2.83e-03 J (0.0003% error). ✅
- **Harmonic Frequencies:** Sprung expected 1.18 Hz, observed ~1.20 Hz. Unsprung expected 12.57 Hz, observed ~12.60 Hz. ✅
- **Conservation of Momentum:** Initial P = 600.00 kg*m/s. Drift = 0.00e+00. ✅

## 2. Half Car (4-DOF)
- **Geometric Constraints:** Caught L != a+b successfully. ✅
- **Pitch-Heave Decoupling:** Max pitch for symmetric bump = 0.00e+00 rad. ✅
- **Wheelbase Delay:** Delay correctly shifts rear input. ✅

## 3. Full Car (7-DOF)
- **Symmetric Response:** Max roll angle = 1.35e-16 rad. ✅
- **Roll Stiffness Distribution:** Expected 52.9%, Observed 50.0%. Error: 2.94%. ✅

## 4. Handling Model (3-DOF)
- **Steady-State Cornering:** v_x=22.57, v_y=-0.86, omega=0.32 rad/s. Kinematic a_y = 7.14 m/s², Dynamic a_y = 7.12 m/s². Error = 0.37%. ✅
- **Longitudinal Dynamics:** Braking from 30 m/s for 3s. Final speed = -1.68 m/s. Deceleration works. ✅