"""
tests/test_scientific_integrity_truthfulness.py
================================================
SuspensionLab PRO — Scientific Integrity & False-Confidence Elimination Test Suite

Verifies:
1. "NO DATA = NO CLAIM": Zero-data evaluation strictly yields UNVALIDATED with 0.0% confidence score.
2. Purge of all hardcoded 91.4% correlation, fake 97.0% VALIDATED banners, and auto-PASS defaults.
3. C++ Kinematics Facade truthful reporting of solver engine (python_reference vs cpp).
4. Zero demo-mode delta fabrication in hydrated engineering reports (+0.000 s instead of -0.087 s).
5. Digital Twin and Physics Provenance zero-data defaults.
"""

import uuid
from datetime import datetime, timezone
import pytest
from unittest.mock import patch

from suspensionlab.physics.confidence_banner import (
    SimulationConfidenceBanner,
    ValidityStatus,
)
from suspensionlab.physics.digital_twin import DigitalTwin
from suspensionlab.physics.provenance import (
    PhysicsObservability,
    create_provenance,
)
from suspensionlab.physics.kinematics_facade import (
    KinematicsBackendFactory,
    CppKinematicsBackend,
    PythonReferenceBackend,
    solve_kinematics,
)
from suspensionlab.backend.database.core import SessionLocal
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.services.report_service import hydrate_engineering_report


def test_confidence_banner_zero_data_truthfulness():
    """
    Verify that with zero empirical datasets, the confidence banner strictly
    evaluates to UNVALIDATED with 0.0% confidence score.
    No 91.4% correlation or 97.0% VALIDATED defaults allowed.
    """
    banner = SimulationConfidenceBanner.evaluate(
        tire_calibrated=False,
        aero_calibrated=False,
        correlation_pct=None,
        kinematics_valid="NOT_EVALUATED",
        out_of_envelope_count=0,
    )

    assert banner.validity_status == ValidityStatus.UNVALIDATED
    assert banner.confidence_score_pct == 0.0
    assert banner.telemetry_correlation_pct is None
    assert banner.tire_calibrated is False
    assert banner.aero_calibrated is False
    assert banner.operating_range_exceeded is False
    assert banner.out_of_envelope_points == 0

    badge = banner.to_markdown_badge()
    assert "UNVALIDATED" in badge
    assert "0.0%" in badge


def test_digital_twin_zero_data_defaults():
    """
    Verify DigitalTwin initializes with empty calibration history and None validation score.
    """
    twin = DigitalTwin(
        twin_id="TWIN-UNVALIDATED-001",
        chassis_name="Chassis-ZeroData",
        geometry={},
        mass_properties={},
        suspension={},
        tire_model={},
        aero_map={},
        powertrain={},
    )
    assert twin.calibration_sessions == []
    assert twin.calibrated_samples_count == 0
    assert twin.validation_score_pct is None
    assert twin.uncertainty_pct is None
    assert twin.calibration_result is None


def test_provenance_zero_data_defaults():
    """
    Verify PhysicsObservability and SimulationProvenance initialize truthfully as unvalidated.
    """
    obs = PhysicsObservability(
        solver="rk45",
        backend="python_reference",
        iterations=10,
        convergence=True,
        execution_time_s=0.012,
        model_version="quarter-car-v2",
    )
    assert obs.validation_status == "unvalidated"
    assert obs.validation_score is None

    prov = create_provenance(
        model_family="quarter_car",
        model_version="quarter-car-v2",
        solver_version="rk4-bdf-1.0",
        params={"k_s": 35000.0},
        inputs={"profile": "step"},
        results={"peak_body_accel": 1.2},
    )
    assert prov.validation_state == "unvalidated"
    assert prov.correlation_error is None


