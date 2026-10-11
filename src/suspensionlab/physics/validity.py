"""
physics/validity.py
===================
SuspensionLab PRO — Central Physics Validity & Provenance Engine

Establishes the authoritative validity lifecycle and provenance tracking
for all physics models and simulation results across SuspensionLab PRO.

Minimum Epistemic States:
- SIMULATION_ESTIMATE: Derived from uncalibrated forward physical simulation.
- MODEL_SUPPORTED: Configuration and inputs lie strictly within validated model assumptions.
- CORRELATED: Simulation outputs correlate with external benchmarks (R² >= 0.70).
- EMPIRICALLY_VALIDATED: Verified directly against authentic physical sensor measurements.
- UNSUPPORTED: Configuration violates model assumptions or physics domain boundaries.
- EXTRAPOLATED: Operating outside calibrated parameter envelope (e.g. RH < 20mm, high slip).
- NUMERICALLY_FAILED: Solver divergence, singular matrix, NaN/Inf, or line search failure.
- UNIDENTIFIABLE: Telemetry lacks observability/excitation to uniquely estimate parameters.

Governing Law:
A downstream module MUST NOT silently convert UNSUPPORTED or EXTRAPOLATED input
into MODEL_SUPPORTED or EMPIRICALLY_VALIDATED output.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


class PhysicsValidityStatus(str, Enum):
    """Authoritative physical and empirical validity status."""
    SIMULATION_ESTIMATE = "SIMULATION_ESTIMATE"
    MODEL_SUPPORTED = "MODEL_SUPPORTED"
    CORRELATED = "CORRELATED"
    EMPIRICALLY_VALIDATED = "EMPIRICALLY_VALIDATED"
    UNSUPPORTED = "UNSUPPORTED"
    EXTRAPOLATED = "EXTRAPOLATED"
    NUMERICALLY_FAILED = "NUMERICALLY_FAILED"
    UNIDENTIFIABLE = "UNIDENTIFIABLE"


# Precedence order: higher index = more degraded validity
_STATUS_DEGRADATION_TIER: Dict[PhysicsValidityStatus, int] = {
    PhysicsValidityStatus.EMPIRICALLY_VALIDATED: 0,
    PhysicsValidityStatus.CORRELATED: 1,
    PhysicsValidityStatus.MODEL_SUPPORTED: 2,
    PhysicsValidityStatus.SIMULATION_ESTIMATE: 3,
    PhysicsValidityStatus.EXTRAPOLATED: 4,
    PhysicsValidityStatus.UNIDENTIFIABLE: 5,
    PhysicsValidityStatus.UNSUPPORTED: 6,
    PhysicsValidityStatus.NUMERICALLY_FAILED: 7,
}


@dataclass
class PhysicsValidityRecord:
    """Central validity and provenance metadata attached to every physics result.

    Attributes
    ----------
    status                  : Current epistemic validity status.
    model                   : Subsystem/model identifier (e.g. "QuarterCar-2DOF-v2.4").
    assumptions             : List of explicit physical assumptions made by model.
    valid_parameter_domain  : Dict mapping parameter names to valid (min, max) bounds.
    extrapolation_status    : True if any parameter or state operated outside valid domain.
    validation_evidence     : Description of evidence supporting this result.
    data_provenance         : Provenance dictionary (hashes, sources, session IDs).
    warnings                : List of blocking or advisory engineering warnings.
    upstream_validity_state : Validity status inherited from input/upstream modules.
    """
    status: PhysicsValidityStatus = PhysicsValidityStatus.SIMULATION_ESTIMATE
    model: str = "QuarterCar-2DOF"
    assumptions: List[str] = field(default_factory=list)
    valid_parameter_domain: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    extrapolation_status: bool = False
    validation_evidence: str = "Theoretical forward model integration"
    data_provenance: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    upstream_validity_state: Optional[PhysicsValidityStatus] = None

    def __post_init__(self):
        # Enforce upstream inheritance guard immediately upon initialization
        if self.upstream_validity_state is not None:
            up_tier = _STATUS_DEGRADATION_TIER.get(self.upstream_validity_state, 3)
            curr_tier = _STATUS_DEGRADATION_TIER.get(self.status, 3)
            # If upstream is EXTRAPOLATED, UNSUPPORTED, NUMERICALLY_FAILED, or UNIDENTIFIABLE,
            # downstream status CANNOT be upgraded to MODEL_SUPPORTED or EMPIRICALLY_VALIDATED.
            if up_tier >= 4 and curr_tier < up_tier:
                self.warnings.append(
                    f"Inherited upstream degraded status '{self.upstream_validity_state.value}'; "
                    f"cannot claim '{self.status.value}'."
                )
                self.status = self.upstream_validity_state

    @property
    def is_valid(self) -> bool:
        """True if result is physically admissible and within supported model domain."""
        return self.status in (
            PhysicsValidityStatus.SIMULATION_ESTIMATE,
            PhysicsValidityStatus.MODEL_SUPPORTED,
            PhysicsValidityStatus.CORRELATED,
            PhysicsValidityStatus.EMPIRICALLY_VALIDATED,
        ) and not self.extrapolation_status

    def propagate_downstream(
        self,
        downstream_model: str,
        additional_assumptions: Optional[List[str]] = None,
        additional_warnings: Optional[List[str]] = None,
    ) -> "PhysicsValidityRecord":
        """Produce a downstream validity record preserving upstream degradation.

        A downstream module MUST NOT silently convert UNSUPPORTED or EXTRAPOLATED
        input into MODEL_SUPPORTED output.
        """
        new_assumptions = list(self.assumptions)
        if additional_assumptions:
            new_assumptions.extend(additional_assumptions)

        new_warnings = list(self.warnings)
        if additional_warnings:
            new_warnings.extend(additional_warnings)

        # Inherit degraded state if upstream is invalid/extrapolated
        if self.status in (
            PhysicsValidityStatus.UNSUPPORTED,
            PhysicsValidityStatus.EXTRAPOLATED,
            PhysicsValidityStatus.NUMERICALLY_FAILED,
            PhysicsValidityStatus.UNIDENTIFIABLE,
        ):
            downstream_status = self.status
            new_warnings.append(
                f"Downstream model '{downstream_model}' received {self.status.value} input; "
                "output validity is strictly degraded."
            )
        else:
            downstream_status = PhysicsValidityStatus.MODEL_SUPPORTED

        return PhysicsValidityRecord(
            status=downstream_status,
            model=downstream_model,
            assumptions=new_assumptions,
            valid_parameter_domain=copy.deepcopy(self.valid_parameter_domain),
            extrapolation_status=self.extrapolation_status,
            validation_evidence=f"Downstream of {self.model}: {self.validation_evidence}",
            data_provenance=copy.deepcopy(self.data_provenance),
            warnings=new_warnings,
            upstream_validity_state=self.status,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "is_valid": self.is_valid,
            "model": self.model,
            "assumptions": self.assumptions,
            "valid_parameter_domain": {
                k: [round(v[0], 4), round(v[1], 4)] for k, v in self.valid_parameter_domain.items()
            },
            "extrapolation_status": self.extrapolation_status,
            "validation_evidence": self.validation_evidence,
            "data_provenance": self.data_provenance,
            "warnings": self.warnings,
            "upstream_validity_state": (
                self.upstream_validity_state.value if self.upstream_validity_state else None
            ),
        }
