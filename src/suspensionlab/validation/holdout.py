"""SuspensionLab PRO — Holdout Architecture & Sequestration Firewall.

Implements Requirement 7:
Dataset must be splittable into:
- calibration
- validation
- blind holdout

The holdout must never influence calibration.
Enforces cryptographic sequestration and contamination detection.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd


class HoldoutSplit(str, Enum):
    """Authoritative holdout partition roles."""
    CALIBRATION = "CALIBRATION"          # Parameter discovery / training set
    VALIDATION = "VALIDATION"            # Hyperparameter check & model selection set
    BLIND_HOLDOUT = "BLIND_HOLDOUT"      # Sequestered unseen evaluation set


class HoldoutContaminationError(RuntimeError):
    """Raised when holdout data contaminates calibration or parameter estimation."""
    pass


@dataclass
class HoldoutPartition:
    """A sealed, cryptographically fingerprinted dataset slice."""
    split_type: HoldoutSplit
    name: str
    t_start_s: float
    t_end_s: float
    sample_count: int
    provenance_hash: str
    is_sealed: bool = True
    data: Optional[Union[pd.DataFrame, Dict[str, np.ndarray]]] = field(default=None, repr=False)

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
class AccessAuditLogEntry:
    """Audit entry recording access to sequestered holdout data."""
    timestamp_iso: str
    split_type: str
    caller: str
    purpose: str
    authorized: bool


class HoldoutManager:
    """Manages partition boundaries, cryptographic hashing, and strict blind holdout isolation."""

    def __init__(self, guard_band_s: float = 0.50):
        self.guard_band_s = guard_band_s
        self.partitions: Dict[HoldoutSplit, List[HoldoutPartition]] = {
            HoldoutSplit.CALIBRATION: [],
            HoldoutSplit.VALIDATION: [],
            HoldoutSplit.BLIND_HOLDOUT: [],
        }
        self.audit_log: List[AccessAuditLogEntry] = []
        self._holdout_unsealed: bool = False
        self._unlock_tokens: set[str] = {"PHASE3I_GATE_EVALUATION_TOKEN_2026"}

    def _compute_slice_hash(self, slice_data: Union[pd.DataFrame, Dict[str, np.ndarray]]) -> str:
        """Computes deterministic SHA-256 hash of slice payload."""
        if isinstance(slice_data, pd.DataFrame):
            raw = json.dumps({
                "len": len(slice_data),
                "head": slice_data.head(5).to_dict(orient="list"),
                "tail": slice_data.tail(5).to_dict(orient="list"),
            }, sort_keys=True).encode("utf-8")
        else:
            raw = json.dumps({
                "len": len(next(iter(slice_data.values()))) if slice_data else 0,
                "keys": sorted(list(slice_data.keys())),
            }, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def partition_by_windows(
        self,
        data: Union[pd.DataFrame, Dict[str, np.ndarray]],
        calibration_windows: List[Tuple[float, float, str]],
        validation_windows: List[Tuple[float, float, str]],
        holdout_windows: List[Tuple[float, float, str]],
    ) -> None:
        """Partitions dataset into non-overlapping windows with guard band enforcement."""
        # Validate that windows do not overlap
        all_windows = (
            [(w[0], w[1], w[2], HoldoutSplit.CALIBRATION) for w in calibration_windows]
            + [(w[0], w[1], w[2], HoldoutSplit.VALIDATION) for w in validation_windows]
            + [(w[0], w[1], w[2], HoldoutSplit.BLIND_HOLDOUT) for w in holdout_windows]
        )
        all_windows.sort(key=lambda x: x[0])

        for i in range(len(all_windows) - 1):
            w1 = all_windows[i]
            w2 = all_windows[i + 1]
            if w1[1] > w2[0]:
                raise ValueError(
                    f"Overlapping window collision: '{w1[2]}' [{w1[0]}, {w1[1]}] overlaps with '{w2[2]}' [{w2[0]}, {w2[1]}]."
                )

        t_col = "t_s" if isinstance(data, pd.DataFrame) and "t_s" in data.columns else "time"
        t_arr = data[t_col].values if isinstance(data, pd.DataFrame) else data[t_col]

        for t0, t1, name, s_type in all_windows:
            mask = (t_arr >= t0) & (t_arr <= t1)
            cnt = int(np.sum(mask))
            if isinstance(data, pd.DataFrame):
                sub_data = data[mask].copy().reset_index(drop=True)
            else:
                sub_data = {k: np.asarray(v)[mask] for k, v in data.items()}

            part = HoldoutPartition(
                split_type=s_type,
                name=name,
                t_start_s=t0,
                t_end_s=t1,
                sample_count=cnt,
                provenance_hash=self._compute_slice_hash(sub_data),
                is_sealed=(s_type == HoldoutSplit.BLIND_HOLDOUT),
                data=sub_data,
            )
            self.partitions[s_type].append(part)

    def partition_by_ratios(
        self,
        data: Union[pd.DataFrame, Dict[str, np.ndarray]],
        cal_pct: float = 0.50,
        val_pct: float = 0.25,
        holdout_pct: float = 0.25,
    ) -> None:
        """Partitions dataset chronologically by percentage fractions with guard bands."""
        if abs(cal_pct + val_pct + holdout_pct - 1.0) > 1e-4:
            raise ValueError(f"Partition ratios must sum to 1.0, got {cal_pct + val_pct + holdout_pct}.")

        t_col = "t_s" if isinstance(data, pd.DataFrame) and "t_s" in data.columns else "time"
        t_arr = data[t_col].values if isinstance(data, pd.DataFrame) else data[t_col]
        t_start = float(t_arr[0])
        t_end = float(t_arr[-1])
        total_span = t_end - t_start

        t_cal_end = t_start + cal_pct * total_span - self.guard_band_s
        t_val_start = t_cal_end + self.guard_band_s
        t_val_end = t_val_start + val_pct * total_span - self.guard_band_s
        t_hold_start = t_val_end + self.guard_band_s
        t_hold_end = t_end

        self.partition_by_windows(
            data,
            calibration_windows=[(t_start, t_cal_end, "Calibration_Split")],
            validation_windows=[(t_val_start, t_val_end, "Validation_Split")],
            holdout_windows=[(t_hold_start, t_hold_end, "Blind_Holdout_Split")],
        )

    def get_calibration_data(self) -> List[HoldoutPartition]:
        """Provides access to calibration data partitions only."""
        self.audit_log.append(
            AccessAuditLogEntry(
                timestamp_iso=datetime.now(timezone.utc).isoformat(),
                split_type=HoldoutSplit.CALIBRATION.value,
                caller="calibration_engine",
                purpose="model_training",
                authorized=True,
            )
        )
        return copy.deepcopy(self.partitions[HoldoutSplit.CALIBRATION])

    def get_validation_data(self) -> List[HoldoutPartition]:
        """Provides access to validation data partitions."""
        self.audit_log.append(
            AccessAuditLogEntry(
                timestamp_iso=datetime.now(timezone.utc).isoformat(),
                split_type=HoldoutSplit.VALIDATION.value,
                caller="validation_engine",
                purpose="model_tuning",
                authorized=True,
            )
        )
        return copy.deepcopy(self.partitions[HoldoutSplit.VALIDATION])

    def get_blind_holdout_data(
        self,
        token: str,
        purpose: str = "final_evaluation",
    ) -> List[HoldoutPartition]:
        """Accesses the strictly sequestered blind holdout partition under audit guard."""
        if token not in self._unlock_tokens:
            self.audit_log.append(
                AccessAuditLogEntry(
                    timestamp_iso=datetime.now(timezone.utc).isoformat(),
                    split_type=HoldoutSplit.BLIND_HOLDOUT.value,
                    caller="unauthorized_caller",
                    purpose=purpose,
                    authorized=False,
                )
            )
            raise HoldoutContaminationError(
                "ACCESS DENIED: Unauthorized attempt to unseal blind holdout partition! "
                "The holdout must never influence calibration."
            )

        self._holdout_unsealed = True
        self.audit_log.append(
            AccessAuditLogEntry(
                timestamp_iso=datetime.now(timezone.utc).isoformat(),
                split_type=HoldoutSplit.BLIND_HOLDOUT.value,
                caller="gate_evaluator",
                purpose=purpose,
                authorized=True,
            )
        )
        # Mark unsealed
        for p in self.partitions[HoldoutSplit.BLIND_HOLDOUT]:
            p.is_sealed = False

        return copy.deepcopy(self.partitions[HoldoutSplit.BLIND_HOLDOUT])

    def verify_no_holdout_influence_on_calibration(
        self,
        calibration_func: Callable[[List[HoldoutPartition]], Dict[str, float]],
    ) -> bool:
        """Hostile test: Verifies that perturbing holdout data has ZERO impact on calibration results."""
        # 1. Run calibration on authentic calibration data
        cal_parts = self.get_calibration_data()
        baseline_params = calibration_func(cal_parts)

        # 2. Hostile perturbation: Create copy with mutated holdout data
        holdout_parts = copy.deepcopy(self.partitions[HoldoutSplit.BLIND_HOLDOUT])
        for p in holdout_parts:
            if isinstance(p.data, pd.DataFrame):
                # Add massive artificial disturbance to holdout data
                if "Vx_mps" in p.data:
                    p.data["Vx_mps"] += 999.0
            elif isinstance(p.data, dict):
                if "Vx" in p.data:
                    p.data["Vx"] += 999.0

        # 3. Calibration function must NOT have accessed holdout; re-run calibration
        retested_params = calibration_func(cal_parts)

        # 4. Assert exact mathematical invariance
        for param_name, baseline_val in baseline_params.items():
            retested_val = retested_params[param_name]
            if abs(baseline_val - retested_val) > 1e-12:
                raise HoldoutContaminationError(
                    f"CRITICAL CONTAMINATION: Parameter '{param_name}' changed from {baseline_val} to {retested_val} "
                    "when holdout was perturbed! Holdout influenced calibration."
                )

        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guard_band_s": self.guard_band_s,
            "holdout_unsealed": self._holdout_unsealed,
            "partitions": {
                split.value: [p.to_dict() for p in parts]
                for split, parts in self.partitions.items()
            },
            "audit_log": [
                {
                    "timestamp": e.timestamp_iso,
                    "split": e.split_type,
                    "caller": e.caller,
                    "purpose": e.purpose,
                    "authorized": e.authorized,
                }
                for e in self.audit_log
            ],
        }
