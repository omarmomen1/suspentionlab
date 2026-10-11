"""
src/suspensionlab/interop/units.py
===================================
SuspensionLab PRO — Solver Interoperability Physical Dimensions & Unit System.

Provides:
- Physical dimension categorization across automotive & suspension domains.
- Unit compatibility evaluation:
    IDENTICAL: Exact match after normalization.
    CONVERTIBLE: Same physical dimension, convertible via explicit linear scale/offset.
    INCOMPATIBLE: Distinct physical dimensions (e.g. stiffness vs mass).
    UNRESOLVED: Missing, ambiguous, or unknown unit.
- Explicit linear transformations with auditable conversion records.
- Strict Invariants:
    1. NEVER convert across incompatible dimensions.
    2. NEVER silently guess or assume SI units for missing or empty units.
    3. All conversions record exact scale and offset for reproducibility.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


class UnitCompatibilityStatus(str, Enum):
    """Evaluation status of dimensional and unit compatibility."""
    IDENTICAL = "IDENTICAL"
    CONVERTIBLE = "CONVERTIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNRESOLVED = "UNRESOLVED"


class IncompatibleDimensionError(ValueError):
    """Raised when an operation attempts to convert across incompatible physical dimensions."""
    pass


class UnresolvedUnitError(ValueError):
    """Raised when an operation encounters missing, empty, or unrecognized units without authoritative metadata."""
    pass


@dataclass(frozen=True)
class ConversionRecord:
    """Auditable record of a unit conversion applied during exchange."""
    parameter_name: str
    from_unit: str
    to_unit: str
    scale_factor: float
    offset: float = 0.0
    formula: Optional[str] = None


# Authoritative Physical Dimension Groups
# Normalized lower-case unit strings mapped to their physical dimension
DIMENSION_REGISTRY: Dict[str, str] = {
    # Stiffness [Force / Length] -> base SI: N/m
    "n/m": "stiffness",
    "n/mm": "stiffness",
    "kn/m": "stiffness",
    "lb/in": "stiffness",
    "lbs/in": "stiffness",
    "lbf/in": "stiffness",

    # Damping [Force * Time / Length] -> base SI: N*s/m
    "ns/m": "damping",
    "n*s/m": "damping",
    "n-s/m": "damping",
    "ns/mm": "damping",
    "n*s/mm": "damping",
    "lb*s/in": "damping",
    "lbs/in/s": "damping",

    # Mass [Mass] -> base SI: kg
    "kg": "mass",
    "g": "mass",
    "tonne": "mass",
    "t": "mass",
    "lb": "mass",
    "lbs": "mass",
    "slug": "mass",

    # Length [Length] -> base SI: m
    "m": "length",
    "mm": "length",
    "cm": "length",
    "km": "length",
    "in": "length",
    "inch": "length",
    "ft": "length",

    # Angle [Plane Angle] -> base SI: rad (canonical in physics, deg common in engineering)
    "rad": "angle",
    "deg": "angle",
    "degree": "angle",
    "degrees": "angle",
    "rev": "angle",
    "rot": "angle",

    # Pressure [Force / Area] -> base SI: Pa
    "pa": "pressure",
    "kpa": "pressure",
    "mpa": "pressure",
    "bar": "pressure",
    "mbar": "pressure",
    "psi": "pressure",
    "atm": "pressure",

    # Force [Force] -> base SI: N
    "n": "force",
    "kn": "force",
    "mn": "force",
    "lbf": "force",
    "lb_f": "force",

    # Time [Time] -> base SI: s
    "s": "time",
    "sec": "time",
    "ms": "time",
    "min": "time",
    "h": "time",
    "hr": "time",

    # Velocity [Length / Time] -> base SI: m/s
    "m/s": "velocity",
    "mps": "velocity",
    "km/h": "velocity",
    "kmh": "velocity",
    "kph": "velocity",
    "mph": "velocity",
    "ft/s": "velocity",
    "fps": "velocity",
    "knot": "velocity",

    # Acceleration [Length / Time^2] -> base SI: m/s^2
    "m/s^2": "acceleration",
    "m/s2": "acceleration",
    "g": "acceleration",

    # Rotational Stiffness [Force / Angle] -> base SI: N/rad
    "n/rad": "rotational_stiffness",
    "n/deg": "rotational_stiffness",

    # Roll / Torsional Stiffness [Torque / Angle] -> base SI: N*m/rad
    "nm/rad": "roll_stiffness",
    "n*m/rad": "roll_stiffness",
    "nm/deg": "roll_stiffness",
    "n*m/deg": "roll_stiffness",

    # Torque / Moment [Force * Length] -> base SI: N*m
    "nm": "torque",
    "n*m": "torque",
    "kn*m": "torque",
    "ft*lb": "torque",
    "in*lb": "torque",

    # Mass Moment of Inertia [Mass * Length^2] -> base SI: kg*m^2
    "kg*m^2": "inertia",
    "kg*m2": "inertia",
    "kgm^2": "inertia",
    "kgm2": "inertia",
    "lb*ft^2": "inertia",
    "slug*ft^2": "inertia",

    # Flow Rate [Volume / Time] -> base SI: L/min
    "l/min": "flow_rate",
    "l/s": "flow_rate",
    "m^3/s": "flow_rate",

    # Dimensionless [-]
    "-": "dimensionless",
    "ratio": "dimensionless",
    "%": "dimensionless",
    "pct": "dimensionless",
    "ppm": "dimensionless",
}

# Linear conversion factors to canonical base SI unit for each physical dimension.
# (canonical base SI per dimension: stiffness->N/m, damping->N*s/m, mass->kg, length->m,
#  angle->rad, pressure->Pa, force->N, time->s, velocity->m/s, acceleration->m/s^2,
#  rotational_stiffness->N/rad, roll_stiffness->N*m/rad, torque->N*m, inertia->kg*m^2,
#  flow_rate->L/min, dimensionless->ratio)
SI_SCALE_FACTORS: Dict[str, float] = {
    # Stiffness (base: N/m)
    "n/m": 1.0,
    "n/mm": 1000.0,
    "kn/m": 1000.0,
    "lb/in": 175.1268352464764,
    "lbs/in": 175.1268352464764,
    "lbf/in": 175.1268352464764,

    # Damping (base: N*s/m)
    "ns/m": 1.0,
    "n*s/m": 1.0,
    "n-s/m": 1.0,
    "ns/mm": 1000.0,
    "n*s/mm": 1000.0,
    "lb*s/in": 175.1268352464764,
    "lbs/in/s": 175.1268352464764,

    # Mass (base: kg)
    "kg": 1.0,
    "g": 0.001,
    "tonne": 1000.0,
    "t": 1000.0,
    "lb": 0.45359237,
    "lbs": 0.45359237,
    "slug": 14.5939029,

    # Length (base: m)
    "m": 1.0,
    "mm": 0.001,
    "cm": 0.01,
    "km": 1000.0,
    "in": 0.0254,
    "inch": 0.0254,
    "ft": 0.3048,

    # Angle (base: rad)
    "rad": 1.0,
    "deg": math.pi / 180.0,
    "degree": math.pi / 180.0,
    "degrees": math.pi / 180.0,
    "rev": 2.0 * math.pi,
    "rot": 2.0 * math.pi,

    # Pressure (base: Pa)
    "pa": 1.0,
    "kpa": 1000.0,
    "mpa": 1_000_000.0,
    "bar": 100_000.0,
    "mbar": 100.0,
    "psi": 6894.757293168361,
    "atm": 101325.0,

    # Force (base: N)
    "n": 1.0,
    "kn": 1000.0,
    "mn": 1_000_000.0,
    "lbf": 4.4482216152605,
    "lb_f": 4.4482216152605,

    # Time (base: s)
    "s": 1.0,
    "sec": 1.0,
    "ms": 0.001,
    "min": 60.0,
    "h": 3600.0,
    "hr": 3600.0,

    # Velocity (base: m/s)
    "m/s": 1.0,
    "mps": 1.0,
    "km/h": 1.0 / 3.6,
    "kmh": 1.0 / 3.6,
    "kph": 1.0 / 3.6,
    "mph": 0.44704,
    "ft/s": 0.3048,
    "fps": 0.3048,
    "knot": 0.51444444444444,

    # Acceleration (base: m/s^2)
    "m/s^2": 1.0,
    "m/s2": 1.0,
    "g": 9.80665,

    # Rotational Stiffness (base: N/rad)
    "n/rad": 1.0,
    "n/deg": 180.0 / math.pi,

    # Roll Stiffness (base: N*m/rad)
    "nm/rad": 1.0,
    "n*m/rad": 1.0,
    "nm/deg": 180.0 / math.pi,
    "n*m/deg": 180.0 / math.pi,

    # Torque (base: N*m)
    "nm": 1.0,
    "n*m": 1.0,
    "kn*m": 1000.0,
    "ft*lb": 1.3558179483314,
    "in*lb": 0.1129848290276167,

    # Inertia (base: kg*m^2)
    "kg*m^2": 1.0,
    "kg*m2": 1.0,
    "kgm^2": 1.0,
    "kgm2": 1.0,
    "lb*ft^2": 0.0421401100938,
    "slug*ft^2": 1.3558179483314,

    # Flow Rate (base: L/min)
    "l/min": 1.0,
    "l/s": 60.0,
    "m^3/s": 60_000.0,

    # Dimensionless (base: ratio)
    "-": 1.0,
    "ratio": 1.0,
    "%": 0.01,
    "pct": 0.01,
    "ppm": 1e-6,
}


def normalize_unit_string(unit: Optional[str]) -> Optional[str]:
    """Cleans and standardizes unit representation for deterministic lookup."""
    if unit is None:
        return None
    cleaned = unit.strip().lower()
    if not cleaned:
        return None
    # Common alias replacements
    cleaned = cleaned.replace(" ", "")
    return cleaned


def get_physical_dimension(unit: Optional[str]) -> Optional[str]:
    """Resolves the physical dimension of a unit string, or None if unknown/empty."""
    norm = normalize_unit_string(unit)
    if not norm:
        return None
    return DIMENSION_REGISTRY.get(norm)


def are_units_dimensionally_compatible(unit_a: Optional[str], unit_b: Optional[str]) -> bool:
    """Verifies that two units share the exact same physical dimension."""
    status, _ = check_unit_compatibility(unit_a, unit_b)
    return status in (UnitCompatibilityStatus.IDENTICAL, UnitCompatibilityStatus.CONVERTIBLE)


def check_unit_compatibility(
    unit_a: Optional[str],
    unit_b: Optional[str],
) -> Tuple[UnitCompatibilityStatus, Optional[str]]:
    """
    Evaluates compatibility between two unit declarations.

    Returns:
        (status, details_or_dimension)
    """
    norm_a = normalize_unit_string(unit_a)
    norm_b = normalize_unit_string(unit_b)

    if norm_a is None or norm_b is None:
        missing = []
        if norm_a is None:
            missing.append("unit_a")
        if norm_b is None:
            missing.append("unit_b")
        return (
            UnitCompatibilityStatus.UNRESOLVED,
            f"Missing authoritative unit specification for: {', '.join(missing)}",
        )

    if norm_a not in DIMENSION_REGISTRY or norm_b not in DIMENSION_REGISTRY:
        unrecognized = []
        if norm_a not in DIMENSION_REGISTRY:
            unrecognized.append(norm_a)
        if norm_b not in DIMENSION_REGISTRY:
            unrecognized.append(norm_b)
        return (
            UnitCompatibilityStatus.UNRESOLVED,
            f"Unrecognized unit(s) without registry definition: {', '.join(unrecognized)}",
        )

    if norm_a == norm_b:
        return (UnitCompatibilityStatus.IDENTICAL, DIMENSION_REGISTRY[norm_a])

    dim_a = DIMENSION_REGISTRY[norm_a]
    dim_b = DIMENSION_REGISTRY[norm_b]

    if dim_a == dim_b:
        return (UnitCompatibilityStatus.CONVERTIBLE, dim_a)

    return (
        UnitCompatibilityStatus.INCOMPATIBLE,
        f"Incompatible physical dimensions: '{dim_a}' ({norm_a}) vs '{dim_b}' ({norm_b})",
    )


def convert_unit_value(
    value: float,
    from_unit: Optional[str],
    to_unit: Optional[str],
    parameter_name: str = "",
) -> Tuple[float, ConversionRecord]:
    """
    Converts a numerical value from one unit to another within the same physical dimension.

    Raises:
        UnresolvedUnitError: If either unit is missing or unrecognized.
        IncompatibleDimensionError: If units have different physical dimensions.
    """
    status, detail = check_unit_compatibility(from_unit, to_unit)

    if status == UnitCompatibilityStatus.UNRESOLVED:
        raise UnresolvedUnitError(f"Cannot convert value: {detail}")

    if status == UnitCompatibilityStatus.INCOMPATIBLE:
        raise IncompatibleDimensionError(f"Cannot convert value: {detail}")

    norm_from = normalize_unit_string(from_unit)
    norm_to = normalize_unit_string(to_unit)
    assert norm_from is not None and norm_to is not None

    if status == UnitCompatibilityStatus.IDENTICAL:
        record = ConversionRecord(
            parameter_name=parameter_name,
            from_unit=norm_from,
            to_unit=norm_to,
            scale_factor=1.0,
            offset=0.0,
            formula=f"{value} * 1.0",
        )
        return (float(value), record)

    # Both units are CONVERTIBLE in the same dimension
    scale_from = SI_SCALE_FACTORS[norm_from]
    scale_to = SI_SCALE_FACTORS[norm_to]

    # Convert to base SI, then to target unit
    effective_scale = scale_from / scale_to
    converted_val = value * effective_scale

    record = ConversionRecord(
        parameter_name=parameter_name,
        from_unit=norm_from,
        to_unit=norm_to,
        scale_factor=effective_scale,
        offset=0.0,
        formula=f"{value} * {effective_scale:.10e}",
    )
    return (converted_val, record)
