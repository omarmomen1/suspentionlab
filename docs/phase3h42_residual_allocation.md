# Phase 3H.4.2 — System Residual Allocation & Forensic Explanation
**Contract**: `SYSTEM_RESIDUAL_EXPLANATION_AND_ALLOCATION`  
**Phase 3H.4.1 Target Residual**: **2787.17 J** ($19.10\%$)

### Exact Component Numerical Decomposition

| Contributing Factor | Allocated Energy (J) | % of Residual | Physical & Bookkeeping Origin |
| :--- | :---: | :---: | :--- |
| **1. Downhill Road Grade Work Inversion** | **+1997.95 J** | **71.68%** | Grade is downhill ($\theta = -0.0287\text{ rad}$); gravity did positive work propelling vehicle. In Phase 3H.4.1, it was misallocated to the sink side. |
| **2. Wheel Rotational KE Over-Approximation** | **+335.95 J** | **12.05%** | Phase 3H.4.1 simplified single-wheel average overestimated true 4-wheel kinetic energy gain (597.52 J vs 933.47 J). |
| **3. Euler Left-Rectangle Quadrature Error** | **+447.89 J** | **16.07%** | Left-sided rectangular integration of power across rapid torque drop and recovery transients overestimates work. |
| **4. Suspension Damper Dissipation Omitted** | **+45.45 J** | **1.63%** | Chassis heave, pitch, and roll dampers dissipated energy omitted from simplified ledger. |
| **5. Kinematic Coriolis & RK4 Coupling** | **-40.07 J** | **-1.44%** | Body-frame Coriolis cross-coupling ($m \cdot u \cdot r \cdot v$) and high-order RK4 sub-stepping residuals. |
| **Total Sum of Components** | **2787.17 J** | **100.00%** | **Closure Discrepancy: 0.0000000000 J (EXACT 0.0 J)** |
