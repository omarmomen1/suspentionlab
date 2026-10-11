# Phase 3H.4.2 — Sign Conventions Specification Report
**Contract**: `SIGN_CONVENTIONS_SPECIFICATION`  
**Master Framework**: `FIRST_LAW_ENERGY_CONSERVATION_FORMAT`  
**Master Equation**:
$$W_{\text{input}} = \Delta E_{\text{stored}} + E_{\text{dissipated}} + W_{\text{loss}} + E_{\text{numeric\_residual}}$$

| Variable | Classification | Unit | Physical Mechanism & Mathematical Definition |
| :--- | :---: | :---: | :--- |
| **$W_{\text{engine}}$** | `INPUT_WORK` | J | Engine crankshaft mechanical boundary work into flywheel: $\int T_{\text{after\_cut}} \omega_{\text{eng}} dt$. |
| **$W_{\text{clutch}}$** | `INTERNAL_TRANSFER` | J | Work delivered across clutch friction faces into gearbox input shafts: $\int (T_{C1} \omega_{\text{in1}} + T_{C2} \omega_{\text{in2}}) dt$. |
| **$E_{\text{clutch\_diss}}$** | `DISSIPATION` | J | Mechanical friction heat irreversibly dissipated due to dual-clutch relative slip during handover: $\int P_{\text{slip}} dt \ge 0$. |
| **$W_{\text{aero}}$** | `EXTERNAL_LOSS` | J | Aerodynamic drag retarding work: $\int F_{\text{drag}} u dt > 0$. |
| **$W_{\text{grade}}$** | `EXTERNAL_INPUT` | J | Gravitational mechanical work along road slope: $\int (-m g \sin\theta) u dt$. For downhill slope ($\theta < 0$), $W_{\text{grade}} > 0$. |
| **$E_{\text{damper}}$** | `DISSIPATION` | J | Viscous thermal dissipation in suspension dampers from chassis heave/pitch/roll: $\int \sum c_i v_{\text{def},i}^2 dt \ge 0$. |
| **$\Delta KE_{\text{trans}}$** | `STORED_ENERGY` | J | Vehicle chassis translational kinetic energy change: $\frac{1}{2} m (u_1^2 + v_1^2 - u_0^2 - v_0^2)$. |
| **$\Delta KE_{\text{rot}}$** | `STORED_ENERGY` | J | Wheel rotational kinetic energy change: $\sum \frac{1}{2} I_w (\omega_{i,1}^2 - \omega_{i,0}^2)$. |
| **$W_{\text{other}}$** | `DISSIPATION` | J | Modeled internal dissipations: drivetrain gear efficiency loss ($10\%$ of $W_{\text{clutch}}$), tire longitudinal/lateral slip, and bearing viscous loss. |
| **$E_{\text{numeric\_residual}}$** | `NUMERICAL_ERROR` | J | Finite discrete time-step quadrature integration discrepancy. |
