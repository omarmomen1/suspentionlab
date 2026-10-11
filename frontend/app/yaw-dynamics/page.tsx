"use client";

import { useState, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import {
  Activity, RefreshCw, AlertCircle, TrendingUp, TrendingDown,
  Gauge, BarChart3, Play, Settings2,
} from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";

import Plot from "../../components/sim/Plot";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const PLOTLY_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor:  "transparent",
  font:  { color: "#666", size: 11, family: "Inter, monospace" },
  xaxis: { color: "#444", gridcolor: "#1a1a1c", zerolinecolor: "#444" },
  yaxis: { color: "#444", gridcolor: "#1a1a1c", zerolinecolor: "#444" },
  margin: { l: 60, r: 20, t: 36, b: 55 },
  autosize: true,
};

// ─── Types ───────────────────────────────────────────────────────────────────

interface StabilityMetrics {
  understeer_gradient_deg_per_g: number;
  neutral_steer_speed_kmh: number | null;
  stability_index: number;
  yaw_natural_freq_hz: number;
  yaw_damping_ratio: number;
  handling_class: "understeer" | "neutral" | "oversteer";
  time_constant_s: number;
}

interface MMMResult {
  beta_deg: number[];
  delta_deg: number[];
  Fy_total_n: number[][];
  Mz_total_nm: number[][];
  understeer_gradient_deg_per_g: number;
  neutral_steer_speed_ms: number;
}

