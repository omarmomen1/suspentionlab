"""
tests/test_tire_enveloping.py
=============================
Rigorous verification and validation test suite for SuspensionLab PRO
Tire Enveloping Physics Engine.

Validates:
1. Mode Architecture: POINT_CONTACT, GEOMETRIC_ENVELOPING, ADVANCED_ENVELOPING
2. Configurable Tire Geometry (Radius, Width, Pressure, Stiffness, Patch Length)
3. Benchmark Road Profiles (flat, sine, smooth bump, sharp step, kerb, repeated roughness, combined 3D)
4. Mathematical Validation Benchmarks:
   - Flat road zero-distortion test
   - Sinusoidal contact-patch attenuation matching analytical Hertzian theory
   - Sharp step circular carcass arc lead-in and peak impact attenuation
5. Output Metrics: effective road height, tire deflection, tire normal force,
   unsprung/sprung accelerations, RMS, peak reduction, frequency response
6. Advanced Enveloping: dynamic footprint 2a(Fz), horizontal obstacle force Fx_env, 3D variation
7. Epistemic Validity Governance & Provenance
8. Determinism and Reproducibility
"""

import math
import pytest
import numpy as np

from suspensionlab.physics.validity import (
    PhysicsValidityRecord,
    PhysicsValidityStatus,
)
from suspensionlab.physics.contracts import (
    CanonicalRoadProfile,
    ContactState,
)
from suspensionlab.physics.tire_enveloping import (
    TireEnvelopingConfig,
    TireEnvelopingMode,
    TireEnvelopingModel,
    PressureWeightingType,
    EnvelopedRoadProfile,
    create_benchmark_road,
    compare_enveloping_vs_point_contact,
)
from suspensionlab.physics.tire_model import TireDefinition
from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    simulate_time_response,
    run_quarter_car_analysis,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Mode Architecture & Configurable Tire Geometry Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_enveloping_mode_enum_and_defaults():
    """Verify explicit mode enum and baseline configuration defaults."""
    assert TireEnvelopingMode.POINT_CONTACT.value == "POINT_CONTACT"
    assert TireEnvelopingMode.GEOMETRIC_ENVELOPING.value == "GEOMETRIC_ENVELOPING"
    assert TireEnvelopingMode.ADVANCED_ENVELOPING.value == "ADVANCED_ENVELOPING"

    cfg = TireEnvelopingConfig()
    assert cfg.mode == TireEnvelopingMode.POINT_CONTACT
    assert cfg.unloaded_radius == 0.330
    assert cfg.section_width == 0.245
    assert cfg.vertical_stiffness_k_t == 250_000.0
    assert cfg.inflation_pressure_bar == 2.0


def test_tire_geometry_validation_and_rejection():
    """Verify bounds enforcement on tire dimensions and physical parameters."""
    with pytest.raises(ValueError, match="Unloaded radius"):
        TireEnvelopingConfig(unloaded_radius=0.02)

    with pytest.raises(ValueError, match="Section width"):
        TireEnvelopingConfig(section_width=0.01)

    with pytest.raises(ValueError, match="Vertical stiffness"):
        TireEnvelopingConfig(vertical_stiffness_k_t=1000.0)

    with pytest.raises(ValueError, match="Inflation pressure"):
        TireEnvelopingConfig(inflation_pressure_bar=0.1)


def test_tire_definition_to_enveloping_config():
    """Verify seamless connection from canonical TireDefinition to TireEnvelopingConfig."""
    td = TireDefinition(
        unloaded_radius=0.340,
        section_width=0.265,
        vertical_stiffness_k_t=280_000.0,
        nominal_pressure_bar=2.2,
    )
    cfg = td.to_enveloping_config(
        mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING,
        speed_mps=25.0,
    )
    assert cfg.mode == TireEnvelopingMode.GEOMETRIC_ENVELOPING
    assert cfg.unloaded_radius == 0.340
    assert cfg.section_width == 0.265
    assert cfg.vertical_stiffness_k_t == 280_000.0
    assert cfg.inflation_pressure_bar == 2.2
    assert cfg.speed_mps == 25.0


