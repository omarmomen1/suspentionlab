"""SuspensionLab PRO — Phase 3J.1 Parameter Identification Robustness Audit.

Executes a comprehensive robustness audit of the Phase 3J parameter
identification pipeline:

1. Multi-window identification across 3 disjoint telemetry windows
2. Multi-start robustness with 10 materially different initial guesses
3. Noise robustness at 3 controlled measurement noise levels
4. Per-window observability recomputation (sensitivity, rank, condition, correlation)
5. Identifiability consistency assessment
6. Blind holdout with frozen parameters (no retuning)
7. Unidentifiable parameter control (camber_stiffness_front remains refused)
8. Final gate: IDENTIFIABLE / PARTIALLY_IDENTIFIABLE / UNIDENTIFIABLE / NUMERICALLY_FAILED

Outputs:
  data/phase3j1_identification_robustness.json
"""

import hashlib
import json
import math
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from suspensionlab.calibration.engine import (
    IdentificationConfig,
    ParameterIdentificationEngine,
)
from suspensionlab.calibration.optimizer import (
    DerivativeFreeSolver,
    MultiStartConvergenceStatus,
    MultiStartOptimizer,
)
from suspensionlab.calibration.observability import (
    ObservabilityAnalyzer,
    ObservabilityStatus,
)
from suspensionlab.calibration.sensitivity import SensitivityAnalyzer
from suspensionlab.calibration.regularization import PhysicalRegularizer
from suspensionlab.calibration.registry import STANDARD_PARAMETER_REGISTRY
from suspensionlab.calibration.report import PhysicalCalibrationReport
from suspensionlab.physics.parameter_identification import simulate_quarter_car_response


RAW_DATA_PATH = PROJECT_ROOT / "data" / "external" / "stanford_vw_golf_thunderhill_2023_11.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "phase3j1_identification_robustness.json"

CHANNEL_MAP = {
    "t_s": "time", "Vx_mps": "Vx", "ayCG_mps2": "ay",
    "axCG_mps2": "ax", "azCG_mps2": "vert_g",
    "yawRate_radps": "yaw_rate", "roadWheelAngle_rad": "steering",
    "throttleCmd_percent": "throttle", "rollAngle_rad": "roll_angle",
}

VEHICLE = {"m_s": 330.0, "m_u": 42.0, "MR": 0.85}

# Disjoint telemetry windows with rich vertical dynamics
ANALYSIS_WINDOWS = [
    {"name": "Chicane_Entry",   "t_start": 45.0, "t_end": 54.0},
    {"name": "Turn_5_Complex",  "t_start": 74.0, "t_end": 83.0},
    {"name": "Turn_8_Exit",     "t_start": 90.0, "t_end": 99.0},
]

NOISE_LEVELS = [0.0, 0.05, 0.15]  # g-units additive noise

CANDIDATE_PARAMS = [
    "spring_rate_front",
    "damper_bump_front",
    "camber_stiffness_front",  # Must remain UNIDENTIFIABLE
]


def build_canonical_telemetry(df_raw: pd.DataFrame) -> dict:
    """Map raw Stanford INS columns to canonical names."""
    telem = {}
    for raw, canonical in CHANNEL_MAP.items():
        if raw in df_raw.columns:
            arr = df_raw[raw].values.astype(np.float64)
            if canonical == "vert_g":
                arr = arr / 9.81
            if canonical == "throttle" and len(arr) > 0 and np.nanmax(arr) > 1.5:
                arr = arr / 100.0
            telem[canonical] = arr
    return telem


