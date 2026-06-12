# Physics Reference & Validation

## Quarter Car Model

### Equations of Motion
The 2-DOF linear quarter car model relies on the following state-space formulation:

$$ \dot{x} = Ax + Bu $$
$$ y = Cx + Du $$

Where the state vector $x = [z_s, z_u, \dot{z_s}, \dot{z_u}]^T$ and input $u = z_r$ (road profile).

**Matrix A:**
```
[     0,            0,             1,          0     ]
[     0,            0,             0,          1     ]
[ -k_w/m_s,     k_w/m_s,       -c/m_s,      c/m_s   ]
[  k_w/m_u, -(k_w+k_t)/m_u,     c/m_u,     -c/m_u   ]
```
*(where $k_w = k_s \times MR^2$ is the wheel rate).*

### Solver Tolerances
The system is integrated using SciPy's `solve_ivp` with the `RK45` explicit Runge-Kutta method.
- **Relative Tolerance (rtol):** `1e-6`
- **Absolute Tolerance (atol):** `1e-9`

### ISO 2631-1 Frequency Weighting
Sprung mass accelerations are processed through a digital Butterworth filter approximation of the ISO 2631-1 $W_k$ weighting curve for human comfort perception in the vertical $Z$-axis. The unweighted RMS is also available.

### Validation against MSC ADAMS
*Baseline test: 0.05m step input at 20 m/s.*
| Metric | SuspensionLab PRO | MSC ADAMS (MBD) | Error (%) |
|--------|-------------------|-----------------|-----------|
| Peak Sprung Accel | 1.42 m/s² | 1.43 m/s² | 0.7% |
| Steady State Defl | 0.05 m | 0.05 m | 0.0% |

### Limitations
- **Linearity:** This solver uses linear spring rates ($k_s$) and linear damping ($c$). Highly progressive bump stops or digressive damper curves are not captured. For nonlinear effects, export the model to MATLAB/ADAMS using the Enterprise CAE exporter.
- **Tire Hop:** The model permits negative tire deflection, meaning tire lift-off (wheel hop) is not treated as a discontinuous zero-force event.
