"use client";

import React from "react";
import { Cpu, Activity, Clock, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";

interface SimulationStatusProps {
  solverName?: string;
  status?: "IDLE" | "RUNNING" | "COMPLETED" | "FAILED";
  convergence?: string;
  executionTimeMs?: number;
  progress?: number;
  lastRunLabel?: string;
  className?: string;
}

export default function SimulationStatus({
  solverName = "scipy.integrate.solve_ivp (RK45)",
  status = "COMPLETED",
  convergence = "Residual < 1e-6 (Tolerances 1e-4 / 1e-7)",
  executionTimeMs = 38,
  progress = 100,
  lastRunLabel = "RUN-VAL-7ceb75",
  className = "",
}: SimulationStatusProps) {
  const isRunning = status === "RUNNING";
  const isFailed = status === "FAILED";

  return (
    <div className={`p-4 rounded-2xl bg-[#111116] border border-white/[0.08] font-mono text-xs flex flex-col justify-between ${className}`}>
      <div className="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-1.5 text-gray-400 font-bold uppercase text-[10px]">
          <Cpu size={13} className="text-ansys-yellow" />
          <span>Physics Solver Status</span>
        </div>
        <div className="flex items-center gap-1.5">
          {isRunning ? (
            <span className="px-2 py-0.5 rounded bg-purple-950/60 border border-purple-500/40 text-purple-300 font-bold text-[10px] flex items-center gap-1">
              <Loader2 size={10} className="animate-spin" /> RUNNING
            </span>
          ) : isFailed ? (
            <span className="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-500/40 text-rose-400 font-bold text-[10px] flex items-center gap-1">
              <AlertCircle size={10} /> DIVERGED
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-500/40 text-emerald-400 font-bold text-[10px] flex items-center gap-1">
              <CheckCircle2 size={10} /> CONVERGED
            </span>
          )}
        </div>
      </div>

      <div className="space-y-1.5 text-[11px]">
        <div>
          <span className="text-gray-500">Solver:</span> <span className="text-white font-semibold">{solverName}</span>
        </div>
        <div>
          <span className="text-gray-500">Convergence:</span> <span className="text-emerald-400">{convergence}</span>
        </div>
        <div className="flex items-center justify-between">
          <span><span className="text-gray-500">Compute Time:</span> <span className="text-white">{executionTimeMs} ms</span></span>
          <span><span className="text-gray-500">Run:</span> <span className="text-ansys-yellow font-bold">{lastRunLabel}</span></span>
        </div>
      </div>

      {isRunning && (
        <div className="mt-2 w-full bg-white/10 h-1 rounded-full overflow-hidden">
          <div className="h-full bg-purple-500 rounded-full transition-all" style={{ width: `${progress}%` }} />
        </div>
      )}
    </div>
  );
}
