"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import Plot from "../sim/Plot";
import {
  Activity,
  Layers,
  Flag,
  Crosshair,
  Sliders,
  AlertCircle,
  Eye,
  EyeOff,
  Zap,
  Clock,
  Compass,
  ChevronDown,
} from "lucide-react";
import { TelemetryApi, DecimatedTraceResponse, TelemetryEventOverlay } from "../../lib/api_client";
import SampleDemoTelemetryBadge from "../engineering/SampleDemoTelemetryBadge";

export type CornerPhase = "STRAIGHT" | "BRAKING" | "CORNER_ENTRY" | "APEX" | "CORNER_EXIT";

interface TelemetryChannelDef {
  id: string;
  name: string;
  unit: string;
  color: string;
  nominalMin: number;
  nominalMax: number;
}

const AVAILABLE_CHANNELS: TelemetryChannelDef[] = [
  { id: "speed_kmh", name: "Vehicle Speed", unit: "km/h", color: "#22d3ee", nominalMin: 0, nominalMax: 340 },
  { id: "lat_g", name: "Lateral Acceleration", unit: "g", color: "#c084fc", nominalMin: -4.5, nominalMax: 4.5 },
  { id: "long_g", name: "Longitudinal Acceleration", unit: "g", color: "#fbbf24", nominalMin: -5.0, nominalMax: 2.0 },
  { id: "damper_vel_fl", name: "Damper Vel FL", unit: "mm/s", color: "#34d399", nominalMin: -600, nominalMax: 600 },
  { id: "ride_height_f", name: "Ride Height Front", unit: "mm", color: "#f472b6", nominalMin: 15, nominalMax: 60 },
  { id: "steer_deg", name: "Steering Angle", unit: "deg", color: "#60a5fa", nominalMin: -90, nominalMax: 90 },
];

