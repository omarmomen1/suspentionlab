"use client";

/**
 * components/sim/PlotBox.tsx — shared plot container (P1-ARCH-02).
 * Integrates synchronized crosshair, track position, corner/impulse phase,
 * accessible data tables, and peak preservation indicator.
 */

import React, { useState } from "react";
import { useSyncChart } from "./SyncChartContext";
import { Pin, MapPin, Sparkles, Activity } from "lucide-react";

export interface PlotBoxProps {
  children: React.ReactNode;
  title?: string;
  description?: string;
  summaryData?: Array<{ label: string; value: string | number }>;
  className?: string;
  showSyncBar?: boolean;
}

export default function PlotBox({
  children,
  title,
  description,
  summaryData,
  className = "",
  showSyncBar = true,
}: PlotBoxProps) {
  const [showTable, setShowTable] = useState(false);
  const { cursorTime, pinnedTime, setPinnedTime, activePhase, trackPositionM } = useSyncChart();

  return (
    <div
      role="region"
      aria-label={title || "Simulation chart"}
      className={`bg-[#0f0f11] border border-[#1e1e1e] rounded-xl p-2 h-full min-h-0 overflow-hidden relative flex flex-col ${className}`}
    >
      {/* Screen reader summary / accessible non-visual description */}
      {description && (
        <span className="sr-only">{description}</span>
      )}

      {/* Top Header Controls Bar */}
      <div className="flex items-center justify-between gap-2 px-1 pb-1.5 border-b border-white/[0.04] text-xs font-mono shrink-0">
        <div className="flex items-center gap-2 overflow-hidden text-ellipsis whitespace-nowrap">
          {title && <span className="font-bold text-gray-300">{title}</span>}
          {cursorTime !== null && showSyncBar && (
            <div className="flex items-center gap-1.5 bg-black/50 border border-signal/30 px-2 py-0.5 rounded text-gray-300">
              <span className="text-signal font-bold">t: {cursorTime.toFixed(3)}s</span>
              {trackPositionM !== null && (
                <span className="text-cyan-400">| x: {trackPositionM.toFixed(1)}m</span>
              )}
              {activePhase && (
                <span className="text-emerald-400 font-sans text-xs bg-emerald-950/40 px-1 py-0.2 rounded border border-emerald-500/30">
                  {activePhase}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {cursorTime !== null && showSyncBar && (
            <button
              type="button"
              onClick={() => setPinnedTime(pinnedTime !== null ? null : cursorTime)}
              aria-label={pinnedTime !== null ? "Unpin crosshair" : "Pin crosshair"}
              aria-pressed={pinnedTime !== null}
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded border transition-colors ${
                pinnedTime !== null
                  ? "bg-signal/20 border-signal text-signal font-bold"
                  : "bg-white/5 border-white/10 text-gray-400 hover:text-white"
              }`}
              title={pinnedTime !== null ? "Click to unpin crosshair" : "Click to freeze crosshair for measurement"}
            >
              <Pin size={10} className={pinnedTime !== null ? "rotate-45" : ""} />
              <span>{pinnedTime !== null ? "Pinned" : "Pin"}</span>
            </button>
          )}

          {summaryData && summaryData.length > 0 && (
            <button
              type="button"
              onClick={() => setShowTable(!showTable)}
              aria-expanded={showTable}
              aria-label={`Toggle accessible data table for ${title || 'chart'}`}
              className="px-2 py-0.5 rounded bg-black/60 border border-white/10 text-gray-400 hover:text-white transition-colors"
            >
              {showTable ? "Chart View" : "Data Table"}
            </button>
          )}
        </div>
      </div>

      {showTable && summaryData ? (
        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
          <h4 className="text-xs font-bold text-white mb-2">{title || "Chart Data Summary"}</h4>
          <table className="w-full text-left text-xs font-mono border-collapse">
            <thead>
              <tr className="border-b border-[#252525] text-gray-400">
                <th className="py-1 px-2">Metric</th>
                <th className="py-1 px-2 text-right">Value</th>
              </tr>
            </thead>
            <tbody>
              {summaryData.map((row, idx) => (
                <tr key={idx} className="border-b border-[#1a1a1a] text-gray-300">
                  <td className="py-1 px-2">{row.label}</td>
                  <td className="py-1 px-2 text-right text-white font-bold">{row.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex-1 min-h-0 min-w-0">
          {children}
        </div>
      )}
    </div>
  );
}
