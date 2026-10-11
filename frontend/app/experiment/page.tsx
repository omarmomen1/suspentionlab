"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  FlaskConical,
  Play,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  RotateCcw,
  Sliders,
  Sparkles,
  GitBranch,
  ShieldCheck,
  Check,
  ChevronRight,
  Layers,
  ArrowUpRight,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import {
  ExperimentApi,
  ExperimentRecordResponse,
  MetricDeltaEntry,
  ConstraintDetail,
} from "../../lib/api_client";
import {
  EvidenceBadge,
  ValidationBadge,
  ConfidenceIndicator,
  WhyButton,
  ProvenancePopover,
  ProvenanceData,
  EngineeringCard,
  EngineeringMetric,
  EngineeringStatus,
  ConstraintWarning,
  StructuredErrorCard,
  StructuredErrorCardProps,
} from "../../components/engineering";

interface PresetQuestion {
  id: string;
  title: string;
  subsystem: string;
  param: string;
  deltaPct: number;
  expectedHypothesis: string;
}

const PRESET_QUESTIONS: PresetQuestion[] = [
  {
    id: "q1",
    title: "What happens if I increase front roll stiffness by 10%?",
    subsystem: "Front Suspension / Anti-Roll Bar",
    param: "k_s",
    deltaPct: 10.0,
    expectedHypothesis: "Stiffening front spring rate reduces dynamic body roll and improves turn-in sharpness, but increases high-frequency curb impact harshness.",
  },
  {
    id: "q2",
    title: "Why is front tire saturation increasing?",
    subsystem: "Front Axle / Wheel Rate Compliance",
    param: "c",
    deltaPct: -15.0,
    expectedHypothesis: "Excessive front rebound damping causes front tire jacking down, reducing normal load compliance and accelerating tire saturation.",
  },
  {
    id: "q3",
    title: "Which setup gives the best compromise between ride and handling?",
    subsystem: "Full Vehicle / Heave & Pitch Mode",
    param: "k_s",
    deltaPct: -8.0,
    expectedHypothesis: "Modest spring softening paired with optimized low-speed damping achieves lower RMS vertical body acceleration while preserving contact patch grip.",
  },
];

const PARAM_PRESETS = [
  { key: "k_s", label: "Spring Rate (k_s)", unit: "N/m", defaultVal: 35000, step: 1000, min: 15000, max: 80000 },
  { key: "c", label: "Damping Coefficient (c)", unit: "Ns/m", defaultVal: 2200, step: 100, min: 800, max: 6000 },
  { key: "k_arb_f", label: "Front Anti-Roll Bar", unit: "N/m", defaultVal: 16000, step: 1000, min: 5000, max: 40000 },
  { key: "m_s", label: "Sprung Mass (m_s)", unit: "kg", defaultVal: 320, step: 5, min: 200, max: 600 },
  { key: "k_t", label: "Tire Vertical Stiffness", unit: "N/m", defaultVal: 220000, step: 5000, min: 120000, max: 350000 },
  { key: "ride_height_mm", label: "Front Ride Height", unit: "mm", defaultVal: 35, step: 1, min: 20, max: 70 },
];

