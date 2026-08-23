"""
backend/services/run_artifacts.py
==================================
Immutable Run Artifacts + Setup Diff (Issues 32 & 33).

create_run_from_job()  — snapshot a completed job into an immutable RUN-xxxxxx
get_run() / list_runs()
diff_runs(a, b)        — Setup Diff: parameter table (A/B/Δ%) + predicted
                         consequence deltas from the runs' own metrics
what_changed(a, b)     — the #35 headline summary ("SPAIN — RUN 184 …")

Immutability: this module only INSERTs into simulation_runs. There is no
update path — history is history.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.security.audit import canonical_hash

logger = logging.getLogger(__name__)

SOFTWARE_VERSION = "1.0.0"
SOLVER_VERSION = "rk4-bdf-1.0"
KINEMATICS_VERSION = "kin-cpp-1.0"
PHYSICS_VERSIONS = {
    "quarter_car": "quarter-car-v2",
    "half_car": "half-car-v2",
    "full_car": "full-car-v3",
    "handling": "handling-v2",
    "lap_sim": "qss-lapsim-v2",
}

# Metrics that drive the "predicted consequence" section of a diff.
# key -> (label, unit, lower_is_better)
CONSEQUENCE_METRICS: dict[str, tuple[str, str, bool]] = {
    "rms_body_accel_wk":    ("Ride Comfort (ISO Wk)", "m/s²", True),
    "rms_body_accel":       ("Body Acceleration", "m/s²", True),
    "rms_susp_travel":      ("Suspension Travel", "m", True),
    "peak_susp_travel":     ("Peak Suspension Travel", "m", True),
    "rms_tire_load":        ("Tire Load Variation", "N", True),
    "peak_transmissibility":("Peak Transmissibility", "-", True),
    "lap_time":             ("Lap Time", "s", True),
}


def _physics_version_for(sim_type: str) -> str:
    return PHYSICS_VERSIONS.get(sim_type, "unknown")


def _git_build_id() -> Optional[str]:
    """Best-effort build id from env (CI systems inject these)."""
    import os
    return os.getenv("GIT_COMMIT") or os.getenv("BUILD_ID")


async def create_run_from_job(
    db: AsyncSession,
    job_id: str,
    user_id: str,
    team_id: Optional[str] = None,
    *,
    title: str = "",
    setup_ref: Optional[str] = None,
    tire_ref: Optional[str] = None,
    track_ref: Optional[str] = None,
    telemetry_ref: Optional[str] = None,
) -> dict:
    """
    Snapshot a COMPLETED job into an immutable run artifact.
    Raises 404-mapped ValueError if the job doesn't exist / isn't finished /
    belongs to another user.
    """
    import uuid as _uuid

    uid = _uuid.UUID(user_id)
    jid = _uuid.UUID(job_id)

    result = await db.execute(
        select(JobRecord).where(
            JobRecord.id == jid,
            JobRecord.user_id == uid,
            JobRecord.status == "COMPLETED",
        )
    )
    job: JobRecord | None = result.scalar_one_or_none()
    if job is None:
        raise LookupError("No completed simulation found with that ID for your account.")

    params = job.params or {}
    profile = job.profile or {}
    res = job.result or {}

    # Model validity snapshot at artifact-creation time (Issue 16 integration).
    model_validity = None
    try:
        from suspensionlab.physics.model_validity import assess_quarter_car
        if job.job_type and "QUARTER" in (job.job_type or ""):
            has_damper = bool(params.get("damper_curve_v") or params.get("damper_curve_v_comp"))
            extra = {"damper_curve_v": [1]} if has_damper else {}
            model_validity = assess_quarter_car({**params, **extra}).to_dict()
    except Exception:
        pass

    # Monotonic sequence → RUN-000183 label
    seq_res = await db.execute(select(func.max(SimulationRun.seq)))
    seq = (seq_res.scalar_one() or 0) + 1

    sim_type = (job.job_type or "").lower().replace("simulate_", "").replace("_quarter", "_car").replace("quarter", "quarter_car")
    if "quarter" in sim_type:
        sim_type = "quarter_car"

    warnings = None
    if isinstance(res, dict):
        warnings = res.get("warnings")

    run = SimulationRun(
        seq=seq,
        label=f"RUN-{seq:06d}",
        job_id=jid,
        user_id=uid,
        team_id=_uuid.UUID(team_id) if team_id else None,
        simulation_type=sim_type,
        title=title or f"{job.job_type} run",
        vehicle_ref=setup_ref,   # caller may refine; kept distinct below
        setup_ref=setup_ref,
        tire_ref=tire_ref,
        track_ref=track_ref,
        telemetry_ref=telemetry_ref,
        params=params,
        profile=profile,
        result=res,
        warnings=warnings,
        model_validity=model_validity,
        software_version=SOFTWARE_VERSION,
        physics_version=_physics_version_for(sim_type),
        kinematics_version=KINEMATICS_VERSION,
        solver_version=SOLVER_VERSION,
        git_build_id=_git_build_id(),
        params_hash=canonical_hash(params),
        result_hash=canonical_hash(res),
        input_hash=canonical_hash(profile),
    )
    # Capture response data BEFORE commit — committing expires ORM instances
    # and lazy-loading them afterwards breaks inside async sessions.
    payload = {
        "label": run.label,
        "id": str(run.id),
        "seq": run.seq,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "params_hash": run.params_hash,
        "result_hash": run.result_hash,
    }
    db.add(run)
    await db.commit()
    logger.info("Created immutable artifact %s from job %s", payload["label"], job_id)
    return payload


async def get_run(db: AsyncSession, label_or_id: str, user_id: str,
                  team_id: Optional[str] = None) -> SimulationRun:
    """Fetch one run visible to this user (own runs + team runs)."""
    import uuid as _uuid
    q = select(SimulationRun).limit(1)
    if label_or_id.upper().startswith("RUN-"):
        q = q.where(SimulationRun.label == label_or_id.upper())
    else:
        q = q.where(SimulationRun.id == _uuid.UUID(label_or_id))

    conditions = [SimulationRun.user_id == _uuid.UUID(user_id)]
    if team_id:
        conditions.append(SimulationRun.team_id == _uuid.UUID(team_id))
    q = q.where(*conditions)

    result = await db.execute(q)
    run = result.scalar_one_or_none()
    if run is None:
        raise LookupError(f"Run '{label_or_id}' not found.")
    return run


async def list_runs(db: AsyncSession, user_id: str, team_id: Optional[str] = None,
                    limit: int = 50) -> list[SimulationRun]:
    import uuid as _uuid
    conditions = [SimulationRun.user_id == _uuid.UUID(user_id)]
    if team_id:
        conditions.append(SimulationRun.team_id == _uuid.UUID(team_id))
    result = await db.execute(
        select(SimulationRun)
        .where(*conditions)
        .order_by(desc(SimulationRun.seq))
        .limit(min(limit, 200))
    )
    return list(result.scalars().all())


def run_to_dict(run: SimulationRun, include_payload: bool = False) -> dict:
    d = {
        "label": run.label,
        "simulation_type": run.simulation_type,
        "title": run.title,
        "vehicle_ref": run.vehicle_ref,
        "setup_ref": run.setup_ref,
        "tire_ref": run.tire_ref,
        "track_ref": run.track_ref,
        "telemetry_ref": run.telemetry_ref,
        "software_version": run.software_version,
        "physics_version": run.physics_version,
        "solver_version": run.solver_version,
        "git_build_id": run.git_build_id,
        "params_hash": run.params_hash,
        "result_hash": run.result_hash,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "model_validity": run.model_validity,
    }
    if include_payload:
        d.update({"params": run.params, "result": run.result,
                  "profile": run.profile, "warnings": run.warnings})
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Setup Diff (#33) + What Changed (#35)
# ─────────────────────────────────────────────────────────────────────────────

def diff_params(params_a: dict, params_b: dict) -> list[dict]:
    """Parameter-level diff table: Parameter | A | B | Δ%."""
    rows = []
    keys = sorted(set(params_a) | set(params_b))
    for k in keys:
        va, vb = params_a.get(k), params_b.get(k)
        if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
            continue  # skip LUT arrays / non-numeric
        delta_pct = None
        if abs(va) > 1e-12:
            delta_pct = round(100.0 * (vb - va) / abs(va), 3)
        elif va != vb:
            delta_pct = float("inf")
        if va == vb:
            continue  # only show changed parameters
        rows.append({
            "parameter": k,
            "a": round(float(va), 6),
            "b": round(float(vb), 6),
            "delta_pct": delta_pct,
        })
    return rows


def diff_metrics(result_a: dict, result_b: dict) -> list[dict]:
    """Predicted consequences: metric deltas between the two runs' results."""
    rows = []
    for key, (label, unit, lower_is_better) in CONSEQUENCE_METRICS.items():
        va, vb = result_a.get(key), result_b.get(key)
        if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
            continue
        change_pct = round(100.0 * (vb - va) / abs(va), 2) if abs(va) > 1e-12 else None
        improved = None
        if change_pct is not None and change_pct != 0:
            improved = (change_pct < 0) == lower_is_better
        rows.append({
            "metric": label, "key": key, "unit": unit,
            "a": round(float(va), 5), "b": round(float(vb), 5),
            "change_pct": change_pct,
            "improved": improved,
        })
    return rows


