"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  XCircle,
  HelpCircle,
  RotateCcw,
  Copy,
  CheckCircle2,
  ChevronDown,
  Info,
  Bug,
  Compass,
} from "lucide-react";

export interface ParsedEngineeringError {
  cause: string;
  impact: string;
  nextAction: string;
  what: string;
  where: string;
  why: string;
  whatToDo: string;
  // 5 Explicit Engineering Failure Factors
  whatFailed: string;
  whyFailed: string;
  whatRemainsValid: string;
  whatCannotBeClaimed: string;
  whatUserCanDoNext: string;
  code?: string;
  requestId?: string;
  rawDetails?: string;
  severity: "FATAL" | "DIVERGENCE" | "VALIDATION" | "SYSTEM";
}

export function parseEngineeringError(err: unknown): ParsedEngineeringError {
  if (!err) {
    return {
      cause: "An unhandled runtime exception occurred in the simulation pipeline.",
      impact: "Numerical state integration was interrupted before convergence.",
      nextAction: "Review system logs and retry the simulation.",
      what: "Simulation Pipeline",
      where: "Runtime Environment",
      why: "An unhandled runtime exception occurred in the simulation pipeline.",
      whatToDo: "Review system logs and retry the simulation.",
      whatFailed: "Simulation Pipeline Execution",
      whyFailed: "An unhandled runtime exception occurred in the simulation pipeline.",
      whatRemainsValid: "Workspace vehicle model templates and previously saved setups.",
      whatCannotBeClaimed: "Convergence and derived KPIs for the interrupted run.",
      whatUserCanDoNext: "Review system logs, verify parameter values, and retry.",
      severity: "SYSTEM",
    };
  }

  const errString = typeof err === "string" ? err : (err as any)?.message || JSON.stringify(err);
  let parsedJson: any = null;

  try {
    const jsonMatch = errString.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      parsedJson = JSON.parse(jsonMatch[0]);
    }
  } catch {}

  const detail = parsedJson?.detail || errString;
  const requestId = parsedJson?.request_id || (err as any)?.requestId || "req-" + Math.random().toString(36).slice(2, 9);
  const code = parsedJson?.type ? parsedJson.type.split("/").pop() : (err as any)?.code || "SIMULATION_ERROR";

  // 1. Negative Mass / Zero Damping Physics Rules
  if (detail.toLowerCase().includes("mass cannot be negative") || detail.toLowerCase().includes("negative mass") || detail.toLowerCase().includes("mass is too low")) {
    const cause = "Physical mass specified as non-positive (m_s <= 0 or m_u <= 0). Real inertial matrices must remain strictly positive-definite.";
    const impact = "Inertial acceleration division by non-positive mass causes immediate state-space numerical singularity.";
    const nextAction = "Specify realistic positive vehicle masses (e.g. sprung mass m_s in [150, 1200] kg, unsprung mass m_u in [20, 80] kg).";
    return {
      cause,
      impact,
      nextAction,
      what: "Rigid Body Inertial Matrix",
      where: "Parameter `m_s` (Sprung Mass) / `m_u` (Unsprung Mass)",
      why: cause,
      whatToDo: nextAction,
      whatFailed: "Rigid Body Inertia Matrix (m_s / m_u <= 0)",
      whyFailed: cause,
      whatRemainsValid: "Static geometry, linkage coordinates, and tire spring stiffness definitions.",
      whatCannotBeClaimed: "Any dynamic transient response, natural frequency, or damping ratio.",
      whatUserCanDoNext: nextAction,
      code: "INERTIA_INVALID",
      requestId,
      rawDetails: detail,
      severity: "VALIDATION",
    };
  }

  if (detail.toLowerCase().includes("undamped system") || detail.toLowerCase().includes("c = 0") || detail.toLowerCase().includes("zero damping")) {
    const cause = "Zero or negligible damping coefficient (c = 0 Ns/m) eliminates energy dissipation from the quarter car system.";
    const impact = "Pure imaginary system eigenvalues (+/- j*omega_n) cause unbounded state resonance and solver divergence.";
    const nextAction = "Increase damping coefficient c >= 800 Ns/m to achieve minimum damping ratio zeta_s >= 0.20.";
    return {
      cause,
      impact,
      nextAction,
      what: "Damped Harmonic Oscillator",
      where: "Parameter `c` (Damper Rate) / `zeta_s` (Damping Ratio)",
      why: cause,
      whatToDo: nextAction,
      whatFailed: "Suspension Damper Energy Dissipation (c = 0)",
      whyFailed: cause,
      whatRemainsValid: "Static wheel rate, spring rate k_s, and geometric roll centers.",
      whatCannotBeClaimed: "Ride comfort index, settling time, or crest stability.",
      whatUserCanDoNext: nextAction,
      code: "UNDAMPED_RESONANCE",
      requestId,
      rawDetails: detail,
      severity: "DIVERGENCE",
    };
  }

  // 2. Numerical Divergence / Step Size Underflow
  if (detail.toLowerCase().includes("step size underflow") || detail.toLowerCase().includes("diverge") || detail.toLowerCase().includes("singularity")) {
    const cause = "Adaptive step size underflow in scipy.integrate.solve_ivp (local truncation error exceeded tolerances).";
    const impact = "Explicit RK45 integrator halted due to stiff system matrix; trajectory cannot advance.";
    const nextAction = "Switch solver formulation to stiff Radau/BDF method or adjust damping to condition the stiffness matrix.";
    return {
      cause,
      impact,
      nextAction,
      what: "Adaptive ODE Integrator (scipy.solve_ivp)",
      where: "Solver Integration Loop (RK45 / Radau)",
      why: cause,
      whatToDo: nextAction,
      whatFailed: "Adaptive ODE State Integration (Step-Size Underflow)",
      whyFailed: cause,
      whatRemainsValid: "Pre-divergence time-history steps, static equilibrium state, and parameter bounds.",
      whatCannotBeClaimed: "Post-event transient trajectory, peak tire deflection, or full cycle settling time.",
      whatUserCanDoNext: nextAction,
      code: "SOLVER_DIVERGENCE",
      requestId,
      rawDetails: detail,
      severity: "DIVERGENCE",
    };
  }

  // 3. Rate Limit / Quota Exceeded
  if (detail.toLowerCase().includes("rate limit") || detail.toLowerCase().includes("quota") || detail.toLowerCase().includes("429")) {
    const cause = "Concurrent simulation limit for your workspace plan tier has been reached.";
    const impact = "Simulation compute job rejected or throttled by API gateway / Redis worker queue.";
    const nextAction = "Wait for active simulation jobs to complete or cancel stale jobs in the Workspace.";
    return {
      cause,
      impact,
      nextAction,
      what: "Compute Governance & Worker Quota",
      where: "Redis Worker Queue / API Gateway",
      why: cause,
      whatToDo: nextAction,
      whatFailed: "Compute Worker Queue Allocation",
      whyFailed: cause,
      whatRemainsValid: "All prior completed simulation runs and baseline KPI caches.",
      whatCannotBeClaimed: "Real-time dispatch guarantee for queued simulation tasks.",
      whatUserCanDoNext: nextAction,
      code: "QUOTA_EXCEEDED",
      requestId,
      rawDetails: detail,
      severity: "SYSTEM",
    };
  }

  // 4. General RFC 7807 Validation Error
  let detailObj: any = null;
  if (typeof detail === "string") {
    try {
      detailObj = JSON.parse(detail);
    } catch {}
  }

  const errorsList = parsedJson?.errors || detailObj?.errors || (Array.isArray(detailObj) ? detailObj : null);
  if (errorsList && Array.isArray(errorsList) && errorsList.length > 0) {
    const firstErr = errorsList[0];
    const loc = Array.isArray(firstErr.loc) ? firstErr.loc.join(" -> ") : "Request Payload";
    const cause = firstErr.msg || "Input parameter failed boundary or type constraint validation.";
    const impact = "Payload rejected by schema contract validation before physics solver initialization.";
    const nextAction = "Review input parameter bounds and enter a valid engineering value.";
    return {
      cause,
      impact,
      nextAction,
      what: "API Schema Contract Verification",
      where: loc,
      why: cause,
      whatToDo: nextAction,
      whatFailed: `Parameter Validation Failure at ${loc}`,
      whyFailed: cause,
      whatRemainsValid: "Unmodified workspace parameters, vehicle geometry, and historical results.",
      whatCannotBeClaimed: "Simulation feasibility with out-of-bounds parameters.",
      whatUserCanDoNext: nextAction,
      code: firstErr.type || "VALIDATION_FAILED",
      requestId: detailObj?.request_id || requestId,
      rawDetails: typeof detail === "string" ? detail : JSON.stringify(detail),
      severity: "VALIDATION",
    };
  }

  // Fallback parsed error
  const fallbackCause = detail.slice(0, 300);
  const fallbackImpact = "Solver execution interrupted before KPI extraction.";
  const fallbackAction = "Verify input parameters or test in Sandbox mode.";
  return {
    cause: fallbackCause,
    impact: fallbackImpact,
    nextAction: fallbackAction,
    what: "Simulation Pipeline Execution",
    where: "Backend Solver Service",
    why: fallbackCause,
    whatToDo: fallbackAction,
    whatFailed: "Numerical Solver Execution",
    whyFailed: fallbackCause,
    whatRemainsValid: "Baseline vehicle definition and telemetry cache.",
    whatCannotBeClaimed: "KPI accuracy and dynamic stability for this configuration.",
    whatUserCanDoNext: fallbackAction,
    code,
    requestId,
    rawDetails: detail,
    severity: "FATAL",
  };
}

