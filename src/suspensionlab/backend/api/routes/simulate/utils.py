import logging
logger = logging.getLogger(__name__)
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from suspensionlab.physics.tir_parser import parse_tir_file
from suspensionlab.shared.models import TireCoeffsSchema
from suspensionlab.physics.telemetry_parser import parse_telemetry_csv
from suspensionlab.shared.models import TelemetryDataSchema
from suspensionlab.backend.security.auth import require_permission
from suspensionlab.backend.security.permissions import Permission
from typing import Any

router = APIRouter()

@router.post("/parse-tir", response_model=TireCoeffsSchema)
async def parse_tir_endpoint(
    file: UploadFile = File(...),
    user: Any = Depends(require_permission(Permission.SIMULATION_RUN))
):
    try:
        content = await file.read()
        text = content.decode('utf-8', errors='ignore')
        coeffs = parse_tir_file(text)
        return TireCoeffsSchema(**coeffs.__dict__)
    except Exception as e:
        logger.exception("parse endpoint failed: %s", e)
        raise HTTPException(status_code=400, detail="The uploaded file could not be parsed. Check the file format and try again.")

@router.post("/parse-telemetry", response_model=TelemetryDataSchema)
async def parse_telemetry_endpoint(
    file: UploadFile = File(...),
    user: Any = Depends(require_permission(Permission.TELEMETRY_UPLOAD))
):
    try:
        content = await file.read()
        text = content.decode('utf-8', errors='ignore')
        data = parse_telemetry_csv(text)
        return TelemetryDataSchema(**data)
    except Exception as e:
        logger.exception("parse endpoint failed: %s", e)
        raise HTTPException(status_code=400, detail="The uploaded file could not be parsed. Check the file format and try again.")
