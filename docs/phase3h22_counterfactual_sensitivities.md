# SuspensionLab PRO — Phase 3H.2.2 Audit Report
## Counterfactual Sensitivity Formalization

### Sensitivity Ledger on HighSpeed S-Curves:
- **CF_L (Predictive Powertrain)**: $\text{RMSE} = 4.1169\text{ m/s}$
- **CF_K (Measured Torque Replay)**: $\text{RMSE} = 2.8177\text{ m/s}$
- **Measured-Torque Replay Sensitivity**:
  $$\Delta \text{RMSE} = \text{RMSE}(\text{CF\_L}) - \text{RMSE}(\text{CF\_K}) = \mathbf{1.2992\text{ m/s}}$$
- **Aerodynamic Drag Sensitivity**:
  $$\Delta \text{RMSE} = \text{RMSE}(\text{CF\_L}) - \text{RMSE}(\text{CF\_P}) = \mathbf{2.1613\text{ m/s}}$$
- **Road Grade Gravity Sensitivity**:
  $$\Delta \text{RMSE} = \text{RMSE}(\text{CF\_L}) - \text{RMSE}(\text{CF\_Q}) = \mathbf{1.6571\text{ m/s}}$$

> [!IMPORTANT]
> *This is a counterfactual sensitivity result and is not an additive causal decomposition of total RMSE.*

**Verdict**: **`COUNTERFACTUAL_LANGUAGE_CORRECTED`**