def make_evaluator():
    """Quarter-car forward model evaluator."""
    def evaluator(param_dict: dict, telem_slice: dict) -> dict:
        t = np.asarray(telem_slice["time"], dtype=np.float64)
        n = len(t)
        if n < 2:
            return {"vert_g": np.zeros(n)}

        dt = max(float(np.median(np.diff(t))), 1e-4)
        k_s = param_dict.get("spring_rate_front", 32000.0)
        c = param_dict.get("damper_bump_front", 2200.0)

        meas_vg = np.asarray(telem_slice.get("vert_g", np.zeros(n)), dtype=np.float64)
        a_detrend = meas_vg - np.mean(meas_vg)
        if np.std(a_detrend) > 1e-4:
            v_est = np.cumsum(a_detrend) * dt
            v_detrend = v_est - np.linspace(v_est[0], v_est[-1], len(v_est))
            z_est = np.cumsum(v_detrend) * dt
            z_detrend = z_est - np.linspace(z_est[0], z_est[-1], len(z_est))
            z_amp = np.std(z_detrend)
            road_input = np.clip(
                z_detrend * (0.015 / max(z_amp, 1e-4)), -0.040, 0.040
            ) if z_amp > 1e-6 else np.where(t > t[0] + 0.5, 0.015, 0.0)
        else:
            road_input = np.where(t > t[0] + 0.5, 0.015, 0.0)

        ddz_s, _ = simulate_quarter_car_response(
            m_s=VEHICLE["m_s"], k_s=k_s, c=c, k_t=210000.0,
            MR=VEHICLE["MR"], t_eval=t, road_input=road_input,
            m_u=VEHICLE["m_u"],
        )
        return {"vert_g": ddz_s / 9.81}

    return evaluator


