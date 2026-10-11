"""
physics/provenance.py
=====================

Simulation Provenance Module for SuspensionLab.
Provides tracking, hashing, and tracing capabilities for simulation runs,
so that all results carry metadata about their lineage and mathematical foundation.

Design Principles:
- Immutability: Provenance metadata represents a snapshot in time.
- Traceability: Cryptographic hashes (SHA-256) of inputs and results allow exact correlation.
- Validatability: Known limitations and correlation states are explicitly tracked.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Optional
from datetime import datetime, timezone

MODEL_VERSIONS = {
    "quarter_car": "quarter-car-v2",
    "half_car": "half-car-v2",
    "full_car": "full-car-v3",
    "handling": "handling-v2",
    "lap_sim": "fast-quasi-steady-v3.0",
    "fast_quasi_steady": "fast-quasi-steady-v3.0",
    "dynamic_lap_sim": "dynamic-transient-14dof-v3.2",
    "dynamic_transient_14dof": "dynamic-transient-14dof-v3.2",
    "durability": "iso8608-palmgren-miner-v1",
}

SOLVER_VERSIONS = {
    "default": "rk4-bdf-1.0",
    "fast_quasi_steady": "ggv-forward-backward-v3.0",
    "dynamic_transient_14dof": "fixed-step-rk4-1khz-v3.2",
}

def compute_hash(data: Any) -> str:
    """Compute a SHA-256 hash of a dictionary or basic Python types by converting to canonical JSON."""
    serialized = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

@dataclass(frozen=True)
class SimulationProvenance:
    model_family: str          # "quarter_car", "full_car", "kinematics", "handling", "lap_sim"
    model_version: str         # semantic version of the model code
    parameter_hash: str        # SHA-256 of the input parameter set
    solver_version: str        # e.g. "newton_fd_v2", "rk4_v1"
    input_hash: str            # SHA-256 of the full input dataset
    validation_state: str      # "unvalidated", "self_consistent", "correlated"
    correlation_error: Optional[float]  # if correlated, the error metric
    known_limitations: list[str]        # explicit list of model limitations
    result_hash: str           # SHA-256 of the output data
    timestamp: str             # ISO 8601

    def to_dict(self) -> dict[str, Any]:
        """Convert the provenance data to a dictionary."""
        return asdict(self)

    def validate(self) -> None:
        """Validate required fields and basic integrity constraints."""
        if not self.model_family:
            raise ValueError("model_family cannot be empty")
        if not self.model_version:
            raise ValueError("model_version cannot be empty")
        if not self.parameter_hash:
            raise ValueError("parameter_hash cannot be empty")
        if not self.solver_version:
            raise ValueError("solver_version cannot be empty")
        if not self.input_hash:
            raise ValueError("input_hash cannot be empty")
        if self.validation_state not in ("unvalidated", "self_consistent", "correlated"):
            raise ValueError(f"Invalid validation_state: {self.validation_state}")
        if self.validation_state == "correlated" and self.correlation_error is None:
            raise ValueError("correlation_error must be provided if state is 'correlated'")
        if not self.result_hash:
            raise ValueError("result_hash cannot be empty")
        if not self.timestamp:
            raise ValueError("timestamp cannot be empty")

def create_provenance(
    model_family: str,
    model_version: str,
    solver_version: str,
    params: Any,
    inputs: Any,
    results: Any,
    validation_state: str = "unvalidated",
    correlation_error: Optional[float] = None,
    known_limitations: Optional[list[str]] = None
) -> SimulationProvenance:
    """
    Factory function to create a SimulationProvenance object by automatically hashing inputs and outputs.
    """
    if known_limitations is None:
        known_limitations = []

    return SimulationProvenance(
        model_family=model_family,
        model_version=model_version,
        parameter_hash=compute_hash(params),
        solver_version=solver_version,
        input_hash=compute_hash(inputs),
        validation_state=validation_state,
        correlation_error=correlation_error,
        known_limitations=known_limitations,
        result_hash=compute_hash(results),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class PhysicsObservability:
    """
    Structured Physics Observability Record (Step 9 & Rule 12).
    Captures complete numerical solver telemetry, execution characteristics,
    physical boundary violations, and validation confidence.
    """
    solver: str
    backend: str
    iterations: int
    convergence: bool
    execution_time_s: float
    model_version: str
    fallback_triggered: bool = False
    fallback_from_backend: str = "none"
    fallback_to_backend: str = "none"
    fallback_reason: str = "none"
    contact_loss: bool = False
    out_of_domain: bool = False
    nan_inf: bool = False
    validation_status: str = "unvalidated"
    validation_score: Optional[float] = None
    input_dataset: str = "default_road_profile"
    parameter_version: str = "1.0.0"
    software_build: str = "suspensionlab-pro-v3.2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "solver": self.solver,
            "backend": self.backend,
            "iterations": self.iterations,
            "convergence": self.convergence,
            "execution_time_s": self.execution_time_s,
            "model_version": self.model_version,
            "fallback": {
                "triggered": self.fallback_triggered,
                "from_backend": self.fallback_from_backend,
                "to_backend": self.fallback_to_backend,
                "reason": self.fallback_reason,
            },
            "contact_loss": self.contact_loss,
            "out_of_domain": self.out_of_domain,
            "nan_inf": self.nan_inf,
            "validation": {
                "status": self.validation_status,
                "score": self.validation_score,
            },
            "provenance_identity": {
                "model_version": self.model_version,
                "solver": self.solver,
                "backend": self.backend,
                "input_dataset": self.input_dataset,
                "parameter_version": self.parameter_version,
                "software_build": self.software_build,
            },
        }

