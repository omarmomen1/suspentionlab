"""
src/suspensionlab/interop/mapping.py
====================================
SuspensionLab PRO — Solver Interoperability Parameter Mapping Contract.

Defines the structured, auditable specification for mapping internal engineering
parameters to external solver variables and vice versa.

Core Principles:
- Authoritative Parameter Definitions: Maps to verified internal entity models.
- Auditable Provenance: Declares whether mapping comes from authoritative specification,
  vendor interface manual, user explicit configuration, or unverified heuristics.
- Strict Invariants:
    1. Zero name-similarity guessing: Similar strings (e.g. m_s vs m_u or speed vs wheel_speed)
       never establish equivalence.
    2. Explicit dimensional compatibility: Incompatible dimensions flag UNSUPPORTED.
    3. Ambiguous or unknown mappings return UNSUPPORTED / AMBIGUOUS rather than guessing.
    4. Internal parameters are authoritative and immutable.
"""
from __future__ import annotations

import difflib
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field, ConfigDict, model_validator

from suspensionlab.interop.units import (
    UnitCompatibilityStatus,
    check_unit_compatibility,
    get_physical_dimension,
)


class MappingProvenance(str, Enum):
    """Origin and authoritative backing of the parameter mapping."""
    AUTHORITATIVE_SPEC = "AUTHORITATIVE_SPEC"        # Defined in official engineering standard / vendor manual
    VENDOR_INTERFACE = "VENDOR_INTERFACE"            # Sourced from solver vendor API / data dictionary
    USER_EXPLICIT = "USER_EXPLICIT"                  # Explicitly defined by engineer in configuration
    UNVERIFIED_HEURISTIC = "UNVERIFIED_HEURISTIC"    # Textual or string-similarity guess (PROHIBITED FOR VALIDATION)


class MappingStatus(str, Enum):
    """Operational validation state of the parameter mapping."""
    VERIFIED = "VERIFIED"          # Authoritative, dimensionally verified, unit-checked
    SUPPORTED = "SUPPORTED"        # Fully supported with defined conversion
    UNSUPPORTED = "UNSUPPORTED"    # Parameter not supported or missing authoritative link
    AMBIGUOUS = "AMBIGUOUS"        # Multiple conflicting candidates or ambiguous coordinate frame
    UNRESOLVED = "UNRESOLVED"      # Missing unit or parameter path information


