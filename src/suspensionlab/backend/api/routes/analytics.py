from fastapi import APIRouter, HTTPException
from suspensionlab.shared.models import RaceEngineerRequest, VerdictRequest, QuarterCarKPIs, RaceEngineerResponse, VerdictResponse, RecommendationSchema
from suspensionlab.physics.quarter_car import QuarterCarParams, QuarterCarResult
from suspensionlab.analytics.race_engineer import generate_race_engineer_report
from suspensionlab.physics.decision_engine import generate_setup_verdict

router = APIRouter()

def _reconstruct_result(kpis: QuarterCarKPIs) -> QuarterCarResult:
    """Reconstruct a minimal QuarterCarResult for analytics from KPIs."""
    dump = kpis.model_dump()
    if "metrics" in dump:
        del dump["metrics"]
    return QuarterCarResult(**dump)

@router.post("/analyze/report", response_model=RaceEngineerResponse)
async def analyze_report(payload: RaceEngineerRequest):
    """Generate race engineer diagnostics from simulation KPIs."""
    try:
        result = _reconstruct_result(payload.kpis)
        report = generate_race_engineer_report(result)
        
        recs = [
            RecommendationSchema(
                category=r.category,
                diagnosis=r.diagnosis,
                finding=r.finding,
                action=r.action,
                severity=r.severity.value,
                confidence=round(r.confidence, 2)
            )
            for r in report.recommendations
        ]
        return RaceEngineerResponse(critical_flags=report.has_critical, recommendations=recs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/analyze/verdict", response_model=VerdictResponse)
async def analyze_verdict(payload: VerdictRequest):
    """Generate setup verdict from simulation KPIs + optimizer output."""
    try:
        result = _reconstruct_result(payload.kpis)
        
        params = None
        if payload.params is not None:
            params = QuarterCarParams(**payload.params.model_dump())
        
        optimizer_output = payload.optimizer_output.model_dump()
        
        verdict = generate_setup_verdict(result, optimizer_output, params)
        return VerdictResponse(**verdict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
