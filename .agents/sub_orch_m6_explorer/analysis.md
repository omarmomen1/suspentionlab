# Verification and Validation (VnV) Test Plan for Physics Models

## 1. Overview
This plan defines the mathematical VnV tests for the 2-DOF Quarter Car and 7-DOF Full Car models. These tests ensure the solvers yield results consistent with classical mechanical vibration theory. The test cases will be implemented in `tests/test_vnv_physics.py`.

## 2. Quarter Car (2-DOF) Tests

### 2.1 Steady-State Step Response
- **Objective**: Verify that a step input to the road profile results in a steady-state where both sprung and unsprung masses track the road perfectly.
- **Inputs**: `RoadProfile(profile_type="step", amplitude=0.05, duration=10.0)` using default `QuarterCarParams`.
- **Verification Criteria**:
  - Extract the final values at $t_{end}$.
  - $z_s \approx 0.05$ and $z_u \approx 0.05$.
  - Velocities ($dz_s, dz_u$) and accelerations ($ddz_s$) approach 0.
  - Suspension travel ($z_s - z_u$) approaches 0.

### 2.2 DC Transmissibility
- **Objective**: Verify that at $f \to 0$, the transmissibility magnitude $|Z_s/Z_r|$ and $|Z_u/Z_r|$ approaches 1.0 (0 dB).
- **Inputs**: `compute_frequency_response(p, f_min=0.001, f_max=1.0, n_points=10)` using default `QuarterCarParams`.
- **Verification Criteria**:
  - The first element of `transmissibility_body` should be $\approx 1.0$.
  - The first element of `transmissibility_wheel` should be $\approx 1.0$.

### 2.3 Undamped Natural Frequencies Match Analytical Formulas
- **Objective**: Verify the eigenvalue solution for natural frequencies matches analytical formulas when damping is zero.
- **Inputs**: `QuarterCarParams` with `c = 0.0`, `c_t = 0.0`.
- **Formulas**:
  - Sprung mass: $\omega_{n,s} = \sqrt{k_w / m_s}$
  - Unsprung mass: $\omega_{n,u} = \sqrt{(k_w + k_t) / m_u}$
- **Verification Criteria**:
  - Call `compute_modal_properties(p)`.
  - Result `omega_n_s` matches analytical formula perfectly.
  - Result `omega_n_u` matches analytical formula perfectly.

## 3. Full Car (7-DOF) Tests

For the full car decoupling tests, we define a perfectly symmetric vehicle:
- $m_s = 1000, I_x = 400, I_y = 1000$
- $a = 1.5, b = 1.5$ (CG exactly in the middle)
- $tw_f = 1.5, tw_r = 1.5$
- $m_{uf} = 40, m_{ur} = 40$
- $k_{sf} = 30000, k_{sr} = 30000$
- $c_f = 2000, c_r = 2000$
- $k_{arb\_f} = 10000, k_{arb\_r} = 10000$
- $k_{tf} = 200000, k_{tr} = 200000$
- $speed\_mps = 10.0$

Create a sine wave profile: $A(t) = 0.05 \sin(2 \pi \cdot 2 \cdot t)$ for a few seconds.

### 3.1 Pure Heave Decoupling
- **Objective**: Verify that symmetric heave excitation produces pure heave motion without exciting pitch or roll.
- **Inputs**: `z_rfl = z_rfr = z_rrl = z_rrr = A(t)`
- **Verification Criteria**:
  - $z_s(t)$ has non-zero variations (e.g., max absolute value > 0.001).
  - $\theta(t)$ (pitch) is uniformly $\approx 0$ (allclose to 0 with `atol=1e-7`).
  - $\phi(t)$ (roll) is uniformly $\approx 0$.

### 3.2 Pure Pitch Decoupling
- **Objective**: Verify that asymmetric front/rear excitation produces pure pitch motion without exciting heave or roll.
- **Inputs**: `z_rfl = z_rfr = A(t)`, `z_rrl = z_rrr = -A(t)`
- **Verification Criteria**:
  - $\theta(t)$ has non-zero variations.
  - $z_s(t)$ (heave) is uniformly $\approx 0$.
  - $\phi(t)$ (roll) is uniformly $\approx 0$.

### 3.3 Pure Roll Decoupling
- **Objective**: Verify that asymmetric left/right excitation produces pure roll motion without exciting heave or pitch.
- **Inputs**: `z_rfl = z_rrl = A(t)`, `z_rfr = z_rrr = -A(t)`
- **Verification Criteria**:
  - $\phi(t)$ has non-zero variations.
  - $z_s(t)$ (heave) is uniformly $\approx 0$.
  - $\theta(t)$ (pitch) is uniformly $\approx 0$.

## 4. Implementation Guidelines for `test_vnv_physics.py`
- Use `pytest` to structure the test cases.
- Use `np.testing.assert_allclose` for array comparisons and scalar float comparisons with appropriate tolerances (`atol=1e-7`).
- Note that `run_full_car_analysis` expects `FourCornerRoadProfile` and `FullCarParams`.
- Note that `run_quarter_car_analysis` expects `RoadProfile` and `QuarterCarParams`. The Quarter car frequency and modal tests can invoke `compute_frequency_response` and `compute_modal_properties` directly without doing a full simulation run.
