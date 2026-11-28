"use client";

import React, { useState, useEffect } from "react";
import {
  GitCompare,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sliders,
  ChevronRight,
  Loader2,
  Sparkles,
  Info,
} from "lucide-react";
import {
  SimulationApi,
  SetupDiffResponse,
  WhatChangedResponse,
  RunDecisionResponse,
} from "../../lib/api_client";

export interface ActiveSetupSnapshot {
  k_spring_front: number;
  k_spring_rear: number;
  k_arb_front: number;
  k_arb_rear: number;
  ride_height_front: number;
  ride_height_rear: number;
}

const DEFAULT_BASELINE_SETUP: ActiveSetupSnapshot = {
  k_spring_front: 35_000,
  k_spring_rear: 45_000,
  k_arb_front: 15_000,
  k_arb_rear: 10_000,
  ride_height_front: 30,
  ride_height_rear: 60,
};

function computeLocalSetupDiff(
  runAName: string,
  runBName: string,
  base: ActiveSetupSnapshot,
  cand: ActiveSetupSnapshot
): {
  diff: SetupDiffResponse;
  whatChanged: WhatChangedResponse;
  decision: RunDecisionResponse;
} {
  const specs: Array<{
    key: keyof ActiveSetupSnapshot;
    label: string;
    unit: string;
  }> = [
    { key: "k_spring_front", label: "Front Spring Stiffness (k_s,f)", unit: "N/m" },
    { key: "k_spring_rear", label: "Rear Spring Stiffness (k_s,r)", unit: "N/m" },
    { key: "k_arb_front", label: "Front ARB Stiffness (k_arb,f)", unit: "N/m" },
    { key: "k_arb_rear", label: "Rear ARB Stiffness (k_arb,r)", unit: "N/m" },
    { key: "ride_height_front", label: "Front Ride Height (h_f)", unit: "mm" },
    { key: "ride_height_rear", label: "Rear Ride Height (h_r)", unit: "mm" },
  ];

  const parameters = specs.map((s) => {
    const bVal = base[s.key];
    const cVal = cand[s.key];
    const delta = cVal - bVal;
    const deltaPct = Math.abs(bVal) > 1e-6 ? Number(((delta / bVal) * 100).toFixed(2)) : 0;
    return {
      parameter: s.label,
      baseline: bVal,
      candidate: cVal,
      delta,
      delta_pct: deltaPct,
      unit: s.unit,
    };
  });

  const baseRollF = 0.5 * (base.k_spring_front + base.k_arb_front) * 1.55 * 1.55;
  const baseRollR = 0.5 * (base.k_spring_rear + base.k_arb_rear) * 1.52 * 1.52;
  const candRollF = 0.5 * (cand.k_spring_front + cand.k_arb_front) * 1.55 * 1.55;
  const candRollR = 0.5 * (cand.k_spring_rear + cand.k_arb_rear) * 1.52 * 1.52;

  const baseFrontPct = (baseRollF / Math.max(1, baseRollF + baseRollR)) * 100;
  const candFrontPct = (candRollF / Math.max(1, candRollF + candRollR)) * 100;
  const deltaFrontPct = Number((candFrontPct - baseFrontPct).toFixed(2));

  const deltaRhF = cand.ride_height_front - base.ride_height_front;
  const deltaRhR = cand.ride_height_rear - base.ride_height_rear;
  const rakeBase = base.ride_height_rear - base.ride_height_front;
  const rakeCand = cand.ride_height_rear - cand.ride_height_front;
  const deltaRake = rakeCand - rakeBase;
  const totalRollBase = baseRollF + baseRollR;
  const totalRollCand = candRollF + candRollR;
  const deltaTotalRoll = Number((totalRollCand - totalRollBase).toFixed(0));

  const changedSpecs = parameters.filter((p) => Math.abs(p.delta) > 1e-6);

  const causal_chain: string[] =
    changedSpecs.length === 0
      ? [
          "No active setup sliders differ from the baseline reference configuration yet.",
          "Switch to Sensitivity Sliders or modify spring, ARB, or ride height values to evaluate live setup deltas.",
        ]
      : [
          `Input Modifications: ${changedSpecs
            .slice(0, 3)
            .map((p) => `${p.parameter} ${p.delta > 0 ? "+" : ""}${p.delta} ${p.unit}`)
            .join(", ")}.`,
          `Elastic Roll Balance: Front roll stiffness distribution shifted ${baseFrontPct.toFixed(1)}% -> ${candFrontPct.toFixed(1)}% (${deltaFrontPct >= 0 ? "+" : ""}${deltaFrontPct}%).`,
          `Aero Rake Platform: Rake changed from ${rakeBase.toFixed(0)} mm to ${rakeCand.toFixed(0)} mm (${deltaRake >= 0 ? "+" : ""}${deltaRake.toFixed(0)} mm).`,
        ];

  return {
    diff: {
      a: runAName,
      b: runBName,
      parameters,
      predicted_consequences: {
        "Front Roll Dist Delta": {
          baseline: Number(baseFrontPct.toFixed(2)),
          candidate: Number(candFrontPct.toFixed(2)),
          delta: deltaFrontPct,
          delta_pct: Number((deltaFrontPct / Math.max(1, baseFrontPct) * 100).toFixed(2)),
          unit: "%",
          beneficial: Math.abs(candFrontPct - 50) <= Math.abs(baseFrontPct - 50),
        },
        "Total Roll Stiffness Delta": {
          baseline: Number(totalRollBase.toFixed(0)),
          candidate: Number(totalRollCand.toFixed(0)),
          delta: deltaTotalRoll,
          delta_pct: Number(((deltaTotalRoll / Math.max(1, totalRollBase)) * 100).toFixed(2)),
          unit: "Nm/rad",
          beneficial: deltaTotalRoll >= 0,
        },
        "Front Ride Height Delta": {
          baseline: base.ride_height_front,
          candidate: cand.ride_height_front,
          delta: deltaRhF,
          delta_pct: Number(((deltaRhF / Math.max(1, base.ride_height_front)) * 100).toFixed(2)),
          unit: "mm",
          beneficial: cand.ride_height_front >= 15,
        },
        "Aero Rake Delta": {
          baseline: rakeBase,
          candidate: rakeCand,
          delta: deltaRake,
          delta_pct: Number(((deltaRake / Math.max(1, Math.abs(rakeBase))) * 100).toFixed(2)),
          unit: "mm",
          beneficial: deltaRake >= 0,
        },
      },
    },
    whatChanged: {
      headline:
        changedSpecs.length === 0
          ? "Active Setup Matches Baseline Configuration"
          : `Active Setup Delta: ${changedSpecs.length} Parameter${changedSpecs.length > 1 ? "s" : ""} Modified`,
      summary:
        changedSpecs.length === 0
          ? "All suspension spring rates, ARB rates, and ride heights are aligned with the baseline setup."
          : `Computed live from active setup state: front roll balance ${candFrontPct.toFixed(1)}% vs baseline ${baseFrontPct.toFixed(1)}%, rake ${rakeCand.toFixed(0)} mm.`,
      confidence_score_pct: 100,
      primary_mechanism:
        Math.abs(deltaFrontPct) > Math.abs(deltaRake)
          ? "Elastic roll stiffness redistribution across front and rear axles"
          : "Aerodynamic rake and platform ride-height sensitivity",
      parameter_deltas: changedSpecs.map((p) => ({
        param: p.parameter,
        from: p.baseline,
        to: p.candidate,
        delta_pct: p.delta_pct,
      })),
      predicted_effects: [
        {
          metric: "Front Roll Distribution",
          delta: deltaFrontPct,
          unit: "%",
          verdict:
            Math.abs(deltaFrontPct) <= 0.5
              ? "NEUTRAL"
              : Math.abs(candFrontPct - 50) <= Math.abs(baseFrontPct - 50)
              ? "IMPROVED"
              : "DEGRADED",
        },
      ],
      causal_chain,
    },
    decision: {
      verdict: cand.ride_height_front >= 15 && cand.ride_height_rear >= 25 ? "GOOD" : "WARNING",
      headline:
        changedSpecs.length === 0
          ? "Baseline Parity Verified"
          : cand.ride_height_front >= 15 && cand.ride_height_rear >= 25
          ? "Active Setup Within Clearance Bounds"
          : "Check Minimum Ride-Height Clearance",
      why: "Evaluated directly from the active suspension setup parameters without stale cached runs.",
      evidence: [
        {
          label: "Front Roll Balance",
          value: `${candFrontPct.toFixed(1)}%`,
          threshold: "44% - 56%",
          status: candFrontPct >= 44 && candFrontPct <= 56 ? "PASS" : "WARN",
        },
        {
          label: "Front Clearance",
          value: `${cand.ride_height_front.toFixed(0)} mm`,
          threshold: ">= 15 mm",
          status: cand.ride_height_front >= 15 ? "PASS" : "FAIL",
        },
        {
          label: "Rear Clearance",
          value: `${cand.ride_height_rear.toFixed(0)} mm`,
          threshold: ">= 25 mm",
          status: cand.ride_height_rear >= 25 ? "PASS" : "FAIL",
        },
      ],
    },
  };
}

