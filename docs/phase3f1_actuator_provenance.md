# SuspensionLab PRO — Phase 3F.1 Actuator Provenance & Terminology Audit
**Evaluation Timestamp:** 2026-09-26 02:25:36 UTC  
**Audit Objective:** Classify four-corner brake inputs and eliminate terminology ambiguities between actuator replay and autonomous prediction.

---

## 1. Physical Signal Trace & Channel Classification

The signal transmission chain implemented in Phase 3F operates as follows:

$$\begin{matrix}
\text{Telemetry Log: } P_{FL}, P_{FR}, P_{RL}, P_{RR} \\
\downarrow \\
\text{Corner Demands: } d_i = \operatorname{BrakeMap}(P_i) \\
\downarrow \\
\text{Corner Torques: } T_{brk, i} = d_i \times T_{max, i} \\
\downarrow \\
\text{Wheel Dynamics: } I_w \dot{\omega}_i = T_{drive, i} - T_{brk, i}\operatorname{sgn}(\omega_i) - R_w F_{x, i} - b \omega_i \\
\downarrow \\
\text{Tire Forces: } F_{x, i} = \operatorname{Pacejka}(\kappa_i, \alpha_i, F_{z, i}) \\
\downarrow \\
\text{Chassis Acceleration: } m a_x = \sum F_{x, i} - F_{drag} - m g \sin(\theta_{grade})
\end{matrix}$$

### Authoritative Scientific Determination:
> **"The simulation replays measured corner brake actuation."**

These pressure channels are **Boundary Actuator Inputs** measured by physical pressure transducers on the Stanford Volkswagen Golf VII GTI.
- The simulator **DOES NOT** contain an active Bosch ABS/ESC/EBD electronic control unit.
- The simulator **DOES NOT** autonomously predict the corner pressure split ($45.2\text{ bar}$ outside front vs $14.3\text{ bar}$ inside front).
- Therefore, Phase 3F represents an **`ACTUATOR-REPLAY VALIDATION`**, **NOT** a brake-distribution prediction.

---

## 2. Decoupled Taxonomy: State-Feedback vs Actuator-Replay

To ensure total scientific transparency and prevent semantic confusion, validation modes must be reported along two orthogonal axes:

| Dimension | Mode | Definition | Status in Phase 3F |
| :--- | :--- | :--- | :---: |
| **State Feedback** | `FULLY_BLIND` | Open-loop integration: zero vehicle states ($V_x, V_y, r, \psi, \text{pos}, \omega$) are fed back. | **ACTIVE** |
| | `SPEED_CONDITIONED` | $V_x$ is clamped to ground-truth telemetry at each integration step. | Evaluated for comparison |
| **Actuator Input** | `ACTUATOR_REPLAY` | Measured driver and chassis actuator signals ($P_{fl}, P_{fr}, P_{rl}, P_{rr}, \delta, \text{thr}$) are replayed. | **ACTIVE** |
| | `AUTONOMOUS_PREDICTION` | ESC/EBD/ABS control algorithms predict line pressure distribution endogenously. | **NOT IMPLEMENTED** |

**Conclusion:** The claim of "Fully Blind" validation is valid **strictly regarding state feedback** (no state drift correction), but the simulation operates under **measured actuator replay**.
