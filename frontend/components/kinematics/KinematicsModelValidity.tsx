"use client";

import React, { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Cpu,
  ShieldCheck,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  Sliders,
  Info,
  Layers,
  Wrench,
  HelpCircle,
  Award,
  Fingerprint,
} from "lucide-react";
import {
  KinematicsValidationReport,
  KinematicsValidationIssue,
  KinematicsPhysicalValidity,
  KinematicsReproducibilityRecord,
  KinematicsBenchmarkItem,
} from "../../lib/api_client";

export interface KinematicsModelValidityProps {
  report?: KinematicsValidationReport | null;
  modelValidity?: KinematicsPhysicalValidity | null;
  numericalStatus?: "PASS" | "WARN" | "FAIL";
  physicalStatus?: "PASS" | "WARN" | "FAIL";
  overallStatus?: "PASS" | "WARN" | "FAIL";
  convergenceSummary?: string;
  reproducibility?: KinematicsReproducibilityRecord | null;
  benchmarks?: KinematicsBenchmarkItem[];
  onOpenBenchmarks?: () => void;
  backendInfo?: {
    backend: string;
    cpp_loaded?: boolean;
    fallback?: boolean;
    solver_version?: string;
    native_library_version?: string | null;
    execution_time_ms?: number;
  } | null;
  allConverged?: boolean;
  travelMm?: number;
  className?: string;
}