# Authoritative Internal Engineering Parameter Dictionary
# (entity_type -> {param_path: (unit, dimension, description)})
AUTHORITATIVE_INTERNAL_PARAMETERS: Dict[str, Dict[str, Tuple[str, str, str]]] = {
    "quarter_car": {
        "m_s": ("kg", "mass", "Quarter car sprung mass"),
        "m_u": ("kg", "mass", "Quarter car unsprung wheel assembly mass"),
        "k_s": ("N/m", "stiffness", "Suspension spring stiffness"),
        "c": ("Ns/m", "damping", "Suspension damper damping coefficient"),
        "k_t": ("N/m", "stiffness", "Tire vertical radial stiffness"),
        "MR": ("-", "dimensionless", "Motion ratio (spring travel / wheel travel)"),
        "c_t": ("Ns/m", "damping", "Tire vertical damping coefficient"),
        "k_w": ("N/m", "stiffness", "Effective wheel spring rate"),
        "c_w": ("Ns/m", "damping", "Effective wheel damping rate"),
    },
    "half_car": {
        "m_s": ("kg", "mass", "Half car sprung mass"),
        "I_y": ("kg*m^2", "inertia", "Pitch mass moment of inertia"),
        "m_uf": ("kg", "mass", "Front unsprung mass"),
        "m_ur": ("kg", "mass", "Rear unsprung mass"),
        "k_sf": ("N/m", "stiffness", "Front suspension spring stiffness"),
        "k_sr": ("N/m", "stiffness", "Rear suspension spring stiffness"),
        "c_f": ("Ns/m", "damping", "Front damper coefficient"),
        "c_r": ("Ns/m", "damping", "Rear damper coefficient"),
        "k_tf": ("N/m", "stiffness", "Front tire vertical stiffness"),
        "k_tr": ("N/m", "stiffness", "Rear tire vertical stiffness"),
        "a": ("m", "length", "Distance from CG to front axle"),
        "b": ("m", "length", "Distance from CG to rear axle"),
        "c_tf": ("Ns/m", "damping", "Front tire vertical damping"),
        "c_tr": ("Ns/m", "damping", "Rear tire vertical damping"),
    },
    "full_car": {
        "m_s": ("kg", "mass", "Chassis sprung mass"),
        "I_x": ("kg*m^2", "inertia", "Roll mass moment of inertia"),
        "I_y": ("kg*m^2", "inertia", "Pitch mass moment of inertia"),
        "I_z": ("kg*m^2", "inertia", "Yaw mass moment of inertia"),
        "m_uf": ("kg", "mass", "Front corner unsprung mass"),
        "m_ur": ("kg", "mass", "Rear corner unsprung mass"),
        "k_sf": ("N/m", "stiffness", "Front corner spring stiffness"),
        "k_sr": ("N/m", "stiffness", "Rear corner spring stiffness"),
        "c_f": ("Ns/m", "damping", "Front corner damper coefficient"),
        "c_r": ("Ns/m", "damping", "Rear corner damper coefficient"),
        "k_tf": ("N/m", "stiffness", "Front tire vertical stiffness"),
        "k_tr": ("N/m", "stiffness", "Rear tire vertical stiffness"),
        "a": ("m", "length", "CG to front axle distance"),
        "b": ("m", "length", "CG to rear axle distance"),
        "tw_f": ("m", "length", "Front axle track width"),
        "tw_r": ("m", "length", "Rear axle track width"),
        "h_cg": ("m", "length", "Center of gravity height above ground"),
        "arb_f": ("Nm/rad", "roll_stiffness", "Front anti-roll bar stiffness"),
        "arb_r": ("Nm/rad", "roll_stiffness", "Rear anti-roll bar stiffness"),
    },
    "kinematics": {
        "camber_gain_f": ("deg/m", "dimensionless", "Front wheel camber gain per travel"),
        "camber_gain_r": ("deg/m", "dimensionless", "Rear wheel camber gain per travel"),
        "toe_gain_f": ("deg/m", "dimensionless", "Front wheel bump steer gain"),
        "toe_gain_r": ("deg/m", "dimensionless", "Rear wheel bump steer gain"),
        "caster_deg_f": ("deg", "angle", "Front steering caster angle"),
        "kpi_deg_f": ("deg", "angle", "Front kingpin inclination angle"),
        "anti_dive_pct": ("%", "dimensionless", "Front suspension anti-dive percentage"),
        "anti_squat_pct": ("%", "dimensionless", "Rear suspension anti-squat percentage"),
        "roll_center_height_f": ("m", "length", "Front kinematic roll center height"),
        "roll_center_height_r": ("m", "length", "Rear kinematic roll center height"),
    },
    "tire_mf52": {
        "Fz0": ("N", "force", "Nominal vertical wheel load"),
        "p0_bar": ("bar", "pressure", "Nominal tire inflation pressure"),
        "pCy1": ("-", "dimensionless", "Lateral shape factor C_y"),
        "pDy1": ("-", "dimensionless", "Lateral peak friction coefficient"),
        "pEy1": ("-", "dimensionless", "Lateral curvature factor E_y"),
        "pKy1": ("N/rad", "rotational_stiffness", "Lateral cornering stiffness at Fz0"),
        "pKx1": ("N", "force", "Longitudinal slip stiffness at Fz0"),
    },
}


class ParameterMapping(BaseModel):
    """
    Structured definition of a parameter mapping between SuspensionLab PRO
    and an external engineering solver.
    """
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    internal_entity_type: str = Field(
        ...,
        description="Internal entity family (e.g. quarter_car, half_car, full_car, kinematics, tire_mf52)."
    )
    internal_parameter_path: str = Field(
        ...,
        description="Authoritative internal parameter name or dot-path (e.g. m_s, k_sf)."
    )
    external_solver_name: str = Field(
        ...,
        description="Target external solver identifier (e.g. MSC_ADAMS, MATLAB_SIMULINK, CARMAKER)."
    )
    external_model_version: Optional[str] = Field(
        default=None,
        description="Version of the external solver or model template."
    )
    external_variable_id: str = Field(
        ...,
        description="Variable or field name in external solver (e.g. PART_2_MASS, sys.A, FNOMIN)."
    )
    internal_unit: Optional[str] = Field(
        default=None,
        description="Authoritative unit of the internal parameter."
    )
    external_unit: Optional[str] = Field(
        default=None,
        description="Declared unit of the external solver variable."
    )
    physical_dimension: Optional[str] = Field(
        default=None,
        description="Physical dimension of the mapped quantity."
    )
    is_dimensionally_compatible: bool = Field(
        default=True,
        description="True if internal and external units share the exact same physical dimension."
    )
    scale_factor: float = Field(
        default=1.0,
        description="Linear scale factor applied during exchange: val_ext = val_int * scale + offset."
    )
    offset: float = Field(
        default=0.0,
        description="Linear offset applied during exchange."
    )
    sign_multiplier: float = Field(
        default=1.0,
        description="Sign convention multiplier (typically +1.0 or -1.0 for inverted axis/damper conventions)."
    )
    coordinate_axis: Optional[str] = Field(
        default=None,
        description="Associated coordinate axis if spatial quantity (X, Y, Z)."
    )
    coordinate_convention: Optional[str] = Field(
        default=None,
        description="Relevant coordinate convention (e.g. ISO_8855, SAE_J670)."
    )
    provenance: MappingProvenance = Field(
        default=MappingProvenance.AUTHORITATIVE_SPEC,
        description="Authoritative provenance of this mapping entry."
    )
    status: MappingStatus = Field(
        default=MappingStatus.SUPPORTED,
        description="Validation status of the mapping."
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Operational warnings or considerations."
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Known limitations of this mapping entry."
    )

    @model_validator(mode="after")
    def validate_mapping_integrity(self) -> "ParameterMapping":
        """Validates authoritative identity, units, and rejection of guessed similarities."""
        is_valid, validation_warnings = validate_parameter_mapping(self)
        if validation_warnings:
            self.warnings.extend([w for w in validation_warnings if w not in self.warnings])
        return self


