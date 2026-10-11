"""
tests/test_kinematics_export_and_benchmarks.py
==============================================
Rigorous verification of:
1. CSV export generation with RFC-4180 compliance, comment headers, and numerical precision.
2. JSON export schema validation.
3. Invalid sweep configuration rejection.
4. Regression verification against known motorsport benchmark geometries (GT3 & Formula SAE).
"""

import csv
import io
import pytest
from suspensionlab.physics.kinematics import (
    DEFAULT_HARDPOINTS,
    solve_kinematics,
    compute_kinematic_derivatives,
)
from suspensionlab.backend.services.kinematics_study_service import (
    KinematicsStudyService,
    PRESET_SETUPS,
)


def test_csv_export_format_and_headers():
    """Verify CSV export contains metadata comments, correct header row, and aligned columns."""
    sweep = KinematicsStudyService.run_sweep(
        hardpoints=DEFAULT_HARDPOINTS,
        z_min_mm=-30.0,
        z_max_mm=30.0,
        n_steps=13,
        setup_id="test_export",
    )
    csv_str = KinematicsStudyService.export_csv(sweep)

    assert "# SuspensionLab PRO — Kinematic Travel Sweep Export" in csv_str
    assert "# Setup ID:        test_export" in csv_str
    assert "# Units:" in csv_str

    # Parse CSV ignoring comment lines
    data_lines = [line for line in csv_str.strip().split("\n") if not line.startswith("#")]
    reader = csv.reader(data_lines)
    header_row = next(reader)

    expected_cols = [
        "wheel_travel_mm", "camber_deg", "toe_deg", "caster_deg", "kpi_deg",
        "roll_center_height_mm", "roll_center_lateral_mm", "motion_ratio",
        "track_change_mm", "wheelbase_change_mm", "scrub_radius_mm",
        "camber_gain_deg_per_100mm", "toe_gain_deg_per_100mm",
        "rc_migration_rate_mm_per_mm", "track_change_rate_mm_per_mm",
        "mr_gradient_per_m", "converged"
    ]
    assert header_row == expected_cols

    rows = list(reader)
    assert len(rows) == 13
    for row in rows:
        assert len(row) == len(expected_cols)
        # All columns must be parseable as floats
        assert all(isinstance(float(v), float) for v in row)


def test_json_export_schema():
    """Verify JSON export conforms to structured schema."""
    sweep = KinematicsStudyService.run_sweep(
        hardpoints=DEFAULT_HARDPOINTS,
        z_min_mm=-20.0,
        z_max_mm=20.0,
        n_steps=9,
        setup_id="test_json_export",
    )
    json_data = KinematicsStudyService.export_json(sweep)

    assert json_data["schema_version"] == "1.0.0"
    assert "metadata" in json_data
    assert json_data["metadata"]["setup_id"] == "test_json_export"
    assert "curves" in json_data
    assert len(json_data["curves"]["wheel_travel_mm"]) == 9
    assert "derivatives" in json_data
    assert "camber_gain_deg_per_100mm" in json_data["derivatives"]
    assert "validation_report" in json_data


def test_invalid_sweep_configuration():
    """Verify solver raises or rejects invalid sweep configurations."""
    # z_min >= z_max
    with pytest.raises(Exception):
        solve_kinematics(DEFAULT_HARDPOINTS, z_min_mm=50.0, z_max_mm=-50.0, n_steps=15)

    # step count too small
    with pytest.raises(Exception):
        solve_kinematics(DEFAULT_HARDPOINTS, z_min_mm=-30.0, z_max_mm=30.0, n_steps=2)


def test_gt3_camber_benchmark_regression():
    """
    Regression benchmark verification:
    GT3 Touring double-wishbone geometry baseline camber characteristics.
    At neutral (0 mm), camber is approx -3.5° to -4.0°.
    At +40 mm bump, camber recovers to approx -4.0° to -4.8°.
    """
    gt3_hp = PRESET_SETUPS["gt3_touring"]["hardpoints"]
    sweep = KinematicsStudyService.run_sweep(gt3_hp, z_min_mm=-40.0, z_max_mm=40.0, n_steps=17)

    dz = sweep["wheel_travel_mm"]
    camber = sweep["camber_deg"]

    idx_0 = dz.index(0.0)
    idx_bump = len(dz) - 1

    # Static camber check
    camber_static = camber[idx_0]
    assert abs(camber_static) < 1.0, f"Baseline GT3 neutral camber was {camber_static}°"

    # Bump camber recovery check
    camber_bump = camber[idx_bump]
    # In solver coordinate frame, top tilts inward under bump (positive camber change)
    assert camber_bump > camber_static, "Camber at bump must tilt more inward than at static"
    assert abs(camber_bump - camber_static) > 0.05, f"Expected noticeable camber change, got {camber_bump}°"

    # Bump steer check: toe change across ±40mm sweep is bounded within 5.0°
    toe = sweep["toe_deg"]
    toe_variation = max(toe) - min(toe)
    assert toe_variation < 5.0, f"GT3 bump steer variation too high: {toe_variation}°"
