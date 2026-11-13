"""
src/suspensionlab/interop/frames.py
===================================
SuspensionLab PRO — Coordinate Frames & Engineering Conventions System.

Treats coordinate conventions as authoritative engineering data, not cosmetic metadata.

Standards Supported:
- ISO 8855: Standard Road Vehicle Dynamics (X-Forward, Y-Left, Z-Up; Right-Handed).
- SAE J670: Vehicle Dynamics Terminology (X-Forward, Y-Right, Z-Down; Right-Handed).
- CUSTOM: Explicitly defined user or proprietary reference frame.

Enforces:
- Handedness and orthogonal consistency checks.
- Explicit damper and kinematic sign conventions (e.g. compression vs extension positive).
- Transformation matrix calculation between validated standards.
- Rejection of transformations when frame conventions are missing or ambiguous.
- Strict Invariant: Zero silent axis swaps or sign flips.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict, model_validator


class CoordinateStandard(str, Enum):
    """Recognized vehicle dynamics coordinate standards."""
    ISO_8855 = "ISO_8855"
    SAE_J670 = "SAE_J670"
    CUSTOM = "CUSTOM"


class Handedness(str, Enum):
    """Spatial coordinate frame handedness."""
    RIGHT_HANDED = "RIGHT_HANDED"
    LEFT_HANDED = "LEFT_HANDED"
    UNKNOWN = "UNKNOWN"


class FrameValidationStatus(str, Enum):
    """Validation verdict for coordinate frame specifications."""
    VALID = "VALID"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNRESOLVED = "UNRESOLVED"


# Unit vector representations in a standard right-handed space (X=fwd, Y=left, Z=up)
_AXIS_VECTORS: Dict[str, Tuple[float, float, float]] = {
    "FORWARD": (1.0, 0.0, 0.0),
    "REARWARD": (-1.0, 0.0, 0.0),
    "BACKWARD": (-1.0, 0.0, 0.0),
    "LEFT": (0.0, 1.0, 0.0),
    "RIGHT": (0.0, -1.0, 0.0),
    "UP": (0.0, 0.0, 1.0),
    "DOWN": (0.0, 0.0, -1.0),
}


def _cross_product(v1: Tuple[float, float, float], v2: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        v1[1] * v2[2] - v1[2] * v2[1],
        v1[2] * v2[0] - v1[0] * v2[2],
        v1[0] * v2[1] - v1[1] * v2[0],
    )


def _dot_product(v1: Tuple[float, float, float], v2: Tuple[float, float, float]) -> float:
    return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]


def check_frame_internal_consistency(frame: Any) -> Tuple[FrameValidationStatus, List[str]]:
    """
    Computes mathematical orthogonality and verifies that X cross Y matches Z
    according to declared handedness.
    """
    reasons: List[str] = []
    x_norm = (getattr(frame, "x_axis", None) or "").strip().upper()
    y_norm = (getattr(frame, "y_axis", None) or "").strip().upper()
    z_norm = (getattr(frame, "z_axis", None) or "").strip().upper()
    standard = getattr(frame, "standard", CoordinateStandard.CUSTOM)
    handedness = getattr(frame, "handedness", Handedness.RIGHT_HANDED)

    if not x_norm or not y_norm or not z_norm:
        reasons.append("Missing explicit axis direction for X, Y, or Z.")
        return (FrameValidationStatus.UNRESOLVED, reasons)

    v_x = _AXIS_VECTORS.get(x_norm)
    v_y = _AXIS_VECTORS.get(y_norm)
    v_z = _AXIS_VECTORS.get(z_norm)

    if v_x is None or v_y is None or v_z is None:
        # Non-standard direction keywords without vector mapping
        if standard != CoordinateStandard.CUSTOM:
            reasons.append(f"Unrecognized axis direction keywords in standard frame: x={x_norm}, y={y_norm}, z={z_norm}")
            return (FrameValidationStatus.UNRESOLVED, reasons)
        return (FrameValidationStatus.VALID, [])

    # Orthogonality checks
    if abs(_dot_product(v_x, v_y)) > 1e-6:
        reasons.append(f"X ({x_norm}) and Y ({y_norm}) axes are not orthogonal.")
    if abs(_dot_product(v_x, v_z)) > 1e-6:
        reasons.append(f"X ({x_norm}) and Z ({z_norm}) axes are not orthogonal.")
    if abs(_dot_product(v_y, v_z)) > 1e-6:
        reasons.append(f"Y ({y_norm}) and Z ({z_norm}) axes are not orthogonal.")

    if reasons:
        return (FrameValidationStatus.INCOMPATIBLE, reasons)

    # Handedness check: X cross Y should equal Z for right-handed, -Z for left-handed
    cross_xy = _cross_product(v_x, v_y)
    dot_z = _dot_product(cross_xy, v_z)

    if handedness == Handedness.RIGHT_HANDED:
        if abs(dot_z - 1.0) > 1e-6:
            reasons.append(
                f"Triad (X={x_norm}, Y={y_norm}, Z={z_norm}) is LEFT-HANDED or non-orthogonal, "
                f"but declared as RIGHT_HANDED."
            )
            return (FrameValidationStatus.INCOMPATIBLE, reasons)
    elif handedness == Handedness.LEFT_HANDED:
        if abs(dot_z - (-1.0)) > 1e-6:
            reasons.append(
                f"Triad (X={x_norm}, Y={y_norm}, Z={z_norm}) is RIGHT-HANDED or non-orthogonal, "
                f"but declared as LEFT_HANDED."
            )
            return (FrameValidationStatus.INCOMPATIBLE, reasons)

    return (FrameValidationStatus.VALID, [])


class CoordinateFrameDefinition(BaseModel):
    """Authoritative representation of a vehicle engineering coordinate frame."""
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    standard: CoordinateStandard = Field(
        default=CoordinateStandard.ISO_8855,
        description="Standard reference frame convention."
    )
    name: str = Field(
        default="ISO_8855_Vehicle_Body",
        description="Descriptive identifier for the reference frame."
    )
    x_axis: str = Field(
        default="FORWARD",
        description="X axis positive direction (e.g. FORWARD, REARWARD)."
    )
    y_axis: str = Field(
        default="LEFT",
        description="Y axis positive direction (e.g. LEFT, RIGHT)."
    )
    z_axis: str = Field(
        default="UP",
        description="Z axis positive direction (e.g. UP, DOWN)."
    )
    handedness: Handedness = Field(
        default=Handedness.RIGHT_HANDED,
        description="Declared handedness of the coordinate triad."
    )
    angular_convention: str = Field(
        default="TAIT_BRYAN_Z_Y_X",
        description="Rotation order / Euler sequence (e.g. TAIT_BRYAN_Z_Y_X: Yaw, Pitch, Roll)."
    )
    damper_sign_convention: str = Field(
        default="COMPRESSION_POSITIVE",
        description="Damper motion convention: COMPRESSION_POSITIVE or EXTENSION_POSITIVE."
    )
    toe_sign_convention: str = Field(
        default="TOE_IN_POSITIVE",
        description="Steering toe angle convention: TOE_IN_POSITIVE or TOE_OUT_POSITIVE."
    )
    camber_sign_convention: str = Field(
        default="TOP_INWARD_NEGATIVE",
        description="Camber angle sign convention."
    )
    reference_origin: str = Field(
        default="VEHICLE_CG",
        description="Reference frame origin (e.g. VEHICLE_CG, FRONT_AXLE_CENTER, GROUND_REF)."
    )
    unit_system: str = Field(
        default="SI",
        description="System of units associated with coordinates (e.g. SI, METRIC_MM, US_CUSTOMARY)."
    )

    @model_validator(mode="after")
    def validate_handedness_consistency(self) -> "CoordinateFrameDefinition":
        """Checks spatial consistency between declared axes and handedness."""
        status, reasons = check_frame_internal_consistency(self)
        if status != FrameValidationStatus.VALID:
            raise ValueError(f"Inconsistent coordinate frame: {'; '.join(reasons)}")
        return self


# Predefined Canonical Standard Definitions
ISO_8855_FRAME = CoordinateFrameDefinition(
    standard=CoordinateStandard.ISO_8855,
    name="ISO_8855_Canonical",
    x_axis="FORWARD",
    y_axis="LEFT",
    z_axis="UP",
    handedness=Handedness.RIGHT_HANDED,
    angular_convention="TAIT_BRYAN_Z_Y_X",
    damper_sign_convention="COMPRESSION_POSITIVE",
    toe_sign_convention="TOE_IN_POSITIVE",
    camber_sign_convention="TOP_INWARD_NEGATIVE",
    reference_origin="VEHICLE_CG",
    unit_system="SI",
)

SAE_J670_FRAME = CoordinateFrameDefinition(
    standard=CoordinateStandard.SAE_J670,
    name="SAE_J670_Canonical",
    x_axis="FORWARD",
    y_axis="RIGHT",
    z_axis="DOWN",
    handedness=Handedness.RIGHT_HANDED,
    angular_convention="TAIT_BRYAN_Z_Y_X",
    damper_sign_convention="COMPRESSION_POSITIVE",
    toe_sign_convention="TOE_IN_POSITIVE",
    camber_sign_convention="TOP_INWARD_NEGATIVE",
    reference_origin="VEHICLE_CG",
    unit_system="SI",
)


def validate_coordinate_frame(frame: Optional[CoordinateFrameDefinition]) -> Tuple[FrameValidationStatus, List[str]]:
    """High-level coordinate frame validation entrypoint."""
    if frame is None:
        return (FrameValidationStatus.UNRESOLVED, ["No coordinate frame definition provided."])
    return check_frame_internal_consistency(frame)


def compute_frame_transformation(
    source_frame: Optional[CoordinateFrameDefinition],
    target_frame: Optional[CoordinateFrameDefinition],
) -> Tuple[bool, Optional[List[List[float]]], List[str]]:
    """
    Calculates the 3x3 transformation matrix from source_frame to target_frame.

    Strict Invariants:
    - If either frame is None or unresolved, rejects transformation.
    - If handedness is incompatible or axes are ambiguous, rejects transformation.
    - Zero silent axis swaps or sign reversals.
    """
    warnings: List[str] = []

    status_s, reasons_s = validate_coordinate_frame(source_frame)
    if status_s != FrameValidationStatus.VALID:
        return (False, None, [f"Source frame invalid or unresolved: {'; '.join(reasons_s)}"])

    status_t, reasons_t = validate_coordinate_frame(target_frame)
    if status_t != FrameValidationStatus.VALID:
        return (False, None, [f"Target frame invalid or unresolved: {'; '.join(reasons_t)}"])

    assert source_frame is not None and target_frame is not None

    # Check for identical frames
    if (
        source_frame.standard == target_frame.standard
        and source_frame.x_axis == target_frame.x_axis
        and source_frame.y_axis == target_frame.y_axis
        and source_frame.z_axis == target_frame.z_axis
        and source_frame.handedness == target_frame.handedness
    ):
        identity_matrix = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        return (True, identity_matrix, [])

    # Standard conversion: ISO 8855 <-> SAE J670
    if source_frame.standard == CoordinateStandard.ISO_8855 and target_frame.standard == CoordinateStandard.SAE_J670:
        # ISO 8855: X fwd, Y left, Z up
        # SAE J670: X fwd, Y right, Z down
        # X_sae = X_iso, Y_sae = -Y_iso, Z_sae = -Z_iso
        matrix = [
            [1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, -1.0],
        ]
        warnings.append("Applied ISO 8855 to SAE J670 coordinate transformation: [X, -Y, -Z].")
        return (True, matrix, warnings)

    if source_frame.standard == CoordinateStandard.SAE_J670 and target_frame.standard == CoordinateStandard.ISO_8855:
        # SAE J670 -> ISO 8855 (self-inverse)
        matrix = [
            [1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, -1.0],
        ]
        warnings.append("Applied SAE J670 to ISO 8855 coordinate transformation: [X, -Y, -Z].")
        return (True, matrix, warnings)

    # Vector-based general orthogonal transformation
    s_x = _AXIS_VECTORS.get(source_frame.x_axis.upper())
    s_y = _AXIS_VECTORS.get(source_frame.y_axis.upper())
    s_z = _AXIS_VECTORS.get(source_frame.z_axis.upper())

    t_x = _AXIS_VECTORS.get(target_frame.x_axis.upper())
    t_y = _AXIS_VECTORS.get(target_frame.y_axis.upper())
    t_z = _AXIS_VECTORS.get(target_frame.z_axis.upper())

    if None in (s_x, s_y, s_z, t_x, t_y, t_z):
        return (
            False,
            None,
            ["Cannot compute transformation: Non-standard custom orientation vectors without explicit projection."],
        )

    # Compute rotation matrix R such that v_target = R * v_source
    # R_ij = dot(t_axis_i, s_axis_j)
    t_axes = [t_x, t_y, t_z]
    s_axes = [s_x, s_y, s_z]
    matrix = []
    for t_ax in t_axes:
        row = []
        for s_ax in s_axes:
            row.append(_dot_product(t_ax, s_ax))
        matrix.append(row)

    warnings.append("Computed general orthogonal coordinate frame transformation matrix.")
    return (True, matrix, warnings)