def test_pressure_dependent_stiffness_and_footprint():
    """Verify vertical stiffness and contact patch scale physically with inflation pressure."""
    cfg = TireEnvelopingConfig(
        vertical_stiffness_k_t=250_000.0,
        nominal_pressure_bar=2.0,
        inflation_pressure_bar=1.5,
    )
    # Lower pressure -> lower carcass vertical stiffness
    kt_low = cfg.effective_vertical_stiffness(pressure_bar=1.5)
    kt_nom = cfg.effective_vertical_stiffness(pressure_bar=2.0)
    kt_high = cfg.effective_vertical_stiffness(pressure_bar=2.5)
    assert kt_low < kt_nom < kt_high

    # Lower pressure -> larger contact patch length and width under identical load
    a_low, b_low = cfg.compute_static_contact_patch(Fz=4000.0)
    cfg.inflation_pressure_bar = 2.5
    a_high, b_high = cfg.compute_static_contact_patch(Fz=4000.0)
    assert a_low > a_high
    assert b_low > b_high


# ─────────────────────────────────────────────────────────────────────────────
# 2. Benchmark Road Profiles Suite
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ptype", [
    "flat", "sine", "smooth_bump", "sharp_step", "kerb", "repeated_roughness", "combined_3d"
])
def test_all_benchmark_road_profiles(ptype):
    """Verify that all required benchmark road profiles generate valid CanonicalRoadProfile objects."""
    road = create_benchmark_road(ptype, length_m=30.0, amplitude_m=0.03, dx=0.005)
    assert isinstance(road, CanonicalRoadProfile)
    assert len(road.x) > 100
    assert len(road.z) == len(road.x)
    assert road.dz_dx is not None
    assert np.all(np.isfinite(road.z))
    assert np.all(np.isfinite(road.dz_dx))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Mathematical Validation Benchmarks
# ─────────────────────────────────────────────────────────────────────────────

def test_mathematical_validation_flat_road():
    """Verify that flat road excitation yields exact zero distortion in effective elevation and slope."""
    cfg = TireEnvelopingConfig(mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING)
    model = TireEnvelopingModel(cfg)
    res = model.validate_flat_road()
    assert bool(res["passed"]) is True
    assert res["max_elevation_error_m"] < 1e-6
    assert res["max_slope_error"] < 1e-6
    assert res["status"] == PhysicsValidityStatus.MODEL_SUPPORTED.value


def test_mathematical_validation_sine_attenuation():
    """Verify contact patch geometric filtering matches theoretical continuous Hertzian attenuation."""
    cfg = TireEnvelopingConfig(
        mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING,
        unloaded_radius=0.330,
        vertical_stiffness_k_t=250_000.0,
        pressure_weighting=PressureWeightingType.PARABOLIC,
        include_carcass_cam=False,  # Test pure footprint averaging
    )
    model = TireEnvelopingModel(cfg)
    # Sine wavelength = 1.0m, footprint half-length a ~ 0.07m
    res = model.validate_sine_attenuation(wavelength_m=1.0, amplitude_m=0.02)
    assert bool(res["passed"]) is True
    assert 0.80 <= res["simulated_attenuation"] <= 1.05
    assert res["status"] == PhysicsValidityStatus.MODEL_SUPPORTED.value


def test_mathematical_validation_sharp_step_circular_cam():
    """Verify that a sharp step is enveloped smoothly with circular carcass pre-contact."""
    cfg = TireEnvelopingConfig(
        mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING,
        unloaded_radius=0.330,
        include_carcass_cam=True,
    )
    model = TireEnvelopingModel(cfg)
    step_h = 0.03
    step_x = 5.0
    res = model.validate_sharp_step(step_height_m=step_h, step_x_m=step_x)
    assert bool(res["passed"]) is True
    # Effective road height ahead of the step center must be intermediate (pre-contact rising)
    assert 0.005 < res["w_at_step_entry_m"] < step_h
    assert res["w_at_step_center_m"] <= step_h + 1e-6
    # Max enveloped slope must be finite
    assert res["max_enveloped_slope"] < 2.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Enveloping vs. Point-Contact Output Comparisons
# ─────────────────────────────────────────────────────────────────────────────

def test_step_comparison_unsprung_accel_reduction():
    """Verify that enveloping strictly reduces peak unsprung acceleration over a sharp step."""
    p = QuarterCarParams()
    step_road = create_benchmark_road("sharp_step", amplitude_m=0.03, start_x_m=2.0, length_m=10.0)

    cfg = TireEnvelopingConfig(
        mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING,
        speed_mps=15.0,
    )
    comp = compare_enveloping_vs_point_contact(
        p=p,
        road_profile=step_road,
        enveloping_config=cfg,
        speed_mps=15.0,
        duration_s=0.5,
    )

    # Point-contact exhibits an aggressive acceleration spike; enveloping attenuates it physically
    assert comp.peak_unsprung_accel_env < comp.peak_unsprung_accel_point
    assert comp.peak_unsprung_reduction_pct > 5.0  # Significant physical attenuation

    # Tire deflection is smoothed and continuous
    assert np.all(np.isfinite(comp.tire_deflection_env))
    assert np.all(np.isfinite(comp.tire_force_env))

    # Provenance and validity records are populated
    assert comp.validity_record.status == PhysicsValidityStatus.MODEL_SUPPORTED
    assert len(comp.provenance_hash) > 0


