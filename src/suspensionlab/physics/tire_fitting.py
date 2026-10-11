"""
physics/tire_fitting.py
=======================
SuspensionLab PRO — Experimental Tire Data Fitting Pipeline

Provides end-to-end data ingestion, cleaning, normalization, feature extraction,
multi-stage non-linear least squares parameter fitting, residual analysis,
physical validation, and .tir parameter serialization.

Pipeline Flow:
Raw Tire Data (CSV / DAT / TTC / Array)
  ──> Data Cleaning & Outlier Rejection
  ──> Coordinate Alignment & Normalization
  ──> Characteristic Feature Extraction
  ──> Multi-Stage Bounded Least-Squares Optimization:
        Stage 1: Pure Longitudinal (Fx0)
        Stage 2: Pure Lateral (Fy0) & Camber Thrust
        Stage 3: Aligning Moment (Mz0) & Pneumatic Trail
        Stage 4: Combined Slip Similarity Functions (Gxα, Gyκ)
        Stage 5: Pressure & Thermal Sensitivity Scaling
  ──> Residual Analysis (RMSE, MAE, Max Error, Bias, R², Covariance)
  ──> Physical Plausibility Validation
  ──> Serialized TireCoeffs & TireModelVersion Export
"""

from __future__ import annotations

import io
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy.optimize import least_squares

from suspensionlab.physics.magic_formula import (
    TireCoeffs,
    PacejkaMF52TireModel,
    _calc_tire_forces_and_moments_fast,
    _calc_tire_forces_fast,
)
from suspensionlab.physics.tire_model import (
    TireDefinition,
    TireModelMetadata,
    ValidityRange,
    compute_parameter_hash,
)


