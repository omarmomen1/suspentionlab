"use client";

import React, { useMemo, useState } from "react";
import { MapPin, Activity, ChevronDown, ChevronUp, Flag, Sparkles } from "lucide-react";
import Plot from "./Plot";
import { darkLayout } from "./theme";

export interface CornerInfo {
  corner_id: number;
  name?: string;
  entry_distance_m?: number;
  apex_distance_m: number;
  exit_distance_m?: number;
  min_speed_mps?: number;
  min_speed_kmh?: number;
  peak_lateral_g?: number;
  limiting_factor?: string;
  time_loss_s?: number;
}

export interface GgvEnvelopeData {
  speeds_kmh?: number[];
  speeds_ms?: number[];
  ay_max_g?: number[];
  ay_max_ms2?: number[];
  ax_accel_g?: number[];
  ax_accel_ms2?: number[];
  ax_brake_g?: number[];
  ax_brake_ms2?: number[];
}

export interface TrackMapProps {
  // New preferred props
  x_m?: number[];
  y_m?: number[];
  speed_kmh?: number[];
  limiting_factor?: string[];
  // Backwards-compatible aliases
  x?: number[];
  y?: number[];
  distances?: number[];
  s_m?: number[];
  speedsKmh?: number[];
  lateralG?: number[];
  longitudinalG?: number[];
  tireUtilization?: number[];
  limitingFactors?: string[];
  corners?: CornerInfo[];
  hoverDist?: number | null;
  onHoverDist?: (dist: number | null) => void;
  onSelectCorner?: (corner: CornerInfo) => void;
  sectorBoundaries?: [number, number];
  ggv?: GgvEnvelopeData;
  showGgPlot?: boolean;
  circuitName?: string;
  driverSpeedsKmh?: number[];
}

export type ColorMode = "bottleneck" | "speed" | "lateral_g" | "utilization" | "driver_delta";

export const BOTTLENECK_COLORS = {
  POWER: {
    color: "#06B6D4", // Telemetry Cyan
    label: "Power Limited",
    desc: "Full Throttle / Drag Limited",
    bg: "rgba(6, 182, 212, 0.12)",
    border: "rgba(6, 182, 212, 0.35)",
  },
  BRAKING: {
    color: "#F43F5E", // Racing Coral
    label: "Braking Limited",
    desc: "Threshold Braking Zone",
    bg: "rgba(244, 63, 94, 0.12)",
    border: "rgba(244, 63, 94, 0.35)",
  },
  UNDERSTEER_FRONT: {
    color: "#F59E0B", // Precision Amber
    label: "Understeer",
    desc: "Front Axle Grip Saturated",
    bg: "rgba(245, 158, 11, 0.12)",
    border: "rgba(245, 158, 11, 0.35)",
  },
  OVERSTEER_REAR: {
    color: "#10B981", // Emerald
    label: "Oversteer",
    desc: "Rear Axle Traction Saturated",
    bg: "rgba(16, 185, 129, 0.12)",
    border: "rgba(16, 185, 129, 0.35)",
  },
};

export function getBottleneckColor(factor?: string): string {
  if (!factor) return BOTTLENECK_COLORS.POWER.color;
  const upper = factor.toUpperCase();
  if (upper.includes("POWER") || upper.includes("ACCEL") || upper.includes("ENGINE") || upper.includes("TRACTION")) {
    return BOTTLENECK_COLORS.POWER.color;
  }
  if (upper.includes("BRAKE") || upper.includes("BRAKING") || upper.includes("DECEL")) {
    return BOTTLENECK_COLORS.BRAKING.color;
  }
  if (upper.includes("UNDERSTEER") || upper.includes("FRONT")) {
    return BOTTLENECK_COLORS.UNDERSTEER_FRONT.color;
  }
  if (upper.includes("OVERSTEER") || upper.includes("REAR")) {
    return BOTTLENECK_COLORS.OVERSTEER_REAR.color;
  }
  return "#A855F7";
}

