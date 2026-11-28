"use client";

import React from "react";

interface ConfidenceIndicatorProps {
  confidence: number | null | undefined; // 0.0 to 1.0 or null
  sourceTag?: string; // e.g. "R² Correlation", "Monte Carlo 1000x", "Dyno Identification"
  showBar?: boolean;
  size?: "sm" | "md";
  className?: string;
}

export default function ConfidenceIndicator({
  confidence,
  sourceTag,
  showBar = true,
  size = "md",
  className = "",
}: ConfidenceIndicatorProps) {
  if (confidence === null || confidence === undefined || isNaN(confidence)) {
    return (
      <div className={`inline-flex items-center gap-1.5 font-mono text-zinc-400 text-xs ${className}`}>
        <span className="w-2 h-2 rounded-full bg-zinc-600" />
        <span className="font-semibold text-xs uppercase tracking-wider text-zinc-400">DATA UNAVAILABLE</span>
      </div>
    );
  }

  // Normalize between 0 and 1
  const normVal = confidence > 1 ? confidence / 100 : Math.max(0, Math.min(1, confidence));
  const pct = Math.round(normVal * 100);

  let band = "LOW";
  let color = "text-rose-400";
  let barColor = "bg-rose-500";
  let borderColor = "border-rose-500/30";
  let bgColor = "bg-rose-950/20";

  if (normVal >= 0.8) {
    band = "HIGH";
    color = "text-emerald-400";
    barColor = "bg-emerald-400";
    borderColor = "border-emerald-500/30";
    bgColor = "bg-emerald-950/20";
  } else if (normVal >= 0.55) {
    band = "MEDIUM";
    color = "text-amber-400";
    barColor = "bg-amber-400";
    borderColor = "border-amber-500/30";
    bgColor = "bg-amber-950/20";
  }

  return (
    <div
      className={`inline-flex flex-col gap-1 p-2 rounded-xl border ${bgColor} ${borderColor} font-mono ${className}`}
      title={`Engineering Confidence: ${pct}% (${band}) ${sourceTag ? `via ${sourceTag}` : ""}`}
    >
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="text-xs text-gray-400 font-sans font-semibold uppercase tracking-wider">
          Confidence
        </span>
        <div className="flex items-center gap-1.5 font-bold">
          <span className={color}>{normVal.toFixed(2)}</span>
          <span className={`text-xs px-1 py-0.2 rounded font-semibold ${color} bg-white/5`}>
            {band}
          </span>
        </div>
      </div>

      {showBar && (
        <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}

      {sourceTag && (
        <div className="text-xs text-gray-400 truncate max-w-[160px]">
          Source: {sourceTag}
        </div>
      )}
    </div>
  );
}
