"""
tests/test_corner_analysis_and_lap_delta.py
===========================================
Unit test suite for corner detection, zone classification, and sector delta causal attribution.
"""

import numpy as np
import pytest

from suspensionlab.physics.corner_analysis import (
    TrackZone,
    CornerMetrics,
    CornerComparison,
    classify_zones,
    detect_corners,
    compare_corners,
    analyze_lap_corners,
)
from suspensionlab.physics.lap_delta import (
    TimeLossCategory,
    CausalConfidence,
    SectorDelta,
    ZoneDelta,
    LapDeltaReport,
    compute_lap_delta,
    format_engineering_report,
)
from suspensionlab.physics.lap_sim_errors import (
    LapSimError,
    InvalidTrackError,
    TireModelError,
    SolverNonConvergenceError,
    ImpossibleSpeedError,
    MissingVehicleDataError,
    PowertrainError,
    EnergyBudgetError,
)
from suspensionlab.physics.lap_sim import LapSimResult


def test_corner_detection_and_classification():
    """Verify corner detection finds apex, entry, exit, and classifies track zones."""
    N = 300
    distances = np.linspace(0, 1500, N)
    curvatures = np.zeros(N)
    
    # Place a corner between 400m and 700m (indices ~80 to 140)
    curvatures[80:140] = 0.02 * np.sin(np.pi * np.linspace(0, 1, 60))
    
    speeds = np.full(N, 60.0)
    # Speed drops into the corner
    speeds[80:110] = np.linspace(60.0, 25.0, 30)
    speeds[110:140] = np.linspace(25.0, 55.0, 30)
    
    lateral_g = speeds**2 * curvatures / 9.81
    longitudinal_g = np.zeros(N)
    longitudinal_g[70:110] = -0.8  # braking into corner
    longitudinal_g[110:150] = 0.5   # acceleration out
    
    # 1. Test zone classification
    zones = classify_zones(distances, speeds, curvatures, longitudinal_g)
    assert len(zones) == N
    assert TrackZone.BRAKING_ZONE.value in zones
    assert TrackZone.CORNER_ENTRY.value in zones
    assert TrackZone.APEX.value in zones
    assert TrackZone.CORNER_EXIT.value in zones
    assert TrackZone.ACCELERATION_ZONE.value in zones
    
    # 2. Test corner detection
    corners = detect_corners(
        distances, speeds, curvatures, lateral_g, longitudinal_g,
        min_corner_length_m=10.0,
    )
    assert len(corners) == 1
    c = corners[0]
    assert c.corner_id == 1
    assert c.name == "Turn 1"
    assert c.min_speed_mps == pytest.approx(25.0, abs=1.0)
    assert c.entry_distance_m < c.apex_distance_m < c.exit_distance_m
    assert c.braking_distance_m > 0.0
    assert c.peak_lateral_g > 0.5


def test_corner_comparison():
    """Verify pairwise corner delta computation and causal heuristics."""
    c1 = CornerMetrics(
        corner_id=1, name="Turn 1", sector_id=1,
        entry_station=50, apex_station=80, exit_station=110,
        entry_distance_m=200.0, apex_distance_m=350.0, exit_distance_m=500.0,
        entry_speed_mps=50.0, min_speed_mps=20.0, exit_speed_mps=45.0,
        braking_distance_m=45.0, peak_lateral_g=2.2, mean_lateral_g=1.8,
        peak_longitudinal_g=-1.2, time_in_corner_s=6.5,
        tire_utilization_peak=0.95, tire_utilization_mean=0.82,
        aero_downforce_at_entry_n=3000.0, aero_downforce_at_apex_n=1500.0,
    )
    
    # Setup B has higher apex and exit speed
    c2 = CornerMetrics(
        corner_id=1, name="Turn 1", sector_id=1,
        entry_station=50, apex_station=80, exit_station=110,
        entry_distance_m=200.0, apex_distance_m=350.0, exit_distance_m=500.0,
        entry_speed_mps=50.5, min_speed_mps=22.0, exit_speed_mps=47.5,
        braking_distance_m=40.0, peak_lateral_g=2.4, mean_lateral_g=1.9,
        peak_longitudinal_g=-1.3, time_in_corner_s=6.2,
        tire_utilization_peak=0.98, tire_utilization_mean=0.85,
        aero_downforce_at_entry_n=3200.0, aero_downforce_at_apex_n=1650.0,
    )
    
    comps = compare_corners([c1], [c2])
    assert len(comps) == 1
    cmp = comps[0]
    assert cmp.delta_min_speed_mps == pytest.approx(2.0)
    assert cmp.delta_time_s == pytest.approx(-0.3)
    assert cmp.confidence in ["HIGH", "MEDIUM"]
    assert "apex speed" in cmp.likely_cause.lower() or "traction" in cmp.likely_cause.lower()


def test_lap_delta_causal_attribution():
    """Verify sector delta and causal attribution between baseline and modified setups."""
    N = 200
    distances = np.linspace(0, 1000, N)
    
    # Create baseline result
    res_a = LapSimResult(
        total_time=60.0,
        sector_times=[20.0, 20.0, 20.0],
        distances=distances,
        speeds=np.full(N, 50.0),
        lateral_g=np.zeros(N),
        longitudinal_g=np.zeros(N),
        curvatures=np.zeros(N),
        aero_downforce_n=np.full(N, 2000.0),
        aero_drag_n=np.full(N, 800.0),
        drive_force_n=np.full(N, 800.0),
    )
    
    # Create modified result (faster in sector 1)
    res_b = LapSimResult(
        total_time=59.4,
        sector_times=[19.4, 20.0, 20.0],
        distances=distances,
        speeds=np.full(N, 52.0),
        lateral_g=np.zeros(N),
        longitudinal_g=np.zeros(N),
        curvatures=np.zeros(N),
        aero_downforce_n=np.full(N, 2000.0),
        aero_drag_n=np.full(N, 750.0),  # lower drag
        drive_force_n=np.full(N, 800.0),
    )
    
    report = compute_lap_delta(res_a, res_b)
    assert report.total_delta_s == pytest.approx(-0.6, abs=0.01)
    assert len(report.sector_deltas) == 3
    assert report.sector_deltas[0].delta_s == pytest.approx(-0.6, abs=0.01)
    assert report.model_assumptions_caveat != ""
    
    # Format engineering text report
    text_rep = format_engineering_report(report)
    assert "Lap Time Delta" in text_rep
    assert "Sector 1" in text_rep


def test_error_classes_and_serialization():
    """Verify structured engineering errors have correct messages and serialization."""
    err = InvalidTrackError(issues=["Δκ/Δs excessive"], message="Curvature discontinuity detected", station_index=42)
    assert err.station_index == 42
    d = err.to_dict()
    assert d["error_type"] == "InvalidTrackError"
    assert d["station_index"] == 42
    assert "issues" in d
    
    tire_err = TireModelError(tire_corner="FL", Fz=-50.0, alpha=0.1, kappa=0.0, message="Negative normal force", station_index=10)
    assert tire_err.tire_corner == "FL"
    assert tire_err.Fz == -50.0
    assert tire_err.to_dict()["error_type"] == "TireModelError"
    
    solver_err = SolverNonConvergenceError(phase="apex", max_residual=0.15, iteration_count=15, message="Apex iteration failed")
    assert solver_err.phase == "apex"
    assert solver_err.iteration_count == 15