export default function TelemetrySyncView() {
  const [activeChannels, setActiveChannels] = useState<string[]>([
    "speed_kmh",
    "lat_g",
    "damper_vel_fl",
    "ride_height_f",
  ]);
  const [lodLevel, setLodLevel] = useState<"OVERVIEW" | "DETAILED" | "RAW">("OVERVIEW");
  const [hoverTime, setHoverTime] = useState<number | null>(4.5);
  const [rawDataset, setRawDataset] = useState<{ ts: number[]; channels: Record<string, number[]> } | null>(null);
  const [decimatedTraces, setDecimatedTraces] = useState<Record<string, DecimatedTraceResponse>>({});
  const [loading, setLoading] = useState(false);

  // Generate deterministic 100 Hz dataset for Spa lap segment (0 to 30 seconds)
  useEffect(() => {
    const totalSamples = 3000; // 30 seconds at 100 Hz
    const ts: number[] = new Array(totalSamples);
    const speed: number[] = new Array(totalSamples);
    const latG: number[] = new Array(totalSamples);
    const longG: number[] = new Array(totalSamples);
    const damperVel: number[] = new Array(totalSamples);
    const rideHeight: number[] = new Array(totalSamples);
    const steer: number[] = new Array(totalSamples);

    for (let i = 0; i < totalSamples; i++) {
      const t = i * 0.01;
      ts[i] = Number(t.toFixed(2));

      // Speed profile: braking from Kemmel into Les Combes
      if (t < 5.0) {
        speed[i] = 315 - t * 4;
        longG[i] = -0.2;
        latG[i] = 0.05 * Math.sin(t * 2);
        steer[i] = 0.5;
        damperVel[i] = 25 * Math.sin(t * 15);
        rideHeight[i] = 22 + Math.cos(t * 10);
      } else if (t < 10.0) {
        // Heavy braking zone
        const dtBrake = t - 5.0;
        speed[i] = Math.max(95, 295 - dtBrake * 42);
        longG[i] = -4.2 + dtBrake * 0.3;
        latG[i] = 0.2;
        steer[i] = -2.0;
        damperVel[i] = -120 + 30 * Math.sin(t * 25);
        rideHeight[i] = 18 + dtBrake * 2;
      } else if (t < 18.0) {
        // Les Combes right-left chicane
        const dtCorner = t - 10.0;
        speed[i] = 110 + dtCorner * 8;
        latG[i] = 3.8 * Math.sin(dtCorner * 0.8);
        longG[i] = 0.4 * Math.sin(dtCorner);
        steer[i] = 45 * Math.sin(dtCorner * 0.8);
        // Curb strike spike at t = 12.8s
        const spike = Math.abs(t - 12.8) < 0.15 ? 580 : 0;
        damperVel[i] = 40 * Math.cos(t * 12) + spike;
        rideHeight[i] = 26 + 8 * Math.sin(dtCorner * 0.8) - (spike > 0 ? 9 : 0);
      } else {
        // Acceleration out of Malmedy
        const dtExit = t - 18.0;
        speed[i] = Math.min(270, 174 + dtExit * 12);
        longG[i] = 1.2 - dtExit * 0.05;
        latG[i] = Math.max(0, 2.5 - dtExit * 0.4);
        steer[i] = Math.max(0, 25 - dtExit * 4);
        damperVel[i] = 15 * Math.sin(t * 8);
        rideHeight[i] = 32 - dtExit * 0.5;
      }
    }

    setRawDataset({
      ts,
      channels: {
        speed_kmh: speed,
        lat_g: latG,
        long_g: longG,
        damper_vel_fl: damperVel,
        ride_height_f: rideHeight,
        steer_deg: steer,
      },
    });
  }, []);

  // Compute decimation when LOD changes
  useEffect(() => {
    if (!rawDataset) return;
    const targetPoints = lodLevel === "OVERVIEW" ? 500 : lodLevel === "DETAILED" ? 1500 : 3000;

    async function runDecimations() {
      setLoading(true);
      const results: Record<string, DecimatedTraceResponse> = {};

      for (const ch of AVAILABLE_CHANNELS) {
        if (!rawDataset) continue;
        const vals = rawDataset.channels[ch.id];
        if (!vals) continue;

        try {
          const dec = await TelemetryApi.decimateTrace({
            timestamps: rawDataset.ts,
            values: vals,
            channel_name: ch.id,
            target_points: targetPoints,
            detect_events: true,
          });
          results[ch.id] = dec;
        } catch {
          // Fallback if network fails
          results[ch.id] = {
            channel_name: ch.id,
            original_points: rawDataset.ts.length,
            decimated_points: rawDataset.ts.length,
            lod_level: "RAW",
            timestamps: rawDataset.ts,
            values: vals,
            events: [],
          };
        }
      }

      setDecimatedTraces(results);
      setLoading(false);
    }

    runDecimations();
  }, [rawDataset, lodLevel]);

  // Determine current corner phase from hoverTime
  const currentCornerPhase: { phase: CornerPhase; label: string; color: string } = useMemo(() => {
    const t = hoverTime ?? 0;
    if (t < 5.0) return { phase: "STRAIGHT", label: "Kemmel Straight (Terminal Vmax)", color: "text-blue-400 bg-blue-950/40 border-blue-500/30" };
    if (t < 8.2) return { phase: "BRAKING", label: "Turn 5 Braking Zone (-4.2G)", color: "text-rose-400 bg-rose-950/40 border-rose-500/30" };
    if (t < 11.5) return { phase: "CORNER_ENTRY", label: "Turn 5 Entry (Trail Braking)", color: "text-amber-400 bg-amber-950/40 border-amber-500/30" };
    if (t < 14.8) return { phase: "APEX", label: "Turn 6 Apex (Inner Curb Strike)", color: "text-purple-400 bg-purple-950/40 border-purple-500/30" };
    return { phase: "CORNER_EXIT", label: "Turn 7 Exit (Full Throttle Acceleration)", color: "text-emerald-400 bg-emerald-950/40 border-emerald-500/30" };
  }, [hoverTime]);

  // Aggregate all detected events across all active channels
  const allEvents = useMemo(() => {
    const evts: TelemetryEventOverlay[] = [];
    Object.values(decimatedTraces).forEach((d) => {
      if (d.events) evts.push(...d.events);
    });
    return evts;
  }, [decimatedTraces]);

  const toggleChannel = (id: string) => {
    setActiveChannels((prev) =>
      prev.includes(id) ? (prev.length > 1 ? prev.filter((c) => c !== id) : prev) : [...prev, id]
    );
  };

  // Track position percentage (0 to 1) for track minimap
  const trackProgress = useMemo(() => {
    const t = hoverTime ?? 0;
    return Math.max(0, Math.min(1, t / 30));
  }, [hoverTime]);

  return (
    <div className="space-y-6 select-none font-sans text-white">
      {/* Telemetry Control & Inspection Bar */}
      <div className="p-4 rounded-2xl bg-[#111116] border border-white/[0.08] flex flex-wrap items-center justify-between gap-4">
        {/* Synchronized Hover Telemetry Values */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Crosshair size={16} className="text-ansys-yellow shrink-0" />
            <div>
              <div className="text-[10px] font-mono text-gray-400 uppercase">Synchronized Cursor</div>
              <div className="text-sm font-mono font-bold text-white">
                T = {hoverTime !== null ? hoverTime.toFixed(2) : "0.00"} s
              </div>
            </div>
          </div>

          <div className="h-8 w-px bg-white/10" />

          {/* Active Corner Phase */}
          <div>
            <div className="text-[10px] font-mono text-gray-400 uppercase">Corner Phase</div>
            <div className="flex flex-wrap items-center gap-2 mt-0.5">
              <span className={`px-2.5 py-0.5 rounded-full border text-xs font-mono font-bold inline-block ${currentCornerPhase.color}`}>
                {currentCornerPhase.label}
              </span>
              <SampleDemoTelemetryBadge size="xs" />
            </div>
          </div>
        </div>

        {/* Multi-Resolution LOD Selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-gray-400">Resolution LOD:</span>
          {(["OVERVIEW", "DETAILED", "RAW"] as const).map((level) => (
            <button
              key={level}
              onClick={() => setLodLevel(level)}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-bold border transition-all ${
                lodLevel === level
                  ? "bg-ansys-yellow text-black border-ansys-yellow"
                  : "bg-white/5 border-white/10 text-gray-400 hover:text-white"
              }`}
            >
              {level}
            </button>
          ))}
        </div>
      </div>

      {/* Main Analysis Layout: Track Minimap & Channel Selector on Left, Charts on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Track Minimap + Channel Toggles + Detected Events */}
        <div className="lg:col-span-4 space-y-4">
          {/* Track Map with Synchronized Vehicle Position */}
          <div className="p-4 rounded-2xl bg-[#111116] border border-white/[0.08] space-y-3">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="font-bold text-white flex items-center gap-1.5">
                <Flag size={14} className="text-cyan-400" /> Spa Sector 2 Map
              </span>
              <span className="text-gray-400">{Math.round(trackProgress * 100)}% of sector</span>
            </div>

            {/* SVG Track Outline */}
            <div className="relative w-full h-44 bg-black/40 rounded-xl border border-white/5 flex items-center justify-center overflow-hidden">
              <svg viewBox="0 0 300 140" className="w-full h-full p-3">
                {/* Track Circuit Path */}
                <path
                  d="M 20 20 L 140 20 Q 170 20 180 50 L 190 80 Q 200 110 230 110 L 280 110"
                  fill="none"
                  stroke="#334155"
                  strokeWidth="8"
                  strokeLinecap="round"
                />
                <path
                  d="M 20 20 L 140 20 Q 170 20 180 50 L 190 80 Q 200 110 230 110 L 280 110"
                  fill="none"
                  stroke="#f2a900"
                  strokeWidth="2"
                  strokeDasharray="4 4"
                />

                {/* Animated Vehicle Cursor along Path */}
                {(() => {
                  // Parametric position
                  let cx = 20 + trackProgress * 260;
                  let cy = 20;
                  if (trackProgress > 0.4 && trackProgress < 0.75) {
                    const norm = (trackProgress - 0.4) / 0.35;
                    cy = 20 + norm * 90;
                  } else if (trackProgress >= 0.75) {
                    cy = 110;
                  }
                  return (
                    <g transform={`translate(${cx}, ${cy})`}>
                      <circle r="8" fill="#22d3ee" fillOpacity="0.3" className="animate-ping" />
                      <circle r="5" fill="#f2a900" stroke="#ffffff" strokeWidth="1.5" />
                    </g>
                  );
                })()}
              </svg>

              <div className="absolute bottom-2 left-3 text-[10px] font-mono text-gray-500">
                Turn 5 / 6 (Les Combes)
              </div>
            </div>
          </div>

          {/* Channel Selector */}
          <div className="p-4 rounded-2xl bg-[#111116] border border-white/[0.08] space-y-3">
            <div className="text-xs font-mono font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
              <Sliders size={14} className="text-ansys-yellow" />
              Active Channels ({activeChannels.length}/{AVAILABLE_CHANNELS.length})
            </div>

            <div className="space-y-1.5">
              {AVAILABLE_CHANNELS.map((ch) => {
                const isSelected = activeChannels.includes(ch.id);
                const currentVal = rawDataset && hoverTime !== null
                  ? rawDataset.channels[ch.id]?.[Math.min(rawDataset.ts.length - 1, Math.round(hoverTime * 100))]
                  : null;

                return (
                  <button
                    key={ch.id}
                    onClick={() => toggleChannel(ch.id)}
                    className={`w-full flex items-center justify-between p-2.5 rounded-xl border text-xs font-mono transition-all ${
                      isSelected
                        ? "bg-white/[0.04] border-white/20 text-white"
                        : "bg-black/20 border-white/5 text-gray-500 hover:text-gray-300"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: ch.color }} />
                      <span>{ch.name}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      {currentVal !== null && currentVal !== undefined && (
                        <span className="text-white font-bold font-mono">
                          {currentVal.toFixed(1)} {ch.unit}
                        </span>
                      )}
                      {isSelected ? <Eye size={13} className="text-gray-400" /> : <EyeOff size={13} />}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Detected Event Overlays */}
          <div className="p-4 rounded-2xl bg-[#111116] border border-white/[0.08] space-y-3">
            <div className="text-xs font-mono font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
              <Zap size={14} className="text-amber-400" />
              Detected Anomaly Events ({allEvents.length})
            </div>

            <div className="space-y-2 max-h-48 overflow-y-auto custom-scrollbar">
              {allEvents.length === 0 ? (
                <div className="text-xs font-mono text-gray-500 py-3 text-center">
                  No abnormal spikes or lockups detected in current window.
                </div>
              ) : (
                allEvents.map((evt, i) => (
                  <div
                    key={i}
                    onClick={() => setHoverTime(evt.time_s)}
                    className="p-2.5 rounded-xl bg-amber-950/20 border border-amber-500/30 text-xs font-mono cursor-pointer hover:bg-amber-950/40 transition-colors"
                  >
                    <div className="flex items-center justify-between font-bold text-amber-300">
                      <span>{evt.type}</span>
                      <span>t = {evt.time_s.toFixed(2)}s</span>
                    </div>
                    <div className="text-[11px] text-gray-400 mt-0.5">{evt.desc}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Synchronized Stacked Time-Series Charts */}
        <div className="lg:col-span-8 space-y-4">
          {activeChannels.map((chId) => {
            const chDef = AVAILABLE_CHANNELS.find((c) => c.id === chId);
            const trace = decimatedTraces[chId];
            if (!chDef) return null;

            const xData = trace ? trace.timestamps : rawDataset?.ts || [];
            const yData = trace ? trace.values : rawDataset?.channels[chId] || [];

            return (
              <div
                key={chId}
                className="p-4 rounded-2xl bg-[#111116] border border-white/[0.08] relative overflow-hidden"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: chDef.color }} />
                    <span className="text-xs font-mono font-bold text-white">{chDef.name}</span>
                    <span className="text-[10px] font-mono text-gray-500">[{chDef.unit}]</span>
                  </div>

                  <div className="text-xs font-mono font-bold text-white">
                    {trace
                      ? `${trace.decimated_points} pts (${trace.lod_level})`
                      : "Loading..."}
                  </div>
                </div>

                <div className="w-full h-36">
                  <Plot
                    data={[
                      {
                        x: xData,
                        y: yData,
                        type: "scatter",
                        mode: "lines",
                        line: { color: chDef.color, width: 2 },
                        name: chDef.name,
                      },
                    ]}
                    layout={{
                      paper_bgcolor: "transparent",
                      plot_bgcolor: "transparent",
                      font: { color: "#666", size: 10, family: "Inter, monospace" },
                      xaxis: {
                        color: "#555",
                        gridcolor: "#18181b",
                        zerolinecolor: "#27272a",
                        title: { text: "Time [s]", font: { size: 10 } },
                      },
                      yaxis: {
                        color: "#555",
                        gridcolor: "#18181b",
                        zerolinecolor: "#27272a",
                      },
                      shapes: hoverTime !== null ? [
                        {
                          type: "line",
                          x0: hoverTime,
                          x1: hoverTime,
                          y0: 0,
                          y1: 1,
                          yref: "paper",
                          line: { color: "#f2a900", width: 1.5, dash: "dot" },
                        },
                      ] : [],
                      margin: { l: 45, r: 15, t: 10, b: 35 },
                      autosize: true,
                    }}
                    config={{ responsive: true, displayModeBar: false }}
                    className="w-full h-full"
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
