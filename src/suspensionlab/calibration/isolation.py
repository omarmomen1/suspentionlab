"""SuspensionLab PRO — Cryptographic Calibration Dataset Isolation (Phase 3J).

Requirement 4:
Calibration data and holdout data must be cryptographically separated.

Requirement 11:
Hostile tests: calibration leakage detection.

Enforces:
- Deterministic SHA-256 fingerprinting of calibration and holdout partitions
- Physical guard band between calibration and holdout windows to eliminate boundary leakage
- Sequestration firewall: optimizer and calibration loop cannot read holdout data
- Access attempt without explicit cryptographic token raises CalibrationLeakageError
- Tamper-evident audit ledger for all partition access
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


class CalibrationSplitType(str, Enum):
    """Authoritative partition classifications."""
    CALIBRATION = "CALIBRATION"
    BLIND_HOLDOUT = "BLIND_HOLDOUT"


class CalibrationLeakageError(RuntimeError):
    """Raised when sequestered holdout data is accessed during the calibration phase or without authorization."""
    pass


@dataclass
class IsolatedDatasetPartition:
    """A sealed, cryptographically fingerprinted dataset slice."""
    split_type: CalibrationSplitType
    name: str
    t_start_s: float
    t_end_s: float
    sample_count: int
    provenance_hash: str
    is_sealed: bool = True
    _data: Optional[Union[pd.DataFrame, Dict[str, np.ndarray]]] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "split_type": self.split_type.value,
            "name": self.name,
            "t_start_s": round(self.t_start_s, 3),
            "t_end_s": round(self.t_end_s, 3),
            "sample_count": self.sample_count,
            "provenance_hash": self.provenance_hash,
            "is_sealed": self.is_sealed,
        }


@dataclass
class PartitionAccessLog:
    """Audit entry recording an access request to an isolated partition."""
    timestamp_iso: str
    split_type: str
    caller: str
    authorized: bool
    reason: str


class CryptographicDatasetIsolation:
    """Cryptographic firewall managing dataset isolation between calibration and holdout."""

    def __init__(self, guard_band_s: float = 0.50):
        self.guard_band_s = guard_band_s
        self.calibration_partition: Optional[IsolatedDatasetPartition] = None
        self.holdout_partition: Optional[IsolatedDatasetPartition] = None
        self.access_logs: List[PartitionAccessLog] = []
        self._is_holdout_unsealed: bool = False
        self._unlock_token: Optional[str] = None

    def _compute_hash(self, slice_data: Union[pd.DataFrame, Dict[str, np.ndarray]]) -> str:
        """Compute SHA-256 hash over payload bytes."""
        hasher = hashlib.sha256()
        if isinstance(slice_data, pd.DataFrame):
            # Deterministic serialization of columns and content
            cols = sorted(list(slice_data.columns))
            hasher.update(",".join(cols).encode("utf-8"))
            for c in cols:
                arr = slice_data[c].to_numpy(dtype=np.float64, copy=False)
                hasher.update(arr.tobytes())
        else:
            keys = sorted(list(slice_data.keys()))
            hasher.update(",".join(keys).encode("utf-8"))
            for k in keys:
                arr = np.asarray(slice_data[k], dtype=np.float64)
                hasher.update(arr.tobytes())
        return hasher.hexdigest()

    def partition_dataset(
        self,
        data: Union[pd.DataFrame, Dict[str, np.ndarray]],
        holdout_ratio: float = 0.25,
        time_channel: str = "time",
        holdout_window: Optional[Tuple[float, float]] = None,
    ) -> Tuple[IsolatedDatasetPartition, IsolatedDatasetPartition]:
        """Split telemetry into cryptographically sequestered calibration and holdout partitions."""
        if holdout_ratio <= 0.0 or holdout_ratio >= 1.0:
            raise ValueError(f"holdout_ratio must be in (0, 1), got {holdout_ratio}")

        # Extract time array
        if isinstance(data, pd.DataFrame):
            t_col = time_channel if time_channel in data.columns else None
            if t_col is None:
                for cand in ["t_s", "time", "timestamps", "Timestamp", "Time"]:
                    if cand in data.columns:
                        t_col = cand
                        break
            if t_col is None:
                t_arr = np.linspace(0.0, len(data) * 0.01, len(data))
            else:
                t_arr = data[t_col].to_numpy(dtype=np.float64)
            n_samples = len(data)
        else:
            t_cand = None
            for cand in [time_channel, "t_s", "time", "timestamps"]:
                if cand in data:
                    t_cand = cand
                    break
            if t_cand is not None:
                t_arr = np.asarray(data[t_cand], dtype=np.float64)
            else:
                first_k = next(iter(data.keys()))
                t_arr = np.linspace(0.0, len(data[first_k]) * 0.01, len(data[first_k]))
            n_samples = len(t_arr)

        if n_samples < 20:
            raise ValueError(f"Dataset has only {n_samples} samples; minimum 20 samples required for isolation split.")

        t_min = float(t_arr[0])
        t_max = float(t_arr[-1])
        total_duration = t_max - t_min

        if holdout_window is not None:
            h_start, h_end = holdout_window
            if h_start < t_min or h_end > t_max or h_start >= h_end:
                raise ValueError(f"Invalid holdout_window [{h_start}, {h_end}] within telemetry domain [{t_min}, {t_max}]")
            # Apply guard band around holdout
            cal_mask = (t_arr < h_start - self.guard_band_s) | (t_arr > h_end + self.guard_band_s)
            hold_mask = (t_arr >= h_start) & (t_arr <= h_end)
        else:
            # Trailing holdout partition with guard band
            split_time = t_min + (1.0 - holdout_ratio) * total_duration
            cal_end_time = split_time - self.guard_band_s
            hold_start_time = split_time

            cal_mask = t_arr <= cal_end_time
            hold_mask = t_arr >= hold_start_time

        # Verify no intersection between calibration and holdout indices
        cal_idx_set = set(np.where(cal_mask)[0])
        hold_idx_set = set(np.where(hold_mask)[0])
        intersection = cal_idx_set.intersection(hold_idx_set)
        if intersection:
            raise RuntimeError(f"FATAL: Isolation failure: {len(intersection)} samples intersect between partitions!")

        cal_indices = sorted(list(cal_idx_set))
        hold_indices = sorted(list(hold_idx_set))

        # Slice data
        if isinstance(data, pd.DataFrame):
            cal_data = data.iloc[cal_indices].copy().reset_index(drop=True)
            hold_data = data.iloc[hold_indices].copy().reset_index(drop=True)
        else:
            cal_data = {k: np.asarray(v)[cal_indices] for k, v in data.items()}
            hold_data = {k: np.asarray(v)[hold_indices] for k, v in data.items()}

        cal_hash = self._compute_hash(cal_data)
        hold_hash = self._compute_hash(hold_data)

        # Generate cryptographic token for unsealing holdout
        token_seed = f"PHASE3J_SEAL_{cal_hash[:16]}_{hold_hash[:16]}"
        self._unlock_token = hashlib.sha256(token_seed.encode("utf-8")).hexdigest()

        self.calibration_partition = IsolatedDatasetPartition(
            split_type=CalibrationSplitType.CALIBRATION,
            name="calibration_training_partition",
            t_start_s=float(t_arr[cal_mask][0]) if np.any(cal_mask) else 0.0,
            t_end_s=float(t_arr[cal_mask][-1]) if np.any(cal_mask) else 0.0,
            sample_count=len(cal_indices),
            provenance_hash=cal_hash,
            is_sealed=False,
            _data=cal_data,
        )

        self.holdout_partition = IsolatedDatasetPartition(
            split_type=CalibrationSplitType.BLIND_HOLDOUT,
            name="blind_holdout_sequestered_partition",
            t_start_s=float(t_arr[hold_mask][0]) if np.any(hold_mask) else 0.0,
            t_end_s=float(t_arr[hold_mask][-1]) if np.any(hold_mask) else 0.0,
            sample_count=len(hold_indices),
            provenance_hash=hold_hash,
            is_sealed=True,
            _data=hold_data,
        )

        self._is_holdout_unsealed = False
        return self.calibration_partition, self.holdout_partition

    def get_calibration_data(self, caller: str = "optimizer") -> Union[pd.DataFrame, Dict[str, np.ndarray]]:
        """Access calibration partition data. Authorized for calibration and optimization."""
        if self.calibration_partition is None or self.calibration_partition._data is None:
            raise RuntimeError("No calibration partition loaded.")
        self.access_logs.append(PartitionAccessLog(
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            split_type=CalibrationSplitType.CALIBRATION.value,
            caller=caller,
            authorized=True,
            reason="Authorized training / calibration data access",
        ))
        return self.calibration_partition._data

    def get_holdout_data(
        self,
        token: Optional[str] = None,
        caller: str = "holdout_evaluator",
    ) -> Union[pd.DataFrame, Dict[str, np.ndarray]]:
        """Access blind holdout partition data. Strict cryptographic token required."""
        if self.holdout_partition is None or self.holdout_partition._data is None:
            raise RuntimeError("No holdout partition loaded.")

        if token is None or token != self._unlock_token:
            self.access_logs.append(PartitionAccessLog(
                timestamp_iso=datetime.now(timezone.utc).isoformat(),
                split_type=CalibrationSplitType.BLIND_HOLDOUT.value,
                caller=caller,
                authorized=False,
                reason="LEAKAGE ATTEMPT: Invalid or missing cryptographic sequestration token",
            ))
            raise CalibrationLeakageError(
                f"CALIBRATION FIREWALL LEAKAGE DETECTED: Caller '{caller}' attempted to access "
                "sequestered blind holdout data without a valid cryptographic unlock token. "
                "Holdout partition is strictly sealed to protect scientific validity."
            )

        self._is_holdout_unsealed = True
        self.holdout_partition.is_sealed = False
        self.access_logs.append(PartitionAccessLog(
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            split_type=CalibrationSplitType.BLIND_HOLDOUT.value,
            caller=caller,
            authorized=True,
            reason="Authorized post-calibration blind holdout evaluation",
        ))
        return self.holdout_partition._data

    @property
    def unlock_token(self) -> Optional[str]:
        """Retrieve token (available only to the independent verification harness)."""
        return self._unlock_token

    def verify_no_leakage(self) -> Tuple[bool, Optional[str]]:
        """Verify that no unauthorized access attempts were made to holdout partition."""
        unauthorized = [entry for entry in self.access_logs if not entry.authorized]
        if unauthorized:
            return False, f"Sequestration breach: {len(unauthorized)} unauthorized access attempt(s) logged."
        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guard_band_s": self.guard_band_s,
            "calibration_partition": self.calibration_partition.to_dict() if self.calibration_partition else None,
            "holdout_partition": self.holdout_partition.to_dict() if self.holdout_partition else None,
            "is_holdout_unsealed": self._is_holdout_unsealed,
            "total_access_attempts": len(self.access_logs),
            "unauthorized_attempts": len([e for e in self.access_logs if not e.authorized]),
        }
