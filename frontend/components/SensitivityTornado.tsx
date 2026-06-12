"use client";

import React, { useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { Zap, RefreshCw, AlertTriangle, TrendingUp, Activity } from "lucide-react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SensitivityResult {
  base_kpis: Record<string, number>;
  kpi_labels: Record<string, string>;
  sensitivities: Array<{
    param_key: string;
    param_label: string;
    sensitivity: Record<string, number>;
    magnitude: number;
  }>;
  perturbation_pct: number;
  n_simulations: number;
}

interface Props {
  payload: object;  // The same SimulateRequest payload used for the main sim
  authHeader: () => Record<string, string>;
}

const DARK_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#666", size: 11, family: "Inter, monospace" },
  margin: { l: 200, r: 60, t: 40, b: 60 },
  autosize: true,
  hoverlabel: { bgcolor: "#0d0d0f", bordercolor: "#333", font: { color: "#ccc", size: 11 } },
};

// Color scale: negative sensitivity (red) → zero (grey) → positive (gold)
function sensitivityColor(v: number): string {
  if (v > 0.5)  return "#ff2d55";
  if (v > 0.1)  return "#ff9f0a";
  if (v < -0.5) return "#34d399";
  if (v < -0.1) return "#00aeff";
  return "#555";
}

const KPI_COLORS: Record<string, string> = {
  rms_body_accel_wk:     "#ff2d55",
  rms_susp_travel:       "#bf5af2",
  peak_transmissibility: "#f2a900",
  rms_tire_load:         "#00aeff",
};

