# SuspensionLab PRO — Phase 3C.1 Complete Input-Dependency Graph

This document traces the complete signal flow from physical telemetry to predicted outputs for all 19 validated quantities.

## Output: `yaw_rate`
- **Direct Measured Inputs**: `roadWheelAngle_rad, throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `bank_rad, grade_rad`
- **Initial Conditions**: `yawRate_radps[0], yawAngle_rad[0], Vx_mps[0], Vy_mps[0]`
- **Derived States**: `actuator_steering_rad, steering_deg, T_drive, T_brake, Mz_diff`
- **Simulation States**: `yaw_rate_rads, v_mps, u_mps, tire_relaxation_sigma_y`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: yawRate_radps is only used for initial condition at t=0; never injected during simulation.

## Output: `roll`
- **Direct Measured Inputs**: `roadWheelAngle_rad, throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `bank_rad, grade_rad`
- **Initial Conditions**: `rollAngle_rad[0] - phi_bias, rollRate_radps[0]`
- **Derived States**: `dFz_lat_f, dFz_lat_r, M_roll_inertial, F_susp_diff`
- **Simulation States**: `roll_phi, roll_rate, heave_z_s, ay`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: rollAngle_rad is used only for t=0 initial condition with mounting bias removal; never injected.

## Output: `suspension_travel_FL`
- **Direct Measured Inputs**: `roadWheelAngle_rad, throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `bank_rad, grade_rad`
- **Initial Conditions**: `heave_z_s=0, z_u_fl=0`
- **Derived States**: `z_s_fl = heave_z_s - a*theta + (tw_f/2)*phi, def_fl = z_s_fl - z_u_fl`
- **Simulation States**: `heave_z_s, pitch_theta, roll_phi, z_u_fl`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: Measured suspFLpos_m is never injected into simulation states or force equations.

## Output: `suspension_travel_FR`
- **Direct Measured Inputs**: `roadWheelAngle_rad, throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `bank_rad, grade_rad`
- **Initial Conditions**: `heave_z_s=0, z_u_fr=0`
- **Derived States**: `z_s_fr = heave_z_s - a*theta - (tw_f/2)*phi, def_fr = z_s_fr - z_u_fr`
- **Simulation States**: `heave_z_s, pitch_theta, roll_phi, z_u_fr`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: Measured suspFRpos_m is never injected into simulation states or force equations.

## Output: `suspension_travel_RL`
- **Direct Measured Inputs**: `roadWheelAngle_rad, throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `bank_rad, grade_rad`
- **Initial Conditions**: `heave_z_s=0, z_u_rl=0`
- **Derived States**: `z_s_rl = heave_z_s + b*theta + (tw_r/2)*phi, def_rl = z_s_rl - z_u_rl`
- **Simulation States**: `heave_z_s, pitch_theta, roll_phi, z_u_rl`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: Measured suspRLpos_m is never injected into simulation states or force equations.

## Output: `suspension_travel_RR`
- **Direct Measured Inputs**: `roadWheelAngle_rad, throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `bank_rad, grade_rad`
- **Initial Conditions**: `heave_z_s=0, z_u_rr=0`
- **Derived States**: `z_s_rr = heave_z_s + b*theta - (tw_r/2)*phi, def_rr = z_s_rr - z_u_rr`
- **Simulation States**: `heave_z_s, pitch_theta, roll_phi, z_u_rr`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: RR sensor is physically missing on car; measured comparison uses rigid chassis planar reconstruction.

## Output: `wheel_speed_FL`
- **Direct Measured Inputs**: `throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `roadWheelAngle_rad, grade_rad`
- **Initial Conditions**: `wheelspeed_fl[0]`
- **Derived States**: `T_drive_fl, T_brk_fl, Fx_fl, kappa_fl`
- **Simulation States**: `omega_fl, u_mps, tire_relaxation_sigma_x`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`True`**
  - Notes: In FULLY_BLIND, omega_fl evolves purely from torque balance. In SPEED_CONDITIONED, forced Vx alters tire force feedback.

## Output: `wheel_speed_FR`
- **Direct Measured Inputs**: `throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `roadWheelAngle_rad, grade_rad`
- **Initial Conditions**: `wheelspeed_fr[0]`
- **Derived States**: `T_drive_fr, T_brk_fr, Fx_fr, kappa_fr`
- **Simulation States**: `omega_fr, u_mps, tire_relaxation_sigma_x`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`True`**
  - Notes: In FULLY_BLIND, omega_fr evolves purely from torque balance. In SPEED_CONDITIONED, forced Vx alters tire force feedback.

## Output: `wheel_speed_RL`
- **Direct Measured Inputs**: `brake_fl_bar`
- **Indirect Measured Inputs**: `grade_rad`
- **Initial Conditions**: `wheelspeed_rl[0]`
- **Derived States**: `T_brk_rl, Fx_rl, kappa_rl`
- **Simulation States**: `omega_rl, u_mps, tire_relaxation_sigma_x`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`True`**
  - Notes: In FULLY_BLIND, undriven rear wheel speed evolves via braking torque and road friction.

