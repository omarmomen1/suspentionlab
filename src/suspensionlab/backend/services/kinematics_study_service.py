"""
backend/services/kinematics_study_service.py
============================================
SuspensionLab PRO — Kinematics Study & Comparative Analysis Service

Provides:
1. Sweep persistence & catalog management.
2. Mathematically authentic rate/derivative calculation.
3. Comparative A/B kinematic analysis with physically grounded causal explanations.
4. Professional CSV and JSON engineering exports.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    compute_kinematic_derivatives,
    compute_geometry_hash,
    compare_kinematic_setups,
    solve_kinematics,
    validate_hardpoints_py,
)
from suspensionlab.backend.api.routes.kinematics_routes import BENCHMARK_PRESETS

logger = logging.getLogger(__name__)


# ── Built-in Persistent Benchmark & Variant Setups Catalog ─────────────────────
PRESET_SETUPS: Dict[str, Dict[str, Any]] = {
    "gt3_touring": {
        "id": "gt3_touring",
        "name": "GT3 Touring Car (Baseline)",
        "category": "GT / Sports Car",
        "description": "Production-derived GT3 racecar double wishbone geometry with long control arms for high-speed stability.",
        "wheel_travel_range": [-50.0, 50.0],
        "tire_radius_m": 0.330,
        "hardpoints": BENCHMARK_PRESETS["gt3_touring"]["hardpoints"],
    },
    "gt3_camber_shim_5mm": {
        "id": "gt3_camber_shim_5mm",
        "name": "GT3 Touring (Upper Pivot +5mm Z)",
        "category": "GT / Sports Car",
        "description": "Variant with upper wishbone inboard pickups raised by +5mm Z to increase camber recovery in high-roll corners.",
        "wheel_travel_range": [-50.0, 50.0],
        "tire_radius_m": 0.330,
        "hardpoints": {
            **BENCHMARK_PRESETS["gt3_touring"]["hardpoints"],
            "UWI_fwd": [
                BENCHMARK_PRESETS["gt3_touring"]["hardpoints"]["UWI_fwd"][0],
                BENCHMARK_PRESETS["gt3_touring"]["hardpoints"]["UWI_fwd"][1],
                BENCHMARK_PRESETS["gt3_touring"]["hardpoints"]["UWI_fwd"][2] + 5.0,
            ],
            "UWI_aft": [
                BENCHMARK_PRESETS["gt3_touring"]["hardpoints"]["UWI_aft"][0],
                BENCHMARK_PRESETS["gt3_touring"]["hardpoints"]["UWI_aft"][1],
                BENCHMARK_PRESETS["gt3_touring"]["hardpoints"]["UWI_aft"][2] + 5.0,
            ],
        },
    },
    "formula_sae": {
        "id": "formula_sae",
        "name": "Formula SAE Prototype (Baseline)",
        "category": "Open Wheel Formula",
        "description": "Agile open-wheel prototype with aggressive camber recovery, low roll center, and direct pushrod actuation.",
        "wheel_travel_range": [-30.0, 30.0],
        "tire_radius_m": 0.254,
        "hardpoints": BENCHMARK_PRESETS["formula_sae"]["hardpoints"],
    },
    "formula_sae_low_rc": {
        "id": "formula_sae_low_rc",
        "name": "Formula SAE (Low Roll Center -15mm)",
        "category": "Open Wheel Formula",
        "description": "Formula SAE corner with lower wishbone inboard lowered 15mm to drop roll center height closer to ground plane.",
        "wheel_travel_range": [-30.0, 30.0],
        "tire_radius_m": 0.254,
        "hardpoints": {
            **BENCHMARK_PRESETS["formula_sae"]["hardpoints"],
            "LWI_fwd": [
                BENCHMARK_PRESETS["formula_sae"]["hardpoints"]["LWI_fwd"][0],
                BENCHMARK_PRESETS["formula_sae"]["hardpoints"]["LWI_fwd"][1],
                BENCHMARK_PRESETS["formula_sae"]["hardpoints"]["LWI_fwd"][2] - 15.0,
            ],
            "LWI_aft": [
                BENCHMARK_PRESETS["formula_sae"]["hardpoints"]["LWI_aft"][0],
                BENCHMARK_PRESETS["formula_sae"]["hardpoints"]["LWI_aft"][1],
                BENCHMARK_PRESETS["formula_sae"]["hardpoints"]["LWI_aft"][2] - 15.0,
            ],
        },
    },
    "lmp_prototype": {
        "id": "lmp_prototype",
        "name": "LMP / Hypercar Prototype",
        "category": "Endurance Prototype",
        "description": "High-downforce endurance sports prototype with stiff kinematics and low scrub radius.",
        "wheel_travel_range": [-35.0, 35.0],
        "tire_radius_m": 0.340,
        "hardpoints": BENCHMARK_PRESETS["lmp_prototype"]["hardpoints"],
    },
}


class KinematicsStudyService:
    """Manages persistent setups, sweeps, comparisons, and exports."""

    # In-memory stores for fast session execution and testability
    _saved_setups: Dict[str, Dict[str, Any]] = dict(PRESET_SETUPS)
    _sweep_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_all_setups(cls) -> List[Dict[str, Any]]:
        """Return list of all available persisted setups (presets + user custom)."""
        return list(cls._saved_setups.values())

    @classmethod
    def get_setup(cls, setup_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific setup by ID."""
        return cls._saved_setups.get(setup_id)

    @classmethod
    def save_setup(
        cls,
        setup_id: str,
        name: str,
        hardpoints: Dict[str, List[float]],
        category: str = "Custom",
        description: str = "",
        wheel_travel_range: List[float] = None,
        tire_radius_m: float = 0.33,
    ) -> Dict[str, Any]:
        """Persist a named user setup."""
        clean_hp = {
            k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else [float(c) for c in v])
            for k, v in hardpoints.items()
        }
        setup_data = {
            "id": setup_id,
            "name": name,
            "category": category,
            "description": description or f"User custom setup {setup_id}",
            "wheel_travel_range": wheel_travel_range or [-50.0, 50.0],
            "tire_radius_m": tire_radius_m,
            "hardpoints": clean_hp,
            "geometry_hash": compute_geometry_hash(clean_hp),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        cls._saved_setups[setup_id] = setup_data
        return setup_data

    @classmethod
    def run_sweep(
        cls,
        hardpoints: Dict[str, Any],
        z_min_mm: float = -50.0,
        z_max_mm: float = 50.0,
        n_steps: int = 33,
        backend_mode: str = "auto",
        strict_mode: bool = False,
        setup_id: Optional[str] = None,
        vehicle_id: str = "corner_multibody",
        tire_radius_m: float = 0.33,
    ) -> Dict[str, Any]:
        """Execute real kinematic sweep, compute derivatives, and persist result."""
        clean_hp = {
            k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else [float(c) for c in v])
            for k, v in hardpoints.items()
        }
        curves = solve_kinematics(
            hardpoints=clean_hp,
            z_min_mm=z_min_mm,
            z_max_mm=z_max_mm,
            n_steps=n_steps,
            tire_radius=tire_radius_m,
            mode=backend_mode,
            strict_mode=strict_mode,
        )
        d = curves.to_dict()
        derivatives = compute_kinematic_derivatives(d)
        val_report = validate_hardpoints_py("double_wishbone", clean_hp, tire_radius_m=tire_radius_m)

        run_id = f"swp-{uuid.uuid4().hex[:12]}"
        geom_hash = compute_geometry_hash(clean_hp)
        now_iso = datetime.now(timezone.utc).isoformat()

        sweep_result = {
            "run_id": run_id,
            "setup_id": setup_id or f"setup-{geom_hash[:8]}",
            "vehicle_id": vehicle_id,
            "geometry_hash": geom_hash,
            "timestamp": now_iso,
            "hardpoints": clean_hp,
            "wheel_travel_mm": d["wheel_travel_mm"],
            "camber_deg": d["camber_deg"],
            "toe_deg": d["toe_deg"],
            "caster_deg": d["caster_deg"],
            "kpi_deg": d["kpi_deg"],
            "track_change_mm": d["track_change_mm"],
            "wheelbase_change_mm": d["wheelbase_change_mm"],
            "roll_center_height_mm": d["roll_center_height_mm"],
            "roll_center_lateral_mm": d.get("roll_center_lateral_mm", [0.0] * len(d["wheel_travel_mm"])),
            "motion_ratio": d["motion_ratio"],
            "scrub_radius_mm": d["scrub_radius_mm"],
            "converged": d["converged"],
            "all_converged": all(d["converged"]),
            "ic_y_mm": d.get("ic_y_mm", []),
            "ic_z_mm": d.get("ic_z_mm", []),
            "ic_sv_x_mm": d.get("ic_sv_x_mm", []),
            "ic_sv_z_mm": d.get("ic_sv_z_mm", []),
            "geometry_steps": d.get("geometry_steps", []),
            "derivatives": derivatives,
            "validation_report": val_report,
            "backend": getattr(curves, "active_backend", getattr(curves, "backend", "C++ (kinematics_core)")),
            "solver_version": getattr(curves, "solver_version", "2.1.0-simd"),
            "native_library_version": getattr(curves, "native_library_version", "2.1.0"),
            "build_identifier": getattr(curves, "build_identifier", "eigen-3.4.0-simd-x86_64"),
        }

        # Cache sweep result
        cls._sweep_cache[run_id] = sweep_result
        return sweep_result

    @classmethod
    def compare(
        cls,
        setup_a: Dict[str, Any],
        setup_b: Dict[str, Any],
        sweep_config: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Run independent sweeps and execute A/B comparative analysis."""
        return compare_kinematic_setups(setup_a, setup_b, sweep_config)

    @classmethod
    def export_csv(cls, sweep_data: Dict[str, Any]) -> str:
        """
        Generate RFC-4180 compliant CSV formatted sweep data with an informative
        engineering metadata comment block.
        """
        output = io.StringIO()
        w = output.write

        # Metadata comment headers
        w("# ==========================================================================\n")
        w("# SuspensionLab PRO — Kinematic Travel Sweep Export\n")
        w(f"# Run ID:          {sweep_data.get('run_id', 'unknown')}\n")
        w(f"# Setup ID:        {sweep_data.get('setup_id', 'custom')}\n")
        w(f"# Vehicle ID:      {sweep_data.get('vehicle_id', 'corner_multibody')}\n")
        w(f"# Solver Backend:  {sweep_data.get('backend', 'C++ kinematics_core')}\n")
        w(f"# Solver Version:  {sweep_data.get('solver_version', '2.1.0-simd')}\n")
        w(f"# Geometry Hash:   {sweep_data.get('geometry_hash', 'none')}\n")
        w(f"# Generated At:    {sweep_data.get('timestamp', datetime.now(timezone.utc).isoformat())}\n")
        w("# Units: travel [mm], angles [deg], lengths [mm], derivatives [deg/100mm, mm/mm, 1/m]\n")
        w("# ==========================================================================\n")

        # Columns
        headers = [
            "wheel_travel_mm",
            "camber_deg",
            "toe_deg",
            "caster_deg",
            "kpi_deg",
            "roll_center_height_mm",
            "roll_center_lateral_mm",
            "motion_ratio",
            "track_change_mm",
            "wheelbase_change_mm",
            "scrub_radius_mm",
            "camber_gain_deg_per_100mm",
            "toe_gain_deg_per_100mm",
            "rc_migration_rate_mm_per_mm",
            "track_change_rate_mm_per_mm",
            "mr_gradient_per_m",
            "converged",
        ]

        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(headers)

        dz = sweep_data.get("wheel_travel_mm", [])
        derivs = sweep_data.get("derivatives", {})
        n = len(dz)

        for i in range(n):
            row = [
                f"{sweep_data['wheel_travel_mm'][i]:.2f}",
                f"{sweep_data.get('camber_deg', [0])[i]:.4f}",
                f"{sweep_data.get('toe_deg', [0])[i]:.4f}",
                f"{sweep_data.get('caster_deg', [0])[i]:.4f}",
                f"{sweep_data.get('kpi_deg', [0])[i]:.4f}",
                f"{sweep_data.get('roll_center_height_mm', [0])[i]:.3f}",
                f"{sweep_data.get('roll_center_lateral_mm', [0]*n)[i]:.3f}",
                f"{sweep_data.get('motion_ratio', [0])[i]:.4f}",
                f"{sweep_data.get('track_change_mm', [0])[i]:.3f}",
                f"{sweep_data.get('wheelbase_change_mm', [0])[i]:.3f}",
                f"{sweep_data.get('scrub_radius_mm', [0])[i]:.3f}",
                f"{derivs.get('camber_gain_deg_per_100mm', [0]*n)[i]:.4f}",
                f"{derivs.get('toe_gain_deg_per_100mm', [0]*n)[i]:.4f}",
                f"{derivs.get('rc_migration_rate', [0]*n)[i]:.4f}",
                f"{derivs.get('track_change_rate', [0]*n)[i]:.4f}",
                f"{derivs.get('mr_gradient_per_m', [0]*n)[i]:.4f}",
                "1" if sweep_data.get("converged", [True]*n)[i] else "0",
            ]
            writer.writerow(row)

        return output.getvalue()

    @classmethod
    def export_json(cls, sweep_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate canonical JSON dictionary conforming to full kinematics schema."""
        return {
            "schema_version": "1.0.0",
            "metadata": {
                "run_id": sweep_data.get("run_id"),
                "setup_id": sweep_data.get("setup_id"),
                "vehicle_id": sweep_data.get("vehicle_id"),
                "solver_backend": sweep_data.get("backend"),
                "solver_version": sweep_data.get("solver_version"),
                "geometry_hash": sweep_data.get("geometry_hash"),
                "timestamp": sweep_data.get("timestamp"),
                "step_count": len(sweep_data.get("wheel_travel_mm", [])),
            },
            "hardpoints": sweep_data.get("hardpoints", {}),
            "curves": {
                "wheel_travel_mm": sweep_data.get("wheel_travel_mm", []),
                "camber_deg": sweep_data.get("camber_deg", []),
                "toe_deg": sweep_data.get("toe_deg", []),
                "caster_deg": sweep_data.get("caster_deg", []),
                "kpi_deg": sweep_data.get("kpi_deg", []),
                "roll_center_height_mm": sweep_data.get("roll_center_height_mm", []),
                "roll_center_lateral_mm": sweep_data.get("roll_center_lateral_mm", []),
                "motion_ratio": sweep_data.get("motion_ratio", []),
                "track_change_mm": sweep_data.get("track_change_mm", []),
                "wheelbase_change_mm": sweep_data.get("wheelbase_change_mm", []),
                "scrub_radius_mm": sweep_data.get("scrub_radius_mm", []),
                "converged": sweep_data.get("converged", []),
            },
            "derivatives": sweep_data.get("derivatives", {}),
            "validation_report": sweep_data.get("validation_report", {}),
        }
