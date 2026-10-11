"use client";

import React, { useState, useMemo } from "react";
import {
  KinematicsApi,
  KinematicsOptimizationResponse,
  KinematicsParetoCandidate,
  ApplyToExperimentResponse,
} from "../../lib/api_client";
import {
  Sliders,
  Target,
  RefreshCw,
  Award,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Send,
  Layers,
  Activity,
  ArrowRight,
  HelpCircle,
  Eye,
} from "lucide-react";

interface KinematicsOptimizerPanelProps {
  hardpoints: Record<string, [number, number, number]>;
  onApplyCandidate: (candidateHp: Record<string, [number, number, number]>, label: string) => void;
  onSetAsSetupB?: (candidateHp: Record<string, [number, number, number]>, label: string) => void;
}

export default function KinematicsOptimizerPanel({
  hardpoints,
  onApplyCandidate,
  onSetAsSetupB,
}: KinematicsOptimizerPanelProps) {
  // Optimization Setup State
  const [targetHps, setTargetHps] = useState<string[]>(["UWI_aft", "LWI_aft", "TRO"]);
  const [allowedAxes, setAllowedAxes] = useState<string[]>(["Y", "Z"]);
  const [boundsMm, setBoundsMm] = useState<number>(6.0);
  const [nSamples, setNSamples] = useState<number>(25);

  // Objectives
  const [primaryObj, setPrimaryObj] = useState<string>("camber_gain_deg_per_100mm");
  const [primaryDir, setPrimaryDir] = useState<"maximize" | "minimize">("maximize");
  const [secondaryObj, setSecondaryObj] = useState<string>("toe_variation_deg");
  const [secondaryDir, setSecondaryDir] = useState<"maximize" | "minimize">("minimize");

  // Execution State
  const [loading, setLoading] = useState<boolean>(false);
  const [results, setResults] = useState<KinematicsOptimizationResponse | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<KinematicsParetoCandidate | null>(null);
  const [transferring, setTransferring] = useState<boolean>(false);
  const [experimentResult, setExperimentResult] = useState<ApplyToExperimentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const availableHps = [
    { id: "UWI_fwd", label: "Upper Wishbone Front Chassis (UWI_fwd)" },
    { id: "UWI_aft", label: "Upper Wishbone Rear Chassis (UWI_aft)" },
    { id: "UWO", label: "Upper Ball Joint Upright (UWO)" },
    { id: "LWI_fwd", label: "Lower Wishbone Front Chassis (LWI_fwd)" },
    { id: "LWI_aft", label: "Lower Wishbone Rear Chassis (LWI_aft)" },
    { id: "LWO", label: "Lower Ball Joint Upright (LWO)" },
    { id: "TRI", label: "Tie Rod Inboard Chassis (TRI)" },
    { id: "TRO", label: "Tie Rod Outboard Upright (TRO)" },
  ];

  const handleToggleHp = (hpId: string) => {
    if (targetHps.includes(hpId)) {
      if (targetHps.length > 1) {
        setTargetHps(targetHps.filter((x) => x !== hpId));
      }
    } else {
      setTargetHps([...targetHps, hpId]);
    }
  };

  const handleToggleAxis = (ax: string) => {
    if (allowedAxes.includes(ax)) {
      if (allowedAxes.length > 1) {
        setAllowedAxes(allowedAxes.filter((x) => x !== ax));
      }
    } else {
      setAllowedAxes([...allowedAxes, ax]);
    }
  };

  const handleRunOptimization = async () => {
    setLoading(true);
    setError(null);
    setExperimentResult(null);
    try {
      const res = await KinematicsApi.runOptimization({
        hardpoints,
        target_hardpoints: targetHps,
        allowed_axes: allowedAxes,
        hardpoint_bounds_mm: boundsMm,
        objectives: [
          { metric: primaryObj, direction: primaryDir, weight: 1.0 },
          { metric: secondaryObj, direction: secondaryDir, weight: 1.0 },
        ],
        constraints: [
          { metric: "roll_center_height_static_mm", min_val: -120.0, max_val: 30.0 },
        ],
        n_samples: nSamples,
        z_min_mm: -30.0,
        z_max_mm: 30.0,
        n_steps: 11,
      });

      setResults(res);
      if (res.best_compromise_candidate) {
        setSelectedCandidate(res.best_compromise_candidate);
      } else if (res.pareto_frontier.length > 0) {
        setSelectedCandidate(res.pareto_frontier[0]);
      }
    } catch (err: any) {
      setError(err?.message || "Optimization failed to complete.");
    } finally {
      setLoading(false);
    }
  };

  const handleApplyToExperiment = async () => {
    if (!selectedCandidate) return;
    setTransferring(true);
    try {
      const res = await KinematicsApi.applyToExperiment({
        baseline_hardpoints: hardpoints,
        candidate_hardpoints: selectedCandidate.hardpoints,
        question: `Kinematics Multi-Objective Pareto Study: ${primaryObj} vs ${secondaryObj}`,
        hypothesis: `Pareto Candidate ${selectedCandidate.candidate_id} balances ${primaryObj} (${selectedCandidate.metrics[primaryObj]?.toFixed(3)}) with ${secondaryObj} (${selectedCandidate.metrics[secondaryObj]?.toFixed(3)}) with Utopia distance ${selectedCandidate.utopia_distance.toFixed(4)}.`,
        candidate_id: selectedCandidate.candidate_id,
        optimization_id: results?.optimization_id,
      });
      setExperimentResult(res);
    } catch (err: any) {
      alert(`Error transferring to experiment: ${err?.message || err}`);
    } finally {
      setTransferring(false);
    }
  };

  // SVG Scatter plot bounds
  const scatterPlotData = useMemo(() => {
    if (!results || !results.all_candidates || results.all_candidates.length === 0) return null;

    const all = results.all_candidates;
    const xVals = all.map((c) => c.objective_values[primaryObj] ?? c.metrics[primaryObj] ?? 0);
    const yVals = all.map((c) => c.objective_values[secondaryObj] ?? c.metrics[secondaryObj] ?? 0);

    const minX = Math.min(...xVals);
    const maxX = Math.max(...xVals);
    const minY = Math.min(...yVals);
    const maxY = Math.max(...yVals);

    const padX = (maxX - minX) * 0.1 || 0.1;
    const padY = (maxY - minY) * 0.1 || 0.1;

    return {
      minX: minX - padX,
      maxX: maxX + padX,
      minY: minY - padY,
      maxY: maxY + padY,
    };
  }, [results, primaryObj, secondaryObj]);

  const mapToPlotCoords = (x: number, y: number, plotW = 500, plotH = 260) => {
    if (!scatterPlotData) return { cx: 0, cy: 0 };
    const { minX, maxX, minY, maxY } = scatterPlotData;
    const cx = ((x - minX) / (maxX - minX)) * (plotW - 60) + 40;
    // Invert Y for SVG coordinates
    const cy = plotH - 30 - ((y - minY) / (maxY - minY)) * (plotH - 50);
    return { cx, cy };
  };

  return (
    <div className="space-y-5">
      {/* ── Configuration Card ── */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded-lg">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                Bounded Multi-Objective Kinematics Optimizer
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  REAL NEWTON-RAPHSON SOLVER
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Systematically searches within bounded chassis/upright packaging envelopes and identifies non-dominated Pareto tradeoffs.
              </p>
            </div>
          </div>

          <button
            onClick={handleRunOptimization}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-semibold rounded-lg text-xs shadow-lg shadow-purple-900/30 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            {loading ? "Evaluating Real Sweeps..." : "Run Multi-Objective Optimization"}
          </button>
        </div>

        {/* Form Controls */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 text-xs">
          {/* Col 1: Target Hardpoints */}
          <div className="space-y-2">
            <label className="font-semibold text-slate-300 block uppercase tracking-wider text-[11px]">
              Design Hardpoints to Perturb ({targetHps.length} selected)
            </label>
            <div className="space-y-1 max-h-48 overflow-y-auto pr-1 bg-slate-950/40 p-2 rounded-lg border border-slate-800">
              {availableHps.map((hp) => (
                <label
                  key={hp.id}
                  className="flex items-center gap-2 text-slate-300 hover:text-white cursor-pointer py-0.5"
                >
                  <input
                    type="checkbox"
                    checked={targetHps.includes(hp.id)}
                    onChange={() => handleToggleHp(hp.id)}
                    className="rounded border-slate-700 text-purple-500 focus:ring-0 bg-slate-900"
                  />
                  <span className="font-mono text-[11px]">{hp.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Col 2: Perturbation Bounds & Allowed Axes */}
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-slate-300 mb-1">
                <span className="font-semibold text-[11px] uppercase tracking-wider">Hardpoint Bounds Limit:</span>
                <span className="font-mono font-bold text-cyan-400">±{boundsMm.toFixed(1)} mm</span>
              </div>
              <input
                type="range"
                min={2.0}
                max={15.0}
                step={1.0}
                value={boundsMm}
                onChange={(e) => setBoundsMm(parseFloat(e.target.value))}
                className="w-full accent-purple-500 cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                <span>±2.0 mm (Fine)</span>
                <span>±8.0 mm (Moderate)</span>
                <span>±15.0 mm (Structural)</span>
              </div>
            </div>

            <div>
              <label className="font-semibold text-slate-300 block mb-1.5 uppercase tracking-wider text-[11px]">
                Allowed Displacement Axes
              </label>
              <div className="flex gap-2">
                {["X", "Y", "Z"].map((ax) => (
                  <button
                    key={ax}
                    onClick={() => handleToggleAxis(ax)}
                    className={`flex-1 py-1 rounded font-mono font-bold text-xs border transition ${
                      allowedAxes.includes(ax)
                        ? "bg-purple-500/20 text-purple-300 border-purple-500/40"
                        : "bg-slate-800/40 text-slate-500 border-slate-800"
                    }`}
                  >
                    Δ{ax}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="font-semibold text-slate-300 block mb-1 uppercase tracking-wider text-[11px]">
                Sweep Sample Budget
              </label>
              <div className="flex gap-2">
                {[15, 25, 40].map((n) => (
                  <button
                    key={n}
                    onClick={() => setNSamples(n)}
                    className={`flex-1 py-1 rounded font-mono text-xs border transition ${
                      nSamples === n
                        ? "bg-slate-800 text-cyan-400 font-bold border-cyan-500/40"
                        : "bg-slate-900 text-slate-400 border-slate-800"
                    }`}
                  >
                    {n} runs
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Col 3: Multi-Objective Selection */}
          <div className="space-y-3 bg-slate-950/40 p-3 rounded-lg border border-slate-800">
            <div>
              <label className="font-semibold text-slate-300 block mb-1 uppercase tracking-wider text-[11px]">
                Objective 1 (X-Axis)
              </label>
              <div className="flex gap-2">
                <select
                  value={primaryObj}
                  onChange={(e) => setPrimaryObj(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-700 rounded p-1.5 text-slate-200 text-xs"
                >
                  <option value="camber_gain_deg_per_100mm">Camber Recovery Rate</option>
                  <option value="roll_center_height_static_mm">Static Roll Center Z</option>
                  <option value="motion_ratio_static">Motion Ratio</option>
                </select>
                <button
                  onClick={() => setPrimaryDir(primaryDir === "maximize" ? "minimize" : "maximize")}
                  className={`px-2 py-1 rounded font-bold text-[10px] uppercase border ${
                    primaryDir === "maximize"
                      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                      : "bg-amber-500/20 text-amber-300 border-amber-500/40"
                  }`}
                >
                  {primaryDir}
                </button>
              </div>
            </div>

            <div>
              <label className="font-semibold text-slate-300 block mb-1 uppercase tracking-wider text-[11px]">
                Objective 2 (Y-Axis)
              </label>
              <div className="flex gap-2">
                <select
                  value={secondaryObj}
                  onChange={(e) => setSecondaryObj(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-700 rounded p-1.5 text-slate-200 text-xs"
                >
                  <option value="toe_variation_deg">Toe Variation Range</option>
                  <option value="toe_gain_deg_per_100mm">Bump Steer Rate</option>
                  <option value="track_change_max_mm">Max Track Change</option>
                  <option value="scrub_radius_static_mm">Scrub Radius</option>
                </select>
                <button
                  onClick={() => setSecondaryDir(secondaryDir === "maximize" ? "minimize" : "maximize")}
                  className={`px-2 py-1 rounded font-bold text-[10px] uppercase border ${
                    secondaryDir === "maximize"
                      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                      : "bg-amber-500/20 text-amber-300 border-amber-500/40"
                  }`}
                >
                  {secondaryDir}
                </button>
              </div>
            </div>

            <div className="text-[11px] text-slate-400 pt-1">
              <span className="text-slate-300 font-medium">Active Constraints:</span>
              <div className="mt-0.5 font-mono text-[10px] text-slate-400">
                • Roll Center Height ∈ [-120, +30] mm<br />
                • Structural Wishbone Length &gt; 120 mm
              </div>
            </div>
          </div>
        </div>

        {error && (
          <div className="p-3 bg-red-500/20 border border-red-500/40 text-red-300 rounded-lg text-xs">
            {error}
          </div>
        )}
      </div>

      {/* ── Optimization Results & Pareto Frontier ── */}
      {results && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Left Column: Interactive Pareto Tradeoff Scatter Plot (7 cols) */}
          <div className="lg:col-span-7 bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-xl space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-bold text-white flex items-center gap-2">
                  Multi-Objective Pareto Frontier
                  <span className="text-xs font-mono font-normal text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800">
                    {results.pareto_count} Non-Dominated Candidates
                  </span>
                </h4>
                <p className="text-[11px] text-slate-400">
                  Tradeoff between {primaryObj} and {secondaryObj}. Non-dominated frontier points represent optimal compromises.
                </p>
              </div>

              <div className="flex items-center gap-2 text-[10px] font-mono text-slate-400">
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 inline-block" /> Pareto Frontier
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" /> Best Compromise
                </span>
              </div>
            </div>

            {/* SVG Scatter Plot */}
            <div className="relative bg-slate-950/80 border border-slate-800 rounded-xl p-2">
              <svg viewBox="0 0 500 260" className="w-full h-64 select-none">
                {/* Axes and Grid Lines */}
                <line x1="40" y1="230" x2="480" y2="230" stroke="#334155" strokeWidth="1" />
                <line x1="40" y1="20" x2="40" y2="230" stroke="#334155" strokeWidth="1" />

                {/* Axis Labels */}
                <text x="260" y="252" fill="#94a3b8" fontSize="10" textAnchor="middle" fontFamily="monospace">
                  {primaryObj} ({primaryDir}) →
                </text>
                <text
                  x="-125"
                  y="18"
                  transform="rotate(-90)"
                  fill="#94a3b8"
                  fontSize="10"
                  textAnchor="middle"
                  fontFamily="monospace"
                >
                  {secondaryObj} ({secondaryDir}) →
                </text>

                {/* Plot Dominated Candidates */}
                {results.all_candidates
                  .filter((c) => !results.pareto_frontier.some((p) => p.candidate_id === c.candidate_id))
                  .map((cand) => {
                    const x = cand.objective_values[primaryObj] ?? cand.metrics[primaryObj] ?? 0;
                    const y = cand.objective_values[secondaryObj] ?? cand.metrics[secondaryObj] ?? 0;
                    const { cx, cy } = mapToPlotCoords(x, y);
                    const isSelected = selectedCandidate?.candidate_id === cand.candidate_id;

                    return (
                      <circle
                        key={cand.candidate_id}
                        cx={cx}
                        cy={cy}
                        r={isSelected ? 6 : 4}
                        fill="#475569"
                        stroke={isSelected ? "#38bdf8" : "#1e293b"}
                        strokeWidth={isSelected ? 2 : 1}
                        className="cursor-pointer transition hover:fill-slate-400"
                        onClick={() => setSelectedCandidate(cand)}
                      />
                    );
                  })}

                {/* Connect Pareto Frontier with Line */}
                {results.pareto_frontier.length > 1 && (
                  <path
                    d={results.pareto_frontier
                      .slice()
                      .sort((a, b) => (a.objective_values[primaryObj] || 0) - (b.objective_values[primaryObj] || 0))
                      .map((p, idx) => {
                        const x = p.objective_values[primaryObj] ?? p.metrics[primaryObj] ?? 0;
                        const y = p.objective_values[secondaryObj] ?? p.metrics[secondaryObj] ?? 0;
                        const { cx, cy } = mapToPlotCoords(x, y);
                        return `${idx === 0 ? "M" : "L"} ${cx} ${cy}`;
                      })
                      .join(" ")}
                    fill="none"
                    stroke="#06b6d4"
                    strokeWidth="1.5"
                    strokeDasharray="4 2"
                    opacity="0.6"
                  />
                )}

                {/* Plot Pareto Frontier Candidates */}
                {results.pareto_frontier.map((cand) => {
                  const x = cand.objective_values[primaryObj] ?? cand.metrics[primaryObj] ?? 0;
                  const y = cand.objective_values[secondaryObj] ?? cand.metrics[secondaryObj] ?? 0;
                  const { cx, cy } = mapToPlotCoords(x, y);
                  const isSelected = selectedCandidate?.candidate_id === cand.candidate_id;
                  const isBest = cand.is_best_compromise;

                  return (
                    <g
                      key={cand.candidate_id}
                      className="cursor-pointer"
                      onClick={() => setSelectedCandidate(cand)}
                    >
                      {/* Glow halo if selected or best */}
                      {(isSelected || isBest) && (
                        <circle
                          cx={cx}
                          cy={cy}
                          r={isBest ? 10 : 8}
                          fill={isBest ? "#f59e0b" : "#06b6d4"}
                          opacity="0.25"
                        />
                      )}
                      <circle
                        cx={cx}
                        cy={cy}
                        r={isBest ? 6 : 5}
                        fill={isBest ? "#f59e0b" : "#38bdf8"}
                        stroke="#0f172a"
                        strokeWidth="1.5"
                      />
                    </g>
                  );
                })}
              </svg>
            </div>

            {/* Frontier Candidate Selector Chips */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
              <span className="text-slate-500 font-mono text-[11px] whitespace-nowrap">Pareto Set:</span>
              {results.pareto_frontier.map((p, idx) => (
                <button
                  key={p.candidate_id}
                  onClick={() => setSelectedCandidate(p)}
                  className={`px-2 py-1 rounded font-mono text-[11px] whitespace-nowrap border transition ${
                    selectedCandidate?.candidate_id === p.candidate_id
                      ? "bg-cyan-500 text-slate-950 font-bold border-cyan-400"
                      : p.is_best_compromise
                      ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                      : "bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700"
                  }`}
                >
                  {p.is_best_compromise ? `★ BEST COMPROMISE` : `Frontier #${idx + 1}`}
                </button>
              ))}
            </div>
          </div>

          {/* Right Column: 5-Point Candidate Explanation Inspector (5 cols) */}
          <div className="lg:col-span-5 bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-xl flex flex-col justify-between space-y-3">
            {selectedCandidate ? (
              <div className="space-y-3">
                <div className="flex items-start justify-between border-b border-slate-800 pb-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-base font-bold text-white font-mono">
                        {selectedCandidate.candidate_id}
                      </span>
                      {selectedCandidate.is_best_compromise && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1">
                          <Award className="w-3 h-3" /> BEST COMPROMISE
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                      Utopia Distance d* = {selectedCandidate.utopia_distance.toFixed(4)}
                    </div>
                  </div>

                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
                    selectedCandidate.constraint_status === "PASS"
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                      : "bg-red-500/20 text-red-300 border border-red-500/40"
                  }`}>
                    {selectedCandidate.constraint_status}
                  </span>
                </div>

                {/* 5-Point Candidate Explanation Report */}
                <div className="space-y-2 text-xs">
                  {/* Point 1: What Changed */}
                  <div className="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                      1. What Changed
                    </span>
                    <p className="text-slate-300 font-mono text-[11px]">
                      {selectedCandidate.explanation?.what_changed || "Hardpoint coordinate adjustments applied."}
                    </p>
                  </div>

                  {/* Point 2: Why It Was Chosen */}
                  <div className="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                      2. Why It Was Chosen (Utopia Distance)
                    </span>
                    <p className="text-slate-300 text-[11px]">
                      {selectedCandidate.explanation?.why_chosen || "Minimizes normalized distance to the theoretical Utopia point across all objectives."}
                    </p>
                  </div>

                  {/* Point 3: What Improved */}
                  <div className="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wider block mb-1">
                      3. What Improved
                    </span>
                    <ul className="list-disc list-inside text-emerald-300/90 space-y-0.5 text-[11px]">
                      {selectedCandidate.explanation?.what_improved?.map((imp, idx) => (
                        <li key={idx}>{imp}</li>
                      )) || <li>Balanced objective trade-off achieved.</li>}
                    </ul>
                  </div>

                  {/* Point 4: What Got Worse */}
                  <div className="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-[10px] font-semibold text-amber-500 uppercase tracking-wider block mb-1">
                      4. What Got Worse
                    </span>
                    {selectedCandidate.explanation?.what_got_worse?.length ? (
                      <ul className="list-disc list-inside text-amber-300/90 space-y-0.5 text-[11px]">
                        {selectedCandidate.explanation.what_got_worse.map((w, idx) => (
                          <li key={idx}>{w}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-slate-400 italic text-[11px]">No secondary metrics degraded significantly.</p>
                    )}
                  </div>
                </div>

                {/* Experiment Confirmation Toast if created */}
                {experimentResult && (
                  <div className="p-3 bg-emerald-950/50 border border-emerald-500/40 rounded-lg text-xs text-emerald-200 flex items-center justify-between">
                    <div>
                      <div className="font-semibold">Transferred to Experiment!</div>
                      <div className="text-[10px] font-mono text-emerald-300/80">ID: {experimentResult.experiment_id}</div>
                    </div>
                    <a
                      href={experimentResult.redirect_url}
                      className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded text-[11px]"
                    >
                      View
                    </a>
                  </div>
                )}

                {/* Actions */}
                <div className="pt-2 border-t border-slate-800 space-y-2">
                  <div className="flex gap-2">
                    <button
                      onClick={() =>
                        onApplyCandidate(selectedCandidate.hardpoints, `Candidate ${selectedCandidate.candidate_id}`)
                      }
                      className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium rounded-lg text-xs transition"
                    >
                      Apply to 3D View
                    </button>

                    {onSetAsSetupB && (
                      <button
                        onClick={() =>
                          onSetAsSetupB(selectedCandidate.hardpoints, `Candidate ${selectedCandidate.candidate_id}`)
                        }
                        className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-cyan-400 font-medium rounded-lg text-xs transition"
                      >
                        Set as Setup B
                      </button>
                    )}
                  </div>

                  <button
                    onClick={handleApplyToExperiment}
                    disabled={transferring}
                    className="w-full py-2 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold rounded-lg text-xs flex items-center justify-center gap-1.5 shadow-md shadow-cyan-950/40 transition disabled:opacity-50"
                  >
                    <Send className="w-3.5 h-3.5" />
                    {transferring ? "Transferring Candidate..." : "1-Click Apply to Experiment System"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 text-xs">
                Select a candidate from the Pareto plot or list to inspect details.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
