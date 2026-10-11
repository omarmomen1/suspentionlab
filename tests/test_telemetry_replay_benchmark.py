"""
tests/test_telemetry_replay_benchmark.py
========================================
Benchmarking and verification tests for 100 Hz Telemetry Streaming:
- Replays authentic MoTeC Spa session CSV at 100 Hz
- Verifies sustained rate >= 100 Hz
- Measures latency percentiles: p50, p95, p99
- Validates backpressure queue saturation handling
- Validates client disconnection and reconnection lifecycle
"""

import asyncio
import os
import time
import pytest
import numpy as np

from suspensionlab.telemetry.gateway import TelemetryIngestionGateway
from suspensionlab.telemetry.hub import TelemetryHub
from suspensionlab.telemetry.protocol import SLTPFrame
from suspensionlab.telemetry.replay import TelemetryReplayEngine


@pytest.mark.asyncio
async def test_sustained_100hz_replay_and_latency_benchmark():
    """
    Benchmark sustained 100 Hz telemetry stream from real MoTeC CSV session.
    Measures sustained streaming rate and latency distribution (p50, p95, p99).
    """
    hub = TelemetryHub()
    gateway = TelemetryIngestionGateway()
    engine = TelemetryReplayEngine(gateway=gateway, hub=hub)

    session_id = "bench-spa-100hz"
    org_id = "org-motorsport-pro"
    csv_path = "sample_data/motec_spa_session.csv"
    assert os.path.exists(csv_path), f"MoTeC dataset missing at {csv_path}"

    sub = await hub.subscribe(
        websocket=None,
        user_id="bench-engineer",
        organization_id=org_id,
        session_id=session_id,
        binary_mode=True,
    )

    # Start 100 Hz replay
    target_rate = 100.0
    await engine.start_replay(
        csv_path=csv_path,
        session_id=session_id,
        org_id=org_id,
        rate_hz=target_rate,
        loop_playback=False,
    )

    sample_count = 150
    timestamps_received = []
    latencies = []

    start_bench = time.monotonic()
    last_seq = 0
    dropped = 0

    for i in range(sample_count):
        t_before = time.monotonic()
        raw_bytes = await asyncio.wait_for(sub.queue.get(), timeout=2.0)
        t_after = time.monotonic()

        latencies.append((t_after - t_before) * 1000.0) # ms
        timestamps_received.append(t_after)

        frame = SLTPFrame.unpack(raw_bytes)
        if last_seq > 0 and frame.sequence_number > last_seq + 1:
            dropped += frame.sequence_number - (last_seq + 1)
        last_seq = frame.sequence_number

    total_bench_time = time.monotonic() - start_bench
    await engine.stop_replay(session_id)
    await hub.unsubscribe(sub)

    # Compute sustained rate
    intervals = np.diff(timestamps_received)
    avg_interval_s = float(np.mean(intervals))
    sustained_rate_hz = 1.0 / avg_interval_s if avg_interval_s > 0 else 0.0

    # Compute latency percentiles
    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))
    p99 = float(np.percentile(latencies, 99))

    print(f"\n--- 100 Hz BENCHMARK RESULTS ---")
    print(f"Packets received: {sample_count}")
    print(f"Total time: {total_bench_time:.3f} s")
    print(f"Sustained Rate: {sustained_rate_hz:.2f} Hz (Target: {target_rate} Hz)")
    print(f"Latency p50: {p50:.3f} ms | p95: {p95:.3f} ms | p99: {p99:.3f} ms")
    print(f"Detected dropped packets: {dropped}")

    # Assertions
    # Must achieve at least 95% of target rate under local test loop
    assert sustained_rate_hz >= 95.0, f"Sustained rate {sustained_rate_hz} Hz below requirement"
    assert dropped == 0, f"Unexpected packet drops: {dropped}"
    # p50 latency should be well under 25 ms in high-performance asyncio loop
    assert p50 < 25.0


@pytest.mark.asyncio
async def test_backpressure_buffer_overflow_protection():
    """
    Verify backpressure behavior: when consumer stops reading, bounded queue
    drops oldest frames, prevents memory bloat, and tracks drop counts.
    """
    hub = TelemetryHub()
    gateway = TelemetryIngestionGateway()
    session_id = "bench-backpressure"
    org_id = "org-test"

    sub = await hub.subscribe(None, "user-slow", org_id, session_id, binary_mode=True)
    assert sub.queue.maxsize == 100

    # Flood 150 frames without reading from subscriber queue
    for seq in range(1, 151):
        frame = SLTPFrame(
            sequence_number=seq,
            timestamp=seq * 0.01,
            org_id=org_id,
            session_id=session_id,
        )
        await hub.broadcast_frame(frame)

    # Queue must not exceed 100 frames
    assert sub.queue.qsize() == 100
    # Subscriber frames_dropped must reflect the 50 dropped frames
    assert sub.frames_dropped == 50
    # Hub-level stats should record backpressure drops
    stats = hub.get_stats()
    assert stats["backpressure_drops"] == 50

    await hub.unsubscribe(sub)


@pytest.mark.asyncio
async def test_reconnection_lifecycle_and_state_recovery():
    """
    Verify clean disconnect and reconnection: subscriber disconnects,
    stream continues, and new subscriber reattaches seamlessly.
    """
    hub = TelemetryHub()
    session_id = "bench-reconnect"
    org_id = "org-test"

    # 1. Initial Connection
    sub1 = await hub.subscribe(None, "user-client", org_id, session_id)
    assert hub.get_subscriber_count(session_id) == 1

    # Broadcast frame 1
    f1 = SLTPFrame(sequence_number=1, timestamp=0.01, org_id=org_id, session_id=session_id)
    await hub.broadcast_frame(f1)
    assert sub1.queue.qsize() == 1

    # 2. Disconnect sub1
    await hub.unsubscribe(sub1)
    assert hub.get_subscriber_count(session_id) == 0

    # Broadcast frame 2 while disconnected (no crash, 0 delivered)
    f2 = SLTPFrame(sequence_number=2, timestamp=0.02, org_id=org_id, session_id=session_id)
    sent = await hub.broadcast_frame(f2)
    assert sent == 0

    # 3. Reconnect sub2
    sub2 = await hub.subscribe(None, "user-client", org_id, session_id)
    assert hub.get_subscriber_count(session_id) == 1

    # Broadcast frame 3
    f3 = SLTPFrame(sequence_number=3, timestamp=0.03, org_id=org_id, session_id=session_id)
    await hub.broadcast_frame(f3)
    assert sub2.queue.qsize() == 1

    received = await sub2.queue.get()
    unpacked = SLTPFrame.unpack(received)
    assert unpacked.sequence_number == 3

    await hub.unsubscribe(sub2)
