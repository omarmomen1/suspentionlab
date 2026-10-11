"use client";

import React, { useMemo, useState } from "react";
import { Layers, MapPin, Gauge, Eye } from "lucide-react";

interface CornerInfo {
  corner_id: number;
  name: string;
  entry_distance_m?: number;
  apex_distance_m: number;
  exit_distance_m?: number;
  min_speed_mps: number;
  peak_lateral_g?: number;
}

interface TrackMapProps {
  x: number[];
  y: number[];
  distances: number[];
  speedsKmh: number[];
  lateralG?: number[];
  longitudinalG?: number[];
  tireUtilization?: number[];
  corners?: CornerInfo[];
  hoverDist?: number | null;
  onHoverDist?: (dist: number | null) => void;
  onSelectCorner?: (corner: CornerInfo) => void;
}

type ColorMode = "speed" | "lateral_g" | "longitudinal_g" | "utilization";

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

export default function TrackMap({
  x,
  y,
  distances,
  speedsKmh,
  lateralG,
  longitudinalG,
  tireUtilization,
  corners = [],
  hoverDist,
  onHoverDist,
  onSelectCorner,
}: TrackMapProps) {
  const [colorMode, setColorMode] = useState<ColorMode>("speed");

  // Transform coordinates to 800x600 SVG canvas preserving aspect ratio
  const { segments, cornerMarkers, hoverPos, bounds } = useMemo(() => {
    if (!x || !y || x.length < 2 || y.length < 2) {
      return { segments: [], cornerMarkers: [], hoverPos: null, bounds: null };
    }

    const minX = Math.min(...x);
    const maxX = Math.max(...x);
    const minY = Math.min(...y);
    const maxY = Math.max(...y);

    const spanX = Math.max(maxX - minX, 1);
    const spanY = Math.max(maxY - minY, 1);

    const width = 800;
    const height = 550;
    const padding = 50;

    const scale = Math.min((width - 2 * padding) / spanX, (height - 2 * padding) / spanY);
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    const toSvgX = (valX: number) => (valX - centerX) * scale + width / 2;
    // Invert Y so North is up
    const toSvgY = (valY: number) => height / 2 - (valY - centerY) * scale;

    // Determine values for coloring
    let vals = speedsKmh;
    let palette = SPEED_PALETTE;
    if (colorMode === "lateral_g" && lateralG) {
      vals = lateralG.map(Math.abs);
      palette = LAT_PALETTE;
    } else if (colorMode === "utilization" && tireUtilization) {
      vals = tireUtilization.map(u => u * 100);
      palette = UTIL_PALETTE;
    }

    const minVal = Math.min(...vals);
    const maxVal = Math.max(...vals);

    // Build segments
    const segs: Array<{ x1: number; y1: number; x2: number; y2: number; color: string; dist: number }> = [];
    for (let i = 0; i < x.length - 1; i++) {
      const col = interpolateColor(vals[i], minVal, maxVal, palette);
      segs.push({
        x1: toSvgX(x[i]),
        y1: toSvgY(y[i]),
        x2: toSvgX(x[i + 1]),
        y2: toSvgY(y[i + 1]),
        color: col,
        dist: distances[i],
      });
    }

    // Locate corner apex points on the SVG canvas
    const markers = corners.map(c => {
      // Find closest station index
      let bestIdx = 0;
      let minDiff = Infinity;
      for (let i = 0; i < distances.length; i++) {
        const diff = Math.abs(distances[i] - c.apex_distance_m);
        if (diff < minDiff) {
          minDiff = diff;
          bestIdx = i;
        }
      }
      return {
        ...c,
        svgX: toSvgX(x[bestIdx]),
        svgY: toSvgY(y[bestIdx]),
      };
    });

    // Locate hover point
    let hPos: { svgX: number; svgY: number; speed: number; dist: number } | null = null;
    if (hoverDist !== null && hoverDist !== undefined) {
      let bestIdx = 0;
      let minDiff = Infinity;
      for (let i = 0; i < distances.length; i++) {
        const diff = Math.abs(distances[i] - hoverDist);
        if (diff < minDiff) {
          minDiff = diff;
          bestIdx = i;
        }
      }
      hPos = {
        svgX: toSvgX(x[bestIdx]),
        svgY: toSvgY(y[bestIdx]),
        speed: speedsKmh[bestIdx],
        dist: distances[bestIdx],
      };
    }

    return { segments: segs, cornerMarkers: markers, hoverPos: hPos, bounds: { minVal, maxVal } };
  }, [x, y, distances, speedsKmh, lateralG, tireUtilization, colorMode, corners, hoverDist]);

  if (!segments.length) {
    return (
      <div className="w-full h-[450px] flex items-center justify-center bg-[#0d0d0f] border border-[#1f1f23] rounded-xl text-gray-500 text-xs">
        No circuit coordinate telemetry available for 2D track rendering.
      </div>
    );
  }

  return (
    <div className="relative w-full h-[550px] bg-[#0a0a0c] border border-[#1f1f23] rounded-xl p-4 flex flex-col">
      {/* Top Controls & Legend Bar */}
      <div className="flex items-center justify-between pb-3 border-b border-[#1f1f23]">
        <div className="flex items-center gap-2">
          <MapPin size={16} className="text-[#f2a900]" />
          <span className="text-xs font-bold text-white tracking-wide">Interactive Circuit Map</span>
          <span className="text-[10px] text-gray-500 bg-[#16161a] px-2 py-0.5 rounded border border-[#27272a]">
            {distances[distances.length - 1]?.toFixed(0)} m centerline
          </span>
        </div>

        {/* Colormap mode toggles */}
        <div className="flex items-center gap-1 bg-[#141417] p-1 rounded-lg border border-[#27272a]">
          <button
            onClick={() => setColorMode("speed")}
            className={`px-2 py-1 text-[10px] font-semibold rounded ${
              colorMode === "speed" ? "bg-[#f2a900] text-black" : "text-gray-400 hover:text-white"
            }`}
          >
            Speed (km/h)
          </button>
          <button
            onClick={() => setColorMode("lateral_g")}
            className={`px-2 py-1 text-[10px] font-semibold rounded ${
              colorMode === "lateral_g" ? "bg-[#f2a900] text-black" : "text-gray-400 hover:text-white"
            }`}
          >
            Lateral G
          </button>
          <button
            onClick={() => setColorMode("utilization")}
            className={`px-2 py-1 text-[10px] font-semibold rounded ${
              colorMode === "utilization" ? "bg-[#f2a900] text-black" : "text-gray-400 hover:text-white"
            }`}
          >
            Tire Utilization %
          </button>
        </div>
      </div>

      {/* SVG Canvas */}
      <div className="relative flex-1 w-full overflow-hidden flex items-center justify-center">
        <svg
          viewBox="0 0 800 550"
          className="w-full h-full"
          style={{ filter: "drop-shadow(0 0 12px rgba(0,0,0,0.8))" }}
        >
          {/* Circuit background glow / track casing */}
          {segments.map((seg, idx) => (
            <line
              key={`bg-${idx}`}
              x1={seg.x1}
              y1={seg.y1}
              x2={seg.x2}
              y2={seg.y2}
              stroke="#18181b"
              strokeWidth={14}
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
              strokeWidth={6}
              strokeLinecap="round"
              className="cursor-pointer transition-colors duration-150"
              onMouseEnter={() => onHoverDist?.(seg.dist)}
            />
          ))}

          {/* Corner Apex Badges */}
          {cornerMarkers.map(c => (
            <g
              key={c.corner_id}
              className="cursor-pointer group"
              onClick={() => onSelectCorner?.(c)}
              transform={`translate(${c.svgX}, ${c.svgY})`}
            >
              <circle
                r={10}
                fill="#09090b"
                stroke="#f2a900"
                strokeWidth={2}
                className="group-hover:fill-[#f2a900] transition-colors"
              />
              <text
                textAnchor="middle"
                dy={3.5}
                fontSize={8}
                fontWeight="bold"
                fill="#ffffff"
                className="group-hover:fill-black pointer-events-none"
              >
                T{c.corner_id}
              </text>
            </g>
          ))}

          {/* Hover scrubber indicator */}
          {hoverPos && (
            <g transform={`translate(${hoverPos.svgX}, ${hoverPos.svgY})`}>
              <circle r={7} fill="#ffffff" stroke="#f2a900" strokeWidth={3} />
              <circle r={14} fill="none" stroke="#ffffff" strokeWidth={1} strokeDasharray="3,3" opacity={0.6} />
            </g>
          )}
        </svg>

        {/* Hover telemetry tooltip */}
        {hoverPos && (
          <div className="absolute top-4 right-4 bg-[#121215]/90 border border-[#f2a900]/40 backdrop-blur-md rounded-lg px-3 py-2 text-xs shadow-xl pointer-events-none">
            <div className="text-[10px] text-gray-400 font-mono">STATION: {hoverPos.dist.toFixed(1)} m</div>
            <div className="text-sm font-bold text-white font-mono">{hoverPos.speed.toFixed(1)} km/h</div>
          </div>
        )}
      </div>

      {/* Metric Range Legend */}
      {bounds && (
        <div className="flex items-center justify-between pt-2 border-t border-[#1f1f23] text-[10px] text-gray-500 font-mono">
          <span>Min: {bounds.minVal.toFixed(1)}</span>
          <div className="flex items-center gap-1.5">
            <div
              className="w-36 h-2 rounded"
              style={{
                background:
                  colorMode === "speed"
                    ? "linear-gradient(to right, #3b82f6, #06b6d4, #10b981, #eab308, #ef4444)"
                    : colorMode === "lateral_g"
                    ? "linear-gradient(to right, #10b981, #eab308, #f97316, #ef4444, #a855f7)"
                    : "linear-gradient(to right, #22c55e, #84cc16, #eab308, #f97316, #ef4444)",
              }}
            />
          </div>
          <span>Max: {bounds.maxVal.toFixed(1)}</span>
        </div>
      )}
    </div>
  );
}