def test_kinematics_facade_truthfulness():
    """
    Verify Kinematics Facade truthfully reports active backend:
    - cpp when available
    - python_reference with explicit fallback_reason when C++ is absent
    - strict mode raises RuntimeError instead of silent fallback.
    """
    # 1. Native execution with mode="cpp"
    res_cpp = solve_kinematics(mode="cpp", strict_mode=False)
    assert res_cpp.metadata["active_backend"] in ("cpp", "python_reference")
    if res_cpp.metadata["active_backend"] == "cpp":
        assert res_cpp.metadata["fallback_reason"] is None
        assert "kinematics-core" in res_cpp.metadata["solver_version"]

    # 2. Simulated C++ absence: verify truthful fallback reporting
    backend = CppKinematicsBackend()
    with patch.object(backend, "_get_cpp_module", return_value=None):
        fallback_res = backend.sweep(hardpoints={
            "chassis_upper_front": [0.0, 300.0, 350.0],
            "chassis_upper_rear": [300.0, 300.0, 350.0],
            "upright_upper": [150.0, 700.0, 340.0],
            "chassis_lower_front": [0.0, 250.0, 150.0],
            "chassis_lower_rear": [300.0, 250.0, 150.0],
            "upright_lower": [150.0, 720.0, 140.0],
            "chassis_tie_rod": [50.0, 280.0, 200.0],
            "upright_tie_rod": [100.0, 710.0, 200.0],
            "wheel_center": [150.0, 760.0, 330.0],
        })
        assert fallback_res.metadata["requested_backend"] == "cpp"
        assert fallback_res.metadata["active_backend"] == "python_reference"
        assert fallback_res.metadata["fallback_reason"] in (
            "C++ kinematics_core extension not loaded in runtime environment",
            "cpp_extension_not_loaded",
        )

    # 3. Strict mode: verify silent fallback is strictly forbidden
    sample_hardpoints = {
        "chassis_upper_front": [0.0, 300.0, 350.0],
        "chassis_upper_rear": [300.0, 300.0, 350.0],
        "upright_upper": [150.0, 700.0, 340.0],
        "chassis_lower_front": [0.0, 250.0, 150.0],
        "chassis_lower_rear": [300.0, 250.0, 150.0],
        "upright_lower": [150.0, 720.0, 140.0],
        "chassis_tie_rod": [50.0, 280.0, 200.0],
        "upright_tie_rod": [100.0, 710.0, 200.0],
        "wheel_center": [150.0, 760.0, 330.0],
    }
    with patch("suspensionlab.physics.kinematics._HAVE_CPP", False):
        with pytest.raises(RuntimeError, match="Native C\\+\\+ kinematics binary required in production mode"):
            solve_kinematics(hardpoints=sample_hardpoints, mode="cpp", strict_mode=True)


@pytest.mark.asyncio
async def test_hydrate_engineering_report_zero_delta_fabrication():
    """
    Verify that hydrate_engineering_report does NOT inject fake demo mode deltas
    (-0.087s lap delta, 1.8% body roll, 3.1% tire load) or fake 91.4% correlation
    when no empirical dataset or comparison setup exists.
    """
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    run_id = uuid.uuid4()
    run_label = f"RUN-TRUTH-{uuid.uuid4().hex[:6].upper()}"

    unique_seq = int(uuid.uuid4().int % 1000000000 + 5000000)
    async with SessionLocal() as db:
        sim_run = SimulationRun(
            id=run_id,
            seq=unique_seq,
            label=run_label,
            user_id=user_id,
            team_id=team_id,
            vehicle_ref="Chassis-Truth-01",
            simulation_type="quarter_car",
            params={"k_s": 35000.0, "c": 2200.0, "k_t": 200000.0, "m_s": 300.0, "m_u": 40.0},
            result={"peak_body_accel": 1.25, "rms_body_accel_wk": 0.42, "status": "PASS"},
            software_version="3.0.0",
            physics_version="2.0.0",
            solver_version="scipy-1.11.0",
            params_hash="dummy_hash_p",
            result_hash="dummy_hash_r",
            created_at=datetime.now(timezone.utc),
        )
        db.add(sim_run)
        await db.commit()

    async with SessionLocal() as db:
        hydrated = await hydrate_engineering_report(
            db=db,
            run_id_or_label=run_label,
            user_id=str(user_id),
            team_id=str(team_id),
        )

        # Truthful validation state & score
        assert hydrated["validation_status"] == "UNVALIDATED"
        assert hydrated["correlation_pct"] is None

        # Zero fabricated deltas
        metrics = hydrated.get("metrics", {})
        assert metrics.get("Telemetry Correlation") == "UNVALIDATED (No empirical dataset)"
        assert metrics.get("Simulated Lap Delta") == "+0.000 s"  # Not -0.087 s
