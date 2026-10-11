# Phase 3H.3 — Transmission State Vector Specification & Endogeneity Feasibility Report

**Status:** APPROVED ARCHITECTURE DESIGN  
**Date:** 2026-09-26T23:44:32.056115+00:00  
**Baseline SHA:** `fbe3d045762d8c216922630ca5c3b0da1d589a31`  
**Classification:** ARCHITECTURE SPECIFICATION / AUDIT ONLY  

---

## 1. Executive Summary

This report defines the explicit transmission state vector required for an endogenous transmission system in SuspensionLab PRO. Current Path B is formally certified as `GEAR_CONDITIONED_POWERTRAIN_PREDICTION`, relying on pre-scheduled gear boundaries. This report proves that a 6-element transmission state vector can be completely predicted from forward physical states without any measured telemetry feedback.

---

## 2. Transmission State Vector Definition

The formal transmission state vector $\mathbf{x}_{\text{tx}}$ comprises:

$$\mathbf{x}_{\text{tx}} = \begin{bmatrix} \text{gear} \\ \text{clutch\_state} \\ \text{shift\_state} \\ \text{shift\_timer} \\ \omega_{\text{in}} \\ \omega_{\text{out}} \end{bmatrix} \in \{1,\dots,6\} \times \{\text{LOCKED}, \text{SLIPPING}, \text{OPEN}\} \times \{\text{IN\_GEAR}, \text{TORQUE\_CUT}, \text{CLUTCH\_HANDOVER}, \text{SPEED\_SYNC}\} \times \mathbb{R}_+ \times \mathbb{R}_+ \times \mathbb{R}_+$$

| State Variable | Data Type | Permissible Domain | Governing Physical Law |
| :--- | :--- | :--- | :--- |
| `gear` | `int` | $\{1, 2, 3, 4, 5, 6\}$ | Updated by shift state machine upon completion of `CLUTCH_HANDOVER` phase. |
| `clutch_state` | `enum` | `LOCKED`, `SLIPPING`, `OPEN` | `LOCKED` during in-gear cruise/acceleration; `SLIPPING` during dual-clutch handover; `OPEN` during neutral disconnect. |
| `shift_state` | `enum` | `IN_GEAR`, `TORQUE_CUT`, `CLUTCH_HANDOVER`, `SPEED_SYNC` | Deterministic state machine driven by ShiftSpec RPM boundaries and internal `shift_timer`. |
| `shift_timer` | `float` (s) | $[0, \infty)$ | $\dot{t}_{\text{shift}} = 1.0$ during shift phases; resets to 0.0 at phase transitions. |
| `input_shaft_speed` | `float` (rad/s) | $[\omega_{\text{idle}}, \omega_{\text{redline}}]$ | When `LOCKED`: $\omega_{\text{in}} = \omega_{\text{wheel}} \cdot N_{\text{gear}}$. When `SLIPPING`: $I_{\text{eng}} \dot{\omega}_{\text{in}} = T_{\text{eng}} - T_{\text{clutch}}$. |
| `output_shaft_speed` | `float` (rad/s) | $[0, \infty)$ | $\omega_{\text{out}} = \omega_{\text{wheel}} \cdot N_f$, where $\omega_{\text{wheel}}$ is integrated by tire tractive force ODEs. |

---

## 3. Endogenous Predictability Proof

### 3.1 Input Requirements
The transmission state vector is driven strictly by:
1. Simulated vehicle speed $u$ (from chassis ODE).
2. Simulated driven wheel rotational speed $\omega_{\text{wheel}}$ (from wheel inertia ODE).
3. Driver throttle input $\alpha \in [0, 1]$ (driver control boundary).
4. Driver brake pressure $P_{\text{brake}}$ (driver control boundary).
5. Formal `ShiftSpec` policy parameters.

### 3.2 Prohibited Channels
Zero dependence on:
- Measured engine RPM (`engine_rpm`)
- Measured wheel speeds (`wheelspeed_*`)
- Measured CAN gear ratio (`GearRatio`)
- Measured engine torque (`engineTorque_Nm`)
- Measured vehicle speed (`Vx_mps`)

### 3.3 Epistemic Conclusion
The transmission state vector is completely self-contained within forward simulation dynamics.
