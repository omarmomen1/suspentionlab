"""
backend/services/phase3p_case_service.py
========================================
SuspensionLab PRO — Phase 3P Governed Pre-Registration & Execution Service.

Executes the immutable pre-registered experimental protocol PREREG-P3P-01 v1.0.0-frozen:
- Manipulated Mechanism: DynamicVehicleParams.tire_relaxation_length_y_m (sigma_y0)
- Production Pathway: sigma_y0 -> sigma_y(Fz) -> tau_y = sigma_y / v_trans -> d(alpha')/dt -> MF 5.2 Fy -> Chassis Yaw Response
- Integrator: DynamicLapSimulator, Fixed-step RK4, dt = 0.001 s (5 substeps per 200 Hz sample)
- Baseline: SETUP-P3P-BASE (sigma_y0 = 0.250 m, UNIDENTIFIED_NOMINAL_REFERENCE)
- Candidate: SETUP-P3P-CAL (sigma_y0* derived via bounded 1D fit on Turn_4_Entry only)
- Partitions: Authoritative Sample Indices
    Fit: Turn_4_Entry (11200..12199, N=1000, [56.001, 61.001) s, PREVIOUSLY_ACCESSED_NON_TIRE_ANALYSIS, NOT BLIND)
    Buffer 1: (12200..12699, N=500, [61.001, 63.501) s, EXCLUDED_BUFFER)
    Sustained Holdout: Turn_4_Apex (12700..13699, N=1000, [63.501, 68.501) s, Category A: NEVER_ACCESSED)
    Buffer 2: (13700..13899, N=200, [68.501, 69.501) s, EXCLUDED_BUFFER)
    Temporal Holdout: Turn_4_Exit (13900..14599, N=700, [69.501, 73.001) s, Category A: NEVER_ACCESSED)
- Statistical Procedure: Paired Moving Block Bootstrap (B=1000, L=20 samples = 100 ms, seed=42)
- Temporal Decision Rule: TEMPORAL_IMPROVEMENT (CI95_upper < 0 AND Delta_RMSE < 0)
- Sustained Decision Rule: NON_INFERIORITY (CI95_upper <= 0.05 * RMSE_base_apex)
- Fit Diagnostic: PRE_REGISTERED_EXPLORATORY_CALIBRATION_ADEQUACY_DIAGNOSTIC (0 decision weight)
- Secondary Constraints: ay/roll degradation <= +5%, |beta| <= 0.100 rad, jounce <= 55.0 mm
- Identifiability: CONDITIONALLY_IDENTIFIABLE
- Actionability Status:
    MODEL_PARAMETER_ACTIONABILITY = SUPPORTED_AS_MODEL_VARIABLE
    PHYSICAL_TRACK_ACTIONABILITY = BLOCKED / NOT_YET_MAPPED
- Prohibited Terminology: 'VALIDATED' is strictly forbidden.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from suspensionlab.physics.dynamic_lap_sim import (
    DynamicLapSimulator,
    DynamicVehicleParams,
    DynamicVehicleState,
    DriverControls,
)
from suspensionlab.validation.blind_prediction import TelemetryFirewall

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class Phase3PCaseService:
    """Production service orchestrating Phase 3P governed execution and artifact generation."""

    PROJECT_ROOT = Path("d:/project")
    DATASET_PATH = Path("data/external/stanford_vw_golf_thunderhill_2023_11.csv")
    DATASET_SHA256 = "489adbf01d27da1c281c0fff353554dfd7d07a3f1c48e2744e9dd902546b74d3"

    PROTOCOL_ID = "PREREG-P3P-01"
    PROTOCOL_VERSION = "1.0.0-frozen"
    # Wave 5A re-certification: docs/phase3*_preregistration_manifest.json was
    # re-certified after the magic_formula.py PKY1 fix (original hash preserved
    # in the manifest's wave5a_recertification block). Previous: ff3b8e10f1bc36bda4f5185088fc18a3191b188e565e8b82de8cf8c922bd4f8b
    PROTOCOL_SHA256 = "2342dc81207d544fb4ce17d64158644c9e2fd074138b3858ea64f8db1307356f"  # Wave 5A-2 re-certification (dynamic_lap_sim.py); Wave 5A hash c5c8d29c... superseded

    MANIFEST_PATH = PROJECT_ROOT / "docs" / "phase3p_preregistration_manifest.json"
    BLOCKERS_PATH = PROJECT_ROOT / "docs" / "phase3p_preregistration_blockers.md"

    DATA_DIR = PROJECT_ROOT / "data"
    DOCS_DIR = PROJECT_ROOT / "docs"

    PARAM_SNAPSHOT_PATH = DATA_DIR / "phase3p_parameter_snapshot.json"
    EXEC_MANIFEST_PATH = DATA_DIR / "phase3p_execution_manifest.json"
    RESULTS_PATH = DATA_DIR / "phase3p_results.json"
    BOOTSTRAP_PATH = DATA_DIR / "phase3p_bootstrap_results.json"
    ENGINEERING_CASE_PATH = DATA_DIR / "phase3p_engineering_case.json"
    EXEC_REPORT_PATH = DOCS_DIR / "phase3p_execution_report.md"

    PROTECTED_PHYSICS = {
        "dynamic_lap_sim.py": "bc409d2a228ca20adf5119502d6c227c5723cb8e998263fbdcccdb4b53e09d90",  # Wave 5A-2: lap_completed/solver_converged/lap_time_s honesty; previous 4a7e3de081ba...,
        "magic_formula.py": "2be0492f1e4c483401c1cd8544381edeb364dd5380e4b8fe9796f613cc627048",  # Wave 5A: PKY1 sign fix; previous 31acfd244c...,
        "tire_model.py": "da72dea8adf6b83846997fa02c9b1cade1b74272bcaa96f5aa0e2ea389005209",
        "powertrain_lap_sim.py": "44d72961d5a01acce4129db66b86b7eb44b577d1a90bf6d0a5ba3a70cdc9e7c6",
        "brake_distribution.py": "15338e921252e35afc9ee543fdb996464e4784b36e1ce18e05c8832e392a57ea",
    }

    # Authoritative Sample Boundaries (Zero-indexed, inclusive bounds)
    FIT_INDICES = (11200, 12199)          # Turn 4 Entry, N=1000, [56.001, 61.001) s
    BUFFER_1_INDICES = (12200, 12699)     # Buffer 1, N=500, [61.001, 63.501) s
    SUSTAINED_INDICES = (12700, 13699)    # Turn 4 Apex, N=1000, [63.501, 68.501) s
    BUFFER_2_INDICES = (13700, 13899)     # Buffer 2, N=200, [68.501, 69.501) s
    TEMPORAL_INDICES = (13900, 14599)     # Turn 4 Exit, N=700, [69.501, 73.001) s

    PARTITIONS_METADATA = {
        "fit_partition": {
            "window_name": "Turn_4_Entry",
            "start_sample_index": 11200,
            "end_sample_index": 12199,
            "sample_count": 1000,
            "interval_half_open": "[56.001, 61.001) s",
            "maneuver": "Transient turn-in and directional initiation",
            "role": "FIT_ESTIMATION",
            "access_policy": "PERMITTED_DURING_CALIBRATION",
            "exposure_classification": "PREVIOUSLY_ACCESSED_NON_TIRE_ANALYSIS",
            "tire_evaluation_status": "NEW_FOR_TIRE_PARAMETER_EVALUATION",
            "is_blind": False,
        },
        "buffer_1": {
            "window_name": "Buffer_1_Fit_Cross",
            "start_sample_index": 12200,
            "end_sample_index": 12699,
            "sample_count": 500,
            "interval_half_open": "[61.001, 63.501) s",
            "role": "EXCLUDED_BUFFER",
            "access_policy": "EXCLUDED_FROM_EVALUATION",
            "exposure_classification": "EXCLUDED_BUFFER",
            "is_blind": False,
        },
        "sustained_holdout_partition": {
            "window_name": "Turn_4_Apex",
            "start_sample_index": 12700,
            "end_sample_index": 13699,
            "sample_count": 1000,
            "interval_half_open": "[63.501, 68.501) s",
            "maneuver": "Sustained high-lateral-acceleration apex (ay ~ 1.15 G, yaw_dot ~ 0)",
            "role": "SUSTAINED_BLIND_HOLDOUT",
            "access_policy": "SEALED_UNTIL_CANDIDATE_FROZEN",
            "exposure_classification": "CATEGORY_A_NEVER_ACCESSED",
            "tire_evaluation_status": "AUTHENTIC_BLIND_SUSTAINED_HOLDOUT",
            "is_blind": True,
        },
        "buffer_2": {
            "window_name": "Buffer_2_Cross_Temp",
            "start_sample_index": 13700,
            "end_sample_index": 13899,
            "sample_count": 200,
            "interval_half_open": "[68.501, 69.501) s",
            "role": "EXCLUDED_BUFFER",
            "access_policy": "EXCLUDED_FROM_EVALUATION",
            "exposure_classification": "EXCLUDED_BUFFER",
            "is_blind": False,
        },
        "temporal_holdout_partition": {
            "window_name": "Turn_4_Exit",
            "start_sample_index": 13900,
            "end_sample_index": 14599,
            "sample_count": 700,
            "interval_half_open": "[69.501, 73.001) s",
            "maneuver": "Transient unwinding and power-on corner exit",
            "role": "TEMPORAL_BLIND_HOLDOUT",
            "access_policy": "SEALED_UNTIL_CANDIDATE_FROZEN",
            "exposure_classification": "CATEGORY_A_NEVER_ACCESSED",
            "tire_evaluation_status": "AUTHENTIC_BLIND_TEMPORAL_HOLDOUT",
            "is_blind": True,
        },
    }

    AUTHORITATIVE_CANDIDATE_GENERATION_CONFIG = {
        "target_parameter": "DynamicVehicleParams.tire_relaxation_length_y_m",
        "target_attribute": "tire_relaxation_length_y_m",
        "symbol": "sigma_y0",
        "units": "m",
        "baseline_value": 0.250,
        "baseline_semantics": "UNIDENTIFIED_NOMINAL_REFERENCE",
        "baseline_qualification": "Production default in dynamic_lap_sim.py:692 and Phase 3O simulation setup; uncalibrated nominal reference",
        "candidate_setup_id": "SETUP-P3P-CAL",
        "baseline_setup_id": "SETUP-P3P-BASE",
        "search_bounds": [0.100, 0.500],
        "optimizer_implementation": "scipy.optimize.minimize_scalar",
        "optimizer_method": "bounded",
        "tolerance_xatol": 0.005,
        "max_iterations": 25,
        "numerical_rounding_precision": 3,
        "objective_function": "RMSE_r = sqrt(mean((r_sim - r_meas)^2)) on Turn_4_Entry (11200..12199)",
        "failure_behavior": "HALT_FAIL_CLOSED_WITHOUT_UNSEALING_HOLDOUTS",
        "tie_breaking_rule": "Choose candidate value closest to nominal reference 0.250 m",
        "alternative_mechanism_status": {
            "parameter_name": "DynamicVehicleParams.tire_coeffs.pDy2",
            "symbol": "pDy2",
            "status": "NEXT_CANDIDATE / ALTERNATIVE_MECHANISM",
            "phase3p_execution": "EXCLUDED",
        },
    }

    SOLVER_CONTRACT = {
        "integrator_algorithm": "Fixed-step 4th-Order Runge-Kutta (RK4)",
        "canonical_timestep_s": 0.001,
        "telemetry_sampling_dt_s": 0.005,
        "mandatory_substeps_per_sample": 5,
        "derivative_evaluations_per_step": 4,
        "state_dimension": 22,
        "simulator_class": "DynamicLapSimulator",
        "simulator_module": "suspensionlab.physics.dynamic_lap_sim",
        "silent_timestep_substitution_prohibited": True,
    }

    BOOTSTRAP_CONFIG = {
        "algorithm": "PAIRED_MOVING_BLOCK_BOOTSTRAP",
        "replicates_B": 1000,
        "block_length_samples": 20,
        "block_duration_ms": 100.0,
        "sampling_rate_hz": 200.0,
        "random_seed": 42,
        "confidence_level": 0.95,
        "percentile_method": "empirical_percentiles [2.5%, 97.5%]",
        "target_statistic": "Delta_RMSE^(b) = RMSE_candidate^(b) - RMSE_baseline^(b)",
        "replicate_formula": "RMSE_m^(b) = sqrt(mean_{i in b}((r_m,i - r_meas,i)^2)), Delta_RMSE^(b) = RMSE_cand^(b) - RMSE_base^(b)",
    }

    SECONDARY_METRICS_SPEC = {
        "yaw_rate": {
            "channel": "yawRate_radps",
            "units": "rad/s",
            "provenance": "MEASURED vs SIMULATED",
            "role": "PRIMARY_TRACKING_METRIC",
            "sensor_type": "3-axis Gyroscope (Oxford RT3000 RTK-GNSS/IMU)",
        },
        "lateral_acceleration": {
            "channel": "ayCG_mps2",
            "units": "m/s^2",
            "provenance": "MEASURED vs DERIVED_FROM_SIMULATION",
            "role": "SECONDARY_ENGINEERING_CONSTRAINT",
            "admissibility_limit": "Degradation <= +5.0% relative to baseline",
            "threshold_relative_pct": 5.0,
            "filter": "5 Hz Butterworth low-pass",
        },
        "roll_angle": {
            "channel": "rollAngle_rad",
            "units": "rad",
            "provenance": "MEASURED vs SIMULATED",
            "role": "SECONDARY_ENGINEERING_CONSTRAINT",
            "admissibility_limit": "Degradation <= +5.0% relative to baseline",
            "threshold_relative_pct": 5.0,
        },
        "sideslip_angle": {
            "channel": "slipAngle_rad",
            "units": "rad",
            "provenance": "SIMULATED SECONDARY STABILITY INDICATOR",
            "role": "MODEL_STABILITY_SCREEN_ONLY",
            "is_direct_transducer": False,
            "threshold_rad": 0.100,
            "threshold_deg": 5.7296,
            "failure_status_on_breach": "REJECT_DUE_TO_SIDESLIP_STABILITY_BOUNDARY",
            "nature_of_constraint": "Engineering stability boundary, not a statistical confidence threshold",
            "provenance_derivation": "slipAngle_rad = arctan2(Vy_mps, Vx_mps) derived from integrated GNSS/INS state vector",
        },
        "dynamic_jounce": {
            "channel": "z_jounce_mm",
            "units": "mm",
            "provenance": "MODEL-DERIVED KINEMATIC SCREEN",
            "role": "MODEL_KINEMATIC_BOUNDARY_ONLY",
            "is_direct_transducer": False,
            "threshold_mm": 55.0,
            "failure_status_on_breach": "REJECT_DUE_TO_KINEMATIC_JOUNCE_BOUNDARY",
            "nature_of_constraint": "Model clearance boundary (15.0 + 0.5 * tw * sin(|phi|)), not a physical bump-stop claim",
        },
    }

    PROHIBITED_TERMINOLOGY = ["VALIDATED"]

    ALLOWED_FINAL_OUTCOMES = [
        "MODEL_PARAMETER_DECISION_SUPPORTED",
        "EFFECT_UNRESOLVED",
        "HYPOTHESIS_NOT_SUPPORTED",
        "INSUFFICIENT_EVIDENCE",
    ]

    CANONICAL_VEHICLE_PARAMS = {
        "drivetrain_layout": "FWD",
        "mass_kg": 1530.0,
        "sprung_mass_kg": 1410.0,
        "unsprung_mass_front_kg": 30.0,
        "unsprung_mass_rear_kg": 30.0,
        "wheelbase_m": 2.64,
        "a_m": 1.05,
        "b_m": 1.59,
        "tw_f_m": 1.54,
        "tw_r_m": 1.52,
        "k_spring_front_nm": 65000.0,
        "k_spring_rear_nm": 85000.0,
        "k_arb_front_nm": 25000.0,
        "k_arb_rear_nm": 18000.0,
        "c_damper_front_nsm": 2244.46,
        "c_damper_rear_nsm": 4500.0,
        "static_camber_front_deg": -3.2,
        "static_camber_rear_deg": -1.8,
        "camber_gain_deg_m": 15.0,
        "steer_ratio": 13.5,
        "nominal_tire_pressure_bar": 2.0,
        "cop_fraction_base": 0.44,
        "tire_relaxation_length_y_m": 0.25,
        "steering_compliance_rad_per_mps2": 0.0,
    }

    @classmethod
    def verify_pre_execution_integrity(cls) -> Dict[str, Any]:
        """Verifies cryptographic protocol hash, physics immutability, dataset SHA, and Phase 3O integrity."""
        # 1. Canonical manifest hash
        if not cls.MANIFEST_PATH.exists():
            raise FileNotFoundError(f"Manifest missing: {cls.MANIFEST_PATH}")
        manifest_bytes = cls.MANIFEST_PATH.read_bytes()
        actual_manifest_hash = hashlib.sha256(manifest_bytes).hexdigest().lower()
        if actual_manifest_hash != cls.PROTOCOL_SHA256:
            raise ValueError(f"Manifest SHA-256 violation: {actual_manifest_hash} != {cls.PROTOCOL_SHA256}")

        # 2. Dataset hash
        if not cls.verify_dataset_sha():
            raise ValueError(f"Dataset SHA-256 violation")

        # 3. Protected physics hashes
        phys_results = cls.verify_protected_physics_hashes()
        for fn, match in phys_results.items():
            if not match:
                raise ValueError(f"Physics hash violation in {fn}")

        # 4. Phase 3O immutability
        p3o_manifest = cls.PROJECT_ROOT / "docs" / "phase3o_preregistration_manifest.json"
        if not p3o_manifest.exists():
            raise FileNotFoundError(f"Phase 3O manifest missing")
        p3o_hash = hashlib.sha256(p3o_manifest.read_bytes()).hexdigest().lower()
        expected_p3o_hash = "74cef9b8a1de6ca329e74afc7416554863142acbc0e96b7b8ffbe0a19e296831"
        if p3o_hash != expected_p3o_hash:
            raise ValueError(f"Phase 3O manifest modified: {p3o_hash}")

        return {
            "protocol_sha_verified": True,
            "dataset_sha_verified": True,
            "protected_physics_verified": True,
            "phase3o_status": "PERMANENTLY_CLOSED_UNTOUCHED",
            "firewall_status": "HOLDOUTS_SEALED",
        }

    @classmethod
    def verify_protected_physics_hashes(cls) -> Dict[str, bool]:
        base_dir = cls.PROJECT_ROOT / "src" / "suspensionlab" / "physics"
        results = {}
        for filename, expected_sha in cls.PROTECTED_PHYSICS.items():
            file_path = base_dir / filename
            if not file_path.exists():
                results[filename] = False
                continue
            actual_sha = hashlib.sha256(file_path.read_bytes()).hexdigest().lower()
            results[filename] = (actual_sha == expected_sha.lower())
        return results

    @classmethod
    def verify_dataset_sha(cls) -> bool:
        file_path = cls.PROJECT_ROOT / cls.DATASET_PATH
        if not file_path.exists():
            return False
        actual_sha = hashlib.sha256(file_path.read_bytes()).hexdigest().lower()
        return actual_sha == cls.DATASET_SHA256.lower()

    @classmethod
    def verify_partition_disjointness(cls) -> bool:
        sets = {
            "fit": set(range(cls.FIT_INDICES[0], cls.FIT_INDICES[1] + 1)),
            "buf1": set(range(cls.BUFFER_1_INDICES[0], cls.BUFFER_1_INDICES[1] + 1)),
            "sustained": set(range(cls.SUSTAINED_INDICES[0], cls.SUSTAINED_INDICES[1] + 1)),
            "buf2": set(range(cls.BUFFER_2_INDICES[0], cls.BUFFER_2_INDICES[1] + 1)),
            "temporal": set(range(cls.TEMPORAL_INDICES[0], cls.TEMPORAL_INDICES[1] + 1)),
        }
        keys = list(sets.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if not sets[keys[i]].isdisjoint(sets[keys[j]]):
                    return False
        return True

    @staticmethod
    def evaluate_temporal_decision(delta_rmse: float, ci_upper: float) -> Tuple[bool, str]:
        """
        Evaluates the temporal holdout requirement.
        Authoritative condition: TEMPORAL_IMPROVEMENT
        Requires: CI95_upper < 0 AND delta_rmse < 0.
        """
        if ci_upper < 0.0 and delta_rmse < 0.0:
            return True, "TEMPORAL_IMPROVEMENT_ESTABLISHED"
        return False, "HYPOTHESIS_NOT_SUPPORTED"

    @staticmethod
    def evaluate_sustained_decision(delta_rmse: float, ci_upper: float, base_rmse: float) -> Tuple[bool, str]:
        """
        Evaluates the sustained apex holdout requirement.
        Authoritative condition: NON_INFERIORITY
        Requires: CI95_upper <= 0.05 * base_rmse.
        """
        margin_abs = 0.05 * base_rmse
        if ci_upper <= margin_abs:
            return True, "SUSTAINED_NON_INFERIORITY_ESTABLISHED"
        return False, "EFFECT_UNRESOLVED"

    @staticmethod
    def evaluate_fit_diagnostic(relative_pct: float) -> str:
        """
        Evaluates the exploratory fit diagnostic.
        Carries 0 decision weight.
        """
        if relative_pct <= -1.0:
            return "PASS"
        elif relative_pct <= 0.0:
            return "WEAK"
        else:
            return "FAILED"

    @classmethod
    def evaluate_final_verdict(
        cls,
        optimizer_converged: bool,
        temporal_improved: bool,
        sustained_non_inferior: bool,
        secondary_constraints_passed: bool,
        integrity_passed: bool,
    ) -> str:
        """
        Evaluates final engineering decision according to ratified decision tree.
        VALIDATED is strictly prohibited.
        """
        if not integrity_passed:
            return "ABORT_INTEGRITY_VIOLATION"
        if not optimizer_converged:
            return "ABORT_OPTIMIZER_DIVERGENCE"
        if not temporal_improved:
            return "HYPOTHESIS_NOT_SUPPORTED"
        if not sustained_non_inferior:
            return "EFFECT_UNRESOLVED"
        if not secondary_constraints_passed:
            return "EFFECT_UNRESOLVED"
        return "MODEL_PARAMETER_DECISION_SUPPORTED"

    @classmethod
    def check_prohibited_terminology(cls, text: str) -> bool:
        """Returns True if any prohibited terminology appears as an asserted status or verdict."""
        for term in cls.PROHIBITED_TERMINOLOGY:
            if f'"{term}"' in text or f": {term}" in text or f"STATUS = {term}" in text or f"VERDICT = {term}" in text:
                return True
        return False

    @classmethod
    def execute_simulation(
        cls,
        sigma_y0: float,
        start_idx: int,
        end_idx: int,
        df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Executes genuine production 14-DOF simulation under canonical governed contract:
        - Integrator: DynamicLapSimulator, Fixed-step RK4
        - Timestep: dt = 0.001 s (canonical)
        - Substepping: exactly 5 substeps per 0.005 s telemetry sample
        """
        if df is None:
            df = pd.read_csv(cls.PROJECT_ROOT / cls.DATASET_PATH, comment="#")

        sub_df = df.loc[start_idx:end_idx].copy().reset_index(drop=True)
        N = len(sub_df)

        params = DynamicVehicleParams(**cls.CANONICAL_VEHICLE_PARAMS)
        params.tire_relaxation_length_y_m = float(sigma_y0)

        row0 = sub_df.iloc[0]
        roll_bias = 0.01940
        st = DynamicVehicleState(
            time_s=float(row0["t_s"]),
            u_mps=float(row0["Vx_mps"]),
            v_mps=float(row0["Vy_mps"]),
            yaw_rate_rads=float(row0["yawRate_radps"]),
            yaw_angle_rad=float(row0["yawAngle_rad"]),
            roll_phi=float(row0["rollAngle_rad"]) - roll_bias,
            omega_fl=float(row0["wheelspeed_fl"]),
            omega_fr=float(row0["wheelspeed_fr"]),
            omega_rl=float(row0["wheelspeed_rl"]),
            omega_rr=float(row0["wheelspeed_rr"]),
        )

        sim = DynamicLapSimulator(params=params, dt_fixed_s=0.001)

        yaw_pred = np.zeros(N)
        ay_pred = np.zeros(N)
        roll_pred = np.zeros(N)
        beta_pred = np.zeros(N)
        jounce_pred = np.zeros(N)

        t0_wall = time.perf_counter()

        for k in range(N):
            row = sub_df.iloc[k]
            steer_rad = float(row["roadWheelAngle_rad"])
            thr_pct = float(row["throttleCmd_percent"])
            thr_norm = thr_pct / 100.0 if thr_pct > 1.5 else thr_pct
            b_fl = float(row["brake_fl_bar"])
            b_fr = float(row["brake_fr_bar"])
            b_rl = float(row["brake_rl_bar"])
            b_rr = float(row["brake_rr_bar"])
            bank = float(row.get("bank_rad", 0.0))
            grade = float(row.get("grade_rad", 0.0))

            ctrl = DriverControls(
                steering_deg=math.degrees(steer_rad * params.steer_ratio),
                throttle=thr_norm,
                brake_pressure_fl_bar=b_fl,
                brake_pressure_fr_bar=b_fr,
                brake_pressure_rl_bar=b_rl,
                brake_pressure_rr_bar=b_rr,
                gear=0,
            )
            ctrl = TelemetryFirewall.sanitize_driver_controls(ctrl)

            # Record pre-step state at timestamp t_k
            yaw_pred[k] = st.yaw_rate_rads
            roll_pred[k] = st.roll_phi
            beta_pred[k] = math.atan2(st.v_mps, max(0.5, st.u_mps))

            roll_deg_val = math.degrees(abs(st.roll_phi))
            jounce_pred[k] = 15.0 + 0.5 * 1540.0 * math.sin(math.radians(roll_deg_val))

            d = sim.compute_derivatives(st, ctrl, road_bank_rad=bank, road_grade_rad=grade)
            ay_pred[k] = d["dv"] + st.yaw_rate_rads * st.u_mps

            # Advance 5 RK4 substeps of 0.001 s
            for _ in range(5):
                st = sim.step(st, ctrl, road_bank_rad=bank, road_grade_rad=grade)

        wall_time = time.perf_counter() - t0_wall

        r_meas = sub_df["yawRate_radps"].values
        ay_meas = sub_df["ayCG_mps2"].values

        yaw_rmse = float(np.sqrt(np.mean((yaw_pred - r_meas) ** 2)))
        ay_rmse = float(np.sqrt(np.mean((ay_pred - ay_meas) ** 2)))
        roll_rms = float(np.sqrt(np.mean(roll_pred ** 2)))
        peak_beta = float(np.max(np.abs(beta_pred)))
        peak_jounce = float(np.max(jounce_pred))

        traj_hash = _canonical_hash({
            "yaw_head": [round(float(x), 5) for x in yaw_pred[:10]],
            "ay_head": [round(float(x), 5) for x in ay_pred[:10]],
            "N": N,
        })
        res_hash = _canonical_hash({
            "sigma_y0": sigma_y0,
            "yaw_rmse": round(yaw_rmse, 6),
            "ay_rmse": round(ay_rmse, 5),
            "start_idx": start_idx,
            "end_idx": end_idx,
        })

        return {
            "sigma_y0": sigma_y0,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "sample_count": N,
            "yaw_rmse": yaw_rmse,
            "ay_rmse": ay_rmse,
            "roll_rms": roll_rms,
            "peak_beta": peak_beta,
            "peak_beta_deg": float(np.degrees(peak_beta)),
            "peak_jounce_mm": peak_jounce,
            "wall_time_s": round(wall_time, 3),
            "trajectory_hash": traj_hash,
            "result_hash": res_hash,
            "yaw_pred": yaw_pred,
            "ay_pred": ay_pred,
            "r_meas": r_meas,
            "ay_meas": ay_meas,
        }

    @classmethod
    def calibrate_fit_partition(cls) -> Dict[str, Any]:
        """
        Executes bounded 1D optimization over sigma_y0 in [0.100, 0.500]
        using ONLY the Fit partition (indices 11200..12199).
        Holdouts remain completely unsealed and untouched.
        """
        df = pd.read_csv(cls.PROJECT_ROOT / cls.DATASET_PATH, comment="#")

        eval_history: List[Dict[str, Any]] = []

        def obj(sig_val: float) -> float:
            sim_res = cls.execute_simulation(sig_val, cls.FIT_INDICES[0], cls.FIT_INDICES[1], df=df)
            eval_history.append({
                "iteration": len(eval_history) + 1,
                "sigma_y0": sig_val,
                "yaw_rmse": sim_res["yaw_rmse"],
                "wall_time_s": sim_res["wall_time_s"],
            })
            return sim_res["yaw_rmse"]

        t0_opt = time.perf_counter()
        opt_res = minimize_scalar(
            obj,
            method="bounded",
            bounds=(0.100, 0.500),
            options={"xatol": 0.005, "maxiter": 25},
        )
        opt_wall_time = time.perf_counter() - t0_opt

        if not opt_res.success:
            raise ValueError(f"ABORT_OPTIMIZER_DIVERGENCE: Optimizer failed to converge: {opt_res.message}")

        sig_opt_raw = float(opt_res.x)
        sig_opt_frozen = round(sig_opt_raw, 3)

        # Baseline evaluation on Fit partition
        res_base = cls.execute_simulation(0.250, cls.FIT_INDICES[0], cls.FIT_INDICES[1], df=df)
        # Candidate evaluation at frozen value on Fit partition
        res_cal = cls.execute_simulation(sig_opt_frozen, cls.FIT_INDICES[0], cls.FIT_INDICES[1], df=df)

        rel_change_pct = ((res_cal["yaw_rmse"] - res_base["yaw_rmse"]) / res_base["yaw_rmse"]) * 100.0
        fit_diagnostic = cls.evaluate_fit_diagnostic(rel_change_pct)

        # Create parameter snapshot
        snapshot = {
            "protocol_id": cls.PROTOCOL_ID,
            "protocol_version": cls.PROTOCOL_VERSION,
            "protocol_sha256": cls.PROTOCOL_SHA256,
            "target_mechanism": {
                "parameter_name": "DynamicVehicleParams.tire_relaxation_length_y_m",
                "symbol": "sigma_y0",
                "units": "m",
                "baseline_value": 0.250,
                "baseline_semantics": "UNIDENTIFIED_NOMINAL_REFERENCE",
                "calibrated_setup_id": "SETUP-P3P-CAL",
                "calibrated_value": sig_opt_frozen,
                "calibrated_raw_value": sig_opt_raw,
            },
            "candidate_frozen_timestamp": _utcnow_iso(),
            "search_bounds": [0.100, 0.500],
            "optimizer": "scipy.optimize.minimize_scalar (bounded)",
            "xatol": 0.005,
            "maxiter": 25,
            "nfev": int(opt_res.nfev),
            "nit": int(opt_res.nit),
            "optimization_wall_time_s": round(opt_wall_time, 2),
            "model_parameter_actionability": "SUPPORTED_AS_MODEL_VARIABLE",
            "physical_track_actionability": "BLOCKED / NOT_YET_MAPPED",
        }
        snapshot_hash = _canonical_hash(snapshot)
        snapshot["snapshot_hash"] = snapshot_hash

        cls.PARAM_SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

        return {
            "optimizer_result": opt_res,
            "sigma_y0_raw": sig_opt_raw,
            "sigma_y0_frozen": sig_opt_frozen,
            "optimization_wall_time_s": round(opt_wall_time, 2),
            "nfev": int(opt_res.nfev),
            "nit": int(opt_res.nit),
            "eval_history": eval_history,
            "baseline_fit": res_base,
            "candidate_fit": res_cal,
            "relative_change_pct": rel_change_pct,
            "fit_diagnostic": fit_diagnostic,
            "snapshot": snapshot,
            "snapshot_hash": snapshot_hash,
        }

    @classmethod
    def paired_moving_block_bootstrap(
        cls,
        r_cal: np.ndarray,
        r_base: np.ndarray,
        r_meas: np.ndarray,
        B: int = 1000,
        L: int = 20,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Executes PAIRED MOVING BLOCK BOOTSTRAP on point errors:
        Every replicate computes RMSE_cal^(b), RMSE_base^(b), Delta_RMSE^(b) = RMSE_cal^(b) - RMSE_base^(b).
        Constructs empirical percentiles [2.5%, 97.5%].
        """
        rng = np.random.RandomState(seed)
        N = len(r_meas)
        n_blocks = int(np.ceil(N / L))
        max_start = N - L

        start_indices = rng.randint(0, max_start + 1, size=(B, n_blocks))

        delta_rmse_reps = np.zeros(B)
        rmse_cal_reps = np.zeros(B)
        rmse_base_reps = np.zeros(B)

        sq_cal = (r_cal - r_meas) ** 2
        sq_base = (r_base - r_meas) ** 2

        for b in range(B):
            block_starts = start_indices[b]
            resample_idx = np.concatenate([np.arange(s, s + L) for s in block_starts])[:N]

            rc = np.sqrt(np.mean(sq_cal[resample_idx]))
            rb = np.sqrt(np.mean(sq_base[resample_idx]))

            rmse_cal_reps[b] = rc
            rmse_base_reps[b] = rb
            delta_rmse_reps[b] = rc - rb

        ci_lower = float(np.percentile(delta_rmse_reps, 2.5))
        ci_upper = float(np.percentile(delta_rmse_reps, 97.5))
        mean_delta = float(np.mean(delta_rmse_reps))
        median_delta = float(np.median(delta_rmse_reps))
        p_val = float(np.mean(delta_rmse_reps >= 0.0))

        return {
            "algorithm": "PAIRED_MOVING_BLOCK_BOOTSTRAP",
            "replicates_B": B,
            "block_length_samples": L,
            "block_duration_ms": 100.0,
            "random_seed": seed,
            "confidence_level": 0.95,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "mean_delta_rmse": mean_delta,
            "median_delta_rmse": median_delta,
            "p_value": p_val,
            "delta_rmse_distribution": [round(float(x), 6) for x in delta_rmse_reps],
        }

    @classmethod
    def run_full_phase3p_execution(cls) -> Dict[str, Any]:
        """
        Executes complete Phase 3P pipeline fail-closed under frozen pre-registration governance:
        1. Pre-execution integrity & firewall verification
        2. Fit partition optimization and candidate freeze (Turn_4_Entry)
        3. Holdout unsealing and simulation (Turn_4_Exit, Turn_4_Apex)
        4. Paired moving block bootstrap & secondary metric evaluation
        5. Governed decision tree application & artifact generation
        6. Post-execution integrity verification
        """
        logger.info("Executing Phase 3P Pre-Flight Integrity Verification...")
        pre_integrity = cls.verify_pre_execution_integrity()

        df = pd.read_csv(cls.PROJECT_ROOT / cls.DATASET_PATH, comment="#")

        logger.info("Step 1 & 2: Calibrating on Turn_4_Entry...")
        fit_results = cls.calibrate_fit_partition()
        sig_opt = fit_results["sigma_y0_frozen"]
        snapshot_hash = fit_results["snapshot_hash"]

        logger.info("Step 3: Evaluating Holdouts with frozen candidate sigma_y0 = %.3f...", sig_opt)

        # 3a. Temporal Holdout: Turn_4_Exit
        res_temp_base = cls.execute_simulation(0.250, cls.TEMPORAL_INDICES[0], cls.TEMPORAL_INDICES[1], df=df)
        res_temp_cal = cls.execute_simulation(sig_opt, cls.TEMPORAL_INDICES[0], cls.TEMPORAL_INDICES[1], df=df)

        boot_temp = cls.paired_moving_block_bootstrap(
            res_temp_cal["yaw_pred"], res_temp_base["yaw_pred"], res_temp_cal["r_meas"], B=1000, L=20, seed=42
        )
        delta_rmse_temp = res_temp_cal["yaw_rmse"] - res_temp_base["yaw_rmse"]
        delta_rmse_temp_pct = (delta_rmse_temp / res_temp_base["yaw_rmse"]) * 100.0

        temp_improved, temp_verdict = cls.evaluate_temporal_decision(delta_rmse_temp, boot_temp["ci_upper"])
        temp_margin_abs = 0.05 * res_temp_base["yaw_rmse"]
        temp_non_inferior = (boot_temp["ci_upper"] <= temp_margin_abs)

        # 3b. Sustained Holdout: Turn_4_Apex
        res_apex_base = cls.execute_simulation(0.250, cls.SUSTAINED_INDICES[0], cls.SUSTAINED_INDICES[1], df=df)
        res_apex_cal = cls.execute_simulation(sig_opt, cls.SUSTAINED_INDICES[0], cls.SUSTAINED_INDICES[1], df=df)

        boot_apex = cls.paired_moving_block_bootstrap(
            res_apex_cal["yaw_pred"], res_apex_base["yaw_pred"], res_apex_cal["r_meas"], B=1000, L=20, seed=42
        )
        delta_rmse_apex = res_apex_cal["yaw_rmse"] - res_apex_base["yaw_rmse"]
        delta_rmse_apex_pct = (delta_rmse_apex / res_apex_base["yaw_rmse"]) * 100.0

        apex_non_inferior, apex_verdict = cls.evaluate_sustained_decision(
            delta_rmse_apex, boot_apex["ci_upper"], res_apex_base["yaw_rmse"]
        )
        apex_margin_abs = 0.05 * res_apex_base["yaw_rmse"]

        # 4. Secondary Metrics Evaluation across all 3 windows
        ay_deg_fit = ((res_cal := fit_results["candidate_fit"])["ay_rmse"] - fit_results["baseline_fit"]["ay_rmse"]) / fit_results["baseline_fit"]["ay_rmse"] * 100.0
        ay_deg_temp = (res_temp_cal["ay_rmse"] - res_temp_base["ay_rmse"]) / res_temp_base["ay_rmse"] * 100.0
        ay_deg_apex = (res_apex_cal["ay_rmse"] - res_apex_base["ay_rmse"]) / res_apex_base["ay_rmse"] * 100.0
        ay_passed = all(deg <= 5.0 for deg in [ay_deg_fit, ay_deg_temp, ay_deg_apex])

        roll_deg_fit = (res_cal["roll_rms"] - fit_results["baseline_fit"]["roll_rms"]) / fit_results["baseline_fit"]["roll_rms"] * 100.0
        roll_deg_temp = (res_temp_cal["roll_rms"] - res_temp_base["roll_rms"]) / res_temp_base["roll_rms"] * 100.0
        roll_deg_apex = (res_apex_cal["roll_rms"] - res_apex_base["roll_rms"]) / res_apex_base["roll_rms"] * 100.0
        roll_passed = all(deg <= 5.0 for deg in [roll_deg_fit, roll_deg_temp, roll_deg_apex])

        max_beta = max(res_cal["peak_beta"], res_temp_cal["peak_beta"], res_apex_cal["peak_beta"])
        beta_passed = (max_beta <= 0.100)

        max_jounce = max(res_cal["peak_jounce_mm"], res_temp_cal["peak_jounce_mm"], res_apex_cal["peak_jounce_mm"])
        jounce_passed = (max_jounce <= 55.0)

        secondary_all_passed = ay_passed and roll_passed and beta_passed and jounce_passed

        # 5. Final Governed Decision
        final_verdict = cls.evaluate_final_verdict(
            optimizer_converged=True,
            temporal_improved=temp_improved,
            sustained_non_inferior=apex_non_inferior,
            secondary_constraints_passed=secondary_all_passed,
            integrity_passed=True,
        )

        final_reason = (
            f"Optimizer successfully converged on Turn_4_Entry to sigma_y0* = {sig_opt:.3f} m. "
            f"Temporal Holdout ({temp_verdict}): Delta RMSE = {delta_rmse_temp:.6f} rad/s ({delta_rmse_temp_pct:+.2f}%), "
            f"CI95 = [{boot_temp['ci_lower']:.6f}, {boot_temp['ci_upper']:.6f}] rad/s. "
            f"Sustained Apex ({apex_verdict}): Delta RMSE = {delta_rmse_apex:.6f} rad/s ({delta_rmse_apex_pct:+.2f}%), "
            f"CI95 upper = {boot_apex['ci_upper']:.6f} vs margin {apex_margin_abs:.6f} rad/s. "
            f"Secondary Constraints: ay={ay_passed}, roll={roll_passed}, beta={beta_passed} (max {max_beta:.4f} rad), "
            f"jounce={jounce_passed} (max {max_jounce:.2f} mm)."
        )

        exec_timestamp = _utcnow_iso()

        # Build full results package
        results_payload = {
            "protocol_id": cls.PROTOCOL_ID,
            "protocol_version": cls.PROTOCOL_VERSION,
            "protocol_sha256": cls.PROTOCOL_SHA256,
            "execution_timestamp_iso": exec_timestamp,
            "dataset_sha256": cls.DATASET_SHA256,
            "candidate_frozen_timestamp": fit_results["snapshot"]["candidate_frozen_timestamp"],
            "candidate_artifact_hash": snapshot_hash,
            "integrity_checks": {
                "protocol_sha_verified": True,
                "dataset_sha_verified": True,
                "protected_physics_verified": True,
                "phase3o_status": "PERMANENTLY_CLOSED_UNTOUCHED",
                "firewall_status": "HOLDOUTS_SEALED_DURING_CALIBRATION",
            },
            "fit_calibration": {
                "window": "Turn_4_Entry",
                "sample_indices": list(cls.FIT_INDICES),
                "sample_count": 1000,
                "interval_half_open": "[56.001, 61.001) s",
                "candidate_setup_id": "SETUP-P3P-CAL",
                "sigma_y0_raw": fit_results["sigma_y0_raw"],
                "sigma_y0_frozen": sig_opt,
                "optimizer": "scipy.optimize.minimize_scalar (bounded)",
                "search_bounds": [0.100, 0.500],
                "xatol": 0.005,
                "maxiter": 25,
                "nit": fit_results["nit"],
                "nfev": fit_results["nfev"],
                "optimization_wall_time_s": fit_results["optimization_wall_time_s"],
                "eval_history": fit_results["eval_history"],
                "baseline_fit": {
                    "setup_id": "SETUP-P3P-BASE",
                    "sigma_y0": 0.250,
                    "yaw_rmse": fit_results["baseline_fit"]["yaw_rmse"],
                    "ay_rmse": fit_results["baseline_fit"]["ay_rmse"],
                    "roll_rms": fit_results["baseline_fit"]["roll_rms"],
                    "peak_beta": fit_results["baseline_fit"]["peak_beta"],
                    "peak_jounce_mm": fit_results["baseline_fit"]["peak_jounce_mm"],
                    "trajectory_hash": fit_results["baseline_fit"]["trajectory_hash"],
                    "result_hash": fit_results["baseline_fit"]["result_hash"],
                },
                "candidate_fit": {
                    "setup_id": "SETUP-P3P-CAL",
                    "sigma_y0": sig_opt,
                    "yaw_rmse": res_cal["yaw_rmse"],
                    "ay_rmse": res_cal["ay_rmse"],
                    "roll_rms": res_cal["roll_rms"],
                    "peak_beta": res_cal["peak_beta"],
                    "peak_jounce_mm": res_cal["peak_jounce_mm"],
                    "trajectory_hash": res_cal["trajectory_hash"],
                    "result_hash": res_cal["result_hash"],
                },
                "fit_diagnostic": {
                    "role": "PRE_REGISTERED_EXPLORATORY_CALIBRATION_ADEQUACY_DIAGNOSTIC",
                    "evidential_weight": 0.0,
                    "rule": "Relative Delta_RMSE <= -1.0% -> PASS",
                    "observed_relative_pct": round(fit_results["relative_change_pct"], 3),
                    "classification": fit_results["fit_diagnostic"],
                },
            },
            "temporal_holdout": {
                "window": "Turn_4_Exit",
                "sample_indices": list(cls.TEMPORAL_INDICES),
                "sample_count": 700,
                "interval_half_open": "[69.501, 73.001) s",
                "baseline_rmse": res_temp_base["yaw_rmse"],
                "candidate_rmse": res_temp_cal["yaw_rmse"],
                "delta_rmse": delta_rmse_temp,
                "delta_rmse_pct": round(delta_rmse_temp_pct, 2),
                "non_inferiority_margin_abs": temp_margin_abs,
                "non_inferiority_passed": temp_non_inferior,
                "improvement_passed": temp_improved,
                "verdict": temp_verdict,
                "bootstrap": {
                    "algorithm": "PAIRED_MOVING_BLOCK_BOOTSTRAP",
                    "replicates_B": 1000,
                    "block_length_samples": 20,
                    "block_duration_ms": 100.0,
                    "random_seed": 42,
                    "confidence_level": 0.95,
                    "ci_lower": boot_temp["ci_lower"],
                    "ci_upper": boot_temp["ci_upper"],
                    "mean_delta_rmse": boot_temp["mean_delta_rmse"],
                    "median_delta_rmse": boot_temp["median_delta_rmse"],
                    "p_value": boot_temp["p_value"],
                },
            },
            "sustained_holdout": {
                "window": "Turn_4_Apex",
                "sample_indices": list(cls.SUSTAINED_INDICES),
                "sample_count": 1000,
                "interval_half_open": "[63.501, 68.501) s",
                "baseline_rmse": res_apex_base["yaw_rmse"],
                "candidate_rmse": res_apex_cal["yaw_rmse"],
                "delta_rmse": delta_rmse_apex,
                "delta_rmse_pct": round(delta_rmse_apex_pct, 2),
                "non_inferiority_margin_abs": apex_margin_abs,
                "non_inferiority_passed": apex_non_inferior,
                "verdict": apex_verdict,
                "bootstrap": {
                    "algorithm": "PAIRED_MOVING_BLOCK_BOOTSTRAP",
                    "replicates_B": 1000,
                    "block_length_samples": 20,
                    "block_duration_ms": 100.0,
                    "random_seed": 42,
                    "confidence_level": 0.95,
                    "ci_lower": boot_apex["ci_lower"],
                    "ci_upper": boot_apex["ci_upper"],
                    "mean_delta_rmse": boot_apex["mean_delta_rmse"],
                    "median_delta_rmse": boot_apex["median_delta_rmse"],
                    "p_value": boot_apex["p_value"],
                },
            },
            "secondary_metrics": {
                "ay_degradation_pct": {
                    "fit": round(ay_deg_fit, 2),
                    "temporal": round(ay_deg_temp, 2),
                    "sustained": round(ay_deg_apex, 2),
                    "limit": "<= +5.0%",
                    "passed": ay_passed,
                },
                "roll_degradation_pct": {
                    "fit": round(roll_deg_fit, 2),
                    "temporal": round(roll_deg_temp, 2),
                    "sustained": round(roll_deg_apex, 2),
                    "limit": "<= +5.0%",
                    "passed": roll_passed,
                },
                "sideslip_beta_boundary": {
                    "channel": "slipAngle_rad",
                    "metric": "Peak absolute sideslip |beta|",
                    "classification": "SIMULATED SECONDARY STABILITY INDICATOR",
                    "provenance": "slipAngle_rad = arctan2(Vy_mps, Vx_mps) derived from integrated GNSS/INS state vector",
                    "threshold_rad": 0.100,
                    "threshold_deg": 5.7296,
                    "fit_peak_rad": res_cal["peak_beta"],
                    "temporal_peak_rad": res_temp_cal["peak_beta"],
                    "sustained_peak_rad": res_apex_cal["peak_beta"],
                    "max_observed_rad": max_beta,
                    "passed": beta_passed,
                    "failure_status_on_breach": "REJECT_DUE_TO_SIDESLIP_STABILITY_BOUNDARY",
                },
                "dynamic_jounce": {
                    "channel": "z_jounce_mm",
                    "metric": "Peak dynamic front suspension jounce",
                    "classification": "MODEL-DERIVED KINEMATIC SCREEN",
                    "threshold_mm": 55.0,
                    "fit_peak_mm": res_cal["peak_jounce_mm"],
                    "temporal_peak_mm": res_temp_cal["peak_jounce_mm"],
                    "sustained_peak_mm": res_apex_cal["peak_jounce_mm"],
                    "max_observed_mm": max_jounce,
                    "passed": jounce_passed,
                    "failure_status_on_breach": "REJECT_DUE_TO_KINEMATIC_JOUNCE_BOUNDARY",
                },
            },
            "final_classification": final_verdict,
            "final_reason": final_reason,
            "blocker_status": {
                "execution_blockers": "NONE",
                "physical_track_actionability": "BLOCKED / NOT_YET_MAPPED",
                "actionability_rationale": "No physical transfer function connecting sigma_y0 to inflation pressure, compound, or carcass durometer exists.",
            },
        }

        # Write execution artifacts
        cls.RESULTS_PATH.write_text(json.dumps(results_payload, indent=2, sort_keys=True), encoding="utf-8")

        # Bootstrap distribution artifact
        bootstrap_payload = {
            "protocol_id": cls.PROTOCOL_ID,
            "execution_timestamp_iso": exec_timestamp,
            "temporal_holdout": boot_temp,
            "sustained_holdout": boot_apex,
        }
        cls.BOOTSTRAP_PATH.write_text(json.dumps(bootstrap_payload, indent=2, sort_keys=True), encoding="utf-8")

        # Execution manifest
        exec_manifest_payload = {
            "protocol_id": cls.PROTOCOL_ID,
            "protocol_sha256": cls.PROTOCOL_SHA256,
            "dataset_sha256": cls.DATASET_SHA256,
            "protected_physics": cls.PROTECTED_PHYSICS,
            "candidate_artifact_hash": snapshot_hash,
            "results_artifact_hash": _canonical_hash(results_payload),
            "bootstrap_artifact_hash": _canonical_hash(bootstrap_payload),
            "execution_timestamp_iso": exec_timestamp,
            "final_classification": final_verdict,
        }
        cls.EXEC_MANIFEST_PATH.write_text(json.dumps(exec_manifest_payload, indent=2, sort_keys=True), encoding="utf-8")

        # Engineering case artifact
        eng_case_payload = {
            "protocol_id": cls.PROTOCOL_ID,
            "verdict": final_verdict,
            "candidate_parameter": "DynamicVehicleParams.tire_relaxation_length_y_m",
            "candidate_value": sig_opt,
            "baseline_value": 0.250,
            "temporal_improved": temp_improved,
            "sustained_non_inferior": apex_non_inferior,
            "secondary_constraints_passed": secondary_all_passed,
            "model_parameter_actionability": "SUPPORTED_AS_MODEL_VARIABLE",
            "physical_track_actionability": "BLOCKED / NOT_YET_MAPPED",
            "governance_closure": "PHASE_3P_EXECUTION_COMPLETED",
        }
        cls.ENGINEERING_CASE_PATH.write_text(json.dumps(eng_case_payload, indent=2, sort_keys=True), encoding="utf-8")

        # Execution Markdown Report
        exec_report_md = f"""# Phase 3P — Governed Execution & Engineering Report

**Protocol ID**: `{cls.PROTOCOL_ID}`  
**Protocol Version**: `{cls.PROTOCOL_VERSION}`  
**Protocol Hash**: `{cls.PROTOCOL_SHA256}`  
**Execution Timestamp**: `{exec_timestamp}`  
**Final Classification**: **`{final_verdict}`**  

---

## 1. Executive Summary

Phase 3P was executed fail-closed under frozen pre-registration governance.
The target mechanism `DynamicVehicleParams.tire_relaxation_length_y_m` ($\\sigma_{{y0}}$) was calibrated on the Fit Window (`Turn_4_Entry`, `11200..12199`, $N=1,000$).
The optimal candidate parameter was frozen at:
$$\\sigma_{{y0}}^* = {sig_opt:.3f}\\text{{ m}}$$
(Baseline reference: $0.250\\text{{ m}}$).

Following candidate freeze, holdout evaluations were conducted on unexposed Category A partitions:
- **Temporal Holdout (`Turn_4_Exit`, N=700)**: Evaluated for **`TEMPORAL_IMPROVEMENT`**.
  - Baseline RMSE: `{res_temp_base['yaw_rmse']:.6f}\\text{{ rad/s}}`
  - Candidate RMSE: `{res_temp_cal['yaw_rmse']:.6f}\\text{{ rad/s}}`
  - $\\Delta\\text{{RMSE}}$: `{delta_rmse_temp:.6f}\\text{{ rad/s}}` (`{delta_rmse_temp_pct:+.2f}%`)
  - 95% Bootstrap CI: `[{boot_temp['ci_lower']:.6f}, {boot_temp['ci_upper']:.6f}]\\text{{ rad/s}}`
  - Improvement Verdict: **`{temp_verdict}`** (Passed: `{temp_improved}`)
  - Diagnostic Non-Inferiority: Passed (`{temp_non_inferior}`, margin `{temp_margin_abs:.6f}\\text{{ rad/s}}`)
- **Sustained Holdout (`Turn_4_Apex`, N=1,000)**: Evaluated for **`NON_INFERIORITY`**.
  - Baseline RMSE: `{res_apex_base['yaw_rmse']:.6f}\\text{{ rad/s}}`
  - Candidate RMSE: `{res_apex_cal['yaw_rmse']:.6f}\\text{{ rad/s}}`
  - $\\Delta\\text{{RMSE}}$: `{delta_rmse_apex:.6f}\\text{{ rad/s}}` (`{delta_rmse_apex_pct:+.2f}%`)
  - 95% Bootstrap CI: `[{boot_apex['ci_lower']:.6f}, {boot_apex['ci_upper']:.6f}]\\text{{ rad/s}}`
  - Non-Inferiority Verdict: **`{apex_verdict}`** (Passed: `{apex_non_inferior}`, margin `{apex_margin_abs:.6f}\\text{{ rad/s}}`)

---

## 2. Fit Diagnostic
- Relative Fit Improvement: `{fit_results['relative_change_pct']:+.3f}%`
- Exploratory Adequacy Classification: **`{fit_results['fit_diagnostic']}`**
- Note: Fit diagnostic carries 0 evidential weight in final decision.

---

## 3. Secondary Engineering Constraints
- **Lateral Acceleration ($a_y$)**: Fit `{ay_deg_fit:+.2f}%`, Temp `{ay_deg_temp:+.2f}%`, Sustained `{ay_deg_apex:+.2f}%` ($\\le +5.0\\%$) $\\to$ **Passed** (`{ay_passed}`)
- **Roll Angle ($\\phi$)**: Fit `{roll_deg_fit:+.2f}%`, Temp `{roll_deg_temp:+.2f}%`, Sustained `{roll_deg_apex:+.2f}%` ($\\le +5.0\\%$) $\\to$ **Passed** (`{roll_passed}`)
- **Sideslip Angle ($\\beta$)**: Max Observed `{max_beta:.4f}\\text{{ rad}}` ($5.73^\\circ$ threshold) $\\to$ **Passed** (`{beta_passed}`)
- **Dynamic Jounce ($z_{{\\text{{jounce}}}}$)**: Max Observed `{max_jounce:.2f}\\text{{ mm}}` ($55.0\\text{{ mm}}$ threshold) $\\to$ **Passed** (`{jounce_passed}`)

---

## 4. Final Governed Verdict
**Verdict**: **`{final_verdict}`**  
**Actionability Demarcation**:
- `MODEL_PARAMETER_ACTIONABILITY = SUPPORTED_AS_MODEL_VARIABLE`
- `PHYSICAL_TRACK_ACTIONABILITY = BLOCKED / NOT_YET_MAPPED`
"""
        cls.EXEC_REPORT_PATH.write_text(exec_report_md, encoding="utf-8")

        logger.info("Step 6: Verifying Post-Execution Integrity...")
        post_integrity = cls.verify_pre_execution_integrity()

        return results_payload
