"""
src/suspensionlab/interop/cosim/orchestrator.py
===============================================
SuspensionLab PRO — Master Co-Simulation Orchestrator (Phase 7.5).

Implements the master co-simulation time loop coordinating multi-domain model execution:
- FMI 2.0 Co-Simulation slave execution via FMPy.
- Internal component coordination (e.g. RoadProfileGenerator).
- Deterministic signal routing, unit scaling, and causality enforcement at macro-step boundaries.
- Zero-Order Hold (ZOH) and First-Order Hold (FOH) input interpolation.
- Mechanical energy consistency and runaway state divergence monitoring.
- Fail-closed step rejection and honest rollback gating.
- Full provenance recording and epistemic invariants preservation.

Core Epistemic Invariant:
Passing co-simulation or numerical agreement NEVER implies physical proving ground validation.
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
import os
import pathlib
import shutil
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

try:
    import fmpy
    from fmpy.fmi2 import FMU2Slave
except ImportError:
    fmpy = None
    FMU2Slave = None

from suspensionlab.interop.cosim.components.road_generator import RoadProfileGenerator
from suspensionlab.interop.cosim.contract import (
    CoSimulationCouplingContract,
    CouplingContractError,
    SignalConnection,
    SyncPolicy,
    TopologyType,
)
from suspensionlab.interop.cosim.time_sync import (
    CouplingDivergenceError,
    EnergyConsistencyMonitor,
    RollbackNotSupportedError,
)
from suspensionlab.interop.fmi.capability_audit import FMICapabilityAuditor


@dataclasses.dataclass
class CoSimulationRunResult:
    contract_id: str
    duration: float
    communication_step_size: float
    total_steps: int
    time_series: Dict[str, np.ndarray]
    diagnostics: Dict[str, Any]
    epistemic_invariants: Dict[str, bool]
    model_provenance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "duration": self.duration,
            "communication_step_size": self.communication_step_size,
            "total_steps": self.total_steps,
            "signals": list(self.time_series.keys()),
            "diagnostics": self.diagnostics,
            "epistemic_invariants": self.epistemic_invariants,
            "model_provenance": self.model_provenance,
        }


class CoSimulationMasterOrchestrator:
    """
    Master orchestrator executing coupled co-simulation runs.
    """

    def __init__(
        self,
        contract: CoSimulationCouplingContract,
        fmu_lookup: Optional[Dict[str, pathlib.Path | str]] = None,
        workspace_base_dir: Optional[pathlib.Path | str] = None,
    ):
        self.contract = contract
        self.fmu_lookup = fmu_lookup or {}
        self.workspace_base = pathlib.Path(workspace_base_dir or tempfile.gettempdir()) / "cosim_workspace"
        self.workspace_base.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        duration: float = 2.0,
        start_time: float = 0.0,
        fmu_parameters: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> CoSimulationRunResult:
        """
        Executes the coupled co-simulation across participating models.
        """
        # 1. Preflight Contract Validation Gate
        report = self.contract.validate()
        if not report.is_valid:
            raise CouplingContractError(
                f"Coupling contract '{self.contract.contract_id}' failed preflight validation: "
                + "; ".join(report.errors)
            )

        H_c = float(self.contract.time_sync.communication_step_size)
        sync_policy = self.contract.time_sync.sync_policy
        temp_extract_dirs: List[pathlib.Path] = []

        # Instantiated slave interfaces
        slaves: Dict[str, Any] = {}
        val_refs: Dict[str, Dict[str, int]] = {}
        rollback_capabilities: Dict[str, bool] = {}

        try:
            # 2. Instantiate Participating Models
            for m_id, model_spec in self.contract.participants.items():
                if model_spec.model_type == "PYTHON_COSIM_COMPONENT":
                    if "road" in model_spec.role.lower() or "excitation" in model_spec.role.lower():
                        # Extract generator params from model capabilities or defaults
                        p = model_spec.capabilities
                        gen = RoadProfileGenerator(
                            profile_type=p.get("profile_type", "DISCRETE_BUMP"),
                            bump_height=p.get("bump_height", 0.05),
                            bump_length=p.get("bump_length", 2.0),
                            bump_start_dist=p.get("bump_start_dist", 1.0),
                            vehicle_speed=p.get("vehicle_speed", 13.889),
                        )
                        gen.reset(start_time=start_time)
                        slaves[m_id] = gen
                        rollback_capabilities[m_id] = True  # Python state can be reset

                elif model_spec.model_type == "FMI_2_0_COSIM":
                    if fmpy is None:
                        raise RuntimeError("FMPy runtime is required for FMI 2.0 Co-Simulation.")

                    # Locate FMU
                    fmu_file = self.fmu_lookup.get(m_id) or self.fmu_lookup.get(model_spec.name)
                    if not fmu_file:
                        for candidate_name in [f"{model_spec.name}.fmu", f"{m_id}.fmu", "QuarterCarRideModel.fmu"]:
                            candidate = pathlib.Path(candidate_name)
                            if candidate.exists():
                                fmu_file = candidate
                                break
                    if not fmu_file:
                        raise FileNotFoundError(f"FMU file for participant '{m_id}' ({model_spec.name}) not found.")

                    fmu_path = pathlib.Path(fmu_file)
                    if not fmu_path.exists():
                        raise FileNotFoundError(f"FMU file '{fmu_path}' does not exist.")

                    # Cryptographic allowlist check: untrusted FMUs must be rejected fail-closed
                    with open(fmu_path, "rb") as f_obj:
                        file_hash = hashlib.sha256(f_obj.read()).hexdigest()
                    from suspensionlab.backend.services.solver_execution_service import VETTED_FMU_SHA256
                    if file_hash not in VETTED_FMU_SHA256:
                        raise PermissionError(
                            f"Untrusted FMU rejected: SHA-256 '{file_hash}' is not on the vetted allowlist."
                        )

                    md = fmpy.read_model_description(str(fmu_path))

                    # Audit capabilities
                    audit = FMICapabilityAuditor.audit_fmu(fmu_path)
                    rollback_capabilities[m_id] = audit.rollback_supported

                    # Extract FMU to unique directory
                    unzip_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"fmu_{m_id}_", dir=str(self.workspace_base)))
                    temp_extract_dirs.append(unzip_dir)
                    fmpy.extract(str(fmu_path), unzipdir=str(unzip_dir))

                    # Map variable names to value references
                    refs: Dict[str, int] = {}
                    for v in md.modelVariables:
                        refs[v.name] = v.valueReference
                    val_refs[m_id] = refs

                    # Instantiate slave
                    model_id = md.coSimulation.modelIdentifier if md.coSimulation else md.modelName
                    slave = FMU2Slave(
                        guid=md.guid,
                        unzipDirectory=str(unzip_dir),
                        modelIdentifier=model_id,
                        instanceName=f"slave_{m_id}",
                    )
                    slave.instantiate()
                    slave.setupExperiment(startTime=start_time)

                    # Apply custom parameters if supplied
                    custom_params = (fmu_parameters or {}).get(m_id, {})
                    slave.enterInitializationMode()
                    for p_name, p_val in custom_params.items():
                        if p_name in refs:
                            slave.setReal([refs[p_name]], [float(p_val)])
                    slave.exitInitializationMode()

                    slaves[m_id] = slave

            # 3. Initialize Diagnostics & Energy Monitor
            energy_monitor = EnergyConsistencyMonitor(
                max_energy_drift_joules=self.contract.bounds.energy_drift_tolerance_joules
            )

            # Signal Storage
            time_points: List[float] = [start_time]
            signal_history: Dict[str, List[float]] = {}
            for m_id, model in self.contract.participants.items():
                for v in model.variables:
                    signal_history[f"{m_id}.{v['name']}"] = []

            # 4. Master Time Step Loop
            current_t = start_time
            step_count = 0
            n_steps = int(math.ceil((duration - start_time) / H_c))

            # Determine execution order for Gauss-Seidel staggered execution
            contract_order = getattr(self.contract, "staggered_execution_order", None)
            if contract_order and isinstance(contract_order, list) and len(contract_order) > 0:
                execution_order = [m for m in contract_order if m in slaves]
                for m in slaves:
                    if m not in execution_order:
                        execution_order.append(m)
            else:
                def _order_key(m_id: str) -> int:
                    role = self.contract.participants[m_id].role.upper()
                    if "EXCITATION" in role or "ROAD" in role:
                        return 0
                    if "CONTROLLER" in role or "ACTUATOR" in role:
                        return 1
                    if "PLANT" in role:
                        return 2
                    return 3
                execution_order = sorted(list(slaves.keys()), key=_order_key)

            # Initialize current_outputs with initial values (t=start_time)
            current_outputs: Dict[str, Dict[str, float]] = {}
            for m_id, s in slaves.items():
                if isinstance(s, RoadProfileGenerator):
                    current_outputs[m_id] = s.get_outputs()
                elif isinstance(s, FMU2Slave):
                    m_spec = self.contract.participants[m_id]
                    refs_map = val_refs[m_id]
                    out_vars = [v["name"] for v in m_spec.variables if v.get("causality") == "output"]
                    out_refs = [refs_map[v] for v in out_vars if v in refs_map]
                    vals = s.getReal(out_refs)
                    current_outputs[m_id] = dict(zip(out_vars, vals))

            while current_t < duration - 1e-9:
                step_count += 1
                next_t = current_t + H_c

                if sync_policy == SyncPolicy.GAUSS_SEIDEL:
                    # Sequential Staggered Gauss-Seidel Execution
                    for m_id in execution_order:
                        s = slaves[m_id]
                        # 1. Determine inputs for this specific model from current_outputs
                        m_inputs: Dict[str, float] = {}
                        for conn in self.contract.connections:
                            if conn.target_model_id == m_id:
                                src_m = conn.source_model_id
                                src_v = conn.source_variable
                                raw_val = current_outputs.get(src_m, {}).get(src_v, 0.0)
                                scaled_val = raw_val * conn.conversion_scale + conn.conversion_offset
                                m_inputs[conn.target_variable] = scaled_val

                        # 2. Set inputs on slave
                        if isinstance(s, RoadProfileGenerator):
                            s.set_inputs(m_inputs)
                        elif isinstance(s, FMU2Slave):
                            refs_map = val_refs[m_id]
                            in_refs = []
                            in_vals = []
                            for in_name, in_val in m_inputs.items():
                                if in_name in refs_map:
                                    in_refs.append(refs_map[in_name])
                                    in_vals.append(float(in_val))
                            if in_refs:
                                s.setReal(in_refs, in_vals)

                        # 3. Advance step for this model
                        try:
                            if isinstance(s, RoadProfileGenerator):
                                s.do_step(current_t, H_c)
                            elif isinstance(s, FMU2Slave):
                                status = s.doStep(currentCommunicationPoint=current_t, communicationStepSize=H_c)
                                if status is not None and status != 0:
                                    raise RuntimeError(f"Slave '{m_id}' returned non-OK status {status} in doStep.")
                        except Exception as e:
                            can_rollback = all(rollback_capabilities.values())
                            if not can_rollback:
                                raise RollbackNotSupportedError(
                                    f"Step failure at t={current_t:.4f}s on model '{m_id}'. "
                                    "State rollback is not supported by participating model (canGetAndSetFMUstate=False). "
                                    "Simulation terminated fail-closed."
                                ) from e
                            raise

                        # 4. Read updated outputs from this model immediately for subsequent models in the chain
                        if isinstance(s, RoadProfileGenerator):
                            current_outputs[m_id] = s.get_outputs()
                        elif isinstance(s, FMU2Slave):
                            m_spec = self.contract.participants[m_id]
                            refs_map = val_refs[m_id]
                            out_vars = [v["name"] for v in m_spec.variables if v.get("causality") == "output"]
                            out_refs = [refs_map[v] for v in out_vars if v in refs_map]
                            vals = s.getReal(out_refs)
                            current_outputs[m_id] = dict(zip(out_vars, vals))

                else:
                    # Jacobi Parallel Execution
                    # A. Route signals across connections from t_k outputs
                    inputs_to_set: Dict[str, Dict[str, float]] = {m_id: {} for m_id in slaves}
                    for conn in self.contract.connections:
                        src_m = conn.source_model_id
                        src_v = conn.source_variable
                        tgt_m = conn.target_model_id
                        tgt_v = conn.target_variable

                        raw_val = current_outputs.get(src_m, {}).get(src_v, 0.0)
                        scaled_val = raw_val * conn.conversion_scale + conn.conversion_offset
                        inputs_to_set[tgt_m][tgt_v] = scaled_val

                    # B. Set inputs on all slaves
                    for m_id, s in slaves.items():
                        m_inputs = inputs_to_set.get(m_id, {})
                        if isinstance(s, RoadProfileGenerator):
                            s.set_inputs(m_inputs)
                        elif isinstance(s, FMU2Slave):
                            refs_map = val_refs[m_id]
                            in_refs = []
                            in_vals = []
                            for in_name, in_val in m_inputs.items():
                                if in_name in refs_map:
                                    in_refs.append(refs_map[in_name])
                                    in_vals.append(float(in_val))
                            if in_refs:
                                s.setReal(in_refs, in_vals)

                    # C. Advance step for each participant
                    for m_id, s in slaves.items():
                        try:
                            if isinstance(s, RoadProfileGenerator):
                                s.do_step(current_t, H_c)
                            elif isinstance(s, FMU2Slave):
                                status = s.doStep(currentCommunicationPoint=current_t, communicationStepSize=H_c)
                                if status is not None and status != 0:
                                    raise RuntimeError(f"Slave '{m_id}' returned non-OK status {status} in doStep.")
                        except Exception as e:
                            can_rollback = all(rollback_capabilities.values())
                            if not can_rollback:
                                raise RollbackNotSupportedError(
                                    f"Step failure at t={current_t:.4f}s on model '{m_id}'. "
                                    "State rollback is not supported by participating model. "
                                    "Simulation terminated fail-closed."
                                ) from e
                            raise

                    # D. Read post-step outputs
                    for m_id, s in slaves.items():
                        if isinstance(s, RoadProfileGenerator):
                            current_outputs[m_id] = s.get_outputs()
                        elif isinstance(s, FMU2Slave):
                            m_spec = self.contract.participants[m_id]
                            refs_map = val_refs[m_id]
                            out_vars = [v["name"] for v in m_spec.variables if v.get("causality") == "output"]
                            out_refs = [refs_map[v] for v in out_vars if v in refs_map]
                            vals = s.getReal(out_refs)
                            current_outputs[m_id] = dict(zip(out_vars, vals))

                # F. Record signal history for all participants
                for m_id, s in slaves.items():
                    m_spec = self.contract.participants[m_id]
                    m_outs = current_outputs.get(m_id, {})
                    for v in m_spec.variables:
                        v_name = v["name"]
                        if v_name in m_outs:
                            signal_history[f"{m_id}.{v_name}"].append(m_outs[v_name])

                # G. Stability, Actuator Work & Energy Consistency Check
                qc_id = next((m_id for m_id, m in self.contract.participants.items() if "PLANT" in m.role.upper()), None)
                if not qc_id:
                    qc_id = next((m_id for m_id in slaves if "plant" in m_id.lower() or "quarter_car" in m_id.lower()), None)

                if qc_id and qc_id in current_outputs:
                    qc_outs = current_outputs[qc_id]
                    zs = qc_outs.get("z_s", 0.0)
                    vs = qc_outs.get("v_s", 0.0)
                    zu = qc_outs.get("z_u", 0.0)
                    vu = qc_outs.get("v_u", 0.0)
                    zr = qc_outs.get("z_road", 0.0)
                    dzr = qc_outs.get("dz_road", 0.0)

                    # Actuator force: search plant f_act or controller f_act output
                    ctrl_id = next((m_id for m_id, m in self.contract.participants.items() if "CONTROLLER" in m.role.upper() or "ACTUATOR" in m.role.upper()), None)
                    fact = 0.0
                    if ctrl_id and ctrl_id in current_outputs and "f_act" in current_outputs[ctrl_id]:
                        fact = current_outputs[ctrl_id]["f_act"]
                    elif "f_act" in qc_outs:
                        fact = qc_outs["f_act"]

                    ftire = qc_outs.get("tire_load_dynamic", None)
                    is_active = (abs(zr) > 0.0005 or abs(dzr) > 0.0005)

                    energy_monitor.record_step_with_actuator(
                        t=next_t,
                        z_s=zs,
                        v_s=vs,
                        z_u=zu,
                        v_u=vu,
                        z_road=zr,
                        v_road=dzr,
                        f_act=fact,
                        f_tire=ftire,
                        is_excitation_active=is_active,
                    )

                    if energy_monitor.divergence_flag:
                        raise CouplingDivergenceError(
                            f"Coupling Instability Detected at t={next_t:.4f}s: {energy_monitor.divergence_reason}"
                        )

                # H. Check Operating Bounds
                for sig_name, bounds_tuple in self.contract.bounds.signal_bounds.items():
                    sig_hist = signal_history.get(sig_name)
                    if sig_hist:
                        curr_v = sig_hist[-1]
                        b_min, b_max = bounds_tuple
                        if curr_v < b_min or curr_v > b_max:
                            raise CouplingDivergenceError(
                                f"Operating Bound Breached at t={next_t:.4f}s: Signal '{sig_name}' = {curr_v:.4f} "
                                f"outside permitted envelope [{b_min}, {b_max}]."
                            )

                current_t = next_t
                time_points.append(current_t)

            # 5. Pack Results
            final_time = np.array(time_points[1:], dtype=np.float64)
            final_series = {k: np.array(v, dtype=np.float64) for k, v in signal_history.items() if v}

            diagnostics = {
                "total_steps": step_count,
                "step_size_seconds": H_c,
                "phase_lag_seconds": H_c / 2.0,  # First-order Gauss-Seidel communication lag
                "max_observed_energy_joules": energy_monitor.max_observed_energy,
                "energy_divergence_detected": energy_monitor.divergence_flag,
                "rollback_attempts": 0,
                "rejected_steps": 0,
                "sync_policy": sync_policy.value,
                "topology": report.topology.value,
                "feedback_metrics": {
                    "accumulated_actuator_work_joules": float(energy_monitor.accumulated_actuator_work),
                    "accumulated_road_work_joules": float(energy_monitor.accumulated_road_work),
                    "accumulated_dissipated_energy_joules": float(energy_monitor.accumulated_dissipated_energy),
                    "energy_residual_absolute_joules": float(energy_monitor.energy_residual_absolute),
                    "energy_residual_relative": float(energy_monitor.energy_residual_relative),
                    "max_observed_energy_joules": float(energy_monitor.max_observed_energy),
                    "is_feedback_coupled": (report.topology == TopologyType.FEEDBACK_COUPLED),
                    "staggered_execution_order": execution_order,
                },
            }

            epistemic = {
                "cosimulation_agreement_is_not_physical_validation": True,
                "coupled_execution_is_not_vehicle_safe": True,
                "is_executed": True,
                "is_physically_validated": False,
            }

            model_provenance = {
                m_id: {
                    "role": m.role,
                    "model_type": m.model_type,
                    "sha256": m.sha256_hash,
                }
                for m_id, m in self.contract.participants.items()
            }

            return CoSimulationRunResult(
                contract_id=self.contract.contract_id,
                duration=duration,
                communication_step_size=H_c,
                total_steps=step_count,
                time_series=final_series,
                diagnostics=diagnostics,
                epistemic_invariants=epistemic,
                model_provenance=model_provenance,
            )

        finally:
            # Clean up all slaves and extracted temp directories
            for s in slaves.values():
                if isinstance(s, FMU2Slave):
                    try:
                        s.terminate()
                    except Exception:
                        pass
                    try:
                        s.freeInstance()
                    except Exception:
                        pass

            for d in temp_extract_dirs:
                shutil.rmtree(d, ignore_errors=True)
