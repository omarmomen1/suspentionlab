"""Wave 6 §2: telemetry ingestion hardening (rejection surfacing, CSV template, channel-map preview)."""
import pytest


@pytest.mark.asyncio
async def test_reference_csv_template_downloadable(client):
    resp = await client.get("/api/v1/telemetry/csv-template")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    body = resp.text
    header = body.splitlines()[0]
    assert "time" in header and "susp_fl" in header
    assert len(body.splitlines()) >= 2  # header + example rows


@pytest.mark.asyncio
async def test_channel_map_preview_motec_aliases(authenticated_client):
    csv = "Time,Vehicle Speed,Throttle Pos,G Force Lat,Unknown Channel XYZ\n0.0,120.5,45.0,0.8,42\n"
    resp = await authenticated_client.post(
        "/api/v1/telemetry/channel-map-preview",
        files={"file": ("motec.csv", csv, "text/csv")},
    )
    assert resp.status_code == 200, resp.text[:300]
    data = resp.json()
    assert data["n_mapped"] >= 3
    # Speed alias detected
    keys = set(data["channel_map"].keys())
    assert any("speed" in k for k in keys)
    # Unknown column reported, not silently dropped
    assert "Unknown Channel XYZ" in data["unmapped_columns"]
