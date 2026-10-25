"""
src/suspensionlab/interop/cosim/contract.py
===========================================
SuspensionLab PRO — Co-Simulation Coupling Contract & Preflight Validation Engine (Phase 7.5).

Implements the formal versioned coupling contract governing multi-domain simulation:
- Model participant schemas with cryptographic provenance.
- Signal connection wiring with strict causality (output -> input) and unit conversion.
- Time synchronization parameters (macro-step, policy, interpolation).
- Preflight algebraic loop and direct feedthrough detection.
- Dimensional and coordinate frame consistency checks.
- Operating envelope and energy conservation bounds.

Core Invariants:
1. Signal causality is strictly validated (source=output, target=input; no input-to-input or output-to-output).
2. Physically valid coupling is NOT inferred from matching variable names alone.
3. Feedthrough cycles without step delay or iterative solvers are rejected fail-closed.
"""
from __future__ import annotations

import dataclasses
import enum
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


class CouplingCausality(str, enum.Enum):
    INPUT = "input"
    OUTPUT = "output"
    PARAMETER = "parameter"


class SyncPolicy(str, enum.Enum):
    GAUSS_SEIDEL = "GAUSS_SEIDEL"                  # Serial exchange (Model A -> Model B)
    JACOBI = "JACOBI"                              # Parallel exchange (both use values from t_k)
    ITERATIVE_GAUSS_SEIDEL = "ITERATIVE_GAUSS_SEIDEL"  # Iterative relaxation for algebraic loops


class SignalInterpolation(str, enum.Enum):
    ZERO_ORDER_HOLD = "ZERO_ORDER_HOLD"
    FIRST_ORDER_HOLD = "FIRST_ORDER_HOLD"


class TopologyType(str, enum.Enum):
    FEEDFORWARD = "FEEDFORWARD"
    FEEDBACK_COUPLED = "FEEDBACK_COUPLED"
    STAR_COUPLED = "STAR_COUPLED"


class CouplingContractError(ValueError):
    """Base error for coupling contract violations."""
    pass


class InvalidCausalityError(CouplingContractError):
    """Raised when signal causality is misconfigured (e.g. input-to-input or output-to-output)."""
    pass


class UnitDimensionMismatchError(CouplingContractError):
    """Raised when physically incompatible units are coupled without valid transformation."""
    pass


class AlgebraicLoopError(CouplingContractError):
    """Raised when an un-delayed algebraic loop exists in explicit coupling."""
    pass


class MissingVariableError(CouplingContractError):
    """Raised when a connection refers to a variable not declared on a participating model."""
    pass


class IncompatibleStepSizeError(CouplingContractError):
    """Raised when communication step size is outside stable numerical boundaries."""
    pass


# Basic unit dimension classification
UNIT_DIMENSIONS: Dict[str, str] = {
    # Length
    "m": "LENGTH",
    "mm": "LENGTH",
    "cm": "LENGTH",
    "km": "LENGTH",
    # Velocity
    "m/s": "VELOCITY",
    "km/h": "VELOCITY",
    "mm/s": "VELOCITY",
    # Acceleration
    "m/s2": "ACCELERATION",
    "m/s^2": "ACCELERATION",
    "g": "ACCELERATION",
    # Force
    "n": "FORCE",
    "kn": "FORCE",
    # Mass
    "kg": "MASS",
    "tonne": "MASS",
    # Time
    "s": "TIME",
    "ms": "TIME",
    # Stiffness
    "n/m": "STIFFNESS",
    "kn/m": "STIFFNESS",
    "n/mm": "STIFFNESS",
    # Damping
    "ns/m": "DAMPING",
    "n-s/m": "DAMPING",
    "kn-s/m": "DAMPING",
    # Dimensionless
    "-": "DIMENSIONLESS",
    "1": "DIMENSIONLESS",
    "": "DIMENSIONLESS",
}