def is_authoritative_internal_parameter(entity_type: str, parameter_path: str) -> bool:
    """Verifies whether a given parameter path exists in authoritative specifications."""
    entity_params = AUTHORITATIVE_INTERNAL_PARAMETERS.get(entity_type)
    if not entity_params:
        return False
    return parameter_path in entity_params


def get_authoritative_parameter_metadata(entity_type: str, parameter_path: str) -> Optional[Tuple[str, str, str]]:
    """Returns (unit, dimension, description) for an authoritative internal parameter."""
    entity_params = AUTHORITATIVE_INTERNAL_PARAMETERS.get(entity_type)
    if not entity_params:
        return None
    return entity_params.get(parameter_path)


def validate_parameter_mapping(mapping: ParameterMapping) -> Tuple[bool, List[str]]:
    """
    Validates a parameter mapping against authoritative specifications.

    Rules:
    1. Rejects purely heuristic / string-similarity mappings.
    2. Enforces dimensional compatibility.
    3. Flags missing units as UNRESOLVED.
    4. Rejects unrecognized internal parameter paths as UNSUPPORTED.
    """
    warnings: List[str] = []

    # 1. Reject unverified heuristics
    if mapping.provenance == MappingProvenance.UNVERIFIED_HEURISTIC:
        warnings.append(
            "Rejected unverified heuristic parameter mapping. Name-similarity alone cannot establish engineering equivalence."
        )
        mapping.status = MappingStatus.UNSUPPORTED
        return (False, warnings)

    # 2. Check authoritative internal parameter
    auth_meta = get_authoritative_parameter_metadata(mapping.internal_entity_type, mapping.internal_parameter_path)
    if auth_meta is None:
        warnings.append(
            f"Unknown internal parameter '{mapping.internal_parameter_path}' for entity '{mapping.internal_entity_type}'. "
            f"Reported as UNSUPPORTED."
        )
        mapping.status = MappingStatus.UNSUPPORTED
        return (False, warnings)

    expected_unit, expected_dim, desc = auth_meta

    # Set authoritative internal unit if omitted
    if not mapping.internal_unit:
        mapping.internal_unit = expected_unit
    if not mapping.physical_dimension:
        mapping.physical_dimension = expected_dim

    # 3. Check unit compatibility if external unit is provided
    if mapping.external_unit:
        unit_status, unit_detail = check_unit_compatibility(mapping.internal_unit, mapping.external_unit)
        if unit_status == UnitCompatibilityStatus.INCOMPATIBLE:
            warnings.append(
                f"Incompatible physical dimensions: Internal '{mapping.internal_unit}' ({expected_dim}) "
                f"vs External '{mapping.external_unit}'. Mapping marked UNSUPPORTED."
            )
            mapping.is_dimensionally_compatible = False
            mapping.status = MappingStatus.UNSUPPORTED
            return (False, warnings)
        elif unit_status == UnitCompatibilityStatus.UNRESOLVED:
            warnings.append(f"Unresolved external unit '{mapping.external_unit}': {unit_detail}")
            mapping.status = MappingStatus.UNRESOLVED
            return (False, warnings)
        else:
            mapping.is_dimensionally_compatible = True
    else:
        # Missing external unit
        warnings.append("Missing explicit external unit declaration. Mapping marked UNRESOLVED.")
        mapping.status = MappingStatus.UNRESOLVED
        return (False, warnings)

    # If all checks pass
    if mapping.status in (MappingStatus.SUPPORTED, MappingStatus.VERIFIED):
        return (True, warnings)

    return (False, warnings)


def detect_heuristic_name_mismatch(name_a: str, name_b: str) -> bool:
    """
    Demonstrates that textual similarity ratio > 0.7 does NOT establish
    engineering equivalence (e.g. 'm_s' vs 'm_u', 'speed' vs 'wheel_speed', 'k_w' vs 'k_t').
    """
    ratio = difflib.SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
    # High textual similarity but known distinct engineering identities
    return ratio >= 0.5
