"use client";

import React, { useState, useCallback } from "react";
import { Zap, AlertTriangle, TrendingUp, Activity } from "lucide-react";
import Plot from "./sim/Plot";
import { apiFetch } from "../lib/api";

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
  const [showTable, setShowTable] = useState(false);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await apiFetch("/api/v1/sensitivity", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
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
    <div
      role="region"
      aria-label="Parametric Sensitivity Analysis"
      className="flex flex-col gap-4 h-full"
    >
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <p className="text-[9px] font-bold tracking-[0.2em] text-ansys-yellow uppercase">
            Parametric Sensitivity
          </p>
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Activity size={14} className="text-ansys-yellow" />
            Sensitivity Analysis
          </h2>
          <p className="text-[10px] text-gray-400 mt-0.5">
            Normalized finite-difference sensitivities of each KPI to ±{data?.perturbation_pct ?? 10}% parameter perturbation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <button
              type="button"
              onClick={() => setShowTable(!showTable)}
              aria-expanded={showTable}
              className="px-3 py-1.5 rounded-lg bg-[#141416] border border-[#252525] text-xs font-semibold text-gray-300 hover:text-white transition-colors"
            >
              {showTable ? "Chart View" : "Data Table"}
            </button>
          )}
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
      </div>

      {/* Error */}
      {error && (
        <div role="alert" aria-live="assertive" className="flex items-center gap-2 px-4 py-3 bg-red-950/30 border border-red-800/40 rounded-xl text-red-400 text-xs">
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
            <p className="text-xs text-gray-400 max-w-xs">
              Runs <strong className="text-gray-300">13 parallel simulations</strong> at ±10% perturbation for each of 6
              physical parameters. Identifies which parameters dominate ride quality, suspension travel, and tire grip.
            </p>
          </div>
        </div>
      )}

      {/* Loading pulse */}
      {loading && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4" role="status" aria-live="polite">
          <div className="w-10 h-10 border-2 border-ansys-yellow/20 border-t-ansys-yellow rounded-full animate-spin" />
          <p className="text-xs text-gray-400">
            Running {data?.n_simulations ?? 13} BDF simulations concurrently…
          </p>
        </div>
      )}

      {/* Results */}
      {data && !loading && (
        <div className="flex flex-col gap-4">
          {/* Controls & Baseline Bar: KPI Selector + Baseline KPIs */}
          <div className="flex flex-col gap-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-[#0d0d0f] border border-[#1e1e1e] rounded-xl p-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Target KPI:</span>
                {/* KPI selector */}
                <div className="flex gap-2 flex-wrap" role="tablist" aria-label="KPI sensitivity targets">
                  {Object.entries(data.kpi_labels).map(([key, label]) => (
                    <button
                      key={key}
                      role="tab"
                      aria-selected={activeKpi === key}
                      onClick={() => setActiveKpi(key)}
                      style={activeKpi === key ? { borderColor: KPI_COLORS[key], color: KPI_COLORS[key] } : {}}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                        activeKpi === key
                          ? "bg-[#18181c] shadow-[0_0_10px_rgba(255,255,255,0.05)]"
                          : "bg-[#111113] border-[#1e1e1e] text-gray-400 hover:text-gray-200"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <span className="text-[10px] text-gray-500 font-mono">
                ±{data.perturbation_pct}% Perturbation · {data.n_simulations} Runs
              </span>
            </div>

            {/* Base KPI Overview Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {Object.entries(data.base_kpis).map(([key, val]) => {
                const isSelected = activeKpi === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setActiveKpi(key)}
                    className={`text-left rounded-xl p-3 flex flex-col gap-1 transition-all border ${
                      isSelected
                        ? "bg-[#161619] border-ansys-yellow/50 shadow-[0_0_12px_rgba(242,169,0,0.12)]"
                        : "bg-[#111113] border-[#1e1e1e] hover:border-[#2d2d32]"
                    }`}
                  >
                    <div className="flex items-center justify-between w-full">
                      <span className="text-[10px] font-bold tracking-wider text-gray-400 uppercase truncate">
                        {data.kpi_labels[key] ?? key}
                      </span>
                      <span className="text-[9px] text-gray-500 font-mono">Baseline</span>
                    </div>
                    <span className="text-base font-bold font-mono" style={{ color: KPI_COLORS[key] ?? "#fff" }}>
                      {val.toFixed(3)}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Table or Chart View */}
          {showTable ? (
            <div className="bg-[#0d0d0f] border border-[#1e1e1e] rounded-xl p-4 overflow-x-auto">
              <h3 className="text-xs font-bold text-white mb-3">
                Sensitivity Ranking for {data.kpi_labels[activeKpi]} (±{data.perturbation_pct}% Perturbation)
              </h3>
              <table className="w-full text-left text-xs font-mono border-collapse">
                <thead>
                  <tr className="border-b border-[#252525] text-gray-400">
                    <th className="py-2 px-3">Parameter</th>
                    <th className="py-2 px-3 text-right">Sensitivity d(KPI)/d(param)</th>
                    <th className="py-2 px-3 text-right">Physical Direction</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sensitivities.map((s) => {
                    const val = s.sensitivity[activeKpi] ?? 0;
                    return (
                      <tr key={s.param_key} className="border-b border-[#18181a] text-gray-300">
                        <td className="py-2 px-3 font-semibold text-white">{s.param_label}</td>
                        <td className="py-2 px-3 text-right font-bold" style={{ color: sensitivityColor(val) }}>
                          {val.toFixed(4)}
                        </td>
                        <td className="py-2 px-3 text-right text-[11px] text-gray-400">
                          {val > 0 ? "Increasing param increases KPI" : "Increasing param reduces KPI"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="w-full bg-[#0d0d0f] border border-[#1e1e1e] rounded-xl p-3 min-h-[460px] h-[480px]">
              <Plot
                data={buildTornadoTraces()}
                layout={{
                  ...DARK_BASE,
                  autosize: true,
                  height: 450,
                  margin: { l: 190, r: 40, t: 40, b: 50 },
                  title: {
                    text: `Sensitivity of <b>${data.kpi_labels[activeKpi]}</b> to ±${data.perturbation_pct}% Perturbation`,
                    font: { color: "#9ca3af", size: 12 },
                  },
                  xaxis: {
                    color: "#888888",
                    gridcolor: "#161618",
                    zerolinecolor: "#3f3f46",
                    title: { text: "Normalized Sensitivity  d(KPI)/d(param) × param/KPI", font: { color: "#9ca3af", size: 10 } },
                    tickfont: { color: "#9ca3af", size: 10 },
                  },
                  yaxis: {
                    color: "#888888",
                    gridcolor: "#161618",
                    tickfont: { color: "#d1d5db", size: 11 },
                    autorange: "reversed" as const,
                  },
                  shapes: [
                    { type: "line" as const, x0: 0, x1: 0, y0: -0.5, y1: data.sensitivities.length - 0.5,
                      line: { color: "#333", width: 1.5, dash: "dot" } },
                  ],
                }}
                useResizeHandler
                style={{ width: "100%", height: "100%" }}
                config={{ responsive: true, displayModeBar: true }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