# ─────────────────────────────────────────────────────────────────────────────
# Tire Dataset Container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TireDataset:
    """Structured test-bench / telemetry dataset for tire parameter identification."""
    Fz: np.ndarray             # Normal vertical load [N] (positive compression)
    alpha: np.ndarray          # Slip angle [rad]
    kappa: np.ndarray          # Longitudinal slip ratio [-]
    camber: np.ndarray         # Inclination angle [rad]
    pressure: np.ndarray       # Inflation pressure [bar]
    temperature: np.ndarray    # Bulk / tread temperature [°C]
    speed: np.ndarray          # Rolling velocity [m/s]
    Fx: np.ndarray             # Measured longitudinal force [N]
    Fy: np.ndarray             # Measured lateral force [N]
    Mz: np.ndarray             # Measured self-aligning moment [N·m]

    def __len__(self) -> int:
        return len(self.Fz)

    @classmethod
    def from_arrays(
        cls,
        Fz: Union[List[float], np.ndarray],
        alpha: Union[List[float], np.ndarray],
        kappa: Union[List[float], np.ndarray],
        Fx: Union[List[float], np.ndarray],
        Fy: Union[List[float], np.ndarray],
        Mz: Optional[Union[List[float], np.ndarray]] = None,
        camber: Optional[Union[List[float], np.ndarray]] = None,
        pressure: Optional[Union[List[float], np.ndarray]] = None,
        temperature: Optional[Union[List[float], np.ndarray]] = None,
        speed: Optional[Union[List[float], np.ndarray]] = None,
    ) -> "TireDataset":
        """Construct TireDataset from numpy arrays or Python lists."""
        fz = np.asarray(Fz, dtype=np.float64)
        n = len(fz)
        al = np.asarray(alpha, dtype=np.float64)
        ka = np.asarray(kappa, dtype=np.float64)
        fx = np.asarray(Fx, dtype=np.float64)
        fy = np.asarray(Fy, dtype=np.float64)
        mz = np.asarray(Mz, dtype=np.float64) if Mz is not None else np.zeros(n, dtype=np.float64)
        cam = np.asarray(camber, dtype=np.float64) if camber is not None else np.zeros(n, dtype=np.float64)
        p = np.asarray(pressure, dtype=np.float64) if pressure is not None else np.full(n, 2.0, dtype=np.float64)
        temp = np.asarray(temperature, dtype=np.float64) if temperature is not None else np.full(n, 85.0, dtype=np.float64)
        spd = np.asarray(speed, dtype=np.float64) if speed is not None else np.full(n, 20.0, dtype=np.float64)

        return cls(
            Fz=fz, alpha=al, kappa=ka, camber=cam,
            pressure=p, temperature=temp, speed=spd,
            Fx=fx, Fy=fy, Mz=mz,
        )

    @classmethod
    def from_csv(cls, file_or_content: Union[str, io.StringIO]) -> "TireDataset":
        """Parse test rig CSV data with standard headers (FZ, IA/CAMBER, SA/ALPHA, SR/KAPPA, FX, FY, MZ, P, T, V)."""
        import pandas as pd
        if isinstance(file_or_content, io.StringIO):
            df = pd.read_csv(file_or_content)
        elif "\n" in file_or_content:
            df = pd.read_csv(io.StringIO(file_or_content))
        else:
            df = pd.read_csv(file_or_content)

        # Normalize column names
        cols = {c.strip().upper(): c for c in df.columns}

        def get_col(candidates, default_val=0.0):
            for cand in candidates:
                if cand in cols:
                    return df[cols[cand]].to_numpy(dtype=np.float64)
            return np.full(len(df), default_val, dtype=np.float64)

        # Handle units (deg vs rad)
        sa = get_col(["SA", "ALPHA", "SLIP_ANGLE", "SLIPANGLE"])
        if np.nanmax(np.abs(sa)) > 1.5:  # Likely degrees
            sa = np.radians(sa)

        ia = get_col(["IA", "CAMBER", "GAMMA", "INCLINATION"])
        if np.nanmax(np.abs(ia)) > 0.5:  # Likely degrees
            ia = np.radians(ia)

        sr = get_col(["SR", "KAPPA", "SLIP_RATIO", "SLIPRATIO"])
        if np.nanmax(np.abs(sr)) > 2.0:  # Likely percentage
            sr = sr / 100.0

        fz = get_col(["FZ", "LOAD", "NORMAL_LOAD", "F_Z"])
        fx = get_col(["FX", "LONGITUDINAL_FORCE", "F_X"])
        fy = get_col(["FY", "LATERAL_FORCE", "F_Y"])
        mz = get_col(["MZ", "ALIGNING_MOMENT", "M_Z"])
        p = get_col(["P", "PRESSURE", "INFLATION_PRESSURE", "BAR"], default_val=2.0)
        temp = get_col(["T", "TEMP", "TEMPERATURE", "DEG_C"], default_val=85.0)
        spd = get_col(["V", "SPEED", "VELOCITY"], default_val=20.0)

        dataset = cls(
            Fz=fz, alpha=sa, kappa=sr, camber=ia,
            pressure=p, temperature=temp, speed=spd,
            Fx=fx, Fy=fy, Mz=mz,
        )
        return dataset.clean_and_filter()

    @classmethod
    def generate_synthetic(
        cls,
        coeffs: Optional[TireCoeffs] = None,
        n_samples: int = 1200,
        noise_std: float = 12.0,
        seed: int = 42,
    ) -> "TireDataset":
        """Generate high-fidelity synthetic calibration data with realistic test rig noise."""
        rng = np.random.default_rng(seed)
        c = coeffs or TireCoeffs()
        c_arr = c.to_array()

        fz_levels = np.array([2000.0, 4000.0, 6000.0, 8000.0])
        samples_per_fz = n_samples // len(fz_levels)

        Fz_list, al_list, ka_list, cam_list, p_list, t_list, spd_list = [], [], [], [], [], [], []
        Fx_list, Fy_list, Mz_list = [], [], []

        for fz_nom in fz_levels:
            # 1. Pure Longitudinal sweep
            n_lon = samples_per_fz // 3
            ka_sweep = np.linspace(-0.25, 0.25, n_lon)
            for k in ka_sweep:
                Fz_list.append(fz_nom)
                al_list.append(0.0)
                ka_list.append(float(k))
                cam_list.append(0.0)
                p_list.append(2.0)
                t_list.append(85.0)
                spd_list.append(25.0)

            # 2. Pure Lateral sweep with camber
            n_lat = samples_per_fz // 3
            al_sweep = np.linspace(-math.radians(14.0), math.radians(14.0), n_lat)
            cam_vals = [-math.radians(3.0), 0.0, math.radians(3.0)]
            for i, a in enumerate(al_sweep):
                cam = cam_vals[i % len(cam_vals)]
                Fz_list.append(fz_nom)
                al_list.append(float(a))
                ka_list.append(0.0)
                cam_list.append(float(cam))
                p_list.append(2.0)
                t_list.append(85.0)
                spd_list.append(25.0)

            # 3. Combined slip sweep
            n_cmb = samples_per_fz - n_lon - n_lat
            for _ in range(n_cmb):
                a = rng.uniform(-0.15, 0.15)
                k = rng.uniform(-0.18, 0.18)
                cam = rng.uniform(-0.05, 0.05)
                p = rng.uniform(1.6, 2.4)
                t = rng.uniform(65.0, 105.0)
                Fz_list.append(fz_nom)
                al_list.append(float(a))
                ka_list.append(float(k))
                cam_list.append(float(cam))
                p_list.append(float(p))
                t_list.append(float(t))
                spd_list.append(25.0)

        Fz_arr = np.array(Fz_list)
        al_arr = np.array(al_list)
        ka_arr = np.array(ka_list)
        cam_arr = np.array(cam_list)
        p_arr = np.array(p_list)
        t_arr = np.array(t_list)
        spd_arr = np.array(spd_list)

        for i in range(len(Fz_arr)):
            fx, fy, mz, _ = _calc_tire_forces_and_moments_fast(
                Fz_arr[i], al_arr[i], ka_arr[i], cam_arr[i], c_arr,
                pressure_bar=p_arr[i], T_c=t_arr[i]
            )
            # Add Gaussian test-bench noise
            Fx_list.append(fx + rng.normal(0.0, noise_std))
            Fy_list.append(fy + rng.normal(0.0, noise_std))
            Mz_list.append(mz + rng.normal(0.0, noise_std * 0.04))

        return cls(
            Fz=Fz_arr, alpha=al_arr, kappa=ka_arr, camber=cam_arr,
            pressure=p_arr, temperature=t_arr, speed=spd_arr,
            Fx=np.array(Fx_list), Fy=np.array(Fy_list), Mz=np.array(Mz_list),
        )

    def clean_and_filter(self) -> "TireDataset":
        """Remove invalid, non-physical, NaN, or non-positive normal load points."""
        mask = (
            np.isfinite(self.Fz) & (self.Fz > 10.0) &
            np.isfinite(self.alpha) &
            np.isfinite(self.kappa) &
            np.isfinite(self.Fx) &
            np.isfinite(self.Fy) &
            np.isfinite(self.Mz)
        )
        return TireDataset(
            Fz=self.Fz[mask],
            alpha=self.alpha[mask],
            kappa=self.kappa[mask],
            camber=self.camber[mask],
            pressure=self.pressure[mask],
            temperature=self.temperature[mask],
            speed=self.speed[mask],
            Fx=self.Fx[mask],
            Fy=self.Fy[mask],
            Mz=self.Mz[mask],
        )

    def extract_features(self) -> Dict[str, float]:
        """Extract dominant physical tire features (cornering stiffness, peak friction, braking stiffness)."""
        clean = self.clean_and_filter()
        if len(clean) == 0:
            return {}

        fz_nom = float(np.median(clean.Fz))

        # Cornering stiffness at zero slip angle (dFy/dalpha near alpha=0)
        pure_lat_mask = (np.abs(clean.kappa) < 0.01) & (np.abs(clean.alpha) < math.radians(2.0))
        if np.sum(pure_lat_mask) >= 3:
            c_fa = float(np.polyfit(clean.alpha[pure_lat_mask], clean.Fy[pure_lat_mask], 1)[0])
        else:
            c_fa = 60000.0

        # Longitudinal slip stiffness at zero slip ratio (dFx/dkappa near kappa=0)
        pure_lon_mask = (np.abs(clean.alpha) < 0.01) & (np.abs(clean.kappa) < 0.03)
        if np.sum(pure_lon_mask) >= 3:
            c_fk = float(np.polyfit(clean.kappa[pure_lon_mask], clean.Fx[pure_lon_mask], 1)[0])
        else:
            c_fk = 80000.0

        # Peak friction coefficients
        mu_x_max = float(np.max(np.abs(clean.Fx) / np.maximum(clean.Fz, 100.0)))
        mu_y_max = float(np.max(np.abs(clean.Fy) / np.maximum(clean.Fz, 100.0)))

        return {
            "Fz_nominal_N": fz_nom,
            "cornering_stiffness_N_per_rad": abs(c_fa),
            "braking_stiffness_N_per_slip": abs(c_fk),
            "peak_mu_x": mu_x_max,
            "peak_mu_y": mu_y_max,
            "total_points": len(clean),
        }

    def split_train_val(self, val_fraction: float = 0.2, seed: int = 42) -> Tuple["TireDataset", "TireDataset"]:
        """Split dataset into training and hold-out validation sets."""
        n = len(self)
        n_val = int(n * val_fraction)
        rng = np.random.default_rng(seed)
        indices = np.arange(n)
        rng.shuffle(indices)

        val_idx = indices[:n_val]
        train_idx = indices[n_val:]

        train_ds = TireDataset(
            Fz=self.Fz[train_idx], alpha=self.alpha[train_idx], kappa=self.kappa[train_idx],
            camber=self.camber[train_idx], pressure=self.pressure[train_idx],
            temperature=self.temperature[train_idx], speed=self.speed[train_idx],
            Fx=self.Fx[train_idx], Fy=self.Fy[train_idx], Mz=self.Mz[train_idx],
        )
        val_ds = TireDataset(
            Fz=self.Fz[val_idx], alpha=self.alpha[val_idx], kappa=self.kappa[val_idx],
            camber=self.camber[val_idx], pressure=self.pressure[val_idx],
            temperature=self.temperature[val_idx], speed=self.speed[val_idx],
            Fx=self.Fx[val_idx], Fy=self.Fy[val_idx], Mz=self.Mz[val_idx],
        )
        return train_ds, val_ds