## Output: `wheel_speed_RR`
- **Direct Measured Inputs**: `brake_fl_bar`
- **Indirect Measured Inputs**: `grade_rad`
- **Initial Conditions**: `wheelspeed_rr[0]`
- **Derived States**: `T_brk_rr, Fx_rr, kappa_rr`
- **Simulation States**: `omega_rr, u_mps, tire_relaxation_sigma_x`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`True`**
  - Notes: In FULLY_BLIND, undriven rear wheel speed evolves via braking torque and road friction.

## Output: `Vx`
- **Direct Measured Inputs**: `throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `grade_rad, roadWheelAngle_rad`
- **Initial Conditions**: `Vx_mps[0]`
- **Derived States**: `sum_Fx, F_drag, f_grade_gravity`
- **Simulation States**: `u_mps, v_mps, yaw_rate_rads`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`True`**
  - Notes: In SPEED_CONDITIONED mode, measured Vx_mps is directly assigned to state u_mps at every timestep (DIRECTLY FORCED).

## Output: `ax`
- **Direct Measured Inputs**: `throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `grade_rad`
- **Initial Conditions**: `None (kinematic derivative)`
- **Derived States**: `du = (sum_Fx - F_drag + f_grade)/m + r*v, ax = du - r*v`
- **Simulation States**: `u_mps, v_mps, yaw_rate_rads, omega_fl..rr`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: Measured axCG_mps2 is never injected into equations of motion.

## Output: `ay`
- **Direct Measured Inputs**: `roadWheelAngle_rad`
- **Indirect Measured Inputs**: `bank_rad`
- **Initial Conditions**: `None (kinematic derivative)`
- **Derived States**: `dv = (sum_Fy + f_bank)/m - r*u, ay = dv + r*u`
- **Simulation States**: `u_mps, v_mps, yaw_rate_rads`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: Measured ayCG_mps2 is never injected into equations of motion.

## Output: `trajectory_E`
- **Direct Measured Inputs**: `roadWheelAngle_rad, throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `bank_rad, grade_rad`
- **Initial Conditions**: `posE_m[0], yawAngle_rad[0]`
- **Derived States**: `v_e = -u*sin(psi) - v*cos(psi), pos_e += v_e * dt`
- **Simulation States**: `pos_x_m, yaw_angle_rad, u_mps, v_mps`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: posE_m is used strictly for t=0 origin; zero GPS position resets or filtering nudges during integration.

## Output: `trajectory_N`
- **Direct Measured Inputs**: `roadWheelAngle_rad, throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `bank_rad, grade_rad`
- **Initial Conditions**: `posN_m[0], yawAngle_rad[0]`
- **Derived States**: `v_n = u*cos(psi) - v*sin(psi), pos_n += v_n * dt`
- **Simulation States**: `pos_y_m, yaw_angle_rad, u_mps, v_mps`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: posN_m is used strictly for t=0 origin; zero GPS position resets or filtering nudges during integration.

## Output: `pitch`
- **Direct Measured Inputs**: `throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `grade_rad`
- **Initial Conditions**: `pitch_theta=0, pitch_rate=0`
- **Derived States**: `M_pitch_inertial = m_s * du * h_s, M_aero_pitch, F_tot_f - F_tot_r`
- **Simulation States**: `pitch_theta, pitch_rate, heave_z_s`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: Measured pitchAngle_rad from IMU is never injected; chassis pitch evolves purely from suspension load moments.

## Output: `slip_ratio`
- **Direct Measured Inputs**: `throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `grade_rad`
- **Initial Conditions**: `sigma_x=0`
- **Derived States**: `kappa_ss = (omega*Rw - vx)/max(vx, omega*Rw), relaxation dsigma_x/dt`
- **Simulation States**: `omega_fl..rr, u_mps, tire_relaxation_sigma_x`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`True`**
  - Notes: In SPEED_CONDITIONED, slip ratio calculation is conditioned on forced forward speed Vx.

## Output: `lap_position`
- **Direct Measured Inputs**: `roadWheelAngle_rad, throttleCmd_percent, brake_fl_bar`
- **Indirect Measured Inputs**: `track centerline s_m`
- **Initial Conditions**: `s_m[0]`
- **Derived States**: `ds/dt = u*cos(e_psi)/(1 - e_y*kappa)`
- **Simulation States**: `distance_m, lat_path_error_m, heading_error_rad`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: Lap distance is integrated; track position is not nudged to GPS.

## Output: `lap_time`
- **Direct Measured Inputs**: `simulation time step dt`
- **Indirect Measured Inputs**: `None`
- **Initial Conditions**: `t_s[0]`
- **Derived States**: `elapsed_time = k * dt`
- **Simulation States**: `time_s`
- **Ground Truth Injection**:
  - Fully Blind Mode: **`False`**
  - Speed-Conditioned Mode: **`False`**
  - Notes: Physical timing transponder beacons are absent from raw telemetry; lap timing is simulation elapsed time.

