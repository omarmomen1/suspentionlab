# Handoff Report: VnV Test Plan for Physics Models

## 1. Observation
I have analyzed the `quarter_car.py` and `full_car.py` models:
- **Quarter Car**: Uses state-space representations and ODE integration for time response (`run_quarter_car_analysis` -> `simulate_time_response`), and analytical impedance matrices for frequency response (`compute_frequency_response`). Eigenvalues of the state matrix are used for natural frequencies (`compute_modal_properties`). The analytical formula for natural frequencies uses $k_w = k_s \times MR^2$.
- **Full Car**: Uses a 14-state space model formed by mass, stiffness, and damping matrices (`build_full_car_state_space`), simulated via `scipy.signal.lsim` in `run_full_car_analysis`. State variables include $z_s$ (heave), $\theta$ (pitch), and $\phi$ (roll).

## 2. Logic Chain
- To verify the steady-state of the quarter car, a simple step input can be provided. At steady-state, velocities/accelerations decay to 0, and position matches the step amplitude.
- To verify DC transmissibility, low frequency evaluation of the transfer functions should asymptotically approach 1.
- Undamped natural frequencies can be checked by setting damping parameters (`c`, `c_t`) to zero and verifying that the eigenvalue-derived modes match the exact $1/ \sqrt{m \dots}$ formulas.
- For the full car, the 7-DOF model couples heave, pitch, and roll. A completely symmetric parameterization ensures that the mass, damping, and stiffness matrices are diagonalized in terms of the modes. Therefore, applying pure heave (all 4 wheels equal), pure pitch (front vs rear), or pure roll (left vs right) excitations should perfectly isolate those respective motions, leaving the other body DOFs precisely at 0.

## 3. Caveats
- No numerical integration is perfect; "exactly 0" in simulations means checking against a small numerical tolerance (`atol=1e-7`) with `np.testing.assert_allclose`.
- For the step response, it must be simulated long enough for transients to decay, so `duration=10.0` or checking only the last point of the simulation is recommended.

## 4. Conclusion
The detailed plan for the 6 requested test cases has been successfully drafted and saved. The plan includes the objective, inputs, and verification criteria for each test.

## 5. Verification Method
- Implement the test cases in `tests/test_vnv_physics.py` as instructed in `analysis.md`.
- Run `pytest tests/test_vnv_physics.py` from the project root.
- All tests should pass without errors.
