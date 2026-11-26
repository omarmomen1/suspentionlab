"use client";

import React, { useMemo } from "react";
import {
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  Pin,
  RefreshCw,
  Gauge,
  Zap,
  Activity,
  ArrowRight,
  Sliders,
} from "lucide-react";
import Plot from "./Plot";
import { darkLayout } from "./theme";
import DifferenceRibbon from "../v2/instruments/DifferenceRibbon";
import { cornerDeltasFromCumulative } from "../../lib/v2/instruments";

export interface SectorDeltaItem {
  sector_id: number;
  time_a_s: number;
  time_b_s: number;
  delta_s: number;
  primary_category?: string;
  contributing_factors?: string[];
  confidence?: string;
  evidence?: string[];
}

export interface LapDeltaReportData {
  total_delta_s: number;
  sector_deltas: SectorDeltaItem[];
  cumulative_delta_distance: number[];
  cumulative_delta_time: number[];
  speed_diff: number[];
  summary: string;
  model_assumptions_caveat?: string;
}

export interface LapRunData {
  lap_time_s: number;
  sector_times?: number[];
  max_speed_kmh?: number;
  min_speed_kmh?: number;
  avg_speed_kmh?: number;
  energy_used_kj?: number;
  trace?: {
    s_m?: number[];
    speed_kmh?: number[];
    lat_g?: number[];
    long_g?: number[];
    limiting_factor?: string[];
  };
  telemetry?: {
    distances?: number[];
    speeds_kmh?: number[];
  };
}

export interface VehicleSetupParameters {
  mass?: number;
  power_kw?: number;
  cl?: number;
  cd?: number;
  tire_mu?: number;
  front_spring_rate?: number;
  rear_spring_rate?: number;
  front_arb?: number;
  rear_arb?: number;
  front_rc_height?: number;
  rear_rc_height?: number;
  [key: string]: any;
}

export interface LapDeltaViewProps {
  baselineRun?: LapRunData | null; // Setup A
  currentRun?: LapRunData | null;  // Setup B
  // Backwards compatible aliases
  lapA?: LapRunData | null;
  lapB?: LapRunData | null;
  report?: LapDeltaReportData | null;
  setupAParams?: VehicleSetupParameters | null;
  setupBParams?: VehicleSetupParameters | null;
  setupAName?: string;
  setupBName?: string;
  onPinBaseline?: () => void;
  onResetToBaseline?: () => void;
  /** Corner apex positions [m] for the difference ribbon. Omit when the track has no corner list. */
  corners?: { name: string; distM: number }[];
}


/** Corner zones: from the midpoint to the previous apex to the midpoint to the next. First starts at the first sample, last ends at the last. */
function cornerZones(corners: { name: string; distM: number }[] | undefined, sM: number[]) {
  if (!corners || corners.length === 0 || sM.length < 2) return [];
  const sorted = [...corners].sort((a, b) => a.distM - b.distM);
  const start = sM[0];
  const end = sM[sM.length - 1];
  return sorted.map((c, i) => ({
    corner: c.name,
    start_m: i === 0 ? start : (sorted[i - 1].distM + c.distM) / 2,
    end_m: i === sorted.length - 1 ? end : (c.distM + sorted[i + 1].distM) / 2,
  }));
}

