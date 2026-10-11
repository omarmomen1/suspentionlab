"""
tests/test_decision_dashboard_and_overlays.py
=============================================
Tests for decision-first executive dashboard, semantic overlays, and accessible tables (Findings 63, 64, 65, 68).
"""

import pytest
import numpy as np

from suspensionlab.physics.semantic_overlays import (
    compute_damper_distribution,
    segment_corner_phases,
    DamperQuadrantDistribution,
    CornerPhase,
)
from suspensionlab.physics.decision_dashboard import (
    generate_executive_summary,
    ExecutiveEngineeringSummary,
    WorkflowStage,
)
from suspensionlab.physics.accessibility_tables import (
    generate_time_series_accessible_table,
    AccessibleTableData,
)


def test_damper_velocity_quadrant_distribution():
    # Synthetic velocities: mixture of low and high speed compression and rebound
    v_damper = np.array([0.02, 0.04, 0.08, 0.12, -0.01, -0.03, -0.09, -0.15])
    dist = compute_damper_distribution(v_damper, knee_velocity_m_s=0.050)
    
    assert isinstance(dist, DamperQuadrantDistribution)
    assert dist.low_speed_comp_pct == 25.0
    assert dist.high_speed_comp_pct == 25.0
    assert dist.low_speed_reb_pct == 25.0
    assert dist.high_speed_reb_pct == 25.0


def test_corner_phase_segmentation():
    dist = np.array([0.0, 50.0, 100.0, 150.0, 200.0])
    spd = np.array([50.0, 40.0, 30.0, 35.0, 45.0])
    ax = np.array([0.0, -0.6, 0.0, 0.3, 0.4])    # Braking -> Apex -> Exit
    ay = np.array([0.1, 0.2, 1.4, 0.9, 0.2])

    bands = segment_corner_phases(dist, spd, ax, ay)
    assert len(bands) >= 2
    phases = [b.phase for b in bands]
    assert CornerPhase.BRAKING in phases or CornerPhase.APEX in phases


def test_decision_first_executive_summary():
    base = {"k_sf": 35000.0, "k_sr": 38000.0, "c_lsr": 2400.0}
    cand = {"k_sf": 35000.0, "k_sr": 42000.0, "c_lsr": 2600.0}

    summary = generate_executive_summary(base, cand, lap_delta_s=-0.087, confidence_pct=87.0)
    assert isinstance(summary, ExecutiveEngineeringSummary)
    assert summary.lap_time_delta_s == -0.087
    assert summary.confidence_score_pct == 87.0
    assert len(summary.causal_explanation) >= 3
    assert len(summary.recommended_actions) >= 2

    md_card = summary.to_markdown_card()
    assert "Executive Engineering Summary" in md_card
    assert "-0.087 s" in md_card
    assert "What Should I Change?" in md_card


def test_accessible_tabular_alternatives():
    time_s = np.linspace(0.0, 1.0, 50)
    channels = {
        "body_displacement_mm": np.sin(time_s) * 10.0,
        "damper_velocity_mm_s": np.cos(time_s) * 50.0,
    }

    tbl = generate_time_series_accessible_table(time_s, channels, sample_stride=5)
    assert isinstance(tbl, AccessibleTableData)
    assert len(tbl.column_headers) == 3
    assert len(tbl.rows) == 10

    md_tbl = tbl.to_markdown_table()
    assert "| Time (s) | Body Displacement Mm | Damper Velocity Mm S |" in md_tbl
