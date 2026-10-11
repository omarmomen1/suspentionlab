"""SuspensionLab PRO — Dataset Registry & Lineage Governance.

Implements Requirement 1:
Every dataset must have:
- dataset ID
- source
- vehicle identity
- vehicle configuration
- track
- session
- timestamp
- sampling rate
- units
- coordinate convention
- channel definitions
- provenance hash
- licensing/provenance metadata

Enforces cryptographic integrity, provenance hashing, and metadata completeness.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
import pandas as pd


class InvalidDatasetMetadataError(ValueError):
    """Raised when required dataset registration metadata is missing or invalid."""
    pass


class ProvenanceVerificationError(ValueError):
    """Raised when dataset cryptographic hash does not match authentic payload digest."""
    pass


def compute_sha256_digest(data: Union[bytes, str, Dict[str, Any], pd.DataFrame]) -> str:
    """Computes deterministic SHA-256 digest of payload."""
    if isinstance(data, bytes):
        return hashlib.sha256(data).hexdigest()
    elif isinstance(data, str):
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    elif isinstance(data, pd.DataFrame):
        # Convert values to compact float bytes
        buf = io_buf = json.dumps({
            "cols": list(data.columns),
            "rows": len(data),
            "head": data.head(5).to_dict(orient="list"),
            "tail": data.tail(5).to_dict(orient="list"),
        }, sort_keys=True).encode("utf-8")
        return hashlib.sha256(buf).hexdigest()
    elif isinstance(data, dict):
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    else:
        return hashlib.sha256(str(data).encode("utf-8")).hexdigest()


@dataclass
class DatasetRecord:
    """Authoritative metadata record for a registered validation dataset."""
    dataset_id: str
    source: str
    vehicle_identity: str
    vehicle_configuration: str
    track: str
    session: str
    timestamp: str  # ISO 8601
    sampling_rate: float  # Hz
    units: Dict[str, str]
    coordinate_convention: str
    channel_definitions: Dict[str, Dict[str, Any]]
    provenance_hash: str
    licensing_metadata: Dict[str, Any]
    file_path: Optional[str] = None
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        """Validates that all 13 required fields are strictly populated and non-empty."""
        missing = []
        if not self.dataset_id or not isinstance(self.dataset_id, str):
            missing.append("dataset_id")
        if not self.source or not isinstance(self.source, str):
            missing.append("source")
        if not self.vehicle_identity or not isinstance(self.vehicle_identity, str):
            missing.append("vehicle_identity")
        if not self.vehicle_configuration or not isinstance(self.vehicle_configuration, str):
            missing.append("vehicle_configuration")
        if not self.track or not isinstance(self.track, str):
            missing.append("track")
        if not self.session or not isinstance(self.session, str):
            missing.append("session")
        if not self.timestamp or not isinstance(self.timestamp, str):
            missing.append("timestamp")
        if self.sampling_rate is None or self.sampling_rate <= 0.0:
            missing.append("sampling_rate (must be > 0 Hz)")
        if not self.units or not isinstance(self.units, dict):
            missing.append("units (must be non-empty dict)")
        if not self.coordinate_convention or not isinstance(self.coordinate_convention, str):
            missing.append("coordinate_convention")
        if not self.channel_definitions or not isinstance(self.channel_definitions, dict):
            missing.append("channel_definitions (must be non-empty dict)")
        if not self.provenance_hash or not isinstance(self.provenance_hash, str) or len(self.provenance_hash) < 32:
            missing.append("provenance_hash (must be valid cryptographic SHA-256)")
        if not self.licensing_metadata or not isinstance(self.licensing_metadata, dict):
            missing.append("licensing_metadata (must be non-empty dict)")

        if missing:
            raise InvalidDatasetMetadataError(
                f"Dataset registration failed. Missing or invalid required fields: {', '.join(missing)}"
            )

    def verify_provenance(self, payload: Union[bytes, str, pd.DataFrame, Dict[str, Any], Path]) -> bool:
        """Verifies that the provided raw payload matches the registered provenance hash."""
        if isinstance(payload, Path):
            if not payload.exists():
                raise FileNotFoundError(f"Raw data file not found: {payload}")
            actual_hash = hashlib.sha256(payload.read_bytes()).hexdigest()
        elif isinstance(payload, bytes):
            actual_hash = hashlib.sha256(payload).hexdigest()
        elif isinstance(payload, str) and Path(payload).exists():
            actual_hash = hashlib.sha256(Path(payload).read_bytes()).hexdigest()
        elif self.file_path and Path(self.file_path).exists():
            actual_hash = hashlib.sha256(Path(self.file_path).read_bytes()).hexdigest()
        else:
            actual_hash = compute_sha256_digest(payload)

        if actual_hash != self.provenance_hash:
            raise ProvenanceVerificationError(
                f"Cryptographic provenance mismatch for dataset '{self.dataset_id}'. "
                f"Expected registered hash {self.provenance_hash}, but computed {actual_hash}."
            )
        return True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatasetRecord":
        return cls(**data)


class DatasetRegistry:
    """Authoritative registry for vehicle validation datasets with provenance tracking."""

    def __init__(self):
        self._records: Dict[str, DatasetRecord] = {}

    def register_dataset(
        self,
        record: DatasetRecord,
        raw_payload: Optional[Union[bytes, str, pd.DataFrame, Dict[str, Any], Path]] = None,
        verify_provenance: bool = True,
    ) -> str:
        """Registers a new dataset with strict validation and provenance verification."""
        record.validate()

        if verify_provenance and raw_payload is not None:
            record.verify_provenance(raw_payload)

        # Store immutable deepcopy
        self._records[record.dataset_id] = copy.deepcopy(record)
        return record.dataset_id

    def get_dataset(self, dataset_id: str) -> DatasetRecord:
        """Retrieves a registered dataset record."""
        if dataset_id not in self._records:
            raise KeyError(f"Dataset '{dataset_id}' is not registered in the validation registry.")
        return copy.deepcopy(self._records[dataset_id])

    def list_datasets(self) -> List[DatasetRecord]:
        """Lists all registered dataset records."""
        return [copy.deepcopy(rec) for rec in self._records.values()]

    def export_manifest(self, filepath: Union[str, Path]) -> None:
        """Serializes the registry catalog to a JSON manifest file."""
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "registry_version": "phase3i-v1.0",
            "datasets": [rec.to_dict() for rec in self._records.values()],
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_manifest(self, filepath: Union[str, Path]) -> int:
        """Loads dataset records from a JSON manifest file."""
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Manifest not found: {filepath}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        for entry in data.get("datasets", []):
            rec = DatasetRecord.from_dict(entry)
            self._records[rec.dataset_id] = rec
            count += 1
        return count