export interface EngineeringErrorDisplayProps {
  error: unknown;
  onRetry?: () => void;
  onDismiss?: () => void;
  retryCount?: number;
}

export default function EngineeringErrorDisplay({
  error,
  onRetry,
  onDismiss,
  retryCount = 0,
}: EngineeringErrorDisplayProps) {
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!error) return null;

  const diag = parseEngineeringError(error);

  const getSeverityBadge = () => {
    switch (diag.severity) {
      case "DIVERGENCE":
        return "bg-amber-950/70 border-amber-500/50 text-amber-300";
      case "VALIDATION":
        return "bg-blue-950/70 border-blue-500/50 text-blue-300";
      case "FATAL":
      default:
        return "bg-rose-950/70 border-rose-500/50 text-rose-300";
    }
  };

  const copyDiagnostics = () => {
    const text = `SUSPENSIONLAB ENGINEERING FAILURE DIAGNOSTICS:
1. WHAT FAILED: ${diag.whatFailed}
2. WHY: ${diag.whyFailed}
3. WHAT REMAINS VALID: ${diag.whatRemainsValid}
4. WHAT CANNOT BE CLAIMED: ${diag.whatCannotBeClaimed}
5. WHAT THE USER CAN DO NEXT: ${diag.whatUserCanDoNext}

SYSTEM CONTEXT:
CAUSE: ${diag.cause}
IMPACT: ${diag.impact}
SUBSYSTEM: ${diag.where}
ERROR CODE: ${diag.code || "SIMULATION_ERROR"}
REQUEST ID: ${diag.requestId || "N/A"}
SEVERITY: ${diag.severity}
RAW DETAILS: ${diag.rawDetails || "N/A"}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="p-5 rounded-2xl bg-[#111116] border border-rose-500/50 text-white shadow-2xl space-y-4 my-4 animate-in fade-in zoom-in-95 duration-150"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-rose-500/20 border border-rose-500/40 flex items-center justify-center shrink-0">
            <XCircle size={18} className="text-rose-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-extrabold text-sm text-white tracking-tight">
                Engineering Solver Diagnostics &amp; Failure Analysis
              </h3>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold border ${getSeverityBadge()}`}>
                {diag.severity}
              </span>
            </div>
            <div className="text-[10px] font-mono text-gray-400 mt-0.5">
              Ref: <span className="text-gray-300">{diag.requestId}</span> | Code: <span className="text-ansys-yellow">{diag.code}</span>
              {retryCount > 0 && <span className="ml-2 text-amber-400 font-bold">(Attempt #{retryCount})</span>}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={copyDiagnostics}
            className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs font-mono text-gray-300 flex items-center gap-1.5 transition-colors"
            title="Copy structured diagnostics for audit or bug report"
          >
            {copied ? <CheckCircle2 size={12} className="text-emerald-400" /> : <Copy size={12} />}
            {copied ? "Copied" : "Copy Diagnostics"}
          </button>
          {onDismiss && (
            <button
              onClick={onDismiss}
              aria-label="Dismiss error"
              className="p-1 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* 5 Explicit Engineering Failure Factors */}
      <div className="space-y-2.5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
          {/* 1. WHAT FAILED */}
          <div className="p-3 rounded-xl bg-rose-950/20 border border-rose-500/30 space-y-1">
            <span className="text-[10px] uppercase font-bold text-rose-400 flex items-center gap-1.5">
              <Bug size={12} /> 1. What Failed
            </span>
            <p className="text-gray-200 font-semibold leading-relaxed font-sans text-xs">{diag.whatFailed}</p>
            {diag.where && diag.where !== "Runtime Environment" && (
              <div className="text-[10px] text-zinc-400 font-mono flex items-center gap-1 pt-1">
                <Compass size={10} className="text-zinc-500" />
                <span>Location: {diag.where}</span>
              </div>
            )}
          </div>

          {/* 2. WHY */}
          <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-500/30 space-y-1">
            <span className="text-[10px] uppercase font-bold text-amber-400 flex items-center gap-1.5">
              <HelpCircle size={12} /> 2. Why It Failed
            </span>
            <p className="text-gray-200 leading-relaxed font-sans text-xs">{diag.whyFailed}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
          {/* 3. WHAT REMAINS VALID */}
          <div className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/30 space-y-1">
            <span className="text-[10px] uppercase font-bold text-emerald-400 flex items-center gap-1.5">
              <CheckCircle2 size={12} /> 3. What Remains Valid
            </span>
            <p className="text-zinc-300 leading-relaxed font-sans text-xs">{diag.whatRemainsValid}</p>
          </div>

          {/* 4. WHAT CANNOT BE CLAIMED */}
          <div className="p-3 rounded-xl bg-purple-950/20 border border-purple-500/30 space-y-1">
            <span className="text-[10px] uppercase font-bold text-purple-400 flex items-center gap-1.5">
              <AlertTriangle size={12} /> 4. What Cannot Be Claimed
            </span>
            <p className="text-zinc-300 leading-relaxed font-sans text-xs">{diag.whatCannotBeClaimed}</p>
          </div>
        </div>

        {/* 5. WHAT THE USER CAN DO NEXT */}
        <div className="p-3 rounded-xl bg-cyan-950/20 border border-cyan-500/30 space-y-1">
          <span className="text-[10px] uppercase font-bold text-cyan-400 flex items-center gap-1.5">
            <Info size={12} /> 5. What You Can Do Next
          </span>
          <p className="text-cyan-200 font-semibold leading-relaxed font-sans text-xs">{diag.whatUserCanDoNext}</p>
        </div>
      </div>

      {/* Action Bar & Raw Trace Toggle */}
      <div className="flex items-center justify-between pt-2 border-t border-white/[0.06]">
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="text-[11px] font-mono text-gray-400 hover:text-white flex items-center gap-1 transition-colors"
        >
          <ChevronDown size={13} className={`transition-transform ${showRaw ? "rotate-180" : ""}`} />
          {showRaw ? "Hide Raw Stack Trace" : "View Raw Backend Stack Trace"}
        </button>

        <div className="flex items-center gap-2">
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="px-3 py-1.5 bg-white/5 hover:bg-white/10 text-gray-300 font-bold text-xs rounded-xl border border-white/10 transition-all"
            >
              Cancel
            </button>
          )}
          {onRetry && (
            <button
              onClick={onRetry}
              className="px-4 py-1.5 bg-ansys-yellow text-black font-bold text-xs rounded-xl hover:brightness-110 flex items-center gap-1.5 transition-all shadow-lg"
            >
              <RotateCcw size={13} />
              Retry Simulation
            </button>
          )}
        </div>
      </div>

      {showRaw && (
        <div className="p-3 rounded-xl bg-black/60 border border-white/5 font-mono text-[11px] text-gray-400 whitespace-pre-wrap overflow-x-auto max-h-48 custom-scrollbar">
          {diag.rawDetails || "No raw details available."}
        </div>
      )}
    </div>
  );
}