export default function LapDeltaView({
  baselineRun,
  currentRun,
  lapA,
  lapB,
  report,
  setupAParams,
  setupBParams,
  setupAName = "Setup A (Baseline)",
  setupBName = "Setup B (Candidate)",
  onPinBaseline,
  onResetToBaseline,
  corners,
}: LapDeltaViewProps) {
  // Normalize runs safely
  const runA = baselineRun ?? lapA ?? null;
  const runB = currentRun ?? lapB ?? null;

  // Compute live deltas between Setup A and Setup B
  const comparison = useMemo(() => {
    if (!runA || !runB) return null;

    // Track-length compatibility guard: comparing laps from different-length
    // tracks produces nonsense deltas (e.g. "-80.676s FASTER"). Bail honestly.
    const lenOf = (run: any): number | null => {
      const s = run?.trace?.s_m ?? run?.telemetry?.distances;
      return Array.isArray(s) && s.length > 0 ? s[s.length - 1] : null;
    };
    const lenA = lenOf(runA);
    const lenB = lenOf(runB);
    if (lenA && lenB && Math.abs(lenA - lenB) / Math.max(lenA, lenB) > 0.10) {
      return { incompatible: true as const, lenA, lenB };
    }

    const timeA = runA.lap_time_s ?? 0;
    const timeB = runB.lap_time_s ?? 0;
    const totalDeltaS = timeB - timeA;

    // Sector splits
    const sA = Array.isArray(runA.sector_times) ? runA.sector_times : [timeA / 3, timeA / 3, timeA / 3];
    const sB = Array.isArray(runB.sector_times) ? runB.sector_times : [timeB / 3, timeB / 3, timeB / 3];

    const deltaS1 = (sB[0] ?? 0) - (sA[0] ?? 0);
    const deltaS2 = (sB[1] ?? 0) - (sA[1] ?? 0);
    const deltaS3 = (sB[2] ?? 0) - (sA[2] ?? 0);

    // Speed and energy deltas
    const maxSpeedA = runA.max_speed_kmh ?? 0;
    const maxSpeedB = runB.max_speed_kmh ?? 0;
    const deltaVMax = maxSpeedB - maxSpeedA;

    const minSpeedA = runA.min_speed_kmh ?? 0;
    const minSpeedB = runB.min_speed_kmh ?? 0;
    const deltaVMin = minSpeedB - minSpeedA;

    const energyA = runA.energy_used_kj ?? 0;
    const energyB = runB.energy_used_kj ?? 0;
    const deltaEnergy = energyB - energyA;

    // Distance and speed traces
    const traceA = runA.trace ?? { s_m: runA.telemetry?.distances, speed_kmh: runA.telemetry?.speeds_kmh };
    const traceB = runB.trace ?? { s_m: runB.telemetry?.distances, speed_kmh: runB.telemetry?.speeds_kmh };

    const distsA = Array.isArray(traceA?.s_m) ? traceA.s_m : [];
    const speedsA = Array.isArray(traceA?.speed_kmh) ? traceA.speed_kmh : [];
    const distsB = Array.isArray(traceB?.s_m) ? traceB.s_m : [];
    const speedsB = Array.isArray(traceB?.speed_kmh) ? traceB.speed_kmh : [];

    const commonLen = Math.min(distsA.length, speedsA.length, distsB.length, speedsB.length);
    const sM: number[] = [];
    const speedAFiltered: number[] = [];
    const speedBFiltered: number[] = [];
    const cumulativeDeltaTime: number[] = [];

    let runningDeltaT = 0;
    for (let i = 0; i < commonLen; i++) {
      const s = distsA[i];
      sM.push(s);
      const vA = Math.max(speedsA[i] / 3.6, 1.0);
      const vB = Math.max(speedsB[i] / 3.6, 1.0);

      speedAFiltered.push(speedsA[i]);
      speedBFiltered.push(speedsB[i]);

      if (i > 0) {
        const ds = distsA[i] - distsA[i - 1];
        runningDeltaT += ds / vB - ds / vA;
      }
      cumulativeDeltaTime.push(runningDeltaT);
    }

    return {
      timeA,
      timeB,
      totalDeltaS,
      sA,
      sB,
      deltaS1,
      deltaS2,
      deltaS3,
      deltaVMax,
      deltaVMin,
      deltaEnergy,
      sM,
      speedAFiltered,
      speedBFiltered,
      cumulativeDeltaTime,
    };
  }, [runA, runB]);

  if (!comparison && !report) {
    return (
      <div className="w-full p-8 text-center bg-[#0D1017] border border-[#1f2430] rounded-xl flex flex-col items-center justify-center space-y-3">
        <div className="w-12 h-12 rounded-xl bg-[#151922] border border-[#252c3b] flex items-center justify-center">
          <Pin size={20} className="text-amber-400" />
        </div>
        <div className="text-sm font-bold text-white">Ghost Car Comparison Inactive</div>
        <p className="text-xs text-zinc-500 max-w-md">
          Click <strong className="text-amber-400">&quot;Pin as Baseline (Setup A)&quot;</strong> after running a simulation, then tweak vehicle sliders to inspect live delta time, sector splits, and continuous time gain/loss.
        </p>
        {onPinBaseline && (
          <button
            onClick={onPinBaseline}
            className="mt-2 px-3.5 py-1.5 rounded-lg text-xs font-bold bg-[#f2a900] text-black hover:bg-[#ffb800] transition-all flex items-center gap-1.5 cursor-pointer shadow-md"
          >
            <Pin size={12} />
            Pin Current Setup as Baseline A
          </button>
        )}
      </div>
    );
  }

  if (comparison && "incompatible" in comparison) {
    return (
      <div className="w-full p-8 text-center bg-[#0D1017] border border-[#1f2430] rounded-xl flex flex-col items-center justify-center space-y-3">
        <div className="text-sm font-bold text-amber-400">Incompatible Track Lengths - Delta N/A</div>
        <p className="text-xs text-zinc-500 max-w-md">
          Baseline A ran {((comparison.lenA ?? 0) / 1000).toFixed(2)} km but Candidate B ran {((comparison.lenB ?? 0) / 1000).toFixed(2)} km
          (&gt;10% length mismatch). Lap-time deltas across different tracks are meaningless.
          Re-pin a baseline on the same track to compare setups.
        </p>
      </div>
    );
  }

  const deltaS = comparison?.totalDeltaS ?? report?.total_delta_s ?? 0;
  const isFaster = deltaS < -0.005;
  const isSlower = deltaS > 0.005;

  return (
    <div className="w-full bg-[#0D1017] border border-[#1f2430] rounded-xl p-4 flex flex-col space-y-4 shadow-xl">
      {/* Top Banner: Total Lap Time Delta & Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-xl bg-[#121620] border border-[#1f2533]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] text-zinc-400 uppercase tracking-widest font-mono">
              Live Ghost Comparison
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-mono">
              Setup B vs. Setup A
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Formatted Δt */}
            <span
              className={`text-2xl font-black font-mono tracking-tight ${
                isFaster ? "text-[#10B981]" : isSlower ? "text-[#F43F5E]" : "text-zinc-300"
              }`}
            >
              {deltaS < 0 ? "" : "+"}
              {deltaS.toFixed(3)}s
            </span>

            {/* Faster/Slower Badge */}
            <span
              className={`px-2.5 py-1 rounded-md text-[10px] font-black uppercase tracking-wider border font-mono ${
                isFaster
                  ? "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/40"
                  : isSlower
                  ? "bg-[#F43F5E]/15 text-[#F43F5E] border-[#F43F5E]/40"
                  : "bg-zinc-800 text-zinc-400 border-zinc-700"
              }`}
            >
              {isFaster
                ? `${Math.abs(deltaS).toFixed(2)}s FASTER`
                : isSlower
                ? `+${deltaS.toFixed(2)}s SLOWER`
                : "EQUAL PACE"}
            </span>
          </div>

          {comparison && (
            <div className="flex items-center gap-3 mt-1.5 text-[11px] font-mono text-zinc-400">
              <span>
                Baseline A: <strong className="text-white">{comparison.timeA.toFixed(3)}s</strong>
              </span>
              <ArrowRight size={11} className="text-zinc-600" />
              <span>
                Candidate B: <strong className="text-amber-400">{comparison.timeB.toFixed(3)}s</strong>
              </span>
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          {onPinBaseline && (
            <button
              onClick={onPinBaseline}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#161c28] hover:bg-[#1e2536] text-amber-300 border border-amber-500/40 transition-all flex items-center gap-1.5 cursor-pointer shadow-sm"
              title="Pin current vehicle parameters as Setup A baseline"
            >
              <Pin size={12} />
              Pin Baseline (A)
            </button>
          )}

          {onResetToBaseline && (
            <button
              onClick={onResetToBaseline}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#121620] hover:bg-[#1a202d] text-zinc-300 border border-zinc-700 transition-all flex items-center gap-1.5 cursor-pointer"
              title="Restore candidate sliders to match Setup A baseline"
            >
              <RefreshCw size={12} />
              Reset to Setup A
            </button>
          )}
        </div>
      </div>

      {/* Sector 1, 2, 3 Deltas & Velocity/Energy Deltas Strip */}
      {comparison && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {/* ΔS1 */}
          <div className="p-2.5 rounded-lg bg-[#121620] border border-[#1f2533] flex flex-col justify-between">
            <span className="text-[9px] uppercase tracking-wider font-mono text-zinc-500">Δ Sector 1</span>
            <span
              className={`text-sm font-black font-mono mt-0.5 ${
                comparison.deltaS1 < 0 ? "text-[#10B981]" : comparison.deltaS1 > 0 ? "text-[#F43F5E]" : "text-zinc-300"
              }`}
            >
              {comparison.deltaS1 < 0 ? "" : "+"}
              {comparison.deltaS1.toFixed(3)}s
            </span>
          </div>

          {/* ΔS2 */}
          <div className="p-2.5 rounded-lg bg-[#121620] border border-[#1f2533] flex flex-col justify-between">
            <span className="text-[9px] uppercase tracking-wider font-mono text-zinc-500">Δ Sector 2</span>
            <span
              className={`text-sm font-black font-mono mt-0.5 ${
                comparison.deltaS2 < 0 ? "text-[#10B981]" : comparison.deltaS2 > 0 ? "text-[#F43F5E]" : "text-zinc-300"
              }`}
            >
              {comparison.deltaS2 < 0 ? "" : "+"}
              {comparison.deltaS2.toFixed(3)}s
            </span>
          </div>

          {/* ΔS3 */}
          <div className="p-2.5 rounded-lg bg-[#121620] border border-[#1f2533] flex flex-col justify-between">
            <span className="text-[9px] uppercase tracking-wider font-mono text-zinc-500">Δ Sector 3</span>
            <span
              className={`text-sm font-black font-mono mt-0.5 ${
                comparison.deltaS3 < 0 ? "text-[#10B981]" : comparison.deltaS3 > 0 ? "text-[#F43F5E]" : "text-zinc-300"
              }`}
            >
              {comparison.deltaS3 < 0 ? "" : "+"}
              {comparison.deltaS3.toFixed(3)}s
            </span>
          </div>

          {/* ΔV_max */}
          <div className="p-2.5 rounded-lg bg-[#121620] border border-[#1f2533] flex flex-col justify-between">
            <span className="text-[9px] uppercase tracking-wider font-mono text-zinc-500">Δ V_max</span>
            <span
              className={`text-sm font-black font-mono mt-0.5 ${
                comparison.deltaVMax > 0 ? "text-[#10B981]" : comparison.deltaVMax < 0 ? "text-[#F43F5E]" : "text-zinc-300"
              }`}
            >
              {comparison.deltaVMax > 0 ? "+" : ""}
              {comparison.deltaVMax.toFixed(1)} km/h
            </span>
          </div>

          {/* ΔV_min */}
          <div className="p-2.5 rounded-lg bg-[#121620] border border-[#1f2533] flex flex-col justify-between">
            <span className="text-[9px] uppercase tracking-wider font-mono text-zinc-500">Δ V_min (Apex)</span>
            <span
              className={`text-sm font-black font-mono mt-0.5 ${
                comparison.deltaVMin > 0 ? "text-[#10B981]" : comparison.deltaVMin < 0 ? "text-[#F43F5E]" : "text-zinc-300"
              }`}
            >
              {comparison.deltaVMin > 0 ? "+" : ""}
              {comparison.deltaVMin.toFixed(1)} km/h
            </span>
          </div>

          {/* ΔEnergy */}
          <div className="p-2.5 rounded-lg bg-[#121620] border border-[#1f2533] flex flex-col justify-between">
            <span className="text-[9px] uppercase tracking-wider font-mono text-zinc-500">Δ Energy</span>
            <span
              className={`text-sm font-black font-mono mt-0.5 ${
                comparison.deltaEnergy < 0 ? "text-[#10B981]" : comparison.deltaEnergy > 0 ? "text-[#F43F5E]" : "text-zinc-300"
              }`}
            >
              {comparison.deltaEnergy > 0 ? "+" : ""}
              {comparison.deltaEnergy.toFixed(0)} kJ
            </span>
          </div>
        </div>
      )}

      {/* V2 Difference Ribbon: per-corner-zone time delta (only when a corner list exists and the guard passed) */}
      {comparison && !("incompatible" in comparison) && (
        <DifferenceRibbon
          deltas={cornerDeltasFromCumulative(comparison.sM, comparison.cumulativeDeltaTime, cornerZones(corners, comparison.sM))}
        />
      )}

      {/* Synchronized Plotly Distance-Domain Trace: Speed A (#06B6D4) vs Speed B (#F43F5E) & Δt(s) (#F59E0B) */}
      {comparison && comparison.sM.length > 0 && (
        <div className="h-[270px] w-full bg-[#090c12] border border-[#1b202c] rounded-xl p-2.5">
          <Plot
            data={[
              {
                x: comparison.sM,
                y: comparison.speedAFiltered,
                type: "scatter",
                mode: "lines",
                name: "Setup A Speed (Baseline)",
                line: { color: "#06B6D4", width: 1.8 },
                yaxis: "y",
              },
              {
                x: comparison.sM,
                y: comparison.speedBFiltered,
                type: "scatter",
                mode: "lines",
                name: "Setup B Speed (Candidate)",
                line: { color: "#F43F5E", width: 1.8 },
                yaxis: "y",
              },
              {
                x: comparison.sM,
                y: comparison.cumulativeDeltaTime,
                type: "scatter",
                mode: "lines",
                name: "Cumulative Δt(s) (Gain/Loss)",
                line: { color: "#F59E0B", width: 2, dash: "dot" },
                yaxis: "y2",
              },
            ]}
            layout={{
              ...darkLayout({
                title: {
                  text: "Distance-Domain Trace: Setup A Speed vs. Setup B Speed & Cumulative Time Gain/Loss Δt(s)",
                  font: { color: "#a1a1aa", size: 11 },
                },
                xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                yaxis: { title: { text: "Speed [km/h]", font: { color: "#71717a" } } },
                margin: { l: 50, r: 50, t: 30, b: 40 },
                legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } },
              }),
              yaxis2: {
                title: { text: "Δt [s]", font: { color: "#F59E0B" } },
                tickfont: { color: "#F59E0B" },
                overlaying: "y",
                side: "right",
                gridcolor: "transparent",
                zeroline: true,
                zerolinecolor: "#3f3f46",
              },
            } as Record<string, unknown>}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
          />
        </div>
      )}

      {/* Parameter Diff Table (Setup A vs Setup B) */}
      {setupAParams && setupBParams && (
        <div className="pt-2 border-t border-[#1f2430]">
          <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-400 mb-2 font-mono flex items-center gap-1.5">
            <Sliders size={12} className="text-amber-400" />
            <span>Setup Parameter Variance</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            {[
              { label: "Mass", key: "mass", unit: "kg" },
              { label: "Power", key: "power_kw", unit: "kW" },
              { label: "Downforce Cl", key: "cl", unit: "" },
              { label: "Drag Cd", key: "cd", unit: "" },
              { label: "Tire Grip μ", key: "tire_mu", unit: "" },
              { label: "Front Spring", key: "front_spring_rate", unit: "N/mm" },
              { label: "Rear Spring", key: "rear_spring_rate", unit: "N/mm" },
              { label: "Front ARB", key: "front_arb", unit: "N/mm" },
              { label: "Rear ARB", key: "rear_arb", unit: "N/mm" },
              { label: "Front RC", key: "front_rc_height", unit: "mm" },
              { label: "Rear RC", key: "rear_rc_height", unit: "mm" },
            ].map(({ label, key, unit }) => {
              const valA = setupAParams[key];
              const valB = setupBParams[key];
              if (valA === undefined && valB === undefined) return null;
              const numA = typeof valA === "number" ? valA : 0;
              const numB = typeof valB === "number" ? valB : 0;
              const diff = numB - numA;
              const hasDiff = Math.abs(diff) > 1e-4;

              return (
                <div
                  key={key}
                  className={`p-2 rounded-lg border text-[10px] font-mono flex flex-col justify-between ${
                    hasDiff
                      ? "bg-[#161d2a] border-amber-500/40 text-zinc-200"
                      : "bg-[#10141d] border-[#1c2230] text-zinc-500"
                  }`}
                >
                  <span className="text-zinc-400 font-sans text-[9px] uppercase truncate">{label}</span>
                  <div className="flex items-baseline justify-between mt-1">
                    <span className="text-zinc-400">{numA}</span>
                    <span className="text-zinc-600">➔</span>
                    <span className={hasDiff ? "text-amber-400 font-bold" : "text-zinc-400"}>
                      {numB} {unit}
                    </span>
                  </div>
                  {hasDiff && (
                    <div
                      className={`text-[9px] mt-0.5 text-right font-bold ${
                        diff > 0 ? "text-cyan-400" : "text-rose-400"
                      }`}
                    >
                      {diff > 0 ? `+${diff.toFixed(2)}` : diff.toFixed(2)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
