from fastapi import APIRouter, Depends, Response
from suspensionlab.shared.models import FullCarParamsSchema, PlanTier
from suspensionlab.backend.security.auth import require_plan
from suspensionlab.physics.full_car import FullCarParams, build_full_car_state_space

router = APIRouter(prefix="/export", tags=["CAE Export Pipeline"])

@router.post("/simulink", response_class=Response)
async def export_simulink(
    params_schema: FullCarParamsSchema,
    user: dict = Depends(require_plan(PlanTier.ENTERPRISE))
):
    """
    Generate a MATLAB (.m) initialization script for Simulink integration.
    """
    params = FullCarParams(**params_schema.model_dump())
    A, B, C_mat, D_mat = build_full_car_state_space(params)
    
    def matrix_to_matlab(mat, name):
        rows = []
        for row in mat:
            rows.append("    " + " ".join(f"{val:.6e}" for val in row))
        return f"{name} = [\n" + ";\n".join(rows) + "\n];"
        
    script = f"% SuspensionLab PRO - Full Car 7-DOF State Space\n"
    script += f"% Auto-generated for Simulink Integration\n\n"
    script += matrix_to_matlab(A, "A") + "\n\n"
    script += matrix_to_matlab(B, "B") + "\n\n"
    script += matrix_to_matlab(C_mat, "C") + "\n\n"
    script += matrix_to_matlab(D_mat, "D") + "\n\n"
    script += "sys = ss(A, B, C, D);\n"
    script += "disp('SuspensionLab 7-DOF State-Space Model loaded into workspace.');\n"
    
    return Response(
        content=script,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=suspensionlab_7dof_ss.m"}
    )

@router.post("/adams", response_class=Response)
async def export_adams(
    params_schema: FullCarParamsSchema,
    user: dict = Depends(require_plan(PlanTier.ENTERPRISE))
):
    """
    Generate an MSC ADAMS (.adm) solver dataset.
    """
    p = params_schema
    # Basic ADAMS Solver dataset template for a 7-DOF representation
    adm = f"""! ADAMS/Solver Dataset - SuspensionLab PRO Export
! 7-DOF Full Car Vehicle Model

! --- Units ---
UNITS/ FORCE = NEWTON, MASS = KILOGRAM, LENGTH = METER, TIME = SECOND

! --- Sprung Mass ---
PART/1, GROUND
PART/2, MASS={p.m_s:.2f}, CM=1, IP={p.I_x:.2f}, {p.I_y:.2f}, 1000.0
MARKER/1, PART=2, QP=0,0,0.5
  
! --- Unsprung Masses ---
! FL
PART/3, MASS={p.m_uf:.2f}, CM=2
MARKER/2, PART=3, QP={p.a:.3f}, {p.tw_f/2:.3f}, 0.3
! FR
PART/4, MASS={p.m_uf:.2f}, CM=3
MARKER/3, PART=4, QP={p.a:.3f}, {-p.tw_f/2:.3f}, 0.3
! RL
PART/5, MASS={p.m_ur:.2f}, CM=4
MARKER/4, PART=5, QP={-p.b:.3f}, {p.tw_r/2:.3f}, 0.3
! RR
PART/6, MASS={p.m_ur:.2f}, CM=5
MARKER/5, PART=6, QP={-p.b:.3f}, {-p.tw_r/2:.3f}, 0.3

! --- Suspension Springs/Dampers ---
SFORCE/1, TRANSLATION, I=11, J=21, ACTIONONLY, FUNCTION={p.k_sf:.2f}*DM(11,21) + {p.c_f:.2f}*VR(11,21)
SFORCE/2, TRANSLATION, I=12, J=22, ACTIONONLY, FUNCTION={p.k_sf:.2f}*DM(12,22) + {p.c_f:.2f}*VR(12,22)
SFORCE/3, TRANSLATION, I=13, J=23, ACTIONONLY, FUNCTION={p.k_sr:.2f}*DM(13,23) + {p.c_r:.2f}*VR(13,23)
SFORCE/4, TRANSLATION, I=14, J=24, ACTIONONLY, FUNCTION={p.k_sr:.2f}*DM(14,24) + {p.c_r:.2f}*VR(14,24)

! --- Anti-Roll Bars ---
SFORCE/5, ROTATION, I=31, J=41, ACTIONONLY, FUNCTION={p.k_arb_f:.2f}*AZ(31,41)
SFORCE/6, ROTATION, I=32, J=42, ACTIONONLY, FUNCTION={p.k_arb_r:.2f}*AZ(32,42)

! --- Tire Stiffness ---
SFORCE/7, TRANSLATION, I=21, J=1, ACTIONONLY, FUNCTION={p.k_tf:.2f}*DM(21,1)
SFORCE/8, TRANSLATION, I=22, J=1, ACTIONONLY, FUNCTION={p.k_tf:.2f}*DM(22,1)
SFORCE/9, TRANSLATION, I=23, J=1, ACTIONONLY, FUNCTION={p.k_tr:.2f}*DM(23,1)
SFORCE/10, TRANSLATION, I=24, J=1, ACTIONONLY, FUNCTION={p.k_tr:.2f}*DM(24,1)

! END
"""
    return Response(
        content=adm,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=suspensionlab_7dof.adm"}
    )
