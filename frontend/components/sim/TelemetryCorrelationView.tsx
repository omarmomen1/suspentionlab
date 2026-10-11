"use client";

import React from "react";
import { Activity, ShieldAlert, CheckCircle2, Clock, MapPin } from "lucide-react";
import Plot from "./Plot";
import { darkLayout } from "./theme";

export interface ChannelMetrics {
  channel_name: string;
  unit: string;
  rmse: number;
  mae: number;
  r_squared: number;
  max_abs_error: number;
  max_error_location_m: number;
  phase_lag_m: number;
}

export interface SectorCorrelation {
  sector_id: number;
  start_distance_m: number;
  end_distance_m: number;
  speed_rmse_mps: number;
  speed_rmse_kmh: number;
  fit_rating: string;
}

export interface CorrelationReportData {
  session_id: string;
  track_length_m: number;
  num_aligned_points: number;
  channels: Record<string, ChannelMetrics>;
  aligned_distance_m: number[];
  residuals: Record<string, number[]>;
  sector_correlations: SectorCorrelation[];
  overall_fit_pct: number;
  summary: string;
  model_disclaimer: string;
}

interface TelemetryCorrelationViewProps {
  report: CorrelationReportData | null;
  simSpeedsKmh?: number[];
  measSpeedsKmh?: number[];
  distances?: number[];
}

export default function TelemetryCorrelationView({
  report,
  simSpeedsKmh,
  measSpeedsKmh,
  distances,
}: TelemetryCorrelationViewProps) {
  if (!report) {
    return (
      <div className="p-8 text-center text-gray-500 text-xs bg-[#0d0d0f] border border-[#1f1f23] rounded-xl">
        Upload or provide measured vehicle telemetry to inspect distance-aligned correlation and residuals.
      </div>
    );
  }

  const speedMetrics = report.channels["speed"];

  return (
    <div className="w-full bg-[#0a0a0c] border border-[#1f1f23] rounded-xl p-4 flex flex-col space-y-4">
      {/* Top Correlation Banner */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 rounded-lg bg-[#141417] border border-[#222226]">
          <div className="text-[9px] text-gray-400 uppercase tracking-wider font-mono">Dynamic Fit Index</div>
          <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
            {report.overall_fit_pct.toFixed(1)}%
          </div>
          <div className="text-[9px] text-gray-500 font-mono mt-0.5">Normalized error correlation</div>
        </div>

        <div className="p-3 rounded-lg bg-[#141417] border border-[#222226]">
          <div className="text-[9px] text-gray-400 uppercase tracking-wider font-mono">Speed RMSE</div>
          <div className="text-xl font-bold font-mono text-white mt-1">
            {speedMetrics ? `${(speedMetrics.rmse * 3.6).toFixed(2)} km/h` : "—"}
          </div>
          <div className="text-[9px] text-gray-500 font-mono mt-0.5">
            {speedMetrics ? `${speedMetrics.rmse.toFixed(2)} m/s root-mean-square` : ""}
          </div>
        </div>

        <div className="p-3 rounded-lg bg-[#141417] border border-[#222226]">
          <div className="text-[9px] text-gray-400 uppercase tracking-wider font-mono">Goodness of Fit (R²)</div>
          <div className="text-xl font-bold font-mono text-blue-400 mt-1">
            {speedMetrics ? speedMetrics.r_squared.toFixed(3) : "—"}
          </div>
          <div className="text-[9px] text-gray-500 font-mono mt-0.5">Variance explained</div>
        </div>

        <div className="p-3 rounded-lg bg-[#141417] border border-[#222226]">
          <div className="text-[9px] text-gray-400 uppercase tracking-wider font-mono">Spatial Phase Lag</div>
          <div className="text-xl font-bold font-mono text-[#f2a900] mt-1">
            {speedMetrics ? `${speedMetrics.phase_lag_m > 0 ? "+" : ""}${speedMetrics.phase_lag_m.toFixed(1)} m` : "—"}
          </div>
          <div className="text-[9px] text-gray-500 font-mono mt-0.5">Cross-correlation peak</div>
        </div>
      </div>

      {/* Residuals Chart */}
      {report.residuals["speed"] && (
        <div className="h-[230px] w-full">
          <Plot
            data={[
              {
                x: report.aligned_distance_m,
                y: report.residuals["speed"].map(r => r * 3.6),
                type: "scatter",
                mode: "lines",
                name: "Speed Residual Δv (km/h)",
                line: { color: "#f2a900", width: 1.5 },
              },
              {
                x: report.aligned_distance_m,
                y: Array(report.aligned_distance_m.length).fill(0),
                type: "scatter",
                mode: "lines",
                name: "Zero Residual Reference",
                line: { color: "#52525b", dash: "dash", width: 1 },
              },
            ]}
            layout={darkLayout({
              title: { text: "Point-by-Point Speed Residuals (v_sim - v_meas)", font: { color: "#71717a", size: 11 } },
              xaxis: { title: { text: "Distance along Circuit [m]", font: { color: "#71717a" } } },
              yaxis: { title: { text: "Residual [km/h]", font: { color: "#71717a" } }, zeroline: true },
              margin: { l: 55, r: 20, t: 25, b: 40 },
            })}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
          />
        </div>
      )}

      {/* Sector Correlation Breakdown Table */}
      {report.sector_correlations && report.sector_correlations.length > 0 && (
        <div className="w-full overflow-x-auto border-t border-[#1f1f23] pt-3">
          <div className="text-[10px] font-bold uppercase text-gray-400 font-mono mb-2">Sector Correlation Fit</div>
          <table className="w-full text-left text-[11px] font-mono border-collapse">
            <thead>
              <tr className="border-b border-[#222226] text-gray-500 text-[9px] uppercase">
                <th className="py-1.5 px-2">Sector</th>
                <th className="py-1.5 px-2">Span</th>
                <th className="py-1.5 px-2">Speed RMSE (km/h)</th>
                <th className="py-1.5 px-2">Speed RMSE (m/s)</th>
                <th className="py-1.5 px-2">Fit Rating</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#18181c]">
              {report.sector_correlations.map(sec => (
                <tr key={sec.sector_id}>
                  <td className="py-1.5 px-2 font-bold text-white">Sector {sec.sector_id}</td>
                  <td className="py-1.5 px-2 text-gray-400">
                    {sec.start_distance_m.toFixed(0)}m – {sec.end_distance_m.toFixed(0)}m
                  </td>
                  <td className="py-1.5 px-2 text-emerald-400">{sec.speed_rmse_kmh.toFixed(2)} km/h</td>
                  <td className="py-1.5 px-2 text-gray-300">{sec.speed_rmse_mps.toFixed(3)} m/s</td>
                  <td className="py-1.5 px-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                        sec.fit_rating === "GOOD"
                          ? "bg-emerald-950 text-emerald-400 border border-emerald-800/40"
                          : sec.fit_rating === "FAIR"
                          ? "bg-amber-950 text-amber-400 border border-amber-800/40"
                          : "bg-rose-950 text-rose-400 border border-rose-800/40"
                      }`}
                    >
                      {sec.fit_rating}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Mandatory Honest Model Disclaimer Banner */}
      <div className="p-3 rounded-lg bg-[#141419] border border-amber-500/30 flex items-start gap-2.5 text-[10px] text-amber-300/90 leading-relaxed">
        <ShieldAlert size={16} className="text-amber-400 flex-shrink-0 mt-0.5" />
        <div>
          <strong className="text-white block mb-0.5">Scientific Validation Disclosure</strong>
          {report.model_disclaimer}
        </div>
      </div>
    </div>
  );
}
