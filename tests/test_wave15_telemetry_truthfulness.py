"""
tests/test_wave15_telemetry_truthfulness.py
===========================================
Wave 15 - Telemetry: label the replay, give sessions a home.

Pins four behaviours:
1. The bundled Spa fallback is labeled SAMPLE_REPLAY end to end.
2. A non-sample replay requires an explicit dataset id (and a missing file is a
   404, never a silent substitution).
3. The Live Monitor does not auto-start the bundled replay on mount.
4. A dead WebSocket has a real polling fallback, and the label that goes with it.
"""

import os

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOOK = os.path.join(REPO, "frontend", "lib", "telemetry", "useLiveTelemetry.ts")
DIGITAL_TWIN = os.path.join(REPO, "frontend", "app", "digital-twin", "page.tsx")
TELEMETRY_PAGE = os.path.join(REPO, "frontend", "app", "telemetry", "page.tsx")
ROUTES = os.path.join(
    REPO, "src", "suspensionlab", "backend", "api", "routes", "telemetry_routes.py"
)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _synthetic_csv(n=200, rate_hz=100.0):
    rows = ["time,speed,vert_g,lat_g,long_g,steerangle,throttlepos,brakepress_f,enginerpm,susptravel_fl"]
    for i in range(n):
        t = i / rate_hz
        rows.append(
            f"{t:.3f},{30.0 + 5.0 * (i % 20) / 20.0:.3f},{0.02 * ((i % 7) - 3):.4f},"
            f"{0.6 * ((i % 11) - 5) / 5.0:.3f},{0.3 * ((i % 5) - 2) / 2.0:.3f},"
            f"{12.0 * ((i % 9) - 4) / 4.0:.3f},{20.0 + (i % 30):.1f},"
            f"{5.0 + (i % 4):.1f},{4000 + (i % 50) * 20},{(i % 13) - 6:.2f}"
        )
    return "\n".join(rows) + "\n"


@pytest.mark.asyncio
async def test_replay_default_is_labeled_sample_replay(authenticated_client):
    """No dataset named: the bundled Spa session runs, labeled SAMPLE_REPLAY."""
    try:
        resp = await authenticated_client.post(
            "/api/v1/telemetry/replay/start", json={"session_id": "sess-wave15-sample"}
        )
        assert resp.status_code == 200, resp.text[:300]
        data = resp.json()
        assert data["source"] == "SAMPLE_REPLAY"
        assert data["is_sample"] is True
        assert data["explicit_dataset"] is False
        assert "not your car" in data["banner"]

        status = await authenticated_client.get(
            "/api/v1/telemetry/replay/status?session_id=sess-wave15-sample"
        )
        assert status.status_code == 200
        assert status.json()["source"] == "SAMPLE_REPLAY"
        assert status.json()["is_sample"] is True
    finally:
        await authenticated_client.post(
            "/api/v1/telemetry/replay/stop", params={"session_id": "sess-wave15-sample"}
        )


@pytest.mark.asyncio
async def test_replay_requires_explicit_dataset_for_non_sample(authenticated_client):
    """A named dataset replays as DATASET_REPLAY; a missing one is a 404, not the sample."""
    try:
        resp = await authenticated_client.post(
            "/api/v1/telemetry/replay/start",
            json={
                "dataset": "sample_data/aim_silverstone_session.csv",
                "session_id": "sess-wave15-aim",
            },
        )
        assert resp.status_code == 200, resp.text[:300]
        data = resp.json()
        assert data["source"] == "DATASET_REPLAY"
        assert data["is_sample"] is False
        assert data["explicit_dataset"] is True
    finally:
        await authenticated_client.post(
            "/api/v1/telemetry/replay/stop", params={"session_id": "sess-wave15-aim"}
        )

    missing = await authenticated_client.post(
        "/api/v1/telemetry/replay/start",
        json={"dataset": "sample_data/does_not_exist.csv", "session_id": "sess-wave15-missing"},
    )
    assert missing.status_code == 404, missing.text[:300]
    assert "not found" in missing.text.lower()