def what_changed(run_a: SimulationRun, run_b: SimulationRun) -> dict:
    """
    The Issue-35 headline: one screen answering 'what changed?'.

    Returns title, headline metric delta (largest consequential improvement),
    per-domain deltas, parameter diff table, and validity comparison.
    """
    param_diff = diff_params(run_a.params or {}, run_b.params or {})
    metric_diff = diff_metrics(run_a.result or {}, run_b.result or {})

    # Headline: first improved metric by absolute impact, else worst regression.
    improved = [m for m in metric_diff if m["improved"]]
    headline = None
    if improved:
        headline = max(improved, key=lambda m: abs(m["change_pct"] or 0))

    regressions = [m for m in metric_diff if m["improved"] is False]

    validity_a = (run_a.model_validity or {}).get("score")
    validity_b = (run_b.model_validity or {}).get("score")

    return {
        "title": f"{(run_a.track_ref or run_a.title or run_a.simulation_type).upper()} — {run_a.label} vs {run_b.label}",
        "run_a": run_a.label,
        "run_b": run_b.label,
        "headline": headline,
        "metrics": metric_diff,
        "improvements": len(improved),
        "regressions": len(regressions),
        "parameter_changes": param_diff,
        "n_parameter_changes": len(param_diff),
        "model_validity": {"a": validity_a, "b": validity_b},
        "versions": {
            "a": {"physics": run_a.physics_version, "solver": run_a.solver_version},
            "b": {"physics": run_b.physics_version, "solver": run_b.solver_version},
        },
    }