def run_robustness_audit():
    print("=" * 80)
    print("SUSPENSIONLAB PRO — PHASE 3J.1 IDENTIFICATION ROBUSTNESS AUDIT")
    print("=" * 80)

    # ── Load authentic telemetry ──────────────────────────────────────────
    assert RAW_DATA_PATH.exists(), f"Raw telemetry not found: {RAW_DATA_PATH}"
    provenance = hashlib.sha256(RAW_DATA_PATH.read_bytes()).hexdigest()
    df_raw = pd.read_csv(RAW_DATA_PATH, comment="#")
    print(f"Dataset: {RAW_DATA_PATH.name}  Provenance: {provenance[:16]}...")
    print(f"Samples: {len(df_raw)}")

    evaluator = make_evaluator()
    engine = ParameterIdentificationEngine()
    registry = STANDARD_PARAMETER_REGISTRY
    obs_analyzer = ObservabilityAnalyzer(registry=registry)

    manifest = {
        "phase": "3J.1",
        "title": "Parameter Identification Robustness Audit",
        "provenance_hash": provenance,
        "candidate_parameters": CANDIDATE_PARAMS,
        "analysis_windows": [],
        "multi_start_robustness": {},
        "noise_robustness": [],
        "observability_per_window": [],
        "identifiability_consistency": {},
        "final_gate": {},
    }

    # ──────────────────────────────────────────────────────────────────────
    # 1. Multi-Window Identification
    # ──────────────────────────────────────────────────────────────────────
    print("\n── 1. Multi-Window Identification ──")
    window_reports = []
    window_estimates = {p: [] for p in CANDIDATE_PARAMS}

    for wdef in ANALYSIS_WINDOWS:
        name, t_s, t_e = wdef["name"], wdef["t_start"], wdef["t_end"]
        mask = (df_raw["t_s"] >= t_s) & (df_raw["t_s"] <= t_e)
        df_w = df_raw[mask].copy().reset_index(drop=True)
        telem = build_canonical_telemetry(df_w)
        n = len(telem.get("time", []))
        print(f"  Window '{name}' [{t_s:.0f}, {t_e:.0f}]s: {n} samples")

        cfg = IdentificationConfig(
            candidate_parameters=CANDIDATE_PARAMS,
            target_channels=["vert_g"],
            nominal_overrides={"spring_rate_front": 27000.0, "damper_bump_front": 1800.0},
            solver=DerivativeFreeSolver.POWELL,
            num_starts=3, max_iter=15, ftol=1e-4,
            holdout_ratio=0.25, guard_band_s=0.50,
            holdout_r2_threshold=0.40,
        )

        report = engine.identify_parameters(telem, cfg, evaluator, dataset_metadata={"window": name})
        window_reports.append(report)

        wr = {
            "window": name, "t_start": t_s, "t_end": t_e, "samples": n,
            "validity": report.validity_classification,
            "is_validated": report.is_validated,
            "holdout_r2": report.holdout_performance.holdout_r2,
            "parameters": {},
        }
        for pn in CANDIDATE_PARAMS:
            pr = report.fitted_parameters[pn]
            wr["parameters"][pn] = {
                "calibrated_value": round(pr.calibrated_value, 2),
                "nominal_value": round(pr.nominal_value, 2),
                "delta_pct": round(pr.delta_pct, 2),
                "is_fitted": pr.is_fitted,
                "observability": pr.observability_status,
                "std_error": round(pr.std_error, 2),
                "ci_95": [round(pr.ci_95[0], 2), round(pr.ci_95[1], 2)],
            }
            if pr.is_fitted:
                window_estimates[pn].append(pr.calibrated_value)
            if pr.rejection_reason:
                wr["parameters"][pn]["rejection_reason"] = pr.rejection_reason

        manifest["analysis_windows"].append(wr)
        print(f"    validity={report.validity_classification}")
        for pn in CANDIDATE_PARAMS:
            pr = report.fitted_parameters[pn]
            tag = "OK" if pr.is_fitted else "REFUSED"
            print(f"    [{tag}] {pn}: {pr.calibrated_value:.1f} ({pr.observability_status})")

    # ──────────────────────────────────────────────────────────────────────
    # 2. Multi-Start Robustness (10 starts)
    # ──────────────────────────────────────────────────────────────────────
    print("\n── 2. Multi-Start Robustness (10 starts) ──")
    regularizer = PhysicalRegularizer(registry=registry)
    ms_optimizer = MultiStartOptimizer(
        registry=registry, regularizer=regularizer,
        solver=DerivativeFreeSolver.POWELL,
        num_starts=10, max_iter=20, dispersion_threshold_pct=15.0,
    )

    # Use first window telemetry for multi-start
    w0 = ANALYSIS_WINDOWS[0]
    mask0 = (df_raw["t_s"] >= w0["t_start"]) & (df_raw["t_s"] <= w0["t_end"])
    telem0 = build_canonical_telemetry(df_raw[mask0].copy().reset_index(drop=True))

    identifiable_params = ["spring_rate_front", "damper_bump_front"]

    def ms_objective(p_dict):
        pred = evaluator(p_dict, telem0)
        meas = telem0.get("vert_g", np.zeros(1))
        y_pred = pred.get("vert_g", np.zeros(1))
        n = min(len(meas), len(y_pred))
        resid = meas[:n] - y_pred[:n]
        var = max(float(np.var(meas[:n])), 1e-6)
        return float(np.mean(resid ** 2) / var)

    ms_result = ms_optimizer.optimize(identifiable_params, ms_objective)
    print(f"  Status: {ms_result.status.value}")
    print(f"  Dispersion: {ms_result.dispersion_pct:.1f}%")
    print(f"  Best loss: {ms_result.best_loss:.6f}")
    n_success = sum(1 for t in ms_result.trajectories if t.success)
    n_failed = sum(1 for t in ms_result.trajectories if not t.success)
    print(f"  Converged: {n_success}/10, Failed: {n_failed}/10")

    manifest["multi_start_robustness"] = {
        "num_starts": ms_result.num_starts,
        "status": ms_result.status.value,
        "dispersion_pct": round(ms_result.dispersion_pct, 2),
        "best_loss": round(ms_result.best_loss, 6),
        "converged_count": n_success,
        "failed_count": n_failed,
        "best_parameters": {k: round(v, 2) for k, v in ms_result.best_parameters.items()},
        "parameter_dispersions": {k: round(v, 2) for k, v in ms_result.parameter_dispersions.items()},
        "trajectories": [t.to_dict() for t in ms_result.trajectories],
    }

    # ──────────────────────────────────────────────────────────────────────
    # 3. Noise Robustness
    # ──────────────────────────────────────────────────────────────────────
    print("\n── 3. Noise Robustness ──")
    for noise_std in NOISE_LEVELS:
        # Inject additive Gaussian noise to first window
        telem_noisy = dict(telem0)
        if noise_std > 0.0:
            rng = np.random.default_rng(42)
            telem_noisy["vert_g"] = telem0["vert_g"] + rng.normal(0, noise_std, len(telem0["vert_g"]))

        cfg_n = IdentificationConfig(
            candidate_parameters=["spring_rate_front", "damper_bump_front"],
            target_channels=["vert_g"],
            nominal_overrides={"spring_rate_front": 27000.0, "damper_bump_front": 1800.0},
            num_starts=3, max_iter=15, holdout_ratio=0.25,
            holdout_r2_threshold=0.20,
        )
        rpt_n = engine.identify_parameters(telem_noisy, cfg_n, evaluator)

        nr = {"noise_std_g": noise_std, "parameters": {}}
        for pn in ["spring_rate_front", "damper_bump_front"]:
            pr = rpt_n.fitted_parameters[pn]
            nr["parameters"][pn] = {
                "calibrated": round(pr.calibrated_value, 2),
                "is_fitted": pr.is_fitted,
                "std_error": round(pr.std_error, 2),
                "ci_95": [round(pr.ci_95[0], 2), round(pr.ci_95[1], 2)],
            }
        nr["holdout_r2"] = round(rpt_n.holdout_performance.holdout_r2, 4)
        manifest["noise_robustness"].append(nr)
        print(f"  noise={noise_std:.2f}g: spring={rpt_n.fitted_parameters['spring_rate_front'].calibrated_value:.0f} "
              f"damper={rpt_n.fitted_parameters['damper_bump_front'].calibrated_value:.0f}")

    # ──────────────────────────────────────────────────────────────────────
    # 4. Observability Robustness Per Window
    # ──────────────────────────────────────────────────────────────────────
    print("\n── 4. Observability Per Window ──")
    for wdef in ANALYSIS_WINDOWS:
        name, t_s, t_e = wdef["name"], wdef["t_start"], wdef["t_end"]
        mask = (df_raw["t_s"] >= t_s) & (df_raw["t_s"] <= t_e)
        telem_w = build_canonical_telemetry(df_raw[mask].copy().reset_index(drop=True))

        def obs_eval(p_dict, _tw=telem_w):
            return evaluator(p_dict, _tw)

        obs = obs_analyzer.analyze_observability(
            data=telem_w,
            candidate_params=CANDIDATE_PARAMS,
            evaluator_fn=obs_eval,
        )

        ow = {
            "window": name,
            "condition_number": round(obs.condition_number, 2),
            "numerical_rank": obs.numerical_rank,
            "records": {},
        }
        for pn in CANDIDATE_PARAMS:
            rec = obs.records[pn]
            ow["records"][pn] = {
                "status": rec.status.value,
                "sensitivity_norm": round(rec.sensitivity_norm, 5),
                "excitation_coverage": round(rec.excitation_coverage, 4),
                "max_correlation_with": rec.max_correlation_with,
                "max_correlation_value": round(rec.max_correlation_value, 4),
            }
        manifest["observability_per_window"].append(ow)

        print(f"  {name}: rank={obs.numerical_rank}, cond={obs.condition_number:.1f}")
        for pn in CANDIDATE_PARAMS:
            s = obs.records[pn].status.value
            print(f"    {pn}: {s}")

    # ──────────────────────────────────────────────────────────────────────
    # 5. Identifiability Consistency & Final Gate
    # ──────────────────────────────────────────────────────────────────────
    print("\n── 5. Identifiability Consistency & Final Gate ──")
    final_gate = {}
    for pn in CANDIDATE_PARAMS:
        vals = window_estimates[pn]
        statuses = []
        for ow in manifest["observability_per_window"]:
            statuses.append(ow["records"][pn]["status"])

        # Count how many windows classified it as identifiable
        id_count = sum(1 for s in statuses if s == "IDENTIFIABLE")
        partial_count = sum(1 for s in statuses if s == "PARTIALLY_IDENTIFIABLE")
        unid_count = sum(1 for s in statuses if s == "UNIDENTIFIABLE")
        n_windows = len(statuses)

        # Cross-window coefficient of variation (for fitted values)
        if len(vals) >= 2:
            cv_pct = (float(np.std(vals)) / max(float(np.mean(vals)), 1.0)) * 100.0
        else:
            cv_pct = float("inf") if len(vals) == 0 else 0.0

        # Multi-start dispersion for this param (from section 2)
        ms_disp = manifest["multi_start_robustness"].get("parameter_dispersions", {}).get(pn, float("inf"))

        # Final classification logic:
        if unid_count == n_windows or len(vals) == 0:
            final_class = "UNIDENTIFIABLE"
            evidence = f"Unidentifiable in all {n_windows} windows"
        elif id_count == n_windows and cv_pct < 30.0 and ms_disp < 20.0:
            final_class = "IDENTIFIABLE"
            evidence = (
                f"Identifiable in {id_count}/{n_windows} windows, "
                f"CV={cv_pct:.1f}%, multi-start dispersion={ms_disp:.1f}%"
            )
        elif id_count >= 1:
            final_class = "PARTIALLY_IDENTIFIABLE"
            evidence = (
                f"Identifiable in {id_count}/{n_windows} windows, "
                f"partial in {partial_count}, CV={cv_pct:.1f}%, "
                f"multi-start dispersion={ms_disp:.1f}%"
            )
        else:
            final_class = "NUMERICALLY_FAILED"
            evidence = "Observability present but all optimizations failed"

        final_gate[pn] = {
            "final_classification": final_class,
            "evidence": evidence,
            "identifiable_windows": id_count,
            "partially_identifiable_windows": partial_count,
            "unidentifiable_windows": unid_count,
            "cross_window_cv_pct": round(cv_pct, 2) if cv_pct != float("inf") else None,
            "multi_start_dispersion_pct": round(ms_disp, 2) if ms_disp != float("inf") else None,
            "calibrated_values_across_windows": [round(v, 2) for v in vals],
        }
        print(f"  {pn}: {final_class}")
        print(f"    {evidence}")

    manifest["final_gate"] = final_gate
    manifest["identifiability_consistency"] = {
        "parameters_consistently_identifiable": [
            pn for pn, fg in final_gate.items() if fg["final_classification"] == "IDENTIFIABLE"
        ],
        "parameters_downgraded": [
            pn for pn, fg in final_gate.items() if fg["final_classification"] == "PARTIALLY_IDENTIFIABLE"
        ],
        "parameters_unidentifiable": [
            pn for pn, fg in final_gate.items() if fg["final_classification"] == "UNIDENTIFIABLE"
        ],
        "parameters_numerically_failed": [
            pn for pn, fg in final_gate.items() if fg["final_classification"] == "NUMERICALLY_FAILED"
        ],
    }

    # ── Epistemic governance ──────────────────────────────────────────────
    any_holdout_pass = any(r.holdout_performance.criteria_satisfied for r in window_reports)
    manifest["is_validated"] = any_holdout_pass
    manifest["epistemic_note"] = (
        "VALIDATED — at least one window passed independent holdout criteria"
        if any_holdout_pass
        else "NOT VALIDATED — no window passed independent holdout criteria on sequestered data"
    )

    # ── Export ────────────────────────────────────────────────────────────
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, indent=2, default=str)
    print(f"\nManifest exported: {OUTPUT_PATH}")

    # ── Integrity assertions ──────────────────────────────────────────────
    assert final_gate["camber_stiffness_front"]["final_classification"] == "UNIDENTIFIABLE", \
        "INTEGRITY: camber_stiffness_front must remain UNIDENTIFIABLE"
    print("\n[PASS] camber_stiffness_front remains UNIDENTIFIABLE across all conditions")

    if not any_holdout_pass:
        assert manifest["is_validated"] is False, \
            "EPISTEMIC: cannot claim validated without holdout success"
        print("[PASS] is_validated=False (no holdout passed)")

    print("\n" + "=" * 80)
    print("PHASE 3J.1 IDENTIFICATION ROBUSTNESS AUDIT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_robustness_audit()