export default function KinematicsModelValidity({
  report,
  modelValidity,
  numericalStatus,
  physicalStatus,
  overallStatus,
  convergenceSummary,
  reproducibility,
  benchmarks = [],
  onOpenBenchmarks,
  backendInfo,
  allConverged = true,
  travelMm = 0,
  className = "",
}: KinematicsModelValidityProps) {
  const [expanded, setExpanded] = useState(true);

  // Decouple Numerical vs Physical
  const numStatus = numericalStatus || modelValidity?.numerical_status || (allConverged ? "PASS" : "FAIL");
  const physStatus = physicalStatus || modelValidity?.physical_status || (report?.valid !== false ? "PASS" : "FAIL");
  const ovStatus = overallStatus || modelValidity?.overall_status || (numStatus === "PASS" && physStatus === "PASS" ? "PASS" : (numStatus === "FAIL" || physStatus === "FAIL" ? "FAIL" : "WARN"));
  const isValid = ovStatus === "PASS";

  const isNumericallyConvergedPhysicallyQuestionable = numStatus === "PASS" && physStatus !== "PASS";

  const coveragePct = modelValidity?.validation_coverage_pct ?? report?.validation_coverage_pct ?? (ovStatus === "PASS" ? 100 : 0);
  const issues = report?.issues || [];
  const geometryIssuesCount = modelValidity?.geometry_issues ?? ((report?.critical_count || 0) + (report?.warning_count || 0));

  const isCpp = backendInfo?.backend?.toLowerCase().includes("cpp") || backendInfo?.cpp_loaded === true;
  const isFallback = backendInfo?.fallback === true || backendInfo?.backend?.toLowerCase().includes("python");
  const solverName = isCpp ? "C++ Newton-Raphson QR" : "Python Reference Fallback";

  const passedBenchmarksCount = benchmarks.filter(b => b.status === "PASS").length;

  return (
    <div
      className={`bg-[#0c0d10] border rounded-xl overflow-hidden shadow-lg transition-all ${
        ovStatus === "PASS"
          ? "border-emerald-500/30"
          : ovStatus === "WARN"
          ? "border-amber-500/40"
          : "border-rose-500/50"
      } ${className}`}
    >
      {/* ── Top Header: Decoupled CURRENT MODEL STATUS ─────────────────────── */}
      <div className="p-4 border-b border-[#1c1d24] bg-[#0f1015]/80">
        <div className="flex flex-col gap-3">
          {/* Top Status Row */}
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
            {/* Primary Status Banner */}
            <div className="flex flex-wrap items-center gap-2">
              <div
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-mono text-xs font-bold tracking-wider uppercase border shadow-inner ${
                  ovStatus === "PASS"
                    ? "bg-emerald-950/70 border-emerald-500/50 text-emerald-300"
                    : ovStatus === "WARN"
                    ? "bg-amber-950/70 border-amber-500/50 text-amber-300"
                    : "bg-rose-950/70 border-rose-500/50 text-rose-300"
                }`}
              >
                <span className="relative flex h-2 w-2">
                  <span
                    className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                      ovStatus === "PASS" ? "bg-emerald-400" : ovStatus === "WARN" ? "bg-amber-400" : "bg-rose-400"
                    }`}
                  />
                  <span
                    className={`relative inline-flex rounded-full h-2 w-2 ${
                      ovStatus === "PASS" ? "bg-emerald-500" : ovStatus === "WARN" ? "bg-amber-500" : "bg-rose-500"
                    }`}
                  />
                </span>
                <span>CURRENT MODEL STATUS: {ovStatus}</span>
              </div>

              {/* Numerical Status Pill */}
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#141620] border border-[#232738] text-[11px] font-mono">
                <span className="text-gray-400">Numerical:</span>
                <span className={`font-bold ${numStatus === "PASS" ? "text-emerald-400" : numStatus === "WARN" ? "text-amber-400" : "text-rose-400"}`}>
                  {numStatus}
                </span>
              </div>

              {/* Physical Status Pill */}
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#141620] border border-[#232738] text-[11px] font-mono">
                <span className="text-gray-400">Physical:</span>
                <span className={`font-bold ${physStatus === "PASS" ? "text-emerald-400" : physStatus === "WARN" ? "text-amber-400" : "text-rose-400"}`}>
                  {physStatus}
                </span>
              </div>

              {/* Geometry Issues Pill */}
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#141620] border border-[#232738] text-[11px] font-mono">
                <span className="text-gray-400">Geometry:</span>
                <span className={`font-bold ${geometryIssuesCount === 0 ? "text-emerald-400" : "text-amber-400"}`}>
                  {geometryIssuesCount} {geometryIssuesCount === 1 ? "issue" : "issues"}
                </span>
              </div>

              {/* Fallback Pill */}
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#141620] border border-[#232738] text-[11px] font-mono">
                <span className="text-gray-400">Fallback:</span>
                <span className={`font-bold ${isFallback ? "text-amber-400" : "text-gray-300"}`}>
                  {isFallback ? "ACTIVE" : "NONE"}
                </span>
              </div>
            </div>

            {/* Right Header Quick Actions / Metrics */}
            <div className="flex items-center gap-3 ml-auto">
              {/* Benchmarks Button */}
              {onOpenBenchmarks && (
                <button
                  type="button"
                  data-testid="btn-open-benchmarks"
                  onClick={onOpenBenchmarks}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950/40 hover:bg-cyan-900/50 border border-cyan-500/40 text-cyan-300 text-xs font-mono transition-colors cursor-pointer"
                >
                  <Award className="w-3.5 h-3.5 text-cyan-400" />
                  <span>
                    {benchmarks.length > 0
                      ? `Benchmarks: ${passedBenchmarksCount}/${benchmarks.length} Passed`
                      : "Benchmarks Audit"}
                  </span>
                </button>
              )}

              {/* Coverage Gauge */}
              <div className="flex items-center gap-2 bg-[#14151b] border border-[#242632] px-3 py-1.5 rounded-lg">
                <Layers className="w-3.5 h-3.5 text-cyan-400" />
                <div className="flex flex-col">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[9px] font-semibold uppercase tracking-wider text-gray-400">
                      Coverage
                    </span>
                    <span className="text-xs font-mono font-bold text-cyan-300">
                      {coveragePct}%
                    </span>
                  </div>
                  <div className="w-20 h-1.5 bg-gray-800 rounded-full overflow-hidden mt-0.5">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 rounded-full transition-all duration-300"
                      style={{ width: `${Math.min(100, Math.max(0, coveragePct))}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Collapse Toggle */}
              <button
                onClick={() => setExpanded(!expanded)}
                className="p-1.5 rounded-lg bg-[#181a22] hover:bg-[#20232f] text-gray-400 hover:text-gray-200 border border-[#2c2f3d] transition-colors"
                title={expanded ? "Collapse details" : "Expand details"}
              >
                {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Decoupled Hostile Auditor Warning if Numerically Converged but Physically Questionable */}
          {isNumericallyConvergedPhysicallyQuestionable && (
            <div className="p-3 bg-amber-950/50 border border-amber-500/60 rounded-lg flex items-start gap-2.5 text-amber-200 text-xs">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <strong className="uppercase tracking-wider">CAE AUDIT WARNING: NUMERICALLY CONVERGED, PHYSICALLY QUESTIONABLE</strong>
                <p className="text-amber-300/80 mt-0.5 text-[11px] leading-relaxed">
                  Newton-Raphson constraints converged to zero mathematical residual, but resulting camber slopes, scrub radius, or motion ratios fall outside plausible high-performance vehicle dynamics bounds. Review physical validation issues below before manufacturing or track testing.
                </p>
              </div>
            </div>
          )}

          {/* Provenance and Reproducibility Fingerprint */}
          {reproducibility && (
            <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-[#1a1c24] text-[10px] font-mono text-gray-400">
              <div className="flex items-center gap-1.5 text-gray-300">
                <Fingerprint className="w-3.5 h-3.5 text-purple-400" />
                <span>Input SHA: <strong className="text-purple-300">{reproducibility.input_hash.slice(0, 10)}…</strong></span>
              </div>
              <div className="flex items-center gap-1.5 text-gray-300">
                <span>Output SHA: <strong className="text-cyan-300">{reproducibility.output_hash.slice(0, 10)}…</strong></span>
              </div>
              <div className="flex items-center gap-1.5 text-gray-400 ml-auto">
                <span>Solver Build: {reproducibility.solver_build}</span>
                {convergenceSummary && <span>• {convergenceSummary}</span>}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Diagnostic Remediation & Detail Body ──────────────────────────── */}
      {expanded && (
        <div className="p-4 bg-[#0a0b0e] space-y-4">
          {/* Critical Solver / Model Failure Banner */}
          {!isValid && (
            <div className="p-3 bg-rose-950/40 border border-rose-500/50 rounded-lg flex items-start gap-3">
              <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-xs font-bold text-rose-200 uppercase tracking-wider">
                  Kinematic Inadmissibility Detected
                </h4>
                <p className="text-xs text-rose-300/80 mt-0.5">
                  The current suspension coordinates violate rigid-body mobility constraints or Newton-Raphson convergence tolerances. Review the 5-point diagnostic remediation steps below.
                </p>
              </div>
            </div>
          )}

          {/* Diagnostic Remediation Cards (5 Required Fields) */}
          {issues.length > 0 ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-gray-300 uppercase tracking-wider">
                <Wrench className="w-4 h-4 text-amber-400" />
                <span>Diagnostic Remediation Checklist ({issues.length} {issues.length === 1 ? "Issue" : "Issues"})</span>
              </div>

              <div className="grid grid-cols-1 gap-3">
                {issues.map((issue, idx) => {
                  const what = issue.what_is_invalid || issue.issue || "Geometric Constraint Violation";
                  const why = issue.why || issue.reason || "Hardpoint relationship violates double-wishbone degrees of freedom.";
                  const param = issue.affected_parameter || "Hardpoint Coordinates";
                  const safeRange = issue.safe_range || "Standard kinematic domain limits";
                  const action = issue.what_engineer_should_change || "Adjust inboard/outboard pivot coordinates to restore clearance.";
                  const severity = issue.severity || "CRITICAL";

                  const isCrit = severity === "CRITICAL";

                  return (
                    <div
                      key={idx}
                      className={`border rounded-lg p-3.5 bg-[#0e1017] transition-colors ${
                        isCrit ? "border-rose-600/60 bg-rose-950/10" : "border-amber-600/50 bg-amber-950/10"
                      }`}
                    >
                      {/* Header */}
                      <div className="flex items-center justify-between gap-2 pb-2 border-b border-[#1e2230]">
                        <div className="flex items-center gap-2">
                          {isCrit ? (
                            <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                          ) : (
                            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                          )}
                          <span className="font-semibold text-xs text-gray-100">{what}</span>
                        </div>
                        <span
                          className={`text-[9px] font-mono px-2 py-0.5 rounded font-bold uppercase ${
                            isCrit
                              ? "bg-rose-900/60 text-rose-300 border border-rose-700/50"
                              : "bg-amber-900/60 text-amber-300 border border-amber-700/50"
                          }`}
                        >
                          {severity}
                        </span>
                      </div>

                      {/* 5-Field Grid */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 text-xs">
                        {/* 1. What is invalid */}
                        <div className="bg-[#12141d] p-2 rounded border border-[#222533]">
                          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-0.5">
                            1. What is Invalid
                          </span>
                          <span className="text-gray-200 font-mono text-[11px]">{what}</span>
                        </div>

                        {/* 2. Why (Physical Mechanism) */}
                        <div className="bg-[#12141d] p-2 rounded border border-[#222533]">
                          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-0.5">
                            2. Why (Kinematic Mechanism)
                          </span>
                          <span className="text-gray-300 text-[11px] leading-relaxed">{why}</span>
                        </div>

                        {/* 3. Affected Parameter */}
                        <div className="bg-[#12141d] p-2 rounded border border-[#222533]">
                          <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider block mb-0.5">
                            3. Affected Parameter
                          </span>
                          <code className="text-cyan-300 font-mono text-[11px] px-1 py-0.5 rounded bg-cyan-950/40">
                            {param}
                          </code>
                        </div>

                        {/* 4. Safe Operating Range */}
                        <div className="bg-[#12141d] p-2 rounded border border-[#222533]">
                          <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider block mb-0.5">
                            4. Safe Design Range
                          </span>
                          <span className="text-emerald-300 font-mono text-[11px]">{safeRange}</span>
                        </div>
                      </div>

                      {/* 5. What Engineer Should Change */}
                      <div className="mt-3 p-2.5 rounded bg-amber-950/30 border border-amber-500/40">
                        <div className="flex items-start gap-2">
                          <Wrench className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                          <div>
                            <span className="text-[10px] font-bold text-amber-300 uppercase tracking-wider block mb-0.5">
                              5. Actionable Engineering Change
                            </span>
                            <p className="text-amber-100 text-[11px] leading-relaxed font-medium">
                              {action}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="p-3 bg-emerald-950/20 border border-emerald-500/30 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="text-xs text-emerald-200 font-medium">
                  All kinematic admissibility constraints satisfied (Wishbone triangular stability, ball-joint clearance, positive kingpin, scrub radius limits).
                </span>
              </div>
              <span className="text-[10px] font-mono text-emerald-400 font-bold px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-700/50">
                0 VIOLATIONS
              </span>
            </div>
          )}

          {/* Solver Provenance & Technical Metadata Footer */}
          <div className="p-3 bg-[#11131a] rounded-lg border border-[#1f222e] flex flex-wrap items-center justify-between gap-3 text-[11px] text-gray-400 font-mono">
            <div className="flex items-center gap-2">
              <span className="text-gray-500 font-sans">Topology:</span>
              <span className="text-gray-200 uppercase">{report?.topology || "Double Wishbone (SLA)"}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-500 font-sans">Tolerance:</span>
              <span className="text-cyan-400">1e-7 mm</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-500 font-sans">Status:</span>
              <span className={allConverged ? "text-emerald-400" : "text-rose-400"}>
                {allConverged ? "ALL ITERATIONS CONVERGED" : "PARTIAL DRIFT"}
              </span>
            </div>
            {backendInfo?.execution_time_ms !== undefined && (
              <div className="flex items-center gap-2">
                <span className="text-gray-500 font-sans">Solve Time:</span>
                <span className="text-gray-200">{backendInfo.execution_time_ms.toFixed(2)} ms</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
