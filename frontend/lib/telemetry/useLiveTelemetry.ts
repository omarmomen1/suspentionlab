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

export function useLiveTelemetry(token: string | null) {
  const [status, setStatus] = useState<StreamStatus>("DISCONNECTED");
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [isReplaying, setIsReplaying] = useState<boolean>(false);

  const [telemetry, setTelemetry] = useState<LiveTelemetryData>({
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
  });

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
  const backoffRef = useRef<number>(1000);
  const frameCountWindowRef = useRef<number>(0);
  const lastRateCalcTimeRef = useRef<number>(Date.now());
  const lastFrameTimeRef = useRef<number>(0);

  const cleanupSocket = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    cleanupSocket();

    const wsProtocol = API_BASE.startsWith("https") ? "wss:" : "ws:";
    const host = API_BASE.replace(/^https?:\/\//, "");
    const authToken = token || "demo";
    const wsUrl = `${wsProtocol}//${host}/api/v1/telemetry/live?token=${encodeURIComponent(authToken)}&session_id=sess-live&format=binary`;

    try {
      const ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        backoffRef.current = 1000;
        setStatus("LIVE");

        // Send periodic heartbeat ping
        heartbeatIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 15000);
      };

      ws.onmessage = (event) => {
        const now = Date.now();
        lastFrameTimeRef.current = now;
        frameCountWindowRef.current += 1;

        // Rate calculation (every 500ms)
        const dtRate = now - lastRateCalcTimeRef.current;
        if (dtRate >= 500) {
          const currentHz = Number(((frameCountWindowRef.current / dtRate) * 1000).toFixed(1));
          frameCountWindowRef.current = 0;
          lastRateCalcTimeRef.current = now;

          const loss = trackerRef.current.getLossRatePct();
          // Update streaming health status
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
        }

        if (event.data instanceof ArrayBuffer) {
          try {
            const frame = parseSLTPBinaryFrame(event.data);
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
              trackerRef.current.processSequence(json.seq || 0);
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
            }
          } catch {}
        }
      };

      ws.onclose = () => {
        setStatus("DISCONNECTED");
        if (isStreaming) {
          // Engage exponential backoff reconnection with jitter
          const jitter = Math.random() * 500;
          const delay = Math.min(15000, backoffRef.current + jitter);
          backoffRef.current = Math.min(15000, backoffRef.current * 1.5);
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        }
      };

      ws.onerror = (err) => {
        console.warn("WebSocket error:", err);
        setStatus("DISCONNECTED");
      };
    } catch (e) {
      console.error("WebSocket connection failure:", e);
      setStatus("DISCONNECTED");
    }
  }, [cleanupSocket, token, isStreaming]);

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
    setIsStreaming(true);
    trackerRef.current = new TelemetrySequenceTracker();
    connect();
  }, [connect]);

  const stopStream = useCallback(async () => {
    setIsStreaming(false);
    cleanupSocket();
    setStatus("DISCONNECTED");
    if (isReplaying) {
      try {
        await apiFetch("/api/v1/telemetry/replay/stop", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: token ? `Bearer ${token}` : "",
          },
          body: JSON.stringify({ session_id: "sess-live" }),
        });
      } catch {}
      setIsReplaying(false);
    }
  }, [cleanupSocket, isReplaying, token]);

  const triggerReplay = useCallback(async (rateHz: number = 100.0) => {
    try {
      startStream();
      setIsReplaying(true);
      const res = await apiFetch("/api/v1/telemetry/replay/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({
          dataset: "sample_data/motec_spa_session.csv",
          session_id: "sess-live",
          rate_hz: rateHz,
        }),
      });
      if (!res.ok) {
        console.warn("Failed to start server replay:", await res.text());
      }
    } catch (err) {
      console.error("Error triggering replay:", err);
    }
  }, [startStream, token]);

  useEffect(() => {
    return () => cleanupSocket();
  }, [cleanupSocket]);

  return {
    status,
    isStreaming,
    isReplaying,
    telemetry,
    twin,
    metrics,
    startStream,
    stopStream,
    triggerReplay,
  };
}
