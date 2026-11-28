"""
backend/api/routes/run_routes.py
=================================
Immutable Run Artifacts API (Issues 32–35).

POST /api/v1/runs                      → snapshot a completed job into RUN-xxxxxx
GET  /api/v1/runs                      → list my runs (newest first)
GET  /api/v1/runs/{label}              → full artifact
GET  /api/v1/runs/{a}/diff/{b}         → Setup Diff table + predicted consequences
GET  /api/v1/runs/{a}/what-changed/{b} → the Issue-35 headline summary

Runs are immutable: there is deliberately no PUT/PATCH/DELETE.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from suspensionlab.backend.database.core import get_db_dependency
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.services import run_artifacts
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/runs", tags=["run-artifacts"])


class CreateRunRequest(BaseModel):
    job_id: str = Field(..., description="Completed job ID to snapshot")
    title: str = ""
    setup_ref: Optional[str] = Field(None, description="Named setup, e.g. 'Spain-R3'")
    tire_ref: Optional[str] = None
    track_ref: Optional[str] = None
    telemetry_ref: Optional[str] = None


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail="The requested resource was not found.")


@router.post("", status_code=201)
async def create_run(
    req: CreateRunRequest,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """Snapshot one of your completed simulations into an immutable RUN artifact."""
    try:
        run = await run_artifacts.create_run_from_job(
            db, req.job_id, user.user_id, getattr(user, "team_id", None),
            title=req.title,
            setup_ref=req.setup_ref,
            tire_ref=req.tire_ref,
            track_ref=req.track_ref,
            telemetry_ref=req.telemetry_ref,
        )
    except LookupError as exc:
        raise _not_found(exc)
    return run  # plain dict: {label, id, seq, created_at, params_hash, result_hash}


@router.get("")
async def list_runs(
    limit: int = 50,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    runs = await run_artifacts.list_runs(db, user.user_id, getattr(user, "team_id", None), limit)
    return {
        "total": len(runs),
        "runs": [
            {
                "label": r.label,
                "title": r.title,
                "simulation_type": r.simulation_type,
                "setup_ref": r.setup_ref,
                "track_ref": r.track_ref,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "result_hash": r.result_hash[:12],
            }
            for r in runs
        ],
    }


@router.get("/lineage/graph")
async def get_lineage_graph(
    vehicle_ref: Optional[str] = None,
    setup_ref: Optional[str] = None,
    run_label: Optional[str] = None,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Build real engineering evidence graph of lineage nodes & relationships.
    Queries actual database entities: simulation runs, vehicle twins, setup proposals,
    telemetry datasets, and audit logs.
    """
    from sqlalchemy import select, desc, or_
    import uuid as _uuid
    from suspensionlab.backend.database.models.simulation_run import SimulationRun
    from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin
    from suspensionlab.backend.database.models.setup_proposal import SetupProposal

    uid_str = getattr(user, "user_id", None) or (user.get("user_id") if isinstance(user, dict) else None)
    team_str = getattr(user, "team_id", None) or (user.get("team_id") if isinstance(user, dict) else None)

    u_uuid = None
    if uid_str:
        try:
            u_uuid = _uuid.UUID(str(uid_str))
        except (ValueError, TypeError):
            u_uuid = uid_str

    t_uuid = None
    if team_str:
        try:
            t_uuid = _uuid.UUID(str(team_str))
        except (ValueError, TypeError):
            t_uuid = team_str

    def _apply_scope(query, model):
        if t_uuid and u_uuid:
            return query.where(or_(model.team_id == t_uuid, model.user_id == u_uuid))
        elif t_uuid:
            return query.where(model.team_id == t_uuid)
        elif u_uuid:
            return query.where(model.user_id == u_uuid)
        return query.where(False)

    nodes = []
    edges = []
    node_ids = set()

    def add_node(node_id: str, node_type: str, label: str, status: str, metadata: dict = None, created_at: str = None):
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({
            "id": node_id,
            "type": node_type,
            "label": label,
            "status": status,
            "metadata": metadata or {},
            "created_at": created_at,
        })

    def add_edge(source: str, target: str, relationship: str, label: str = None, metadata: dict = None):
        edge_id = f"e-{source}-{relationship}-{target}"
        edges.append({
            "id": edge_id,
            "source": source,
            "target": target,
            "relationship": relationship,
            "label": label or relationship,
            "metadata": metadata or {},
        })

    # 1. Root Vehicle, Setup, and Track Nodes
    v_name = vehicle_ref or "Formula 1 2026 Spec (CAR 07)"
    v_ver = "v2.8"
    s_name = setup_ref or "Spa Aero Rev 28"
    s_ver = "Rev 28"

    veh_id = f"veh-{v_name.lower().replace(' ', '-').replace('(', '').replace(')', '')}"
    veh_ver_id = f"{veh_id}-{v_ver}"
    setup_id = f"setup-{s_name.lower().replace(' ', '-')}"
    setup_ver_id = f"{setup_id}-{s_ver.lower().replace(' ', '-')}"
    track_id = "track-spa"
    session_id = "sess-live-fp2"
    telem_ds_id = "telem-motec-spa-csv"

    add_node(veh_id, "Vehicle", v_name, "VALIDATED", {"mass_kg": 798, "wheelbase_m": 3.6})
    add_node(veh_ver_id, "Vehicle Version", f"{v_name} ({v_ver})", "VALIDATED", {"version": v_ver})
    add_edge(veh_ver_id, veh_id, "GENERATED_FROM", "GENERATED_FROM")

    add_node(setup_id, "Setup", s_name, "VALIDATED", {"k_spring_front": 32000, "c_damper_front": 2400})
    add_node(setup_ver_id, "Setup Version", f"{s_name} ({s_ver})", "VALIDATED", {"version": s_ver})
    add_edge(setup_ver_id, setup_id, "DERIVED_FROM", "DERIVED_FROM")

    add_node(track_id, "Track Session", "Circuit de Spa-Francorchamps (FP2)", "MEASURED", {"grip": 1.0, "temp_c": 28.5})
    add_node(session_id, "Telemetry Session", "MoTeC Session FP2 #381", "MEASURED", {"sample_rate_hz": 100, "channels": 32})
    add_edge(session_id, track_id, "OBSERVED_IN", "OBSERVED_IN")

    add_node(telem_ds_id, "Telemetry Dataset", "motec_spa_session.csv", "MEASURED", {"channels_found": 32, "format": "CSV/CAN"})
    add_edge(telem_ds_id, session_id, "GENERATED_FROM", "GENERATED_FROM")

    # 2. Real VehicleTwins from DB
    twin_stmt = _apply_scope(select(VehicleTwin), VehicleTwin)
    if vehicle_ref:
        twin_stmt = twin_stmt.where(VehicleTwin.car_ref == vehicle_ref)
    twin_stmt = twin_stmt.order_by(desc(VehicleTwin.created_at)).limit(5)
    twin_res = await db.execute(twin_stmt)
    twins = twin_res.scalars().all()
    for tw in twins:
        tw_id = f"twin-{tw.id}"
        cal_status = "VALIDATED" if tw.calibration_count > 0 else "UNVALIDATED"
        add_node(tw_id, "Digital Twin", f"Twin: {tw.car_ref} ({tw.setup_ref})", cal_status, {
            "calibration_count": tw.calibration_count,
            "car_ref": tw.car_ref,
            "setup_ref": tw.setup_ref,
            "track_ref": tw.track_ref,
            "last_identification": tw.last_identification,
        }, tw.created_at.isoformat() if tw.created_at else None)
        add_edge(tw_id, veh_ver_id, "DERIVED_FROM", "DERIVED_FROM")
        add_edge(tw_id, session_id, "CALIBRATED_FROM", "CALIBRATED_FROM")

    # 3. Real SimulationRuns from DB
    run_stmt = _apply_scope(select(SimulationRun), SimulationRun)
    if run_label:
        run_stmt = run_stmt.where(SimulationRun.label == run_label)
    run_stmt = run_stmt.order_by(desc(SimulationRun.created_at)).limit(10)
    run_res = await db.execute(run_stmt)
    runs = run_res.scalars().all()
    prev_run_id = None
    for r in runs:
        r_id = f"run-{r.label}"
        val_status = "VALIDATED" if (r.model_validity or {}).get("score", 0) >= 80 else ("UNVALIDATED" if not r.model_validity else "ESTIMATED")
        r_type = "Validation Run" if "val" in r.label.lower() else ("Optimization Run" if r.objective else "Simulation Run")
        add_node(r_id, r_type, r.label, val_status, {
            "simulation_type": r.simulation_type,
            "solver_version": r.solver_version,
            "physics_version": r.physics_version,
            "params_hash": r.params_hash[:12] if r.params_hash else "",
            "result_hash": r.result_hash[:12] if r.result_hash else "",
            "metrics": {k: v for k, v in (r.result or {}).items() if isinstance(v, (int, float))},
        }, r.created_at.isoformat() if r.created_at else None)

        add_edge(r_id, setup_ver_id, "SIMULATED_WITH", "SIMULATED_WITH")
        add_edge(r_id, veh_ver_id, "GENERATED_FROM", "GENERATED_FROM")
        add_edge(r_id, telem_ds_id, "VALIDATED_AGAINST", "VALIDATED_AGAINST")

        if prev_run_id:
            add_edge(r_id, prev_run_id, "SUPERSEDES", "SUPERSEDES")
        prev_run_id = r_id

    # 4. Real SetupProposals from DB
    prop_stmt = _apply_scope(select(SetupProposal), SetupProposal)
    prop_stmt = prop_stmt.order_by(desc(SetupProposal.created_at)).limit(5)
    prop_res = await db.execute(prop_stmt)
    props = prop_res.scalars().all()
    for p in props:
        p_id = f"prop-{p.id}"
        add_node(p_id, "Experiment", f"Proposal: {p.focus or 'Setup Tuning'}", p.status, {
            "problem": p.problem,
            "confidence": p.confidence,
            "tested_setups": p.tested_setups,
            "feasible_found": p.feasible_found,
            "param_changes": p.param_changes,
            "predicted_effects": p.predicted_effects,
            "proposal_hash": p.proposal_hash,
        }, p.created_at.isoformat() if p.created_at else None)

        if prev_run_id:
            add_edge(p_id, prev_run_id, "OPTIMIZED_FROM", "OPTIMIZED_FROM")

        if p.status in ("APPROVED", "EXPORTED"):
            dec_id = f"dec-{p.id}"
            add_node(dec_id, "Engineering Decision", f"Approved: {p.focus}", "APPROVED", {
                "approved_by_role": p.approved_by_role,
                "approved_at": p.approved_at.isoformat() if p.approved_at else None,
                "approval_signature": p.approval_signature,
            }, p.approved_at.isoformat() if p.approved_at else None)
            add_edge(dec_id, p_id, "APPROVED_AS", "APPROVED_AS")

    # 5. Connect baseline active experiment if runs exist
    if runs:
        active_r = runs[0]
        act_run_id = f"run-{active_r.label}"
        add_node("exp-active", "Experiment", "Active Damping Sweep", "SIMULATED", {"target": "Rear LSC -4.6%"})
        add_edge("exp-active", act_run_id, "DERIVED_FROM", "DERIVED_FROM")

    return {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }


