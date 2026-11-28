"use client";

import React from "react";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import EvidenceBadge, { EngineeringStateType } from "./EvidenceBadge";
import WhyButton from "./WhyButton";
import { ProvenanceData } from "./ProvenancePopover";

interface EngineeringMetricProps {
  label: string;
  value: string | number | null | undefined;
  unit?: string;
  state?: EngineeringStateType | string;
  emptyReason?: string | null;
  delta?: {
    value: number;
    unit?: string;
    beneficial?: boolean; // if true, green; if false, red/amber
    label?: string; // e.g. "vs FP2 Baseline"
  };
  provenance?: ProvenanceData | null;
  subtext?: string;
  className?: string;
  loading?: boolean;
}

export default function EngineeringMetric({
  label,
  value,
  unit,
  state,
  emptyReason,
  delta,
  provenance,
  subtext,
  className = "",
  loading = false,
}: EngineeringMetricProps) {
  if (loading) {
    return (
      <div className={`p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] animate-pulse ${className}`}>
        <div className="h-3 bg-white/10 rounded w-1/2 mb-2" />
        <div className="h-6 bg-white/10 rounded w-3/4 mb-2" />
        <div className="h-2.5 bg-white/5 rounded w-1/3" />
      </div>
    );
  }

  const isUnavailable = value === null || value === undefined || (typeof value === "string" && value.trim() === "");

  return (
    <div
      className={`p-4 rounded-2xl bg-[#111116] border border-white/[0.08] relative flex flex-col justify-between transition-all hover:border-white/15 ${className}`}
    >
      {/* Top Header: Label, State Badge, Why Button */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider truncate font-sans">
          {label}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {state && <EvidenceBadge state={state} size="xs" />}
          <WhyButton
            title={label}
            provenance={provenance || null}
          />
        </div>
      </div>

      {/* Main Metric Value */}
      <div className="my-1">
        {isUnavailable ? (
          <div className="text-xs font-mono text-zinc-400 font-semibold tracking-wide py-1">
            {emptyReason || "DATA UNAVAILABLE"}
          </div>
        ) : (
          <div className="text-2xl font-black text-white font-mono tracking-tight flex items-baseline gap-1">
            <span>{value}</span>
            {unit && <span className="text-xs text-gray-400 font-normal">{unit}</span>}
          </div>
        )}
      </div>

      {/* Bottom Row: Delta & Subtext */}
      <div className="flex items-center justify-between gap-2 text-xs font-mono mt-1">
        {delta ? (
          <div
            className={`flex items-center gap-1 font-bold ${
              delta.beneficial === undefined
                ? delta.value > 0
                  ? "text-emerald-400"
                  : "text-rose-400"
                : delta.beneficial
                ? "text-emerald-400"
                : "text-rose-400"
            }`}
          >
            {delta.value > 0 ? (
              <TrendingUp size={13} />
            ) : delta.value < 0 ? (
              <TrendingDown size={13} />
            ) : (
              <Minus size={13} />
            )}
            <span>
              {delta.value > 0 ? `+${delta.value}` : delta.value}
              {delta.unit || "%"}
            </span>
            {delta.label && <span className="text-xs text-zinc-400 font-normal font-sans">({delta.label})</span>}
          </div>
        ) : (
          <div className="text-xs text-zinc-400 truncate font-sans">{subtext || ""}</div>
        )}
      </div>
    </div>
  );
}
