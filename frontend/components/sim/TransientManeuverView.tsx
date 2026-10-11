"use client";

import React from "react";
import { ShieldCheck, Activity, Gauge, Disc, Compass, Zap } from "lucide-react";
import Plot from "./Plot";
import { DARK_BASE } from "./theme";

export interface ManeuverTelemetry {
  times: number[];
  speeds_kmh: number[];
  speeds_ms?: number[];
  steering_deg: number[];
  yaw_rates: number[];
  lateral_g: number[];
  longitudinal_g: number[];
  roll_deg: number[];
  pitch_deg: number[];
  wheel_load_fl_n: number[];
  wheel_load_fr_n: number[];
  wheel_load_rl_n: number[];
  wheel_load_rr_n: number[];
}

export interface ManeuverResultData {
  maneuver_type: string;
  duration_s: number;
  metrics: Record<string, any>;
  telemetry: ManeuverTelemetry;
  validity_record?: {
    status: string;
    model: string;
    assumptions?: string[];
  };
}

interface TransientManeuverViewProps {
  result: ManeuverResultData | null;
}

export default function TransientManeuverView({ result }: TransientManeuverViewProps) {
  if (!result || !result.telemetry) {
    return (
      <div className="p-8 text-center text-gray-500 text-xs bg-[#0d0d0f] border border-[#1f1f23] rounded-xl">
        Select a maneuver type, configure handling parameters, and run transient simulation to view ISO vehicle dynamics responses.
      </div>
    );
  }

  const tel = result.telemetry;
  const m = result.metrics || {};
  const mtype = result.maneuver_type.toUpperCase();

  return (
    <div className="w-full bg-[#0a0a0c] border border-[#1f1f23] rounded-xl p-4 flex flex-col space-y-4">
      {/* Top Banner: Key Handling Metrics */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-[#141418] border border-[#222228]">
        <div>
          <div className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
            Handling Test: {mtype.replace(/_/g, " ")}
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xl font-bold font-mono text-[#f2a900]">
              {result.duration_s.toFixed(2)} s
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-[#1e1e26] text-zinc-300 border border-[#333340]">
              ISO 14-DOF Dynamic
            </span>
          </div>
        </div>

        {result.validity_record && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-950/40 border border-emerald-800/40 text-emerald-400 text-[10px] font-mono">
            <ShieldCheck size={13} />
            <span>{result.validity_record.status}</span>
          </div>
        )}
      </div>

      {/* Dynamic Metric Cards based on Maneuver */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        {mtype === "STEP_STEER" && (
          <>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Steady-State Yaw Rate</div>
              <div className="text-lg font-bold font-mono text-white mt-0.5">
                {(m.steady_state_yaw_rate_rads ?? 0).toFixed(3)} rad/s
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Peak Yaw Rate</div>
              <div className="text-lg font-bold font-mono text-amber-400 mt-0.5">
                {(m.peak_yaw_rate_rads ?? 0).toFixed(3)} rad/s
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Yaw Rate Overshoot</div>
              <div className="text-lg font-bold font-mono text-rose-400 mt-0.5">
                {(m.yaw_rate_overshoot_pct ?? 0).toFixed(1)} %
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Roll Gain</div>
              <div className="text-lg font-bold font-mono text-blue-400 mt-0.5">
                {(m.roll_gain_deg_per_g ?? 0).toFixed(2)} deg/g
              </div>
            </div>
          </>
        )}

        {mtype === "THRESHOLD_BRAKING" && (
          <>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Stopping Distance</div>
              <div className="text-lg font-bold font-mono text-emerald-400 mt-0.5">
                {(m.stopping_distance_m ?? 0).toFixed(1)} m
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Mean Deceleration</div>
              <div className="text-lg font-bold font-mono text-white mt-0.5">
                {(m.mean_decel_g ?? 0).toFixed(2)} g
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Peak Deceleration</div>
              <div className="text-lg font-bold font-mono text-amber-400 mt-0.5">
                {(m.peak_decel_g ?? 0).toFixed(2)} g
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Pitch / Nose Dive</div>
              <div className="text-lg font-bold font-mono text-rose-400 mt-0.5">
                {(m.peak_nose_dive_deg ?? 0).toFixed(2)} deg
              </div>
            </div>
          </>
        )}

        {mtype !== "STEP_STEER" && mtype !== "THRESHOLD_BRAKING" && (
          <>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Peak Lateral Accel</div>
              <div className="text-lg font-bold font-mono text-amber-400 mt-0.5">
                {(m.peak_lateral_g ?? m.max_lateral_g ?? 0).toFixed(2)} g
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Peak Yaw Rate</div>
              <div className="text-lg font-bold font-mono text-white mt-0.5">
                {(m.peak_yaw_rate_rads ?? 0).toFixed(3)} rad/s
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Understeer Gradient</div>
              <div className="text-lg font-bold font-mono text-blue-400 mt-0.5">
                {(m.understeer_gradient_deg_g ?? 0).toFixed(2)} deg/g
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#111115] border border-[#1e1e24]">
              <div className="text-[9px] text-zinc-500 uppercase tracking-wider font-mono">Peak Roll Angle</div>
              <div className="text-lg font-bold font-mono text-purple-400 mt-0.5">
                {(m.peak_roll_deg ?? 0).toFixed(2)} deg
              </div>
            </div>
          </>
        )}
      </div>

      {/* Time-Domain Plots Grid (2x2) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 min-h-[480px]">
        {/* Plot 1: Steering Angle & Yaw Rate */}
        <div className="h-[240px] bg-[#0d0d10] border border-[#1e1e24] rounded-lg p-2">
          <Plot
            data={[
              {
                x: tel.times,
                y: tel.steering_deg,
                type: "scatter",
                mode: "lines",
                name: "Steering [deg]",
                line: { color: "#f2a900", width: 1.5 },
                yaxis: "y",
              },
              {
                x: tel.times,
                y: tel.yaw_rates,
                type: "scatter",
                mode: "lines",
                name: "Yaw Rate [rad/s]",
                line: { color: "#3b82f6", width: 1.5 },
                yaxis: "y2",
              },
            ]}
            layout={{
              ...DARK_BASE,
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              title: { text: "Steering Demand & Yaw Response", font: { color: "#888", size: 11 } },
              xaxis: { ...DARK_BASE.xaxis, title: { text: "Time [s]", font: { color: "#666" } } },
              yaxis: { ...DARK_BASE.yaxis, title: { text: "Steer [deg]", font: { color: "#f2a900" } } },
              yaxis2: {
                title: { text: "Yaw Rate [rad/s]", font: { color: "#3b82f6" } },
                overlaying: "y",
                side: "right",
                gridcolor: "transparent",
              },
              legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } },
              margin: { l: 45, r: 45, t: 30, b: 35 },
            } as Record<string, unknown>}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
          />
        </div>

        {/* Plot 2: Accelerations (ay & ax) */}
        <div className="h-[240px] bg-[#0d0d10] border border-[#1e1e24] rounded-lg p-2">
          <Plot
            data={[
              {
                x: tel.times,
                y: tel.lateral_g,
                type: "scatter",
                mode: "lines",
                name: "Lateral Accel (ay)",
                line: { color: "#ef4444", width: 1.5 },
              },
              {
                x: tel.times,
                y: tel.longitudinal_g,
                type: "scatter",
                mode: "lines",
                name: "Longitudinal Accel (ax)",
                line: { color: "#10b981", width: 1.5 },
              },
            ]}
            layout={{
              ...DARK_BASE,
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              title: { text: "Vehicle Accelerations [g]", font: { color: "#888", size: 11 } },
              xaxis: { ...DARK_BASE.xaxis, title: { text: "Time [s]", font: { color: "#666" } } },
              yaxis: { ...DARK_BASE.yaxis, title: { text: "Accel [g]", font: { color: "#666" } } },
              legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } },
              margin: { l: 45, r: 20, t: 30, b: 35 },
            } as Record<string, unknown>}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
          />
        </div>

        {/* Plot 3: Body Attitude (Roll & Pitch) */}
        <div className="h-[240px] bg-[#0d0d10] border border-[#1e1e24] rounded-lg p-2">
          <Plot
            data={[
              {
                x: tel.times,
                y: tel.roll_deg,
                type: "scatter",
                mode: "lines",
                name: "Roll Angle [deg]",
                line: { color: "#a855f7", width: 1.5 },
              },
              {
                x: tel.times,
                y: tel.pitch_deg,
                type: "scatter",
                mode: "lines",
                name: "Pitch Angle [deg]",
                line: { color: "#06b6d4", width: 1.5 },
              },
            ]}
            layout={{
              ...DARK_BASE,
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              title: { text: "Chassis Body Attitude Dynamics", font: { color: "#888", size: 11 } },
              xaxis: { ...DARK_BASE.xaxis, title: { text: "Time [s]", font: { color: "#666" } } },
              yaxis: { ...DARK_BASE.yaxis, title: { text: "Angle [deg]", font: { color: "#666" } } },
              legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } },
              margin: { l: 45, r: 20, t: 30, b: 35 },
            } as Record<string, unknown>}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
          />
        </div>

        {/* Plot 4: 4-Wheel Dynamic Normal Loads */}
        <div className="h-[240px] bg-[#0d0d10] border border-[#1e1e24] rounded-lg p-2">
          <Plot
            data={[
              { x: tel.times, y: tel.wheel_load_fl_n, type: "scatter", mode: "lines", name: "FL", line: { color: "#3b82f6", width: 1.2 } },
              { x: tel.times, y: tel.wheel_load_fr_n, type: "scatter", mode: "lines", name: "FR", line: { color: "#f2a900", width: 1.2 } },
              { x: tel.times, y: tel.wheel_load_rl_n, type: "scatter", mode: "lines", name: "RL", line: { color: "#22c55e", width: 1.2 } },
              { x: tel.times, y: tel.wheel_load_rr_n, type: "scatter", mode: "lines", name: "RR", line: { color: "#ef4444", width: 1.2 } },
            ]}
            layout={{
              ...DARK_BASE,
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              title: { text: "Dynamic Wheel Normal Loads [N]", font: { color: "#888", size: 11 } },
              xaxis: { ...DARK_BASE.xaxis, title: { text: "Time [s]", font: { color: "#666" } } },
              yaxis: { ...DARK_BASE.yaxis, title: { text: "Load [N]", font: { color: "#666" } } },
              legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } },
              margin: { l: 45, r: 20, t: 30, b: 35 },
            } as Record<string, unknown>}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
          />
        </div>
      </div>
    </div>
  );
}
