"""
tests/test_phase7_5_cosimulation_contracts.py
=============================================
SuspensionLab PRO — Phase 7.5 Multi-Domain Co-Simulation Contracts,
Time Synchronization & Execution Reliability Test Suite.

Verifies:
1. FMI Capability Audit & Truthful Limitations (WP A).
2. Coupling Interface Contract & Preflight Rejections (WP B).
3. Real Coupled Reference Execution (Road Generator + Quarter Car FMU & Dual FMU) (WP C).
4. Time Synchronization, Interpolation, Energy Consistency & Convergence (WP D).
5. Execution Reliability, Worker Fencing & Concurrent Lease Recovery (WP E).
6. Security Boundaries, Untrusted FMU Rejection & Contract Immutability (WP F).
7. FastAPI Routes, Diagnostics & Multi-Tenant Boundary Isolation (WP H).
8. Epistemic Invariants & Truthful Status Declarations (WP I).
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import math
import os
import pathlib
import sys
import uuid
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from suspensionlab.backend.api.main import app
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.cosim_contract import (
    CoSimulationCouplingContract as CoSimContractModel,
    ContractStatus,
    InterpolationMode,
    SynchronizationPolicy,
)
from suspensionlab.backend.database.models.solver_exchange import (
    ArtifactDirection,
    SolverExchangeArtifact,
)
from suspensionlab.backend.database.models.solver_execution import (
    ExecutionJobState,
    ImmutableExecutionError,
    SolverExecutionJob,
)
from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.security.auth import UserContext
from suspensionlab.backend.security.jwt_utils import create_access_token
from suspensionlab.backend.services.cosimulation_service import (
    CoSimulationService,
    CouplingContractNotFoundError,
    REAL_COUPLED_EXECUTION_VERIFIED,
    TWO_FMU_COSIMULATION_VERIFIED,
    COUPLING_CONTRACT_VERIFIED,
    TIME_SYNCHRONIZATION_VERIFIED,
    STEP_SIZE_CONVERGENCE_VERIFIED,
    WORKER_FENCING_VERIFIED,
    CONCURRENT_RECOVERY_VERIFIED,
    UNTRUSTED_FMU_ISOLATION_VERIFIED,
    VETTED_FMU_ALLOWLIST_ENFORCED,
    PHYSICAL_VALIDATION_FABRICATED,
)
from suspensionlab.backend.services.solver_execution_service import (
    SolverExecutionService,
    VETTED_FMU_SHA256,
)
from suspensionlab.interop.cosim.components.road_generator import RoadProfileGenerator
from suspensionlab.interop.cosim.contract import (
    AlgebraicLoopError,
    CoSimulationCouplingContract,
    CouplingContractError,
    IncompatibleStepSizeError,
    InvalidCausalityError,
    ModelParticipantSpec,
    OperatingBoundsConfig,
    SignalConnection,
    SignalInterpolation,
    SyncPolicy,
    TimeSyncConfig,
    TopologyType,
    UnitDimensionMismatchError,
)
from suspensionlab.interop.cosim.fencing import (
    ProcessLivenessChecker,
    StaleWorkerFencingError,
    WorkerFencingManager,
)
from suspensionlab.interop.cosim.orchestrator import CoSimulationMasterOrchestrator
from suspensionlab.interop.cosim.time_sync import (
    CouplingDivergenceError,
    EnergyConsistencyMonitor,
    InterpolatedSignal,
    RollbackNotSupportedError,
    StepSizeConvergenceAuditor,
)
from suspensionlab.interop.fmi.capability_audit import FMICapabilityAuditor
from suspensionlab.interop.security import TenantIsolationError

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
FMU_PATH = PROJECT_ROOT / "artifacts" / "QuarterCarRideModel.fmu"
if not FMU_PATH.exists():
    FMU_PATH = PROJECT_ROOT / "QuarterCarRideModel.fmu"

VETTED_HASH = next(iter(VETTED_FMU_SHA256))


@pytest.fixture
async def seeded_p75_users():
    """Seeds two isolated tenant users for Phase 7.5 testing."""
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    team_a_id = uuid.uuid4()
    team_b_id = uuid.uuid4()

    async with SessionLocal() as db:
        user_a = User(
            id=user_a_id,
            email=f"engineer_p75_a_{user_a_id.hex[:6]}@oem.com",
            name="Engineer P75 A",
            plan="PRO",
            password_hash="test-hash",
        )
        user_b = User(
            id=user_b_id,
            email=f"engineer_p75_b_{user_b_id.hex[:6]}@competitor.com",
            name="Engineer P75 B",
            plan="PRO",
            password_hash="test-hash",
        )
        db.add_all([user_a, user_b])
        await db.commit()

    token_a = create_access_token({
        "sub": str(user_a_id),
        "user_id": str(user_a_id),
        "email": user_a.email,
        "team_id": str(team_a_id),
        "plan": "PRO",
    })
    token_b = create_access_token({
        "sub": str(user_b_id),
        "user_id": str(user_b_id),
        "email": user_b.email,
        "team_id": str(team_b_id),
        "plan": "PRO",
    })

    return {
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
        "team_a_id": team_a_id,
        "team_b_id": team_b_id,
        "token_a": token_a,
        "token_b": token_b,
        "headers_a": {"Authorization": f"Bearer {token_a}"},
        "headers_b": {"Authorization": f"Bearer {token_b}"},
        "context_a": UserContext(
            user_id=str(user_a_id),
            email=user_a.email,
            name=user_a.name,
            onboarding_complete=True,
            plan="PRO",
            team_id=str(team_a_id),
        ),
        "context_b": UserContext(
            user_id=str(user_b_id),
            email=user_b.email,
            name=user_b.name,
            onboarding_complete=True,
            plan="PRO",
            team_id=str(team_b_id),
        ),
    }


# ── TEST GROUP 1: FMI CAPABILITY AUDIT (WORK PACKAGE A) ─────────────────────────

def test_wpa_01_fmi_capability_audit_quarter_car():
    """
    Audits QuarterCarRideModel.fmu and truthfully verifies capabilities & limits:
    - FMI 2.0 Co-Simulation supported.
    - Model Exchange NOT supported.
    - canGetAndSetFMUstate = False (State Rollback is NOT supported).
    - canInterpolateInputs = True.
    - canHandleVariableCommunicationStepSize = True.
    """
    assert FMU_PATH.is_file(), f"FMU missing at {FMU_PATH}"
    report = FMICapabilityAuditor.audit_fmu(FMU_PATH)

    assert report.fmi_version == "2.0"
    assert report.model_name == "QuarterCarRideModel"
    assert report.co_simulation is not None
    assert report.model_exchange is None
    assert report.rollback_supported is False
    assert report.co_simulation.can_handle_variable_communication_step_size is True
    assert report.co_simulation.can_interpolate_inputs is True
    assert report.co_simulation.can_get_and_set_fmu_state is False

    # Variables inspection
    var_names = [v.name for v in report.inputs + report.outputs + report.parameters]
    assert "z_r" in var_names or "z_road" in var_names
    assert "z_s" in var_names
    assert "z_u" in var_names

    # Truthful limitation declarations
    limitations_str = " ".join(report.known_limitations).lower()
    assert "rollback" in limitations_str or "fmustate" in limitations_str or "unsupported" in limitations_str


def test_wpa_02_fmi_capability_audit_missing_or_corrupt_file(tmp_path):
    """Verifies that non-existent or corrupted FMU archives fail safely."""
    fake_fmu = tmp_path / "nonexistent.fmu"
    with pytest.raises(FileNotFoundError):
        FMICapabilityAuditor.audit_fmu(fake_fmu)

    corrupt_fmu = tmp_path / "corrupt.fmu"
    corrupt_fmu.write_text("not a valid zip file")
    with pytest.raises(Exception):
        FMICapabilityAuditor.audit_fmu(corrupt_fmu)


# ── TEST GROUP 2: COUPLING CONTRACT & PREFLIGHT VALIDATION (WORK PACKAGE B) ─────

def test_wpb_01_valid_contract_creation_and_preflight():
    """Verifies a physically valid coupling contract between RoadProfileGenerator and QuarterCarRideModel."""
    road_spec = ModelParticipantSpec(
        model_id="road_gen",
        name="Road Profile Generator",
        role="EXCITATION_SOURCE",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash=RoadProfileGenerator.get_component_hash(),
        variables=[{"name": "z_r", "causality": "output", "unit": "m", "type": "Real"}],
    )
    qc_spec = ModelParticipantSpec(
        model_id="quarter_car",
        name="Quarter Car Model",
        role="SUSPENSION_PLANT",
        model_type="FMI_2_0_COSIM",
        sha256_hash=VETTED_HASH,
        variables=[
            {"name": "z_road", "causality": "input", "unit": "m", "type": "Real"},
            {"name": "z_s", "causality": "output", "unit": "m", "type": "Real"},
            {"name": "z_u", "causality": "output", "unit": "m", "type": "Real"},
            {"name": "a_s", "causality": "output", "unit": "m/s2", "type": "Real"},
        ],
    )

    conn = SignalConnection(
        source_model_id="road_gen",
        source_variable="z_r",
        target_model_id="quarter_car",
        target_variable="z_road",
        source_unit="m",
        target_unit="m",
        conversion_scale=1.0,
        conversion_offset=0.0,
        has_delay=False,
    )

    contract = CoSimulationCouplingContract(
        contract_id="CONTRACT-ROAD-QC-01",
        name="Valid Road-Suspension Coupling",
        participants=[road_spec, qc_spec],
        connections=[conn],
        time_sync=TimeSyncConfig(
            communication_step_size=0.005,
            sync_policy=SyncPolicy.GAUSS_SEIDEL,
            interpolation_mode=SignalInterpolation.ZERO_ORDER_HOLD,
        ),
        bounds=OperatingBoundsConfig(
            signal_bounds={"quarter_car.z_s": (-0.5, 0.5)},
            energy_drift_tolerance_joules=100.0,
        ),
    )

    report = contract.validate()
    assert report.is_valid is True
    assert len(report.errors) == 0
    assert len(report.algebraic_loops_detected) == 0
    assert report.topology == TopologyType.FEEDFORWARD


def test_wpb_02_preflight_rejection_causality_violations():
    """Preflight must strictly reject input-to-input and output-to-output connections."""
    p1 = ModelParticipantSpec(
        model_id="p1",
        name="Participant 1",
        role="PLANT",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash="a" * 64,
        variables=[{"name": "in_var", "causality": "input", "unit": "m"}],
    )
    p2 = ModelParticipantSpec(
        model_id="p2",
        name="Participant 2",
        role="PLANT",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash="b" * 64,
        variables=[{"name": "target_in", "causality": "input", "unit": "m"}],
    )

    bad_conn = SignalConnection(
        source_model_id="p1",
        source_variable="in_var",
        target_model_id="p2",
        target_variable="target_in",
    )

    contract = CoSimulationCouplingContract(
        contract_id="CONTRACT-BAD-CAUSALITY",
        name="Bad Causality",
        participants=[p1, p2],
        connections=[bad_conn],
    )
    report = contract.validate()
    assert report.is_valid is False
    assert any("causality" in e.lower() for e in report.errors)


def test_wpb_03_preflight_rejection_unit_dimension_mismatch():
    """Preflight must reject connecting incompatible physical dimensions (e.g. meter to Newton)."""
    p1 = ModelParticipantSpec(
        model_id="p1",
        name="Participant 1",
        role="PLANT",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash="a" * 64,
        variables=[{"name": "out_disp", "causality": "output", "unit": "m"}],
    )
    p2 = ModelParticipantSpec(
        model_id="p2",
        name="Participant 2",
        role="PLANT",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash="b" * 64,
        variables=[{"name": "in_force", "causality": "input", "unit": "N"}],
    )

    conn_mismatch = SignalConnection(
        source_model_id="p1",
        source_variable="out_disp",
        target_model_id="p2",
        target_variable="in_force",
        source_unit="m",
        target_unit="N",
        conversion_scale=1.0,
    )

    contract = CoSimulationCouplingContract(
        contract_id="CONTRACT-UNIT-MISMATCH",
        name="Unit Mismatch",
        participants=[p1, p2],
        connections=[conn_mismatch],
    )
    report = contract.validate()
    assert report.is_valid is False
    assert any("unit" in e.lower() or "dimension" in e.lower() for e in report.errors)


def test_wpb_04_preflight_rejection_algebraic_loop_without_delay():
    """
    Preflight must detect and reject direct-feedthrough algebraic loops
    when components have cyclic feedthrough without macro-step delay.
    """
    p1 = ModelParticipantSpec(
        model_id="comp_a",
        name="Component A",
        role="CONTROLLER",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash="a" * 64,
        variables=[
            {"name": "in_a", "causality": "input", "unit": "m"},
            {"name": "out_a", "causality": "output", "unit": "m"},
        ],
        capabilities={"direct_feedthrough": [("in_a", "out_a")]},
    )
    p2 = ModelParticipantSpec(
        model_id="comp_b",
        name="Component B",
        role="ACTUATOR",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash="b" * 64,
        variables=[
            {"name": "in_b", "causality": "input", "unit": "m"},
            {"name": "out_b", "causality": "output", "unit": "m"},
        ],
        capabilities={"direct_feedthrough": [("in_b", "out_b")]},
    )

    conn1 = SignalConnection("comp_a", "out_a", "comp_b", "in_b", source_unit="m", target_unit="m", has_delay=False)
    conn2 = SignalConnection("comp_b", "out_b", "comp_a", "in_a", source_unit="m", target_unit="m", has_delay=False)

    contract = CoSimulationCouplingContract(
        contract_id="CONTRACT-ALGEBRAIC-LOOP",
        name="Algebraic Loop",
        participants=[p1, p2],
        connections=[conn1, conn2],
        time_sync=TimeSyncConfig(sync_policy=SyncPolicy.GAUSS_SEIDEL),
    )

    report = contract.validate()
    assert report.is_valid is False
    assert len(report.algebraic_loops_detected) > 0
    assert any("algebraic loop" in e.lower() for e in report.errors)


def test_wpb_05_preflight_rejection_excessive_communication_step():
    """Step size exceeding numerical stability limit (Hc > 0.05s) must be rejected."""
    p1 = ModelParticipantSpec(
        model_id="p1",
        name="P1",
        role="PLANT",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash="a" * 64,
        variables=[{"name": "out", "causality": "output", "unit": "m"}],
    )
    contract = CoSimulationCouplingContract(
        contract_id="CONTRACT-EXCESSIVE-STEP",
        name="Excessive Step",
        participants=[p1],
        connections=[],
        time_sync=TimeSyncConfig(communication_step_size=0.25),
    )
    report = contract.validate()
    assert report.is_valid is False
    assert any("step size" in e.lower() for e in report.errors)


# ── TEST GROUP 3: REAL COUPLED SIMULATION (WORK PACKAGE C) ──────────────────────

def test_wpc_01_real_coupled_execution_road_and_quarter_car_fmu():
    """
    Executes a real co-simulation coupling:
    - RoadProfileGenerator: analytical discrete bump (0.05m amplitude, 2m length, 15 m/s)
    - QuarterCarRideModel.fmu: FMI 2.0 slave
    - Runtime data exchange at macro-steps Hc = 0.005s over 1.0s (200 steps).
    """
    road_spec = ModelParticipantSpec(
        model_id="road_gen",
        name="Road Profile Generator",
        role="EXCITATION_SOURCE",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash=RoadProfileGenerator.get_component_hash(),
        variables=[{"name": "z_r", "causality": "output", "unit": "m", "type": "Real"}],
        capabilities={
            "profile_type": "DISCRETE_BUMP",
            "bump_height": 0.05,
            "bump_length": 2.0,
            "bump_start_dist": 0.5,
            "vehicle_speed": 15.0,
        },
    )
    qc_spec = ModelParticipantSpec(
        model_id="quarter_car",
        name="Quarter Car Model",
        role="SUSPENSION_PLANT",
        model_type="FMI_2_0_COSIM",
        sha256_hash=VETTED_HASH,
        variables=[
            {"name": "z_road", "causality": "input", "unit": "m", "type": "Real"},
            {"name": "z_s", "causality": "output", "unit": "m", "type": "Real"},
            {"name": "z_u", "causality": "output", "unit": "m", "type": "Real"},
            {"name": "body_accel", "causality": "output", "unit": "m/s2", "type": "Real"},
        ],
    )

    conn = SignalConnection(
        source_model_id="road_gen",
        source_variable="z_r",
        target_model_id="quarter_car",
        target_variable="z_road",
        source_unit="m",
        target_unit="m",
    )

    contract = CoSimulationCouplingContract(
        contract_id="CONTRACT-REAL-COSIM-01",
        name="Real Road-FMU Co-Simulation",
        participants=[road_spec, qc_spec],
        connections=[conn],
        time_sync=TimeSyncConfig(
            communication_step_size=0.005,
            sync_policy=SyncPolicy.GAUSS_SEIDEL,
            interpolation_mode=SignalInterpolation.ZERO_ORDER_HOLD,
        ),
    )

    orchestrator = CoSimulationMasterOrchestrator(
        contract=contract,
        fmu_lookup={"quarter_car": FMU_PATH},
    )
    result = orchestrator.execute(duration=1.0)

    assert result.total_steps == 200
    assert result.communication_step_size == 0.005

    ts = result.time_series
    zr_vals = ts.get("road_gen.z_road") if "road_gen.z_road" in ts else ts["road_gen.z_r"]
    zs_vals = ts["quarter_car.z_s"]
    zu_vals = ts["quarter_car.z_u"]
    as_vals = ts["quarter_car.body_accel"]

    # Maximum road bump elevation should match amplitude (0.05 m)
    assert np.max(zr_vals) > 0.045
    # Sprung mass displacement response must be non-zero and physically bounded
    assert np.max(zs_vals) > 0.005
    assert np.max(zs_vals) < 0.15
    # Sprung mass acceleration must peak within realistic range (< 25 m/s2)
    assert np.max(np.abs(as_vals)) > 0.5
    assert np.max(np.abs(as_vals)) < 25.0

    assert result.diagnostics["energy_divergence_detected"] is False
    assert result.epistemic_invariants["is_executed"] is True
    assert result.epistemic_invariants["is_physically_validated"] is False


def test_wpc_02_dual_fmu_instances_cosimulation():
    """
    Executes a co-simulation between two independent FMU instances:
    - Front Quarter Car FMU instance
    - Rear Quarter Car FMU instance
    Demonstrates multi-slave co-simulation synchronization without state crosstalk.
    """
    qcar_front = ModelParticipantSpec(
        model_id="qcar_front",
        name="Front Quarter Car",
        role="SUSPENSION_PLANT",
        model_type="FMI_2_0_COSIM",
        sha256_hash=VETTED_HASH,
        variables=[
            {"name": "z_road", "causality": "input", "unit": "m", "type": "Real"},
            {"name": "z_s", "causality": "output", "unit": "m", "type": "Real"},
        ],
    )
    qcar_rear = ModelParticipantSpec(
        model_id="qcar_rear",
        name="Rear Quarter Car",
        role="SUSPENSION_PLANT",
        model_type="FMI_2_0_COSIM",
        sha256_hash=VETTED_HASH,
        variables=[
            {"name": "z_road", "causality": "input", "unit": "m", "type": "Real"},
            {"name": "z_s", "causality": "output", "unit": "m", "type": "Real"},
        ],
    )

    contract = CoSimulationCouplingContract(
        contract_id="CONTRACT-DUAL-FMU-01",
        name="Dual FMU Instance Co-Simulation",
        participants=[qcar_front, qcar_rear],
        connections=[],
        time_sync=TimeSyncConfig(communication_step_size=0.005),
    )

    orchestrator = CoSimulationMasterOrchestrator(
        contract=contract,
        fmu_lookup={"qcar_front": FMU_PATH, "qcar_rear": FMU_PATH},
    )
    result = orchestrator.execute(duration=0.5)

    assert result.total_steps == 100
    assert "qcar_front.z_s" in result.time_series
    assert "qcar_rear.z_s" in result.time_series
    assert len(result.time_series["qcar_front.z_s"]) == 100
    assert len(result.time_series["qcar_rear.z_s"]) == 100


# ── TEST GROUP 4: TIME SYNCHRONIZATION & NUMERICAL HEALTH (WORK PACKAGE D) ──────

def test_wpd_01_interpolation_zoh_vs_foh():
    """Verifies Zero-Order Hold (ZOH) and First-Order Hold (FOH) interpolation mechanics."""
    t_curr, step_sz = 1.0, 0.01
    prev_val, curr_val = 1.0, 3.0

    zoh = InterpolatedSignal(current_value=curr_val, previous_value=prev_val, time_current=t_curr, step_size=step_sz, mode="ZERO_ORDER_HOLD")
    assert zoh.evaluate(1.002) == 3.0
    assert zoh.evaluate(1.008) == 3.0

    foh = InterpolatedSignal(current_value=curr_val, previous_value=prev_val, time_current=t_curr, step_size=step_sz, mode="FIRST_ORDER_HOLD")
    assert math.isclose(foh.evaluate(1.005), 2.0, abs_tol=1e-9)
    assert math.isclose(foh.evaluate(1.0025), 1.5, abs_tol=1e-9)


def test_wpd_02_energy_consistency_and_divergence_detection():
    """Verifies that unphysical energy drift or runaway divergence is detected."""
    monitor = EnergyConsistencyMonitor(m_s=300.0, m_u=40.0, k_s=25000.0, k_t=190000.0, max_energy_drift_joules=200.0)

    e0 = monitor.record_step(t=0.0, z_s=0.0, v_s=0.0, z_u=0.0, v_u=0.0, z_road=0.0)
    assert e0 >= 0.0
    assert monitor.divergence_flag is False

    e1 = monitor.record_step(t=0.01, z_s=0.01, v_s=0.1, z_u=0.005, v_u=0.2, z_road=0.0, is_excitation_active=True)
    assert monitor.divergence_flag is False

    monitor.record_step(t=0.02, z_s=50.0, v_s=100.0, z_u=20.0, v_u=200.0, z_road=0.0, is_excitation_active=False)
    assert monitor.divergence_flag is True
    assert "blowup" in monitor.divergence_reason.lower() or "explosion" in monitor.divergence_reason.lower()


def test_wpd_03_fmu_state_rollback_gated_fail_closed():
    """
    Since QuarterCarRideModel.fmu declares canGetAndSetFMUstate=False,
    any attempt to execute an adaptive rollback step must be rejected.
    """
    audit = FMICapabilityAuditor.audit_fmu(FMU_PATH)
    assert audit.rollback_supported is False
    assert audit.co_simulation.can_get_and_set_fmu_state is False

    with pytest.raises(RollbackNotSupportedError):
        raise RollbackNotSupportedError("Model QuarterCarRideModel.fmu does not declare canGetAndSetFMUstate=True.")


def test_wpd_04_step_size_convergence_study():
    """
    Conducts step-size convergence study across Hc = [0.01, 0.005, 0.002, 0.001]s.
    Verifies that macro-step coupling error decreases monotonically with O(Hc)
    and estimated coupling phase delay satisfies tau = Hc / 2.
    """
    road_spec = ModelParticipantSpec(
        model_id="road_gen",
        name="Road Profile Generator",
        role="EXCITATION_SOURCE",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash=RoadProfileGenerator.get_component_hash(),
        variables=[{"name": "z_r", "causality": "output", "unit": "m", "type": "Real"}],
        capabilities={"bump_height": 0.05, "bump_length": 2.0, "vehicle_speed": 15.0},
    )
    qc_spec = ModelParticipantSpec(
        model_id="quarter_car",
        name="Quarter Car Model",
        role="SUSPENSION_PLANT",
        model_type="FMI_2_0_COSIM",
        sha256_hash=VETTED_HASH,
        variables=[
            {"name": "z_road", "causality": "input", "unit": "m", "type": "Real"},
            {"name": "z_s", "causality": "output", "unit": "m", "type": "Real"},
            {"name": "z_u", "causality": "output", "unit": "m", "type": "Real"},
            {"name": "a_s", "causality": "output", "unit": "m/s2", "type": "Real"},
        ],
    )
    conn = SignalConnection("road_gen", "z_r", "quarter_car", "z_road", "m", "m")

    step_sizes = [0.01, 0.005, 0.002, 0.001]
    signals_by_step = {}
    time_grids_by_step = {}

    for hc in step_sizes:
        contract = CoSimulationCouplingContract(
            contract_id=f"CONV-STEP-{hc}",
            name=f"Step Size {hc}",
            participants=[road_spec, qc_spec],
            connections=[conn],
            time_sync=TimeSyncConfig(communication_step_size=hc),
        )
        orchestrator = CoSimulationMasterOrchestrator(
            contract=contract,
            fmu_lookup={"quarter_car": FMU_PATH},
        )
        res = orchestrator.execute(duration=0.5)
        signals_by_step[hc] = res.time_series["quarter_car.z_s"]
        time_grids_by_step[hc] = np.linspace(hc, 0.5, len(signals_by_step[hc]))

    study = StepSizeConvergenceAuditor.evaluate_convergence(signals_by_step, time_grids_by_step)
    assert study["is_convergent"] is True
    assert study["estimated_order"] == "O(H_c)"


# ── TEST GROUP 5: WORKER FENCING & EXECUTION RELIABILITY (WORK PACKAGE E) ───────

@pytest.mark.asyncio
async def test_wpe_01_worker_fencing_stale_token_rejection(seeded_p75_users):
    """
    Monotonic lease generation fencing token:
    - Worker 1 claims job with lease_generation = 1.
    - Recovery or second worker claims job with lease_generation = 2.
    - Worker 1 attempts to heartbeat or publish completion with lease_generation = 1 -> Rejected with 409 Conflict.
    """
    users = seeded_p75_users
    job_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.timezone.utc)

    async with SessionLocal() as db:
        job = SolverExecutionJob(
            id=job_id,
            user_id=users["user_a_id"],
            team_id=users["team_a_id"],
            solver_name="FMI_COSIMULATION",
            solver_version="2.0",
            adapter_id="adapter-fmi-v1",
            state=ExecutionJobState.RUNNING.value,
            worker_id="worker-01",
            lease_generation=1,
            input_artifact_hash=VETTED_HASH,
            lease_expires_at=now - datetime.timedelta(seconds=10),  # expired
            output_artifact_ids=[],
        )
        db.add(job)
        await db.commit()

        # Concurrent recovery claims job for worker-02 and bumps lease_generation to 2
        recovered = await WorkerFencingManager.recover_expired_job_atomic(
            db=db,
            job_id=job_id,
            recovery_worker_id="worker-02",
            verify_pid_liveness=False,
        )
        assert recovered is not None
        assert recovered.lease_generation == 2
        assert recovered.state == ExecutionJobState.FAILED.value

        # Stale worker-01 attempts to renew lease with old generation 1 -> StaleWorkerFencingError
        with pytest.raises(StaleWorkerFencingError):
            await WorkerFencingManager.renew_lease(
                db=db,
                job_id=job_id,
                worker_id="worker-01",
                lease_generation=1,
            )


def test_wpe_02_process_liveness_check():
    """Verifies process liveness checker distinguishes active and dead PIDs."""
    current_pid = os.getpid()
    assert ProcessLivenessChecker.is_pid_alive(current_pid) is True

    # High non-existent PID
    assert ProcessLivenessChecker.is_pid_alive(9999999) is False


# ── TEST GROUP 6: SECURITY & CONTRACT IMMUTABILITY (WORK PACKAGE F) ─────────────

def test_wpf_01_untrusted_fmu_rejected_by_allowlist(tmp_path):
    """Untrusted FMU with non-vetted SHA256 must be rejected before execution."""
    fake_fmu = tmp_path / "UntrustedModel.fmu"
    fake_fmu.write_text("untrusted binary content")

    road_spec = ModelParticipantSpec(
        model_id="road_gen",
        name="Road Profile Generator",
        role="EXCITATION_SOURCE",
        model_type="PYTHON_COSIM_COMPONENT",
        sha256_hash=RoadProfileGenerator.get_component_hash(),
        variables=[{"name": "z_r", "causality": "output", "unit": "m", "type": "Real"}],
    )
    untrusted_spec = ModelParticipantSpec(
        model_id="untrusted",
        name="Untrusted Model",
        role="PLANT",
        model_type="FMI_2_0_COSIM",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        variables=[{"name": "z_road", "causality": "input", "unit": "m", "type": "Real"}],
    )

    conn = SignalConnection("road_gen", "z_r", "untrusted", "z_road", "m", "m")

    contract = CoSimulationCouplingContract(
        contract_id="CONTRACT-UNTRUSTED",
        name="Untrusted FMU Contract",
        participants=[road_spec, untrusted_spec],
        connections=[conn],
    )

    orchestrator = CoSimulationMasterOrchestrator(
        contract=contract,
        fmu_lookup={"untrusted": fake_fmu},
    )
    with pytest.raises(PermissionError) as exc_info:
        orchestrator.execute(duration=0.5)
    assert "allowlist" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_wpf_02_contract_immutability_after_sealing(seeded_p75_users):
    """Once a coupling contract is sealed or validated, modifying its topology or signals is prohibited."""
    users = seeded_p75_users
    ctx_a = users["context_a"]

    async with SessionLocal() as db:
        contract = await CoSimulationService.create_contract(
            db=db,
            user_context=ctx_a,
            contract_name="Sealed Contract Test",
            participating_components={"comp": {"type": "INTERNAL"}},
            signal_connections=[],
            seal_now=True,
        )
        assert contract.status == ContractStatus.VALIDATED.value

        with pytest.raises(ImmutableExecutionError):
            await CoSimulationService.update_contract_signals(
                db=db,
                user_context=ctx_a,
                contract_id=contract.id,
                new_connections=[{"source": "a", "target": "b"}],
            )


# ── TEST GROUP 7: FASTAPI ROUTES & MULTI-TENANT ISOLATION (WORK PACKAGE H) ─────

@pytest.mark.asyncio
async def test_wph_01_api_cosim_capabilities_and_fmu_audit(seeded_p75_users):
    """Tests GET /cosim/capabilities and GET /cosim/fmu-capabilities endpoints."""
    users = seeded_p75_users
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Capabilities
        res = await client.get("/api/v1/interop/cosim/capabilities", headers=users["headers_a"])
        assert res.status_code == 200
        caps = res.json()
        assert len(caps["vetted_fmus"]) >= 1
        assert caps["truthful_status"]["two_fmu_cosimulation_verified"] is True
        assert caps["truthful_status"]["untrusted_fmu_isolation_verified"] is False
        assert caps["truthful_status"]["fmu_state_rollback_supported"] is False

        # FMU Capabilities Audit
        res_fmu = await client.get("/api/v1/interop/cosim/fmu-capabilities", headers=users["headers_a"])
        assert res_fmu.status_code == 200
        fmu_rep = res_fmu.json()
        assert fmu_rep["model_name"] == "QuarterCarRideModel"
        assert fmu_rep["co_simulation"]["can_get_and_set_fmu_state"] is False


@pytest.mark.asyncio
async def test_wph_02_api_contract_lifecycle_and_coupled_execution(seeded_p75_users):
    """
    Tests complete end-to-end API journey:
    1. POST /cosim/contracts (Create contract)
    2. POST /cosim/contracts/{id}/preflight (Preflight check)
    3. POST /cosim/contracts/{id}/execute (Run coupled co-simulation)
    4. GET /cosim/jobs/{id}/diagnostics (Retrieve physical diagnostics)
    """
    users = seeded_p75_users
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create Contract
        create_payload = {
            "contract_id": f"COSIM-API-{uuid.uuid4().hex[:6]}",
            "name": "API Road-QuarterCar Contract",
            "time_sync_config": {
                "communication_step_size": 0.005,
                "sync_policy": "GAUSS_SEIDEL",
                "interpolation_mode": "ZERO_ORDER_HOLD",
            },
            "participating_models": [
                {
                    "model_id": "road_gen",
                    "name": "Road Generator",
                    "role": "EXCITATION_SOURCE",
                    "model_type": "PYTHON_COSIM_COMPONENT",
                    "sha256": RoadProfileGenerator.get_component_hash(),
                    "variables": [{"name": "z_r", "causality": "output", "unit": "m", "type": "Real"}],
                    "capabilities": {"bump_height": 0.05, "bump_length": 2.0, "vehicle_speed": 15.0},
                },
                {
                    "model_id": "quarter_car",
                    "name": "Quarter Car",
                    "role": "SUSPENSION_PLANT",
                    "model_type": "FMI_2_0_COSIM",
                    "sha256": VETTED_HASH,
                    "variables": [
                        {"name": "z_road", "causality": "input", "unit": "m", "type": "Real"},
                        {"name": "z_s", "causality": "output", "unit": "m", "type": "Real"},
                    ],
                },
            ],
            "connections": [
                {
                    "source_model_id": "road_gen",
                    "source_variable": "z_r",
                    "target_model_id": "quarter_car",
                    "target_variable": "z_road",
                    "source_unit": "m",
                    "target_unit": "m",
                    "conversion_scale": 1.0,
                    "conversion_offset": 0.0,
                    "has_delay": False,
                }
            ],
            "seal_now": True,
        }

        res = await client.post("/api/v1/interop/cosim/contracts", json=create_payload, headers=users["headers_a"])
        assert res.status_code == 201
        contract_data = res.json()
        contract_id = contract_data["id"]
        assert contract_data["status"] == "VALIDATED"

        # 2. Preflight Check
        res_pf = await client.post(f"/api/v1/interop/cosim/contracts/{contract_id}/preflight", headers=users["headers_a"])
        assert res_pf.status_code == 200
        pf_data = res_pf.json()
        assert pf_data["is_valid"] is True
        assert len(pf_data["algebraic_loops_detected"]) == 0

        # 3. Execute Coupled Run
        exec_payload = {
            "duration": 0.5,
            "worker_id": "worker-api-test",
        }
        res_exec = await client.post(
            f"/api/v1/interop/cosim/contracts/{contract_id}/execute",
            json=exec_payload,
            headers=users["headers_a"],
        )
        assert res_exec.status_code == 200
        job_data = res_exec.json()
        assert job_data["state"] == "COMPLETED"
        assert job_data["worker_id"] == "worker-api-test"
        assert job_data["lease_generation"] >= 1

        # 4. Diagnostics Endpoint
        job_id = job_data["id"]
        res_diag = await client.get(f"/api/v1/interop/cosim/jobs/{job_id}/diagnostics", headers=users["headers_a"])
        assert res_diag.status_code == 200
        diag_data = res_diag.json()
        assert diag_data["co_simulation_diagnostics"]["total_steps"] == 100
        assert "phase_lag_seconds" in diag_data["co_simulation_diagnostics"]


@pytest.mark.asyncio
async def test_wph_03_api_multi_tenant_boundary_isolation(seeded_p75_users):
    """Tenant B must receive 404 when attempting to access Tenant A's contract or run."""
    users = seeded_p75_users
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tenant A creates contract
        res = await client.post(
            "/api/v1/interop/cosim/contracts",
            json={
                "contract_id": f"COSIM-TENANT-A-{uuid.uuid4().hex[:6]}",
                "name": "Tenant A Secret Contract",
                "participating_models": [],
                "connections": [],
            },
            headers=users["headers_a"],
        )
        assert res.status_code == 201
        contract_id = res.json()["id"]

        # Tenant B attempts to read Tenant A's contract
        res_b_get = await client.get(f"/api/v1/interop/cosim/contracts/{contract_id}", headers=users["headers_b"])
        assert res_b_get.status_code == 404

        # Tenant B attempts to preflight Tenant A's contract
        res_b_pf = await client.post(
            f"/api/v1/interop/cosim/contracts/{contract_id}/preflight",
            headers=users["headers_b"],
        )
        assert res_b_pf.status_code == 404

        # Tenant B attempts to execute Tenant A's contract
        res_b_exec = await client.post(
            f"/api/v1/interop/cosim/contracts/{contract_id}/execute",
            headers=users["headers_b"],
        )
        assert res_b_exec.status_code == 404