export default function SensitivityTornado({ payload, authHeader }: Props) {
  const [data, setData]       = useState<SensitivityResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [activeKpi, setActiveKpi] = useState("rms_body_accel_wk");

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await fetch(`${API_BASE}/sensitivity`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "Sensitivity analysis failed");
      }
      setData(await res.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [payload, authHeader]);

  const buildTornadoTraces = () => {
    if (!data) return [];
    const labels = data.sensitivities.map((s) => s.param_label);
    const values = data.sensitivities.map((s) => s.sensitivity[activeKpi] ?? 0);
    const colors = values.map((v) => sensitivityColor(v));

    return [{
      type: "bar" as const,
      orientation: "h" as const,
      y: labels,
      x: values,
      marker: { color: colors, line: { color: "rgba(255,255,255,0.05)", width: 1 } },
      hovertemplate:
        "<b>%{y}</b><br>Sensitivity: %{x:.3f}<br>" +
        `(${data.perturbation_pct}% perturbation)<extra></extra>`,
      name: data.kpi_labels[activeKpi] ?? activeKpi,
    }];
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <p className="text-[9px] font-bold tracking-[0.2em] text-ansys-yellow uppercase">
            Revolutionary Feature
          </p>
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Activity size={14} className="text-ansys-yellow" />
            Parametric Sensitivity Analysis
          </h2>
          <p className="text-[10px] text-gray-600 mt-0.5">
            Normalized finite-difference sensitivities of each KPI to ±{data?.perturbation_pct ?? 10}% parameter perturbation.
            Higher bars = stronger influence on the selected KPI.
          </p>
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-ansys-yellow text-black text-xs font-bold rounded-lg
            hover:brightness-110 transition-all shadow-[0_0_16px_rgba(242,169,0,0.2)]
            disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
        >
          {loading ? (
            <><div className="w-3 h-3 border border-black border-t-transparent rounded-full animate-spin" />
            Running {data?.n_simulations ?? 13} simulations…</>
          ) : (
            <><Zap size={13} /> Run Sensitivity</>
          )}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 bg-red-950/30 border border-red-800/40 rounded-xl text-red-400 text-xs">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Empty state */}
      {!data && !loading && !error && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center">
          <div className="w-16 h-16 rounded-2xl bg-ansys-yellow/5 border border-ansys-yellow/10 flex items-center justify-center">
            <TrendingUp size={32} strokeWidth={1} className="text-ansys-yellow/40" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-400 mb-1">Sensitivity Analysis</p>
            <p className="text-xs text-gray-700 max-w-xs">
              Runs <strong className="text-gray-500">13 parallel simulations</strong> at ±10% perturbation for each of 6
              physical parameters. Identifies which parameters dominate ride quality, suspension travel, and tire grip.
            </p>
          </div>
        </div>
      )}

      {/* Loading pulse */}
      {loading && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <div className="w-10 h-10 border-2 border-ansys-yellow/20 border-t-ansys-yellow rounded-full animate-spin" />
          <p className="text-xs text-gray-500">
            Running {data?.n_simulations ?? 13} BDF simulations concurrently…
          </p>
          <div className="grid grid-cols-3 gap-2 mt-2">
            {["m_s ±10%", "m_u ±10%", "k_s ±10%", "c ±10%", "k_t ±10%", "MR ±10%"].map((l) => (
              <div key={l} className="text-[10px] text-gray-700 bg-[#141416] border border-[#252525] px-2 py-1 rounded-lg animate-pulse">
                {l}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {data && !loading && (
        <div className="flex flex-col gap-3 flex-1 overflow-hidden">
          {/* KPI selector */}
          <div className="flex gap-2 flex-wrap shrink-0">
            {Object.entries(data.kpi_labels).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setActiveKpi(key)}
                style={activeKpi === key ? { borderColor: KPI_COLORS[key], color: KPI_COLORS[key] } : {}}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                  activeKpi === key
                    ? "bg-[#141416]"
                    : "bg-[#111113] border-[#1e1e1e] text-gray-500 hover:text-gray-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Tornado chart */}
          <div className="flex-1 min-h-0 relative">
            <Plot
              data={buildTornadoTraces()}
              layout={{
                ...DARK_BASE,
                title: {
                  text: `Sensitivity of <b>${data.kpi_labels[activeKpi]}</b> to ±${data.perturbation_pct}% Perturbation`,
                  font: { color: "#888", size: 12 },
                },
                xaxis: {
                  color: "#444",
                  gridcolor: "#161618",
                  zerolinecolor: "#2a2a2a",
                  title: { text: "Normalized Sensitivity  d(KPI)/d(param) × param/KPI", font: { color: "#444", size: 10 } },
                  tickfont: { color: "#555", size: 10 },
                },
                yaxis: {
                  color: "#444",
                  gridcolor: "#161618",
                  tickfont: { color: "#aaa", size: 11 },
                  autorange: "reversed" as const,
                },
                shapes: [
                  { type: "line" as const, x0: 0, x1: 0, y0: -0.5, y1: data.sensitivities.length - 0.5,
                    line: { color: "#333", width: 1.5, dash: "dot" } },
                ],
                annotations: [
                  { x: 0.5, xref: "paper" as const, y: -0.12, yref: "paper" as const,
                    text: `▶ Positive: increasing param increases KPI &nbsp; ◀ Negative: increasing param reduces KPI`,
                    showarrow: false, font: { color: "#555", size: 9 }, xanchor: "center" as const },
                ],
              }}
              useResizeHandler
              style={{ width: "100%", height: "100%" }}
              config={{ responsive: true, displayModeBar: true }}
            />
          </div>

          {/* Base KPI table */}
          <div className="shrink-0 grid grid-cols-4 gap-2">
            {Object.entries(data.base_kpis).map(([key, val]) => (
              <div key={key} className="bg-[#141416] border border-[#252525] rounded-xl p-2 flex flex-col gap-0.5">
                <span className="text-[9px] font-bold tracking-widest text-gray-700 uppercase truncate">
                  {data.kpi_labels[key] ?? key}
                </span>
                <span className="text-sm font-bold font-mono" style={{ color: KPI_COLORS[key] ?? "#fff" }}>
                  {val.toFixed(3)}
                </span>
                <span className="text-[9px] text-gray-700">Baseline</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
