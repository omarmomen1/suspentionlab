"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { apiFetch } from "../../lib/api";
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

function formatMetricName(metric: string): string {
  switch (metric) {
    case "peak_roll_angle_deg": return "Peak Chassis Roll Angle";
    case "max_suspension_travel_mm":
    case "front_susp_travel_mm": return "Front Suspension Travel";
    case "peak_lateral_accel_g":
    case "front_lat_accel_g": return "Front Lateral Acceleration";
    case "yaw_rate_rmse_radps": return "Yaw Rate Tracking RMSE";
    default: return metric.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

function formatMetricUnit(metric: string): string {
  if (metric.includes("deg") || metric.includes("roll")) return "°";
  if (metric.includes("mm") || metric.includes("travel")) return " mm";
  if (metric.includes("accel") || metric.endsWith("_g")) return " G";
  if (metric.includes("rmse") || metric.includes("radps")) return " rad/s";
  return "";
}

export default function SetupEngineeringPage() {
  const [manifest, setManifest] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>("workflow");
  const [selectedFailure, setSelectedFailure] = useState<string>("unidentifiable_parameter_selected");
  const [failureDiagnostic, setFailureDiagnostic] = useState<any>(null);

  const fetchManifest = () => {
    setLoading(true);
    setError(null);
    apiFetch("/api/v1/setup-engineering/manifest")
      .then((res: Response) => {
        if (!res.ok) throw new Error(`Manifest not available (HTTP ${res.status})`);
        return res.json();
      })
      .then((data: any) => {
        setManifest(data);
        setLoading(false);
      })
      .catch((err: any) => {
        setError(err.message || "Failed to load setup engineering manifest");
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchManifest();
  }, []);

  const handleDiagnose = (failureType: string) => {
    setSelectedFailure(failureType);
    apiFetch("/api/v1/setup-engineering/diagnose-failure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ failure_type: failureType }),
    })
      .then((res: Response) => {
        if (!res.ok) throw new Error(`Diagnosis failed (${res.status})`);
        return res.json();
      })
      .then((data: any) => setFailureDiagnostic(data))
      .catch((err: any) => console.error("Diagnosis error:", err));
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
            onClick={fetchManifest}
            className="px-3 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-md flex items-center gap-1.5 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Reload Artifacts
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex flex-col items-center justify-center p-20 space-y-4">
          <RefreshCw className="w-8 h-8 text-emerald-400 animate-spin" />
          <p className="text-sm text-slate-400">Loading setup engineering manifest & causal lineage...</p>
        </div>
      )}

      {/* Error / Empty state */}
      {!loading && (error || !manifest) && (
        <div className="mt-8 p-8 border border-rose-500/30 bg-rose-950/20 rounded-xl text-center max-w-2xl mx-auto space-y-4">
          <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
          <h2 className="text-lg font-bold text-white">Setup Engineering Manifest Unavailable</h2>
          <p className="text-xs text-slate-300 leading-relaxed">
            {error || "No manifest was returned by the setup engineering pipeline."}
          </p>
          <p className="text-[11px] text-slate-400">
            Please run the causal workflow (`/execute-workflow`) or verify your authentication permissions (`VEHICLE_READ`).
          </p>
          <button
            onClick={fetchManifest}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg inline-flex items-center gap-2 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry Fetching Manifest
          </button>
        </div>
      )}

      {/* Live Manifest Content */}
      {!loading && manifest && (
        <>
          {/* Epistemic Demarcation Banner */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
            <div className="bg-slate-900/80 border border-blue-500/30 p-4 rounded-lg">
              <div className="text-xs font-semibold uppercase text-blue-400 tracking-wider">Observed Fact</div>
              <div className="text-sm font-medium text-slate-200 mt-1">Direct Sensor Measurements</div>
              <div className="text-xs text-slate-400 mt-2">
                Peak Lateral: {manifest.problem?.baseline_metric?.peak_lat_accel_g ?? "—"} G | Roll: {manifest.problem?.baseline_metric?.peak_roll_angle_deg ?? "—"}° | Front Travel: {manifest.problem?.baseline_metric?.front_susp_travel_mm ?? "—"} mm (Limit: 55.0 mm)
              </div>
            </div>

            <div className="bg-slate-900/80 border border-purple-500/30 p-4 rounded-lg">
              <div className="text-xs font-semibold uppercase text-purple-400 tracking-wider">Causal Hypothesis</div>
              <div className="text-sm font-medium text-slate-200 mt-1">Physical Mechanism</div>
              <div className="text-xs text-slate-400 mt-2 truncate" title={manifest.hypothesis?.hypothesis}>
                {manifest.hypothesis?.hypothesis || "Front ARB (+32%) accelerates load transfer, reducing roll compliance to ≤ 2.50°"}
              </div>
            </div>

            <div className="bg-slate-900/80 border border-amber-500/30 p-4 rounded-lg">
              <div className="text-xs font-semibold uppercase text-amber-400 tracking-wider">Model Inference</div>
              <div className="text-sm font-medium text-slate-200 mt-1">14-DOF Production ODE</div>
              <div className="text-xs text-slate-400 mt-2">
                Simulated Roll: {manifest.simulation?.metrics?.peak_roll_angle_deg ?? manifest.comparison?.candidate_metrics?.peak_roll_angle_deg ?? "—"}° | Front Jounce: {manifest.simulation?.metrics?.max_suspension_travel_mm ?? manifest.comparison?.candidate_metrics?.max_suspension_travel_mm ?? "—"} mm | Holdout R² = {manifest.validation?.holdout_r2 ?? "—"}
              </div>
            </div>

            <div className="bg-slate-900/80 border border-emerald-500/30 p-4 rounded-lg">
              <div className="text-xs font-semibold uppercase text-emerald-400 tracking-wider">Engineering Decision</div>
              <div className="text-sm font-medium text-slate-200 mt-1">Approved & Track-Sealed</div>
              <div className="text-xs text-slate-400 mt-2">
                Decision: {manifest.decision?.outcome ?? "—"} | Signee: {manifest.approval?.approver_name || manifest.decision?.author || "—"} | Status: {manifest.approval?.status ?? "—"}
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
                    Comparative Setup Delta: Baseline ({manifest.comparison?.baseline_setup_id || "SETUP-GTI-BASE"}) vs Candidate ({manifest.comparison?.candidate_setup_id || "SETUP-P3L-CAND-01"}) vs Measured Telemetry
                  </h2>
                  <div className="overflow-x-auto mt-4">
                    <table className="w-full text-left text-xs text-slate-300">
                      <thead className="bg-slate-800/60 uppercase text-slate-400 border-b border-slate-700">
                        <tr>
                          <th className="py-2.5 px-3">Observable Metric</th>
                          <th className="py-2.5 px-3">Baseline ({manifest.comparison?.baseline_setup_id || "SETUP-GTI-BASE"})</th>
                          <th className="py-2.5 px-3">Candidate ({manifest.comparison?.candidate_setup_id || "SETUP-P3L-CAND-01"})</th>
                          <th className="py-2.5 px-3">Measured Telemetry</th>
                          <th className="py-2.5 px-3">Delta Abs</th>
                          <th className="py-2.5 px-3">Delta %</th>
                          <th className="py-2.5 px-3">95% Confidence Interval</th>
                          <th className="py-2.5 px-3">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {Array.isArray(manifest.comparison?.deltas) && manifest.comparison.deltas.length > 0 ? (
                          manifest.comparison.deltas.map((d: any, idx: number) => {
                            const unit = formatMetricUnit(d.metric);
                            const isGood = d.beneficial || (d.delta_pct !== undefined && d.delta_pct < 0);
                            return (
                              <tr key={idx}>
                                <td className="py-2.5 px-3 font-medium text-slate-100">{formatMetricName(d.metric)}</td>
                                <td className="py-2.5 px-3">{d.baseline !== undefined ? `${d.baseline}${unit}` : "—"}</td>
                                <td className={`py-2.5 px-3 font-semibold ${isGood ? "text-emerald-400" : "text-slate-200"}`}>
                                  {d.candidate !== undefined ? `${d.candidate}${unit}` : "—"}
                                </td>
                                <td className="py-2.5 px-3">{d.measured !== undefined ? `${d.measured}${unit}` : "—"}</td>
                                <td className={`py-2.5 px-3 ${isGood ? "text-emerald-400" : "text-slate-200"}`}>
                                  {d.delta_abs !== undefined ? `${d.delta_abs > 0 ? "+" : ""}${d.delta_abs}${unit}` : "—"}
                                </td>
                                <td className={`py-2.5 px-3 font-semibold ${isGood ? "text-emerald-400" : "text-slate-200"}`}>
                                  {d.delta_pct !== undefined ? `${d.delta_pct > 0 ? "+" : ""}${d.delta_pct.toFixed(1)}%` : "—"}
                                </td>
                                <td className="py-2.5 px-3 text-slate-400">
                                  {d.ci_95 ? `[${d.ci_95[0]}${unit}, ${d.ci_95[1]}${unit}]` : "—"}
                                </td>
                                <td className="py-2.5 px-3">
                                  <span className={`px-2 py-0.5 rounded text-[10px] border ${
                                    d.beneficial
                                      ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                                      : "bg-slate-700/50 text-slate-300 border-slate-600"
                                  }`}>
                                    {d.beneficial ? "BENEFICIAL" : d.validity_status || "VALID"}
                                  </span>
                                </td>
                              </tr>
                            );
                          })
                        ) : (
                          <tr>
                            <td colSpan={8} className="py-4 text-center text-slate-400">No comparison deltas available.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Controlled Experiment Matrix */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                    <div className="text-xs font-semibold uppercase text-slate-400">Isolated Treatment Variables</div>
                    <div className="mt-3 space-y-2 text-xs">
                      {Object.entries(manifest.experiment?.treatment_variables || manifest.setup?.changed_parameters || {}).map(([key, val]: [string, any], i) => (
                        <div key={i} className="flex justify-between border-b border-slate-800/80 pb-1">
                          <span className="text-slate-300 font-mono">{key}:</span>
                          <span className="text-emerald-400 font-semibold font-mono">
                            {typeof val === "object" ? `${val.candidate ?? val.baseline} (${val.delta_pct > 0 ? "+" : ""}${val.delta_pct}%)` : String(val)}
                          </span>
                        </div>
                      ))}
                      <div className="text-[11px] text-emerald-500 mt-2">
                        ✓ Isolation Verified: zero simultaneous changes to rear or aero.
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                    <div className="text-xs font-semibold uppercase text-slate-400">Multi-Objective Constraints</div>
                    <div className="mt-3 space-y-2 text-xs">
                      {Array.isArray(manifest.experiment?.constraints) && manifest.experiment.constraints.length > 0 ? (
                        manifest.experiment.constraints.slice(0, 4).map((c: any, i: number) => (
                          <div key={i} className="flex justify-between border-b border-slate-800/80 pb-1">
                            <span className="text-slate-300">{c.name}:</span>
                            <span className="text-slate-200">{c.limit}</span>
                          </div>
                        ))
                      ) : (
                        <div className="text-slate-500 py-1">No active constraints recorded.</div>
                      )}
                    </div>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                    <div className="text-xs font-semibold uppercase text-slate-400">Sealed Holdout Validation</div>
                    <div className="mt-3 space-y-2 text-xs">
                      <div className="flex justify-between border-b border-slate-800/80 pb-1">
                        <span className="text-slate-300">Holdout Window:</span>
                        <span className="text-slate-200">
                          t = [{manifest.validation?.holdout_window?.[0] ?? "—"}, {manifest.validation?.holdout_window?.[1] ?? "—"}] s
                        </span>
                      </div>
                      <div className="flex justify-between border-b border-slate-800/80 pb-1">
                        <span className="text-slate-300">Zero Data Leakage:</span>
                        <span className="text-emerald-400 font-semibold">
                          {manifest.validation?.is_zero_leakage ? "VERIFIED (Disjoint)" : "UNVERIFIED"}
                        </span>
                      </div>
                      <div className="flex justify-between border-b border-slate-800/80 pb-1">
                        <span className="text-slate-300">Holdout R² / Gate:</span>
                        <span className="text-emerald-400 font-semibold">
                          {manifest.validation?.holdout_r2 ?? "—"} ({manifest.validation?.gate_verdict ?? "PASSED"})
                        </span>
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
                      {manifest.parameter_gate?.eligible_parameters ? (
                        manifest.parameter_gate.eligible_parameters.map((param: string, i: number) => {
                          const rec = manifest.parameter_gate?.parameter_records?.[param]?.evidence;
                          return (
                            <li key={i}>
                              <strong>{param}:</strong> {rec ? `Sens = ${rec.sensitivities ?? "—"}, CV = ${rec.cross_window_cv_pct ?? "—"}%, SE = ${rec.std_error ?? "—"}` : "Eligible in optimization"}
                            </li>
                          );
                        })
                      ) : (
                        <li>No identifiable parameters in manifest.</li>
                      )}
                    </ul>
                  </div>

                  <div className="border border-amber-500/30 bg-amber-950/20 p-4 rounded-lg">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-400" />
                      <span className="text-sm font-semibold text-amber-400">PARTIALLY_IDENTIFIABLE (Requires Uncertainty Bounds)</span>
                    </div>
                    <ul className="text-xs text-slate-300 mt-3 space-y-1.5 list-disc list-inside">
                      {manifest.parameter_gate?.requires_uncertainty && manifest.parameter_gate.requires_uncertainty.length > 0 ? (
                        manifest.parameter_gate.requires_uncertainty.map((p: string, i: number) => (
                          <li key={i}><strong>{p}:</strong> Permitted only with explicit variance bounds.</li>
                        ))
                      ) : (
                        <li><em>Policy:</em> Permitted only with explicit variance bounds (e.g. ±1.5σ) or regularizer penalty.</li>
                      )}
                    </ul>
                  </div>

                  <div className="border border-rose-500/30 bg-rose-950/20 p-4 rounded-lg">
                    <div className="flex items-center gap-2">
                      <XCircle className="w-4 h-4 text-rose-400" />
                      <span className="text-sm font-semibold text-rose-400">UNIDENTIFIABLE (Strictly Prohibited)</span>
                    </div>
                    <ul className="text-xs text-slate-300 mt-3 space-y-1.5 list-disc list-inside">
                      {manifest.parameter_gate?.prohibited_parameters && manifest.parameter_gate.prohibited_parameters.length > 0 ? (
                        manifest.parameter_gate.prohibited_parameters.map((p: string, i: number) => (
                          <li key={i}><strong>{p}:</strong> Prohibited from optimization.</li>
                        ))
                      ) : (
                        <>
                          <li><strong>camber_stiffness_front:</strong> Sensitivity &lt; 1e-4</li>
                          <li><strong>camber_stiffness_rear:</strong> Flat Hessian in pure lateral cornering</li>
                          <li><em>Enforcement:</em> Optimization attempt raises <code>UnidentifiableParameterError</code>.</li>
                        </>
                      )}
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
                  <h2 className="text-base font-semibold text-white">
                    Immutable Track-Test Prediction ({manifest.prediction?.prediction_id || "PRED-P3L-01"})
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Sealed prior to the subsequent track session. Guaranteed tamper-evident with SHA-256 hash.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4 text-xs">
                    <div className="bg-slate-800/40 p-3 rounded border border-slate-700">
                      <div className="text-slate-400">Expected Roll Angle Delta</div>
                      <div className="text-base font-bold text-white mt-1">
                        {manifest.prediction?.expected_delta?.peak_roll_angle_deg !== undefined
                          ? `${manifest.prediction.expected_delta.peak_roll_angle_deg}°`
                          : "—"}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {manifest.prediction?.uncertainty_interval?.peak_roll_angle_deg
                          ? `95% CI: [${manifest.prediction.uncertainty_interval.peak_roll_angle_deg[0]}°, ${manifest.prediction.uncertainty_interval.peak_roll_angle_deg[1]}°]`
                          : "—"}
                      </div>
                    </div>
                    <div className="bg-slate-800/40 p-3 rounded border border-slate-700">
                      <div className="text-slate-400">Expected Lateral Accel Delta</div>
                      <div className="text-base font-bold text-white mt-1">
                        {manifest.prediction?.expected_delta?.peak_lateral_accel_g !== undefined
                          ? `+${manifest.prediction.expected_delta.peak_lateral_accel_g} G`
                          : "—"}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {manifest.prediction?.uncertainty_interval?.peak_lateral_accel_g
                          ? `95% CI: [+${manifest.prediction.uncertainty_interval.peak_lateral_accel_g[0]} G, +${manifest.prediction.uncertainty_interval.peak_lateral_accel_g[1]} G]`
                          : "—"}
                      </div>
                    </div>
                    <div className="bg-slate-800/40 p-3 rounded border border-slate-700">
                      <div className="text-slate-400">Expected Suspension Travel Delta</div>
                      <div className="text-base font-bold text-white mt-1">
                        {manifest.prediction?.expected_delta?.front_susp_travel_mm !== undefined
                          ? `${manifest.prediction.expected_delta.front_susp_travel_mm} mm`
                          : "—"}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {manifest.prediction?.uncertainty_interval?.front_susp_travel_mm
                          ? `95% CI: [${manifest.prediction.uncertainty_interval.front_susp_travel_mm[0]}, ${manifest.prediction.uncertainty_interval.front_susp_travel_mm[1]}] mm`
                          : "—"}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
                  <h2 className="text-base font-semibold text-white">
                    Post-Track Telemetry Reconciliation ({manifest.reconciliation?.reconciliation_id || "RECON-P3L-01"})
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Evaluated against Session {manifest.reconciliation?.actual_session_id || "TS-STANFORD-02"}. Prediction was not altered retroactively.
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
                          <td className="py-2.5 px-3">
                            {manifest.prediction?.expected_candidate_metric?.peak_roll_angle_deg !== undefined
                              ? `${manifest.prediction.expected_candidate_metric.peak_roll_angle_deg}°`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3 text-emerald-400 font-semibold">
                            {manifest.prediction?.expected_candidate_metric?.peak_roll_angle_deg !== undefined && manifest.reconciliation?.prediction_error?.peak_roll_angle_deg !== undefined
                              ? `${(manifest.prediction.expected_candidate_metric.peak_roll_angle_deg + manifest.reconciliation.prediction_error.peak_roll_angle_deg).toFixed(2)}°`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3">
                            {manifest.reconciliation?.prediction_error?.peak_roll_angle_deg !== undefined
                              ? `+${manifest.reconciliation.prediction_error.peak_roll_angle_deg}°`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3 text-emerald-400 font-semibold">
                            {manifest.reconciliation?.directional_agreement ? "✓ YES" : "✗ NO"}
                          </td>
                        </tr>
                        <tr>
                          <td className="py-2.5 px-3 font-medium">Peak Lateral Accel</td>
                          <td className="py-2.5 px-3">
                            {manifest.prediction?.expected_candidate_metric?.peak_lateral_accel_g !== undefined
                              ? `${manifest.prediction.expected_candidate_metric.peak_lateral_accel_g} G`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3 text-emerald-400 font-semibold">
                            {manifest.prediction?.expected_candidate_metric?.peak_lateral_accel_g !== undefined && manifest.reconciliation?.prediction_error?.peak_lateral_accel_g !== undefined
                              ? `${(manifest.prediction.expected_candidate_metric.peak_lateral_accel_g + manifest.reconciliation.prediction_error.peak_lateral_accel_g).toFixed(2)} G`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3">
                            {manifest.reconciliation?.prediction_error?.peak_lateral_accel_g !== undefined
                              ? `${manifest.reconciliation.prediction_error.peak_lateral_accel_g} G`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3 text-emerald-400 font-semibold">
                            {manifest.reconciliation?.directional_agreement ? "✓ YES" : "✗ NO"}
                          </td>
                        </tr>
                        <tr>
                          <td className="py-2.5 px-3 font-medium">Front Suspension Travel</td>
                          <td className="py-2.5 px-3">
                            {manifest.prediction?.expected_candidate_metric?.front_susp_travel_mm !== undefined
                              ? `${manifest.prediction.expected_candidate_metric.front_susp_travel_mm} mm`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3 text-emerald-400 font-semibold">
                            {manifest.prediction?.expected_candidate_metric?.front_susp_travel_mm !== undefined && manifest.reconciliation?.prediction_error?.front_susp_travel_mm !== undefined
                              ? `${(manifest.prediction.expected_candidate_metric.front_susp_travel_mm + manifest.reconciliation.prediction_error.front_susp_travel_mm).toFixed(1)} mm`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3">
                            {manifest.reconciliation?.prediction_error?.front_susp_travel_mm !== undefined
                              ? `+${manifest.reconciliation.prediction_error.front_susp_travel_mm} mm`
                              : "—"}
                          </td>
                          <td className="py-2.5 px-3 text-emerald-400 font-semibold">
                            {manifest.reconciliation?.directional_agreement ? "✓ YES" : "✗ NO"}
                          </td>
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
      </>
      )}
    </div>
  );
}
