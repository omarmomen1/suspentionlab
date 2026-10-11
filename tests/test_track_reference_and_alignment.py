"""
tests/test_track_reference_and_alignment.py
===========================================
Tests for Step 7: TrackReference spatial curvature, elevation, banking, and sector alignment.
"""

import pytest
import numpy as np

from suspensionlab.physics.telemetry_dataset import (
    TrackReference,
    CornerSegment,
    SectorSegment,
)


def test_track_reference_spatial_properties():
    """Verify TrackReference correctly interpolates curvature, banking, and elevation."""
    dist_grid = np.array([0.0, 1000.0, 2000.0, 3000.0])
    curv_grid = np.array([0.0, 0.015, 0.0, 0.020]) # 1/m
    bank_grid = np.array([0.0, 3.5, 0.0, 5.0])    # deg
    elev_grid = np.array([100.0, 105.0, 95.0, 110.0]) # m

    track = TrackReference(
        track_name="Test Circuit",
        track_id="TEST-01",
        total_length_m=3000.0,
        distance_grid=dist_grid,
        curvature_grid=curv_grid,
        banking_grid=bank_grid,
        elevation_grid=elev_grid,
    )

    props = track.get_spatial_properties(np.array([500.0, 1000.0, 2500.0]))
    
    # At s=500 -> halfway between 0 and 1000 -> curvature 0.0075, bank 1.75 deg, elev 102.5 m
    assert pytest.approx(props["curvature_1_m"][0], abs=1e-4) == 0.0075
    assert pytest.approx(props["bank_deg"][0], abs=1e-3) == 1.75
    assert pytest.approx(props["elevation_m"][0], abs=1e-3) == 102.5


def test_track_reference_corner_identification():
    """Verify corner segmentation correctly identifies active corner at distance s."""
    c1 = CornerSegment("T1", "Abbey", start_distance_m=100.0, end_distance_m=400.0, apex_distance_m=250.0, apex_radius_m=120.0, direction="right")
    c2 = CornerSegment("T2", "Farm", start_distance_m=500.0, end_distance_m=800.0, apex_distance_m=650.0, apex_radius_m=180.0, direction="left")

    track = TrackReference(
        track_name="Silverstone GP",
        total_length_m=5891.0,
        corners=[c1, c2],
    )

    # In T1
    found1 = track.identify_corner_at(200.0)
    assert found1 is not None
    assert found1.corner_id == "T1"
    assert found1.name == "Abbey"

    # In T2
    found2 = track.identify_corner_at(600.0)
    assert found2 is not None
    assert found2.corner_id == "T2"

    # On straight between corners
    found_straight = track.identify_corner_at(450.0)
    assert found_straight is None


def test_speed_profile_distance_integration():
    """Verify speed integration projects timestamps to track distance accurately."""
    track = TrackReference()
    t = np.array([0.0, 1.0, 2.0, 3.0])
    v = np.array([10.0, 20.0, 20.0, 10.0]) # m/s

    # Integral:
    # 0->1: 0.5 * (10 + 20) * 1 = 15 m
    # 1->2: 20 * 1 = 20 m (total 35 m)
    # 2->3: 0.5 * (20 + 10) * 1 = 15 m (total 50 m)
    dist = track.project_speed_profile_to_distance(t, v)
    
    assert len(dist) == 4
    assert pytest.approx(dist[0], abs=1e-3) == 0.0
    assert pytest.approx(dist[1], abs=1e-3) == 15.0
    assert pytest.approx(dist[2], abs=1e-3) == 35.0
    assert pytest.approx(dist[3], abs=1e-3) == 50.0