interface TransientResult {
  t: number[];
  beta_deg: number[];
  r_rads: number[];
  Fy_n: number[];
  Mz_nm: number[];
  settled_at_t: number;
  r_steady_state: number;
  delta_steer_deg: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-[#111113] border border-[#252525] rounded-xl p-4 ${className}`}>
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="text-[9px] font-bold text-gray-600 uppercase tracking-[0.16em] mb-3">{children}</div>;
}

function MetricRow({ label, value, unit = "", highlight = false }: {
  label: string; value: string | number; unit?: string; highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-[#1a1a1c] last:border-0">
      <span className="text-[10px] text-gray-500">{label}</span>
      <span className={`text-[12px] font-mono ${highlight ? "text-[#f2a900] font-bold" : "text-white"}`}>
        {value}{unit && <span className="text-gray-600 text-[9px] ml-0.5">{unit}</span>}
      </span>
    </div>
  );
}

function ParamInput({ label, value, onChange, min, max, step = 0.1, unit = "" }: {
  label: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number; unit?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <label className="text-[10px] text-gray-500 flex-1 leading-tight">{label}</label>
      <div className="flex items-center gap-1">
        <input
          type="number" value={value} min={min} max={max} step={step}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          className="w-[72px] bg-[#0d0d0d] border border-[#252525] text-[11px] rounded px-2 py-1
            text-white focus:outline-none focus:border-[#f2a900]/50 text-right font-mono"
        />
        {unit && <span className="text-[9px] text-gray-700 w-9">{unit}</span>}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function YawDynamicsPage() {
  const { fetchWithAuth } = useAuth();

  const [params, setParams] = useState({
    mass:           800.0,
    Iz:             1200.0,
    wheelbase:      2.70,
    cog_dist_front: 1.35,
    C_alpha_front:  120_000.0,
    C_alpha_rear:   140_000.0,
  });

  const [simParams, setSimParams] = useState({
    v_ms:      60.0,
    radius_m:  60.0,
    t_total_s: 3.0,
  });

  const [metrics,   setMetrics]   = useState<StabilityMetrics | null>(null);
  const [mmmResult, setMmmResult] = useState<MMMResult | null>(null);
  const [transient, setTransient] = useState<TransientResult | null>(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  const setP = (key: string) => (v: number) => setParams(prev => ({ ...prev, [key]: v }));

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = { params, v_ms: simParams.v_ms, n_beta: 31, n_delta: 13 };

      const [yawRes, transRes] = await Promise.all([
        fetchWithAuth("/api/v1/intelligence/yaw", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
        fetchWithAuth("/api/v1/intelligence/yaw/transient", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ params, v_ms: simParams.v_ms, radius_m: simParams.radius_m, t_total_s: simParams.t_total_s, dt_s: 0.005 }),
        }),
      ]);

      if (!yawRes.ok)   throw new Error(`Yaw API: ${yawRes.status}`);
      if (!transRes.ok) throw new Error(`Transient API: ${transRes.status}`);

      const yawData   = await yawRes.json();
      const transData = await transRes.json();

      setMetrics(yawData.stability_metrics);
      setMmmResult(yawData.mmm);
      setTransient(transData);
    } catch (e: any) {
      setError(e.message ?? "Request failed");
    } finally {
      setLoading(false);
    }
  }, [params, simParams, fetchWithAuth]);

  // ── MMM chart data ────────────────────────────────────────────────────────
  const mmmData = mmmResult
    ? mmmResult.delta_deg.map((delta, j) => ({
        type:  "scatter" as const,
        mode:  "lines" as const,
        name:  `δ=${delta.toFixed(1)}°`,
        x:     mmmResult.Fy_total_n.map(row => row[j]),
        y:     mmmResult.Mz_total_nm.map(row => row[j]),
        line:  {
          color: j === Math.floor(mmmResult.delta_deg.length / 2)
            ? "#f2a900"
            : `hsl(${200 + j * 25}, 60%, 55%)`,
          width: j === Math.floor(mmmResult.delta_deg.length / 2) ? 2.5 : 1.5,
        },
      }))
    : [];

  // Stability lines (constant beta)
  const stabilityLines = mmmResult
    ? mmmResult.beta_deg
        .filter((_, i) => i % 4 === 0)
        .map((beta, i) => ({
          type:      "scatter" as const,
          mode:      "lines" as const,
          name:      `β=${beta.toFixed(0)}°`,
          x:         mmmResult.Fy_total_n[i * 4],
          y:         mmmResult.Mz_total_nm[i * 4],
          line:      { color: "#555", width: 1, dash: "dot" as const },
          showlegend: false,
        }))
    : [];

  // ── Transient chart data ──────────────────────────────────────────────────
  const transientData = transient
    ? [
        {
          type: "scatter" as const, mode: "lines" as const, name: "Sideslip β [deg]",
          x: transient.t, y: transient.beta_deg,
          line: { color: "#f2a900", width: 2 }, yaxis: "y",
        },
        {
          type: "scatter" as const, mode: "lines" as const, name: "Yaw rate r [deg/s]",
          x: transient.t, y: transient.r_rads.map(r => r * 180 / Math.PI),
          line: { color: "#3b82f6", width: 2 }, yaxis: "y2",
        },
      ]
    : [];

  const handleClass = metrics?.handling_class;
  const handleColor = handleClass === "understeer"
    ? "text-red-400"
    : handleClass === "oversteer"
      ? "text-blue-400"
      : "text-emerald-400";

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-white px-4 py-6">
      <div className="max-w-[1600px] mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-bold text-white flex items-center gap-2">
              <Activity size={18} className="text-[#f2a900]" />
              Yaw Dynamics / MMM
            </h1>
            <p className="text-[11px] text-gray-500 mt-0.5">
              Milliken Moment Method diagram + 2-DOF transient bicycle model
            </p>
          </div>
          <div className="flex items-center gap-3">
            {error && (
              <span className="text-[10px] text-red-400 flex items-center gap-1">
                <AlertCircle size={11} /> {error}
              </span>
            )}
            <button
              onClick={runAnalysis}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-[#f2a900] hover:bg-[#f2a900]/80 disabled:opacity-50
                text-black text-xs font-bold rounded-lg transition-colors"
            >
              {loading ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
              Compute MMM
            </button>
          </div>
        </div>

        <div className="grid grid-cols-[280px_1fr] gap-4">

          {/* ── Left panel ─────────────────────────────────────────────── */}
          <div className="space-y-4">
            <Card>
              <SectionTitle>Vehicle Parameters</SectionTitle>
              <div className="space-y-2.5">
                <ParamInput label="Mass"            value={params.mass}           onChange={setP("mass")}           unit="kg"    step={10} />
                <ParamInput label="Yaw inertia Iz"  value={params.Iz}             onChange={setP("Iz")}             unit="kg·m²" step={50} />
                <ParamInput label="Wheelbase"       value={params.wheelbase}      onChange={setP("wheelbase")}      unit="m"     step={0.05} />
                <ParamInput label="CoG to front"    value={params.cog_dist_front} onChange={setP("cog_dist_front")} unit="m"     step={0.05} />
                <ParamInput label="Cα front (axle)" value={params.C_alpha_front / 1000}
                  onChange={v => setP("C_alpha_front")(v * 1000)} unit="kN/rad" step={5} />
                <ParamInput label="Cα rear (axle)"  value={params.C_alpha_rear / 1000}
                  onChange={v => setP("C_alpha_rear")(v * 1000)} unit="kN/rad" step={5} />
              </div>
            </Card>

            <Card>
              <SectionTitle>Simulation Parameters</SectionTitle>
              <div className="space-y-2.5">
                <ParamInput label="Analysis speed"  value={simParams.v_ms * 3.6}
                  onChange={v => setSimParams(p => ({ ...p, v_ms: v / 3.6 }))} unit="km/h" step={5} />
                <ParamInput label="Corner radius"   value={simParams.radius_m}
                  onChange={v => setSimParams(p => ({ ...p, radius_m: v }))} unit="m" step={5} />
                <ParamInput label="Transient time"  value={simParams.t_total_s}
                  onChange={v => setSimParams(p => ({ ...p, t_total_s: v }))} unit="s" step={0.5} />
              </div>
            </Card>

            {/* Stability Metrics */}
            {metrics && (
              <Card>
                <SectionTitle>Stability Metrics</SectionTitle>
                <div className="mb-3">
                  <div className={`text-sm font-bold capitalize ${handleColor}`}>
                    {metrics.handling_class}
                  </div>
                  <div className="text-[9px] text-gray-600 mt-0.5">
                    at {simParams.v_ms.toFixed(0)} m/s
                  </div>
                </div>
                <div className="space-y-0">
                  <MetricRow label="Understeer gradient"
                    value={metrics.understeer_gradient_deg_per_g.toFixed(2)} unit=" deg/g"
                    highlight={Math.abs(metrics.understeer_gradient_deg_per_g) > 2} />
                  <MetricRow label="Neutral steer speed"
                    value={metrics.neutral_steer_speed_kmh !== null
                      ? metrics.neutral_steer_speed_kmh.toFixed(0) : "∞"} unit=" km/h" />
                  <MetricRow label="Yaw natural freq"
                    value={metrics.yaw_natural_freq_hz.toFixed(2)} unit=" Hz" />
                  <MetricRow label="Yaw damping ratio"
                    value={metrics.yaw_damping_ratio.toFixed(3)}
                    highlight={metrics.yaw_damping_ratio < 0.3} />
                  <MetricRow label="Time constant τ"
                    value={metrics.time_constant_s.toFixed(3)} unit=" s" />
                </div>
              </Card>
            )}

            {/* Transient info */}
            {transient && (
              <Card>
                <SectionTitle>Transient Response</SectionTitle>
                <div className="space-y-0">
                  <MetricRow label="Required steer δ"
                    value={transient.delta_steer_deg.toFixed(2)} unit=" °" />
                  <MetricRow label="Steady-state r"
                    value={(transient.r_steady_state * 180 / Math.PI).toFixed(2)} unit=" °/s" />
                  <MetricRow label="Settled at t"
                    value={transient.settled_at_t.toFixed(2)} unit=" s"
                    highlight={transient.settled_at_t > 1.0} />
                </div>
              </Card>
            )}
          </div>

          {/* ── Right panel: charts ─────────────────────────────────────── */}
          <div className="space-y-4">

            {/* MMM diagram */}
            <Card>
              <SectionTitle>
                Milliken Moment Method Diagram — {simParams.v_ms.toFixed(0)} m/s ({(simParams.v_ms*3.6).toFixed(0)} km/h)
              </SectionTitle>
              {mmmData.length > 0 ? (
                <Plot
                  data={[...mmmData, ...stabilityLines]}
                  layout={{
                    ...PLOTLY_BASE,
                    height: 340,
                    xaxis: {
                      ...PLOTLY_BASE.xaxis,
                      title: { text: "Total Lateral Force Fy [N]", font: { size: 10, color: "#555" } },
                    },
                    yaxis: {
                      ...PLOTLY_BASE.yaxis,
                      title: { text: "Total Yaw Moment Mz [N·m]", font: { size: 10, color: "#555" } },
                    },
                    legend: { font: { color: "#666", size: 9 }, x: 1.0, y: 1.0 },
                    shapes: [
                      // Zero yaw moment line
                      { type: "line" as const, x0: -1, x1: 1, y0: 0, y1: 0,
                        xref: "paper" as const, yref: "y",
                        line: { color: "#333", width: 1, dash: "dash" as const } },
                    ],
                  }}
                  config={{ displayModeBar: false }}
                  style={{ width: "100%", height: 340 }}
                />
              ) : (
                <div className="h-80 flex flex-col items-center justify-center gap-2 text-gray-600">
                  <BarChart3 size={24} />
                  <span className="text-[11px]">Click &quot;Compute MMM&quot; to run analysis</span>
                </div>
              )}
            </Card>

            {/* Transient response */}
            <Card>
              <SectionTitle>
                Transient Yaw Response — R={simParams.radius_m.toFixed(0)}m at {(simParams.v_ms*3.6).toFixed(0)} km/h
              </SectionTitle>
              {transientData.length > 0 ? (
                <Plot
                  data={transientData}
                  layout={{
                    ...PLOTLY_BASE,
                    height: 260,
                    xaxis: {
                      ...PLOTLY_BASE.xaxis,
                      title: { text: "Time [s]", font: { size: 10, color: "#555" } },
                    },
                    yaxis: {
                      ...PLOTLY_BASE.yaxis,
                      title: { text: "Sideslip β [deg]", font: { size: 10, color: "#f2a900" } },
                    },
                    yaxis2: {
                      title: { text: "Yaw rate [deg/s]", font: { size: 10, color: "#3b82f6" } },
                      overlaying: "y" as const,
                      side: "right" as const,
                      color: "#444",
                      gridcolor: "#1a1a1c",
                    },
                    legend: { font: { color: "#888", size: 10 } },
                    shapes: transient ? [
                      {
                        type: "line" as const,
                        x0: transient.settled_at_t, x1: transient.settled_at_t,
                        y0: 0, y1: 1, yref: "paper" as const, xref: "x" as const,
                        line: { color: "#22c55e", width: 1, dash: "dot" as const },
                      },
                    ] : [],
                    annotations: transient && transient.settled_at_t < simParams.t_total_s * 0.95 ? [
                      {
                        x: transient.settled_at_t, y: 0.95, yref: "paper" as const,
                        text: `Settled t=${transient.settled_at_t.toFixed(2)}s`,
                        font: { color: "#22c55e", size: 9 },
                        showarrow: false,
                        xanchor: "left" as const,
                      },
                    ] : [],
                  }}
                  config={{ displayModeBar: false }}
                  style={{ width: "100%", height: 260 }}
                />
              ) : (
                <div className="h-60 flex items-center justify-center text-gray-600 text-[11px]">
                  Run analysis to see transient response
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

