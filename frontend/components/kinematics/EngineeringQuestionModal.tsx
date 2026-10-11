"use client";

import React, { useState } from "react";
import {
  KinematicsApi,
  EngineeringQuestionResponse,
  EngineeringQuestionCandidate,
  ApplyToExperimentResponse,
} from "../../lib/api_client";
import {
  HelpCircle,
  Sparkles,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  X,
  RefreshCw,
  Award,
  Layers,
  FileCheck,
  Send,
} from "lucide-react";

interface EngineeringQuestionModalProps {
  isOpen: boolean;
  onClose: () => void;
  hardpoints: Record<string, [number, number, number]>;
  onApplyCandidateToWorkspace: (candidateHp: Record<string, [number, number, number]>, label: string) => void;
}

export default function EngineeringQuestionModal({
  isOpen,
  onClose,
  hardpoints,
  onApplyCandidateToWorkspace,
}: EngineeringQuestionModalProps) {
  const [selectedPreset, setSelectedPreset] = useState<string>("camber_gain_without_toe");
  const [customMetric, setCustomMetric] = useState<string>("camber_gain_deg_per_100mm");
  const [customDirection, setCustomDirection] = useState<"maximize" | "minimize">("maximize");
  const [loading, setLoading] = useState<boolean>(false);
  const [results, setResults] = useState<EngineeringQuestionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [transferringId, setTransferringId] = useState<string | null>(null);
  const [experimentCreated, setExperimentCreated] = useState<ApplyToExperimentResponse | null>(null);

  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const presets = [
    {
      id: "camber_gain_without_toe",
      title: "Increase negative camber gain in bump while minimizing bump steer",
      objective: "camber_gain_deg_per_100mm (maximize)",
      constraint: "toe_variation_deg < 0.5°",
    },
    {
      id: "raise_roll_center",
      title: "Raise static roll center height without degrading bump camber recovery",
      objective: "roll_center_height_static_mm (maximize)",
      constraint: "camber_gain >= 0.8× baseline",
    },
    {
      id: "minimize_scrub_radius",
      title: "Minimize scrub radius while maintaining kingpin inclination stability",
      objective: "scrub_radius_static_mm (minimize)",
      constraint: "kpi_static_deg within ±1.5°",
    },
    {
      id: "maximize_wheel_rate_linearity",
      title: "Maximize bump travel motion ratio with minimal track width variation",
      objective: "motion_ratio_static (maximize)",
      constraint: "track_change_max_mm < 4.0 mm",
    },
    {
      id: "custom",
      title: "Custom Engineering Question Builder",
      objective: "User-defined target",
      constraint: "User-defined limits",
    },
  ];

  const handleRunEvaluation = async () => {
    setLoading(true);
    setError(null);
    setExperimentCreated(null);
    try {
      let payload: any = {
        hardpoints,
        perturbation_steps_mm: [-4.0, -2.0, 2.0, 4.0],
      };

      if (selectedPreset === "custom") {
        payload.custom_objective = {
          metric: customMetric,
          direction: customDirection,
        };
      } else {
        payload.question_preset_id = selectedPreset;
      }

      const res = await KinematicsApi.recommendHardpoints(payload);
      setResults(res);
    } catch (err: any) {
      setError(err?.message || "Failed to evaluate engineering question.");
    } finally {
      setLoading(false);
    }
  };

  const handleApplyToExperiment = async (cand: EngineeringQuestionCandidate) => {
    setTransferringId(cand.candidate_id);
    try {
      const res = await KinematicsApi.applyToExperiment({
        baseline_hardpoints: hardpoints,
        candidate_hardpoints: cand.hardpoints,
        question: results?.question || "Kinematic hardpoint optimization study",
        hypothesis: `Perturbation of ${cand.hardpoint} by ${cand.delta_mm}mm along ${cand.axis} optimizes ${results?.objective_metric}.`,
        candidate_id: cand.candidate_id,
      });
      setExperimentCreated(res);
    } catch (err: any) {
      alert(`Error creating experiment: ${err?.message || err}`);
    } finally {
      setTransferringId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm overflow-y-auto">
      <div className="relative w-full max-w-4xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 my-8 text-slate-200 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-xl">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                Engineering Question Mode
                <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono font-semibold border border-amber-500/30">
                  SENSITIVITY-BASED RECOMMENDATION
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Determines which hardpoint to change to achieve targeted suspension kinematics behavior.
              </p>
            </div>
          </div>
          <button
            data-testid="btn-close-question-modal"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto py-4 space-y-5 pr-1">
          {/* Strict Safety & Causal Banner */}
          <div className="p-3 bg-slate-800/60 border border-slate-700/60 rounded-xl text-xs flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="text-slate-300">
              <span className="font-semibold text-slate-200">Strict Engineering Advisory:</span>{" "}
              Recommendations are evaluated using verified finite difference sweeps and double wishbone geometric kinematic constraints.
              Kinematics recommendations must be verified across full dynamic roll and pitch before cutting metal.
            </div>
          </div>

          {/* Question Selector */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Select Design Engineering Question
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {presets.map((p) => (
                <div
                  key={p.id}
                  onClick={() => setSelectedPreset(p.id)}
                  className={`p-3 rounded-xl border cursor-pointer transition ${
                    selectedPreset === p.id
                      ? "bg-cyan-950/40 border-cyan-500/80 shadow-md shadow-cyan-950/20"
                      : "bg-slate-800/40 border-slate-800 hover:border-slate-700 hover:bg-slate-800/70"
                  }`}
                >
                  <div className="font-medium text-xs text-white mb-1">{p.title}</div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                    <span>Obj: {p.objective}</span>
                    <span className="text-amber-400/80">{p.constraint}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Custom Builder if selected */}
          {selectedPreset === "custom" && (
            <div className="p-4 bg-slate-800/40 border border-slate-700/60 rounded-xl space-y-3">
              <div className="text-xs font-semibold text-slate-300">Configure Custom Objective</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="text-slate-400 block mb-1">Target Output Metric</label>
                  <select
                    value={customMetric}
                    onChange={(e) => setCustomMetric(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-slate-200"
                  >
                    <option value="camber_gain_deg_per_100mm">Camber Recovery Rate (deg/100mm)</option>
                    <option value="toe_variation_deg">Toe Variation Range (deg)</option>
                    <option value="roll_center_height_static_mm">Static Roll Center Height (mm)</option>
                    <option value="motion_ratio_static">Static Motion Ratio</option>
                    <option value="scrub_radius_static_mm">Static Scrub Radius (mm)</option>
                    <option value="kpi_static_deg">Kingpin Inclination (deg)</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400 block mb-1">Optimization Direction</label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setCustomDirection("maximize")}
                      className={`flex-1 py-2 rounded-lg text-xs font-semibold transition ${
                        customDirection === "maximize"
                          ? "bg-emerald-600 text-white"
                          : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                      }`}
                    >
                      Maximize
                    </button>
                    <button
                      onClick={() => setCustomDirection("minimize")}
                      className={`flex-1 py-2 rounded-lg text-xs font-semibold transition ${
                        customDirection === "minimize"
                          ? "bg-amber-600 text-white"
                          : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                      }`}
                    >
                      Minimize
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Action Button */}
          <div>
            <button
              data-testid="btn-evaluate-question"
              onClick={handleRunEvaluation}
              disabled={loading}
              className="w-full py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold rounded-xl text-xs flex items-center justify-center gap-2 shadow-lg shadow-cyan-900/20 transition disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              {loading ? "Testing Candidate Perturbations with Solver..." : "Evaluate Engineering Question"}
            </button>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-red-500/20 border border-red-500/40 text-red-300 text-xs">
              {error}
            </div>
          )}

          {/* Transfer Notification Banner */}
          {experimentCreated && (
            <div className="p-4 bg-emerald-950/40 border border-emerald-500/40 rounded-xl text-xs text-emerald-200 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <div>
                  <div className="font-semibold">Applied directly to Scientific Experiment!</div>
                  <div className="text-[11px] text-emerald-300/80">
                    Experiment ID: {experimentCreated.experiment_id} — Provenance & hardpoint deltas recorded.
                  </div>
                </div>
              </div>
              <a
                data-testid="btn-go-to-experiment"
                href={experimentCreated.redirect_url}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold text-xs transition"
              >
                Go to Experiment
              </a>
            </div>
          )}

          {/* ── Results Display ── */}
          {results && (
            <div className="space-y-4 pt-2">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold text-white flex items-center gap-2">
                  Ranked Hardpoint Recommendations
                  <span className="text-xs font-mono font-normal text-slate-400">
                    ({results.evaluated_candidates.length} candidates evaluated)
                  </span>
                </h4>
                <span className="text-[11px] font-mono text-cyan-400 bg-cyan-950/50 px-2 py-0.5 rounded border border-cyan-800">
                  Objective: {results.objective_metric} ({results.direction})
                </span>
              </div>

              {/* Best Candidate Card */}
              {results.best_candidate && (
                <div className="p-4 bg-gradient-to-br from-slate-900 to-slate-800 border-2 border-amber-500/60 rounded-xl shadow-xl space-y-3 relative overflow-hidden">
                  <div className="absolute top-0 right-0 bg-amber-500 text-slate-950 text-[10px] font-bold uppercase tracking-wider px-3 py-0.5 rounded-bl-lg flex items-center gap-1 shadow">
                    <Award className="w-3 h-3" /> Best Sensitivity Candidate
                  </div>

                  {/* Candidate Title & Delta */}
                  <div className="flex items-baseline gap-3">
                    <div className="text-base font-bold text-white font-mono">
                      {results.best_candidate.hardpoint}
                    </div>
                    <div className="text-xs px-2 py-0.5 rounded font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                      Δ{results.best_candidate.axis} = {results.best_candidate.delta_mm > 0 ? `+${results.best_candidate.delta_mm}` : results.best_candidate.delta_mm} mm
                    </div>
                    <div className="text-xs text-slate-400 font-mono">
                      Objective: <span className="text-emerald-400 font-bold">{((results.best_candidate.objective_value ?? (results.best_candidate as any).candidate_val ?? 0)).toFixed(4)}</span>
                      {" "}({(results.best_candidate.delta_obj ?? 0) > 0 ? `+${(results.best_candidate.delta_obj ?? 0).toFixed(4)}` : (results.best_candidate.delta_obj ?? 0).toFixed(4)})
                    </div>
                  </div>

                  {/* 5-Point Explanation Report */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs bg-slate-950/50 p-3 rounded-lg border border-slate-800">
                    <div className="space-y-1">
                      <span className="text-[10px] font-semibold uppercase text-slate-500 tracking-wider">
                        1. What Changed
                      </span>
                      <p className="text-slate-300 font-mono">
                        Shifted {results.best_candidate.hardpoint} by {results.best_candidate.delta_mm > 0 ? `+${results.best_candidate.delta_mm}` : results.best_candidate.delta_mm} mm along {results.best_candidate.axis}-axis.
                      </p>
                    </div>

                    <div className="space-y-1">
                      <span className="text-[10px] font-semibold uppercase text-slate-500 tracking-wider">
                        2. Why It Was Chosen (Physical Mechanism)
                      </span>
                      <p className="text-slate-300">
                        {results.best_candidate.why_chosen}
                      </p>
                    </div>

                    <div className="space-y-1">
                      <span className="text-[10px] font-semibold uppercase text-emerald-500 tracking-wider">
                        3. What Improved
                      </span>
                      <ul className="list-disc list-inside text-emerald-300/90 space-y-0.5">
                        {results.best_candidate.what_improved.map((imp, idx) => (
                          <li key={idx}>{imp}</li>
                        ))}
                      </ul>
                    </div>

                    <div className="space-y-1">
                      <span className="text-[10px] font-semibold uppercase text-amber-500 tracking-wider">
                        4. What Got Worse
                      </span>
                      {results.best_candidate.what_got_worse.length > 0 ? (
                        <ul className="list-disc list-inside text-amber-300/90 space-y-0.5">
                          {results.best_candidate.what_got_worse.map((w, idx) => (
                            <li key={idx}>{w}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-slate-400 italic">No metrics degraded beyond tolerance.</p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-slate-400">Constraint Status:</span>
                      <span className={`px-2 py-0.5 rounded font-mono font-bold text-[11px] ${
                        results.best_candidate.constraint_status === "PASS"
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                          : "bg-red-500/20 text-red-300 border border-red-500/40"
                      }`}>
                        {results.best_candidate.constraint_status}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() =>
                          results.best_candidate &&
                          onApplyCandidateToWorkspace(
                            results.best_candidate.hardpoints,
                            `${results.best_candidate.hardpoint} Δ${results.best_candidate.axis}${results.best_candidate.delta_mm > 0 ? `+${results.best_candidate.delta_mm}` : results.best_candidate.delta_mm}mm`
                          )
                        }
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition"
                      >
                        Load into 3D Workspace
                      </button>

                      <button
                        data-testid="btn-apply-to-experiment"
                        onClick={() => results.best_candidate && handleApplyToExperiment(results.best_candidate)}
                        disabled={transferringId === (results.best_candidate.candidate_id || `${results.best_candidate.hardpoint}_${results.best_candidate.axis}`)}
                        className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
                      >
                        <Send className="w-3.5 h-3.5" />
                        {transferringId === (results.best_candidate.candidate_id || `${results.best_candidate.hardpoint}_${results.best_candidate.axis}`) ? "Transferring..." : "Apply to Experiment (1-Click)"}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Other Evaluated Candidates */}
              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Other Perturbation Candidates Evaluated
                </div>
                {results.evaluated_candidates.slice(1).map((cand, idx) => (
                  <div
                    key={cand.candidate_id || `${cand.hardpoint}_${cand.axis}_${cand.delta_mm}_${idx}`}
                    className="p-3 bg-slate-800/30 hover:bg-slate-800/60 border border-slate-800 rounded-xl flex items-center justify-between gap-4 text-xs transition"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-slate-500 font-mono font-bold">#{idx + 2}</span>
                      <div>
                        <div className="font-bold text-slate-200 font-mono">
                          {cand.hardpoint} Δ{cand.axis} ({cand.delta_mm > 0 ? `+${cand.delta_mm}` : cand.delta_mm} mm)
                        </div>
                        <div className="text-[11px] text-slate-400 max-w-md line-clamp-1">
                          {cand.why_chosen}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4">
                      <div className="text-right font-mono">
                        <div className="text-slate-200 font-semibold">{((cand.objective_value ?? (cand as any).candidate_val ?? 0)).toFixed(4)}</div>
                        <div className={`text-[10px] ${(cand.delta_obj ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                          {(cand.delta_obj ?? 0) >= 0 ? `+${(cand.delta_obj ?? 0).toFixed(4)}` : (cand.delta_obj ?? 0).toFixed(4)}
                        </div>
                      </div>

                      <span className={`px-1.5 py-0.5 rounded font-mono text-[10px] font-bold ${
                        cand.constraint_status === "PASS"
                          ? "bg-emerald-500/20 text-emerald-400"
                          : "bg-red-500/20 text-red-400"
                      }`}>
                        {cand.constraint_status}
                      </span>

                      <button
                        onClick={() =>
                          onApplyCandidateToWorkspace(
                            cand.hardpoints,
                            `${cand.hardpoint} Δ${cand.axis}${cand.delta_mm > 0 ? `+${cand.delta_mm}` : cand.delta_mm}mm`
                          )
                        }
                        className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs transition"
                      >
                        Load
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
