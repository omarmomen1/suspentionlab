"""
src/suspensionlab/backend/api/routes/solver_interop_routes.py
=============================================================
SuspensionLab PRO — Solver Interoperability API Router.

Exposes typed, read-only and validation endpoints for:
- Deterministic adapter capability discovery.
- Canonical exchange manifest validation and schema version verification.
- Parameter mapping audit and dimensional compatibility checking.
- Unit compatibility and coordinate frame consistency validation.

Multi-tenant aware, safely bounded, and independent of concurrent UI/API work.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from suspensionlab.interop.adapter import AdapterCapability, SupportLevel
from suspensionlab.interop.frames import (
    CoordinateFrameDefinition,
    FrameValidationStatus,
    validate_coordinate_frame,
)
from suspensionlab.interop.manifest import (
    CanonicalExchangeManifest,
    validate_canonical_manifest,
)
from suspensionlab.interop.mapping import (
    ParameterMapping,
    validate_parameter_mapping,
)
from suspensionlab.interop.registry import get_adapter_registry
from suspensionlab.interop.service import SolverInteropService
from suspensionlab.interop.units import (
    UnitCompatibilityStatus,
    check_unit_compatibility,
    convert_unit_value,
)

router = APIRouter(prefix="/interop", tags=["Solver Interoperability"])


class UnitCheckRequest(BaseModel):
    unit_a: str = Field(..., description="First unit string.")
    unit_b: str = Field(..., description="Second unit string.")


class UnitCheckResponse(BaseModel):
    status: UnitCompatibilityStatus
    dimension: Optional[str] = None
    detail: Optional[str] = None


class ManifestValidationResponse(BaseModel):
    is_valid: bool
    warnings: List[str]
    manifest: Optional[Dict[str, Any]] = None


class MappingValidationResponse(BaseModel):
    is_valid: bool
    status: str
    is_dimensionally_compatible: bool
    warnings: List[str]


@router.get("/adapters", response_model=List[AdapterCapability])
def list_solver_adapters() -> List[AdapterCapability]:
    """
    Returns list of registered solver interoperability adapters in deterministic order.
    """
    reg = get_adapter_registry()
    return reg.list_adapters()


@router.get("/adapters/{adapter_id}", response_model=AdapterCapability)
def get_solver_adapter(adapter_id: str) -> AdapterCapability:
    """
    Retrieves capability specifications for a specific registered adapter.
    """
    reg = get_adapter_registry()
    adapter = reg.get_adapter(adapter_id)
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Adapter '{adapter_id}' is not registered.",
        )
    return adapter.get_capabilities()


@router.post("/manifests/validate", response_model=ManifestValidationResponse)
def validate_manifest(payload: Dict[str, Any]) -> ManifestValidationResponse:
    """
    Validates a canonical exchange manifest against schema version,
    units, coordinate frames, and numerical safety constraints.
    """
    is_valid, warnings, manifest_obj = validate_canonical_manifest(payload)
    return ManifestValidationResponse(
        is_valid=is_valid,
        warnings=warnings,
        manifest=manifest_obj.model_dump(mode="json") if manifest_obj else None,
    )


@router.post("/mappings/validate", response_model=MappingValidationResponse)
def validate_mapping(mapping: ParameterMapping) -> MappingValidationResponse:
    """
    Validates parameter mapping against authoritative models and dimensions.
    """
    is_valid, warnings = validate_parameter_mapping(mapping)
    return MappingValidationResponse(
        is_valid=is_valid,
        status=mapping.status.value,
        is_dimensionally_compatible=mapping.is_dimensionally_compatible,
        warnings=warnings,
    )


@router.post("/units/check", response_model=UnitCheckResponse)
def check_units(req: UnitCheckRequest) -> UnitCheckResponse:
    """
    Checks dimensional compatibility between two unit declarations.
    """
    comp_status, detail = check_unit_compatibility(req.unit_a, req.unit_b)
    dim = detail if comp_status in (UnitCompatibilityStatus.IDENTICAL, UnitCompatibilityStatus.CONVERTIBLE) else None
    return UnitCheckResponse(
        status=comp_status,
        dimension=dim,
        detail=detail,
    )


@router.post("/frames/check")
def check_frame(frame: CoordinateFrameDefinition) -> Dict[str, Any]:
    """
    Checks coordinate frame orthogonality and handedness consistency.
    """
    f_status, reasons = validate_coordinate_frame(frame)
    return {
        "status": f_status.value,
        "is_valid": f_status == FrameValidationStatus.VALID,
        "reasons": reasons,
    }