def test_kerb_comparison_outputs_and_frequency_response():
    """Verify that enveloping over a race track kerb produces all canonical comparative outputs."""
    p = QuarterCarParams()
    kerb_road = create_benchmark_road("kerb", amplitude_m=0.035, start_x_m=3.0, length_m=15.0)

    cfg = TireEnvelopingConfig(
        mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING,
        speed_mps=20.0,
    )
    comp = compare_enveloping_vs_point_contact(
        p=p,
        road_profile=kerb_road,
        enveloping_config=cfg,
        speed_mps=20.0,
        duration_s=0.6,
    )

    # 1. Effective road height vs raw road height
    assert len(comp.effective_road_height) == len(comp.time)
    assert len(comp.raw_road_height) == len(comp.time)
    assert np.all(np.isfinite(comp.effective_road_height))

    # 2. Tire deflection
    assert len(comp.tire_deflection_env) == len(comp.time)
    assert len(comp.tire_deflection_point) == len(comp.time)
    assert np.all(np.isfinite(comp.tire_deflection_env))

    # 3. Tire force
    assert len(comp.tire_force_env) == len(comp.time)
    assert len(comp.tire_force_point) == len(comp.time)
    assert np.all(np.isfinite(comp.tire_force_env))

    # 4. Unsprung acceleration
    assert len(comp.unsprung_accel_env) == len(comp.time)
    assert len(comp.unsprung_accel_point) == len(comp.time)
    assert np.all(np.isfinite(comp.unsprung_accel_env))

    # 5. Sprung acceleration
    assert len(comp.sprung_accel_env) == len(comp.time)
    assert len(comp.sprung_accel_point) == len(comp.time)
    assert np.all(np.isfinite(comp.sprung_accel_env))

    # 6. RMS acceleration
    assert comp.rms_unsprung_accel_env > 0.0
    assert comp.rms_sprung_accel_env > 0.0

    # 7. Peak acceleration
    assert comp.peak_unsprung_accel_env > 0.0
    assert comp.peak_sprung_accel_env > 0.0

    # 8. Frequency response vectors
    assert len(comp.freqs_hz) > 50
    assert len(comp.transmissibility_point) == len(comp.freqs_hz)
    assert len(comp.transmissibility_env) == len(comp.freqs_hz)


def test_repeated_roughness_rms_reduction():
    """Verify that enveloping over stochastic rough road reduces RMS and peak unsprung acceleration."""
    p = QuarterCarParams()
    road = create_benchmark_road("repeated_roughness", length_m=30.0)
    cfg = TireEnvelopingConfig(mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING, speed_mps=20.0)
    comp = compare_enveloping_vs_point_contact(p, road, cfg, speed_mps=20.0, duration_s=1.0)
    assert comp.rms_unsprung_accel_env < comp.rms_unsprung_accel_point
    assert comp.peak_unsprung_accel_env < comp.peak_unsprung_accel_point


# ─────────────────────────────────────────────────────────────────────────────
# 5. Advanced Enveloping Features (Dynamic Footprint, Fx_env, 3D Variation)
# ─────────────────────────────────────────────────────────────────────────────

def test_advanced_enveloping_dynamic_footprint_scaling():
    """Verify that contact patch length expands with normal load under ADVANCED_ENVELOPING."""
    cfg = TireEnvelopingConfig(mode=TireEnvelopingMode.ADVANCED_ENVELOPING)
    model = TireEnvelopingModel(cfg)
    step_road = create_benchmark_road("sharp_step", amplitude_m=0.02, start_x_m=5.0)

    state_low_fz = model.evaluate_effective_road(step_road, x_center=3.0, speed_mps=20.0, Fz=2000.0)
    state_high_fz = model.evaluate_effective_road(step_road, x_center=3.0, speed_mps=20.0, Fz=8000.0)

    # Footprint length must expand under higher load
    assert state_high_fz.contact_length > state_low_fz.contact_length
    assert state_high_fz.contact_width > state_low_fz.contact_width


