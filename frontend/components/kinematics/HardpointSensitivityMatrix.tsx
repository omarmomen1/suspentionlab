"use client";

import React, { useState, useMemo } from "react";
import { HardpointSensitivityMatrixResponse } from "../../lib/api_client";
import {
  Activity,
  Sliders,
  Filter,
  Info,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Layers,
  HelpCircle,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";

interface HardpointSensitivityMatrixProps {
  data: HardpointSensitivityMatrixResponse | null;
  loading: boolean;
  stepSizeMm: number;
  onChangeStepSize: (val: number) => void;
  onRecompute: () => void;
  onSelectCandidate?: (hardpoint: string, axis: string) => void;
}

// Friendly names and exact mathematical derivative symbols for kinematic sensitivities
const METRIC_DISPLAY_INFO: Record<
  string,
  { label: string; group: string; derivativeSymbol: string; kinematicSymbol: string }
> = {
  camber_static_deg: {
    label: "Static Camber",
    group: "Camber & Toe",
    derivativeSymbol: "∂γ₀/∂p",
    kinematicSymbol: "γ₀",
  },
  camber_bump_deg: {
    label: "Bump Peak Camber",
    group: "Camber & Toe",
    derivativeSymbol: "∂γ_bump/∂p",
    kinematicSymbol: "γ_bump",
  },
  camber_gain_deg_per_100mm: {
    label: "Camber Gain Rate",
    group: "Camber & Toe",
    derivativeSymbol: "∂(dγ/dz)/∂p",
    kinematicSymbol: "dγ/dz",
  },
  toe_static_deg: {
    label: "Static Toe",
    group: "Camber & Toe",
    derivativeSymbol: "∂toe₀/∂p",
    kinematicSymbol: "toe₀",
  },
  toe_variation_deg: {
    label: "Bump Steer Range",
    group: "Camber & Toe",
    derivativeSymbol: "∂(Δtoe)/∂p",
    kinematicSymbol: "Δtoe",
  },
  toe_gain_deg_per_100mm: {
    label: "Bump Steer Rate",
    group: "Camber & Toe",
    derivativeSymbol: "∂(d(toe)/dz)/∂p",
    kinematicSymbol: "d(toe)/dz",
  },
  roll_center_height_static_mm: {
    label: "Static Roll Center Z",
    group: "Roll Center",
    derivativeSymbol: "∂RC_z/∂p",
    kinematicSymbol: "RC_z,₀",
  },
  rc_migration_range_mm: {
    label: "RC Migration Range",
    group: "Roll Center",
    derivativeSymbol: "∂(ΔRC_z)/∂p",
    kinematicSymbol: "ΔRC_z",
  },
  rc_migration_rate: {
    label: "RC Migration Rate",
    group: "Roll Center",
    derivativeSymbol: "∂(d(RC_z)/dz)/∂p",
    kinematicSymbol: "d(RC_z)/dz",
  },
  motion_ratio_static: {
    label: "Static Motion Ratio",
    group: "Suspension Rates",
    derivativeSymbol: "∂MR/∂p",
    kinematicSymbol: "MR₀",
  },
  track_change_max_mm: {
    label: "Max Track Scrub",
    group: "Packaging",
    derivativeSymbol: "∂(Δtrack)/∂p",
    kinematicSymbol: "Δtrack",
  },
  wheelbase_change_max_mm: {
    label: "Max Wheelbase Scrub",
    group: "Packaging",
    derivativeSymbol: "∂(Δwb)/∂p",
    kinematicSymbol: "Δwb",
  },
  caster_static_deg: {
    label: "Static Caster",
    group: "Steering Axis",
    derivativeSymbol: "∂caster/∂p",
    kinematicSymbol: "caster₀",
  },
  kpi_static_deg: {
    label: "Static Kingpin Incl.",
    group: "Steering Axis",
    derivativeSymbol: "∂KPI/∂p",
    kinematicSymbol: "KPI₀",
  },
  scrub_radius_static_mm: {
    label: "Static Scrub Radius",
    group: "Steering Axis",
    derivativeSymbol: "∂r_scrub/∂p",
    kinematicSymbol: "r_scrub",
  },
};

const PRIMARY_COLUMNS = [
  "camber_gain_deg_per_100mm",
  "toe_variation_deg",
  "toe_gain_deg_per_100mm",
  "roll_center_height_static_mm",
  "rc_migration_rate",
  "motion_ratio_static",
  "kpi_static_deg",
  "scrub_radius_static_mm",
];

export default function HardpointSensitivityMatrix({
  data,
  loading,
  stepSizeMm,
  onChangeStepSize,
  onRecompute,
  onSelectCandidate,
}: HardpointSensitivityMatrixProps) {
  const [componentFilter, setComponentFilter] = useState<"ALL" | "UWI" | "LWI" | "TR">("ALL");
  const [axisFilter, setAxisFilter] = useState<"ALL" | "X" | "Y" | "Z">("ALL");
  const [selectedCell, setSelectedCell] = useState<{ rowKey: string; colKey: string } | null>(null);

  // Filter rows
  const filteredRows = useMemo(() => {
    if (!data || !data.jacobian_matrix) return [];
    const keys = Object.keys(data.jacobian_matrix);
    return keys.filter((key) => {
      // key format: "HP_AXIS", e.g. "UWI_aft_Z"
      const parts = key.split("_");
      const axis = parts[parts.length - 1];
      const hp = parts.slice(0, -1).join("_");

      if (axisFilter !== "ALL" && axis !== axisFilter) return false;

      if (componentFilter === "UWI" && !hp.startsWith("UWI") && hp !== "UWO") return false;
      if (componentFilter === "LWI" && !hp.startsWith("LWI") && hp !== "LWO") return false;
      if (componentFilter === "TR" && !hp.startsWith("TR")) return false;

      return true;
    });
  }, [data, componentFilter, axisFilter]);

  // Compute min/max for color scale per column
  const columnExtremes = useMemo(() => {
    if (!data || !data.jacobian_matrix) return {};
    const res: Record<string, { maxAbs: number }> = {};
    for (const col of PRIMARY_COLUMNS) {
      let maxAbs = 0;
      for (const rowKey of Object.keys(data.jacobian_matrix)) {
        const val = data.jacobian_matrix[rowKey]?.[col] || 0;
        if (Math.abs(val) > maxAbs) maxAbs = Math.abs(val);
      }
      res[col] = { maxAbs: maxAbs || 1e-6 };
    }
    return res;
  }, [data]);

  const getHeatmapColor = (val: number, col: string) => {
    const ext = columnExtremes[col];
    if (!ext || ext.maxAbs === 0) return "bg-slate-800/40 text-slate-400";
    const norm = val / ext.maxAbs; // between -1 and +1

    if (Math.abs(norm) < 0.05) {
      return "bg-slate-800/30 text-slate-400";
    }

    if (norm > 0) {
      // Positive derivative: warm amber/orange
      if (norm > 0.66) return "bg-amber-500/30 text-amber-200 font-semibold border-amber-500/40";
      if (norm > 0.33) return "bg-amber-500/20 text-amber-300 border-amber-500/20";
      return "bg-amber-500/10 text-amber-400";
    } else {
      // Negative derivative: cyan/blue
      if (norm < -0.66) return "bg-cyan-500/30 text-cyan-200 font-semibold border-cyan-500/40";
      if (norm < -0.33) return "bg-cyan-500/20 text-cyan-300 border-cyan-500/20";
      return "bg-cyan-500/10 text-cyan-400";
    }
  };

  const parseRowKey = (rowKey: string) => {
    const parts = rowKey.split("_");
    const axis = parts[parts.length - 1];
    const hp = parts.slice(0, -1).join("_");
    return { hp, axis };
  };

  const activeCellDetail = useMemo(() => {
    if (!selectedCell || !data || !data.jacobian_matrix) return null;
    const { rowKey, colKey } = selectedCell;
    const gradient = data.jacobian_matrix[rowKey]?.[colKey] ?? 0;
    const { hp, axis } = parseRowKey(rowKey);
    const unit = data.metric_units?.[colKey] || "unit/mm";
    const baseline = data.baseline_metrics?.[colKey];

    const info = METRIC_DISPLAY_INFO[colKey];

    return {
      rowKey,
      colKey,
      hp,
      axis,
      gradient,
      unit,
      baseline,
      metricName: info?.label || colKey,
      derivativeSymbol: info?.derivativeSymbol || `∂(${colKey})/∂p`,
      kinematicSymbol: info?.kinematicSymbol || colKey,
    };
  }, [selectedCell, data]);

  if (loading && !data) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
        <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin mx-auto mb-3" />
        <h4 className="text-base font-semibold text-slate-200">Computing Kinematic Sensitivity Jacobian...</h4>
        <p className="text-xs text-slate-400 mt-1">
          Evaluating finite difference sweeps across target chassis and upright hardpoints using real C++ solver engine.
        </p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
        <Activity className="w-10 h-10 text-slate-500 mx-auto mb-3" />
        <h4 className="text-base font-semibold text-slate-200">No Sensitivity Matrix Available</h4>
        <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto mb-4">
          Compute the real Jacobian sensitivity matrix to see how every millimeter of chassis/upright adjustment impacts camber gain, bump steer, and roll center height.
        </p>
        <button
          data-testid="btn-recompute-sensitivity"
          onClick={onRecompute}
          className="inline-flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm font-medium transition"
        >
          <Activity className="w-4 h-4" /> Compute Sensitivity Matrix
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Header Controls & Information ── */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-cyan-500/10 rounded-lg text-cyan-400 border border-cyan-500/20">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              Hardpoint Sensitivity Matrix (Finite Difference Jacobian J)
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                {data.total_solver_runs} REAL SOLVER SWEEPS
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Direct kinematic derivatives dOutput / dHardpoint computed via central difference step Δp = ±{data.step_size_mm} mm.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Step Size Selector */}
          <div className="flex items-center gap-1.5 bg-slate-800/80 px-2.5 py-1.5 rounded-lg border border-slate-700">
            <span className="text-xs text-slate-400 font-medium">Step:</span>
            {[0.5, 1.0, 2.0].map((sz) => (
              <button
                key={sz}
                onClick={() => onChangeStepSize(sz)}
                className={`px-2 py-0.5 text-xs rounded font-mono transition ${
                  stepSizeMm === sz
                    ? "bg-cyan-500 text-slate-950 font-bold"
                    : "text-slate-300 hover:bg-slate-700"
                }`}
              >
                ±{sz}mm
              </button>
            ))}
          </div>

          <button
            data-testid="btn-recompute-sensitivity"
            onClick={onRecompute}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs font-medium text-slate-200 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
            {loading ? "Recomputing..." : "Recompute"}
          </button>
        </div>
      </div>

      {/* ── Filters & Legend ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-1 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-slate-400 flex items-center gap-1">
            <Filter className="w-3.5 h-3.5" /> Component:
          </span>
          <div className="flex rounded-md border border-slate-800 bg-slate-900/60 p-0.5">
            {[
              { id: "ALL", label: "All Links" },
              { id: "UWI", label: "Upper Wishbone" },
              { id: "LWI", label: "Lower Wishbone" },
              { id: "TR", label: "Tie Rod" },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setComponentFilter(f.id as any)}
                className={`px-2.5 py-1 rounded text-xs transition ${
                  componentFilter === f.id
                    ? "bg-slate-800 text-cyan-400 font-semibold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          <span className="text-slate-400 ml-2">Axis:</span>
          <div className="flex rounded-md border border-slate-800 bg-slate-900/60 p-0.5">
            {[
              { id: "ALL", label: "All" },
              { id: "X", label: "X (Fore/Aft)" },
              { id: "Y", label: "Y (Lateral)" },
              { id: "Z", label: "Z (Vertical)" },
            ].map((a) => (
              <button
                key={a.id}
                onClick={() => setAxisFilter(a.id as any)}
                className={`px-2 py-1 rounded text-xs transition ${
                  axisFilter === a.id
                    ? "bg-slate-800 text-cyan-400 font-semibold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {a.label}
              </button>
            ))}
          </div>
        </div>

        {/* Color Legend */}
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-cyan-500/30 border border-cyan-500/40 inline-block" /> Negative Rate (Decrease)
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-slate-800 inline-block border border-slate-700" /> Neutral / Minimal
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-amber-500/30 border border-amber-500/40 inline-block" /> Positive Rate (Increase)
          </span>
        </div>
      </div>

      {/* ── Interactive Sensitivity Matrix Table ── */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-800/80 border-b border-slate-700/80 text-slate-300 font-mono">
                <th className="p-3 font-semibold sticky left-0 bg-slate-800/95 z-10 w-44">
                  Hardpoint Perturbation (Δ1mm)
                </th>
                {PRIMARY_COLUMNS.map((col) => {
                  const info = METRIC_DISPLAY_INFO[col];
                  const derivSymbol = info?.derivativeSymbol || `∂(${col})/∂p`;
                  const kinSymbol = info?.kinematicSymbol ? ` [${info.kinematicSymbol}]` : "";
                  const unitStr = data.metric_units?.[col] || "unit/mm";
                  return (
                    <th key={col} className="p-3 text-right font-medium min-w-[145px]">
                      <div className="font-mono text-cyan-400 font-bold text-[12px]">{derivSymbol}</div>
                      <div className="text-[11px] text-slate-200 font-sans">{info?.label || col}<span className="text-cyan-300/80 font-mono text-[10px]">{kinSymbol}</span></div>
                      <div className="text-[10px] text-slate-400 font-mono font-normal">
                        [{unitStr}]
                      </div>
                    </th>
                  );
                })}
                <th className="p-3 text-center w-24">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filteredRows.map((rowKey) => {
                const { hp, axis } = parseRowKey(rowKey);
                return (
                  <tr key={rowKey} className="hover:bg-slate-800/30 transition-colors">
                    {/* Row Header */}
                    <td className="p-2.5 font-medium sticky left-0 bg-slate-900/95 z-10 border-r border-slate-800">
                      <div className="flex items-center justify-between">
                        <span className="text-slate-200 font-bold">{hp}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            axis === "Z"
                              ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                              : axis === "Y"
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              : "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                          }`}
                        >
                          Δ{axis}
                        </span>
                      </div>
                    </td>

                    {/* Gradient Cells */}
                    {PRIMARY_COLUMNS.map((col) => {
                      const val = data.jacobian_matrix[rowKey]?.[col] ?? 0;
                      const isSelected = selectedCell?.rowKey === rowKey && selectedCell?.colKey === col;
                      const colorClass = getHeatmapColor(val, col);

                      // Formatter
                      let formatted = val.toFixed(4);
                      if (Math.abs(val) < 1e-4 && val !== 0) formatted = val.toExponential(2);

                      return (
                        <td
                          key={col}
                          onClick={() => setSelectedCell({ rowKey, colKey: col })}
                          className={`p-2.5 text-right cursor-pointer transition border border-transparent hover:border-cyan-500/60 ${colorClass} ${
                            isSelected ? "ring-2 ring-cyan-400 ring-offset-1 ring-offset-slate-900" : ""
                          }`}
                          title={`Click to inspect causal breakdown for ${hp} Δ${axis} → ${METRIC_DISPLAY_INFO[col]?.label}`}
                        >
                          {val > 0 ? `+${formatted}` : formatted}
                        </td>
                      );
                    })}

                    {/* Actions Column */}
                    <td className="p-2.5 text-center">
                      <button
                        onClick={() => onSelectCandidate && onSelectCandidate(hp, axis)}
                        className="px-2 py-1 bg-slate-800 hover:bg-cyan-600 hover:text-white text-slate-300 rounded text-[11px] font-sans font-medium transition"
                        title="Send this coordinate to Engineering Question / Optimizer"
                      >
                        Target
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Active Cell Inspector Card ── */}
      {activeCellDetail && (
        <div className="bg-slate-900 border border-cyan-500/30 rounded-xl p-4 shadow-lg animate-in fade-in duration-200">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-mono text-xs font-bold border border-cyan-500/40">
                  {activeCellDetail.hp} (Axis {activeCellDetail.axis})
                </span>
                <ArrowRight className="w-4 h-4 text-slate-500" />
                <span className="text-slate-200 text-sm font-semibold">
                  {activeCellDetail.metricName}
                </span>
                <span className="px-1.5 py-0.5 rounded bg-slate-800 text-cyan-400 font-mono text-xs font-bold border border-slate-700">
                  {activeCellDetail.derivativeSymbol}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-4 text-xs font-mono text-slate-300">
                <div>
                  <span className="text-slate-500">Derivative ∂({activeCellDetail.kinematicSymbol})/∂p:</span>{" "}
                  <span className={`font-bold text-sm ${activeCellDetail.gradient >= 0 ? "text-amber-400" : "text-cyan-400"}`}>
                    {activeCellDetail.gradient >= 0 ? `+${activeCellDetail.gradient.toFixed(5)}` : activeCellDetail.gradient.toFixed(5)}{" "}
                    {activeCellDetail.unit}
                  </span>
                </div>
                {activeCellDetail.baseline !== undefined && (
                  <div>
                    <span className="text-slate-500">Baseline Value:</span>{" "}
                    <span className="text-slate-200 font-semibold">{activeCellDetail.baseline.toFixed(3)}</span>
                  </div>
                )}
                <div>
                  <span className="text-slate-500">Expected 5mm Shift Effect:</span>{" "}
                  <span className="text-slate-200 font-semibold">
                    {(activeCellDetail.gradient * 5.0).toFixed(3)}
                  </span>
                </div>
              </div>
            </div>

            <button
              onClick={() => setSelectedCell(null)}
              className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded bg-slate-800 border border-slate-700"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
