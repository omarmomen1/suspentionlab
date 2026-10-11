"use client";

import React from "react";
import { ShieldCheck, Layers } from "lucide-react";
import Plot from "./Plot";
import { DARK_BASE } from "./theme";

export interface CrossValidationData {
  lap_time_qss_s: number;
  lap_time_dyn_s: number;
  delta_s: number;
  gearshift_loss_s: number;
  transient_steer_yaw_lag_s: number;
  compliance_load_transfer_loss_s: number;
  tire_relaxation_lag_s: number;
  ers_energy_delta_kj: number;
  metrics?: {
    speed_r2: number;
    speed_rmse_mps: number;
    speed_rmse_kmh: number;
    max_speed_delta_kmh: number;
    peak_ay_delta_g: number;
    peak_braking_delta_g: number;
  };
  attribution?: {
    gearshift_loss_s: number;
    transient_steer_yaw_lag_s: number;
    compliance_load_transfer_loss_s: number;
    tire_relaxation_lag_s: number;
    ers_energy_delta_kj: number;
  };
  attribution_breakdown_pct?: {
    gearshift_loss_pct: number;
    transient_lag_pct: number;
    compliance_loss_pct: number;
    tire_relaxation_pct: number;
  };
  provenance?: Record<string, unknown>;
  validity_record?: {
    status: string;
    model: string;
    assumptions?: string[];
    validation_evidence?: string;
  };
}

interface CrossValidationViewProps {
  data: CrossValidationData | null;
  qssDistances?: number[];
  qssSpeedsKmh?: number[];
  dynDistances?: number[];
  dynSpeedsKmh?: number[];
}

