"""Targeted regression tests for Sprint 1 fixes (Items 3, 4, 5, 7, 8)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from suspensionlab.backend.api.routes.ai_engineer_routes import _handle_lap_time_worse
from suspensionlab.backend.api.routes.kinematics_routes import BENCHMARK_PRESETS
from suspensionlab.backend.services.experiment_service import ExperimentService


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_item3_gt3_default_preset_passes_physical_benchmarks(authenticated_client):
    """Frontend DEFAULT_HP matches GT3 Touring baseline and passes physical benchmarks with zero warnings."""
    kin_page = (REPO_ROOT / "frontend" / "app" / "kinematics" / "page.tsx").read_text(encoding="utf-8")
    m = re.search(r"const DEFAULT_HP:\s*Hardpoints\s*=\s*\{(.*?)\};", kin_page, re.S)
    assert m is not None, "DEFAULT_HP block not found in kinematics/page.tsx"

    expected_gt3 = BENCHMARK_PRESETS["gt3_touring"]
    for key, coords in expected_gt3["hardpoints"].items():
        if not isinstance(coords, list):
            continue
        km = re.search(rf"{key}:\s*\[([^\]]+)\]", m.group(1))
        assert km is not None, f"Missing key {key} in DEFAULT_HP"
        parsed = [float(x.strip()) for x in km.group(1).split(",")]
        assert parsed == pytest.approx(coords, abs=1e-6)

    resp = await authenticated_client.post(
        "/api/v1/kinematics/solve",
        json={
            "hardpoints": expected_gt3["hardpoints"],
            "tire_radius_m": expected_gt3["tire_radius_m"],
            "z_min_mm": -50.0,
            "z_max_mm": 50.0,
            "n_steps": 21,
        },
    )
    assert resp.status_code == 200, resp.text[:300]
    data = resp.json()
    assert data["overall_model_status"] == "PASS"
    assert data["model_validity"]["overall_status"] == "PASS"
    assert data["physical_issues"] == []

    bench_resp = await authenticated_client.post(
        "/api/v1/kinematics/benchmarks",
        json={
            "hardpoints": expected_gt3["hardpoints"],
            "tire_radius_m": expected_gt3["tire_radius_m"],
            "z_min_mm": -50.0,
            "z_max_mm": 50.0,
            "n_steps": 21,
        },
    )
    assert bench_resp.status_code == 200, bench_resp.text[:300]
    verdicts = {b["status"] for b in bench_resp.json()}
    assert "FAIL" not in verdicts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/telemetry/channel-map-preview",
        "/api/v1/telemetry/analyse",
        "/api/v1/telemetry/dataset",
    ],
)
async def test_item4_garbage_csv_rejected_with_422(authenticated_client, endpoint):
    """Unrelated/garbage CSVs without time + telemetry channels must return HTTP 422."""
    garbage_csv = "col_a,col_b,col_c\n1,2,3\n4,5,6\n"
    resp = await authenticated_client.post(
        endpoint,
        files={"file": ("garbage.csv", garbage_csv, "text/csv")},
    )
    assert resp.status_code == 422, f"{endpoint} accepted garbage CSV: {resp.status_code} {resp.text[:200]}"

    no_telemetry_channels = "time,foo,bar\n0.0,1,2\n0.1,3,4\n"
    resp2 = await authenticated_client.post(
        endpoint,
        files={"file": ("no_channels.csv", no_telemetry_channels, "text/csv")},
    )
    assert resp2.status_code == 422, f"{endpoint} accepted non-telemetry CSV: {resp2.status_code} {resp2.text[:200]}"


def test_item5_optimize_pareto_produces_distinct_archetypes():
    """Widened ISO-8608 Pareto search completes quickly with multiple Pareto points and 3 distinct archetypes."""
    t0 = time.perf_counter()
    res = ExperimentService.batch_optimize_pareto(
        base_params={"m_s": 320.0, "m_u": 45.0, "k_t": 220000.0, "MR": 0.85},
        param_ranges={"k_s": [15000.0, 55000.0, 6], "c": [900.0, 3900.0, 6]},
        road_profile={"speed_mps": 30.0},
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0
    assert res["feasible_count"] >= 10
    assert res["pareto_optimal_count"] >= 3

    frontier = res["pareto_frontier"]
    balanced = res["best_compromise"]
    assert balanced and len(frontier) >= 3
    max_grip = min(frontier, key=lambda pt: pt["objectives"]["tire_load_variation"])
    max_comfort = min(frontier, key=lambda pt: pt["objectives"]["rms_body_accel"])

    setups = {
        (round(balanced["params"]["k_s"], 1), round(balanced["params"]["c"], 1)),
        (round(max_grip["params"]["k_s"], 1), round(max_grip["params"]["c"], 1)),
        (round(max_comfort["params"]["k_s"], 1), round(max_comfort["params"]["c"], 1)),
    }
    assert len(setups) == 3, f"Archetypes collapsed onto fewer than 3 distinct setups: {setups}"


@pytest.mark.asyncio
async def test_item7_ai_engineer_grounded_and_consistent():
    """AI Engineer lap-time diagnosis computes non-zero confidence and avoids fabricated claims or contradictions."""
    resp = await _handle_lap_time_worse(
        "Why is lap time worse on kerbs?",
        {"k_s": 25000.0, "c": 2050.0, "m_s": 300.0, "MR": 0.85},
        None,
    )
    assert resp.confidence > 0.0

    blob = json.dumps(resp.model_dump())
    assert "Lap 12" not in blob
    assert "Lap 14" not in blob
    assert "+6" not in blob

    expected_c = round(max(800.0, 2050.0 * 0.90), 1)
    assert resp.best_feasible[0].recommended_value == pytest.approx(expected_c, abs=1e-6)
    assert resp.recommendations[0].recommended_value == pytest.approx(expected_c, abs=1e-6)


@pytest.mark.asyncio
async def test_item8_ai_approve_returns_403_for_unprivileged_role(authenticated_client):
    """Attempting human approval with an unauthorized role returns HTTP 403 cleanly."""
    resp = await authenticated_client.post(
        "/api/v1/ai/approve",
        json={
            "decision_id": "DEC-SPRINT1-TEST",
            "approver_name": "Viewer User",
            "approver_role": "viewer",
            "autonomous_request": False,
        },
    )
    assert resp.status_code == 403, resp.text[:300]
