"use client";

import React, { useState } from "react";
import { Compass, Gauge, AlertCircle, ArrowUpRight, ArrowDownRight, CheckCircle2 } from "lucide-react";

export interface CornerItem {
  corner_id: number;
  name: string;
  sector_id: number;
  entry_distance_m: number;
  apex_distance_m: number;
  exit_distance_m: number;
  entry_speed_mps: number;
  min_speed_mps: number;
  exit_speed_mps: number;
  braking_distance_m: number;
  peak_lateral_g: number;
  mean_lateral_g: number;
  peak_longitudinal_g: number;
  time_in_corner_s: number;
  tire_utilization_peak?: number;
  aero_downforce_at_apex_n?: number;
}

export interface CornerComparisonItem {
  corner_id: number;
  corner_name: string;
  delta_entry_speed_mps: number;
  delta_min_speed_mps: number;
  delta_exit_speed_mps: number;
  delta_braking_distance_m: number;
  delta_time_s: number;
  delta_peak_lateral_g: number;
  likely_cause: string;
  confidence: string;
}

interface CornerAnalysisPanelProps {
  corners: CornerItem[];
  comparisons?: CornerComparisonItem[];
  selectedCornerId?: number | null;
  onSelectCorner?: (cornerId: number) => void;
}

export default function CornerAnalysisPanel({
  corners,
  comparisons = [],
  selectedCornerId,
  onSelectCorner,
}: CornerAnalysisPanelProps) {
  const [filterSector, setFilterSector] = useState<number | "all">("all");

  const compMap = new Map<number, CornerComparisonItem>();
  comparisons.forEach(c => compMap.set(c.corner_id, c));

  const filteredCorners = filterSector === "all"
    ? corners
    : corners.filter(c => c.sector_id === filterSector);

  if (!corners || corners.length === 0) {
    return (
      <div className="p-8 text-center text-gray-500 text-xs bg-[#0d0d0f] border border-[#1f1f23] rounded-xl">
        No detected corner telemetry available. Run a simulation on a curved circuit to extract corner telemetry.
      </div>
    );
  }

  return (
    <div className="w-full bg-[#0a0a0c] border border-[#1f1f23] rounded-xl p-4 flex flex-col space-y-4">
      {/* Header & Sector Filter */}
      <div className="flex items-center justify-between pb-3 border-b border-[#1f1f23]">
        <div className="flex items-center gap-2">
          <Compass size={16} className="text-[#f2a900]" />
          <h3 className="text-xs font-bold text-white tracking-wide">Corner-by-Corner Engineering Analysis</h3>
          <span className="text-[10px] text-gray-500 bg-[#16161a] px-2 py-0.5 rounded border border-[#27272a]">
            {corners.length} Turns Detected
          </span>
        </div>

        <div className="flex items-center gap-1">
          <span className="text-[10px] text-gray-500 mr-1">Sector:</span>
          {(["all", 1, 2, 3] as const).map(sec => (
            <button
              key={sec}
              onClick={() => setFilterSector(sec)}
              className={`px-2 py-0.5 text-[10px] font-mono rounded ${
                filterSector === sec ? "bg-[#f2a900] text-black font-bold" : "bg-[#141417] text-gray-400 hover:text-white"
              }`}
            >
              {sec === "all" ? "All" : `S${sec}`}
            </button>
          ))}
        </div>
      </div>

      {/* Corners Table */}
      <div className="w-full overflow-x-auto">
        <table className="w-full text-left border-collapse text-[11px] font-mono">
          <thead>
            <tr className="border-b border-[#222226] text-gray-500 uppercase text-[9px] tracking-wider">
              <th className="py-2 px-2">Turn</th>
              <th className="py-2 px-2">Apex Dist</th>
              <th className="py-2 px-2">Apex Speed</th>
              <th className="py-2 px-2">Entry Speed</th>
              <th className="py-2 px-2">Exit Speed</th>
              <th className="py-2 px-2">Braking Dist</th>
              <th className="py-2 px-2">Peak Lat G</th>
              <th className="py-2 px-2">Time in Turn</th>
              {comparisons.length > 0 && <th className="py-2 px-2 text-[#f2a900]">Delta vs Setup A</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#18181c]">
            {filteredCorners.map(c => {
              const isSelected = selectedCornerId === c.corner_id;
              const comp = compMap.get(c.corner_id);

              return (
                <tr
                  key={c.corner_id}
                  onClick={() => onSelectCorner?.(c.corner_id)}
                  className={`cursor-pointer transition-colors ${
                    isSelected ? "bg-[#f2a900]/10 text-white" : "hover:bg-[#141417] text-gray-300"
                  }`}
                >
                  <td className="py-2 px-2 font-bold text-white flex items-center gap-1.5">
                    <span className="w-5 h-5 rounded-full bg-[#18181b] border border-[#27272a] inline-flex items-center justify-center text-[9px] text-[#f2a900]">
                      T{c.corner_id}
                    </span>
                    <span>{c.name}</span>
                  </td>
                  <td className="py-2 px-2 text-gray-400">{c.apex_distance_m.toFixed(0)} m</td>
                  <td className="py-2 px-2 font-bold text-emerald-400">
                    {(c.min_speed_mps * 3.6).toFixed(1)} km/h
                  </td>
                  <td className="py-2 px-2 text-gray-400">{(c.entry_speed_mps * 3.6).toFixed(1)} km/h</td>
                  <td className="py-2 px-2 text-gray-400">{(c.exit_speed_mps * 3.6).toFixed(1)} km/h</td>
                  <td className="py-2 px-2 text-amber-400/90">{c.braking_distance_m.toFixed(1)} m</td>
                  <td className="py-2 px-2 text-purple-400">{c.peak_lateral_g.toFixed(2)} g</td>
                  <td className="py-2 px-2 text-gray-300">{c.time_in_corner_s.toFixed(3)} s</td>

                  {/* Comparison Delta Cell */}
                  {comparisons.length > 0 && (
                    <td className="py-2 px-2">
                      {comp ? (
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              comp.delta_time_s < -0.01
                                ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800/40"
                                : comp.delta_time_s > 0.01
                                ? "bg-rose-950/80 text-rose-400 border border-rose-800/40"
                                : "text-gray-400"
                            }`}
                          >
                            {comp.delta_time_s < 0 ? "" : "+"}
                            {comp.delta_time_s.toFixed(3)}s
                          </span>
                          <span className="text-[9px] text-gray-500 truncate max-w-[160px]" title={comp.likely_cause}>
                            {comp.likely_cause}
                          </span>
                        </div>
                      ) : (
                        <span className="text-gray-600">—</span>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
