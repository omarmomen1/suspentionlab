"use client";

import React, { useMemo, useState } from "react";
import { Activity, Layers, Maximize2 } from "lucide-react";

interface TelemetryChartProps {
  title?: string;
  channelName?: string;
  unit?: string;
  timestamps?: number[];
  measured?: number[];
  simulated?: number[];
  showResiduals?: boolean;
  className?: string;
}

export default function TelemetryChart({
  title = "Suspension Travel & Damper Dynamics",
  channelName = "Damper Disp RL",
  unit = "mm",
  timestamps,
  measured,
  simulated,
  showResiduals = true,
  className = "",
}: TelemetryChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  // Generate realistic deterministic physics traces if props are not supplied
  const data = useMemo(() => {
    if (timestamps && timestamps.length > 0 && (measured || simulated)) {
      return {
        t: timestamps,
        m: measured || [],
        s: simulated || [],
      };
    }

    // High-resolution trail-braking corner entry profile (100 points)
    const n = 100;
    const tArr: number[] = [];
    const mArr: number[] = [];
    const sArr: number[] = [];

    for (let i = 0; i < n; i++) {
      const t = i * 0.04; // 0 to 4.0s
      tArr.push(t);
      // Realistic damper displacement curve through corner entry (bump + weight transfer)
      const baseDisp = 18 + 12 * Math.sin(t * 2.2) * Math.exp(-t * 0.4);
      const bump = t > 1.2 && t < 1.6 ? 8.5 * Math.sin((t - 1.2) * Math.PI / 0.4) : 0;
      const simVal = baseDisp + bump;
      // Physical measurement has high-frequency tire hash + slight residual
      const noise = 0.8 * Math.sin(t * 18.0);
      const measuredVal = simVal + (t > 1.8 ? 3.4 : 0.4) + noise; // +3.4mm residual in Turn 9-11

      mArr.push(Number(measuredVal.toFixed(2)));
      sArr.push(Number(simVal.toFixed(2)));
    }

    return { t: tArr, m: mArr, s: sArr };
  }, [timestamps, measured, simulated]);

  // Compute bounding box
  const minVal = Math.min(...data.m, ...data.s, 0);
  const maxVal = Math.max(...data.m, ...data.s, 35);
  const valRange = maxVal - minVal || 1;

  const svgWidth = 700;
  const svgHeight = 220;
  const padLeft = 45;
  const padRight = 20;
  const padTop = 20;
  const padBottom = 35;
  const plotWidth = svgWidth - padLeft - padRight;
  const plotHeight = svgHeight - padTop - padBottom;

  const toX = (index: number) => padLeft + (index / (data.t.length - 1)) * plotWidth;
  const toY = (val: number) => padTop + plotHeight - ((val - minVal) / valRange) * plotHeight;

  // Build SVG path strings
  const measuredPath = data.m
    .map((v, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(v).toFixed(1)}`)
    .join(" ");

  const simulatedPath = data.s
    .map((v, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(v).toFixed(1)}`)
    .join(" ");

  // Residual polygon
  const residualArea = `${measuredPath} L ${toX(data.s.length - 1)} ${toY(
    data.s[data.s.length - 1]
  )} ` + data.s
    .map((v, i) => `L ${toX(data.s.length - 1 - i).toFixed(1)} ${toY(data.s[data.s.length - 1 - i]).toFixed(1)}`)
    .join(" ") + " Z";

  return (
    <div className={`p-5 rounded-3xl bg-[#0e0e13] border border-white/[0.08] shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <div className="text-[10px] font-mono text-ansys-yellow uppercase tracking-wider font-bold flex items-center gap-1.5">
            <Activity size={12} /> High-Resolution Trace Overlay
          </div>
          <h4 className="text-sm font-bold text-white tracking-tight">{title}</h4>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-[11px] font-mono">
          <div className="flex items-center gap-1.5 text-cyan-400">
            <span className="w-2.5 h-1 bg-cyan-400 rounded-full" />
            <span>MEASURED (MoTeC)</span>
          </div>
          <div className="flex items-center gap-1.5 text-ansys-yellow">
            <span className="w-2.5 h-1 bg-ansys-yellow rounded-full" />
            <span>SIMULATED (RK45)</span>
          </div>
          {showResiduals && (
            <div className="flex items-center gap-1.5 text-amber-400">
              <span className="w-2 h-2 bg-amber-500/20 border border-amber-500/40 rounded-sm" />
              <span>RESIDUAL DIVERGENCE</span>
            </div>
          )}
        </div>
      </div>

      {/* SVG Canvas */}
      <div className="relative w-full overflow-hidden select-none">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-auto"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const relX = ((e.clientX - rect.left) / rect.width) * svgWidth;
            const idx = Math.round(((relX - padLeft) / plotWidth) * (data.t.length - 1));
            if (idx >= 0 && idx < data.t.length) setHoverIndex(idx);
          }}
          onMouseLeave={() => setHoverIndex(null)}
        >
          {/* Sector Overlay Bands */}
          <rect
            x={padLeft}
            y={padTop}
            width={plotWidth * 0.3}
            height={plotHeight}
            fill="#3b82f6"
            fillOpacity="0.04"
          />
          <text x={padLeft + 10} y={padTop + 14} fill="#60a5fa" fontSize="9" fontFamily="monospace">
            STRAIGHT BRAKING
          </text>

          <rect
            x={padLeft + plotWidth * 0.3}
            y={padTop}
            width={plotWidth * 0.4}
            height={plotHeight}
            fill="#f59e0b"
            fillOpacity="0.05"
          />
          <text
            x={padLeft + plotWidth * 0.3 + 10}
            y={padTop + 14}
            fill="#fbbf24"
            fontSize="9"
            fontFamily="monospace"
          >
            TRAIL-BRAKE ENTRY (T9-11)
          </text>

          <rect
            x={padLeft + plotWidth * 0.7}
            y={padTop}
            width={plotWidth * 0.3}
            height={plotHeight}
            fill="#10b981"
            fillOpacity="0.04"
          />
          <text
            x={padLeft + plotWidth * 0.7 + 10}
            y={padTop + 14}
            fill="#34d399"
            fontSize="9"
            fontFamily="monospace"
          >
            MID-CORNER APEX
          </text>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
            const y = padTop + plotHeight * pct;
            const val = maxVal - pct * valRange;
            return (
              <g key={i}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={padLeft + plotWidth}
                  y2={y}
                  stroke="#ffffff"
                  strokeOpacity="0.06"
                  strokeDasharray="3 3"
                />
                <text
                  x={padLeft - 8}
                  y={y + 3}
                  fill="#71717a"
                  fontSize="9"
                  fontFamily="monospace"
                  textAnchor="end"
                >
                  {val.toFixed(0)}
                </text>
              </g>
            );
          })}

          {/* Residual Shaded Area */}
          {showResiduals && (
            <path d={residualArea} fill="#f59e0b" fillOpacity="0.12" stroke="none" />
          )}

          {/* Simulated Trace */}
          <path
            d={simulatedPath}
            fill="none"
            stroke="#f2a900"
            strokeWidth="2"
            strokeLinecap="round"
          />

          {/* Measured Trace */}
          <path
            d={measuredPath}
            fill="none"
            stroke="#22d3ee"
            strokeWidth="1.8"
            strokeLinecap="round"
          />

          {/* Interactive Crosshair Cursor */}
          {hoverIndex !== null && (
            <g>
              <line
                x1={toX(hoverIndex)}
                y1={padTop}
                x2={toX(hoverIndex)}
                y2={padTop + plotHeight}
                stroke="#ffffff"
                strokeWidth="1"
                strokeDasharray="2 2"
              />
              <circle
                cx={toX(hoverIndex)}
                cy={toY(data.m[hoverIndex])}
                r="3.5"
                fill="#22d3ee"
              />
              <circle
                cx={toX(hoverIndex)}
                cy={toY(data.s[hoverIndex])}
                r="3.5"
                fill="#f2a900"
              />
            </g>
          )}
        </svg>

        {/* Hover Inspector Readout */}
        {hoverIndex !== null && (
          <div className="absolute top-2 right-2 p-2 rounded-xl bg-black/90 border border-white/20 font-mono text-[11px] shadow-xl space-y-0.5 pointer-events-none">
            <div className="text-gray-400">Time: {data.t[hoverIndex].toFixed(2)} s</div>
            <div className="text-cyan-400 font-bold">
              Measured: {data.m[hoverIndex]} {unit}
            </div>
            <div className="text-ansys-yellow font-bold">
              Simulated: {data.s[hoverIndex]} {unit}
            </div>
            <div className="text-amber-400 font-bold">
              Residual: {(data.m[hoverIndex] - data.s[hoverIndex]).toFixed(2)} {unit}
            </div>
          </div>
        )}
      </div>

      {/* Footer / Operating Band Callout */}
      <div className="mt-3 pt-2.5 border-t border-white/[0.06] flex items-center justify-between text-[10px] font-mono text-gray-500">
        <span>Channel: {channelName} ({unit})</span>
        <span>Sampling Rate: 100 Hz (Fixed-Step Synchronous)</span>
        <span className="text-amber-400">Peak Residual: +3.4 mm @ T = 2.16s</span>
      </div>
    </div>
  );
}
