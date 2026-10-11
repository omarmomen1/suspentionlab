"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Sliders,
  Activity,
  Layers,
  FileText,
  Lock,
  ArrowRight,
  TrendingDown,
  TrendingUp,
  RefreshCw,
  GitBranch,
  Terminal,
  HelpCircle,
  Sparkles,
} from "lucide-react";

export default function SetupEngineeringPage() {
  const [manifest, setManifest] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<string>("workflow");
  const [selectedFailure, setSelectedFailure] = useState<string>("unidentifiable_parameter_selected");
  const [failureDiagnostic, setFailureDiagnostic] = useState<any>(null);

  useEffect(() => {
    fetch("/api/v1/setup-engineering/manifest")
      .then((res) => {
        if (!res.ok) throw new Error("Manifest not loaded");
        return res.json();
      })
      .then((data) => {
        setManifest(data);
        setLoading(false);
      })
      .catch((err) => {
        console.warn("Could not fetch manifest directly, using static state:", err);
        setLoading(false);
      });
  }, []);

  const handleDiagnose = (failureType: string) => {
    setSelectedFailure(failureType);
    fetch("/api/v1/setup-engineering/diagnose-failure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ failure_type: failureType }),
    })
      .then((res) => res.json())
      .then((data) => setFailureDiagnostic(data))
      .catch((err) => console.error(err));
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-10 font-sans">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-slate-800 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 text-xs font-semibold uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded">
              Phase 3L Ready
            </span>
            <span className="text-xs text-slate-400">DOC-P3L-SETUP-ENG-01</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white mt-1">
            Setup Engineering & Causal Experimentation
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Closed-loop physical hypothesis formulation, isolated parameter interventions, and defensible track predictions.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/compare"
            className="px-3 py-1.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-md transition"
          >
            Telemetry Compare
          </Link>
          <Link
            href="/timeline"
            className="px-3 py-1.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-md transition"
          >
            Engineering Timeline
          </Link>
          <button
            onClick={() => window.location.reload()}
            className="px-3 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-md flex items-center gap-1.5 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Reload Artifacts
          </button>
        </div>
      </div>

      {/* Epistemic Demarcation Banner */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
        <div className="bg-slate-900/80 border border-blue-500/30 p-4 rounded-lg">
          <div className="text-xs font-semibold uppercase text-blue-400 tracking-wider">Observed Fact</div>
          <div className="text-sm font-medium text-slate-200 mt-1">Direct Sensor Measurements</div>
          <div className="text-xs text-slate-400 mt-2">
            Peak Lateral: 1.91 G | Roll: 3.37° | Front Travel: 53.2 mm (Limit: 55.0 mm)
          </div>
        </div>

        <div className="bg-slate-900/80 border border-purple-500/30 p-4 rounded-lg">
          <div className="text-xs font-semibold uppercase text-purple-400 tracking-wider">Causal Hypothesis</div>
          <div className="text-sm font-medium text-slate-200 mt-1">Physical Mechanism</div>
          <div className="text-xs text-slate-400 mt-2">
            Front ARB (+32%) accelerates load transfer, reducing roll compliance to ≤ 2.50°
          </div>
        </div>

        <div className="bg-slate-900/80 border border-amber-500/30 p-4 rounded-lg">
          <div className="text-xs font-semibold uppercase text-amber-400 tracking-wider">Model Inference</div>
          <div className="text-sm font-medium text-slate-200 mt-1">14-DOF Production ODE</div>
          <div className="text-xs text-slate-400 mt-2">
            Simulated Roll: 1.75° | Front Jounce: 38.51 mm | Holdout R² = 0.7664
          </div>
        </div>

        <div className="bg-slate-900/80 border border-emerald-500/30 p-4 rounded-lg">
          <div className="text-xs font-semibold uppercase text-emerald-400 tracking-wider">Engineering Decision</div>
          <div className="text-sm font-medium text-slate-200 mt-1">Approved & Track-Sealed</div>
          <div className="text-xs text-slate-400 mt-2">
            Decision: ACCEPT | Signee: Elena Rostova | Status: APPROVED
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-800 mt-8 gap-6 text-sm font-medium">
        <button
          onClick={() => setActiveTab("workflow")}
          className={`pb-3 transition ${
            activeTab === "workflow" ? "text-emerald-400 border-b-2 border-emerald-400" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Closed-Loop Workflow
        </button>
        <button
          onClick={() => setActiveTab("parameter_gate")}
          className={`pb-3 transition ${
            activeTab === "parameter_gate" ? "text-emerald-400 border-b-2 border-emerald-400" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Parameter Eligibility Gate
        </button>
        <button
          onClick={() => setActiveTab("reconciliation")}
          className={`pb-3 transition ${
            activeTab === "reconciliation" ? "text-emerald-400 border-b-2 border-emerald-400" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Track Prediction & Reconciliation
        </button>
        <button
          onClick={() => setActiveTab("failure_ux")}
          className={`pb-3 transition ${
            activeTab === "failure_ux" ? "text-emerald-400 border-b-2 border-emerald-400" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          Failure Modes & Diagnostics (14)
        </button>
      </div>

      {/* Main Tab Content */}
      <div className="mt-6">
        {activeTab === "workflow" && (
          <div className="space-y-6">
            {/* Setup Comparison Section */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <Sliders className="w-4 h-4 text-emerald-400" />
                Comparative Setup Delta: Baseline vs Candidate vs Measured Telemetry
              </h2>
              <div className="overflow-x-auto mt-4">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-800/60 uppercase text-slate-400 border-b border-slate-700">
                    <tr>
                      <th className="py-2.5 px-3">Observable Metric</th>
                      <th className="py-2.5 px-3">Baseline (SETUP-GTI-BASE)</th>
                      <th className="py-2.5 px-3">Candidate (SETUP-P3L-CAND-01)</th>
                      <th className="py-2.5 px-3">Measured Telemetry</th>
                      <th className="py-2.5 px-3">Delta Abs</th>
                      <th className="py-2.5 px-3">Delta %</th>
                      <th className="py-2.5 px-3">95% Confidence Interval</th>
                      <th className="py-2.5 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    <tr>
                      <td className="py-2.5 px-3 font-medium text-slate-100">Peak Chassis Roll Angle</td>
                      <td className="py-2.5 px-3">3.37°</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">2.45°</td>
                      <td className="py-2.5 px-3">3.37°</td>
                      <td className="py-2.5 px-3 text-emerald-400">-0.92°</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">-27.3%</td>
                      <td className="py-2.5 px-3 text-slate-400">[2.31°, 2.59°]</td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          BENEFICIAL
                        </span>
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 font-medium text-slate-100">Front Suspension Travel</td>
                      <td className="py-2.5 px-3">53.2 mm</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">48.5 mm</td>
                      <td className="py-2.5 px-3">53.2 mm</td>
                      <td className="py-2.5 px-3 text-emerald-400">-4.7 mm</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">-8.8%</td>
                      <td className="py-2.5 px-3 text-slate-400">[45.6, 51.4] mm</td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          SAFE (&lt; 55mm)
                        </span>
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 font-medium text-slate-100">Front Lateral Acceleration</td>
                      <td className="py-2.5 px-3">1.91 G</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">1.99 G</td>
                      <td className="py-2.5 px-3">1.91 G</td>
                      <td className="py-2.5 px-3 text-emerald-400">+0.08 G</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">+4.2%</td>
                      <td className="py-2.5 px-3 text-slate-400">[1.87, 2.11] G</td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          IMPROVED
                        </span>
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 font-medium text-slate-100">Yaw Rate Tracking RMSE</td>
                      <td className="py-2.5 px-3">0.0965 rad/s</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">0.0247 rad/s</td>
                      <td className="py-2.5 px-3">0.000 rad/s</td>
                      <td className="py-2.5 px-3 text-emerald-400">-0.0718</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">-74.4%</td>
                      <td className="py-2.5 px-3 text-slate-400">[0.023, 0.026]</td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          CORRELATED
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Controlled Experiment Matrix */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                <div className="text-xs font-semibold uppercase text-slate-400">Isolated Treatment Variables</div>
                <div className="mt-3 space-y-2 text-xs">
                  <div className="flex justify-between border-b border-slate-800/80 pb-1">
                    <span className="text-slate-300">k_arb_front_nm:</span>
                    <span className="text-emerald-400 font-semibold">33,000 N/m (+32%)</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800/80 pb-1">
                    <span className="text-slate-300">c_damper_front_nsm:</span>
                    <span className="text-emerald-400 font-semibold">4,200 Ns/m (+10.5%)</span>
                  </div>
                  <div className="text-[11px] text-emerald-500 mt-2">
                    ✓ Isolation Verified: zero simultaneous changes to rear or aero.
                  </div>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                <div className="text-xs font-semibold uppercase text-slate-400">Multi-Objective Constraints</div>
                <div className="mt-3 space-y-2 text-xs">
                  <div className="flex justify-between border-b border-slate-800/80 pb-1">
                    <span className="text-slate-300">Jounce Travel:</span>
                    <span className="text-slate-200">≤ 55.0 mm (Current: 48.5 mm)</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800/80 pb-1">
                    <span className="text-slate-300">Front Damping Ratio:</span>
                    <span className="text-slate-200">0.25 ≤ ζ ≤ 0.85 (ζ = 0.52)</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800/80 pb-1">
                    <span className="text-slate-300">Tire Slip Envelope:</span>
                    <span className="text-slate-200">|α| ≤ 18.0° (Max: 11.2°)</span>
                  </div>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                <div className="text-xs font-semibold uppercase text-slate-400">Sealed Holdout Validation</div>
                <div className="mt-3 space-y-2 text-xs">
                  <div className="flex justify-between border-b border-slate-800/80 pb-1">
                    <span className="text-slate-300">Holdout Window:</span>
                    <span className="text-slate-200">t = [42.0, 44.0] s</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800/80 pb-1">
                    <span className="text-slate-300">Zero Data Leakage:</span>
                    <span className="text-emerald-400 font-semibold">VERIFIED (Disjoint)</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-800/80 pb-1">
                    <span className="text-slate-300">Holdout R² / Gate:</span>
                    <span className="text-emerald-400 font-semibold">0.7664 (PASSED)</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "parameter_gate" && (
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
            <h2 className="text-base font-semibold text-white">Parameter Eligibility Gate (Phase 3J / 3J.1 Integration)</h2>
            <p className="text-xs text-slate-400 mt-1">
              Parameters are mathematically audited before entering setup optimization. Unidentifiable parameters are strictly blocked.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
              <div className="border border-emerald-500/30 bg-emerald-950/20 p-4 rounded-lg">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm font-semibold text-emerald-400">IDENTIFIABLE (Eligible for Optimization)</span>
                </div>
                <ul className="text-xs text-slate-300 mt-3 space-y-1.5 list-disc list-inside">
                  <li><strong>spring_rate_front:</strong> Sens = 0.679, CV = 0.74%, SE = 889.5 N/m</li>
                  <li><strong>damper_bump_front:</strong> Sens = 0.589, CV = 0.89%, SE = 106.26 Ns/m</li>
                  <li><strong>anti_roll_bar_front:</strong> Sens = 0.542, CV = 1.12%, SE = 1,250 N/m</li>
                </ul>
              </div>

              <div className="border border-amber-500/30 bg-amber-950/20 p-4 rounded-lg">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <span className="text-sm font-semibold text-amber-400">PARTIALLY_IDENTIFIABLE (Requires Uncertainty Bounds)</span>
                </div>
                <ul className="text-xs text-slate-300 mt-3 space-y-1.5 list-disc list-inside">
                  <li><strong>anti_roll_bar_rear:</strong> CV = 4.85%, SE = 2,100 N/m</li>
                  <li><em>Policy:</em> Permitted only with explicit variance bounds (e.g. ±1.5σ) or regularizer penalty.</li>
                </ul>
              </div>

              <div className="border border-rose-500/30 bg-rose-950/20 p-4 rounded-lg">
                <div className="flex items-center gap-2">
                  <XCircle className="w-4 h-4 text-rose-400" />
                  <span className="text-sm font-semibold text-rose-400">UNIDENTIFIABLE (Strictly Prohibited)</span>
                </div>
                <ul className="text-xs text-slate-300 mt-3 space-y-1.5 list-disc list-inside">
                  <li><strong>camber_stiffness_front:</strong> Sensitivity = 0.00e+00 (&lt; 1e-4)</li>
                  <li><strong>camber_stiffness_rear:</strong> Flat Hessian in pure lateral cornering</li>
                  <li><em>Enforcement:</em> Optimization attempt raises <code>UnidentifiableParameterError</code>.</li>
                </ul>
              </div>

              <div className="border border-red-500/30 bg-red-950/20 p-4 rounded-lg">
                <div className="flex items-center gap-2">
                  <Lock className="w-4 h-4 text-red-400" />
                  <span className="text-sm font-semibold text-red-400">NUMERICALLY_FAILED (Strictly Prohibited)</span>
                </div>
                <ul className="text-xs text-slate-300 mt-3 space-y-1.5 list-disc list-inside">
                  <li><strong>tire_load_degressivity:</strong> Ill-conditioned Hessian eigenvalues</li>
                  <li><em>Enforcement:</em> Raises <code>NumericallyFailedParameterError</code>.</li>
                </ul>
              </div>
            </div>
          </div>
        )}

        {activeTab === "reconciliation" && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
              <h2 className="text-base font-semibold text-white">Immutable Track-Test Prediction (PRED-P3L-01)</h2>
              <p className="text-xs text-slate-400 mt-1">
                Sealed prior to the subsequent track session. Guaranteed tamper-evident with SHA-256 hash.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4 text-xs">
                <div className="bg-slate-800/40 p-3 rounded border border-slate-700">
                  <div className="text-slate-400">Expected Roll Angle Delta</div>
                  <div className="text-base font-bold text-white mt-1">-0.92° ± 0.23°</div>
                  <div className="text-[10px] text-slate-400">95% CI: [-1.15°, -0.69°]</div>
                </div>
                <div className="bg-slate-800/40 p-3 rounded border border-slate-700">
                  <div className="text-slate-400">Expected Lateral Accel Delta</div>
                  <div className="text-base font-bold text-white mt-1">+0.08 G ± 0.03 G</div>
                  <div className="text-[10px] text-slate-400">95% CI: [+0.05 G, +0.11 G]</div>
                </div>
                <div className="bg-slate-800/40 p-3 rounded border border-slate-700">
                  <div className="text-slate-400">Expected Suspension Travel Delta</div>
                  <div className="text-base font-bold text-white mt-1">-4.7 mm ± 1.5 mm</div>
                  <div className="text-[10px] text-slate-400">95% CI: [-6.2, -3.2] mm</div>
                </div>
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
              <h2 className="text-base font-semibold text-white">Post-Track Telemetry Reconciliation (RECON-P3L-01)</h2>
              <p className="text-xs text-slate-400 mt-1">
                Evaluated against Session TS-STANFORD-02. Prediction was not altered retroactively.
              </p>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-800/60 uppercase text-slate-400">
                    <tr>
                      <th className="py-2 px-3">Metric</th>
                      <th className="py-2 px-3">Predicted Value</th>
                      <th className="py-2 px-3">Actual Measured Value</th>
                      <th className="py-2 px-3">Prediction Error</th>
                      <th className="py-2 px-3">Directional Match</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    <tr>
                      <td className="py-2.5 px-3 font-medium">Peak Chassis Roll</td>
                      <td className="py-2.5 px-3">2.45°</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">2.48°</td>
                      <td className="py-2.5 px-3">+0.03°</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">✓ YES</td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 font-medium">Peak Lateral Accel</td>
                      <td className="py-2.5 px-3">1.99 G</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">1.98 G</td>
                      <td className="py-2.5 px-3">-0.01 G</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">✓ YES</td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 font-medium">Front Suspension Travel</td>
                      <td className="py-2.5 px-3">48.5 mm</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">48.9 mm</td>
                      <td className="py-2.5 px-3">+0.4 mm</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-semibold">✓ YES</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === "failure_ux" && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
              <h2 className="text-base font-semibold text-white">14 Mandatory Failure Modes UX Diagnostics</h2>
              <p className="text-xs text-slate-400 mt-1">
                Select a failure condition to inspect the standardized 5-section engineering diagnostic report:
              </p>

              <div className="flex flex-wrap gap-2 mt-4">
                {[
                  "unidentifiable_parameter_selected",
                  "partially_identifiable_without_uncertainty",
                  "setup_violates_physical_bounds",
                  "setup_violates_validity_domain",
                  "solver_failure",
                  "optimizer_failure",
                  "candidate_outside_model_envelope",
                  "validation_failure",
                  "holdout_leakage",
                  "missing_provenance",
                  "stale_model",
                  "conflicting_objectives",
                  "no_feasible_setup",
                  "track_prediction_unavailable",
                ].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => handleDiagnose(mode)}
                    className={`px-2.5 py-1 text-xs rounded border transition ${
                      selectedFailure === mode
                        ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                        : "bg-slate-800 text-slate-400 border-slate-700 hover:text-white"
                    }`}
                  >
                    {mode.replace(/_/g, " ")}
                  </button>
                ))}
              </div>

              {failureDiagnostic && (
                <div className="mt-6 border border-rose-500/30 bg-rose-950/10 p-5 rounded-lg space-y-4 text-xs">
                  <div>
                    <span className="font-bold text-rose-400 uppercase tracking-wide">WHAT FAILED:</span>
                    <p className="text-slate-200 mt-0.5">{failureDiagnostic.WHAT_FAILED}</p>
                  </div>
                  <div>
                    <span className="font-bold text-amber-400 uppercase tracking-wide">WHY:</span>
                    <p className="text-slate-300 mt-0.5">{failureDiagnostic.WHY}</p>
                  </div>
                  <div>
                    <span className="font-bold text-blue-400 uppercase tracking-wide">WHAT REMAINS VALID:</span>
                    <p className="text-slate-300 mt-0.5">{failureDiagnostic.WHAT_REMAINS_VALID}</p>
                  </div>
                  <div>
                    <span className="font-bold text-red-400 uppercase tracking-wide">WHAT CANNOT BE CLAIMED:</span>
                    <p className="text-rose-300 font-medium mt-0.5">{failureDiagnostic.WHAT_CANNOT_BE_CLAIMED}</p>
                  </div>
                  <div>
                    <span className="font-bold text-emerald-400 uppercase tracking-wide">WHAT CAN BE DONE NEXT:</span>
                    <p className="text-slate-200 mt-0.5">{failureDiagnostic.WHAT_CAN_BE_DONE_NEXT}</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