def test_live_monitor_does_not_autostart():
    """The hook exposes no mount-time replay start, and the page states the empty state."""
    hook = _read(HOOK)
    page = _read(DIGITAL_TWIN)

    # No effect may start a stream or replay on its own.
    assert "useEffect(() => {\n    triggerReplay" not in hook
    assert "useEffect(() => {\n    startSampleReplay" not in hook
    assert "useEffect(() => {\n    startStream" not in hook
    assert "useEffect(() => {\n    triggerReplay" not in page
    assert "useEffect(() => {\n    startStream" not in page

    # The required empty state, and a sample replay that is named as a sample.
    assert "No live source. Upload a session, pick a stored dataset, or connect a DAQ gateway." in page
    assert "Play sample replay" in page
    assert "SAMPLE REPLAY - bundled Spa session, not your car" in page


def test_ws_failure_falls_back_to_polling():
    """A dead socket degrades to polling, visibly, instead of spinning."""
    hook = _read(HOOK)
    routes = _read(ROUTES)

    assert "/api/v1/telemetry/live/poll" in hook
    assert "Live stream unavailable on this host - polling mode" in hook
    assert "setMode(\"polling\")" in hook or 'setMode("polling")' in hook
    # an open timeout exists, so a socket that never opens cannot hang forever
    assert "SOCKET_OPEN_TIMEOUT_MS" in hook
    assert "MAX_WS_FAILURES" in hook
    # and the backend really serves the fallback
    assert '@router.get(\n    "/live/poll"' in routes
    assert '"mode": "polling"' in routes

    # the monitor is wired to show the polling notice
    page = _read(DIGITAL_TWIN)
    assert "pollingNotice" in page


def test_telemetry_home_shows_every_channel_and_qa_row():
    """The new page renders the stored /analyse payload: channel map, QA, health, segments."""
    page = _read(TELEMETRY_PAGE)
    assert '/api/v1/telemetry/sessions' in page
    assert '/api/v1/telemetry/analyse' in page
    assert "Channel map" in page
    assert "Health per channel" in page
    assert "Lap segments" in page
    assert "Dropout intervals" in page
    assert "Dead sensors" in page
    assert "Rate mismatch" in page


@pytest.mark.asyncio
async def test_analyse_persists_session_for_the_telemetry_home(authenticated_client):
    """An uploaded session is listed and can be reopened with its channel map and QA."""
    resp = await authenticated_client.post(
        "/api/v1/telemetry/analyse",
        files={"file": ("wave15_session.csv", _synthetic_csv(), "text/csv")},
        data={"session_name": "Wave 15 synthetic session"},
    )
    assert resp.status_code == 200, resp.text[:600]
    body = resp.json()
    assert body["stored"] is True
    session_id = body["session_id"]
    assert session_id.startswith("ts-")

    listing = await authenticated_client.get("/api/v1/telemetry/sessions")
    assert listing.status_code == 200, listing.text[:300]
    rows = listing.json()["sessions"]
    assert any(r["session_id"] == session_id for r in rows)
    row = next(r for r in rows if r["session_id"] == session_id)
    assert row["name"] == "Wave 15 synthetic session"
    assert row["n_channels"] >= 1

    detail = await authenticated_client.get(f"/api/v1/telemetry/sessions/{session_id}")
    assert detail.status_code == 200, detail.text[:300]
    stored = detail.json()
    assert stored["channel_map"]
    assert stored["qa"] is not None
    assert "segments" in stored
    assert "health" in stored


@pytest.mark.asyncio
async def test_live_poll_returns_frames_and_provenance(authenticated_client):
    """The polling endpoint is real: it drains hub frames and labels them."""
    resp = await authenticated_client.get(
        "/api/v1/telemetry/live/poll?session_id=sess-wave15-poll&max_frames=5&timeout_ms=150"
    )
    assert resp.status_code == 200, resp.text[:300]
    body = resp.json()
    assert body["mode"] == "polling"
    assert isinstance(body["frames"], list)
    assert body["count"] == len(body["frames"])
    # every returned frame carries the same provenance the stream would
    for frame in body["frames"]:
        assert frame.get("type") == "telemetry_frame"
        assert frame.get("source") == body["source"]