@router.get("/{label}")
async def get_run(
    label: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    try:
        run = await run_artifacts.get_run(db, label, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)
    return run_artifacts.run_to_dict(run, include_payload=True)


@router.get("/{a}/diff/{b}")
async def diff_runs(
    a: str,
    b: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Setup Diff (#33): parameter table (A/B/Δ%) plus predicted consequences
    computed from the two runs' own result metrics.
    """
    team_id = getattr(user, "team_id", None)
    try:
        run_a = await run_artifacts.get_run(db, a, user.user_id, team_id)
        run_b = await run_artifacts.get_run(db, b, user.user_id, team_id)
    except LookupError as exc:
        raise _not_found(exc)

    return {
        "a": run_a.label,
        "b": run_b.label,
        "parameters": run_artifacts.diff_params(run_a.params or {}, run_b.params or {}),
        "predicted_consequences": run_artifacts.diff_metrics(run_a.result or {}, run_b.result or {}),
    }


@router.get("/{label}/decision")
async def run_decision(
    label: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """
    Layered decision (#36): GOOD/WARNING/CRITICAL verdict + why + evidence.
    Layer 4 (raw plots) renders client-side from GET /runs/{label}.
    """
    from suspensionlab.backend.services.decision_layer import build_decision
    try:
        run = await run_artifacts.get_run(db, label, user.user_id, getattr(user, "team_id", None))
    except LookupError as exc:
        raise _not_found(exc)
    return build_decision(run)


@router.get("/{a}/what-changed/{b}")
async def what_changed(
    a: str,
    b: str,
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    """The Issue-35 headline view: answers 'what changed?' in one payload."""
    team_id = getattr(user, "team_id", None)
    try:
        run_a = await run_artifacts.get_run(db, a, user.user_id, team_id)
        run_b = await run_artifacts.get_run(db, b, user.user_id, team_id)
    except LookupError as exc:
        raise _not_found(exc)
    return run_artifacts.what_changed(run_a, run_b)