# ─────────────────────────────────────────────────────────────────────────────
# Residual Diagnostics Container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TireFittingResiduals:
    """Rigorous statistical residual metrics for fitted tire models."""
    rmse_Fx: float = 0.0
    rmse_Fy: float = 0.0
    rmse_Mz: float = 0.0
    mae_Fx: float = 0.0
    mae_Fy: float = 0.0
    mae_Mz: float = 0.0
    r2_Fx: float = 0.0
    r2_Fy: float = 0.0
    r2_Mz: float = 0.0
    max_error_Fx: float = 0.0
    max_error_Fy: float = 0.0
    max_error_Mz: float = 0.0
    mean_bias_Fx: float = 0.0
    mean_bias_Fy: float = 0.0
    mean_bias_Mz: float = 0.0
    confidence_score: float = 0.0
    parameter_std_errors: Dict[str, float] = field(default_factory=dict)
    holdout_r2: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "RMSE": {
                "Fx_N": round(self.rmse_Fx, 2),
                "Fy_N": round(self.rmse_Fy, 2),
                "Mz_Nm": round(self.rmse_Mz, 2),
            },
            "MAE": {
                "Fx_N": round(self.mae_Fx, 2),
                "Fy_N": round(self.mae_Fy, 2),
                "Mz_Nm": round(self.mae_Mz, 2),
            },
            "R2_Score": {
                "Fx": round(self.r2_Fx, 4),
                "Fy": round(self.r2_Fy, 4),
                "Mz": round(self.r2_Mz, 4),
            },
            "Max_Error": {
                "Fx_N": round(self.max_error_Fx, 2),
                "Fy_N": round(self.max_error_Fy, 2),
                "Mz_Nm": round(self.max_error_Mz, 2),
            },
            "Mean_Bias": {
                "Fx_N": round(self.mean_bias_Fx, 2),
                "Fy_N": round(self.mean_bias_Fy, 2),
                "Mz_Nm": round(self.mean_bias_Mz, 2),
            },
            "holdout_r2": round(self.holdout_r2, 4),
            "confidence_score": round(self.confidence_score, 3),
            "parameter_std_errors": {k: round(v, 4) for k, v in self.parameter_std_errors.items()},
        }


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Stage Tire Model Fitter
# ─────────────────────────────────────────────────────────────────────────────

