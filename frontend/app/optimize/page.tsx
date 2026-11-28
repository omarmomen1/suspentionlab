"use client";

import React, { useState, useEffect, useMemo, Suspense } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Sparkles,
  Play,
  RotateCcw,
  Zap,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Sliders,
  Layers,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Info,
  ShieldCheck,
  Crosshair,
  Award,
  Filter,
} from "lucide-react";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import PlanGate from "../../components/PlanGate";
import {
  ExperimentApi,
  ParetoFrontierResponse,
  ParetoCandidate,
} from "../../lib/api_client";
import {
  ValidationBadge,
  ConfidenceIndicator,
  WhyButton,
} from "../../components/engineering";

function OptimizeContent() {
  const router = useRouter();

  // Parameter grid ranges (wide feasible space for multi-point NSGA-II Pareto frontier)
  const [ksMin, setKsMin] = useState<number>(15000);
  const [ksMax, setKsMax] = useState<number>(55000);
  const [ksSteps, setKsSteps] = useState<number>(6);

  const [cMin, setCMin] = useState<number>(900);
  const [cMax, setCMax] = useState<number>(3900);
  const [cSteps, setCSteps] = useState<number>(6);

  const [roadSpeed, setRoadSpeed] = useState<number>(30); // m/s (~108 km/h)

  // Optimization state
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [frontierData, setFrontierData] = useState<ParetoFrontierResponse | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<ParetoCandidate | null>(null);
  const [filterMode, setFilterMode] = useState<"all" | "pareto" | "feasible">("pareto");
  const [hoveredCandidate, setHoveredCandidate] = useState<ParetoCandidate | null>(null);
  const [lastOptimizedAt, setLastOptimizedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runBatchOptimization = async (userTriggered = false) => {
    setIsRunning(true);
    setError(null);
    setCurrentStep(1); // Generation

    try {
      setTimeout(() => setCurrentStep(2), 300); // ODE Simulation
      setTimeout(() => setCurrentStep(3), 600); // Constraint Check
      setTimeout(() => setCurrentStep(4), 900); // Non-dominated Ranking

      const res = await ExperimentApi.batchOptimize({
        base_params: {
          m_s: 320,
          m_u: 45,
          k_t: 220000,
          MR: 0.85,
        },
        param_ranges: {
          k_s: [ksMin, ksMax, ksSteps],
          c: [cMin, cMax, cSteps],
        },
        road_profile: {
          speed_mps: roadSpeed,
        },
      });

      setFrontierData(res);
      setLastOptimizedAt(new Date().toLocaleTimeString());
      if (res.best_compromise) {
        setSelectedCandidate(res.best_compromise);
      } else if (res.candidates && res.candidates.length > 0) {
        setSelectedCandidate(res.candidates[0]);
      }
      if (userTriggered) {
        setTimeout(() => {
          document.getElementById("pareto-results")?.scrollIntoView({ behavior: "smooth" });
        }, 300);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to execute Pareto batch optimization.");
    } finally {
      setIsRunning(false);
      setCurrentStep(0);
    }
  };

  useEffect(() => {
    runBatchOptimization(false);
  }, []);

  // Filtered candidate list
  const displayedCandidates = useMemo(() => {
    if (!frontierData?.candidates) return [];
    if (filterMode === "pareto") {
      return frontierData.candidates.filter((c) => c.pareto_rank === 0 || c.is_pareto_optimal);
    }
    if (filterMode === "feasible") {
      return frontierData.candidates.filter((c) => c.feasible);
    }
    return frontierData.candidates;
  }, [frontierData, filterMode]);

  // Archetype setups: ensure distinct setups on multi-point Pareto frontiers
  const archetypeBestCompromise = frontierData?.best_compromise;
  const archetypeMaxGrip = useMemo(() => {
    const front = frontierData?.pareto_frontier;
    if (!front || front.length === 0) return null;
    const sorted = [...front].sort(
      (a, b) => (a.objectives.tire_load_variation || 0) - (b.objectives.tire_load_variation || 0)
    );
    return sorted.find((c) => front.length < 3 || c.candidate_id !== archetypeBestCompromise?.candidate_id) ?? sorted[0];
  }, [frontierData, archetypeBestCompromise]);

  const archetypeMaxComfort = useMemo(() => {
    const front = frontierData?.pareto_frontier;
    if (!front || front.length === 0) return null;
    const sorted = [...front].sort(
      (a, b) => (a.objectives.rms_body_accel || 0) - (b.objectives.rms_body_accel || 0)
    );
    return sorted.find(
      (c) =>
        front.length < 3 ||
        (c.candidate_id !== archetypeBestCompromise?.candidate_id && c.candidate_id !== archetypeMaxGrip?.candidate_id)
    ) ?? sorted[0];
  }, [frontierData, archetypeBestCompromise, archetypeMaxGrip]);

  // Scatter plot coordinate calculation
  const plotBounds = useMemo(() => {
    if (!frontierData?.candidates || frontierData.candidates.length === 0) {
      return { minX: 1.0, maxX: 3.0, minY: 200, maxY: 600 };
    }
    const xs = frontierData.candidates.map((c) => c.objectives.rms_body_accel || 1.8);
    const ys = frontierData.candidates.map((c) => c.objectives.tire_load_variation || 400);
    const minX = Math.min(...xs) * 0.92;
    const maxX = Math.max(...xs) * 1.08;
    const minY = Math.min(...ys) * 0.92;
    const maxY = Math.max(...ys) * 1.08;
    return { minX, maxX, minY, maxY };
  }, [frontierData]);

  const handleTestCandidate = (candidate: ParetoCandidate) => {
    const params = new URLSearchParams();
    params.set("clone_from", candidate.candidate_id);
    params.set("optimization_id", "opt-pareto-batch");
    if (candidate.params.k_s) params.set("k_s", candidate.params.k_s.toString());
    if (candidate.params.c) params.set("c", candidate.params.c.toString());
    router.push(`/experiment?${params.toString()}`);
  };

  return (
    <div className="min-h-screen bg-[#070709] text-gray-200">
      <main className="max-w-[1560px] mx-auto px-4 sm:px-6 py-6 space-y-6">

        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
          <div>
            <div className="flex items-center gap-2 text-xs text-zinc-400 mb-1">
              <Link href="/" className="hover:text-white transition-colors">Command Center</Link>
              <span>/</span>
              <Link href="/experiment" className="hover:text-white transition-colors">Hypothesis Testing</Link>
              <span>/</span>
              <span className="text-cyan-400 font-medium">Pareto Optimization</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                <Sparkles size={20} className="animate-pulse" />
              </div>
              <div>
                <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2">
                  Multi-Objective Pareto Optimization
                  <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-950/60 text-cyan-300 font-mono border border-cyan-500/30">
                    Non-Dominated Tradeoff Space
                  </span>
                </h1>
                <p className="text-xs text-gray-400">
                  Explores conflict between <strong className="text-gray-200">Ride Comfort (RMS Accel)</strong> vs <strong className="text-gray-200">Tire Grip (Load Variation)</strong> with constraint guarantees.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              id="run-batch-optimize-btn"
              type="button"
              onClick={() => runBatchOptimization(true)}
              disabled={isRunning}
              className="px-4 py-2 rounded-lg bg-signal hover:bg-[#d6f56e] text-carbon border border-signal text-xs font-bold flex items-center gap-2 transition-colors disabled:opacity-50"
            >
              <Play size={13} className={isRunning ? "animate-spin" : "fill-current"} />
              <span>{isRunning ? "Evaluating Candidates..." : "Run Batch Candidate Optimization"}</span>
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="bg-red-950/40 border border-red-500/40 rounded-xl p-4 flex items-center justify-between text-xs text-red-300 animate-in fade-in duration-150">
            <div className="flex items-center gap-2">
              <AlertTriangle size={16} className="text-red-400 shrink-0" />
              <span><strong>Optimization Failed:</strong> {error}</span>
            </div>
            <button
              type="button"
              onClick={() => runBatchOptimization(true)}
              className="px-3 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-200 rounded font-semibold transition-colors shrink-0 ml-4"
            >
              Retry Optimization
            </button>
          </div>
        )}

        {/* Success / Status Alert when optimized */}
        {lastOptimizedAt && !error && !isRunning && (
          <div className="bg-emerald-950/30 border border-emerald-500/30 rounded-xl px-4 py-2.5 flex items-center justify-between text-xs text-emerald-300 animate-in fade-in duration-150">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
              <span>
                Pareto Frontier generated: <strong>{frontierData?.total_evaluated || ksSteps * cSteps} setups evaluated</strong> ({frontierData?.pareto_optimal_count || 0} non-dominated Pareto designs found).
              </span>
            </div>
            <span className="text-xs text-emerald-500 font-mono">
              Computed at {lastOptimizedAt}
            </span>
          </div>
        )}

        {/* BATCH ITERATION TRACKER */}
        {isRunning && (
          <div className="bg-[#0e0e12] border border-purple-500/30 rounded-xl p-4 space-y-3 animate-in fade-in duration-200">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-white flex items-center gap-2">
                <RotateCcw size={13} className="animate-spin text-purple-400" />
                Batch Optimization Pipeline in Progress
              </span>
              <span className="font-mono text-purple-300 text-xs">
                Stage {currentStep} of 4
              </span>
            </div>

            <div className="grid grid-cols-4 gap-2 text-center text-xs">
              <div className={`p-2 rounded border ${currentStep >= 1 ? "bg-purple-950/60 border-purple-500 text-white" : "bg-white/[0.02] border-white/5 text-zinc-400"}`}>
                <div className="text-xs uppercase font-mono">1. Generation</div>
                <div className="font-bold text-xs mt-0.5">{ksSteps * cSteps} Candidates</div>
              </div>
              <div className={`p-2 rounded border ${currentStep >= 2 ? "bg-purple-950/60 border-purple-500 text-white" : "bg-white/[0.02] border-white/5 text-zinc-400"}`}>
                <div className="text-xs uppercase font-mono">2. ODE Simulation</div>
                <div className="font-bold text-xs mt-0.5">Vectorized solve_ivp</div>
              </div>
              <div className={`p-2 rounded border ${currentStep >= 3 ? "bg-purple-950/60 border-purple-500 text-white" : "bg-white/[0.02] border-white/5 text-zinc-400"}`}>
                <div className="text-xs uppercase font-mono">3. Constraints</div>
                <div className="font-bold text-xs mt-0.5">Travel &lt; 150mm</div>
              </div>
              <div className={`p-2 rounded border ${currentStep >= 4 ? "bg-purple-950/60 border-purple-500 text-white" : "bg-white/[0.02] border-white/5 text-zinc-400"}`}>
                <div className="text-xs uppercase font-mono">4. Pareto Rank</div>
                <div className="font-bold text-xs mt-0.5">Non-Dominated Sort</div>
              </div>
            </div>
          </div>
        )}

        {/* BATCH CONFIGURATION DRAWER */}
        <div className="bg-[#0e0e12] border border-white/10 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-white/10">
            <span className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
              <Sliders size={13} className="text-purple-400" />
              Batch Candidate Grid Parameters
            </span>
            <span className="text-xs text-zinc-400 font-mono">
              Total Grid Size: {ksSteps * cSteps} setups
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            {/* Spring Stiffness Range */}
            <div className="space-y-1.5 bg-white/[0.02] p-3 rounded-lg border border-white/5">
              <div className="flex items-center justify-between font-semibold text-white">
                <span>Spring Rate (k_s)</span>
                <span className="font-mono text-purple-300">{ksMin / 1000}k – {ksMax / 1000}k N/m</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                <div>
                  <label className="text-zinc-400 text-xs">Min (N/m)</label>
                  <input
                    type="number"
                    value={ksMin}
                    onChange={(e) => setKsMin(Number(e.target.value))}
                    step={2000}
                    className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-white font-mono"
                  />
                </div>
                <div>
                  <label className="text-zinc-400 text-xs">Max (N/m)</label>
                  <input
                    type="number"
                    value={ksMax}
                    onChange={(e) => setKsMax(Number(e.target.value))}
                    step={2000}
                    className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-white font-mono"
                  />
                </div>
              </div>
              <div className="flex items-center justify-between text-xs text-zinc-400 pt-1">
                <span>Grid Steps:</span>
                <span className="font-mono text-white">{ksSteps} samples</span>
              </div>
            </div>

            {/* Damping Range */}
            <div className="space-y-1.5 bg-white/[0.02] p-3 rounded-lg border border-white/5">
              <div className="flex items-center justify-between font-semibold text-white">
                <span>Damping Coeff (c)</span>
                <span className="font-mono text-purple-300">{cMin} – {cMax} Ns/m</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                <div>
                  <label className="text-zinc-400 text-xs">Min (Ns/m)</label>
                  <input
                    type="number"
                    value={cMin}
                    onChange={(e) => setCMin(Number(e.target.value))}
                    step={200}
                    className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-white font-mono"
                  />
                </div>
                <div>
                  <label className="text-zinc-400 text-xs">Max (Ns/m)</label>
                  <input
                    type="number"
                    value={cMax}
                    onChange={(e) => setCMax(Number(e.target.value))}
                    step={200}
                    className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-white font-mono"
                  />
                </div>
              </div>
              <div className="flex items-center justify-between text-xs text-zinc-400 pt-1">
                <span>Grid Steps:</span>
                <span className="font-mono text-white">{cSteps} samples</span>
              </div>
            </div>

            {/* Road Speed & Objectives */}
            <div className="space-y-1.5 bg-white/[0.02] p-3 rounded-lg border border-white/5">
              <div className="flex items-center justify-between font-semibold text-white">
                <span>Vehicle Speed</span>
                <span className="font-mono text-signal">{(roadSpeed * 3.6).toFixed(0)} km/h</span>
              </div>
              <div>
                <input
                  type="range"
                  min={15}
                  max={60}
                  value={roadSpeed}
                  onChange={(e) => setRoadSpeed(Number(e.target.value))}
                  className="w-full accent-purple-500 mt-2"
                />
              </div>
              <div className="flex items-center justify-between text-xs text-gray-400 pt-2 border-t border-white/5">
                <span>Objective 1:</span>
                <span className="text-emerald-400 font-semibold">Min RMS Accel (Comfort)</span>
              </div>
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>Objective 2:</span>
                <span className="text-cyan-400 font-semibold">Min Tire Load Var (Grip)</span>
              </div>
            </div>
          </div>
        </div>

        {/* 3 ARCHETYPE COMPROMISE CARDS */}
        {frontierData && (
          <div id="pareto-results" className="grid grid-cols-1 md:grid-cols-3 gap-4 scroll-mt-20">
            {/* Card 1: Best Compromise (Closest to Utopia) */}
            <div className="p-4 rounded-xl bg-gradient-to-b from-purple-950/40 to-[#0e0e12] border border-purple-500/40 space-y-3 relative shadow-lg shadow-purple-950/20">
              <div className="flex items-center justify-between">
                <span className="px-2 py-0.5 rounded text-xs font-bold bg-purple-500 text-black uppercase tracking-wider flex items-center gap-1">
                  <Award size={11} />
                  Best Compromise
                </span>
                <span className="text-xs text-purple-300 font-mono">Utopia Optimum</span>
              </div>

              {archetypeBestCompromise ? (
                <div>
                  <div className="text-sm font-bold text-white mb-1">
                    {archetypeBestCompromise.candidate_id} Balanced Setup
                  </div>
                  <div className="text-xs text-gray-300 font-mono mb-2">
                    k_s: {archetypeBestCompromise.params.k_s} N/m | c: {archetypeBestCompromise.params.c} Ns/m
                  </div>
                  <p className="text-xs text-gray-400 leading-relaxed">
                    {frontierData.best_compromise_explanation}
                  </p>
                  <div className="mt-3 pt-3 border-t border-white/10 flex items-center justify-between">
                    <span className="text-xs text-zinc-400">Pareto Rank: 0 (Non-dominated)</span>
                    <button
                      onClick={() => handleTestCandidate(archetypeBestCompromise)}
                      className="px-2.5 py-1 rounded bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 text-xs font-semibold flex items-center gap-1 transition-colors"
                    >
                      <Zap size={11} />
                      <span>[ TEST THIS CHANGE ]</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-zinc-400">No compromise setup found.</div>
              )}
            </div>

            {/* Card 2: Maximum Grip (Race Focus) */}
            <div className="p-4 rounded-xl bg-gradient-to-b from-cyan-950/30 to-[#0e0e12] border border-cyan-500/30 space-y-3 relative">
              <div className="flex items-center justify-between">
                <span className="px-2 py-0.5 rounded text-xs font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 uppercase tracking-wider">
                  Maximum Grip Archetype
                </span>
                <span className="text-xs text-cyan-400 font-mono">Min Dynamic Load Var</span>
              </div>

              {archetypeMaxGrip ? (
                <div>
                  <div className="text-sm font-bold text-white mb-1">
                    {archetypeMaxGrip.candidate_id} Contact Patch Focus
                  </div>
                  <div className="text-xs text-gray-300 font-mono mb-2">
                    k_s: {archetypeMaxGrip.params.k_s} N/m | c: {archetypeMaxGrip.params.c} Ns/m
                  </div>
                  <p className="text-xs text-gray-400 leading-relaxed">
                    Minimizes normal load oscillations over kerbs and bumps. Yields maximum tire friction coefficient consistency at the expense of higher chassis heave excitation.
                  </p>
                  <div className="mt-3 pt-3 border-t border-white/10 flex items-center justify-between">
                    <span className="text-xs text-zinc-400">Tire Var: {archetypeMaxGrip.objectives.tire_load_variation?.toFixed(0)} N</span>
                    <button
                      onClick={() => handleTestCandidate(archetypeMaxGrip)}
                      className="px-2.5 py-1 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-xs font-semibold flex items-center gap-1 transition-colors"
                    >
                      <Zap size={11} />
                      <span>[ TEST THIS CHANGE ]</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-zinc-400">Evaluating...</div>
              )}
            </div>

            {/* Card 3: Maximum Comfort (Ride Focus) */}
            <div className="p-4 rounded-xl bg-gradient-to-b from-emerald-950/30 to-[#0e0e12] border border-emerald-500/30 space-y-3 relative">
              <div className="flex items-center justify-between">
                <span className="px-2 py-0.5 rounded text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 uppercase tracking-wider">
                  Maximum Comfort Archetype
                </span>
                <span className="text-xs text-emerald-400 font-mono">Min Heave RMS Accel</span>
              </div>

              {archetypeMaxComfort ? (
                <div>
                  <div className="text-sm font-bold text-white mb-1">
                    {archetypeMaxComfort.candidate_id} Isolation Focus
                  </div>
                  <div className="text-xs text-gray-300 font-mono mb-2">
                    k_s: {archetypeMaxComfort.params.k_s} N/m | c: {archetypeMaxComfort.params.c} Ns/m
                  </div>
                  <p className="text-xs text-gray-400 leading-relaxed">
                    Maximizes road bump isolation and reduces driver vibration dose value (VDV). Causes higher pitch and roll gradients under transient braking.
                  </p>
                  <div className="mt-3 pt-3 border-t border-white/10 flex items-center justify-between">
                    <span className="text-xs text-zinc-400">Ride RMS: {archetypeMaxComfort.objectives.rms_body_accel?.toFixed(2)} m/s²</span>
                    <button
                      onClick={() => handleTestCandidate(archetypeMaxComfort)}
                      className="px-2.5 py-1 rounded bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 text-xs font-semibold flex items-center gap-1 transition-colors"
                    >
                      <Zap size={11} />
                      <span>[ TEST THIS CHANGE ]</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-zinc-400">Evaluating...</div>
              )}
            </div>
          </div>
        )}

        {/* INTERACTIVE PARETO FRONTIER SCATTER PLOT & INSPECTOR */}
        {frontierData && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* Left 2 Cols: Interactive Scatter Plot */}
            <div className="lg:col-span-2 bg-[#0e0e12] border border-white/10 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-white/10">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-md bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
                    <Crosshair size={13} />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-white tracking-wider uppercase">
                      Pareto Frontier: Ride Comfort vs Grip Consistency
                    </h3>
                    <p className="text-xs text-zinc-400">
                      Gold stars denote non-dominated optimal tradeoffs. Lower-left is ideal.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 text-xs">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                    <span className="text-xs text-gray-400">Pareto Optimal</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-blue-500/60"></span>
                    <span className="text-xs text-gray-400">Feasible Dominated</span>
                  </div>
                </div>
              </div>

              {/* SVG 2D Interactive Plot */}
              <div className="relative w-full h-[400px] bg-black/40 rounded-xl border border-white/5 p-4 select-none">
                <svg className="w-full h-full" viewBox="0 0 600 350">
                  {/* Grid Lines */}
                  {[0, 1, 2, 3, 4].map((i) => {
                    const y = 30 + i * 65;
                    const x = 50 + i * 110;
                    return (
                      <g key={i}>
                        <line x1="50" y1={y} x2="550" y2={y} stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
                        <line x1={x} y1="30" x2={x} y2="290" stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
                      </g>
                    );
                  })}

                  {/* Axes */}
                  <line x1="50" y1="290" x2="550" y2="290" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" />
                  <line x1="50" y1="30" x2="50" y2="290" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" />

                  {/* Axis Labels */}
                  <text x="300" y="325" fill="#888" fontSize="11" textAnchor="middle" fontFamily="sans-serif">
                    Ride RMS Body Acceleration (m/s²) → [ Lower is more comfortable ]
                  </text>
                  <text x="-160" y="20" fill="#888" fontSize="11" textAnchor="middle" transform="rotate(-90)" fontFamily="sans-serif">
                    Tire Dynamic Load Variation (N) → [ Lower is higher grip ]
                  </text>

                  {/* Utopia Point Indicator */}
                  <circle cx="50" cy="290" r="4" fill="#06B6D4" />
                  <text x="58" y="285" fill="#38bdf8" fontSize="9" fontFamily="monospace">Utopia (Ideal)</text>

                  {/* Connect Pareto optimal points in sorted order */}
                  {(() => {
                    const pPoints = (frontierData?.pareto_frontier || [])
                      .map((c) => {
                        const rawX = c.objectives.rms_body_accel || 1.8;
                        const rawY = c.objectives.tire_load_variation || 400;
                        const normX = 50 + ((rawX - plotBounds.minX) / (plotBounds.maxX - plotBounds.minX)) * 500;
                        const normY = 290 - ((rawY - plotBounds.minY) / (plotBounds.maxY - plotBounds.minY)) * 260;
                        return { x: normX, y: normY, c };
                      })
                      .sort((a, b) => a.x - b.x);

                    if (pPoints.length < 2) return null;
                    const pathStr = pPoints.reduce((acc, p, idx) => `${acc} ${idx === 0 ? "M" : "L"} ${p.x} ${p.y}`, "");

                    return (
                      <path
                        d={pathStr}
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth="2"
                        strokeDasharray="4 2"
                        opacity="0.8"
                      />
                    );
                  })()}

                  {/* Scatter Candidate Points */}
                  {frontierData?.candidates.map((cand) => {
                    const rawX = cand.objectives.rms_body_accel || 1.8;
                    const rawY = cand.objectives.tire_load_variation || 400;
                    const cx = 50 + ((rawX - plotBounds.minX) / (plotBounds.maxX - plotBounds.minX)) * 500;
                    const cy = 290 - ((rawY - plotBounds.minY) / (plotBounds.maxY - plotBounds.minY)) * 260;
                    const isSelected = selectedCandidate?.candidate_id === cand.candidate_id;
                    const isOptimal = cand.pareto_rank === 0 || cand.is_pareto_optimal;

                    return (
                      <g
                        key={cand.candidate_id}
                        className="cursor-pointer transition-transform"
                        onClick={() => setSelectedCandidate(cand)}
                        onMouseEnter={() => setHoveredCandidate(cand)}
                        onMouseLeave={() => setHoveredCandidate(null)}
                      >
                        {isSelected && (
                          <circle cx={cx} cy={cy} r="14" fill="none" stroke="#C8F04B" strokeWidth="2" opacity="0.7" />
                        )}
                        <circle
                          cx={cx}
                          cy={cy}
                          r={isOptimal ? 7 : 4.5}
                          fill={isOptimal ? "#f59e0b" : "#3b82f6"}
                          stroke={isSelected ? "#ffffff" : isOptimal ? "#78350f" : "#1e3a8a"}
                          strokeWidth={isOptimal ? 2 : 1}
                        />
                        {isOptimal && (
                          <text
                            x={cx}
                            y={cy - 10}
                            fill="#f59e0b"
                            fontSize="9"
                            fontFamily="monospace"
                            textAnchor="middle"
                            fontWeight="bold"
                          >
                            {cand.candidate_id}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </svg>

                {/* Floating Hover Tooltip */}
                {hoveredCandidate && (
                  <div className="absolute top-4 right-4 bg-[#14141c] border border-white/20 p-2.5 rounded-lg shadow-xl text-xs space-y-1 z-10 pointer-events-none">
                    <div className="font-bold text-white flex items-center justify-between gap-3">
                      <span>{hoveredCandidate.candidate_id}</span>
                      <span className={`text-xs font-mono px-1 rounded ${
                        (hoveredCandidate.pareto_rank === 0 || hoveredCandidate.is_pareto_optimal)
                          ? "bg-amber-500/20 text-amber-300"
                          : "bg-blue-500/20 text-blue-300"
                      }`}>
                        {(hoveredCandidate.pareto_rank === 0 || hoveredCandidate.is_pareto_optimal)
                          ? "PARETO OPTIMAL"
                          : "FEASIBLE"}
                      </span>
                    </div>
                    <div className="text-xs text-gray-300 font-mono">
                      k_s: {hoveredCandidate.params.k_s} N/m | c: {hoveredCandidate.params.c} Ns/m
                    </div>
                    <div className="text-xs text-gray-400">
                      Ride RMS: <strong className="text-white">{hoveredCandidate.objectives.rms_body_accel?.toFixed(2)} m/s²</strong> | Tire Var: <strong className="text-white">{hoveredCandidate.objectives.tire_load_variation?.toFixed(0)} N</strong>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Right Col: Candidate Inspector Card */}
            <div className="lg:col-span-1 bg-[#0e0e12] border border-white/10 rounded-xl p-5 flex flex-col justify-between space-y-4">
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md bg-signal/10 border border-signal/30 flex items-center justify-center text-signal">
                      <Sliders size={13} />
                    </div>
                    <h3 className="text-xs font-bold text-white tracking-wider uppercase">
                      Candidate Inspector
                    </h3>
                  </div>
                  {selectedCandidate && (
                    <span className="text-xs font-mono font-bold text-signal">
                      {selectedCandidate.candidate_id}
                    </span>
                  )}
                </div>

                {selectedCandidate ? (
                  <div className="space-y-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Classification:</span>
                      <span className={`px-2 py-0.5 rounded text-xs font-bold font-mono ${
                        selectedCandidate.pareto_rank === 0 || selectedCandidate.is_pareto_optimal
                          ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                          : "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                      }`}>
                        {selectedCandidate.pareto_rank === 0 || selectedCandidate.is_pareto_optimal
                          ? "Pareto Optimal (Rank 0)"
                          : `Dominated (Rank ${selectedCandidate.pareto_rank})`}
                      </span>
                    </div>

                    {/* Parameters Box */}
                    <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1.5 font-mono text-xs">
                      <div className="text-gray-400 text-xs uppercase tracking-wider font-semibold font-sans">
                        Setup Parameters:
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Spring Stiffness (k_s):</span>
                        <span className="text-white font-bold">{selectedCandidate.params.k_s} N/m</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Damping (c):</span>
                        <span className="text-white font-bold">{selectedCandidate.params.c} Ns/m</span>
                      </div>
                    </div>

                    {/* KPIs Box */}
                    <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1.5 font-mono text-xs">
                      <div className="text-gray-400 text-xs uppercase tracking-wider font-semibold font-sans">
                        Simulated Objectives:
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Ride RMS Accel:</span>
                        <span className="text-emerald-300 font-bold">
                          {selectedCandidate.objectives.rms_body_accel?.toFixed(2)} m/s²
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Tire Load Var:</span>
                        <span className="text-cyan-300 font-bold">
                          {selectedCandidate.objectives.tire_load_variation?.toFixed(0)} N
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Peak Travel:</span>
                        <span className="text-gray-200">
                          {selectedCandidate.constraints.peak_susp_travel?.toFixed(1)} mm
                        </span>
                      </div>
                    </div>

                    {/* Physical Explanation */}
                    <div className="p-3 rounded-lg bg-purple-950/20 border border-purple-500/20 text-xs text-gray-300 leading-relaxed">
                      {selectedCandidate.explanation}
                    </div>

                    {/* Epistemic disclaimer */}
                    <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                      <ShieldCheck size={12} className="text-signal shrink-0" />
                      <span>UNVALIDATED: Numerical simulation requires damper dyno sign-off.</span>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-12 text-xs text-zinc-400">
                    Click any point on the scatter plot to inspect its tradeoffs.
                  </div>
                )}
              </div>

              {selectedCandidate && (
                <button
                  data-testid="btn-test-candidate-inspector"
                  onClick={() => handleTestCandidate(selectedCandidate)}
                  className="w-full py-2.5 rounded-lg bg-signal hover:bg-[#d6f56e] text-carbon border border-signal text-xs font-bold flex items-center justify-center gap-2 transition-colors"
                >
                  <Zap size={14} />
                  <span>[ TEST THIS CANDIDATE IN BUILDER ]</span>
                </button>
              )}
            </div>

          </div>
        )}

        {/* CANDIDATE RANKING TABLE */}
        {frontierData && (
          <div className="bg-[#0e0e12] border border-white/10 rounded-xl p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-md bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
                  <Filter size={13} />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-white tracking-wider uppercase">
                    Evaluated Candidate Ranking Table
                  </h3>
                  <p className="text-xs text-zinc-400">
                    Sorted by Pareto optimality and Euclidean distance to Utopia point.
                  </p>
                </div>
              </div>

              {/* Filter Tabs */}
              <div className="flex items-center gap-1.5 bg-black/40 p-1 rounded-lg border border-white/5 text-xs">
                <button
                  onClick={() => setFilterMode("pareto")}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    filterMode === "pareto"
                      ? "bg-signal text-carbon font-bold shadow-sm"
                      : "text-gray-400 hover:text-white"
                  }`}
                >
                  Pareto Optimal ({frontierData.pareto_optimal_count})
                </button>
                <button
                  onClick={() => setFilterMode("feasible")}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    filterMode === "feasible"
                      ? "bg-signal text-carbon font-bold shadow-sm"
                      : "text-gray-400 hover:text-white"
                  }`}
                >
                  All Feasible ({frontierData.feasible_count})
                </button>
                <button
                  onClick={() => setFilterMode("all")}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    filterMode === "all"
                      ? "bg-signal text-carbon font-bold shadow-sm"
                      : "text-gray-400 hover:text-white"
                  }`}
                >
                  All Grid ({frontierData.total_evaluated})
                </button>
              </div>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-white/10 text-xs text-gray-400 uppercase">
                    <th className="py-2.5 px-3">Candidate ID</th>
                    <th className="py-2.5 px-3">Spring (k_s)</th>
                    <th className="py-2.5 px-3">Damping (c)</th>
                    <th className="py-2.5 px-3">Ride RMS Accel</th>
                    <th className="py-2.5 px-3">Tire Load Var</th>
                    <th className="py-2.5 px-3">Travel</th>
                    <th className="py-2.5 px-3">Rank</th>
                    <th className="py-2.5 px-3">Classification</th>
                    <th className="py-2.5 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {displayedCandidates.map((cand) => {
                    const isSelected = selectedCandidate?.candidate_id === cand.candidate_id;
                    const isBest = frontierData.best_compromise?.candidate_id === cand.candidate_id;

                    return (
                      <tr
                        key={cand.candidate_id}
                        onClick={() => setSelectedCandidate(cand)}
                        className={`cursor-pointer hover:bg-white/[0.03] transition-colors ${
                          isSelected ? "bg-purple-950/30" : ""
                        }`}
                      >
                        <td className="py-2.5 px-3 font-bold text-white flex items-center gap-1.5">
                          {isBest && <Award size={13} className="text-signal" />}
                          <span>{cand.candidate_id}</span>
                        </td>
                        <td className="py-2.5 px-3 text-gray-300">{cand.params.k_s} N/m</td>
                        <td className="py-2.5 px-3 text-gray-300">{cand.params.c} Ns/m</td>
                        <td className="py-2.5 px-3 text-emerald-400">
                          {cand.objectives.rms_body_accel?.toFixed(2)} m/s²
                        </td>
                        <td className="py-2.5 px-3 text-cyan-400">
                          {cand.objectives.tire_load_variation?.toFixed(0)} N
                        </td>
                        <td className="py-2.5 px-3 text-gray-400">
                          {cand.constraints.peak_susp_travel?.toFixed(1)} mm
                        </td>
                        <td className="py-2.5 px-3">
                          <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                            (cand.pareto_rank === 0 || cand.is_pareto_optimal) ? "bg-amber-500/20 text-amber-300" : "bg-white/5 text-gray-400"
                          }`}>
                            Rank {cand.pareto_rank}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          {isBest ? (
                            <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 text-xs font-semibold border border-purple-500/30 font-sans">
                              Best Compromise
                            </span>
                          ) : (cand.pareto_rank === 0 || cand.is_pareto_optimal) ? (
                            <span className="text-amber-400 text-xs font-sans">Pareto Optimal</span>
                          ) : (
                            <span className="text-zinc-400 text-xs font-sans">Dominated</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <button
                            data-testid="btn-test-candidate-table"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleTestCandidate(cand);
                            }}
                            className="px-2.5 py-1 rounded bg-signal/15 hover:bg-signal/25 border border-signal/30 text-signal text-xs font-sans font-semibold transition-colors inline-flex items-center gap-1"
                          >
                            <Zap size={11} />
                            <span>Test</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </main>
    </div>
  );
}

export default function OptimizePage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#070709] text-white p-8">Loading Pareto optimization...</div>}>
      <PlanGate required="PRO" feature="Multi-Objective Pareto Setup Optimizer">
        <OptimizeContent />
      </PlanGate>
    </Suspense>
  );
}
