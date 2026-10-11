# SuspensionLab PRO — Phase 3H.2.1 Audit Report
## Engine-Speed Causal Trace & Anti-Leakage DAG

### Epistemic Status of Engine Speed in Path B:
- **Classification**: `ALGEBRAICALLY_RECONSTRUCTED_KINEMATIC_STATE`
- **Causal Derivation**:
  $$\\omega_{\\text{drive}} = \\frac{1}{2}(\\omega_{\\text{fl}} + \\omega_{\\text{fr}})$$
  $$\\text{RPM}_{\\text{engine}} = \\max\\left(\\text{RPM}_{\\text{idle}}, \\omega_{\\text{drive}} \\cdot N_{\\text{total}} \\cdot \\frac{60}{2\\pi}\\right)$$
- It is **not** a free differential integrator state.
- It is **not** fed back from measured engine RPM.
- It is **not** fed back from measured wheel speeds.

### Numerical Zero-Leakage Gate:
$$\\frac{\\partial T_{\\text{pred}}}{\\partial \\text{MeasRPM}} = 0.00000000$$
$$\\frac{\\partial T_{\\text{pred}}}{\\partial \\text{MeasTorque}} = 0.00000000$$
$$\\frac{\\partial \\dot{u}}{\\partial \\text{MeasRPM}} = 0.00000000$$

### Healthy Physical Coupling:
$$\\frac{\\partial T_{\\text{pred}}}{\\partial \\omega_{\\text{wheel, sim}}} = 0.2268 > 0$$

**Verdict**: **`DAG_INDEPENDENCE_CONFIRMED`**
