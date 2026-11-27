"use client";
import React from "react";
import EmptyState from "../EmptyState";
import type { CornerDelta } from "../../../lib/v2/instruments";

export interface DifferenceRibbonProps {
  /** Time gained or lost per corner zone, seconds: negative = Setup B faster. */
  deltas: CornerDelta[];
  className?: string;
}

/**
 * Corner-by-corner difference ribbon. Bars left of the centre line are time gained by
 * Setup B, right are time lost, on a common scale. Shows nothing but an empty state when
 * no corner zones are available, rather than inventing them.
 */
export default function DifferenceRibbon({ deltas, className = "" }: DifferenceRibbonProps) {
  const rows = deltas.filter((d) => Number.isFinite(d.delta_s));
  if (rows.length === 0) {
    return (
      <div data-testid="difference-ribbon" className={className}>
        <EmptyState reason="No corner list for this track" />
      </div>
    );
  }
  const max = Math.max(1e-6, ...rows.map((d) => Math.abs(d.delta_s)));
  const total = rows.reduce((s, d) => s + d.delta_s, 0);
  return (
    <div data-testid="difference-ribbon" className={`rounded border border-hairline bg-panel p-3 ${className}`}>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Difference ribbon (B vs A, per corner zone)</p>
        <p className="v2-num text-xs text-white" data-testid="ribbon-total">{`${total > 0 ? "+" : ""}${total.toFixed(3)} s`}</p>
      </div>
      <ul className="space-y-1">
        {rows.map((d) => {
          const w = (Math.abs(d.delta_s) / max) * 50;
          const faster = d.delta_s < 0;
          return (
            <li key={d.corner} data-corner={d.corner} className="grid grid-cols-[7rem_1fr_4.5rem] items-center gap-2 text-[11px]">
              <span className="truncate text-gray-300">{d.corner}</span>
              <span className="relative h-3 border-x border-hairline">
                <span className="absolute inset-y-0 left-1/2 w-px bg-gray-600" />
                <span
                  className={`absolute inset-y-0.5 ${faster ? "bg-verified" : "bg-fault"}`}
                  style={faster ? { right: "50%", width: `${w}%` } : { left: "50%", width: `${w}%` }}
                />
              </span>
              <span className={`v2-num text-right ${faster ? "text-verified" : "text-fault"}`}>{`${d.delta_s > 0 ? "+" : ""}${d.delta_s.toFixed(3)} s`}</span>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-[10px] text-gray-500">
        Zones run from the midpoint to the previous corner apex to the midpoint to the next. Deltas come from the two speed traces
        (integral of ds/v), so they approximate, and need not match, the solver lap-time difference.
      </p>
    </div>
  );
}
