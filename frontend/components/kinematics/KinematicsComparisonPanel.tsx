"use client";

import React, { useState } from "react";
import {
  KinematicsComparisonResponse,
  KinematicsSetupItem,
  CausalAttributionItem,
} from "../../lib/api_client";
import {
  ArrowRightLeft,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Cpu,
  Layers,
  Info,
  ChevronDown,
  ChevronUp,
  Activity,
  FileCode,
} from "lucide-react";

interface KinematicsComparisonPanelProps {
  comparison: KinematicsComparisonResponse | null;
  loading: boolean;
  setups: KinematicsSetupItem[];
  selectedSetupAId: string;
  selectedSetupBId: string;
  onSelectSetupA: (id: string) => void;
  onSelectSetupB: (id: string) => void;
  onSwapSetups: () => void;
  onRunComparison: () => void;
}

export default function KinematicsComparisonPanel({
  comparison,
  loading,
  setups,
  selectedSetupAId,
  selectedSetupBId,
  onSelectSetupA,
  onSelectSetupB,
  onSwapSetups,
  onRunComparison,
}: KinematicsComparisonPanelProps) {
  const [activeTab, setActiveTab] = useState<"causal" | "metrics" | "hardpoints" | "provenance">("causal");

  const renderAttributionBadge = (type: any) => {
    const t = String(type || "").toUpperCase();
    if (t.includes("DIRECT")) {
      return (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
          <CheckCircle2 className="w-3 h-3" /> [DIRECTLY COMPUTED]
        </span>
      );
    }
    if (t.includes("INFER")) {
      return (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded font-mono font-bold bg-sky-500/20 text-sky-300 border border-sky-500/40">
          <Activity className="w-3 h-3" /> [INFERRED]
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
        <HelpCircle className="w-3 h-3" /> [HYPOTHESIZED]
      </span>
    );
  };

  return (
    <div className="bg-slate-900/90 border border-slate-700/60 rounded-xl p-5 shadow-2xl backdrop-blur-md flex flex-col gap-5">
      {/* ── Setup Selectors Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <ArrowRightLeft className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white tracking-wide">
              Kinematics Setup Comparison & Causal Study
            </h3>
            <p className="text-xs text-slate-400">
              Direct physics differential study: Baseline (Setup A) vs Candidate (Setup B)
            </p>
          </div>
        </div>

        {/* Setups controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Setup A */}
          <div className="flex items-center gap-1.5 bg-slate-800/80 px-2.5 py-1.5 rounded-lg border border-slate-700 text-xs">
            <span className="text-sky-400 font-bold font-mono">A:</span>
            <select
              value={selectedSetupAId}
              onChange={(e) => onSelectSetupA(e.target.value)}
              className="bg-transparent text-slate-200 focus:outline-none cursor-pointer text-xs"
            >
              {setups.map((s) => (
                <option key={s.id} value={s.id} className="bg-slate-800 text-slate-200">
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={onSwapSetups}
            title="Swap Setup A and B"
            className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 border border-slate-700 transition"
          >
            <ArrowRightLeft className="w-4 h-4" />
          </button>

          {/* Setup B */}
          <div className="flex items-center gap-1.5 bg-slate-800/80 px-2.5 py-1.5 rounded-lg border border-slate-700 text-xs">
            <span className="text-amber-400 font-bold font-mono">B:</span>
            <select
              data-testid="setup-b-select"
              value={selectedSetupBId}
              onChange={(e) => onSelectSetupB(e.target.value)}
              className="bg-transparent text-slate-200 focus:outline-none cursor-pointer text-xs"
            >
              {setups.map((s) => (
                <option key={s.id} value={s.id} className="bg-slate-800 text-slate-200">
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <button
            data-testid="btn-run-comparison"
            onClick={onRunComparison}
            disabled={loading}
            className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow transition flex items-center gap-1.5"
          >
            {loading ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Solving...
              </>
            ) : (
              <>Compare Setups</>
            )}
          </button>
        </div>
      </div>

      {/* ── Sub-Navigation Tabs ── */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2 text-xs">
        <button
          type="button"
          onClick={() => setActiveTab("causal")}
          className={`px-3 py-1.5 rounded-md font-medium transition ${
            activeTab === "causal"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Why is B Different? ({(comparison?.causal_attribution || (comparison as any)?.causal_findings || []).length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("metrics")}
          className={`px-3 py-1.5 rounded-md font-medium transition ${
            activeTab === "metrics"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Metric Deltas ({Object.keys(comparison?.metric_comparisons || {}).length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("hardpoints")}
          className={`px-3 py-1.5 rounded-md font-medium transition ${
            activeTab === "hardpoints"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Hardpoint Deltas ({Object.keys(comparison?.hardpoint_deltas || {}).length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("provenance")}
          className={`px-3 py-1.5 rounded-md font-medium transition ${
            activeTab === "provenance"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Provenance & Hashes
        </button>
      </div>

      {/* ── Tab Content ── */}
      {loading && !comparison ? (
        <div className="text-center py-8 text-cyan-400 text-xs font-mono">
          Solving Setup A vs Setup B kinematic comparison...
        </div>
      ) : !comparison ? (
        <div className="text-center py-8 text-slate-400 text-xs">
          Select Setup A and B, then click <strong className="text-cyan-400">Compare Setups</strong> to run independent solver sweeps.
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {/* Quick Summary Banners */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* What improved */}
            <div className="bg-emerald-950/20 border border-emerald-800/40 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400 mb-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> What Improved in Candidate (Setup B)
              </div>
              {!comparison.what_improved || comparison.what_improved.length === 0 ? (
                <div className="text-xs text-zinc-400">No primary improvements detected over baseline.</div>
              ) : (
                <ul className="text-xs text-slate-300 space-y-1">
                  {comparison.what_improved.map((item: any, idx: number) => {
                    const text = typeof item === "string" ? item : (item.explanation || item.metric || JSON.stringify(item));
                    return (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-emerald-400 font-bold">•</span>
                        <span>{text}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {/* What got worse */}
            <div className="bg-amber-950/20 border border-amber-800/40 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-400 mb-1.5">
                <AlertTriangle className="w-3.5 h-3.5" /> Tradeoffs & Degradations in Setup B
              </div>
              {!comparison.what_got_worse || comparison.what_got_worse.length === 0 ? (
                <div className="text-xs text-zinc-400">No kinematic degradations observed.</div>
              ) : (
                <ul className="text-xs text-slate-300 space-y-1">
                  {comparison.what_got_worse.map((item: any, idx: number) => {
                    const text = typeof item === "string" ? item : (item.explanation || item.metric || JSON.stringify(item));
                    return (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-amber-400 font-bold">•</span>
                        <span>{text}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>

          {/* TAB 1: Causal Attribution */}
          {activeTab === "causal" && (
            <div className="space-y-3">
              {(() => {
                const attributions = comparison.causal_attribution || (comparison as any).causal_findings || [];
                if (attributions.length === 0) {
                  return (
                    <div className="text-center py-6 text-slate-400 text-xs">
                      Setups appear kinematically identical; no causal deltas found.
                    </div>
                  );
                }
                return attributions.map((item: any, idx: number) => {
                  const type = item.type || item.category || "HYPOTHESIZED";
                  const title = item.title || "Kinematic Causal Delta";
                  const finding = item.finding || item.statement || "";
                  const mechanism = item.mechanism || item.physical_mechanism || finding;
                  const evidence = item.evidence || item.direct_evidence || (item.statement !== finding ? item.statement : "Direct kinematic solver output differential");
                  return (
                    <div
                      key={idx}
                      className="p-3.5 rounded-lg bg-slate-800/60 border border-slate-700/60 flex flex-col gap-2"
                    >
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <div className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                          {title}
                        </div>
                        {renderAttributionBadge(type)}
                      </div>
                      <div className="text-xs text-slate-300 font-medium">
                        {finding}
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-700/50">
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-400 font-bold block mb-0.5">Physical Mechanism:</span>
                          <span className="text-slate-300 font-mono text-xs">{mechanism}</span>
                        </div>
                        <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
                          <span className="text-slate-400 font-bold block mb-0.5">Direct Evidence:</span>
                          <span className="text-slate-300 font-mono text-xs">{evidence}</span>
                        </div>
                      </div>
                      {item.recommendation && (
                        <div className="text-xs text-indigo-300/90 bg-indigo-950/20 p-1.5 rounded border border-indigo-900/30">
                          <strong>Race Engineer Recommendation:</strong> {item.recommendation}
                        </div>
                      )}
                    </div>
                  );
                });
              })()}
            </div>
          )}

          {/* TAB 2: Metric Deltas Table */}
          {activeTab === "metrics" && (
            <div data-testid="metric-deltas-table" className="overflow-x-auto rounded-lg border border-slate-800">
              <table className="w-full text-xs text-left border-collapse">
                <thead className="bg-slate-800/90 text-slate-300 font-semibold uppercase tracking-wider text-xs">
                  <tr>
                    <th className="p-2.5">Kinematic Quantity</th>
                    <th className="p-2.5 text-right">Setup A (Static)</th>
                    <th className="p-2.5 text-right">Setup B (Static)</th>
                    <th className="p-2.5 text-right">Δ Static</th>
                    <th className="p-2.5 text-right">Δ Bump (Max)</th>
                    <th className="p-2.5 text-right">RMS Difference</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 font-mono text-xs">
                  {(() => {
                    const rows = Array.isArray(comparison.metric_comparisons)
                      ? comparison.metric_comparisons
                      : Object.values(comparison.metric_comparisons || {});
                    if (rows.length === 0) {
                      return (
                        <tr>
                          <td colSpan={6} className="p-4 text-center text-slate-400 font-sans">
                            No metric delta rows returned. Click Compare Setups to recompute Setup A vs Setup B.
                          </td>
                        </tr>
                      );
                    }
                    return rows.map((m, idx) => {
                      const mAny = m as any;
                      const staticA = Number(m.setup_a?.static_val ?? mAny.val_a_static ?? 0);
                      const staticB = Number(m.setup_b?.static_val ?? mAny.val_b_static ?? 0);
                      const deltaStatic = Number(m.delta_static ?? mAny.static_difference ?? (staticB - staticA));
                      const deltaBump = Number(m.delta_bump ?? mAny.bump_difference ?? 0);
                      const rmsDiff = Number(m.rms_difference ?? 0);
                      const labelText = m.name || mAny.label || mAny.metric || mAny.channel || `Metric ${idx + 1}`;
                      const deltaColor =
                        Math.abs(deltaStatic) < 1e-4
                          ? "text-slate-400"
                          : deltaStatic > 0
                          ? "text-emerald-400"
                          : "text-amber-400";

                      return (
                        <tr key={idx} className="hover:bg-slate-800/40 transition">
                          <td className="p-2.5 font-sans font-medium text-slate-200">
                            {labelText} <span className="text-slate-400 font-normal">({m.unit ?? ""})</span>
                          </td>
                          <td className="p-2.5 text-right text-slate-300">
                            {Number.isFinite(staticA) ? staticA.toFixed(2) : "—"}
                          </td>
                          <td className="p-2.5 text-right text-slate-300">
                            {Number.isFinite(staticB) ? staticB.toFixed(2) : "—"}
                          </td>
                          <td className={`p-2.5 text-right font-bold ${deltaColor}`}>
                            {Number.isFinite(deltaStatic)
                              ? deltaStatic >= 0
                                ? `+${deltaStatic.toFixed(2)}`
                                : deltaStatic.toFixed(2)
                              : "—"}
                          </td>
                          <td className="p-2.5 text-right text-slate-300">
                            {Number.isFinite(deltaBump)
                              ? deltaBump >= 0
                                ? `+${deltaBump.toFixed(2)}`
                                : deltaBump.toFixed(2)
                              : "—"}
                          </td>
                          <td className="p-2.5 text-right text-slate-400">
                            {Number.isFinite(rmsDiff) ? rmsDiff.toFixed(3) : "—"}
                          </td>
                        </tr>
                      );
                    });
                  })()}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: Hardpoint Deltas Table */}
          {activeTab === "hardpoints" && (
            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <table className="w-full text-xs text-left border-collapse">
                <thead className="bg-slate-800/90 text-slate-400 font-semibold uppercase tracking-wider text-xs">
                  <tr>
                    <th className="p-2.5">Hardpoint</th>
                    <th className="p-2.5">Description</th>
                    <th className="p-2.5 text-right">ΔX (mm)</th>
                    <th className="p-2.5 text-right">ΔY (mm)</th>
                    <th className="p-2.5 text-right">ΔZ (mm)</th>
                    <th className="p-2.5 text-right">3D Distance (mm)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 font-mono text-xs">
                  {Object.entries(comparison.hardpoint_deltas).map(([hpKey, delta], idx) => {
                    const isChanged = delta.distance_mm > 0.01;
                    return (
                      <tr
                        key={idx}
                        className={isChanged ? "bg-indigo-950/20 text-indigo-200" : "text-slate-400"}
                      >
                        <td className="p-2.5 font-bold">{hpKey}</td>
                        <td className="p-2.5 font-sans text-slate-400">{delta.description}</td>
                        <td className="p-2.5 text-right">
                          {delta.delta_xyz[0] >= 0 ? `+${delta.delta_xyz[0].toFixed(1)}` : delta.delta_xyz[0].toFixed(1)}
                        </td>
                        <td className="p-2.5 text-right">
                          {delta.delta_xyz[1] >= 0 ? `+${delta.delta_xyz[1].toFixed(1)}` : delta.delta_xyz[1].toFixed(1)}
                        </td>
                        <td className="p-2.5 text-right font-bold">
                          {delta.delta_xyz[2] >= 0 ? `+${delta.delta_xyz[2].toFixed(1)}` : delta.delta_xyz[2].toFixed(1)}
                        </td>
                        <td className="p-2.5 text-right font-bold text-amber-400">
                          {delta.distance_mm.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 4: Provenance */}
          {activeTab === "provenance" && (
            <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800 space-y-2 font-mono text-xs text-slate-400">
              <div className="flex items-center gap-2 text-indigo-400 font-semibold mb-2">
                <Cpu className="w-4 h-4" /> Solver Audit & Verification Provenance
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-zinc-400">Comparison ID:</span> {comparison.comparison_id}
                </div>
                <div>
                  <span className="text-zinc-400">Timestamp:</span> {comparison.timestamp}
                </div>
                <div>
                  <span className="text-zinc-400">Setup A Hash:</span>{" "}
                  <span className="text-sky-300">{comparison.geometry_hash_a}</span>
                </div>
                <div>
                  <span className="text-zinc-400">Setup B Hash:</span>{" "}
                  <span className="text-amber-300">{comparison.geometry_hash_b}</span>
                </div>
                <div>
                  <span className="text-zinc-400">Sweep Range:</span> [{comparison.provenance.z_min_mm} mm, {comparison.provenance.z_max_mm} mm]
                </div>
                <div>
                  <span className="text-zinc-400">Evaluation Steps:</span> {comparison.provenance.n_steps} monotonic points
                </div>
                <div>
                  <span className="text-zinc-400">Backend A:</span> {comparison.provenance.backend_a}
                </div>
                <div>
                  <span className="text-zinc-400">Backend B:</span> {comparison.provenance.backend_b}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
