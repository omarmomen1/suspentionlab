"use client";
import React from "react";
import { mapBackendStatusToV2, V2_LABEL, type V2Status, V2_STATES } from "../../lib/v2/status";

// Flat fills and 1px hairlines only.
const STYLE: Record<V2Status, { fg: string; border: string; bg: string }> = {
  NOT_RUN: { fg: "text-gray-400", border: "border-gray-500/40", bg: "bg-gray-500/10" },
  RUNNING: { fg: "text-measured", border: "border-measured/50", bg: "bg-measured/10" },
  VERIFIED: { fg: "text-verified", border: "border-verified/50", bg: "bg-verified/10" },
  WARNING: { fg: "text-warning", border: "border-warning/50", bg: "bg-warning/10" },
  OUT_OF_DOMAIN: { fg: "text-warning", border: "border-warning/50 border-dashed", bg: "bg-transparent" },
  FAILED: { fg: "text-fault", border: "border-fault/50", bg: "bg-fault/10" },
};

export interface StatusPillProps {
  /** A V2 state, or any backend status string (mapped through mapBackendStatusToV2). */
  status: string | null | undefined;
  /** Overrides the visible text; the state colour and data attribute stay truthful. */
  label?: string;
  /** Raw backend value or extra detail, shown on hover. */
  detail?: string;
  className?: string;
}

export default function StatusPill({ status, label, detail, className = "" }: StatusPillProps) {
  const isV2 = typeof status === "string" && (V2_STATES as readonly string[]).includes(status);
  const state: V2Status = isV2 ? (status as V2Status) : mapBackendStatusToV2(status);
  const s = STYLE[state];
  const title = [detail, !isV2 && typeof status === "string" && status.trim() ? `Backend status: ${status}` : null].filter(Boolean).join("\n");
  return (
    <span
      data-testid="status-pill"
      data-status={state}
      title={title || undefined}
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${s.fg} ${s.border} ${s.bg} ${className}`}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {label ?? V2_LABEL[state]}
    </span>
  );
}
