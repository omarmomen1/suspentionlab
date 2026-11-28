"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  parseSLTPBinaryFrame,
  TelemetrySequenceTracker,
  StreamStatus,
  StreamMetrics,
  DigitalTwinState,
  ParsedTelemetryFrame,
} from "./telemetryClient";
import { apiFetch } from "../api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Wave 15 item 4: a socket that never opens must not hang the monitor. */
const SOCKET_OPEN_TIMEOUT_MS = 4000;
/** After this many failed socket attempts we stop retrying and poll instead. */
const MAX_WS_FAILURES = 2;
const POLL_INTERVAL_MS = 400;
const POLL_FRAMES = 25;
/** Consecutive HTTP failures before polling itself gives up (never spin forever). */
const MAX_POLL_FAILURES = 5;

const SAMPLE_REPLAY_DATASET = "sample_data/motec_spa_session.csv";
export const POLLING_NOTICE = "Live stream unavailable on this host - polling mode";

export type StreamMode = "idle" | "websocket" | "polling";

export interface LiveTelemetryData {
  speed_ms: number;
  lat_g: number;
  long_g: number;
  steer_rad: number;
  susp_travel_fl: number;
  susp_travel_fr: number;
  susp_travel_rl: number;
  susp_travel_rr: number;
  brake_press_f: number;
  throttle_pos: number;
  engine_rpm: number;
}

const EMPTY_TELEMETRY: LiveTelemetryData = {
  speed_ms: 0,
  lat_g: 0,
  long_g: 0,
  steer_rad: 0,
  susp_travel_fl: 0,
  susp_travel_fr: 0,
  susp_travel_rl: 0,
  susp_travel_rr: 0,
  brake_press_f: 0,
  throttle_pos: 0,
  engine_rpm: 0,
};