function interpolateColor(val: number, min: number, max: number, palette: string[]): string {
  const norm = Math.max(0, Math.min(1, (val - min) / Math.max(max - min, 1e-6)));
  const idx = norm * (palette.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.min(palette.length - 1, lo + 1);
  const frac = idx - lo;

  const hexToRgb = (hex: string) => {
    const bigint = parseInt(hex.replace("#", ""), 16);
    return [(bigint >> 16) & 255, (bigint >> 8) & 255, bigint & 255];
  };

  const rgbLo = hexToRgb(palette[lo]);
  const rgbHi = hexToRgb(palette[hi]);

  const r = Math.round(rgbLo[0] + frac * (rgbHi[0] - rgbLo[0]));
  const g = Math.round(rgbLo[1] + frac * (rgbHi[1] - rgbLo[1]));
  const b = Math.round(rgbLo[2] + frac * (rgbHi[2] - rgbLo[2]));

  return `rgb(${r}, ${g}, ${b})`;
}

const SPEED_PALETTE = ["#3b82f6", "#06b6d4", "#10b981", "#eab308", "#ef4444"];
const LAT_PALETTE = ["#10b981", "#eab308", "#f97316", "#ef4444", "#a855f7"];
const UTIL_PALETTE = ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444"];
const DELTA_PALETTE = ["#ef4444", "#f97316", "#eab308", "#10b981", "#06b6d4"];

export default function TrackMap({
  x_m,
  y_m,
  speed_kmh,
  limiting_factor,
  x,
  y,
  distances,
  s_m,
  speedsKmh,
  lateralG,
  longitudinalG,
  tireUtilization,
  limitingFactors,
  corners = [],
  hoverDist,
  onHoverDist,
  onSelectCorner,
  sectorBoundaries,
  ggv,
  showGgPlot = false,
  circuitName,
  driverSpeedsKmh,
}: TrackMapProps) {
  // Normalize fallback props safely
  const rawX = x_m ?? x ?? [];
  const rawY = y_m ?? y ?? [];
  const rawSpeeds = speed_kmh ?? speedsKmh ?? [];
  const rawFactors = limiting_factor ?? limitingFactors ?? [];
  const rawDistances = s_m ?? distances ?? [];

  const hasBottlenecks = rawFactors.length > 0;
  const [colorMode, setColorMode] = useState<ColorMode>(hasBottlenecks ? "bottleneck" : "speed");
  const [showGgSection, setShowGgSection] = useState<boolean>(showGgPlot);
  const [rightPanelMode, setRightPanelMode] = useState<"ggv" | "gg">("ggv");

  const ggvSpeedValues = useMemo(() => {
    const rawSpeeds = ggv?.speeds_kmh ?? ggv?.speeds_ms ?? [];
    if (rawSpeeds.length > 0) {
      const maxRaw = Math.max(...rawSpeeds, 0);
      return rawSpeeds.map((v: number) => (maxRaw > 0 && maxRaw <= 110 ? Number((v * 3.6).toFixed(1)) : Number(v.toFixed(1))));
    }
    return [36, 72, 108, 144, 180, 216, 252, 288, 300];
  }, [ggv]);

  const ggvAyMaxValues = useMemo(() => {
    if (ggv?.ay_max_g && ggv.ay_max_g.length > 0) return ggv.ay_max_g;
    if ((ggv as any)?.max_lat_g && (ggv as any).max_lat_g.length > 0) return (ggv as any).max_lat_g;
    if (ggv?.ay_max_ms2 && ggv.ay_max_ms2.length > 0) return ggv.ay_max_ms2.map((a) => a / 9.81);
    return [1.38, 1.48, 1.62, 1.82, 2.05, 2.25, 2.38, 2.45, 2.50];
  }, [ggv]);

  const ggvAxAccelValues = useMemo(() => {
    if (ggv?.ax_accel_g && ggv.ax_accel_g.length > 0) return ggv.ax_accel_g;
    if ((ggv as any)?.max_accel_g && (ggv as any).max_accel_g.length > 0) return (ggv as any).max_accel_g;
    if (ggv?.ax_accel_ms2 && ggv.ax_accel_ms2.length > 0) return ggv.ax_accel_ms2.map((a) => a / 9.81);
    return [0.75, 0.62, 0.48, 0.35, 0.26, 0.19, 0.13, 0.08, 0.04];
  }, [ggv]);

  const ggvAxBrakeValues = useMemo(() => {
    if (ggv?.ax_brake_g && ggv.ax_brake_g.length > 0) return ggv.ax_brake_g.map((v: number) => -Math.abs(v));
    if ((ggv as any)?.max_brake_g && (ggv as any).max_brake_g.length > 0) return (ggv as any).max_brake_g.map((b: number) => -Math.abs(b));
    if (ggv?.ax_brake_ms2 && ggv.ax_brake_ms2.length > 0) return ggv.ax_brake_ms2.map((a) => -Math.abs(a / 9.81));
    return [-1.45, -1.55, -1.72, -1.94, -2.18, -2.35, -2.42, -2.45, -2.45];
  }, [ggv]);

  // Compute regime percentages: Power %, Braking %, Understeer %, Oversteer %
  const bottleneckStats = useMemo(() => {
    if (!rawFactors || rawFactors.length === 0) return null;
    const counts = {
      POWER: 0,
      BRAKING: 0,
      UNDERSTEER_FRONT: 0,
      OVERSTEER_REAR: 0,
    };
    let total = 0;
    rawFactors.forEach((f) => {
      const upper = (f || "").toUpperCase();
      if (upper.includes("POWER") || upper.includes("ACCEL") || upper.includes("ENGINE") || upper.includes("TRACTION")) {
        counts.POWER++;
      } else if (upper.includes("BRAKE") || upper.includes("BRAKING") || upper.includes("DECEL")) {
        counts.BRAKING++;
      } else if (upper.includes("UNDERSTEER") || upper.includes("FRONT")) {
        counts.UNDERSTEER_FRONT++;
      } else if (upper.includes("OVERSTEER") || upper.includes("REAR")) {
        counts.OVERSTEER_REAR++;
      } else {
        counts.POWER++;
      }
      total++;
    });
    if (total === 0) return null;
    return {
      powerPct: (counts.POWER / total) * 100,
      brakingPct: (counts.BRAKING / total) * 100,
      understeerPct: (counts.UNDERSTEER_FRONT / total) * 100,
      oversteerPct: (counts.OVERSTEER_REAR / total) * 100,
      total,
    };
  }, [rawFactors]);

  // Transform coordinates to 800x520 SVG canvas preserving aspect ratio
  const { segments, cornerMarkers, hoverPos, bounds, startFinishPos, sectorSplitMarkers } = useMemo(() => {
    if (!Array.isArray(rawX) || !Array.isArray(rawY) || rawX.length < 2 || rawY.length < 2) {
      return {
        segments: [],
        cornerMarkers: [],
        hoverPos: null,
        bounds: null,
        startFinishPos: null,
        sectorSplitMarkers: [],
      };
    }

    const minX = Math.min(...rawX);
    const maxX = Math.max(...rawX);
    const minY = Math.min(...rawY);
    const maxY = Math.max(...rawY);

    const spanX = Math.max(maxX - minX, 1);
    const spanY = Math.max(maxY - minY, 1);

    const svgWidth = 800;
    const svgHeight = 500;
    const padX = svgWidth * 0.14;
    const padY = svgHeight * 0.14;

    const scale = Math.min((svgWidth - 2 * padX) / spanX, (svgHeight - 2 * padY) / spanY);

    const toSvgX = (x: number) => padX + (svgWidth - 2 * padX - spanX * scale) / 2 + (x - minX) * scale;
    // Invert Y so North is up, auto-fitted with padding
    const toSvgY = (y: number) => padY + (svgHeight - 2 * padY - spanY * scale) / 2 + (maxY - y) * scale;

    let vals = rawSpeeds;
    let palette = SPEED_PALETTE;
    if (colorMode === "lateral_g" && lateralG) {
      vals = lateralG.map(Math.abs);
      palette = LAT_PALETTE;
    } else if (colorMode === "utilization" && tireUtilization) {
      vals = tireUtilization.map((u) => u * 100);
      palette = UTIL_PALETTE;
    } else if (colorMode === "driver_delta" && driverSpeedsKmh) {
      vals = rawSpeeds.map((opt, i) => (driverSpeedsKmh[i] !== undefined ? opt - driverSpeedsKmh[i] : 0));
      palette = DELTA_PALETTE;
    }

    const minVal = vals.length > 0 ? Math.min(...vals) : 0;
    const maxVal = vals.length > 0 ? Math.max(...vals) : 100;

    const segs: Array<{
      x1: number;
      y1: number;
      x2: number;
      y2: number;
      color: string;
      dist: number;
      factor?: string;
      speed: number;
    }> = [];

    const nPoints = Math.min(rawX.length, rawY.length);
    for (let i = 0; i < nPoints - 1; i++) {
      let col = "#06B6D4";
      const factor = rawFactors?.[i];

      if (colorMode === "bottleneck" && factor) {
        col = getBottleneckColor(factor);
      } else {
        col = interpolateColor(vals[i] ?? 0, minVal, maxVal, palette);
      }

      segs.push({
        x1: toSvgX(rawX[i]),
        y1: toSvgY(rawY[i]),
        x2: toSvgX(rawX[i + 1]),
        y2: toSvgY(rawY[i + 1]),
        color: col,
        dist: rawDistances[i] ?? 0,
        factor,
        speed: rawSpeeds[i] ?? 0,
      });
    }

    // Corner apex markers
    const markers = (corners || []).map((c) => {
      let bestIdx = 0;
      let minDiff = Infinity;
      for (let i = 0; i < rawDistances.length; i++) {
        const diff = Math.abs(rawDistances[i] - c.apex_distance_m);
        if (diff < minDiff) {
          minDiff = diff;
          bestIdx = i;
        }
      }
      return {
        ...c,
        svgX: toSvgX(rawX[bestIdx]),
        svgY: toSvgY(rawY[bestIdx]),
      };
    });

    // Start/Finish Line marker
    const startFinishPos = rawX.length > 0 ? { svgX: toSvgX(rawX[0]), svgY: toSvgY(rawY[0]) } : null;

    // Sector 1 / Sector 2 / Sector 3 Split markers
    const splits: Array<{ label: string; svgX: number; svgY: number; distM: number }> = [];
    const totalDist = rawDistances[rawDistances.length - 1] ?? 5000;
    const s1End = sectorBoundaries?.[0] ?? totalDist * 0.33;
    const s2End = sectorBoundaries?.[1] ?? totalDist * 0.66;

    const findNearestSvgCoord = (targetDist: number) => {
      let bestIdx = 0;
      let minDiff = Infinity;
      for (let i = 0; i < rawDistances.length; i++) {
        const diff = Math.abs(rawDistances[i] - targetDist);
        if (diff < minDiff) {
          minDiff = diff;
          bestIdx = i;
        }
      }
      return {
        svgX: toSvgX(rawX[bestIdx]),
        svgY: toSvgY(rawY[bestIdx]),
      };
    };

    if (rawDistances.length > 10) {
      const posS1 = findNearestSvgCoord(s1End);
      splits.push({ label: "S1 Split", svgX: posS1.svgX, svgY: posS1.svgY, distM: s1End });
      const posS2 = findNearestSvgCoord(s2End);
      splits.push({ label: "S2 Split", svgX: posS2.svgX, svgY: posS2.svgY, distM: s2End });
    }

    // Hover scrubber position
    let hPos: {
      svgX: number;
      svgY: number;
      speed: number;
      dist: number;
      latG?: number;
      longG?: number;
      factor?: string;
    } | null = null;

    if (hoverDist !== null && hoverDist !== undefined && rawDistances.length > 0) {
      let bestIdx = 0;
      let minDiff = Infinity;
      for (let i = 0; i < rawDistances.length; i++) {
        const diff = Math.abs(rawDistances[i] - hoverDist);
        if (diff < minDiff) {
          minDiff = diff;
          bestIdx = i;
        }
      }
      if (bestIdx < rawX.length) {
        hPos = {
          svgX: toSvgX(rawX[bestIdx]),
          svgY: toSvgY(rawY[bestIdx]),
          speed: rawSpeeds[bestIdx] ?? 0,
          dist: rawDistances[bestIdx] ?? 0,
          latG: lateralG?.[bestIdx],
          longG: longitudinalG?.[bestIdx],
          factor: rawFactors?.[bestIdx],
        };
      }
    }

    return {
      segments: segs,
      cornerMarkers: markers,
      hoverPos: hPos,
      bounds: { minVal, maxVal },
      startFinishPos,
      sectorSplitMarkers: splits,
    };
  }, [
    rawX,
    rawY,
    rawDistances,
    rawSpeeds,
    lateralG,
    longitudinalG,
    tireUtilization,
    rawFactors,
    colorMode,
    corners,
    hoverDist,
    sectorBoundaries,
    driverSpeedsKmh,
  ]);

  if (!segments.length) {
    return (
      <div className="w-full h-[460px] flex flex-col items-center justify-center bg-[#0D1017] border border-[#1f2430] rounded-xl text-zinc-400 text-xs p-6 text-center">
        <MapPin size={28} className="text-zinc-300 mb-2 opacity-50" />
        <span className="font-medium text-zinc-400">No Track Coordinates Loaded</span>
        <span className="text-xs text-zinc-300 mt-1">
          Select a championship circuit or run a simulation to render the 2D bottleneck track map.
        </span>
      </div>
    );
  }

  const trackLengthM = rawDistances[rawDistances.length - 1] ?? 0;

  return (
    <div className="relative w-full bg-[#0D1017] border border-[#1f2430] rounded-xl p-3.5 flex flex-col space-y-3 shadow-2xl">
      {/* Top Header & Colormap Mode Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-[#1f2430]">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-[#06B6D4]/15 border border-[#06B6D4]/40 flex items-center justify-center shadow-sm">
            <MapPin size={13} className="text-[#06B6D4]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-white tracking-wide">
                {circuitName ? `${circuitName} Circuit Map` : "Interactive 2D Circuit Map"}
              </span>
              <span className="text-xs font-mono text-cyan-400 bg-cyan-950/40 px-2 py-0.5 rounded border border-cyan-800/40">
                {trackLengthM.toFixed(0)} m
              </span>
            </div>
            <p className="text-xs text-zinc-400 font-sans">
              Color-coded active bottleneck regimes &middot; S/F &amp; Sector 1/2/3 splits
            </p>
          </div>
        </div>

        {/* View toggles */}
        <div className="flex items-center gap-1 bg-[#151922] p-1 rounded-lg border border-[#252c3b]">
          <button
            onClick={() => setColorMode("bottleneck")}
            className={`px-2.5 py-1 text-xs font-bold rounded transition-all cursor-pointer ${
              colorMode === "bottleneck"
                ? "bg-[#06B6D4] text-black shadow-md"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            Bottlenecks
          </button>
          <button
            onClick={() => setColorMode("speed")}
            className={`px-2 py-1 text-xs font-semibold rounded transition-all cursor-pointer ${
              colorMode === "speed" ? "bg-signal text-carbon" : "text-zinc-400 hover:text-white"
            }`}
          >
            Speed
          </button>
          <button
            onClick={() => setColorMode("lateral_g")}
            className={`px-2 py-1 text-xs font-semibold rounded transition-all cursor-pointer ${
              colorMode === "lateral_g" ? "bg-signal text-carbon" : "text-zinc-400 hover:text-white"
            }`}
          >
            Lateral G
          </button>
          {driverSpeedsKmh && (
            <button
              onClick={() => setColorMode("driver_delta")}
              className={`px-2 py-1 text-xs font-semibold rounded transition-all cursor-pointer ${
                colorMode === "driver_delta" ? "bg-rose-500 text-white" : "text-zinc-400 hover:text-white"
              }`}
            >
              Driver Δv
            </button>
          )}
          <button
            type="button"
            onClick={() => setRightPanelMode((m) => (m === "ggv" ? "gg" : "ggv"))}
            className="px-2 py-1 text-xs font-semibold rounded transition-all flex items-center gap-1 cursor-pointer border bg-[#1f2635] text-amber-400 border-amber-500/40 hover:text-white"
            title="Toggle between GGV Performance Envelope and G-G Friction Circle"
          >
            <Activity size={10} />
            <span>{rightPanelMode === "ggv" ? "G-G Circle" : "GGV Envelope"}</span>
          </button>
        </div>
      </div>

      {/* Crisp Bottleneck Legend Bar showing % of lap spent in each regime */}
      {bottleneckStats && colorMode === "bottleneck" && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-[#121620] p-2 rounded-lg border border-[#1f2533]">
          {/* Power % */}
          <div className="flex items-center gap-2 px-2.5 py-1.5 rounded bg-[#06B6D4]/10 border border-[#06B6D4]/30">
            <div className="w-2.5 h-2.5 rounded-full bg-[#06B6D4] shadow-sm shadow-[#06B6D4]/50" />
            <div className="min-w-0">
              <div className="text-xs text-zinc-400 font-mono uppercase">Power %</div>
              <div className="text-xs font-black text-[#06B6D4] font-mono leading-none mt-0.5">
                {bottleneckStats.powerPct.toFixed(1)}%
              </div>
            </div>
          </div>

          {/* Braking % */}
          <div className="flex items-center gap-2 px-2.5 py-1.5 rounded bg-[#F43F5E]/10 border border-[#F43F5E]/30">
            <div className="w-2.5 h-2.5 rounded-full bg-[#F43F5E] shadow-sm shadow-[#F43F5E]/50" />
            <div className="min-w-0">
              <div className="text-xs text-zinc-400 font-mono uppercase">Braking %</div>
              <div className="text-xs font-black text-[#F43F5E] font-mono leading-none mt-0.5">
                {bottleneckStats.brakingPct.toFixed(1)}%
              </div>
            </div>
          </div>

          {/* Understeer % */}
          <div className="flex items-center gap-2 px-2.5 py-1.5 rounded bg-[#F59E0B]/10 border border-[#F59E0B]/30">
            <div className="w-2.5 h-2.5 rounded-full bg-[#F59E0B] shadow-sm shadow-[#F59E0B]/50" />
            <div className="min-w-0">
              <div className="text-xs text-zinc-400 font-mono uppercase">Understeer %</div>
              <div className="text-xs font-black text-[#F59E0B] font-mono leading-none mt-0.5">
                {bottleneckStats.understeerPct.toFixed(1)}%
              </div>
            </div>
          </div>

          {/* Oversteer % */}
          <div className="flex items-center gap-2 px-2.5 py-1.5 rounded bg-[#10B981]/10 border border-[#10B981]/30">
            <div className="w-2.5 h-2.5 rounded-full bg-[#10B981] shadow-sm shadow-[#10B981]/50" />
            <div className="min-w-0">
              <div className="text-xs text-zinc-400 font-mono uppercase">Oversteer %</div>
              <div className="text-xs font-black text-[#10B981] font-mono leading-none mt-0.5">
                {bottleneckStats.oversteerPct.toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Side-by-Side: 2D Bottleneck TrackMap (Left) & GGV / G-G Performance Envelope (Right) */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 items-stretch">
        {/* Left: SVG Canvas on Carbon Background */}
        <div className="relative w-full h-[410px] bg-[#0D1017] border border-[#1b202c] rounded-xl overflow-hidden flex items-center justify-center p-2">
        <svg
          viewBox="0 0 800 500"
          className="w-full h-full select-none"
          style={{ filter: "drop-shadow(0 0 20px rgba(0,0,0,0.95))" }}
        >
          {/* Circuit background casing / track boundaries */}
          {segments.map((seg, idx) => (
            <line
              key={`bg-${idx}`}
              x1={seg.x1}
              y1={seg.y1}
              x2={seg.x2}
              y2={seg.y2}
              stroke="#151922"
              strokeWidth={16}
              strokeLinecap="round"
            />
          ))}

          {/* Asphalt track bed */}
          {segments.map((seg, idx) => (
            <line
              key={`road-${idx}`}
              x1={seg.x1}
              y1={seg.y1}
              x2={seg.x2}
              y2={seg.y2}
              stroke="#212836"
              strokeWidth={10}
              strokeLinecap="round"
            />
          ))}

          {/* Active colored centerline */}
          {segments.map((seg, idx) => (
            <line
              key={`fg-${idx}`}
              x1={seg.x1}
              y1={seg.y1}
              x2={seg.x2}
              y2={seg.y2}
              stroke={seg.color}
              strokeWidth={5}
              strokeLinecap="round"
              className="cursor-pointer transition-opacity hover:opacity-100"
              onMouseEnter={() => onHoverDist?.(seg.dist)}
            />
          ))}

          {/* Start/Finish Line Gantry (S/F) */}
          {startFinishPos && (
            <g transform={`translate(${startFinishPos.svgX}, ${startFinishPos.svgY})`}>
              <line x1={-10} y1={-10} x2={10} y2={10} stroke="#ffffff" strokeWidth={3} strokeDasharray="3,3" />
              <rect x={-14} y={-24} width={28} height={15} rx={3} fill="#090c10" stroke="#C8F04B" strokeWidth={1.5} />
              <text
                textAnchor="middle"
                dy={-13}
                fontSize={8}
                fontWeight="900"
                fill="#C8F04B"
                className="font-mono pointer-events-none tracking-widest"
              >
                S/F
              </text>
            </g>
          )}

          {/* Sector 1 & Sector 2 Split Markers */}
          {sectorSplitMarkers.map((sp) => (
            <g key={sp.label} transform={`translate(${sp.svgX}, ${sp.svgY})`}>
              <circle r={6} fill="#0D1017" stroke="#38BDF8" strokeWidth={2} />
              <rect x={-18} y={-22} width={36} height={14} rx={3} fill="#0D1017" stroke="#38BDF8" strokeWidth={1} />
              <text
                textAnchor="middle"
                dy={-12}
                fontSize={7.5}
                fontWeight="bold"
                fill="#38BDF8"
                className="font-mono pointer-events-none"
              >
                {sp.label.split(" ")[0]}
              </text>
            </g>
          ))}

          {/* Corner Apex Badges */}
          {cornerMarkers.map((c) => (
            <g
              key={c.corner_id}
              className="cursor-pointer group"
              onClick={() => onSelectCorner?.(c)}
              transform={`translate(${c.svgX}, ${c.svgY})`}
            >
              <circle
                r={10}
                fill="#0D1017"
                stroke="#C8F04B"
                strokeWidth={2}
                className="group-hover:fill-[#C8F04B] group-hover:stroke-white transition-all shadow-md"
              />
              <text
                textAnchor="middle"
                dy={3.5}
                fontSize={8}
                fontWeight="bold"
                fill="#ffffff"
                className="group-hover:fill-black pointer-events-none font-mono"
              >
                T{c.corner_id}
              </text>
            </g>
          ))}

          {/* Hover scrubber indicator & ghost beacon */}
          {hoverPos && (
            <g transform={`translate(${hoverPos.svgX}, ${hoverPos.svgY})`}>
              <circle r={16} fill="none" stroke="#ffffff" strokeWidth={1.2} strokeDasharray="3,3" opacity={0.6} />
              <circle r={9} fill={getBottleneckColor(hoverPos.factor)} opacity={0.35} className="animate-ping" />
              <circle r={5} fill="#ffffff" stroke={getBottleneckColor(hoverPos.factor)} strokeWidth={2.5} />
            </g>
          )}
        </svg>

        {/* Hover telemetry tooltip */}
        {hoverPos && (
          <div className="absolute top-3 right-3 bg-[#0D1017]/95 border border-[#252c3b] backdrop-blur-md rounded-xl p-3 text-xs shadow-2xl pointer-events-none min-w-[200px]">
            <div className="flex items-center justify-between border-b border-[#1f2533] pb-1.5 mb-1.5">
              <span className="text-xs text-zinc-400 font-mono">TRACK STATION</span>
              <span className="text-xs font-bold text-amber-400 font-mono">
                {hoverPos.dist.toFixed(0)} m
              </span>
            </div>

            <div className="space-y-1 font-mono text-xs">
              <div className="flex justify-between">
                <span className="text-zinc-400">Speed:</span>
                <span className="text-white font-bold">{hoverPos.speed.toFixed(1)} km/h</span>
              </div>
              {hoverPos.latG !== undefined && (
                <div className="flex justify-between">
                  <span className="text-zinc-400">Lateral G:</span>
                  <span className="text-zinc-300">{hoverPos.latG.toFixed(2)} g</span>
                </div>
              )}
              {hoverPos.longG !== undefined && (
                <div className="flex justify-between">
                  <span className="text-zinc-400">Longitudinal G:</span>
                  <span className="text-zinc-300">{hoverPos.longG.toFixed(2)} g</span>
                </div>
              )}
              {hoverPos.factor && (
                <div className="pt-1.5 border-t border-[#1f2533] flex items-center justify-between">
                  <span className="text-xs text-zinc-400 uppercase">Limit:</span>
                  <span
                    className="text-xs font-bold px-1.5 py-0.5 rounded font-mono"
                    style={{
                      color: getBottleneckColor(hoverPos.factor),
                      backgroundColor: `${getBottleneckColor(hoverPos.factor)}20`,
                    }}
                  >
                    {hoverPos.factor}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
        </div>

        {/* Right: GGV Performance Envelope & G-G Friction Circle */}
        <div className="flex flex-col min-h-[420px] bg-[#0D1017] border border-[#1b202c] rounded-xl p-2.5">
          <div className="flex items-center justify-between pb-1.5 border-b border-[#1f2533] mb-1.5 flex-shrink-0">
            <div className="flex items-center gap-1.5">
              <Activity size={12} className="text-amber-400" />
              <span className="text-xs font-bold text-white tracking-wide">
                {rightPanelMode === "ggv" ? "GGV Performance Envelope vs Speed" : "G-G Friction Circle & Bottlenecks"}
              </span>
            </div>
            <div className="flex items-center gap-1 bg-[#151922] p-0.5 rounded-lg border border-[#252c3b]">
              <button
                type="button"
                onClick={() => setRightPanelMode("ggv")}
                className={`px-2 py-0.5 text-xs font-bold rounded transition-all cursor-pointer ${
                  rightPanelMode === "ggv" ? "bg-signal text-carbon shadow" : "text-zinc-400 hover:text-white"
                }`}
              >
                GGV Envelope
              </button>
              <button
                type="button"
                onClick={() => setRightPanelMode("gg")}
                className={`px-2 py-0.5 text-xs font-bold rounded transition-all cursor-pointer ${
                  rightPanelMode === "gg" ? "bg-[#06B6D4] text-black shadow" : "text-zinc-400 hover:text-white"
                }`}
              >
                G-G Circle
              </button>
            </div>
          </div>

          <div className="flex-1 w-full" style={{ width: "100%", height: "340px", minHeight: "340px" }}>
            {rightPanelMode === "ggv" ? (
              <Plot
                data={[
                  {
                    x: ggvSpeedValues,
                    y: ggvAyMaxValues,
                    type: "scatter",
                    mode: "lines",
                    name: "ay Cornering Limit",
                    line: { color: "#F59E0B", width: 2 },
                  },
                  {
                    x: ggvSpeedValues,
                    y: ggvAxAccelValues,
                    type: "scatter",
                    mode: "lines",
                    name: "ax Accel (Powertrain)",
                    line: { color: "#06B6D4", width: 1.8, dash: "dot" },
                  },
                  {
                    x: ggvSpeedValues,
                    y: ggvAxBrakeValues,
                    type: "scatter",
                    mode: "lines",
                    name: "ax Braking Limit",
                    line: { color: "#F43F5E", width: 1.8, dash: "dot" },
                  },
                ]}
                layout={darkLayout({
                  xaxis: { title: { text: "Speed [km/h]", font: { color: "#71717a" } }, range: [0, 310] },
                  yaxis: { title: { text: "Acceleration Limits [g]", font: { color: "#71717a" } }, range: [-2.6, 2.6], zeroline: true },
                  margin: { t: 36, r: 16, b: 42, l: 50 },
                  legend: { orientation: "h", y: 1.12, x: 0, font: { color: "#a1a1aa", size: 9 } },
                })}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: "100%", height: "340px" }}
                useResizeHandler
              />
            ) : (
              <Plot
                data={[
                  {
                    x: lateralG ?? [],
                    y: longitudinalG ?? [],
                    type: "scatter",
                    mode: "markers",
                    name: "Vehicle Trajectory",
                    marker: {
                      color: rawFactors.length > 0 ? rawFactors.map(getBottleneckColor) : rawSpeeds,
                      colorscale: rawFactors.length > 0 ? undefined : "Plasma",
                      size: 3,
                      opacity: 0.75,
                    },
                  },
                  ...[70, 160, 250].map((vk, idx) => {
                    const baseMu = 1.38;
                    const gTotal = baseMu + (vk / 160) ** 2 * 0.45;
                    const angles = Array.from({ length: 80 }, (_, i) => (i / 79) * 2 * Math.PI);
                    return {
                      x: angles.map((a) => gTotal * Math.cos(a)),
                      y: angles.map((a) => (idx === 0 ? 1.15 : gTotal * 0.95) * Math.sin(a)),
                      type: "scatter" as const,
                      mode: "lines" as const,
                      name: `Limit @ ${vk} km/h (±${gTotal.toFixed(2)}g)`,
                      line: {
                        color: idx === 0 ? "#06B6D4" : idx === 1 ? "#F59E0B" : "#F43F5E",
                        dash: "dash" as const,
                        width: 1.2,
                      },
                    };
                  }),
                ]}
                layout={darkLayout({
                  title: { text: "G-G Friction Circle & Bottleneck Points", font: { color: "#a1a1aa", size: 11 } },
                  xaxis: {
                    title: { text: "Lateral Accel [g]", font: { color: "#71717a" } },
                    zeroline: true,
                    range: [-2.5, 2.5],
                  },
                  yaxis: {
                    title: { text: "Longitudinal Accel [g]", font: { color: "#71717a" } },
                    zeroline: true,
                    range: [-2.5, 2.0],
                  },
                  margin: { l: 45, r: 15, t: 25, b: 40 },
                  legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 8 } },
                })}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: "100%", height: "100%" }}
                useResizeHandler
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
