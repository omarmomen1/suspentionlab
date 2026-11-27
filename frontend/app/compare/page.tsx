"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  GitCompare,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  RotateCcw,
  ArrowRight,
  ShieldCheck,
  Zap,
  Layers,
  ArrowUpRight,
  Sliders,
  Sparkles,
  ChevronRight,
  Activity,
  FileCheck2,
  Info,
} from "lucide-react";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import PlanGate from "../../components/PlanGate";
import {
  ExperimentApi,
  DeepComparisonResponse,
  MetricDeltaEntry,
  ConstraintDetail,
  ExperimentRecordResponse,
} from "../../lib/api_client";
import {
  EvidenceBadge,
  ValidationBadge,
  ConfidenceIndicator,
  WhyButton,
  EngineeringCard,
  EngineeringMetric,
  ConstraintWarning,
  StructuredErrorCard,
  StructuredErrorCardProps,
} from "../../components/engineering";

interface PresetComparison {
  id: string;
  title: string;
  scenario: string;
  setupA: Record<string, number>;
  setupB: Record<string, number>;
  hypothesis: string;
}

const PRESET_COMPARISONS: PresetComparison[] = [
  {
    id: "comp-1",
    title: "Aero Platform Firming vs Compliance",
    scenario: "High-Speed Circuit Aero Stability vs Kerb Strike Harshness",
    setupA: { k_s: 35000, c: 2200, m_s: 320, k_t: 220000, k_arb_f: 16000 },
    setupB: { k_s: 42000, c: 2600, m_s: 320, k_t: 220000, k_arb_f: 18500 },
    hypothesis: "Stiffening heave springs (+20%) and damping (+18%) stabilizes aerodynamic underbody ride height, but increases kerb impact accelerations by ~8%.",
  },
  {
    id: "comp-2",
    title: "Low-Grip / Wet Surface Compliance",
    scenario: "Wet Weather Cornering & Mechanical Contact Maintenance",
    setupA: { k_s: 35000, c: 2200, m_s: 320, k_t: 220000, k_arb_f: 16000 },
    setupB: { k_s: 28000, c: 1750, m_s: 320, k_t: 220000, k_arb_f: 12500 },
    hypothesis: "Softening spring rate (-20%) and damping (-20%) increases mechanical wheel compliance and reduces tire load fluctuation, at the cost of pitch control.",
  },
  {
    id: "comp-3",
    title: "Damper Rebound Tuning Only",
    scenario: "Post-Kerb Oscillation Settling without Changing Spring Rate",
    setupA: { k_s: 35000, c: 2000, m_s: 320, k_t: 220000, k_arb_f: 16000 },
    setupB: { k_s: 35000, c: 2700, m_s: 320, k_t: 220000, k_arb_f: 16000 },
    hypothesis: "Increasing damping coefficient (+35%) reduces body oscillation decay time, but increases high-frequency force transmission to chassis.",
  },
];

function CompareContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setActiveExperimentId } = useWorkspace();

  // Setup states
  const [setupA, setSetupA] = useState<Record<string, any>>({
    k_s: 35000,
    c: 2200,
    m_s: 320,
    k_t: 220000,
    k_arb_f: 16000,
  });

  const [setupB, setSetupB] = useState<Record<string, any>>({
    k_s: 42000,
    c: 2600,
    m_s: 320,
    k_t: 220000,
    k_arb_f: 18500,
  });

  const [selectedPreset, setSelectedPreset] = useState<string>("comp-1");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [comparisonResult, setComparisonResult] = useState<DeepComparisonResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [structuredError, setStructuredError] = useState<StructuredErrorCardProps | null>(null);
  const [durableExpId, setDurableExpId] = useState<string | null>(null);
  const [recentExperiments, setRecentExperiments] = useState<ExperimentRecordResponse[]>([]);
  const [whyOpenKey, setWhyOpenKey] = useState<string | null>(null);
  const [testQueued, setTestQueued] = useState<boolean>(false);

  // Load comparison on mount or preset switch
  const runDeepCompare = async (aParams: Record<string, any> = setupA, bParams: Record<string, any> = setupB) => {
    setIsLoading(true);
    setError(null);
    setTestQueued(false);

    try {
      const res = await ExperimentApi.compareSetups({
        setup_a: aParams,
        setup_b: bParams,
      });
      setComparisonResult(res);
    } catch (err: any) {
      setError(err?.message || "Failed to execute comparative simulation analysis.");
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch recent experiments for quick comparison loading
  useEffect(() => {
    ExperimentApi.listExperiments(10)
      .then((res) => {
        if (res && res.experiments) {
          setRecentExperiments(res.experiments);
        }
      })
      .catch(() => {
        // Non-critical
      });
  }, []);

  // Initial load & searchParams resolution with Zero Silent Fallback
  useEffect(() => {
    const expId = searchParams.get("exp_id");
    const candidateParam = searchParams.get("candidate");

    setStructuredError(null);

    // 1. If exp_id is provided, fetch durable experiment record
    if (expId) {
      setIsLoading(true);
      setDurableExpId(expId);
      ExperimentApi.getExperiment(expId)
        .then((exp) => {
          if (exp && exp.parent_setup && exp.candidate_setup) {
            setSetupA(exp.parent_setup);
            setSetupB(exp.candidate_setup);
            setActiveExperimentId(exp.id);
            runDeepCompare(exp.parent_setup, exp.candidate_setup);
          } else {
            throw new Error("Experiment payload missing baseline or candidate setup parameters.");
          }
        })
        .catch((err) => {
          setIsLoading(false);
          setComparisonResult(null);
          setStructuredError({
            title: "DURABLE EXPERIMENT RETRIEVAL FAILURE",
            whatFailed: `Failed to load experiment with ID: '${expId}'.`,
            why: err?.message || "Experiment record does not exist (404), was deleted, or belongs to another tenant organization.",
            whatRemainsValid: "Quarter-car physics ODE solver and workspace baseline vehicle configuration.",
            whatCannotBeClaimed: "Comparative evaluation of candidate setup B, delta metrics, and performance tradeoffs.",
            nextAction: "Return to Hypothesis Testing lab to re-execute the experiment, or select a verified experiment from history.",
            actionButton: {
              label: "Return to Experiment Lab",
              href: "/experiment",
            },
          });
        });
      return;
    }

    // 2. If candidate is provided directly in URL (e.g. JSON string)
    if (candidateParam) {
      try {
        const parsedCandidate = JSON.parse(decodeURIComponent(candidateParam));
        if (typeof parsedCandidate !== "object" || parsedCandidate === null) {
          throw new Error("Candidate parameter is not a valid JSON object.");
        }
        const numericKeys = Object.keys(parsedCandidate).filter(
          (k) => typeof parsedCandidate[k] === "number" && !isNaN(parsedCandidate[k])
        );
        if (numericKeys.length === 0) {
          throw new Error("Candidate JSON contains no valid numeric parameter values.");
        }
        const mergedB = { ...setupB, ...parsedCandidate };
        setSetupB(mergedB);
        runDeepCompare(setupA, mergedB);
      } catch (err: any) {
        setComparisonResult(null);
        setStructuredError({
          title: "CANDIDATE SETUP DESERIALIZATION FAILURE",
          whatFailed: "Failed to deserialize candidate setup parameter payload from URL query string.",
          why: err?.message || "URL 'candidate' parameter contains malformed JSON or unparseable tokens.",
          whatRemainsValid: "Quarter-car physics ODE solver and default baseline setup.",
          whatCannotBeClaimed: "Evaluation of intended candidate suspension setup.",
          nextAction: "Re-launch comparison from an experiment or multi-objective candidate.",
          actionButton: {
            label: "Open Experiment Lab",
            href: "/experiment",
          },
        });
      }
      return;
    }

    // 3. If neither exp_id nor candidate is provided, run default comparison
    runDeepCompare();
  }, [searchParams]);

  const handleApplyPreset = (preset: PresetComparison) => {
    setSelectedPreset(preset.id);
    setSetupA(preset.setupA);
    setSetupB(preset.setupB);
    runDeepCompare(preset.setupA, preset.setupB);
  };

  const handleTestThisChange = () => {
    setTestQueued(true);
    // Serialize Setup B parameters and navigate to Experiment Builder
    const query = new URLSearchParams();
    query.set("clone_from", "compare_setup_b");
    if (setupB.k_s) query.set("k_s", setupB.k_s.toString());
    if (setupB.c) query.set("c", setupB.c.toString());
    if (setupB.k_arb_f) query.set("k_arb_f", setupB.k_arb_f.toString());
    if (setupB.m_s) query.set("m_s", setupB.m_s.toString());

    setTimeout(() => {
      router.push(`/experiment?${query.toString()}`);
    }, 700);
  };

  return (
    <div className="min-h-screen bg-[#070709] text-gray-200">
      <main className="max-w-[1560px] mx-auto px-4 sm:px-6 py-6 space-y-6">
        
        {/* Navigation Breadcrumbs & Top Meta */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
          <div>
            <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
              <Link href="/" className="hover:text-white transition-colors">Command Center</Link>
              <span>/</span>
              <Link href="/experiment" className="hover:text-white transition-colors">Hypothesis Testing</Link>
              <span>/</span>
              <span className="text-ansys-yellow font-medium">Comparative Intelligence</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
                <GitCompare size={20} />
              </div>
              <div>
                <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2">
                  Comparative Intelligence Center
                  <span className="text-xs px-2 py-0.5 rounded-full bg-white/[0.06] text-gray-400 font-mono font-normal border border-white/10">
                    Setup A vs Setup B
                  </span>
                </h1>
                <p className="text-xs text-gray-400">
                  Explicitly answers <strong className="text-gray-200">&quot;Why is B better than A?&quot;</strong> with quantitative tradeoffs, physical causality, and model validation boundaries.
                </p>
              </div>
            </div>
          </div>

          {/* Action CTAs */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => runDeepCompare()}
              disabled={isLoading}
              className="px-3 py-2 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] border border-white/10 text-xs font-medium text-gray-300 flex items-center gap-2 transition-all disabled:opacity-50"
            >
              <RotateCcw size={13} className={isLoading ? "animate-spin text-ansys-yellow" : ""} />
              <span>Re-evaluate ODE</span>
            </button>

            <Link
              data-testid="btn-compare-to-optimize"
              href={`/optimize?k_s=${setupB.k_s}&c=${setupB.c}`}
              className="px-3 py-2 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/40 text-xs font-medium text-blue-300 flex items-center gap-2 transition-all"
            >
              <Sliders size={13} className="text-blue-400" />
              <span>[ Multi-Objective Optimizer ]</span>
            </Link>

            <button
              onClick={handleTestThisChange}
              className={`px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all shadow-lg ${
                testQueued
                  ? "bg-green-500 text-black shadow-green-500/20"
                  : "bg-signal hover:bg-[#d6f56e] text-carbon border border-signal"
              }`}
            >
              <Zap size={14} className={testQueued ? "text-black" : "text-black"} />
              <span>{testQueued ? "Redirecting to Builder..." : "[ TEST THIS CHANGE ]"}</span>
            </button>
          </div>
        </div>

        {/* Structured Error Card for Zero-Silent-Fallback Disclosures */}
        {structuredError && (
          <StructuredErrorCard {...structuredError} className="my-4" />
        )}

        {/* Durable Experiment Link Banner */}
        {durableExpId && !structuredError && (
          <div
            data-testid="durable-experiment-banner"
            className="p-3.5 rounded-xl bg-purple-950/20 border border-purple-500/40 text-purple-300 font-mono text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-md"
          >
            <div className="flex items-center gap-2.5">
              <div className="w-2.5 h-2.5 rounded-full bg-purple-400 animate-pulse shrink-0" />
              <div>
                <span className="font-bold text-white font-sans text-xs">
                  [ DURABLE EXPERIMENT LINKED: {durableExpId} ]
                </span>
                <span className="ml-2 text-[10px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 uppercase">
                  VERIFIED RUN
                </span>
              </div>
            </div>
            <div className="text-[11px] text-zinc-400">
              Comparative ODE evaluation derived from recorded parent & candidate setups
            </div>
          </div>
        )}

        {/* Preset Selector Bar */}
        <div className="bg-[#0e0e12] border border-white/10 rounded-xl p-3.5 space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
              <Sliders size={12} className="text-ansys-yellow" />
              Pre-Configured Engineering Hypotheses
            </span>
            <span className="text-[10px] text-gray-500">
              Select an archetype or fine-tune parameters below
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {PRESET_COMPARISONS.map((p) => {
              const active = selectedPreset === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => handleApplyPreset(p)}
                  className={`text-left p-2.5 rounded-lg border transition-all ${
                    active
                      ? "bg-purple-950/30 border-purple-500/40 shadow-sm shadow-purple-950/50"
                      : "bg-white/[0.02] border-white/5 hover:bg-white/[0.04] hover:border-white/10"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs font-semibold text-white mb-0.5">
                    <span>{p.title}</span>
                    {active && <span className="text-[10px] text-purple-400 font-mono">ACTIVE</span>}
                  </div>
                  <div className="text-[10px] text-gray-400 line-clamp-1 mb-1">{p.scenario}</div>
                  <div className="text-[9px] text-gray-500 font-mono">
                    k_s: {p.setupA.k_s / 1000}k → {p.setupB.k_s / 1000}k N/m | c: {p.setupA.c} → {p.setupB.c} Ns/m
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-4 rounded-xl bg-red-950/40 border border-red-500/30 text-red-300 text-xs flex items-center gap-3">
            <AlertTriangle size={16} className="text-red-400 shrink-0" />
            <div>
              <p className="font-semibold text-white">Comparison Solver Error</p>
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* VERDICT COCKPIT & CORE QUESTION BANNER */}
        {comparisonResult && (
          <div className="bg-gradient-to-r from-[#111116] via-[#14141d] to-[#111116] border border-white/10 rounded-2xl p-5 shadow-2xl relative overflow-hidden">
            {/* Background ambient glow */}
            <div className={`absolute top-0 left-0 w-full h-1 ${
              comparisonResult.constraints_passed
                ? "bg-gradient-to-r from-emerald-500 via-ansys-yellow to-purple-500"
                : "bg-gradient-to-r from-amber-500 to-red-500"
            }`} />

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-center">
              {/* Verdict Summary */}
              <div className="lg:col-span-3 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wider uppercase border ${
                    comparisonResult.verdict === "SETUP_B_FAVORED"
                      ? "bg-emerald-950/60 text-emerald-400 border-emerald-500/30"
                      : comparisonResult.verdict === "CONSTRAINT_VIOLATED"
                      ? "bg-red-950/60 text-red-400 border-red-500/30"
                      : "bg-amber-950/60 text-amber-400 border-amber-500/30"
                  }`}>
                    {comparisonResult.verdict.replace(/_/g, " ")}
                  </span>

                  <ValidationBadge
                    status={comparisonResult.validation_state}
                  />

                  <ConfidenceIndicator
                    confidence={comparisonResult.confidence}
                    sourceTag="ODE SOLVER CONFIDENCE"
                  />

                  <span className="text-[10px] text-gray-500 font-mono">
                    Rig R²: {comparisonResult.evidence.correlation_r2 != null
                      ? comparisonResult.evidence.correlation_r2.toFixed(2)
                      : "N/A"}
                  </span>
                </div>

                <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">
                  {comparisonResult.verdict_summary}
                </h2>

                <p className="text-xs text-gray-400 leading-relaxed max-w-4xl">
                  {comparisonResult.engineering_causality[0] || "Parametric adjustments perturb chassis state-space trajectory."}
                </p>
              </div>

              {/* Action Decision Pill */}
              <div className="lg:col-span-1 flex flex-col sm:flex-row lg:flex-col items-start lg:items-end justify-center gap-2 border-t lg:border-t-0 lg:border-l border-white/10 pt-3 lg:pt-0 lg:pl-6">
                <div className="text-left lg:text-right">
                  <div className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">Decision Recommendation</div>
                  <div className="text-xs font-bold text-ansys-yellow mt-0.5">
                    {comparisonResult.constraints_passed ? "Ready for 4-Post Rig / Dyno Test" : "Reject: Constraint Violation"}
                  </div>
                </div>
                <button
                  onClick={handleTestThisChange}
                  className="w-full sm:w-auto px-4 py-2 rounded-lg bg-signal/15 hover:bg-signal/25 border border-signal/40 text-signal text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
                >
                  <Zap size={13} />
                  <span>[ TEST THIS CHANGE ]</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 6-SECTION COMPARATIVE BREAKDOWN */}
        {comparisonResult && (
          <div className="space-y-6">

            {/* GRID: WHAT CHANGED vs WHAT IMPROVED vs WHAT GOT WORSE */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

              {/* SECTION 1: WHAT CHANGED */}
              <div className="bg-[#0e0e12] border border-white/10 rounded-xl p-4 flex flex-col h-full">
                <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400">
                      <Sliders size={13} />
                    </div>
                    <h3 className="text-xs font-bold text-white tracking-wider uppercase">
                      1. What Changed (Inputs)
                    </h3>
                  </div>
                  <span className="text-[10px] font-mono text-gray-400">
                    {comparisonResult.what_changed.length} altered
                  </span>
                </div>

                <div className="space-y-2 flex-1 overflow-y-auto max-h-[360px] pr-1">
                  {comparisonResult.what_changed.map((change, i) => (
                    <div
                      key={i}
                      className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5 hover:border-white/10 transition-colors"
                    >
                      <div className="flex items-center justify-between text-xs font-semibold text-white">
                        <span>{change.parameter.toUpperCase()}</span>
                        <span className={`font-mono text-xs ${
                          change.delta_pct > 0 ? "text-purple-400" : "text-cyan-400"
                        }`}>
                          {change.delta_pct > 0 ? "+" : ""}{change.delta_pct.toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono mt-1">
                        <span>Setup A: {change.setup_a} {change.unit}</span>
                        <ArrowRight size={10} className="text-gray-600" />
                        <span className="text-gray-200 font-semibold">Setup B: {change.setup_b} {change.unit}</span>
                      </div>
                      <div className="text-[10px] text-gray-500 mt-1">
                        Δ Absolute: {change.delta_abs > 0 ? "+" : ""}{change.delta_abs} {change.unit}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* SECTION 2: WHAT IMPROVED */}
              <div className="bg-[#0e0e12] border border-emerald-500/20 rounded-xl p-4 flex flex-col h-full shadow-lg shadow-emerald-950/10">
                <div className="flex items-center justify-between pb-3 border-b border-emerald-500/20 mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                      <TrendingUp size={13} />
                    </div>
                    <h3 className="text-xs font-bold text-emerald-300 tracking-wider uppercase">
                      2. What Improved
                    </h3>
                  </div>
                  <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-500/30">
                    {comparisonResult.what_improved.length} advantages
                  </span>
                </div>

                <div className="space-y-2 flex-1 overflow-y-auto max-h-[360px] pr-1">
                  {comparisonResult.what_improved.length === 0 ? (
                    <div className="text-center py-8 text-xs text-gray-500">
                      No quantified metrics showed net improvement.
                    </div>
                  ) : (
                    comparisonResult.what_improved.map((imp, i) => (
                      <div
                        key={i}
                        className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-500/20 space-y-1.5"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-white">{imp.metric}</span>
                          <span className="font-mono font-bold text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded text-[11px]">
                            {imp.delta_pct > 0 ? "+" : ""}{imp.delta_pct.toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
                          <span>A: {imp.baseline.toFixed(2)} {imp.unit}</span>
                          <ArrowRight size={10} className="text-emerald-500/50" />
                          <span className="text-emerald-300 font-semibold">B: {imp.candidate.toFixed(2)} {imp.unit}</span>
                        </div>
                        <div className="text-[10px] text-gray-400 leading-tight">
                          {imp.explanation || imp.reason}
                        </div>
                        <div className="pt-1 flex justify-end">
                          <WhyButton
                            title={`Mechanism: ${imp.metric}`}
                            provenance={{
                              result: `${imp.delta_pct > 0 ? "+" : ""}${imp.delta_pct.toFixed(1)}%`,
                              source: "Quarter-Car ODE Solver RK45",
                              method: "solve_ivp integration across harmonic road profile",
                              modelVersion: "QCAR-ODE-RK45-v2.1",
                              solver: comparisonResult.evidence.solver,
                              backend: "NumPy / SciPy Vectorized C-Extension",
                              validation: comparisonResult.validation_state,
                              confidence: comparisonResult.confidence,
                            }}
                          />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* SECTION 3: WHAT GOT WORSE (MANDATORY TRADEOFF) */}
              <div className="bg-[#0e0e12] border border-amber-500/20 rounded-xl p-4 flex flex-col h-full shadow-lg shadow-amber-950/10">
                <div className="flex items-center justify-between pb-3 border-b border-amber-500/20 mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
                      <TrendingDown size={13} />
                    </div>
                    <h3 className="text-xs font-bold text-amber-300 tracking-wider uppercase">
                      3. What Got Worse (Tradeoffs)
                    </h3>
                  </div>
                  <span className="text-[10px] font-mono text-amber-400 bg-amber-950/50 px-2 py-0.5 rounded border border-amber-500/30">
                    Mandatory Exposure
                  </span>
                </div>

                <div className="space-y-2 flex-1 overflow-y-auto max-h-[360px] pr-1">
                  {comparisonResult.what_got_worse.length === 0 ? (
                    <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 text-xs text-gray-400">
                      Secondary tradeoffs below detection threshold (&lt;0.5%).
                    </div>
                  ) : (
                    comparisonResult.what_got_worse.map((reg, i) => (
                      <div
                        key={i}
                        className="p-3 rounded-lg bg-amber-950/20 border border-amber-500/20 space-y-1.5"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-white">{reg.metric}</span>
                          <span className="font-mono font-bold text-amber-400 bg-amber-950/80 px-2 py-0.5 rounded text-[11px]">
                            {reg.delta_pct > 0 ? "+" : ""}{reg.delta_pct.toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
                          <span>A: {reg.baseline.toFixed(2)} {reg.unit}</span>
                          <ArrowRight size={10} className="text-amber-500/50" />
                          <span className="text-amber-300 font-semibold">B: {reg.candidate.toFixed(2)} {reg.unit}</span>
                        </div>
                        <div className="text-[10px] text-gray-400 leading-tight">
                          {reg.explanation || reg.reason}
                        </div>
                        <div className="pt-1 flex justify-end">
                          <WhyButton
                            title={`Tradeoff Penalty: ${reg.metric}`}
                            provenance={{
                              result: `${reg.delta_pct > 0 ? "+" : ""}${reg.delta_pct.toFixed(1)}%`,
                              source: "Quarter-Car ODE Solver RK45",
                              method: "Every suspension parameter adjustment carries mechanical tradeoffs",
                              modelVersion: "QCAR-ODE-RK45-v2.1",
                              solver: comparisonResult.evidence.solver,
                              backend: "NumPy / SciPy Vectorized C-Extension",
                              validation: comparisonResult.validation_state,
                              confidence: comparisonResult.confidence,
                            }}
                          />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

            </div>

            {/* SECTION 4: ENGINEERING CAUSALITY CHAIN */}
            <div className="bg-[#0e0e12] border border-white/10 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-white/10">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-md bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
                    <Sparkles size={13} />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-white tracking-wider uppercase">
                      4. Engineering Causality Chain
                    </h3>
                    <p className="text-[10px] text-gray-500">
                      Step-by-step physical mechanism linking input parameter delta to dynamic chassis reaction.
                    </p>
                  </div>
                </div>

                <span className="text-[10px] font-mono text-purple-400 bg-purple-950/40 px-2.5 py-1 rounded border border-purple-500/30">
                  Epistemic Phrasing: &quot;Associated With&quot;
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                {comparisonResult.engineering_causality.map((clause, idx) => (
                  <div
                    key={idx}
                    className="p-3 rounded-lg bg-white/[0.02] border border-white/5 relative flex flex-col justify-between space-y-2 group hover:border-purple-500/30 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono font-bold text-purple-400 bg-purple-950/60 px-1.5 py-0.5 rounded">
                        Step 0{idx + 1}
                      </span>
                      <span className="text-[9px] text-gray-500 uppercase font-mono">Causality Node</span>
                    </div>
                    <p className="text-xs text-gray-300 leading-relaxed">
                      {clause}
                    </p>
                    <div className="text-[9px] text-gray-500 pt-1 border-t border-white/5 font-mono">
                      Mechanics Rule: Verified
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* GRID: SECTION 5 (EVIDENCE & CONSTRAINTS) & SECTION 6 (CONFIDENCE & LIMITATIONS) */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

              {/* SECTION 5: EVIDENCE & OPERATIONAL CONSTRAINTS */}
              <div className="bg-[#0e0e12] border border-white/10 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-white/10">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md bg-ansys-yellow/10 border border-ansys-yellow/30 flex items-center justify-center text-ansys-yellow">
                      <FileCheck2 size={13} />
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-white tracking-wider uppercase">
                        5. Evidence & Boundary Constraints
                      </h3>
                      <p className="text-[10px] text-gray-500">
                        Physical travel envelopes, normal load margins, and 7-post rig correlation.
                      </p>
                    </div>
                  </div>

                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                    comparisonResult.constraints_passed
                      ? "bg-emerald-950/50 text-emerald-400 border-emerald-500/30"
                      : "bg-red-950/50 text-red-400 border-red-500/30"
                  }`}>
                    {comparisonResult.constraints_passed ? "ALL CONSTRAINTS PASSED" : "LIMIT VIOLATIONS"}
                  </span>
                </div>

                <div className="space-y-2.5">
                  {comparisonResult.constraint_details.map((con, idx) => (
                    <div
                      key={idx}
                      className={`p-3 rounded-lg border flex items-center justify-between gap-4 ${
                        con.passed
                          ? "bg-white/[0.02] border-white/5"
                          : "bg-red-950/20 border-red-500/30"
                      }`}
                    >
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          {con.passed ? (
                            <CheckCircle2 size={13} className="text-emerald-400" />
                          ) : (
                            <AlertTriangle size={13} className="text-red-400" />
                          )}
                          <span className="text-xs font-semibold text-white">{con.constraint}</span>
                        </div>
                        <p className="text-[10px] text-gray-400 pl-5">{con.detail}</p>
                      </div>

                      <div className="text-right shrink-0">
                        <div className="text-xs font-mono font-bold text-white">{con.actual}</div>
                        <div className="text-[10px] text-gray-500 font-mono">Limit: {con.limit}</div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Evidence Rig Provenance */}
                <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1.5 text-xs">
                  <div className="flex items-center justify-between text-[11px] text-gray-400">
                    <span>Validation Benchmarks:</span>
                    <span className="text-white font-mono">{comparisonResult.evidence.benchmarks}</span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-gray-400">
                    <span>Rig Correlation (R²):</span>
                    <span className="text-ansys-yellow font-mono font-bold">
                      {comparisonResult.evidence.correlation_r2.toFixed(3)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-gray-400">
                    <span>Numerical Solver:</span>
                    <span className="text-gray-300 font-mono text-[10px]">{comparisonResult.evidence.solver}</span>
                  </div>
                </div>
              </div>

              {/* SECTION 6: CONFIDENCE & MODEL LIMITATIONS */}
              <div className="bg-[#0e0e12] border border-white/10 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-white/10">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                      <ShieldCheck size={13} />
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-white tracking-wider uppercase">
                        6. Confidence & Model Domain Limitations
                      </h3>
                      <p className="text-[10px] text-gray-500">
                        Never overstate confidence. Explicit boundary conditions.
                      </p>
                    </div>
                  </div>

                  <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/40 px-2 py-0.5 rounded border border-cyan-500/30">
                    Domain Bounded
                  </span>
                </div>

                <div className="space-y-3 text-xs">
                  <div className="p-3 rounded-lg bg-cyan-950/20 border border-cyan-500/20 space-y-1">
                    <div className="flex items-center gap-1.5 text-cyan-300 font-semibold">
                      <Info size={13} />
                      <span>Decisive Readiness: Track Test Ready (with Caveats)</span>
                    </div>
                    <p className="text-[11px] text-gray-300 leading-relaxed">
                      Numerical state stability confirmed under nominal road harmonic inputs. Prior to high-speed curbs, physical bump stop rubber progressive stiffness should be measured on damper dyno.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                      Physics Engine Domain Limitations:
                    </div>
                    <ul className="space-y-1.5">
                      {comparisonResult.evidence.limitations.map((lim, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-[11px] text-gray-400">
                          <span className="text-ansys-yellow mt-0.5">•</span>
                          <span>{lim}</span>
                        </li>
                      ))}
                      <li className="flex items-start gap-2 text-[11px] text-gray-400">
                        <span className="text-ansys-yellow mt-0.5">•</span>
                        <span>Damper cavitation and blow-off bypass under severe kerb strikes exceeding 1.8 m/s are linearized.</span>
                      </li>
                    </ul>
                  </div>

                  {/* Test CTA inside card */}
                  <div className="pt-2 border-t border-white/10 flex items-center justify-between">
                    <span className="text-[10px] text-gray-500">
                      Want to verify this candidate in the 1-Click Builder?
                    </span>
                    <button
                      onClick={handleTestThisChange}
                      className="px-3 py-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] border border-white/10 text-xs text-white font-medium flex items-center gap-1.5 transition-colors"
                    >
                      <span>Proceed to Experiment</span>
                      <ArrowRight size={12} />
                    </button>
                  </div>
                </div>
              </div>

            </div>

          </div>
        )}

      </main>
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#070709] text-white p-8">Loading comparative intelligence...</div>}>
      <PlanGate required="PRO" feature="Setup Compare (A vs B)">
        <CompareContent />
      </PlanGate>
    </Suspense>
  );
}