def test_advanced_enveloping_horizontal_obstacle_force():
    """Verify horizontal obstacle force Fx_env opposes motion when climbing an obstacle."""
    cfg = TireEnvelopingConfig(
        mode=TireEnvelopingMode.ADVANCED_ENVELOPING,
        include_longitudinal_force=True,
    )
    model = TireEnvelopingModel(cfg)
    step_road = create_benchmark_road("sharp_step", amplitude_m=0.03, start_x_m=5.0)

    # As tire approaches step, effective road slope dw_eff/dx > 0 (uphill)
    # Hence Fx_env = -Fz * dw_eff/dx must be negative (retarding vehicle)
    state_climbing = model.evaluate_effective_road(step_road, x_center=4.95, speed_mps=15.0, Fz=4000.0)
    assert state_climbing.dw_eff_dx > 0.0
    assert state_climbing.Fx_env < 0.0  # Resistance force


def test_advanced_enveloping_3d_lateral_variation():
    """Verify 3D lateral road surface cross-fall integration."""
    cfg = TireEnvelopingConfig(mode=TireEnvelopingMode.ADVANCED_ENVELOPING)
    model = TireEnvelopingModel(cfg)
    flat_road = create_benchmark_road("flat", length_m=20.0)

    # Centerline is 0, but lateral slope = 0.10 and tire is offset by 0.15m
    state_3d = model.evaluate_effective_road(
        flat_road, x_center=5.0, speed_mps=20.0, y_center=0.15, lateral_slope=0.10
    )
    assert state_3d.w_eff > 0.01  # Elevated by lateral cross-slope


# ─────────────────────────────────────────────────────────────────────────────
# 6. Epistemic Validity & External Dataset Plug-In Interface
# ─────────────────────────────────────────────────────────────────────────────

def test_external_dataset_validation_protocol():
    """Verify validation engine upgrades status properly and rejects fabricated empirical claims."""
    cfg = TireEnvelopingConfig(mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING)
    model = TireEnvelopingModel(cfg)

    t = np.linspace(0, 1.0, 200)
    ideal_signal = np.sin(2 * np.pi * 5.0 * t)

    # 1. Uncalibrated/divergent dataset (R^2 < 0.70) -> UNSUPPORTED
    bad_data = {"effective_road": ideal_signal, "simulated_w_eff": -ideal_signal}
    rec_bad = model.validate_against_dataset(bad_data, source_name="BadRig")
    assert rec_bad.status == PhysicsValidityStatus.UNSUPPORTED
    assert len(rec_bad.warnings) > 0

    # 2. Correlated benchmark simulation (R^2 >= 0.70) -> CORRELATED
    noisy_sim = ideal_signal + 0.1 * np.random.normal(0, 1, len(t))
    corr_data = {"effective_road": ideal_signal, "simulated_w_eff": noisy_sim}
    rec_corr = model.validate_against_dataset(corr_data, source_name="SimBenchmark", is_measured_sensor_data=False)
    assert rec_corr.status == PhysicsValidityStatus.CORRELATED

    # 3. Authentic measured sensor transducer data -> EMPIRICALLY_VALIDATED
    rec_emp = model.validate_against_dataset(corr_data, source_name="PhysicalCleatRig", is_measured_sensor_data=True)
    assert rec_emp.status == PhysicsValidityStatus.EMPIRICALLY_VALIDATED
    assert "Empirically validated against physical dataset" in rec_emp.validation_evidence


# ─────────────────────────────────────────────────────────────────────────────
# 7. Reproducibility & Input/Output Determinism
# ─────────────────────────────────────────────────────────────────────────────

def test_enveloping_simulation_determinism():
    """Verify exact numerical reproducibility across repeated identical runs."""
    p = QuarterCarParams()
    kerb_road = create_benchmark_road("kerb", amplitude_m=0.03, start_x_m=2.0, length_m=10.0)
    cfg = TireEnvelopingConfig(mode=TireEnvelopingMode.GEOMETRIC_ENVELOPING, speed_mps=20.0)

    run1 = compare_enveloping_vs_point_contact(p, kerb_road, cfg, speed_mps=20.0, duration_s=0.4)
    run2 = compare_enveloping_vs_point_contact(p, kerb_road, cfg, speed_mps=20.0, duration_s=0.4)

    assert run1.provenance_hash == run2.provenance_hash
    np.testing.assert_array_equal(run1.effective_road_height, run2.effective_road_height)
    np.testing.assert_array_equal(run1.unsprung_accel_env, run2.unsprung_accel_env)
    assert run1.peak_unsprung_accel_env == run2.peak_unsprung_accel_env
