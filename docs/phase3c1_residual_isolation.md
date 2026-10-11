# SuspensionLab PRO — Phase 3C.1 Residual Isolation Experiments

Controlled perturbation experiments executed on the frozen physics baseline to isolate root causes of observed residuals:

## Experiment A: Tire Stiffness Scaling Perturbation (Turn 4 Sweeper)
- **`s_tire_mult_0.85`**: Yaw RMSE = 1.68°/s, R² = 0.9507
- **`s_tire_mult_1.00`**: Yaw RMSE = 1.72°/s, R² = 0.9486
- **`s_tire_mult_1.15`**: Yaw RMSE = 1.83°/s, R² = 0.9413

## Experiment B: Brake Torque Gain Perturbation (Heavy Braking Holdout)
- **`brake_torque_mult_0.6`** (Max Torque: 2880.0 Nm): Vx RMSE = 2.39 m/s, Final Vx meas=14.5 vs pred=10.1 m/s
- **`brake_torque_mult_0.8`** (Max Torque: 3840.0 Nm): Vx RMSE = 4.50 m/s, Final Vx meas=14.5 vs pred=6.7 m/s
- **`brake_torque_mult_1.0`** (Max Torque: 4800.0 Nm): Vx RMSE = 6.49 m/s, Final Vx meas=14.5 vs pred=3.4 m/s
- **`brake_torque_mult_1.4`** (Max Torque: 6720.0 Nm): Vx RMSE = 8.58 m/s, Final Vx meas=14.5 vs pred=0.3 m/s

## Experiment C: Steering Compliance Perturbation (Turn 1 Entry)
- **`k_steer_0.000000`**: Yaw RMSE = 2.29°/s, R² = 0.9683
- **`k_steer_0.000451`**: Yaw RMSE = 2.22°/s, R² = 0.9701
- **`k_steer_0.000900`**: Yaw RMSE = 2.29°/s, R² = 0.9680

## Experiment D: Pitch Dynamics & Track Grade Decoupling
- **Suspension Pitch vs. Deceleration ($a_x$) Correlation**: **`0.3959`** (True physical coupling)
- **Inertial IMU Pitch vs. Deceleration ($a_x$) Correlation**: **`-0.2056`** (Negative correlation due to grade)
- **Peak Track Grade Pitch**: **3.71°** vs. Peak Suspension Pitch: **0.29°**

## Experiment E: Suspension Potentiometer Unit Scaling Verification
- Column: `suspFLpos_m`, Range: [6.039240000000005, 13.719120000000006]
- Unscaled interpretation stroke: 7.68 m (physically impossible)
- Correct SI scaled stroke: **76.8 mm** (matches Golf GTI kinematics)
