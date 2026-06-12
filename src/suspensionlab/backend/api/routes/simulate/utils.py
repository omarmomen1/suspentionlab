from fastapi import APIRouter, HTTPException, UploadFile, File
from suspensionlab.physics.tir_parser import parse_tir_file
from suspensionlab.shared.models import TireCoeffsSchema
from suspensionlab.physics.telemetry_parser import parse_telemetry_csv
from suspensionlab.shared.models import TelemetryDataSchema

router = APIRouter()

@router.post("/parse-tir", response_model=TireCoeffsSchema)
async def parse_tir_endpoint(file: UploadFile = File(...)):
    try:
        content = await file.read()
        text = content.decode('utf-8', errors='ignore')
        coeffs = parse_tir_file(text)
        return TireCoeffsSchema(**coeffs.__dict__)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/parse-telemetry", response_model=TelemetryDataSchema)
async def parse_telemetry_endpoint(file: UploadFile = File(...)):
    try:
        content = await file.read()
        text = content.decode('utf-8', errors='ignore')
        data = parse_telemetry_csv(text)
        return TelemetryDataSchema(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