interface SetupDiffViewerProps {
  initialRunA?: string;
  initialRunB?: string;
  activeSetup?: ActiveSetupSnapshot;
  baselineSetup?: ActiveSetupSnapshot;
  onSelectRun?: (runId: string) => void;
}

export default function SetupDiffViewer({
  initialRunA = "BASELINE-SETUP",
  initialRunB = "ACTIVE-SETUP",
  activeSetup,
  baselineSetup = DEFAULT_BASELINE_SETUP,
  onSelectRun,
}: SetupDiffViewerProps) {
  const [runA, setRunA] = useState(initialRunA);
  const [runB, setRunB] = useState(initialRunB);
  const [diff, setDiff] = useState<SetupDiffResponse | null>(null);
  const [whatChanged, setWhatChanged] = useState<WhatChangedResponse | null>(null);
  const [decision, setDecision] = useState<RunDecisionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLocalSetupMode =
    (runA === "BASELINE-SETUP" || runA === initialRunA) &&
    (runB === "ACTIVE-SETUP" || runB === initialRunB);

  const fetchDiffData = async () => {
    setError(null);
    if (isLocalSetupMode) {
      const local = computeLocalSetupDiff(runA, runB, baselineSetup, activeSetup ?? baselineSetup);
      setDiff(local.diff);
      setWhatChanged(local.whatChanged);
      setDecision(local.decision);
      return;
    }

    setLoading(true);
    try {
      const [d, wc, dec] = await Promise.all([
        SimulationApi.compareRuns(runA, runB).catch(() => null),
        SimulationApi.getWhatChanged(runA, runB).catch(() => null),
        SimulationApi.getRunDecision(runB).catch(() => null),
      ]);

      const localFallback = computeLocalSetupDiff(runA, runB, baselineSetup, activeSetup ?? baselineSetup);
      setDiff(d ?? localFallback.diff);
      setWhatChanged(wc ?? localFallback.whatChanged);
      setDecision(dec ?? localFallback.decision);
    } catch (e: any) {
      setError(e?.message || "Failed to load setup diff data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isLocalSetupMode) {
      const local = computeLocalSetupDiff(runA, runB, baselineSetup, activeSetup ?? baselineSetup);
      setDiff(local.diff);
      setWhatChanged(local.whatChanged);
      setDecision(local.decision);
    }
  }, [runA, runB, activeSetup, baselineSetup, isLocalSetupMode]);

  return (
    <div className="space-y-6 select-none font-sans text-white">
      {/* Run Selection & Comparison Control Bar */}
      <div className="p-4 rounded-2xl bg-[#111116] border border-white/[0.08] flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
            <GitCompare size={16} />
          </div>
          <div>
            <h3 className="font-extrabold text-sm text-white tracking-tight">
              Setup Comparison & Consequence Engine
            </h3>
            <p className="text-xs text-gray-400">
              Differential analysis of setup revisions with physics-based causal tracking.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 font-mono text-xs">
          <div className="flex items-center gap-2">
            <span className="text-gray-400">Baseline (A):</span>
            <input
              type="text"
              value={runA}
              onChange={(e) => setRunA(e.target.value)}
              className="bg-black/50 border border-white/10 rounded-lg px-2.5 py-1 text-white font-bold w-32 focus:border-signal focus:outline-none"
            />
          </div>

          <ArrowRight size={14} className="text-zinc-400" />

          <div className="flex items-center gap-2">
            <span className="text-gray-400">Candidate (B):</span>
            <input
              type="text"
              value={runB}
              onChange={(e) => setRunB(e.target.value)}
              className="bg-black/50 border border-white/10 rounded-lg px-2.5 py-1 text-signal font-bold w-32 focus:border-signal focus:outline-none"
            />
          </div>

          <button
            onClick={fetchDiffData}
            disabled={loading}
            className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white"
            title="Refresh comparison"
          >
            {loading ? <Loader2 size={14} className="animate-spin text-signal" /> : <RotateCcw size={14} />}
          </button>
        </div>
      </div>

      {/* Decision Summary Card */}
      {decision && (
        <div className="p-4 rounded-2xl bg-[#111116] border border-emerald-500/30 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-950/60 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
              <CheckCircle2 size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-400">
                  VERDICT: {decision.verdict} ({decision.headline})
                </span>
                {whatChanged && (
                  <span className="px-2 py-0.2 rounded-full text-xs font-mono bg-emerald-950/40 border border-emerald-500/30 text-emerald-300">
                    {whatChanged.confidence_score_pct}% Confidence
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-300 mt-0.5">
                {whatChanged?.summary || decision.why}
              </p>
            </div>
          </div>

          {onSelectRun && (
            <button
              onClick={() => onSelectRun(runB)}
              className="px-4 py-1.5 bg-signal text-carbon border border-signal font-bold text-xs rounded-xl hover:bg-[#d6f56e] flex items-center gap-1.5 transition-colors"
            >
              Set {runB} as Active
              <ChevronRight size={13} />
            </button>
          )}
        </div>
      )}

      {/* 2-Column Grid: Parameter Deltas Table vs Causal Chain */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Parameter Deltas Table */}
        <div className="lg:col-span-6 rounded-2xl bg-[#111116] border border-white/[0.08] overflow-hidden">
          <div className="px-5 py-3.5 border-b border-white/[0.06] flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-white">
              <Sliders size={14} className="text-signal" />
              Parameter Modifications
            </div>
            <span className="text-xs font-mono text-gray-400">Baseline vs Candidate</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-white/[0.02] border-b border-white/[0.06] text-gray-400 uppercase text-xs">
                <tr>
                  <th className="py-2.5 px-4">Parameter</th>
                  <th className="py-2.5 px-3 text-right">Setup A</th>
                  <th className="py-2.5 px-3 text-right">Setup B</th>
                  <th className="py-2.5 px-4 text-right">Delta (Δ)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {diff &&
                  diff.parameters.map((p, idx) => {
                    const isPositive = p.delta > 0;
                    return (
                      <tr key={idx} className="hover:bg-white/[0.02]">
                        <td className="py-2.5 px-4 text-gray-300 font-semibold">{p.parameter}</td>
                        <td className="py-2.5 px-3 text-right text-gray-400">
                          {p.baseline} {p.unit}
                        </td>
                        <td className="py-2.5 px-3 text-right text-white font-bold">
                          {p.candidate} {p.unit}
                        </td>
                        <td
                          className={`py-2.5 px-4 text-right font-bold ${
                            isPositive ? "text-cyan-400" : "text-amber-400"
                          }`}
                        >
                          {isPositive ? "+" : ""}
                          {p.delta} {p.unit} ({p.delta_pct > 0 ? "+" : ""}{p.delta_pct}%)
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right Column: Predicted Causal Consequences */}
        <div className="lg:col-span-6 space-y-4">
          <div className="p-5 rounded-2xl bg-[#111116] border border-white/[0.08] space-y-4">
            <div className="flex items-center gap-2 text-xs font-mono font-bold text-white uppercase tracking-wider">
              <Sparkles size={14} className="text-purple-400" />
              Physics Causal Chain (What Changed)
            </div>

            <div className="space-y-3">
              {whatChanged?.causal_chain.map((stepStr, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                  <div className="w-6 h-6 rounded-lg bg-purple-500/20 text-purple-300 font-mono text-xs font-bold flex items-center justify-center shrink-0">
                    {i + 1}
                  </div>
                  <div className="text-xs text-gray-300 font-sans mt-0.5">
                    {stepStr}
                  </div>
                </div>
              ))}
            </div>

            {/* Predicted Consequences Grid */}
            <div className="pt-2 border-t border-white/[0.06] grid grid-cols-2 gap-3">
              {diff &&
                Object.entries(diff.predicted_consequences).map(([mName, mVal], i) => (
                  <div key={i} className="p-2.5 rounded-xl bg-black/40 border border-white/[0.04]">
                    <div className="text-xs text-gray-400 font-mono">{mName}</div>
                    <div className="text-sm font-extrabold font-mono text-emerald-400 mt-0.5 flex items-center gap-1">
                      {mVal.delta < 0 ? <TrendingDown size={14} /> : <TrendingUp size={14} />}
                      {mVal.delta > 0 ? "+" : ""}
                      {mVal.delta} {mVal.unit}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
