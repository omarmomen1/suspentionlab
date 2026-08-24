"use client";

/**
 * components/sim/KPICard.tsx — shared KPI tile (P1-ARCH-02).
 * Canonical version extracted from the sim pages; supports both the
 * status-coloured variant and a direct accent `color` (kinematics style).
 */

import React from "react";

export type Status = "good" | "warn" | "bad" | "neutral";

interface KPICardProps {
  label: string;
  value: number | string;
  unit?: string;
  sub?: string;
  status?: Status;
  /** Optional explicit accent colour (overrides status colouring). */
  color?: string;
}

const COLOURS: Record<Status, string> = {
  good: "text-emerald-400",
  warn: "text-amber-400",
  bad: "text-red-400",
  neutral: "text-white",
};

const BORDERS: Record<Status, string> = {
  good: "border-emerald-900/40 bg-emerald-950/10",
  warn: "border-amber-900/40 bg-amber-950/10",
  bad: "border-red-900/40 bg-red-950/10",
  neutral: "border-[#252525]",
};

export default function KPICard({
  label, value, unit, sub, status = "neutral", color,
}: KPICardProps) {
  const valueClass = color ? "" : COLOURS[status];
  const borderClass = color ? "border-[#252525]" : BORDERS[status];
  return (
    <div className={`bg-[#141416] border ${borderClass} rounded-xl p-3 flex flex-col gap-0.5`}>
      <span className="text-[9px] font-bold tracking-[0.16em] text-gray-600 uppercase">{label}</span>
      <span
        className={`text-[1.1rem] font-bold font-mono leading-tight ${valueClass}`}
        style={color ? { color } : undefined}
      >
        {value}
        {unit && <span className="text-[0.65rem] text-gray-500 ml-1 font-sans">{unit}</span>}
      </span>
      {sub && <span className="text-[10px] text-gray-500">{sub}</span>}
    </div>
  );
}