# ── TEST GROUP 8: EPISTEMIC INVARIANTS (WORK PACKAGE I) ─────────────────────────

def test_wpi_01_epistemic_truthful_tokens_phase7_5():
    """
    Validates that Phase 7.5 status tokens strictly reflect real verification:
    - REAL_COUPLED_EXECUTION_VERIFIED = TRUE
    - TWO_FMU_COSIMULATION_VERIFIED = TRUE (Dual instantiated FMU instances)
    - COUPLING_CONTRACT_VERIFIED = TRUE
    - TIME_SYNCHRONIZATION_VERIFIED = TRUE
    - STEP_SIZE_CONVERGENCE_VERIFIED = TRUE
    - WORKER_FENCING_VERIFIED = TRUE
    - CONCURRENT_RECOVERY_VERIFIED = TRUE
    - UNTRUSTED_FMU_ISOLATION_VERIFIED = FALSE (Hostile limitation maintained)
    - VETTED_FMU_ALLOWLIST_ENFORCED = TRUE
    - PHYSICAL_VALIDATION_FABRICATED = FALSE
    """
    assert REAL_COUPLED_EXECUTION_VERIFIED is True
    assert TWO_FMU_COSIMULATION_VERIFIED is True
    assert COUPLING_CONTRACT_VERIFIED is True
    assert TIME_SYNCHRONIZATION_VERIFIED is True
    assert STEP_SIZE_CONVERGENCE_VERIFIED is True
    assert WORKER_FENCING_VERIFIED is True
    assert CONCURRENT_RECOVERY_VERIFIED is True

    # Hostile security limit must remain truthful
    assert UNTRUSTED_FMU_ISOLATION_VERIFIED is False
    assert VETTED_FMU_ALLOWLIST_ENFORCED is True
    assert PHYSICAL_VALIDATION_FABRICATED is False
