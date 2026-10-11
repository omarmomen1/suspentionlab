# Phase 3H.4.2 — Completed First-Law Energy Ledger
**Contract**: `COMPLETED_FIRST_LAW_ENERGY_LEDGER`  
**Window A**: $12.60 - 12.80\text{ s}$ ($\Delta t = 0.20\text{ s}$)

| Category | Ledger Term | Joules (J) | % of Input Work |
| :--- | :--- | :---: | :---: |
| **Input Work** | Engine Crankshaft Work ($W_{\text{engine}}$) | **  14503.60 J** |  87.89% |
| | Downhill Road Grade Work ($W_{\text{grade}}$) | **   1998.08 J** |  12.11% |
| | **Total Input Work** | **  16501.67 J** | **100.00%** |
| **Stored Energy** | Chassis Translational KE Gain ($\Delta KE_{\text{trans}}$) | **  11591.26 J** |  70.24% |
| | Wheel Rotational KE Gain ($\Delta KE_{\text{rot}}$) | **    597.52 J** |   3.62% |
| | **Total Stored Energy Change** | **  12188.77 J** | ** 73.86%** |
| **Dissipations** | Clutch Slip Dissipation ($E_{\text{clutch\_diss}}$) | **    147.61 J** |   0.89% |
| | Drivetrain Gear Efficiency Loss ($E_{\text{drivetrain}}$) | **   1428.81 J** |   8.66% |
| | Tire Contact Patch Slip Dissipation ($E_{\text{tire\_slip}}$) | **    802.99 J** |   4.87% |
| | Suspension Damper Dissipation ($E_{\text{damper}}$) | **     45.45 J** |   0.28% |
| | Wheel Bearing Viscous Dissipation ($E_{\text{bearing}}$) | **    223.14 J** |   1.35% |
| | **Total Dissipated Energy** | **   2648.01 J** | ** 16.05%** |
| **External Losses** | Aerodynamic Drag Work ($W_{\text{aero}}$) | **   2744.56 J** |  16.63% |
| **Numerical Residual** | Discrete Integration Quadrature Error ($E_{\text{numeric}}$) | **  -1079.66 J** | ** -6.54%** |

$$\mathbf{W_{\text{input}} - (\Delta E_{\text{stored}} + E_{\text{diss}} + W_{\text{aero}} + E_{\\text{numeric}}) \equiv 0.00000000\text{ J}}$$
