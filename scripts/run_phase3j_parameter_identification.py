"""SuspensionLab PRO — Phase 3J Parameter Identification & Observability Runner.

Executes the complete parameter identification pipeline on authentic Stanford
VW Golf GTI Thunderhill telemetry:

1. Load authentic telemetry and map raw sensor channels to canonical names
2. Register candidate parameters (identifiable + deliberately unidentifiable)
3. Cryptographic calibration/holdout dataset isolation
4. Observability analysis (sensitivity matrix, Fisher rank, excitation coverage)
5. Refusal of unidentifiable parameters (zero fitted value)
6. Multi-start derivative-free optimization (Powell)
7. Local sensitivity & Fisher covariance uncertainty quantification
8. Blind holdout evaluation with frozen parameters (zero retuning)
9. Epistemic validity gating

Outputs:
- data/phase3j_calibration_manifest.json
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from suspensionlab.calibration.engine import (
    IdentificationConfig,
    ParameterIdentificationEngine,
)
from suspensionlab.calibration.optimizer import DerivativeFreeSolver
from suspensionlab.calibration.report import PhysicalCalibrationReport
from suspensionlab.physics.parameter_identification import simulate_quarter_car_response

RAW_DATA_PATH = PROJECT_ROOT / "data" / "external" / "stanford_vw_golf_thunderhill_2023_11.csv"
OUTPUT_MANIFEST_PATH = PROJECT_ROOT / "data" / "phase3j_calibration_manifest.json"

# Stanford raw INS column -> canonical name mapping
CHANNEL_MAP = {
    "t_s": "time",
    "Vx_mps": "Vx",
    "ayCG_mps2": "ay",
    "axCG_mps2": "ax",
    "azCG_mps2": "vert_g",
    "yawRate_radps": "yaw_rate",
    "roadWheelAngle_rad": "steering",
    "throttleCmd_percent": "throttle",
    "rollAngle_rad": "roll_angle",
}

# Vehicle nominal parameters for VW Golf GTI Mk7
VEHICLE_PARAMS = {
    "m_s": 330.0,       # quarter-car sprung mass (kg)
    "m_u": 42.0,        # unsprung mass (kg)
    "MR": 0.85,         # motion ratio
}


def build_canonical_telemetry(df_raw: pd.DataFrame) -> dict:
    """Map raw Stanford INS column names to canonical channel names."""
    telem = {}
    for raw_col, canonical in CHANNEL_MAP.items():
        if raw_col in df_raw.columns:
            arr = df_raw[raw_col].values.astype(np.float64)
            # Convert vertical acceleration to g-units
            if canonical == "vert_g":
                arr = arr / 9.81
            # Convert throttle percent to normalized [0, 1]
            if canonical == "throttle" and np.nanmax(arr) > 1.5:
                arr = arr / 100.0
            telem[canonical] = arr
    return telem


def make_quarter_car_evaluator(telem_full: dict):
    """Create a forward-model evaluator wrapping the 2-DOF quarter-car ODE.

    The evaluator takes (param_dict, telem_slice) and returns {channel: prediction_array}.
    It uses the vertical acceleration (vert_g) as the target observable, running
    a forward quarter-car simulation driven by a reconstructed road input.
    """
    def evaluator(param_dict: dict, telem_slice: dict) -> dict:
        t = np.asarray(telem_slice["time"], dtype=np.float64)
        n = len(t)
        if n < 2:
            return {"vert_g": np.zeros(n)}

        dt = float(np.median(np.diff(t)))
        dt = max(dt, 1e-4)

        # Extract parameters
        k_s = param_dict.get("spring_rate_front", 32000.0)
        c = param_dict.get("damper_bump_front", 2200.0)
        k_t = 210000.0  # fixed tire stiffness
        MR = VEHICLE_PARAMS["MR"]
        m_s = VEHICLE_PARAMS["m_s"]
        m_u = VEHICLE_PARAMS["m_u"]

        # Reconstruct road profile from measured vertical acceleration
        meas_vg = np.asarray(telem_slice.get("vert_g", np.zeros(n)), dtype=np.float64)
        a_detrend = meas_vg - np.mean(meas_vg)
        if np.std(a_detrend) > 1e-4:
            # Double-integrate acceleration to approximate road displacement
            v_est = np.cumsum(a_detrend) * dt
            v_detrend = v_est - np.linspace(v_est[0], v_est[-1], len(v_est))
            z_est = np.cumsum(v_detrend) * dt
            z_detrend = z_est - np.linspace(z_est[0], z_est[-1], len(z_est))
            z_amp = np.std(z_detrend)
            if z_amp > 1e-6:
                road_input = np.clip(
                    z_detrend * (0.015 / max(z_amp, 1e-4)), -0.040, 0.040
                )
            else:
                road_input = np.where(t > t[0] + 0.5, 0.015, 0.0)
        else:
            road_input = np.where(t > t[0] + 0.5, 0.015, 0.0)

        # Forward ODE simulation
        ddz_s, _ = simulate_quarter_car_response(
            m_s=m_s, k_s=k_s, c=c, k_t=k_t, MR=MR,
            t_eval=t, road_input=road_input, m_u=m_u,
        )

        # Convert to g-units
        sim_vert_g = ddz_s / 9.81
        return {"vert_g": sim_vert_g}

    return evaluator


def run_phase3j_identification():
    print("=" * 80)
    print("SUSPENSIONLAB PRO — PHASE 3J PARAMETER IDENTIFICATION & OBSERVABILITY")
    print("MODE: CONTROLLED IMPLEMENTATION | FULL PIPELINE")
    print("=" * 80)

    # 1. Load & verify authentic telemetry
    assert RAW_DATA_PATH.exists(), f"Raw telemetry not found: {RAW_DATA_PATH}"
    raw_bytes = RAW_DATA_PATH.read_bytes()
    provenance_hash = hashlib.sha256(raw_bytes).hexdigest()
    print(f"Dataset:         {RAW_DATA_PATH.name}")
    print(f"Provenance SHA:  {provenance_hash}")

    df_raw = pd.read_csv(RAW_DATA_PATH, comment="#")
    print(f"Total samples:   {len(df_raw)}")

    # 2. Extract a dynamic window with vertical excitation
    # Use Turn_5_Tight_Complex window: rich vertical & lateral dynamics
    t_start, t_end = 74.0, 83.0
    mask = (df_raw["t_s"] >= t_start) & (df_raw["t_s"] <= t_end)
    df_window = df_raw[mask].copy().reset_index(drop=True)
    print(f"Analysis window: t=[{t_start:.1f}, {t_end:.1f}]s ({len(df_window)} samples)")

    telem = build_canonical_telemetry(df_window)
    print(f"Canonical channels: {sorted(telem.keys())}")

    # Verify vertical excitation signal is present
    vg_std = float(np.std(telem["vert_g"]))
    print(f"vert_g std:      {vg_std:.4f} g")

    # 3. Configure parameter identification
    # Identifiable parameters: spring_rate_front, damper_bump_front
    # Deliberately unidentifiable: camber_stiffness_front (no camber sensor,
    # vertical vert_g target has zero camber sensitivity)
    candidate_params = [
        "spring_rate_front",
        "damper_bump_front",
        "camber_stiffness_front",  # Deliberate: must be refused as UNIDENTIFIABLE
    ]

    cfg = IdentificationConfig(
        candidate_parameters=candidate_params,
        target_channels=["vert_g"],
        nominal_overrides={
            "spring_rate_front": 27000.0,   # Perturbed -15% from nominal 32000
            "damper_bump_front": 1800.0,     # Perturbed -18% from nominal 2200
        },
        solver=DerivativeFreeSolver.POWELL,
        num_starts=3,
        max_iter=15,
        ftol=1e-4,
        holdout_ratio=0.25,
        guard_band_s=0.50,
        holdout_r2_threshold=0.40,
    )

    # 4. Build evaluator and run identification engine
    evaluator = make_quarter_car_evaluator(telem)
    engine = ParameterIdentificationEngine()

    print("\n--- Running Parameter Identification Pipeline ---")
    report = engine.identify_parameters(
        telemetry=telem,
        config=cfg,
        model_evaluator=evaluator,
        dataset_metadata={
            "source": "Stanford University DDL / Revs Program",
            "vehicle": "2017 VW Golf VII GTI Performance",
            "track": "Thunderhill Raceway Park",
            "provenance_hash": provenance_hash,
            "analysis_window": f"t=[{t_start}, {t_end}]s",
        },
    )

    # 5. Display results
    print("\n" + "=" * 80)
    print("PARAMETER IDENTIFICATION RESULTS")
    print("=" * 80)
    print(f"Validity Classification:  {report.validity_classification}")
    print(f"Is Validated:             {report.is_validated}")
    print(f"Unidentifiable Params:    {report.unidentifiable_parameters}")
    print(f"Partially Identifiable:   {report.partially_identifiable_parameters}")

    print("\n--- Fitted Parameters ---")
    for p_name, p_res in report.fitted_parameters.items():
        status_icon = "OK" if p_res.is_fitted else "X REFUSED"
        print(f"  [{status_icon}] {p_name}")
        print(f"       nominal:     {p_res.nominal_value:.1f} {p_res.units}")
        print(f"       calibrated:  {p_res.calibrated_value:.1f} {p_res.units}")
        print(f"       delta:       {p_res.delta_pct:+.2f}%")
        print(f"       observability: {p_res.observability_status}")
        if p_res.is_fitted:
            print(f"       std_error:   {p_res.std_error:.2f}")
            print(f"       CI_95:       [{p_res.ci_95[0]:.1f}, {p_res.ci_95[1]:.1f}]")
        if p_res.rejection_reason:
            print(f"       REASON:      {p_res.rejection_reason}")

    print("\n--- Residual Evolution ---")
    rc = report.residual_changes
    print(f"  Initial RMSE:     {rc.initial_train_rmse:.4f}")
    print(f"  Final RMSE:       {rc.final_train_rmse:.4f}")
    print(f"  RMSE Reduction:   {rc.rmse_reduction_pct:.1f}%")

    print("\n--- Holdout Performance ---")
    hp = report.holdout_performance
    print(f"  Train R2:         {hp.train_r2:.4f}")
    print(f"  Holdout R2:       {hp.holdout_r2:.4f}")
    print(f"  Holdout RMSE:     {hp.holdout_rmse:.4f}")
    print(f"  Gen Gap:          {hp.generalization_gap_pct:.1f}%")
    print(f"  Criteria Met:     {hp.criteria_satisfied}")
    print(f"  Verdict:          {hp.verdict}")

    print("\n--- Refusal Summary ---")
    for p_name, reason in report.refusal_summary.items():
        print(f"  {p_name}: {reason}")

    # 6. Export calibration manifest
    report.export_json(OUTPUT_MANIFEST_PATH)
    print(f"\nManifest exported: {OUTPUT_MANIFEST_PATH}")

    # 7. Integrity assertions
    # Requirement 3: camber_stiffness_front MUST be refused
    camber_res = report.fitted_parameters.get("camber_stiffness_front")
    if camber_res:
        assert camber_res.is_fitted is False, (
            "INTEGRITY VIOLATION: camber_stiffness_front was fitted despite "
            "having zero camber excitation in vertical vert_g target!"
        )
        print("\n[PASS] camber_stiffness_front correctly refused (UNIDENTIFIABLE)")

    # Requirement 12: Never report validated unless holdout criteria pass
    if not report.holdout_performance.criteria_satisfied:
        assert report.is_validated is False, (
            "EPISTEMIC VIOLATION: Report claims 'validated' but holdout criteria failed!"
        )
        print("[PASS] Epistemic governance: is_validated=False when holdout fails")
    else:
        print(f"[PASS] Holdout criteria satisfied. validity={report.validity_classification}")

    print("\n" + "=" * 80)
    print("PHASE 3J PARAMETER IDENTIFICATION COMPLETE")
    print("=" * 80)
    return report


if __name__ == "__main__":
    run_phase3j_identification()
