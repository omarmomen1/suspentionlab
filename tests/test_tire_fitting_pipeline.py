"""
tests/test_tire_fitting_pipeline.py
===================================
Tests for Experimental Tire Test Data Ingestion, Cleaning, Feature Extraction,
Multi-stage Non-linear Least Squares Optimization, Residual Diagnostics, and .tir roundtrip.
"""

import io
import math
import pytest
import numpy as np

from suspensionlab.physics.magic_formula import TireCoeffs, PacejkaMF52TireModel
from suspensionlab.physics.tire_fitting import (
    TireDataset,
    TireModelFitter,
    TireFittingResiduals,
)
from suspensionlab.physics.tir_parser import parse_tir_file, export_tir_file


def test_synthetic_data_generation_and_features():
    truth_coeffs = TireCoeffs(
        pDx1=1.20, pDy1=1.15, pKx1=25.0, pKy1=18.0
    )
    dataset = TireDataset.generate_synthetic(coeffs=truth_coeffs, n_samples=800, noise_std=10.0)
    assert len(dataset) == 800

    features = dataset.extract_features()
    assert features["Fz_nominal_N"] in (4000.0, 5000.0, 6000.0)
    assert features["cornering_stiffness_N_per_rad"] > 20000.0
    assert features["braking_stiffness_N_per_slip"] > 30000.0
    assert 0.8 <= features["peak_mu_x"] <= 1.6
    assert 0.8 <= features["peak_mu_y"] <= 1.6


def test_csv_ingestion_and_cleaning():
    csv_text = """FZ,ALPHA,KAPPA,CAMBER,FX,FY,MZ,PRESSURE,TEMP
4000.0,0.0,0.10,0.0,4200.0,0.0,0.0,2.0,85.0
4000.0,0.08,0.0,0.0,0.0,3800.0,-80.0,2.0,85.0
-500.0,0.05,0.0,0.0,0.0,0.0,0.0,2.0,85.0
NaN,0.0,0.0,0.0,0.0,0.0,0.0,2.0,85.0
"""
    ds = TireDataset.from_csv(csv_text)
    # The negative Fz and NaN rows should be filtered out
    assert len(ds) == 2
    assert np.all(ds.Fz > 0.0)


def test_multistage_tire_model_parameter_fitting():
    # 1. Generate ground truth synthetic dataset
    true_coeffs = TireCoeffs(
        pDx1=1.15, pDy1=1.10, pCx1=1.55, pCy1=1.35,
        pKx1=24.0, pKy1=16.0, rBx1=11.0, rBy1=11.0
    )
    dataset = TireDataset.generate_synthetic(coeffs=true_coeffs, n_samples=600, noise_std=5.0, seed=123)

    # 2. Fit parameters starting from nominal defaults
    fitter = TireModelFitter()
    fitted_model, residuals = fitter.fit(dataset, val_fraction=0.25, seed=123)

    # 3. Assert high correlation and low residual error
    assert residuals.r2_Fx > 0.92, f"R2_Fx too low: {residuals.r2_Fx:.4f}"
    assert residuals.r2_Fy > 0.92, f"R2_Fy too low: {residuals.r2_Fy:.4f}"
    assert residuals.rmse_Fx < 100.0, f"RMSE_Fx too high: {residuals.rmse_Fx:.2f} N"
    assert residuals.rmse_Fy < 100.0, f"RMSE_Fy too high: {residuals.rmse_Fy:.2f} N"
    assert residuals.holdout_r2 > 0.90
    assert residuals.confidence_score > 0.70


def test_tir_file_export_and_parse_roundtrip():
    original = TireCoeffs(
        Fz0=4500.0,
        pDx1=1.18,
        pDy1=1.12,
        pCx1=1.62,
        pCy1=1.38,
        pKx1=26.0,
        pKy1=17.5,
        qBz1=9.5,
        qDz1=0.038,
    )

    tir_str = export_tir_file(original)
    assert "[LONGITUDINAL_COEFFICIENTS]" in tir_str
    assert "[LATERAL_COEFFICIENTS]" in tir_str
    assert "[ALIGNING_COEFFICIENTS]" in tir_str

    parsed = parse_tir_file(tir_str)
    assert math.isclose(parsed.Fz0, 4500.0, abs_tol=1e-1)
    assert math.isclose(parsed.pDx1, 1.18, abs_tol=1e-3)
    assert math.isclose(parsed.pDy1, 1.12, abs_tol=1e-3)
    assert math.isclose(parsed.pCx1, 1.62, abs_tol=1e-3)
    assert math.isclose(parsed.pCy1, 1.38, abs_tol=1e-3)
    assert math.isclose(parsed.qBz1, 9.5, abs_tol=1e-3)