export default function CrossValidationView({
  data,
  qssDistances = [],
  qssSpeedsKmh = [],
  dynDistances = [],
  dynSpeedsKmh = [],
}: CrossValidationViewProps) {
  if (!data) {
    return (
      <div className="p-8 text-center text-gray-500 text-xs bg-[#0d0d0f] border border-[#1f1f23] rounded-xl">
        Execute Cross-Validation to correlate Fast QSS with 14-DOF Transient Lap Simulation.
      </div>
    );
  }

  const r2 = data.metrics?.speed_r2 ?? 0;
  const rmseKmh = data.metrics?.speed_rmse_kmh ?? ((data.metrics?.speed_rmse_mps ?? 0) * 3.6);
  const deltaS = data.delta_s;
  const attr = data.attribution ?? {
    gearshift_loss_s: data.gearshift_loss_s,
    transient_steer_yaw_lag_s: data.transient_steer_yaw_lag_s,
    compliance_load_transfer_loss_s: data.compliance_load_transfer_loss_s,
    tire_relaxation_lag_s: data.tire_relaxation_lag_s,
    ers_energy_delta_kj: data.ers_energy_delta_kj,
  };
  const breakdown = data.attribution_breakdown_pct ?? {
    gearshift_loss_pct: 0,
    transient_lag_pct: 0,
    compliance_loss_pct: 0,
    tire_relaxation_pct: 0,
  };

  const isHighCorrelation = r2 >= 0.85;

  return (
    <div className="w-full bg-[#0a0a0c] border border-[#1f1f23] rounded-xl p-4 flex flex-col space-y-4">
      {/* Top Banner: Times and Correlation */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {/* QSS Lap Time */}
        <div className="p-3 rounded-lg bg-[#121215] border border-[#202025]">
          <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Fast QSS Baseline</div>
          <div className="text-xl font-bold font-mono text-amber-400 mt-1">
            {data.lap_time_qss_s.toFixed(3)} s
          </div>
          <div className="text-[10px] text-zinc-500 mt-0.5">Steady-state equilibrium</div>
        </div>

        {/* 14-DOF Dynamic Lap Time */}
        <div className="p-3 rounded-lg bg-[#121215] border border-[#202025]">
          <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">14-DOF Transient</div>
          <div className="text-xl font-bold font-mono text-blue-400 mt-1">
            {data.lap_time_dyn_s.toFixed(3)} s
          </div>
          <div className="text-[10px] text-zinc-500 mt-0.5">Driver preview + compliance</div>
        </div>

        {/* Delta */}
        <div className="p-3 rounded-lg bg-[#121215] border border-[#202025]">
          <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Lap Time Delta (Dyn - QSS)</div>
          <div className={`text-xl font-bold font-mono mt-1 ${deltaS >= 0 ? "text-rose-400" : "text-emerald-400"}`}>
            {deltaS >= 0 ? "+" : ""}{deltaS.toFixed(3)} s
          </div>
          <div className="text-[10px] text-zinc-500 mt-0.5">Physical overhead & lag</div>
        </div>

        {/* Correlation R^2 & RMSE */}
        <div className="p-3 rounded-lg bg-[#121215] border border-[#202025]">
          <div className="flex items-center justify-between">
            <span className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Speed R² Correlation</span>
            <ShieldCheck size={13} className={isHighCorrelation ? "text-emerald-400" : "text-amber-400"} />
          </div>
          <div className="text-xl font-bold font-mono text-white mt-1">
            {r2.toFixed(3)}
          </div>
          <div className="text-[10px] text-zinc-400 mt-0.5">RMSE: {rmseKmh.toFixed(1)} km/h</div>
        </div>
      </div>

      {/* Causal Delta Decomposition Breakdown */}
      <div className="p-3.5 rounded-lg bg-[#121215] border border-[#202025] flex flex-col space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-[11px] font-bold text-white uppercase tracking-wider flex items-center gap-1.5 font-mono">
            <Layers size={13} className="text-amber-400" />
            Causal Physical Delta Decomposition
          </div>
          {data.validity_record && (
            <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-[#1c1c22] border border-[#2d2d38] text-zinc-300">
              Validity: {data.validity_record.status}
            </span>
          )}
        </div>

        {/* Stacked Progress Bar */}
        <div className="h-3 w-full bg-[#1c1c22] rounded-full overflow-hidden flex">
          <div
            style={{ width: `${Math.max(breakdown.gearshift_loss_pct, 2)}%` }}
            className="bg-amber-500 h-full"
            title={`Gearshifts: ${breakdown.gearshift_loss_pct}%`}
          />
          <div
            style={{ width: `${Math.max(breakdown.transient_lag_pct, 2)}%` }}
            className="bg-blue-500 h-full"
            title={`Driver/Yaw Lag: ${breakdown.transient_lag_pct}%`}
          />
          <div
            style={{ width: `${Math.max(breakdown.compliance_loss_pct, 2)}%` }}
            className="bg-emerald-500 h-full"
            title={`Compliance: ${breakdown.compliance_loss_pct}%`}
          />
          <div
            style={{ width: `${Math.max(breakdown.tire_relaxation_pct, 2)}%` }}
            className="bg-purple-500 h-full"
            title={`Tire Relaxation: ${breakdown.tire_relaxation_pct}%`}
          />
        </div>

        {/* Breakdown Items Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
          <div className="p-2 rounded bg-[#0d0d10] border border-[#1e1e24]">
            <div className="flex items-center gap-1.5 text-[9px] text-amber-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
              Gearshift Torque Cut
            </div>
            <div className="text-sm font-bold font-mono text-white mt-1">
              +{attr.gearshift_loss_s.toFixed(3)} s
            </div>
            <div className="text-[9px] text-zinc-500 font-mono">
              {breakdown.gearshift_loss_pct}% of delta
            </div>
          </div>

          <div className="p-2 rounded bg-[#0d0d10] border border-[#1e1e24]">
            <div className="flex items-center gap-1.5 text-[9px] text-blue-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
              Steer / Yaw Response Lag
            </div>
            <div className="text-sm font-bold font-mono text-white mt-1">
              +{attr.transient_steer_yaw_lag_s.toFixed(3)} s
            </div>
            <div className="text-[9px] text-zinc-500 font-mono">
              {breakdown.transient_lag_pct}% of delta
            </div>
          </div>

          <div className="p-2 rounded bg-[#0d0d10] border border-[#1e1e24]">
            <div className="flex items-center gap-1.5 text-[9px] text-emerald-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
              Suspension Compliance
            </div>
            <div className="text-sm font-bold font-mono text-white mt-1">
              +{attr.compliance_load_transfer_loss_s.toFixed(3)} s
            </div>
            <div className="text-[9px] text-zinc-500 font-mono">
              {breakdown.compliance_loss_pct}% of delta
            </div>
          </div>

          <div className="p-2 rounded bg-[#0d0d10] border border-[#1e1e24]">
            <div className="flex items-center gap-1.5 text-[9px] text-purple-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-purple-500 shrink-0" />
              Tire Relaxation Length
            </div>
            <div className="text-sm font-bold font-mono text-white mt-1">
              +{attr.tire_relaxation_lag_s.toFixed(3)} s
            </div>
            <div className="text-[9px] text-zinc-500 font-mono">
              {breakdown.tire_relaxation_pct}% of delta
            </div>
          </div>
        </div>
      </div>

      {/* Speed Traces Comparison Plot */}
      {qssDistances.length > 0 && dynDistances.length > 0 && (
        <div className="h-[240px] w-full bg-[#0d0d10] rounded-lg border border-[#1f1f25] p-2">
          <Plot
            data={[
              {
                x: qssDistances,
                y: qssSpeedsKmh,
                type: "scatter",
                mode: "lines",
                name: "Fast QSS Speed",
                line: { color: "#f2a900", width: 1.5 },
              },
              {
                x: dynDistances,
                y: dynSpeedsKmh,
                type: "scatter",
                mode: "lines",
                name: "14-DOF Dynamic Speed",
                line: { color: "#3b82f6", width: 1.5 },
              },
            ]}
            layout={{
              ...DARK_BASE,
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              title: { text: "Speed Profile Comparison: Fast QSS vs 14-DOF Dynamic", font: { color: "#888", size: 11 } },
              xaxis: { ...DARK_BASE.xaxis, title: { text: "Track Distance [m]", font: { color: "#666" } } },
              yaxis: { ...DARK_BASE.yaxis, title: { text: "Speed [km/h]", font: { color: "#666" } } },
              legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } },
              margin: { l: 45, r: 20, t: 30, b: 40 },
            } as Record<string, unknown>}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
          />
        </div>
      )}

      {/* Assumptions & Validity Notes */}
      {data.validity_record?.assumptions && (
        <div className="p-2.5 rounded bg-[#0e0e12] border border-[#1b1b22] text-[10px] text-zinc-500 space-y-1">
          <div className="font-bold text-zinc-400 uppercase tracking-wider font-mono">Auditable Engineering Model Assumptions</div>
          <ul className="list-disc list-inside space-y-0.5">
            {data.validity_record.assumptions.map((assump, idx) => (
              <li key={idx}>{assump}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
