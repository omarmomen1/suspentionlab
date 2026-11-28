"use client";

import React from "react";
import {
  Scale,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  CheckCircle2,
  Sliders,
  Activity,
  ArrowRight,
} from "lucide-react";

export interface CompareParamItem {
  parameter: string;
  baseline: number;
  candidate: number;
  delta: number;
  delta_pct: number;
  unit: string;
}

export interface CompareEffectItem {
  metric: string;
  baseline: number;
  candidate: number;
  delta: number;
  delta_pct: number;
  unit: string;
  beneficial: boolean;
}

export interface CompareViewProps {
  setupAName?: string;
  setupBName?: string;
  parameters: CompareParamItem[];
  consequences: CompareEffectItem[];
  whyExplanation?: string;
  tradeoffsAccepted?: string[];
  evidenceScore?: number;
  onApplyCandidate?: () => void;
}

export default function CompareView({
  setupAName = "Baseline (Setup A)",
  setupBName = "Candidate (Setup B)",
  parameters,
  consequences,
  whyExplanation,
  tradeoffsAccepted = [],
  evidenceScore = 0.94,
  onApplyCandidate,
}: CompareViewProps) {
  return (
    <div className="bg-neutral-900/90 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-6 text-white font-sans">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 uppercase tracking-wider">
            <Scale className="w-4 h-4" />
            <span>Side-by-Side Comparative Intelligence</span>
          </div>
          <h2 className="text-xl font-bold mt-1">
            {setupAName} <span className="text-zinc-400 font-normal">vs</span> {setupBName}
          </h2>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-mono px-3 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
            Holdout Evidence R²: {(evidenceScore * 100).toFixed(1)}%
          </span>
          {onApplyCandidate && (
            <button
              onClick={onApplyCandidate}
              className="px-4 py-2 text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors flex items-center gap-1.5 shadow-lg"
            >
              <span>Promote Candidate</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* 1. What Changed (Parametric Differences) */}
      <div className="space-y-3">
        <h3 className="text-xs font-mono uppercase tracking-wider text-neutral-400 flex items-center gap-2">
          <Sliders className="w-3.5 h-3.5 text-cyan-400" />
          <span>1. What Changed (Physical Parameters)</span>
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono text-xs border-collapse">
            <thead>
              <tr className="border-b border-neutral-800 text-xs text-neutral-400 uppercase">
                <th className="py-2.5 px-3">Parameter</th>
                <th className="py-2.5 px-3">{setupAName}</th>
                <th className="py-2.5 px-3">{setupBName}</th>
                <th className="py-2.5 px-3">Delta (Δ)</th>
                <th className="py-2.5 px-3">Delta %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800/60">
              {parameters.map((p, i) => (
                <tr key={i} className="hover:bg-neutral-800/40 transition-colors">
                  <td className="py-3 px-3 font-sans font-medium text-white">{p.parameter}</td>
                  <td className="py-3 px-3 text-neutral-300">{p.baseline} {p.unit}</td>
                  <td className="py-3 px-3 text-neutral-300">{p.candidate} {p.unit}</td>
                  <td className="py-3 px-3 font-bold text-cyan-400">
                    {p.delta > 0 ? `+${p.delta}` : p.delta} {p.unit}
                  </td>
                  <td className="py-3 px-3 font-bold text-neutral-200">
                    {p.delta_pct > 0 ? `+${p.delta_pct.toFixed(1)}` : p.delta_pct.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 2 & 3. What Improved vs What Got Worse */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Improved */}
        <div className="bg-emerald-950/20 border border-emerald-500/40 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2 text-xs font-mono font-bold uppercase text-emerald-400">
            <TrendingUp className="w-4 h-4" />
            <span>2. What Improved (Simulation Gains)</span>
          </div>
          <div className="space-y-2">
            {consequences.filter((c) => c.beneficial).map((c, i) => (
              <div key={i} className="bg-neutral-950/60 p-2.5 rounded border border-neutral-800/80 flex justify-between items-center text-xs">
                <span className="text-neutral-200 font-medium">{c.metric}</span>
                <span className="font-mono text-emerald-400 font-bold">
                  {c.delta > 0 ? `+${c.delta.toFixed(2)}` : c.delta.toFixed(2)} {c.unit} ({c.delta_pct > 0 ? "+" : ""}{c.delta_pct.toFixed(1)}%)
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Got Worse / Tradeoffs */}
        <div className="bg-amber-950/20 border border-amber-500/40 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2 text-xs font-mono font-bold uppercase text-amber-400">
            <TrendingDown className="w-4 h-4" />
            <span>3. What Got Worse (Mandatory Tradeoffs)</span>
          </div>
          <div className="space-y-2">
            {consequences.filter((c) => !c.beneficial).map((c, i) => (
              <div key={i} className="bg-neutral-950/60 p-2.5 rounded border border-neutral-800/80 flex justify-between items-center text-xs">
                <span className="text-neutral-200 font-medium">{c.metric}</span>
                <span className="font-mono text-amber-400 font-bold">
                  {c.delta > 0 ? `+${c.delta.toFixed(2)}` : c.delta.toFixed(2)} {c.unit} ({c.delta_pct > 0 ? "+" : ""}{c.delta_pct.toFixed(1)}%)
                </span>
              </div>
            ))}
            {tradeoffsAccepted.map((t, i) => (
              <div key={i} className="text-xs text-amber-300/90 font-mono bg-neutral-950/40 p-2 rounded">
                • {t}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 4. Why Explanation */}
      {whyExplanation && (
        <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 space-y-1.5">
          <span className="text-xs font-mono uppercase text-cyan-400 font-bold">4. Causality &amp; Physics Chain</span>
          <p className="text-xs text-neutral-300 leading-relaxed font-sans">{whyExplanation}</p>
        </div>
      )}
    </div>
  );
}