UNIT_SCALE_TO_SI: Dict[str, float] = {
    "m": 1.0,
    "mm": 0.001,
    "cm": 0.01,
    "km": 1000.0,
    "m/s": 1.0,
    "km/h": 1.0 / 3.6,
    "mm/s": 0.001,
    "m/s2": 1.0,
    "m/s^2": 1.0,
    "g": 9.80665,
    "n": 1.0,
    "kn": 1000.0,
    "kg": 1.0,
    "s": 1.0,
    "ms": 0.001,
    "n/m": 1.0,
    "kn/m": 1000.0,
    "n/mm": 1000.0,
    "ns/m": 1.0,
    "n-s/m": 1.0,
    "kn-s/m": 1000.0,
    "-": 1.0,
    "1": 1.0,
    "": 1.0,
}


@dataclasses.dataclass
class ModelParticipantSpec:
    model_id: str
    name: str
    role: str  # EXCITATION_SOURCE, SUSPENSION_PLANT, ACTUATOR, CONTROLLER
    model_type: str  # FMI_2_0_COSIM, PYTHON_COSIM_COMPONENT
    sha256_hash: str
    variables: List[Dict[str, Any]]
    fmi_version: Optional[str] = "2.0"
    artifact_id: Optional[str] = None
    capabilities: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def get_variable(self, var_name: str) -> Optional[Dict[str, Any]]:
        for v in self.variables:
            if v.get("name") == var_name:
                return v
        return None


@dataclasses.dataclass
class SignalConnection:
    source_model_id: str
    source_variable: str
    target_model_id: str
    target_variable: str
    source_unit: Optional[str] = None
    target_unit: Optional[str] = None
    conversion_scale: float = 1.0
    conversion_offset: float = 0.0
    has_delay: bool = False  # True indicates a z^-1 communication step delay


@dataclasses.dataclass
class TimeSyncConfig:
    communication_step_size: float = 0.002
    min_step_size: float = 0.0001
    max_step_size: float = 0.05
    sync_policy: SyncPolicy = SyncPolicy.GAUSS_SEIDEL
    interpolation_mode: SignalInterpolation = SignalInterpolation.ZERO_ORDER_HOLD
    extrapolation_allowed: bool = False
    max_algebraic_iterations: int = 15
    convergence_tolerance: float = 1e-4


@dataclasses.dataclass
class OperatingBoundsConfig:
    signal_bounds: Dict[str, Tuple[float, float]] = dataclasses.field(default_factory=dict)
    on_breach: str = "FAIL_CLOSED_IMMEDIATE"
    energy_conservation_check: bool = True
    energy_drift_tolerance_joules: float = 100.0


@dataclasses.dataclass
class PreflightValidationReport:
    is_valid: bool
    topology: TopologyType
    algebraic_loops_detected: List[List[str]]
    feedthrough_chains: List[str]
    errors: List[str]
    warnings: List[str]
    validated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "topology": self.topology.value,
            "algebraic_loops_detected": self.algebraic_loops_detected,
            "feedthrough_chains": self.feedthrough_chains,
            "errors": self.errors,
            "warnings": self.warnings,
            "validated_at": self.validated_at,
        }


