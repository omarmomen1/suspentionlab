"use client";

import React from "react";
import {
  X,
  AlertOctagon,
  CheckCircle2,
  AlertTriangle,
  Wrench,
  ShieldAlert,
} from "lucide-react";
import { SolverPointDiagnostic } from "../../lib/api_client";

export interface FailedPointModalProps {
  isOpen: boolean;
  onClose: () => void;
  diagnostic: SolverPointDiagnostic | null;
  travelMm: number;
}

export default function FailedPointModal({
  isOpen,
  onClose,
  diagnostic,
  travelMm,
}: FailedPointModalProps) {
  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !diagnostic) return null;

  const failureReason = diagnostic.failure_reason || "Newton-Raphson iteration limit exceeded residual tolerance";
  const condNum = diagnostic.condition_number;
  const isSingular = condNum !== null && condNum !== undefined && condNum > 1e12;
  const iters = diagnostic.iterations;
  const resNorm = diagnostic.residual_norm;
  const tol = diagnostic.tolerance;

  // 1. WHAT FAILED
  const whatFailed = `Newton–Raphson Solver Divergence at ${travelMm >= 0 ? `+${travelMm.toFixed(1)}` : travelMm.toFixed(1)} mm Travel`;

  // 2. WHY
  const whyFailed = isSingular
    ? `The 5×5 kinematic constraint Jacobian became singular (Condition Number: ${condNum.toExponential(2)}), indicating the linkage entered a toggle or kinematic dead-center position where instant angular velocity vectors degenerate.`
    : `Constraint residual norm (${resNorm.toExponential(2)}) exceeded convergence tolerance (${tol.toExponential(2)}) after ${iters} iterations. Link lengths or ball-joint envelopes cannot simultaneously satisfy rigid-body constraints at this deflection.`;

  // 3. WHAT REMAINS VALID
  const whatRemainsValid = `All sweep points prior to this travel threshold that converged with residual < ${tol.toExponential(1)} remain authentic, numerically exact, and safe for engineering analysis.`;

  // 4. WHAT CANNOT BE CLAIMED
  const whatCannotBeClaimed = `Kinematic derivatives (camber gain, bump steer rate), dynamic roll center heights, motion ratios, and jacking forces beyond this travel point are unphysical and cannot be cited in setup sheets or damper specifications.`;

  // 5. WHAT TO DO NEXT
  const whatToDoNext = isSingular
    ? "Relocate wishbone chassis or upright hardpoints to increase the angular separation between control arms, preventing linkage toggle in full travel."
    : "Inspect inboard vs outboard pivot heights (Z-axis). If running high travel targets, widen the vertical distance between upper and lower wishbones or reduce suspension stroke.";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#0e1017] border border-rose-500/50 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 bg-rose-950/40 border-b border-rose-500/30 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-rose-900/60 border border-rose-500/50 text-rose-300">
              <AlertOctagon className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-rose-900/80 text-rose-300 border border-rose-700/50">
                  {diagnostic.convergence_status}
                </span>
                <span className="text-xs font-mono text-gray-400">
                  Step {diagnostic.continuation_step}
                </span>
              </div>
              <h3 className="text-base font-bold text-gray-100 mt-0.5">
                Root-Cause Diagnostic Analysis
              </h3>
            </div>
          </div>
          <button
            data-testid="btn-close-failed-modal"
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
          {/* Numerical Diagnostics Quick Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 rounded-xl bg-[#13151f] border border-[#222535] text-xs font-mono">
            <div>
              <span className="text-[10px] text-gray-500 uppercase block">Travel</span>
              <span className="font-bold text-gray-200">{travelMm >= 0 ? `+${travelMm.toFixed(1)}` : travelMm.toFixed(1)} mm</span>
            </div>
            <div>
              <span className="text-[10px] text-gray-500 uppercase block">Iterations</span>
              <span className="font-bold text-rose-300">{iters} / {diagnostic.max_iterations}</span>
            </div>
            <div>
              <span className="text-[10px] text-gray-500 uppercase block">Residual Norm</span>
              <span className="font-bold text-rose-300">{resNorm.toExponential(2)}</span>
            </div>
            <div>
              <span className="text-[10px] text-gray-500 uppercase block">Condition #</span>
              <span className="font-bold text-amber-300">{condNum ? condNum.toExponential(1) : "N/A"}</span>
            </div>
          </div>

          {/* 5-Field Root Cause Breakdown */}
          <div className="space-y-3">
            {/* 1. What Failed */}
            <div className="p-3.5 rounded-xl bg-rose-950/20 border border-rose-500/30">
              <div className="flex items-center gap-2 text-xs font-bold text-rose-300 uppercase tracking-wider mb-1">
                <ShieldAlert className="w-4 h-4 text-rose-400" />
                <span>1. What Failed</span>
              </div>
              <p className="text-xs text-rose-100 font-medium leading-relaxed">
                {whatFailed}
              </p>
            </div>

            {/* 2. Why (Physical & Kinematic Mechanism) */}
            <div className="p-3.5 rounded-xl bg-[#12141e] border border-[#222533]">
              <div className="flex items-center gap-2 text-xs font-bold text-amber-300 uppercase tracking-wider mb-1">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <span>2. Why (Physical & Numerical Mechanism)</span>
              </div>
              <p className="text-xs text-gray-300 leading-relaxed font-sans">
                {whyFailed}
              </p>
              <div className="mt-2 text-[11px] font-mono text-gray-400 bg-black/40 p-2 rounded border border-white/5">
                {failureReason}
              </div>
            </div>

            {/* 3. What Remains Valid */}
            <div className="p-3.5 rounded-xl bg-[#12141e] border border-[#222533]">
              <div className="flex items-center gap-2 text-xs font-bold text-emerald-400 uppercase tracking-wider mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>3. What Remains Valid</span>
              </div>
              <p className="text-xs text-gray-300 leading-relaxed">
                {whatRemainsValid}
              </p>
            </div>

            {/* 4. What Cannot Be Claimed */}
            <div className="p-3.5 rounded-xl bg-[#12141e] border border-[#222533]">
              <div className="flex items-center gap-2 text-xs font-bold text-rose-400 uppercase tracking-wider mb-1">
                <AlertOctagon className="w-4 h-4 text-rose-400" />
                <span>4. What Cannot Be Claimed</span>
              </div>
              <p className="text-xs text-gray-300 leading-relaxed">
                {whatCannotBeClaimed}
              </p>
            </div>

            {/* 5. What To Do Next */}
            <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-500/30">
              <div className="flex items-center gap-2 text-xs font-bold text-amber-300 uppercase tracking-wider mb-1">
                <Wrench className="w-4 h-4 text-amber-400" />
                <span>5. What To Do Next (Engineering Remediation)</span>
              </div>
              <p className="text-xs text-amber-100 font-medium leading-relaxed">
                {whatToDoNext}
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-[#0a0b0e] border-t border-[#1e2230] flex items-center justify-between">
          <span className="text-[11px] font-mono text-gray-500">
            Continuation state: {diagnostic.continuation_state} | Fallback: {diagnostic.fallback_state}
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white font-medium text-xs transition-colors"
          >
            Acknowledge & Close
          </button>
        </div>
      </div>
    </div>
  );
}
