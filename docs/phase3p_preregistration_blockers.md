# Phase 3P — Pre-Registration Lockdown Blocker Report

**Document**: `docs/phase3p_preregistration_blockers.md`  
**Status**: RESOLVED — CLOSED BY FORMAL GOVERNANCE DECISION  
**Target Mechanism**: `DynamicVehicleParams.tire_relaxation_length_y_m` ($\sigma_{y0}$)  
**Governance Resolution**: Option 1 formally ratified; candidate-generation constants frozen; manifest unblocked.

---

## 1. Executive Summary

In accordance with Phase 3P absolute governance constraints and Section F of the ratified design charter, an exhaustive audit of repository source files, test fixtures, historical manifests, and conversational artifacts was conducted to identify the authoritative numerical candidate-generation constants for $\sigma_{y0}$.

The audit detected conflicting values for the candidate-generation constants between:
1. **The production codebase and empirical reconnaissance records** ($\sigma_{y0} = 0.250\text{ m}$, bounds $[0.100, 0.500]\text{ m}$)
2. **The conversational design specification in recent discourse** ($\sigma_{y0} = 0.300\text{ m}$, bounds $[0.100, 0.800]\text{ m}$)
3. **The standalone tire model configuration in `tire_model.py`** ($\sigma_{y0} = 0.350\text{ m}$)

In accordance with the fail-closed mandate, manifest generation was halted until formal governance resolution.

---

## 2. Conflicting Constants Matrix & Resolution Status

| Parameter / Constant | Option 1 (Codebase / Reconnaissance) | Option 2 (Conversational Design) | Option 3 (Standalone Tire Class) | Final Ratified Resolution |
| :--- | :---: | :---: | :---: | :---: |
| **Baseline Value ($\sigma_{y0,\text{base}}$)** | **$0.250\text{ m}$** | $0.300\text{ m}$ | $0.350\text{ m}$ | **$0.250\text{ m}$ (RATIFIED)** |
| **Search Bounds $[\sigma_{\min}, \sigma_{\max}]$** | **$[0.100, 0.500]\text{ m}$** | $[0.100, 0.800]\text{ m}$ | N/A | **$[0.100, 0.500]\text{ m}$ (RATIFIED)** |
| **Lower Bound ($\sigma_{\min}$)** | $0.100\text{ m}$ | $0.100\text{ m}$ | N/A | **$0.100\text{ m}$ (RATIFIED)** |
| **Upper Bound ($\sigma_{\max}$)** | **$0.500\text{ m}$** | $0.800\text{ m}$ | N/A | **$0.500\text{ m}$ (RATIFIED)** |
| **Tolerance (`xatol`)** | $0.005\text{ m}$ | $0.005\text{ m}$ | N/A | **$0.005\text{ m}$ (RATIFIED)** |
| **Max Iterations (`maxiter`)** | $25$ | $25$ | N/A | **$25$ (RATIFIED)** |
| **Rounding Precision** | 3 decimal places | 3 decimal places | N/A | **3 decimal places (RATIFIED)** |

---

## 3. Exact Source Locations and Provenance

### A. Baseline $\sigma_{y0} = 0.250\text{ m}$ and Bounds $[0.100, 0.500]\text{ m}$ (Ratified)
1. **Production Solver Parameter Default**:
   - `src/suspensionlab/physics/dynamic_lap_sim.py:692`:
     ```python
     tire_relaxation_length_y_m: float = 0.25  # Lateral carcass relaxation length sigma_0,y [m]
     ```
   - `src/suspensionlab/physics/dynamic_lap_sim.py:1226`:
     ```python
     sig_y_base = getattr(p, "tire_relaxation_length_y_m", 0.25)
     ```
   - `src/suspensionlab/physics/dynamic_lap_sim.py:2340`:
     ```python
     "sigma_y_m": getattr(p, "tire_relaxation_length_y_m", 0.25),
     ```
2. **Phase 3O Canonical Setup Dictionary**:
   - `src/suspensionlab/backend/services/phase3o_case_service.py:104`:
     ```python
     "tire_relaxation_length_y_m": 0.25,
     ```
3. **Active Handling Test Fixture**:
   - `tests/test_dynamic_tire_relaxation.py:131`:
     ```python
     tire_relaxation_length_y_m=0.25,
     ```
4. **Reconnaissance Empirical Sensitivity Baseline**:
   - In reconnaissance steps 117, 199, 221, and 245, baseline simulations evaluated with $\sigma_{y0} = 0.250\text{ m}$ produced the sensitivity figures quoted in Section E of the Phase 3P ratified specification:
     - Turn 4 Entry: $\|S_\sigma\| = 0.015324$ (evaluated around $\sigma_{y0} = 0.250\text{ m}$)
     - Turn 4 Apex: $\|S_\sigma\| = 0.009494$ (evaluated around $\sigma_{y0} = 0.250\text{ m}$)
     - Turn 2 Carousel: $\|S_\sigma\| = 0.017650$ (evaluated around $\sigma_{y0} = 0.250\text{ m}$)
   - In steps 199, 221, and 245, the proposed optimization search space was explicitly specified as $\sigma_{y0} \in [0.100, 0.500]\text{ m}$.

### B. Superseded Values
- **$\sigma_{y0} = 0.300\text{ m}$ / $[0.100, 0.800]\text{ m}$**: Originated from conversational design text (step 256) and is formally superseded for pre-registration purposes.
- **$\sigma_{y0} = 0.350\text{ m}$**: Belongs to an unintegrated standalone dataclass in `tire_model.py:342` and is not authoritative for the production Phase 3P target.

---

## 4. Formal Governance Resolution

**Resolution Date**: 2026-10-04  
**Authority**: Project Engineering Governance Directive  
**Decision**: Ratify Option 1 as Authoritative

### Authoritative Specification:
- **Target Parameter**: `DynamicVehicleParams.tire_relaxation_length_y_m`
- **Baseline Value**: $0.250\text{ m}$ (`UNIDENTIFIED_NOMINAL_REFERENCE`)
- **Optimization Search Bounds**: $[0.100, 0.500]\text{ m}$
- **Optimization Method**: `scipy.optimize.minimize_scalar` (`method="bounded"`)
- **Convergence Tolerance**: `xatol = 0.005 m`
- **Maximum Evaluations / Iterations**: $25$
- **Numerical Rounding Precision**: $3$ decimal places (`round(val, 3)`)

### Authoritative Rationale:
The authoritative Phase 3P target is the integrated production parameter `DynamicVehicleParams.tire_relaxation_length_y_m`. The repository audit confirms $0.250\text{ m}$ as the production default for this parameter and confirms $[0.100, 0.500]\text{ m}$ as the bounds used during Phase 3P reconnaissance.

---

## 5. Current Lockdown State

- **`BLOCKER_STATUS`**: `RESOLVED`
- **`PHASE_3P_EXECUTED`**: `FALSE`
- **`HOLDOUTS_EVALUATED`**: `FALSE`
- **`PRODUCTION_PHYSICS_MODIFIED`**: `FALSE`
- **`PHASE_3O_REOPENED`**: `FALSE`
- **`EXECUTION_RESULTS_CREATED`**: `FALSE`
- **`MANIFEST_STATUS`**: `UNBLOCKED_FOR_GENERATION`
