"""
backend/api/routes/cae_routes.py
=================================
SuspensionLab PRO — Incumbent CAE Interoperability API (Requirements 2 & 3).

Endpoints:
- POST /api/v1/cae/import          → Ingests external simulation trace, normalizes, records identity
- POST /api/v1/cae/compare-solver  → Compares external run against native forward ODE
- POST /api/v1/cae/export/{format} → Generates validated MSC Adams / MATLAB export decks
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from suspensionlab.backend.security.auth import require_permission, UserContext
from suspensionlab.backend.security.permissions import Permission
from suspensionlab.backend.services.cae_integration_service import CaeIntegrationService
from suspensionlab.physics.quarter_car import QuarterCarParams

router = APIRouter(prefix="/cae", tags=["cae-interoperability"])


class CaeImportRequest(BaseModel):
    source_tool: str = Field(..., description="e.g. 'MSC Adams', 'MATLAB / Simulink', 'IPG CarMaker'")
    version: str = Field(..., description="e.g. 'Adams 2024.1', 'R2024b'")
    solver: str = Field(..., description="e.g. 'WSTIFF', 'ode45'")
    parameters: Dict[str, Any] = Field(..., description="Vehicle setup parameters (m_s, k_s, c, MR)")
    raw_trace_csv: str = Field(..., description="CSV trace with time, ddz_s (or vert_g), travel, tire_load")
    execution_environment: Optional[str] = Field("External Windows x86_64 CAE Host", description="Execution host")
    inputs_meta: Optional[Dict[str, Any]] = None


class CaeCompareRequest(BaseModel):
    import_payload: CaeImportRequest
    override_native_params: Optional[Dict[str, Any]] = None


class CaeExportRequest(BaseModel):
    m_s: float = Field(320.0, description="Sprung mass (kg)")
    m_u: float = Field(45.0, description="Unsprung mass (kg)")
    k_s: float = Field(35000.0, description="Spring rate (N/m)")
    c: float = Field(2200.0, description="Damping coefficient (Ns/m)")
    k_t: float = Field(220000.0, description="Tire radial stiffness (N/m)")
    MR: float = Field(0.85, description="Motion ratio")


@router.post("/import")
async def import_cae_run_endpoint(
    req: CaeImportRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Ingests and normalizes an external CAE simulation result.
    Attaches complete external model identity (source tool, solver, environment, SHA-256 hash).
    """
    try:
        dataset = CaeIntegrationService.import_and_normalize_external_run(
            source_tool=req.source_tool,
            version=req.version,
            solver=req.solver,
            parameters=req.parameters,
            raw_trace_csv=req.raw_trace_csv,
            execution_environment=req.execution_environment or "External Host",
            inputs_meta=req.inputs_meta,
        )
        return dataset.to_dict()
    except Exception as exc:
        logger.exception("Failed to normalize external CAE dataset: %s", exc)
        raise HTTPException(status_code=400, detail="Failed to normalize external CAE dataset.")


@router.post("/compare-solver")
async def compare_cae_solver_endpoint(
    req: CaeCompareRequest,
    user: UserContext = Depends(require_permission(Permission.VEHICLE_READ)),
):
    """
    Compares an external CAE solver result side-by-side with SuspensionLab PRO forward ODE simulation.
    """
    try:
        dataset = CaeIntegrationService.import_and_normalize_external_run(
            source_tool=req.import_payload.source_tool,
            version=req.import_payload.version,
            solver=req.import_payload.solver,
            parameters=req.import_payload.parameters,
            raw_trace_csv=req.import_payload.raw_trace_csv,
            execution_environment=req.import_payload.execution_environment or "External Host",
            inputs_meta=req.import_payload.inputs_meta,
        )

        nat_p = None
        if req.override_native_params:
            nat_p = QuarterCarParams(
                m_s=req.override_native_params.get("m_s", 320.0),
                m_u=req.override_native_params.get("m_u", 45.0),
                k_s=req.override_native_params.get("k_s", 35000.0),
                c=req.override_native_params.get("c", 2200.0),
                k_t=req.override_native_params.get("k_t", 220000.0),
                MR=req.override_native_params.get("MR", 0.85),
            )

        return CaeIntegrationService.compare_external_vs_native(dataset, nat_p)
    except Exception as exc:
        logger.exception("CAE solver comparison failed: %s", exc)
        raise HTTPException(status_code=400, detail="CAE solver comparison failed.")


@router.post("/export/{format_type}")
async def export_cae_deck_endpoint(
    format_type: str,
    req: CaeExportRequest,
    user: UserContext = Depends(require_permission(Permission.SETUP_CREATE)),
):
    """
    Generates validated syntax export decks for MSC Adams (.adm, .cmd, .py) or MATLAB (.m).
    """
    try:
        p = QuarterCarParams(
            m_s=req.m_s,
            m_u=req.m_u,
            k_s=req.k_s,
            c=req.c,
            k_t=req.k_t,
            MR=req.MR,
        )
        return CaeIntegrationService.export_deck(format_type, p)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.exception("Export failed: %s", exc)
        raise HTTPException(status_code=500, detail="Export failed.")