export function useLiveTelemetry(token: string | null) {
  const [status, setStatus] = useState<StreamStatus>("DISCONNECTED");
  const [mode, setMode] = useState<StreamMode>("idle");
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [isReplaying, setIsReplaying] = useState<boolean>(false);
  // Wave 15 item 1: the backend declares whether this is the bundled sample.
  const [streamSource, setStreamSource] = useState<string | null>(null);

  const [telemetry, setTelemetry] = useState<LiveTelemetryData>(EMPTY_TELEMETRY);
  const [twin, setTwin] = useState<DigitalTwinState | null>(null);

  const [metrics, setMetrics] = useState<StreamMetrics>({
    rateHz: 0,
    latencyMs: 0,
    sequenceNumber: 0,
    droppedPackets: 0,
    duplicatePackets: 0,
    outOfOrderPackets: 0,
    lossRatePct: 0,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const trackerRef = useRef<TelemetrySequenceTracker>(new TelemetrySequenceTracker());
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const heartbeatIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const openTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const wsFailureCountRef = useRef<number>(0);
  const pollFailureCountRef = useRef<number>(0);
  const backoffRef = useRef<number>(1000);
  const frameCountWindowRef = useRef<number>(0);
  const lastRateCalcTimeRef = useRef<number>(Date.now());
  const lastFrameTimeRef = useRef<number>(0);
  const streamingRef = useRef<boolean>(false);
  const sampleReplayRef = useRef<boolean>(false);

  const cleanupSocket = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (openTimeoutRef.current) {
      clearTimeout(openTimeoutRef.current);
      openTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const applyJsonFrame = useCallback((json: any) => {
    if (!json || json.type !== "telemetry_frame") return;
    trackerRef.current.processSequence(json.seq || 0);
    if (json.source) setStreamSource(json.source);
    setTelemetry({
      speed_ms: json.speed_ms ?? 0,
      lat_g: json.lat_g ?? 0,
      long_g: json.long_g ?? 0,
      steer_rad: json.steer_rad ?? 0,
      susp_travel_fl: json.susp_travel_fl ?? 0,
      susp_travel_fr: json.susp_travel_fr ?? 0,
      susp_travel_rl: json.susp_travel_rl ?? 0,
      susp_travel_rr: json.susp_travel_rr ?? 0,
      brake_press_f: json.brake_press_f ?? 0,
      throttle_pos: json.throttle_pos ?? 0,
      engine_rpm: json.engine_rpm ?? 0,
    });
    if (json.twin) {
      setTwin({
        theoreticalMaxLatG: json.twin.theoretical_max_lat_g,
        actualLatG: json.twin.actual_lat_g,
        divergencePct: json.twin.divergence_pct,
        gripStatus: 1,
        gripStatusLabel: json.twin.grip_status,
      });
    }
  }, []);

  const applyBinaryFrame = useCallback((frame: ParsedTelemetryFrame) => {
    trackerRef.current.processSequence(frame.sequenceNumber);
    setTelemetry({
      speed_ms: frame.speedMs,
      lat_g: frame.latG,
      long_g: frame.longG,
      steer_rad: frame.steerRad,
      susp_travel_fl: frame.suspTravelFL,
      susp_travel_fr: frame.suspTravelFR,
      susp_travel_rl: frame.suspTravelRL,
      susp_travel_rr: frame.suspTravelRR,
      brake_press_f: frame.brakePressF,
      throttle_pos: frame.throttlePos,
      engine_rpm: frame.engineRpm,
    });
    if (frame.twin) {
      setTwin(frame.twin);
    }
  }, []);

  const updateRate = useCallback(() => {
    const now = Date.now();
    const dtRate = now - lastRateCalcTimeRef.current;
    if (dtRate < 500) return;
    const currentHz = Number(((frameCountWindowRef.current / dtRate) * 1000).toFixed(1));
    frameCountWindowRef.current = 0;
    lastRateCalcTimeRef.current = now;

    const loss = trackerRef.current.getLossRatePct();
    if (loss > 2.0 || currentHz < 20) {
      setStatus("DEGRADED");
    } else {
      setStatus("LIVE");
    }

    setMetrics((prev) => ({
      ...prev,
      rateHz: currentHz,
      lossRatePct: loss,
      droppedPackets: trackerRef.current.droppedPackets,
      duplicatePackets: trackerRef.current.duplicatePackets,
      outOfOrderPackets: trackerRef.current.outOfOrderPackets,
      sequenceNumber: trackerRef.current.lastSequence,
    }));
  }, []);

  /**
   * Wave 15 item 4: WebSocket is unavailable here, so read frames over HTTP.
   * The monitor says so instead of pretending to be live, and it gives up after
   * MAX_POLL_FAILURES rather than polling forever.
   */
  const pollOnce = useCallback(async (): Promise<void> => {
    try {
      const res = await apiFetch(
        `/api/v1/telemetry/live/poll?session_id=sess-live&max_frames=${POLL_FRAMES}&timeout_ms=250`
      );
      if (!res.ok) {
        throw new Error(`poll ${res.status}`);
      }
      const body = await res.json();
      pollFailureCountRef.current = 0;
      if (body?.source) setStreamSource(body.source);
      const frames: any[] = Array.isArray(body?.frames) ? body.frames : [];
      if (frames.length > 0) {
        lastFrameTimeRef.current = Date.now();
        frames.forEach((f) => applyJsonFrame(f));
        frameCountWindowRef.current += frames.length;
        updateRate();
      }
    } catch (err) {
      pollFailureCountRef.current += 1;
      if (pollFailureCountRef.current >= MAX_POLL_FAILURES) {
        stopPolling();
        setMode("idle");
        setStatus("DISCONNECTED");
        return;
      }
    }
    if (streamingRef.current) {
      pollTimerRef.current = setTimeout(pollOnce, POLL_INTERVAL_MS);
    }
  }, [applyJsonFrame, stopPolling, updateRate]);

  const startPolling = useCallback(() => {
    if (pollTimerRef.current) return;
    cleanupSocket();
    setMode("polling");
    setStatus("DEGRADED");
    pollFailureCountRef.current = 0;
    pollTimerRef.current = setTimeout(pollOnce, 0);
  }, [cleanupSocket, pollOnce]);

  const connect = useCallback(() => {
    cleanupSocket();

    const wsProtocol = API_BASE.startsWith("https") ? "wss:" : "ws:";
    const host = API_BASE.replace(/^https?:\/\//, "");
    // Wave 6 cookie-only auth: when no explicit token is supplied, omit the
    // query param so the backend authenticates via the HttpOnly sl_token
    // cookie (sent automatically on same-origin WebSocket handshakes).
    const tokenParam = token ? `&token=${encodeURIComponent(token)}` : "";
    const wsUrl = `${wsProtocol}//${host}/api/v1/telemetry/live?session_id=sess-live&format=json${tokenParam}`;

    const handleSocketFailure = () => {
      wsFailureCountRef.current += 1;
      if (wsFailureCountRef.current >= MAX_WS_FAILURES) {
        // Stop retrying: this host does not serve the socket.
        startPolling();
        return;
      }
      const jitter = Math.random() * 500;
      const delay = Math.min(15000, backoffRef.current + jitter);
      backoffRef.current = Math.min(15000, backoffRef.current * 1.5);
      reconnectTimeoutRef.current = setTimeout(connect, delay);
    };

    try {
      const ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      // A socket that never opens is a failure, not a wait.
      openTimeoutRef.current = setTimeout(() => {
        if (wsRef.current === ws && ws.readyState !== WebSocket.OPEN) {
          wsRef.current = null;
          try {
            ws.close();
          } catch {}
          setStatus("DISCONNECTED");
          if (streamingRef.current) handleSocketFailure();
        }
      }, SOCKET_OPEN_TIMEOUT_MS);

      ws.onopen = () => {
        if (openTimeoutRef.current) {
          clearTimeout(openTimeoutRef.current);
          openTimeoutRef.current = null;
        }
        backoffRef.current = 1000;
        wsFailureCountRef.current = 0;
        setMode("websocket");
        setStatus("LIVE");

        // Send periodic heartbeat ping
        heartbeatIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 15000);
      };

      ws.onmessage = (event) => {
        lastFrameTimeRef.current = Date.now();
        frameCountWindowRef.current += 1;
        updateRate();

        if (event.data instanceof ArrayBuffer) {
          try {
            applyBinaryFrame(parseSLTPBinaryFrame(event.data));
          } catch (err) {
            console.error("Error parsing binary SLTP frame:", err);
          }
        } else if (typeof event.data === "string") {
          try {
            const json = JSON.parse(event.data);
            if (json.type === "pong") {
              const rtt = Date.now() - (json.ts * 1000);
              if (rtt > 0 && rtt < 5000) {
                setMetrics((prev) => ({ ...prev, latencyMs: Math.round(rtt) }));
              }
            } else if (json.type === "telemetry_frame") {
              applyJsonFrame(json);
            }
          } catch {}
        }
      };

      ws.onclose = () => {
        setStatus("DISCONNECTED");
        if (streamingRef.current) {
          handleSocketFailure();
        }
      };

      ws.onerror = (err) => {
        console.warn("WebSocket error:", err);
        setStatus("DISCONNECTED");
      };
    } catch (e) {
      console.error("WebSocket connection failure:", e);
      setStatus("DISCONNECTED");
      if (streamingRef.current) handleSocketFailure();
    }
  }, [applyBinaryFrame, applyJsonFrame, cleanupSocket, startPolling, token, updateRate]);

  // Check for stale data (detect DEGRADED state if stream stalls)
  useEffect(() => {
    if (!isStreaming) return;
    const interval = setInterval(() => {
      if (lastFrameTimeRef.current > 0 && Date.now() - lastFrameTimeRef.current > 1500) {
        setStatus((prev) => (prev === "LIVE" ? "DEGRADED" : prev));
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [isStreaming]);

  const startStream = useCallback(() => {
    streamingRef.current = true;
    wsFailureCountRef.current = 0;
    setIsStreaming(true);
    trackerRef.current = new TelemetrySequenceTracker();
    connect();
  }, [connect]);

  const stopStream = useCallback(async () => {
    streamingRef.current = false;
    setIsStreaming(false);
    stopPolling();
    cleanupSocket();
    setMode("idle");
    setStatus("DISCONNECTED");
    if (isReplaying) {
      try {
        await apiFetch("/api/v1/telemetry/replay/stop", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ session_id: "sess-live" }),
        });
      } catch {}
      setIsReplaying(false);
    }
  }, [cleanupSocket, isReplaying, stopPolling, token]);

  const startReplayForDataset = useCallback(
    async (dataset: string, rateHz: number) => {
      startStream();
      setIsReplaying(true);
      setStreamSource(null);
      try {
        const res = await apiFetch("/api/v1/telemetry/replay/start", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            dataset,
            session_id: "sess-live",
            rate_hz: rateHz,
          }),
        });
        if (!res.ok) {
          console.warn("Failed to start server replay:", await res.text());
          return;
        }
        const body = await res.json();
        // Wave 15 item 1: the banner comes from the backend's own label.
        setStreamSource(body?.source ?? null);
        sampleReplayRef.current = body?.source === "SAMPLE_REPLAY";
      } catch (err) {
        console.error("Error triggering replay:", err);
      }
    },
    [startStream, token]
  );

  /** Explicit sample replay: the only unasked-for dataset, and it is labeled. */
  const startSampleReplay = useCallback(
    async (rateHz: number = 100.0) => {
      await startReplayForDataset(SAMPLE_REPLAY_DATASET, rateHz);
    },
    [startReplayForDataset]
  );

  /** Wave 15 item 2: any non-sample replay requires an explicit dataset id. */
  const triggerReplay = useCallback(
    async (dataset: string, rateHz: number = 100.0) => {
      if (!dataset || !dataset.trim()) {
        console.warn("Replay requires an explicit dataset id; not falling back to the sample.");
        return;
      }
      await startReplayForDataset(dataset.trim(), rateHz);
    },
    [startReplayForDataset]
  );

  useEffect(() => {
    return () => {
      streamingRef.current = false;
      stopPolling();
      cleanupSocket();
    };
  }, [cleanupSocket, stopPolling]);

  return {
    status,
    mode,
    isStreaming,
    isReplaying,
    streamSource,
    isSampleReplay: streamSource === "SAMPLE_REPLAY",
    pollingNotice: mode === "polling" ? POLLING_NOTICE : null,
    telemetry,
    twin,
    metrics,
    startStream,
    stopStream,
    startSampleReplay,
    triggerReplay,
  };
}