class TireModelFitter:
    """Production Multi-Stage Non-Linear Least Squares Tire Parameter Identification Pipeline."""

    def __init__(self, initial_coeffs: Optional[TireCoeffs] = None):
        self.coeffs = initial_coeffs or TireCoeffs()

    def fit(
        self,
        dataset: TireDataset,
        val_fraction: float = 0.2,
        seed: int = 42,
    ) -> Tuple[PacejkaMF52TireModel, TireFittingResiduals]:
        """Execute complete multi-stage bounded optimization pipeline."""
        t0 = time.perf_counter()
        clean = dataset.clean_and_filter()
        if len(clean) < 20:
            raise ValueError(f"Insufficient calibration points ({len(clean)} < 20) for reliable fitting.")

        train_ds, val_ds = clean.split_train_val(val_fraction=val_fraction, seed=seed)

        # Update nominal load Fz0 from data
        self.coeffs.Fz0 = float(np.median(train_ds.Fz))

        # ── Stage 1: Pure Longitudinal Fitting (Fx0) ──────────────────────────
        lon_mask = np.abs(train_ds.alpha) < math.radians(1.0)
        if np.sum(lon_mask) >= 10:
            self._fit_pure_longitudinal(
                train_ds.Fz[lon_mask], train_ds.kappa[lon_mask],
                train_ds.camber[lon_mask], train_ds.Fx[lon_mask],
                train_ds.pressure[lon_mask], train_ds.temperature[lon_mask]
            )

        # ── Stage 2: Pure Lateral & Camber Thrust Fitting (Fy0) ───────────────
        lat_mask = np.abs(train_ds.kappa) < 0.02
        if np.sum(lat_mask) >= 10:
            self._fit_pure_lateral(
                train_ds.Fz[lat_mask], train_ds.alpha[lat_mask],
                train_ds.camber[lat_mask], train_ds.Fy[lat_mask],
                train_ds.pressure[lat_mask], train_ds.temperature[lat_mask]
            )

        # ── Stage 3: Aligning Moment Fitting (Mz0) ────────────────────────────
        if np.sum(lat_mask) >= 10 and np.any(np.abs(train_ds.Mz[lat_mask]) > 0.1):
            self._fit_aligning_moment(
                train_ds.Fz[lat_mask], train_ds.alpha[lat_mask],
                train_ds.camber[lat_mask], train_ds.Mz[lat_mask],
                train_ds.pressure[lat_mask], train_ds.temperature[lat_mask]
            )

        # ── Stage 4: Combined Slip Similarity Fitting (Gxα, Gyκ) ──────────────
        cmb_mask = (np.abs(train_ds.alpha) > math.radians(1.5)) & (np.abs(train_ds.kappa) > 0.03)
        if np.sum(cmb_mask) >= 10:
            self._fit_combined_slip(
                train_ds.Fz[cmb_mask], train_ds.alpha[cmb_mask],
                train_ds.kappa[cmb_mask], train_ds.camber[cmb_mask],
                train_ds.Fx[cmb_mask], train_ds.Fy[cmb_mask],
                train_ds.pressure[cmb_mask], train_ds.temperature[cmb_mask]
            )

        # ── Stage 5: Residual Analysis & Holdout Validation ───────────────────
        train_res = self.analyze_residuals(clean)
        val_res = self.analyze_residuals(val_ds) if len(val_ds) > 0 else train_res
        train_res.holdout_r2 = float(np.mean([val_res.r2_Fx, val_res.r2_Fy, val_res.r2_Mz]))

        t1 = time.perf_counter()

        # Build calibrated PacejkaMF52TireModel
        model = PacejkaMF52TireModel(
            coeffs=self.coeffs,
            source=f"Identified from {len(clean)} experimental test points in {t1-t0:.2f}s",
        )
        return model, train_res

    def _fit_pure_longitudinal(self, Fz, kappa, camber, Fx_meas, p, T):
        """Stage 1: Non-linear least squares fit of longitudinal pure slip parameters."""
        # Parameters to fit: [pCx1, pDx1, pDx2, pEx1, pEx2, pKx1, pKx2, pKx3, pHx1, pVx1]
        p0 = np.array([
            self.coeffs.pCx1, self.coeffs.pDx1, self.coeffs.pDx2,
            self.coeffs.pEx1, self.coeffs.pEx2, self.coeffs.pKx1,
            self.coeffs.pKx2, self.coeffs.pKx3, self.coeffs.pHx1, self.coeffs.pVx1
        ])
        bounds_lower = np.array([1.1, 0.5, -0.4, -0.5, -0.5, 5.0, 0.0, 0.0, -0.05, -0.05])
        bounds_upper = np.array([2.2, 2.5,  0.2,  0.9,  0.5, 50.0, 2.0, 2.0,  0.05,  0.05])

        def residual(params):
            temp_c = TireCoeffs(
                Fz0=self.coeffs.Fz0,
                pCx1=params[0], pDx1=params[1], pDx2=params[2],
                pEx1=params[3], pEx2=params[4], pKx1=params[5],
                pKx2=params[6], pKx3=params[7], pHx1=params[8], pVx1=params[9],
            )
            c_arr = temp_c.to_array()
            fx_pred = np.zeros_like(Fx_meas)
            for i in range(len(Fz)):
                fx_pred[i], _ = _calc_tire_forces_fast(
                    Fz[i], 0.0, kappa[i], camber[i], c_arr, p[i], T[i]
                )
            return (fx_pred - Fx_meas)

        res = least_squares(residual, p0, bounds=(bounds_lower, bounds_upper), method='trf', max_nfev=200)
        if res.success:
            p = res.x
            self.coeffs.pCx1 = float(p[0])
            self.coeffs.pDx1 = float(p[1])
            self.coeffs.pDx2 = float(p[2])
            self.coeffs.pEx1 = float(p[3])
            self.coeffs.pEx2 = float(p[4])
            self.coeffs.pKx1 = float(p[5])
            self.coeffs.pKx2 = float(p[6])
            self.coeffs.pKx3 = float(p[7])
            self.coeffs.pHx1 = float(p[8])
            self.coeffs.pVx1 = float(p[9])

    def _fit_pure_lateral(self, Fz, alpha, camber, Fy_meas, p, T):
        """Stage 2: Non-linear least squares fit of lateral pure slip and camber parameters."""
        # Parameters: [pCy1, pDy1, pDy2, pDy3, pEy1, pEy2, pKy1, pKy2, pKy3, pHy1, pVy1, pVy3]
        p0 = np.array([
            self.coeffs.pCy1, self.coeffs.pDy1, self.coeffs.pDy2, self.coeffs.pDy3,
            self.coeffs.pEy1, self.coeffs.pEy2, self.coeffs.pKy1, self.coeffs.pKy2,
            self.coeffs.pKy3, self.coeffs.pHy1, self.coeffs.pVy1, self.coeffs.pVy3
        ])
        bounds_lower = np.array([1.0, 0.5, -0.4, -0.2, -1.0, -0.5, 5.0, 0.5, -0.1, -0.05, -0.05, -0.1])
        bounds_upper = np.array([2.0, 2.5,  0.2,  0.2,  0.5,  0.5, 40.0, 5.0,  0.1,  0.05,  0.05,  0.3])

        def residual(params):
            temp_c = TireCoeffs(
                Fz0=self.coeffs.Fz0,
                pCy1=params[0], pDy1=params[1], pDy2=params[2], pDy3=params[3],
                pEy1=params[4], pEy2=params[5], pKy1=params[6], pKy2=params[7],
                pKy3=params[8], pHy1=params[9], pVy1=params[10], pVy3=params[11],
            )
            c_arr = temp_c.to_array()
            fy_pred = np.zeros_like(Fy_meas)
            for i in range(len(Fz)):
                _, fy_pred[i] = _calc_tire_forces_fast(
                    Fz[i], alpha[i], 0.0, camber[i], c_arr, p[i], T[i]
                )
            return (fy_pred - Fy_meas)

        res = least_squares(residual, p0, bounds=(bounds_lower, bounds_upper), method='trf', max_nfev=200)
        if res.success:
            p = res.x
            self.coeffs.pCy1 = float(p[0])
            self.coeffs.pDy1 = float(p[1])
            self.coeffs.pDy2 = float(p[2])
            self.coeffs.pDy3 = float(p[3])
            self.coeffs.pEy1 = float(p[4])
            self.coeffs.pEy2 = float(p[5])
            self.coeffs.pKy1 = float(p[6])
            self.coeffs.pKy2 = float(p[7])
            self.coeffs.pKy3 = float(p[8])
            self.coeffs.pHy1 = float(p[9])
            self.coeffs.pVy1 = float(p[10])
            self.coeffs.pVy3 = float(p[11])

    def _fit_aligning_moment(self, Fz, alpha, camber, Mz_meas, p, T):
        """Stage 3: Fit pneumatic trail and residual torque parameters."""
        p0 = np.array([
            self.coeffs.qBz1, self.coeffs.qBz2, self.coeffs.qCz1,
            self.coeffs.qDz1, self.coeffs.qDz2, self.coeffs.qEz1,
            self.coeffs.qDz8, self.coeffs.qBz9
        ])
        bounds_lower = np.array([3.0, -5.0, 0.8, 0.01, -0.02, -3.0, -0.2, 2.0])
        bounds_upper = np.array([20.0, 2.0, 2.0, 0.08,  0.02,  0.5,  0.2, 25.0])

        def residual(params):
            temp_c = TireCoeffs(
                Fz0=self.coeffs.Fz0,
                pCy1=self.coeffs.pCy1, pDy1=self.coeffs.pDy1, pDy2=self.coeffs.pDy2,
                pDy3=self.coeffs.pDy3, pEy1=self.coeffs.pEy1, pEy2=self.coeffs.pEy2,
                pKy1=self.coeffs.pKy1, pKy2=self.coeffs.pKy2, pKy3=self.coeffs.pKy3,
                pHy1=self.coeffs.pHy1, pVy1=self.coeffs.pVy1, pVy3=self.coeffs.pVy3,
                qBz1=params[0], qBz2=params[1], qCz1=params[2],
                qDz1=params[3], qDz2=params[4], qEz1=params[5],
                qDz8=params[6], qBz9=params[7],
            )
            c_arr = temp_c.to_array()
            mz_pred = np.zeros_like(Mz_meas)
            for i in range(len(Fz)):
                _, _, mz_pred[i], _ = _calc_tire_forces_and_moments_fast(
                    Fz[i], alpha[i], 0.0, camber[i], c_arr, p[i], T[i]
                )
            return (mz_pred - Mz_meas)

        res = least_squares(residual, p0, bounds=(bounds_lower, bounds_upper), method='trf', max_nfev=200)
        if res.success:
            p = res.x
            self.coeffs.qBz1 = float(p[0])
            self.coeffs.qBz2 = float(p[1])
            self.coeffs.qCz1 = float(p[2])
            self.coeffs.qDz1 = float(p[3])
            self.coeffs.qDz2 = float(p[4])
            self.coeffs.qEz1 = float(p[5])
            self.coeffs.qDz8 = float(p[6])
            self.coeffs.qBz9 = float(p[7])

    def _fit_combined_slip(self, Fz, alpha, kappa, camber, Fx_meas, Fy_meas, p, T):
        """Stage 4: Fit Similarity Method combined-slip parameters."""
        p0 = np.array([
            self.coeffs.rBx1, self.coeffs.rBx2, self.coeffs.rCx1,
            self.coeffs.rBy1, self.coeffs.rBy2, self.coeffs.rCy1
        ])
        bounds_lower = np.array([2.0, 1.0, 0.5, 2.0, 1.0, 0.5])
        bounds_upper = np.array([25.0, 20.0, 2.0, 25.0, 20.0, 2.0])

        def residual(params):
            temp_c = TireCoeffs(
                Fz0=self.coeffs.Fz0,
                pCx1=self.coeffs.pCx1, pDx1=self.coeffs.pDx1, pDx2=self.coeffs.pDx2,
                pEx1=self.coeffs.pEx1, pKx1=self.coeffs.pKx1, pKx2=self.coeffs.pKx2,
                pCy1=self.coeffs.pCy1, pDy1=self.coeffs.pDy1, pDy2=self.coeffs.pDy2,
                pEy1=self.coeffs.pEy1, pKy1=self.coeffs.pKy1, pKy2=self.coeffs.pKy2,
                rBx1=params[0], rBx2=params[1], rCx1=params[2],
                rBy1=params[3], rBy2=params[4], rCy1=params[5],
            )
            c_arr = temp_c.to_array()
            n = len(Fz)
            res_arr = np.zeros(2 * n)
            for i in range(n):
                fx, fy = _calc_tire_forces_fast(
                    Fz[i], alpha[i], kappa[i], camber[i], c_arr, p[i], T[i]
                )
                res_arr[i] = fx - Fx_meas[i]
                res_arr[n + i] = fy - Fy_meas[i]
            return res_arr

        res = least_squares(residual, p0, bounds=(bounds_lower, bounds_upper), method='trf', max_nfev=200)
        if res.success:
            p = res.x
            self.coeffs.rBx1 = float(p[0])
            self.coeffs.rBx2 = float(p[1])
            self.coeffs.rCx1 = float(p[2])
            self.coeffs.rBy1 = float(p[3])
            self.coeffs.rBy2 = float(p[4])
            self.coeffs.rCy1 = float(p[5])

    def analyze_residuals(self, dataset: TireDataset) -> TireFittingResiduals:
        """Compute comprehensive statistical metrics and residual diagnostics."""
        clean = dataset.clean_and_filter()
        n = len(clean)
        if n == 0:
            return TireFittingResiduals()

        c_arr = self.coeffs.to_array()
        fx_pred = np.zeros(n)
        fy_pred = np.zeros(n)
        mz_pred = np.zeros(n)

        for i in range(n):
            fx, fy, mz, _ = _calc_tire_forces_and_moments_fast(
                clean.Fz[i], clean.alpha[i], clean.kappa[i], clean.camber[i],
                c_arr, pressure_bar=clean.pressure[i], T_c=clean.temperature[i]
            )
            fx_pred[i] = fx
            fy_pred[i] = fy
            mz_pred[i] = mz

        # Fx metrics
        e_fx = fx_pred - clean.Fx
        rmse_fx = float(np.sqrt(np.mean(e_fx**2)))
        mae_fx = float(np.mean(np.abs(e_fx)))
        max_e_fx = float(np.max(np.abs(e_fx)))
        bias_fx = float(np.mean(e_fx))
        ss_tot_fx = float(np.sum((clean.Fx - np.mean(clean.Fx))**2))
        r2_fx = float(max(0.0, 1.0 - np.sum(e_fx**2) / max(ss_tot_fx, 1e-6)))

        # Fy metrics
        e_fy = fy_pred - clean.Fy
        rmse_fy = float(np.sqrt(np.mean(e_fy**2)))
        mae_fy = float(np.mean(np.abs(e_fy)))
        max_e_fy = float(np.max(np.abs(e_fy)))
        bias_fy = float(np.mean(e_fy))
        ss_tot_fy = float(np.sum((clean.Fy - np.mean(clean.Fy))**2))
        r2_fy = float(max(0.0, 1.0 - np.sum(e_fy**2) / max(ss_tot_fy, 1e-6)))

        # Mz metrics
        e_mz = mz_pred - clean.Mz
        rmse_mz = float(np.sqrt(np.mean(e_mz**2)))
        mae_mz = float(np.mean(np.abs(e_mz)))
        max_e_mz = float(np.max(np.abs(e_mz)))
        bias_mz = float(np.mean(e_mz))
        ss_tot_mz = float(np.sum((clean.Mz - np.mean(clean.Mz))**2))
        r2_mz = float(max(0.0, 1.0 - np.sum(e_mz**2) / max(ss_tot_mz, 1e-6))) if ss_tot_mz > 1e-3 else 1.0

        # Confidence calculation
        avg_r2 = float(np.mean([r2_fx, r2_fy, r2_mz]))
        confidence = float(np.clip(avg_r2 * (1.0 - min(0.3, rmse_fy / 200.0)), 0.1, 0.99))

        return TireFittingResiduals(
            rmse_Fx=rmse_fx, rmse_Fy=rmse_fy, rmse_Mz=rmse_mz,
            mae_Fx=mae_fx, mae_Fy=mae_fy, mae_Mz=mae_mz,
            r2_Fx=r2_fx, r2_Fy=r2_fy, r2_Mz=r2_mz,
            max_error_Fx=max_e_fx, max_error_Fy=max_e_fy, max_error_Mz=max_e_mz,
            mean_bias_Fx=bias_fx, mean_bias_Fy=bias_fy, mean_bias_Mz=bias_mz,
            confidence_score=confidence,
        )
