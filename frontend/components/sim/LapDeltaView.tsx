"use client";

import React from "react";
import { TrendingDown, TrendingUp, AlertTriangle, CheckCircle2, Sliders, ShieldCheck } from "lucide-react";
import Plot from "./Plot";
import { darkLayout } from "./theme";

export interface SectorDeltaItem {
  sector_id: number;
  time_a_s: number;
  time_b_s: number;
  delta_s: number;
  primary_category: string;
  contributing_factors: string[];
  confidence: string;
  evidence: string[];
}

export interface LapDeltaReportData {
  total_delta_s: number;
  sector_deltas: SectorDeltaItem[];
  cumulative_delta_distance: number[];
  cumulative_delta_time: number[];
  speed_diff: number[];
  summary: string;
  model_assumptions_caveat: string;
}

interface LapDeltaViewProps {
  report: LapDeltaReportData | null;
  setupAName?: string;
  setupBName?: string;
}

export default function LapDeltaView({
  report,
  setupAName = "Setup A (Baseline)",
  setupBName = "Setup B (Candidate)",
}: LapDeltaViewProps) {
  if (!report) {
    return (
      <div className="p-8 text-center text-gray-500 text-xs bg-[#0d0d0f] border border-[#1f1f23] rounded-xl">
        Run an A/B setup comparison to generate a causal lap delta attribution report.
      </div>
    );
  }

  const isFaster = report.total_delta_s < -0.005;
  const isSlower = report.total_delta_s > 0.005;

  return (
    <div className="w-full bg-[#0a0a0c] border border-[#1f1f23] rounded-xl p-4 flex flex-col space-y-4">
      {/* Top Delta Summary Banner */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-[#141417] border border-[#222226]">
        <div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wider font-mono">Lap Time Delta (B - A)</div>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className={`text-xl font-bold font-mono ${
                isFaster ? "text-emerald-400" : isSlower ? "text-rose-400" : "text-gray-300"
              }`}
            >
              {report.total_delta_s < 0 ? "" : "+"}
              {report.total_delta_s.toFixed(3)} s
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                isFaster
                  ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800/50"
                  : isSlower
                  ? "bg-rose-950/80 text-rose-400 border border-rose-800/50"
                  : "bg-gray-800 text-gray-400"
              }`}
            >
              {isFaster ? "Setup B Faster" : isSlower ? "Setup B Slower" : "Equal Performance"}
            </span>
          </div>
        </div>

        <div className="text-right max-w-sm">
          <div className="text-[10px] text-gray-500 font-mono">Attribution Summary</div>
          <div className="text-[11px] text-gray-300 line-clamp-2 mt-0.5 leading-snug">
            {report.summary}
          </div>
        </div>
      </div>

      {/* Cumulative Time Delta Chart */}
      <div className="h-[220px] w-full">
        <Plot
          data={[
            {
              x: report.cumulative_delta_distance,
              y: report.cumulative_delta_time,
              type: "scatter",
              mode: "lines",
              name: "Cumulative Delta (s)",
              line: { color: isFaster ? "#10b981" : "#ef4444", width: 2 },
            },
            {
              x: report.cumulative_delta_distance,
              y: Array(report.cumulative_delta_distance.length).fill(0),
              type: "scatter",
              mode: "lines",
              name: "Zero Delta Reference",
              line: { color: "#3f3f46", dash: "dash", width: 1 },
              showlegend: false,
            },
          ]}
          layout={darkLayout({
            title: { text: "Cumulative Time Delta along Circuit", font: { color: "#71717a", size: 11 } },
            xaxis: { title: { text: "Track Distance [m]", font: { color: "#71717a" } } },
            yaxis: {
              title: { text: "Delta [s] (Negative = B Faster)", font: { color: "#71717a" } },
              zeroline: true,
              zerolinecolor: "#3f3f46",
            },
            margin: { l: 55, r: 20, t: 25, b: 40 },
          })}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
        />
      </div>

      {/* Sector Delta Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {report.sector_deltas.map(sec => {
          const secFaster = sec.delta_s < -0.005;
          const secSlower = sec.delta_s > 0.005;

          return (
            <div
              key={sec.sector_id}
              className="p-3 rounded-lg bg-[#111114] border border-[#222226] flex flex-col justify-between space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-white font-mono">SECTOR {sec.sector_id}</span>
                <span
                  className={`text-xs font-bold font-mono ${
                    secFaster ? "text-emerald-400" : secSlower ? "text-rose-400" : "text-gray-400"
                  }`}
                >
                  {sec.delta_s < 0 ? "" : "+"}
                  {sec.delta_s.toFixed(3)}s
                </span>
              </div>

              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#1f1f23] text-gray-300 font-mono">
                  {sec.primary_category}
                </span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${
                    sec.confidence === "PROVEN"
                      ? "bg-blue-950 text-blue-400 border border-blue-800/40"
                      : sec.confidence === "LIKELY"
                      ? "bg-emerald-950 text-emerald-400 border border-emerald-800/40"
                      : "bg-gray-800 text-gray-400"
                  }`}
                >
                  {sec.confidence}
                </span>
              </div>

              {sec.evidence && sec.evidence.length > 0 && (
                <div className="text-[10px] text-gray-400 border-t border-[#1e1e22] pt-1.5 space-y-0.5 font-mono">
                  {sec.evidence.map((ev, i) => (
                    <div key={i} className="truncate" title={ev}>
                      • {ev}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Honest Model Disclaimer Caveat */}
      <div className="p-2.5 rounded-lg bg-[#16130b] border border-[#f2a900]/25 text-[10px] text-[#f2a900]/90 flex items-start gap-2">
        <AlertTriangle size={14} className="flex-shrink-0 mt-0.5 text-[#f2a900]" />
        <span>
          <strong>Engineering Disclaimer</strong>: {report.model_assumptions_caveat}
        </span>
      </div>
    </div>
  );
}
