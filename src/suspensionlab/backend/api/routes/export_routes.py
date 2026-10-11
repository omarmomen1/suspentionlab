import tempfile
import pathlib
from typing import Optional
from fastapi import APIRouter, Depends, Response, Query, HTTPException
from suspensionlab.shared.models import FullCarParamsSchema, PlanTier
from suspensionlab.backend.security.auth import require_plan, require_permission
from suspensionlab.backend.security.permissions import Permission
from typing import Any
from suspensionlab.physics.full_car import FullCarParams, build_full_car_state_space
from suspensionlab.physics.quarter_car import QuarterCarParams
from suspensionlab.physics.fmi_exporter import build_and_package_quarter_car_fmu
from suspensionlab.backend.services.cae_exporter import (
    export_quarter_car_to_adams,
    export_quarter_car_to_adams_view_cmd,
    export_quarter_car_to_adams_view_python,
    export_full_car_to_adams,
)

from sqlalchemy.ext.asyncio import AsyncSession
from suspensionlab.backend.database.core import get_db_dependency

router = APIRouter(prefix="/export", tags=["CAE Export Pipeline"])


@router.post("/fmu")
async def export_fmu(
    user: Any = Depends(require_permission(Permission.REPORT_EXPORT)),
    _plan: Any = Depends(require_plan(PlanTier.ENTERPRISE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Generate and package a standard FMI 2.0 Co-Simulation archive (.fmu).
    Includes:
    - modelDescription.xml
    - Compiled binaries for win64 (DLL), linux64 (SO), and linux-arm64 (SO)
    - Standard HTML documentation
    - Resource descriptors
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        fmu_target = pathlib.Path(tmpdir) / "QuarterCarRideModel.fmu"
        build_and_package_quarter_car_fmu(fmu_target)
        content = fmu_target.read_bytes()

    try:
        from suspensionlab.backend.security.audit import record_audit_event
        await record_audit_event(
            db=db,
            event_type="EXPORT_GENERATED",
            user_id=getattr(user, "user_id", None),
            team_id=getattr(user, "team_id", None),
            artifact_id="QuarterCarRideModel.fmu",
            metadata={"format": "fmu", "model": "quarter_car", "fmi_version": "2.0"}
        )
    except Exception as e:
        import logging
        logging.getLogger("security_audit").warning("Audit logging warning for FMU export: %s", e)

    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=QuarterCarRideModel.fmu"}
    )


@router.post("/simulink", response_class=Response)
async def export_simulink(
    params_schema: FullCarParamsSchema,
    user: Any = Depends(require_permission(Permission.REPORT_EXPORT)),
    _plan: Any = Depends(require_plan(PlanTier.ENTERPRISE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Generate a production MATLAB/Simulink (.m) initialization script for 7-DOF vehicle dynamics.
    Loads state-space matrices (A, B, C, D) directly into the MATLAB workspace for Simulink State-Space blocks.
    """
    try:
        params = FullCarParams(**params_schema.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    A, B, C_mat, D_mat = build_full_car_state_space(params)
    
    def matrix_to_matlab(mat, name):
        rows = []
        for row in mat:
            rows.append("    " + " ".join(f"{val:.6e}" for val in row))
        return f"{name} = [\n" + ";\n".join(rows) + "\n];"
        
    script = f"% SuspensionLab PRO - Full Car 7-DOF State Space\n"
    script += f"% Auto-generated for MATLAB & Simulink Integration\n\n"
    script += matrix_to_matlab(A, "A") + "\n\n"
    script += matrix_to_matlab(B, "B") + "\n\n"
    script += matrix_to_matlab(C_mat, "C") + "\n\n"
    script += matrix_to_matlab(D_mat, "D") + "\n\n"
    script += "sys = ss(A, B, C, D);\n"
    script += "sys.InputName = {'z_r_fl', 'z_r_fr', 'z_r_rl', 'z_r_rr'};\n"
    script += "disp('✅ SuspensionLab 7-DOF State-Space Model `sys` loaded into workspace.');\n"
    
    try:
        from suspensionlab.backend.security.audit import record_audit_event
        await record_audit_event(
            db=db,
            event_type="EXPORT_GENERATED",
            user_id=getattr(user, "user_id", None),
            team_id=getattr(user, "team_id", None),
            artifact_id="suspensionlab_7dof_ss.m",
            metadata={"format": "simulink", "model": "full_car_7dof"}
        )
    except Exception as e:
        import logging
        logging.getLogger("security_audit").warning("Audit logging warning for Simulink export: %s", e)

    return Response(
        content=script,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=suspensionlab_7dof_ss.m"}
    )


@router.post("/adams", response_class=Response)
async def export_adams(
    params_schema: FullCarParamsSchema,
    export_format: str = Query("adm", pattern="^(adm|cmd|py)$"),
    user: Any = Depends(require_permission(Permission.REPORT_EXPORT)),
    _plan: Any = Depends(require_plan(PlanTier.ENTERPRISE)),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Generate an MSC.ADAMS compatible model deck:
    - adm: MSC ADAMS Solver dataset (.adm)
    - cmd: MSC ADAMS View command deck (.cmd)
    - py: MSC ADAMS View Python automation script (.py)
    """
    try:
        p = FullCarParams(**params_schema.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if export_format == "cmd":
        # Convert front axle corner parameters to quarter car for Adams View rig
        qc_params = QuarterCarParams(
            m_s=p.m_s / 4.0,
            m_u=p.m_uf,
            k_s=p.k_sf,
            c=p.c_f,
            k_t=p.k_tf,
            MR=1.0,
        )
        content = export_quarter_car_to_adams_view_cmd(qc_params)
        ext = "cmd"
    elif export_format == "py":
        qc_params = QuarterCarParams(
            m_s=p.m_s / 4.0,
            m_u=p.m_uf,
            k_s=p.k_sf,
            c=p.c_f,
            k_t=p.k_tf,
            MR=1.0,
        )
        content = export_quarter_car_to_adams_view_python(qc_params)
        ext = "py"
    else:
        content = export_full_car_to_adams(p)
        ext = "adm"

    try:
        from suspensionlab.backend.security.audit import record_audit_event
        await record_audit_event(
            db=db,
            event_type="EXPORT_GENERATED",
            user_id=getattr(user, "user_id", None),
            team_id=getattr(user, "team_id", None),
            artifact_id=f"suspensionlab_7dof.{ext}",
            metadata={"format": f"adams_{ext}", "model": "full_car_7dof"}
        )
    except Exception as e:
        import logging
        logging.getLogger("security_audit").warning("Audit logging warning for ADAMS export: %s", e)

    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=suspensionlab_7dof.{ext}"}
    )