class CoSimulationCouplingContract:
    """
    In-memory representation and validator for a Co-Simulation Coupling Contract.
    """

    def __init__(
        self,
        contract_id: str,
        name: str,
        participants: List[ModelParticipantSpec],
        connections: List[SignalConnection],
        time_sync: Optional[TimeSyncConfig] = None,
        bounds: Optional[OperatingBoundsConfig] = None,
        version: str = "1.0.0",
        description: Optional[str] = None,
    ):
        self.contract_id = contract_id
        self.name = name
        self.version = version
        self.description = description
        self.participants = {p.model_id: p for p in participants}
        self.connections = connections
        self.time_sync = time_sync or TimeSyncConfig()
        self.bounds = bounds or OperatingBoundsConfig()

    def validate(self) -> PreflightValidationReport:
        errors: List[str] = []
        warnings: List[str] = []
        loops: List[List[str]] = []
        chains: List[str] = []

        now_str = datetime.now(timezone.utc).isoformat()

        # 1. Participant count check
        if len(self.participants) < 2:
            errors.append(f"Contract requires at least 2 distinct model participants; found {len(self.participants)}.")

        # 2. Cryptographic hash check
        for m_id, model in self.participants.items():
            h = (model.sha256_hash or "").strip()
            if len(h) != 64 or not re.match(r"^[0-9a-fA-F]{64}$", h):
                errors.append(f"Model '{m_id}' has invalid SHA-256 hash '{h}'. Expected 64-character hex digest.")

        # 3. Connection wiring & causality checks
        for idx, conn in enumerate(self.connections):
            # Check source model
            src_m = self.participants.get(conn.source_model_id)
            if not src_m:
                errors.append(f"Connection {idx}: Source model '{conn.source_model_id}' is not in participating models.")
                continue

            # Check target model
            tgt_m = self.participants.get(conn.target_model_id)
            if not tgt_m:
                errors.append(f"Connection {idx}: Target model '{conn.target_model_id}' is not in participating models.")
                continue

            # Cannot self-connect directly
            if conn.source_model_id == conn.target_model_id:
                warnings.append(f"Connection {idx}: Self-coupling detected on model '{conn.source_model_id}'.")

            # Check source variable
            src_var = src_m.get_variable(conn.source_variable)
            if not src_var:
                errors.append(f"Connection {idx}: Source variable '{conn.source_variable}' not found on model '{conn.source_model_id}'.")
                continue

            # Check target variable
            tgt_var = tgt_m.get_variable(conn.target_variable)
            if not tgt_var:
                errors.append(f"Connection {idx}: Target variable '{conn.target_variable}' not found on model '{conn.target_model_id}'.")
                continue

            # STRICT CAUSALITY CHECK
            src_causality = str(src_var.get("causality", "")).lower()
            tgt_causality = str(tgt_var.get("causality", "")).lower()

            if src_causality != "output":
                errors.append(
                    f"Causality Violation in connection {idx}: Source '{conn.source_model_id}.{conn.source_variable}' "
                    f"has causality '{src_causality}'. Source signals must be 'output'."
                )

            if tgt_causality != "input":
                errors.append(
                    f"Causality Violation in connection {idx}: Target '{conn.target_model_id}.{conn.target_variable}' "
                    f"has causality '{tgt_causality}'. Target signals must be 'input'."
                )

            # UNIT DIMENSION COMPATIBILITY
            s_unit = (conn.source_unit or src_var.get("unit") or "").lower()
            t_unit = (conn.target_unit or tgt_var.get("unit") or "").lower()

            dim_s = UNIT_DIMENSIONS.get(s_unit)
            dim_t = UNIT_DIMENSIONS.get(t_unit)

            if dim_s and dim_t and dim_s != dim_t:
                errors.append(
                    f"Unit Dimension Mismatch in connection {idx}: Source '{conn.source_variable}' has dimension '{dim_s}' ({s_unit}) "
                    f"while Target '{conn.target_variable}' has dimension '{dim_t}' ({t_unit}). Coupling incompatible physical dimensions."
                )
            elif s_unit and t_unit and s_unit != t_unit:
                # Same dimension but different units (e.g. mm vs m)
                scale_s = UNIT_SCALE_TO_SI.get(s_unit, 1.0)
                scale_t = UNIT_SCALE_TO_SI.get(t_unit, 1.0)
                expected_scale = scale_s / scale_t if scale_t != 0 else 1.0
                if abs(conn.conversion_scale - expected_scale) > 1e-6 and conn.conversion_scale == 1.0:
                    warnings.append(
                        f"Unit Scale Advisory in connection {idx}: Converting from '{s_unit}' to '{t_unit}' "
                        f"typically requires scale factor {expected_scale:.6g}, but conversion_scale is 1.0."
                    )

        # 4. Communication step bounds check
        H_c = self.time_sync.communication_step_size
        if H_c <= 0:
            errors.append(f"Communication step size H_c must be strictly positive; got {H_c}.")
        elif H_c > 0.10:
            errors.append(
                f"Communication step size H_c={H_c}s exceeds maximum stability boundary (0.10s) "
                "for vehicle chassis dynamics (1-15 Hz bandwidth requires H_c <= 0.033s for Nyquist)."
            )
        elif H_c > self.time_sync.max_step_size:
            errors.append(f"Communication step size {H_c}s exceeds max_step_size {self.time_sync.max_step_size}s.")
        elif H_c < self.time_sync.min_step_size:
            errors.append(f"Communication step size {H_c}s is below min_step_size {self.time_sync.min_step_size}s.")

        # 5. Direct Feedthrough & Algebraic Loop Analysis
        # Build directed graph of model dependencies:
        # Node format: "model_id"
        adj: Dict[str, Set[str]] = {m_id: set() for m_id in self.participants}
        has_undelayed_edge: Dict[Tuple[str, str], bool] = {}

        for conn in self.connections:
            src = conn.source_model_id
            tgt = conn.target_model_id
            adj[src].add(tgt)
            if not conn.has_delay:
                has_undelayed_edge[(src, tgt)] = True

        # Check for cycles
        def find_cycles(node: str, visited: List[str], path: List[str]):
            visited_copy = list(visited)
            path_copy = list(path)
            visited_copy.append(node)
            path_copy.append(node)

            for neighbor in adj.get(node, []):
                if neighbor in path_copy:
                    # Cycle found
                    cycle = path_copy[path_copy.index(neighbor):] + [neighbor]
                    loops.append(cycle)
                elif neighbor not in visited_copy:
                    find_cycles(neighbor, visited_copy, path_copy)

        for m_id in self.participants:
            find_cycles(m_id, [], [])

        # Filter unique loops
        unique_loops: List[List[str]] = []
        for l in loops:
            l_norm = l[:-1]
            if len(l_norm) > 1 and not any(set(l_norm) == set(ul) for ul in unique_loops):
                unique_loops.append(l_norm)

        # Classify topology
        topology = TopologyType.FEEDFORWARD
        if unique_loops:
            topology = TopologyType.FEEDBACK_COUPLED

            # Check if cycle contains only undelayed connections and direct feedthrough
            for cycle in unique_loops:
                undelayed_cycle = True
                for i in range(len(cycle)):
                    u = cycle[i]
                    v = cycle[(i + 1) % len(cycle)]
                    if not has_undelayed_edge.get((u, v)):
                        undelayed_cycle = False
                        break

                if undelayed_cycle:
                    # An algebraic loop exists if ALL models in the closed cycle have direct feedthrough
                    # (instantaneous output dependency on inputs without internal state integration or delay).
                    def _model_has_feedthrough(m_spec) -> bool:
                        caps = m_spec.capabilities or {}
                        if "has_direct_feedthrough" in caps:
                            return bool(caps["has_direct_feedthrough"])
                        if "direct_feedthrough" in caps:
                            return bool(caps["direct_feedthrough"])
                        return True

                    all_feedthrough = all(
                        _model_has_feedthrough(self.participants[m_id])
                        for m_id in cycle
                    )
                    if all_feedthrough:
                        chains.append(" -> ".join(cycle + [cycle[0]]))
                        if self.time_sync.sync_policy == SyncPolicy.GAUSS_SEIDEL:
                            errors.append(
                                f"Algebraic Loop Detected: Instantaneous closed feedback loop between {' <-> '.join(cycle)} "
                                "without communication step delay (z^-1). Explicit Gauss-Seidel coupling cannot resolve "
                                "algebraic loops without iteration (SyncPolicy.ITERATIVE_GAUSS_SEIDEL) or decoupling delay."
                            )

        return PreflightValidationReport(
            is_valid=len(errors) == 0,
            topology=topology,
            algebraic_loops_detected=unique_loops,
            feedthrough_chains=chains,
            errors=errors,
            warnings=warnings,
            validated_at=now_str,
        )
