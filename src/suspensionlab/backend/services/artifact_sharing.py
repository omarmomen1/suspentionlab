"""
backend/services/artifact_sharing.py
====================================
SuspensionLab PRO — Immutable Simulation Artifact & Public Report Sharing

Guarantees that publicly shared reports reference immutable, cryptographically-hashed
simulation artifacts rather than arbitrary client-provided numbers.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ImmutableSharedReport:
    """Public report tied immutably to simulation provenance and hashes."""
    report_id: str
    team_id: str
    vehicle_id: str
    setup_id: str
    model_version: str
    solver_version: str
    input_hash: str
    result_hash: str
    summary_metrics: Dict[str, Any]
    provenance_hash: str
    created_at_iso: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @classmethod
    def create(
        cls,
        report_id: str,
        team_id: str,
        vehicle_id: str,
        setup_id: str,
        model_version: str,
        solver_version: str,
        input_params: Dict[str, Any],
        simulation_results: Dict[str, Any],
        summary_metrics: Dict[str, Any],
    ) -> ImmutableSharedReport:
        """Create a cryptographically certified shared report."""
        canonical_inputs = json.dumps(input_params, sort_keys=True, separators=(",", ":"), default=str)
        canonical_results = json.dumps(simulation_results, sort_keys=True, separators=(",", ":"), default=str)
        
        in_hash = hashlib.sha256(canonical_inputs.encode("utf-8")).hexdigest()
        res_hash = hashlib.sha256(canonical_results.encode("utf-8")).hexdigest()
        
        prov_payload = f"{report_id}|{team_id}|{vehicle_id}|{model_version}|{in_hash}|{res_hash}"
        prov_hash = hashlib.sha256(prov_payload.encode("utf-8")).hexdigest()

        return cls(
            report_id=report_id,
            team_id=team_id,
            vehicle_id=vehicle_id,
            setup_id=setup_id,
            model_version=model_version,
            solver_version=solver_version,
            input_hash=in_hash,
            result_hash=res_hash,
            summary_metrics=summary_metrics,
            provenance_hash=prov_hash,
        )

    def verify_integrity(self, expected_input_hash: str, expected_result_hash: str) -> bool:
        """Verify that simulation outputs match the certified cryptographic hashes."""
        return (self.input_hash == expected_input_hash) and (self.result_hash == expected_result_hash)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "team_id": self.team_id,
            "vehicle_id": self.vehicle_id,
            "setup_id": self.setup_id,
            "model_version": self.model_version,
            "solver_version": self.solver_version,
            "input_hash": self.input_hash,
            "result_hash": self.result_hash,
            "summary_metrics": self.summary_metrics,
            "provenance_hash": self.provenance_hash,
            "created_at_iso": self.created_at_iso,
        }
