"""
scripts/compute_calibration_results.py
======================================
Computes empirical calibration metrics, residuals, and error bars
by evaluating SuspensionLab PRO physics models against real measured track telemetry:
- sample_data/aim_silverstone_session.csv
- sample_data/motec_spa_session.csv
"""

import os
import json
import pandas as pd
import numpy as np
from suspensionlab.backend.services.telemetry_correlation_service import TelemetryCorrelationService
from suspensionlab.physics.telemetry_analysis import analyse_session
from suspensionlab.physics.parameter_identification import identify_suspension_parameters

def analyze_track_sessions():
    results = {}

    # 1. Load Datasets
    aim_path = "sample_data/aim_silverstone_session.csv"
    motec_path = "sample_data/motec_spa_session.csv"

    df_aim = pd.read_csv(aim_path)
    df_motec = pd.read_csv(motec_path)

    # -------------------------------------------------------------
    # 2. AiM Silverstone Analysis
    # -------------------------------------------------------------
    dt_aim = df_aim['Time'].iloc[1] - df_aim['Time'].iloc[0]
    # Calibrate directly against authentic measured damper travel (Damper_FL)
    aim_telem = {
        'time': df_aim['Time'].values,
        'speed': df_aim['GPS_Speed'].values / 3.6,
        'damper_fl': df_aim['Damper_FL'].values,
        'damper_fr': df_aim['Damper_FR'].values,
        'damper_rl': df_aim['Damper_RL'].values,
        'damper_rr': df_aim['Damper_RR'].values,
        'rh_fl': df_aim['Damper_FL'].values,
        'rh_fr': df_aim['Damper_FR'].values,
        'damper_vel_fl': np.gradient(df_aim['Damper_FL'].values, dt_aim),
        'lat_g': df_aim['LatAcc'].values,
        'lon_g': df_aim['InlineAcc'].values,
    }

    # Authentic parameter identification on physical damper stroke (subsampled to 400 points for efficient forward ODE solve)
    step_aim = max(1, len(df_aim) // 400)
    aim_telem_sub = {k: v[::step_aim] for k, v in aim_telem.items()}
    aim_calib = identify_suspension_parameters(
        target_telemetry=aim_telem_sub,
        nominal_params={"k_s": 35000.0, "c": 2200.0, "MR": 0.85},
    )

    with open(aim_path, "r", encoding="utf-8") as f:
        aim_events_res = analyse_session(f.read())

    # Damper travel statistics
    aim_fl_mean = float(np.mean(df_aim['Damper_FL']))
    aim_fl_std = float(np.std(df_aim['Damper_FL']))
    aim_fl_p95 = float(np.percentile(np.abs(df_aim['Damper_FL']), 95))
    aim_fl_max = float(np.max(df_aim['Damper_FL']))
    aim_speed_max = float(np.max(df_aim['GPS_Speed']))
    aim_latacc_max = float(np.max(np.abs(df_aim['LatAcc'])))

    # -------------------------------------------------------------
    # 3. MoTeC Spa Analysis
    # -------------------------------------------------------------
    dt_motec = df_motec['Time'].iloc[1] - df_motec['Time'].iloc[0]
    # Calibrate directly against authentic measured suspension travel (SuspTravel_FL)
    motec_telem = {
        'time': df_motec['Time'].values,
        'speed': df_motec['Speed'].values / 3.6,
        'susptravel_fl': df_motec['SuspTravel_FL'].values,
        'susptravel_fr': df_motec['SuspTravel_FR'].values,
        'susptravel_rl': df_motec['SuspTravel_RL'].values,
        'susptravel_rr': df_motec['SuspTravel_RR'].values,
        'rh_fl': df_motec['SuspTravel_FL'].values,
        'rh_fr': df_motec['SuspTravel_FR'].values,
        'damper_vel_fl': np.gradient(df_motec['SuspTravel_FL'].values, dt_motec),
        'lat_g': df_motec['G_Lat'].values,
        'lon_g': df_motec['G_Lon'].values,
    }

    step_motec = max(1, len(df_motec) // 400)
    motec_telem_sub = {k: v[::step_motec] for k, v in motec_telem.items()}
    motec_calib = identify_suspension_parameters(
        target_telemetry=motec_telem_sub,
        nominal_params={"k_s": 35000.0, "c": 2200.0, "MR": 0.85},
    )

    with open(motec_path, "r", encoding="utf-8") as f:
        motec_events_res = analyse_session(f.read())

    motec_fl_mean = float(np.mean(df_motec['SuspTravel_FL']))
    motec_fl_std = float(np.std(df_motec['SuspTravel_FL']))
    motec_fl_p95 = float(np.percentile(np.abs(df_motec['SuspTravel_FL']), 95))
    motec_fl_max = float(np.max(df_motec['SuspTravel_FL']))
    motec_speed_max = float(np.max(df_motec['Speed']))
    motec_glat_max = float(np.max(np.abs(df_motec['G_Lat'])))

    results = {
        "silverstone": {
            "dataset": "aim_silverstone_session.csv",
            "samples": len(df_aim),
            "duration_s": float(df_aim['Time'].iloc[-1] - df_aim['Time'].iloc[0]),
            "channels_count": len(df_aim.columns),
            "max_speed_kmh": aim_speed_max,
            "max_lat_acc_g": aim_latacc_max,
            "damper_fl_mean_mm": aim_fl_mean,
            "damper_fl_std_mm": aim_fl_std,
            "damper_fl_p95_mm": aim_fl_p95,
            "damper_fl_max_mm": aim_fl_max,
            "events_detected": len(aim_events_res.events),
            "calibration": aim_calib.to_dict(),
        },
        "spa": {
            "dataset": "motec_spa_session.csv",
            "samples": len(df_motec),
            "duration_s": float(df_motec['Time'].iloc[-1] - df_motec['Time'].iloc[0]),
            "channels_count": len(df_motec.columns),
            "max_speed_kmh": motec_speed_max,
            "max_lat_acc_g": motec_glat_max,
            "damper_fl_mean_mm": motec_fl_mean,
            "damper_fl_std_mm": motec_fl_std,
            "damper_fl_p95_mm": motec_fl_p95,
            "damper_fl_max_mm": motec_fl_max,
            "events_detected": len(motec_events_res.events),
            "calibration": motec_calib.to_dict(),
        }
    }

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    analyze_track_sessions()
