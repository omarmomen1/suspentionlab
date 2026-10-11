"""
backend/services/kinematics_optimization_service.py
===================================================
SuspensionLab PRO — Kinematics Optimization & Experiment Transfer Service.

Bridges real multibody kinematics sensitivity analysis with bounded optimization
and the scientific Experiment / Verification pipeline.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from suspensionlab.physics.kinematics import compute_geometry_hash
from suspensionlab.physics.kinematics_sensitivity import (
    compute_hardpoint_sensitivity,
    evaluate_engineering_question,
    optimize_hardpoints,
    OptimizationObjective,
    OptimizationConstraint,
    HardpointSafetyValidator,
)

logger = logging.getLogger(__name__)


class KinematicsOptimizationService:
    """Service handling kinematics sensitivity, recommendations, optimization, and experiment bridging."""

    _cached_studies: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def compute_sensitivity(
        cls,
        hardpoints: Dict[str, List[float]],
        target_hardpoints: Optional[List[str]] = None,
        axes: Optional[List[str]] = None,
        step_size_mm: float = 1.0,
        z_min_mm: float = -35.0,
        z_max_mm: float = 35.0,
        n_steps: int = 15,
    ) -> Dict[str, Any]:
        """Compute full finite-difference Jacobian sensitivity matrix."""
        res = compute_hardpoint_sensitivity(
            hardpoints=hardpoints,
            target_hardpoints=target_hardpoints,
            axes=axes,
            step_size_mm=step_size_mm,
            z_min_mm=z_min_mm,
            z_max_mm=z_max_mm,
            n_steps=n_steps,
        )
        study_id = f"sens-{uuid.uuid4().hex[:10]}"
        res["study_id"] = study_id
        res["timestamp"] = datetime.now(timezone.utc).isoformat()
        res["geometry_hash"] = compute_geometry_hash(hardpoints)
        cls._cached_studies[study_id] = res
        return res

    @classmethod
    def answer_engineering_question(
        cls,
        hardpoints: Dict[str, List[float]],
        question_preset_id: Optional[str] = None,
        custom_objective: Optional[Dict[str, Any]] = None,
        custom_constraints: Optional[Dict[str, Tuple[float, float]]] = None,
        custom_candidates: Optional[List[str]] = None,
        perturbation_steps_mm: Optional[List[float]] = None,
        z_min_mm: float = -35.0,
        z_max_mm: float = 35.0,
        n_steps: int = 15,
    ) -> Dict[str, Any]:
        """Answer engineering questions via real sensitivity perturbations and physics ranking."""
        res = evaluate_engineering_question(
            hardpoints=hardpoints,
            question_preset_id=question_preset_id,
            custom_objective=custom_objective,
            custom_constraints=custom_constraints,
            custom_candidates=custom_candidates,
            perturbation_steps_mm=perturbation_steps_mm,
            z_min_mm=z_min_mm,
            z_max_mm=z_max_mm,
            n_steps=n_steps,
        )
        res["question_id"] = f"q-{uuid.uuid4().hex[:10]}"
        res["timestamp"] = datetime.now(timezone.utc).isoformat()
        res["geometry_hash"] = compute_geometry_hash(hardpoints)
        return res

    @classmethod
    def run_optimization(
        cls,
        hardpoints: Dict[str, List[float]],
        target_hardpoints: List[str],
        allowed_axes: List[str],
        hardpoint_bounds_mm: float = 10.0,
        objectives: Optional[List[Dict[str, Any]]] = None,
        constraints: Optional[List[Dict[str, Any]]] = None,
        n_samples: int = 40,
        z_min_mm: float = -35.0,
        z_max_mm: float = 35.0,
        n_steps: int = 15,
    ) -> Dict[str, Any]:
        """Execute bounded multi-objective optimization with Pareto extraction."""
        obj_objs = []
        if objectives:
            for o in objectives:
                obj_objs.append(
                    OptimizationObjective(
                        metric=o["metric"],
                        direction=o.get("direction", "maximize"),
                        weight=float(o.get("weight", 1.0)),
                        target_val=o.get("target_val"),
                    )
                )

        const_objs = []
        if constraints:
            for c in constraints:
                const_objs.append(
                    OptimizationConstraint(
                        metric=c["metric"],
                        min_val=float(c["min_val"]) if c.get("min_val") is not None else None,
                        max_val=float(c["max_val"]) if c.get("max_val") is not None else None,
                    )
                )

        res = optimize_hardpoints(
            hardpoints=hardpoints,
            target_hardpoints=target_hardpoints,
            allowed_axes=allowed_axes,
            hardpoint_bounds_mm=hardpoint_bounds_mm,
            objectives=obj_objs or None,
            constraints=const_objs or None,
            n_samples=n_samples,
            z_min_mm=z_min_mm,
            z_max_mm=z_max_mm,
            n_steps=n_steps,
        )
        res["timestamp"] = datetime.now(timezone.utc).isoformat()
        res["geometry_hash"] = compute_geometry_hash(hardpoints)
        cls._cached_studies[res["optimization_id"]] = res
        return res

    @classmethod
    def apply_candidate_to_experiment(
        cls,
        baseline_hardpoints: Dict[str, List[float]],
        candidate_hardpoints: Dict[str, List[float]],
        question: str = "Kinematics Hardpoint Optimization",
        hypothesis: Optional[str] = None,
        candidate_id: Optional[str] = None,
        optimization_id: Optional[str] = None,
        author: str = "Lead Kinematics CAE Engineer",
    ) -> Dict[str, Any]:
        """
        Creates an immutable, traceable Experiment payload from an optimized hardpoint candidate.
        Ensures the complete scientific workflow:
        Sensitivity → Candidate Hardpoints → Experiment → Simulation → Compare → Validation.
        """
        clean_base = {k: [float(c) for c in v] for k, v in baseline_hardpoints.items()}
        clean_cand = {k: [float(c) for c in v] for k, v in candidate_hardpoints.items()}

        is_valid, errs = HardpointSafetyValidator.validate(clean_cand)
        if not is_valid:
            raise ValueError(f"Candidate hardpoints are physically invalid: {'; '.join(errs)}")

        base_hash = compute_geometry_hash(clean_base)
        cand_hash = compute_geometry_hash(clean_cand)

        # Detect hardpoint deltas
        changes = []
        for k in sorted(clean_base.keys()):
            if k in clean_cand:
                p_base = clean_base[k]
                p_cand = clean_cand[k]
                d_xyz = [round(p_cand[i] - p_base[i], 3) for i in range(3)]
                dist = round(float(np.linalg.norm(np.array(p_cand) - np.array(p_base))), 3)
                if dist > 0.001:
                    changes.append({
                        "hardpoint": k,
                        "delta_xyz_mm": d_xyz,
                        "displacement_distance_mm": dist,
                        "baseline_xyz": p_base,
                        "candidate_xyz": p_cand,
                    })

        experiment_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        experiment_payload = {
            "experiment_id": experiment_id,
            "status": "READY_FOR_SIMULATION",
            "question": question,
            "hypothesis": hypothesis or f"Moving hardpoints {', '.join(c['hardpoint'] for c in changes)} improves dynamic camber recovery without exceeding toe tolerances.",
            "author": author,
            "timestamp": now_iso,
            "created_at": now_iso,
            "provenance": {
                "origin": "Kinematics Hardpoint Sensitivity & Optimizer",
                "optimization_id": optimization_id or f"opt-{uuid.uuid4().hex[:8]}",
                "candidate_id": candidate_id or f"cand-{cand_hash[:8]}",
                "geometry_hash_baseline": base_hash,
                "geometry_hash_candidate": cand_hash,
                "solver": "Newton-Raphson Multibody Kinematics Solver (C++ kinematics_core / Python fallback)",
            },
            "parent_setup": {
                "name": "Baseline Kinematics Geometry",
                "hardpoints": clean_base,
                "geometry_hash": base_hash,
            },
            "candidate_setup": {
                "name": f"Optimized Geometry ({candidate_id or cand_hash[:8]})",
                "hardpoints": clean_cand,
                "geometry_hash": cand_hash,
            },
            "parameter_changes": changes,
            "redirect_url": f"/experiment?clone_from={experiment_id}&opt_id={optimization_id or ''}&cand_hash={cand_hash}",
        }

        cls._cached_studies[experiment_id] = experiment_payload
        return experiment_payload