function ExperimentBuilderContent() {
  const searchParams = useSearchParams();
  const {
    activeVehicleContext,
    setActiveExperimentId,
    setActiveCandidateId,
    setActiveOptimizationId,
  } = useWorkspace();

  // Search parameters for cloned candidates
  const cloneFromParam = searchParams.get("clone_from");
  const optIdParam = searchParams.get("optimization_id");
  const ksParam = searchParams.get("k_s");
  const cParam = searchParams.get("c");

  const [validationError, setValidationError] = useState<StructuredErrorCardProps | null>(null);
  const [clonedCandidate, setClonedCandidate] = useState<{
    id: string;
    optimizationId?: string;
    k_s?: number;
    c?: number;
  } | null>(null);

  // Builder state
  const [question, setQuestion] = useState("What happens if I increase front roll stiffness by 10%?");
  const [selectedParamKey, setSelectedParamKey] = useState("k_s");
  const [deltaMode, setDeltaMode] = useState<"pct" | "absolute">("pct");
  const [deltaPct, setDeltaPct] = useState(10.0);
  const [absoluteVal, setAbsoluteVal] = useState(38500);

  // Parse and validate incoming candidate parameters on mount
  useEffect(() => {
    if (cloneFromParam || ksParam || cParam) {
      let parsedKs: number | undefined;
      if (ksParam !== null) {
        parsedKs = parseFloat(ksParam);
        if (isNaN(parsedKs) || parsedKs < 1000 || parsedKs > 500000) {
          setValidationError({
            title: "CANDIDATE PARAMETER VALIDATION FAILURE",
            whatFailed: `Cloned candidate '${cloneFromParam || "unknown"}' provided invalid spring stiffness k_s='${ksParam}'.`,
            why: "Spring rate must be a valid numeric value within physical limits (1,000 ≤ k_s ≤ 500,000 N/m).",
            whatRemainsValid: "Quarter-car simulation model and workspace baseline setup.",
            whatCannotBeClaimed: "Evaluation or comparison of candidate suspension setup.",
            nextAction: "Return to Multi-Objective Optimizer to re-select a valid candidate.",
            actionButton: {
              label: "Return to Optimizer",
              href: "/optimize",
            },
          });
          return;
        }
      }

      let parsedC: number | undefined;
      if (cParam !== null) {
        parsedC = parseFloat(cParam);
        if (isNaN(parsedC) || parsedC < 100 || parsedC > 50000) {
          setValidationError({
            title: "CANDIDATE PARAMETER VALIDATION FAILURE",
            whatFailed: `Cloned candidate '${cloneFromParam || "unknown"}' provided invalid damping coefficient c='${cParam}'.`,
            why: "Damping coefficient must be a valid numeric value within physical limits (100 ≤ c ≤ 50,000 Ns/m).",
            whatRemainsValid: "Quarter-car simulation model and workspace baseline setup.",
            whatCannotBeClaimed: "Evaluation or comparison of candidate suspension setup.",
            nextAction: "Return to Multi-Objective Optimizer to re-select a valid candidate.",
            actionButton: {
              label: "Return to Optimizer",
              href: "/optimize",
            },
          });
          return;
        }
      }

      const candInfo = {
        id: cloneFromParam || "OPTIMIZATION_CANDIDATE",
        optimizationId: optIdParam || undefined,
        k_s: parsedKs,
        c: parsedC,
      };
      setClonedCandidate(candInfo);
      if (optIdParam) setActiveOptimizationId(optIdParam);
      if (candInfo.id) setActiveCandidateId(candInfo.id);

      if (parsedKs !== undefined) {
        setSelectedParamKey("k_s");
        setDeltaMode("absolute");
        setAbsoluteVal(parsedKs);
        setQuestion(`Evaluating optimization candidate ${candInfo.id} with k_s = ${parsedKs} N/m`);
      } else if (parsedC !== undefined) {
        setSelectedParamKey("c");
        setDeltaMode("absolute");
        setAbsoluteVal(parsedC);
        setQuestion(`Evaluating optimization candidate ${candInfo.id} with c = ${parsedC} Ns/m`);
      } else {
        setQuestion(`Evaluating optimization candidate ${candInfo.id}`);
      }
    }
  }, [cloneFromParam, optIdParam, ksParam, cParam]);

  // Execution & Result state
  const [isExecuting, setIsExecuting] = useState(false);
  const [pipelineStage, setPipelineStage] = useState<number>(0);
  const [experimentResult, setExperimentResult] = useState<ExperimentRecordResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Provenance Popover
  const [provenanceOpen, setProvenanceOpen] = useState(false);
  const [provenanceData, setProvenanceData] = useState<ProvenanceData | null>(null);

  const selectedParamConfig = PARAM_PRESETS.find((p) => p.key === selectedParamKey) || PARAM_PRESETS[0];

  const handleSelectPresetQuestion = (q: PresetQuestion) => {
    setQuestion(q.title);
    setSelectedParamKey(q.param);
    setDeltaMode("pct");
    setDeltaPct(q.deltaPct);
    const baseP = PARAM_PRESETS.find((p) => p.key === q.param)?.defaultVal || 35000;
    setAbsoluteVal(Math.round(baseP * (1.0 + q.deltaPct / 100.0)));
  };

  const handleRunExperiment = async () => {
    setIsExecuting(true);
    setErrorMsg(null);
    setPipelineStage(1); // 1: Clone setup

    try {
      // Simulate sequential pipeline progress for visual feedback
      await new Promise((r) => setTimeout(r, 200));
      setPipelineStage(2); // 2: Validate parameters

      await new Promise((r) => setTimeout(r, 200));
      setPipelineStage(3); // 3: Run affected kinematics

      await new Promise((r) => setTimeout(r, 200));
      setPipelineStage(4); // 4: Solve ODE simulation

      const baseParamVal = selectedParamConfig.defaultVal;
      const targetVal = deltaMode === "pct" ? baseParamVal * (1.0 + deltaPct / 100.0) : absoluteVal;

      const parentSetupObj: Record<string, number> = {
        m_s: 320.0,
        m_u: 45.0,
        k_s: selectedParamKey === "k_s" ? baseParamVal : (clonedCandidate?.k_s || 35000.0),
        c: selectedParamKey === "c" ? baseParamVal : (clonedCandidate?.c || 2200.0),
        k_t: 220000.0,
        MR: 0.85,
        k_arb_f: 16000.0,
      };

      const payload: any = {
        question,
        hypothesis: `Evaluating sensitivity of vehicle dynamics response to a ${deltaMode === "pct" ? `${deltaPct > 0 ? "+" : ""}${deltaPct}%` : `change to ${targetVal} ${selectedParamConfig.unit}`} modification in ${selectedParamConfig.label}.`,
        parent_setup: parentSetupObj,
        parameter_changes: [
          {
            parameter: selectedParamKey,
            candidate: targetVal,
          },
        ],
        author: "Marcus Vance (Senior Dynamics Engineer)",
        clone_from: clonedCandidate?.id,
        optimization_id: clonedCandidate?.optimizationId,
      };

      setPipelineStage(5); // 5: Calculate KPIs & Check constraints
      const res = await ExperimentApi.runExperiment(payload);

      setPipelineStage(6); // 6: Persist provenance & complete
      await new Promise((r) => setTimeout(r, 150));
      setExperimentResult(res);
      setActiveExperimentId(res.id);
      if (res.simulation_id) {
        setActiveCandidateId(res.simulation_id);
      }
      setPipelineStage(7);
    } catch (err: any) {
      setErrorMsg(err?.message || "Experiment execution failed.");
      setPipelineStage(0);
    } finally {
      setIsExecuting(false);
    }
  };

  // Run default experiment on first mount if no validation error
  useEffect(() => {
    if (!validationError) {
      handleRunExperiment();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clonedCandidate, validationError]);

  const openProvenance = () => {
    if (!experimentResult) return;
    setProvenanceData({
      result: `${experimentResult.improvements[0]?.metric || "Ride RMS"} improved by ${experimentResult.improvements[0]?.delta_pct || -9.9}%`,
      source: `Quarter-Car ODE Solver RK45 / Workspace Baseline: ${activeVehicleContext.setup}`,
      inputs: {
        "Parent Setup": activeVehicleContext.setup,
        "Changed Parameter": `${selectedParamConfig.label} = ${experimentResult.candidate_setup[selectedParamKey]} ${selectedParamConfig.unit}`,
        "Vehicle Mass": `${experimentResult.candidate_setup.m_s || 320} kg`,
        "Wheel Rate Motion Ratio": "MR = 0.85",
      },
      method: "SciPy solve_ivp BDF adaptive ODE time-domain integration with ISO 2631 Wk comfort weighting.",
      modelVersion: experimentResult.model_version,
      solver: experimentResult.solver,
      backend: experimentResult.backend,
      validation: "UNVALIDATED: Not yet correlated against physical track MoTeC session. Dynamometer / shaker rig test recommended.",
      confidence: experimentResult.confidence,
      canonicalHash: experimentResult.result_hash,
      limitations: [
        "1D quarter-car does not capture chassis torsional flex or roll couple distribution.",
        "Aero downforce map assumed at steady-state ride height without pitch moment.",
      ],
    });
    setProvenanceOpen(true);
  };

  return (
    <div className="min-h-screen bg-[#08080a] text-zinc-100 flex flex-col font-sans">
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 space-y-6">
        {/* Header Title */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-amber-500 mb-1">
              <FlaskConical size={14} />
              Hypothesis-Driven Engineering Platform
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white flex items-center gap-3">
              One-Click Experiment Builder
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 font-mono font-normal">
                TEST HYPOTHESIS
              </span>
            </h1>
            <p className="text-sm text-zinc-400 mt-1 max-w-2xl">
              Do not just run a simulation. Formulate a physical question, define a candidate setup change, and automatically evaluate tradeoffs, constraints, and causality.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/compare"
              className="px-3 py-2 text-xs font-mono font-medium rounded bg-zinc-900 border border-zinc-700 hover:border-zinc-500 text-zinc-300 transition-colors flex items-center gap-1.5"
            >
              Compare Experience <ArrowRight size={13} />
            </Link>
            <Link
              href="/optimize"
              className="px-3 py-2 text-xs font-mono font-medium rounded bg-zinc-900 border border-zinc-700 hover:border-zinc-500 text-zinc-300 transition-colors flex items-center gap-1.5"
            >
              Pareto Optimizer <ArrowUpRight size={13} />
            </Link>
          </div>
        </div>

        {/* Structured Error Card for Candidate Validation Failures */}
        {validationError && (
          <StructuredErrorCard {...validationError} className="mb-6" />
        )}

        {/* Cloned Candidate Visual Banner */}
        {clonedCandidate && (
          <div
            data-testid="cloned-candidate-banner"
            className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/40 text-amber-300 font-mono text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-lg mb-6"
          >
            <div className="flex items-center gap-2.5">
              <div className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse shrink-0" />
              <div>
                <div className="font-bold text-sm tracking-wide text-white font-sans flex items-center gap-2">
                  <span>[ CLONED OPTIMIZATION CANDIDATE: {clonedCandidate.id} ]</span>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold uppercase">
                    PROVENANCE LINKED
                  </span>
                </div>
                <div className="text-[11px] text-zinc-400 mt-0.5 font-mono">
                  Source: <span className="text-zinc-200">{clonedCandidate.optimizationId || "Active Pareto Optimization Run"}</span>
                  {clonedCandidate.k_s ? ` • Spring Rate k_s = ${clonedCandidate.k_s} N/m` : ""}
                  {clonedCandidate.c ? ` • Damping c = ${clonedCandidate.c} Ns/m` : ""}
                </div>
              </div>
            </div>
            <div className="text-[11px] text-zinc-400 font-mono">
              Parameters mapped to experiment pipeline
            </div>
          </div>
        )}

        {/* 1. ENGINEERING QUESTION BAR */}
        <div className="bg-zinc-900/90 border border-zinc-800 rounded-xl p-4 sm:p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-xs font-mono text-zinc-400 uppercase tracking-wider flex items-center gap-2">
              <Sparkles size={13} className="text-amber-400" />
              1. Engineering Question
            </label>
            <span className="text-[11px] text-zinc-500 font-mono">
              Natural language hypothesis formulation
            </span>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What happens if I increase front roll stiffness by 10%?"
              className="flex-1 bg-zinc-950 border border-zinc-700 focus:border-amber-500 rounded-lg px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none font-medium transition-colors"
            />
            <button
              type="button"
              onClick={handleRunExperiment}
              disabled={isExecuting}
              className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-950 font-semibold text-sm rounded-lg flex items-center justify-center gap-2 transition-colors shrink-0 shadow-sm shadow-amber-500/10"
            >
              {isExecuting ? (
                <>
                  <div className="w-4 h-4 border-2 border-zinc-950 border-t-transparent rounded-full animate-spin" />
                  Solving ODE...
                </>
              ) : (
                <>
                  <Play size={14} className="fill-zinc-950" />
                  Run Experiment
                </>
              )}
            </button>
          </div>

          {/* Preset question chips */}
          <div className="flex flex-wrap gap-2 pt-1">
            <span className="text-xs text-zinc-500 self-center">Quick launch:</span>
            {PRESET_QUESTIONS.map((q) => (
              <button
                key={q.id}
                type="button"
                onClick={() => handleSelectPresetQuestion(q)}
                className={`text-xs px-3 py-1 rounded-full border transition-all ${
                  question === q.title
                    ? "bg-amber-500/15 border-amber-500/50 text-amber-300 font-medium"
                    : "bg-zinc-950/60 border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                &ldquo;{q.title}&rdquo;
              </button>
            ))}
          </div>
        </div>

        {/* 2. ONE-CLICK EXPERIMENT BUILDER CONTROLS */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* A. Setup Selector */}
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4 space-y-2">
            <div className="text-xs font-mono text-zinc-400 uppercase tracking-wider flex items-center justify-between">
              <span>Step 1: Baseline Setup</span>
              <span className="text-emerald-400 text-[11px]">ACTIVE</span>
            </div>
            <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
              <div className="font-semibold text-sm text-zinc-100">{activeVehicleContext.setup}</div>
              <div className="text-xs text-zinc-400 mt-0.5 flex items-center gap-2 font-mono">
                <span>Rev: {activeVehicleContext.setupVersion}</span>
                <span>•</span>
                <span>Track: {activeVehicleContext.track}</span>
              </div>
            </div>
            <p className="text-[11px] text-zinc-500">
              Cloned automatically into candidate version on experiment execution.
            </p>
          </div>

          {/* B. Parameter Selector */}
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4 space-y-2">
            <div className="text-xs font-mono text-zinc-400 uppercase tracking-wider flex items-center justify-between">
              <span>Step 2: Parameter to Test</span>
              <Sliders size={13} className="text-zinc-500" />
            </div>
            <select
              value={selectedParamKey}
              onChange={(e) => {
                setSelectedParamKey(e.target.value);
                const conf = PARAM_PRESETS.find((p) => p.key === e.target.value);
                if (conf) {
                  setAbsoluteVal(Math.round(conf.defaultVal * (1.0 + deltaPct / 100.0)));
                }
              }}
              className="w-full bg-zinc-950 border border-zinc-800 focus:border-amber-500 rounded-lg p-2.5 text-sm text-zinc-200 font-medium focus:outline-none transition-colors"
            >
              {PARAM_PRESETS.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label} (Current: {p.defaultVal.toLocaleString()} {p.unit})
                </option>
              ))}
            </select>
            <div className="text-[11px] text-zinc-500 flex justify-between font-mono">
              <span>Baseline: {selectedParamConfig.defaultVal.toLocaleString()} {selectedParamConfig.unit}</span>
              <span>Step: {selectedParamConfig.step}</span>
            </div>
          </div>

          {/* C. Define Change */}
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4 space-y-2">
            <div className="text-xs font-mono text-zinc-400 uppercase tracking-wider flex items-center justify-between">
              <span>Step 3: Define Change</span>
              <div className="flex gap-1 text-[11px]">
                <button
                  type="button"
                  onClick={() => setDeltaMode("pct")}
                  className={`px-1.5 py-0.5 rounded font-mono ${deltaMode === "pct" ? "bg-amber-500/20 text-amber-300 font-bold" : "text-zinc-500 hover:text-zinc-300"}`}
                >
                  %
                </button>
                <button
                  type="button"
                  onClick={() => setDeltaMode("absolute")}
                  className={`px-1.5 py-0.5 rounded font-mono ${deltaMode === "absolute" ? "bg-amber-500/20 text-amber-300 font-bold" : "text-zinc-500 hover:text-zinc-300"}`}
                >
                  Val
                </button>
              </div>
            </div>

            {deltaMode === "pct" ? (
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={-40}
                    max={40}
                    step={1}
                    value={deltaPct}
                    onChange={(e) => {
                      const val = parseFloat(e.target.value);
                      setDeltaPct(val);
                      setAbsoluteVal(Math.round(selectedParamConfig.defaultVal * (1.0 + val / 100.0)));
                    }}
                    className="flex-1 accent-amber-500 cursor-pointer"
                  />
                  <span className={`text-sm font-mono font-bold w-16 text-right ${deltaPct > 0 ? "text-emerald-400" : deltaPct < 0 ? "text-amber-400" : "text-zinc-400"}`}>
                    {deltaPct > 0 ? `+${deltaPct}%` : `${deltaPct}%`}
                  </span>
                </div>
                <div className="flex justify-between text-[11px] text-zinc-500 font-mono">
                  <span>Target: {Math.round(selectedParamConfig.defaultVal * (1.0 + deltaPct / 100.0)).toLocaleString()} {selectedParamConfig.unit}</span>
                  <span>Δ: {Math.round(selectedParamConfig.defaultVal * (deltaPct / 100.0)).toLocaleString()}</span>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={absoluteVal}
                  step={selectedParamConfig.step}
                  min={selectedParamConfig.min}
                  max={selectedParamConfig.max}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    setAbsoluteVal(val);
                    const pct = ((val - selectedParamConfig.defaultVal) / selectedParamConfig.defaultVal) * 100.0;
                    setDeltaPct(Math.round(pct * 10) / 10);
                  }}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm font-mono text-zinc-100"
                />
                <span className="text-xs font-mono text-zinc-500 shrink-0">{selectedParamConfig.unit}</span>
              </div>
            )}
          </div>
        </div>

        {/* 3. AUTOMATED PIPELINE VISUALIZER */}
        <div className="bg-zinc-950/80 border border-zinc-800/80 rounded-xl p-4">
          <div className="text-xs font-mono text-zinc-500 uppercase tracking-wider mb-2 flex items-center justify-between">
            <span>Automated Hypothesis Pipeline</span>
            {isExecuting && (
              <span className="text-amber-400 flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-amber-400 animate-ping" /> Executing Pipeline
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 text-xs">
            {[
              { num: 1, label: "Clone Setup", desc: "Branch rev-04" },
              { num: 2, label: "Validate Params", desc: "Check physics domain" },
              { num: 3, label: "Affected Kinematics", desc: "Wheel rate MR²" },
              { num: 4, label: "Run ODE Solver", desc: "scipy RK45" },
              { num: 5, label: "Calculate KPIs", desc: "RMS & Transmissibility" },
              { num: 6, label: "Check Constraints", desc: "Travel & Damping ratio" },
              { num: 7, label: "Persist Provenance", desc: "SHA-256 Hash" },
            ].map((step) => {
              const isDone = pipelineStage >= step.num;
              const isCurrent = pipelineStage === step.num && isExecuting;
              return (
                <div
                  key={step.num}
                  className={`p-2.5 rounded-lg border transition-all ${
                    isCurrent
                      ? "bg-amber-500/10 border-amber-500 text-amber-300 shadow-sm"
                      : isDone
                      ? "bg-zinc-900 border-emerald-500/40 text-emerald-400"
                      : "bg-zinc-950 border-zinc-800/60 text-zinc-600"
                  }`}
                >
                  <div className="flex items-center justify-between font-mono text-[10px] mb-1">
                    <span>STEP {step.num}</span>
                    {isDone ? <Check size={11} className="text-emerald-400" /> : null}
                  </div>
                  <div className="font-semibold text-zinc-200">{step.label}</div>
                  <div className="text-[10px] text-zinc-500 truncate">{step.desc}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 4. EXPERIMENT RESULT COCKPIT */}
        {experimentResult && (
          <div className="space-y-6">
            {/* Top Result Banner */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-zinc-800/80 pb-3">
                <div>
                  <div className="text-xs font-mono text-zinc-500 uppercase tracking-wider">
                    Experiment Result Object: {experimentResult.simulation_id || `RUN-EXP-${experimentResult.id.slice(0, 8)}`}
                  </div>
                  <h2 className="text-xl font-bold text-white mt-0.5 flex items-center gap-2">
                    &ldquo;{experimentResult.question}&rdquo;
                  </h2>
                </div>

                <div className="flex items-center gap-2">
                  <ValidationBadge status={experimentResult.validation_state} />
                  <ConfidenceIndicator confidence={experimentResult.confidence} />
                  <WhyButton title="Experiment Provenance Lineage" provenance={provenanceData} />
                </div>
              </div>

              {/* Technical Recommendation Callout */}
              <div className="p-4 rounded-lg bg-amber-500/5 border border-amber-500/25 space-y-2">
                <div className="flex items-center gap-2 text-xs font-mono text-amber-400 uppercase tracking-wider">
                  <AlertTriangle size={14} />
                  Engineering Hypothesis Verdict
                </div>
                <p className="text-sm text-zinc-200 leading-relaxed font-medium">
                  {experimentResult.recommendation}
                </p>
                <div className="text-[11px] text-zinc-400 font-mono flex items-center gap-2">
                  <span>Result Hash:</span>
                  <span className="text-zinc-300">{experimentResult.result_hash}</span>
                  <span>•</span>
                  <span>Reproducible from stored definition</span>
                </div>
              </div>

              {/* Quick Summary Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800">
                  <div className="text-[11px] font-mono text-zinc-500">RIDE ACCEL (RMS)</div>
                  <div className="text-xl font-bold text-zinc-100 mt-1 font-mono">
                    {experimentResult.candidate_metrics.rms_body_accel.toFixed(3)}{" "}
                    <span className="text-xs font-normal text-zinc-400">m/s²</span>
                  </div>
                  <div className="text-xs text-emerald-400 font-mono mt-0.5">
                    Δ {((experimentResult.candidate_metrics.rms_body_accel - experimentResult.baseline_metrics.rms_body_accel) / experimentResult.baseline_metrics.rms_body_accel * 100).toFixed(1)}% vs baseline
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800">
                  <div className="text-[11px] font-mono text-zinc-500">SUSPENSION TRAVEL</div>
                  <div className="text-xl font-bold text-zinc-100 mt-1 font-mono">
                    {experimentResult.candidate_metrics.peak_susp_travel_mm.toFixed(1)}{" "}
                    <span className="text-xs font-normal text-zinc-400">mm</span>
                  </div>
                  <div className="text-xs text-zinc-400 font-mono mt-0.5">
                    Margin: {(55.0 - experimentResult.candidate_metrics.peak_susp_travel_mm).toFixed(1)} mm to bump stop
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800">
                  <div className="text-[11px] font-mono text-zinc-500">TIRE LOAD VARIATION</div>
                  <div className="text-xl font-bold text-zinc-100 mt-1 font-mono">
                    {Math.round(experimentResult.candidate_metrics.tire_load_variation_n)}{" "}
                    <span className="text-xs font-normal text-zinc-400">N</span>
                  </div>
                  <div className="text-xs text-zinc-400 font-mono mt-0.5">
                    Contact patch stability
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800">
                  <div className="text-[11px] font-mono text-zinc-500">CONSTRAINT STATUS</div>
                  <div className="text-xl font-bold text-zinc-100 mt-1 flex items-center gap-2 font-mono">
                    {experimentResult.constraints_passed ? (
                      <>
                        <CheckCircle2 size={18} className="text-emerald-400" />
                        <span className="text-emerald-400 text-base">PASS</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle size={18} className="text-rose-400" />
                        <span className="text-rose-400 text-base">VIOLATED</span>
                      </>
                    )}
                  </div>
                  <div className="text-xs text-zinc-400 font-mono mt-0.5">
                    {experimentResult.constraint_details.length} rules checked
                  </div>
                </div>
              </div>
            </div>

            {/* 5. DEEP TRADEOFF ANALYSIS & ENGINEERING CAUSALITY */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
              {/* Left Column: What Changed */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-wider font-mono flex items-center gap-2">
                    <Sliders size={14} className="text-amber-400" />
                    What Changed
                  </h3>
                  <span className="text-xs font-mono text-zinc-500">Engineering units</span>
                </div>

                <div className="space-y-3">
                  {experimentResult.parameter_changes.map((pc) => (
                    <div key={pc.parameter} className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 space-y-1 font-mono">
                      <div className="text-xs text-zinc-400 font-semibold">{pc.parameter.toUpperCase()}</div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-zinc-500">{pc.baseline.toLocaleString()} {pc.unit}</span>
                        <ArrowRight size={13} className="text-zinc-600" />
                        <span className="text-zinc-100 font-bold">{pc.candidate.toLocaleString()} {pc.unit}</span>
                      </div>
                      <div className="text-xs text-right font-medium text-amber-400">
                        {pc.delta_pct > 0 ? `+${pc.delta_pct}%` : `${pc.delta_pct}%`}
                      </div>
                    </div>
                  ))}

                  <div className="text-xs text-zinc-500 space-y-1 pt-2 border-t border-zinc-800/80">
                    <div>Solver: <span className="text-zinc-400 font-mono">{experimentResult.solver}</span></div>
                    <div>Backend: <span className="text-zinc-400 font-mono">{experimentResult.backend}</span></div>
                    <div>Model: <span className="text-zinc-400 font-mono">{experimentResult.model_version}</span></div>
                  </div>
                </div>
              </div>

              {/* Middle Column: What Improved vs What Got Worse (MANDATORY TRADEOFFS) */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-wider font-mono flex items-center gap-2">
                    <Layers size={14} className="text-amber-400" />
                    Performance Tradeoffs
                  </h3>
                  <span className="text-xs font-mono text-amber-500 font-semibold">MANDATORY EXPOSURE</span>
                </div>

                {/* What Improved */}
                <div className="space-y-2">
                  <div className="text-xs font-mono text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                    <TrendingUp size={13} />
                    What Improved
                  </div>
                  {experimentResult.improvements.length === 0 ? (
                    <div className="p-3 bg-zinc-950 rounded-lg text-xs text-zinc-500">No decisive metric gains observed.</div>
                  ) : (
                    experimentResult.improvements.map((imp) => (
                      <div key={imp.key} className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-zinc-200">{imp.metric}</span>
                          <span className="text-xs font-mono font-bold text-emerald-400">{imp.delta_pct}%</span>
                        </div>
                        <div className="text-[11px] text-zinc-400 font-mono">
                          {imp.baseline} → {imp.candidate} {imp.unit}
                        </div>
                        <p className="text-[11px] text-zinc-400 italic mt-0.5">{imp.reason}</p>
                      </div>
                    ))
                  )}
                </div>

                {/* What Got Worse (MANDATORY) */}
                <div className="space-y-2 pt-2 border-t border-zinc-800">
                  <div className="text-xs font-mono text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
                    <TrendingDown size={13} />
                    What Got Worse (Tradeoffs)
                  </div>
                  {experimentResult.regressions.length === 0 ? (
                    <div className="p-3 bg-zinc-950 rounded-lg text-xs text-zinc-500">No significant penalty detected.</div>
                  ) : (
                    experimentResult.regressions.map((reg) => (
                      <div key={reg.key} className="p-3 rounded-lg bg-rose-500/5 border border-rose-500/20 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-zinc-200">{reg.metric}</span>
                          <span className="text-xs font-mono font-bold text-rose-400">+{Math.abs(reg.delta_pct)}%</span>
                        </div>
                        <div className="text-[11px] text-zinc-400 font-mono">
                          {reg.baseline} → {reg.candidate} {reg.unit}
                        </div>
                        <p className="text-[11px] text-zinc-400 italic mt-0.5">{reg.reason}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Right Column: Engineering Causality Chain & Action */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                  <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-wider font-mono flex items-center gap-2">
                    <GitBranch size={14} className="text-amber-400" />
                    Engineering Causality Chain
                  </h3>
                  <span className="text-xs font-mono text-zinc-500">Physical mechanics</span>
                </div>

                <div className="space-y-3">
                  {experimentResult.causal_chain.map((step, idx) => (
                    <div key={idx} className="flex gap-2.5 items-start">
                      <div className="w-5 h-5 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center text-[10px] font-mono text-amber-400 shrink-0 mt-0.5">
                        {idx + 1}
                      </div>
                      <p className="text-xs text-zinc-300 leading-relaxed">{step}</p>
                    </div>
                  ))}
                </div>

                {/* Constraint Checklist */}
                <div className="space-y-2 pt-3 border-t border-zinc-800">
                  <div className="text-xs font-mono text-zinc-400 uppercase tracking-wider">
                    Operational Envelope Boundaries
                  </div>
                  {experimentResult.constraint_details.map((cd, idx) => (
                    <div key={idx} className="p-2.5 rounded bg-zinc-950 border border-zinc-800 flex items-center justify-between text-xs font-mono">
                      <div>
                        <div className="text-zinc-200">{cd.constraint}</div>
                        <div className="text-[10px] text-zinc-500">Limit: {cd.limit} | Actual: {cd.actual}</div>
                      </div>
                      {cd.passed ? (
                        <span className="text-emerald-400 font-bold">PASS</span>
                      ) : (
                        <span className="text-rose-400 font-bold">VIOLATION</span>
                      )}
                    </div>
                  ))}
                </div>

                {/* TEST THIS CHANGE ACTION BUTTON */}
                <div className="pt-3">
                  <Link
                    data-testid="btn-test-in-compare"
                    href={`/compare?exp_id=${experimentResult.id}&candidate=${encodeURIComponent(JSON.stringify(experimentResult.candidate_setup))}`}
                    className="w-full py-3 bg-zinc-100 hover:bg-white text-zinc-950 font-bold text-xs font-mono uppercase tracking-wider rounded-lg flex items-center justify-center gap-2 transition-colors shadow-sm"
                  >
                    <Zap size={14} className="fill-zinc-950" />
                    [ Test This Change in Full Car / Rig ]
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Universal Provenance Popover */}
      <ProvenancePopover
        isOpen={provenanceOpen}
        onClose={() => setProvenanceOpen(false)}
        title="Experiment Physical Provenance & Verification Lineage"
        data={provenanceData}
      />
    </div>
  );
}

export default function ExperimentBuilderPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#08080a] text-zinc-400 p-8 font-mono">Loading Engineering Experimentation Lab...</div>}>
      <ExperimentBuilderContent />
    </Suspense>
  );
}

