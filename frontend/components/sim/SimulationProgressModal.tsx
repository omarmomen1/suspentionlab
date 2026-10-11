"use client";

import React, { useEffect, useState } from "react";
import {
  Clock,
  RotateCcw,
  Ban,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Cpu,
  ArrowRight,
  X,
  Layers,
} from "lucide-react";
import EngineeringErrorDisplay from "./EngineeringErrorDisplay";

export type SimulationJobStatus =
  | "QUEUED"
  | "RUNNING"
  | "COMPLETED"
  | "COMPLETED_WITH_WARNINGS"
  | "COMPLETED_VALID"
  | "FAILED"
  | "CANCELLED";

interface SimulationProgressModalProps {
  isOpen: boolean;
  jobId: string | null;
  status: SimulationJobStatus;
  progress: number; // 0 - 100
  simulationType?: string;
  error?: unknown;
  onCancel?: () => void;
  onRetry?: () => void;
  onClose?: () => void;
}

export default function SimulationProgressModal({
  isOpen,
  jobId,
  status,
  progress,
  simulationType = "Quarter Car Simulation",
  error,
  onCancel,
  onRetry,
  onClose,
}: SimulationProgressModalProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (isOpen && (status === "QUEUED" || status === "RUNNING")) {
      interval = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      setElapsedSeconds(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isOpen, status]);

  if (!isOpen) return null;

  const getStatusBadge = () => {
    switch (status) {
      case "QUEUED":
        return {
          bg: "bg-amber-950/40 border-amber-500/40 text-amber-300",
          icon: <Clock size={16} className="text-amber-400 animate-pulse" />,
          label: "QUEUED FOR COMPUTE",
        };
      case "RUNNING":
        return {
          bg: "bg-purple-950/40 border-purple-500/40 text-purple-300",
          icon: <Loader2 size={16} className="text-purple-400 animate-spin" />,
          label: "SOLVER RUNNING (RK45)",
        };
      case "COMPLETED":
      case "COMPLETED_VALID":
        return {
          bg: "bg-emerald-950/40 border-emerald-500/40 text-emerald-300",
          icon: <CheckCircle2 size={16} className="text-emerald-400" />,
          label: "SIMULATION COMPLETED",
        };
      case "COMPLETED_WITH_WARNINGS":
        return {
          bg: "bg-amber-950/40 border-amber-500/40 text-amber-300",
          icon: <AlertTriangle size={16} className="text-amber-400" />,
          label: "COMPLETED WITH WARNINGS",
        };
      case "CANCELLED":
        return {
          bg: "bg-gray-800/60 border-gray-600/40 text-gray-300",
          icon: <Ban size={16} className="text-gray-400" />,
          label: "JOB CANCELLED",
        };
      case "FAILED":
      default:
        return {
          bg: "bg-rose-950/40 border-rose-500/40 text-rose-300",
          icon: <AlertTriangle size={16} className="text-rose-400" />,
          label: "SOLVER FAILED",
        };
    }
  };

  const badge = getStatusBadge();

  // Determine current solver pipeline stage
  const getPipelineStage = () => {
    if (status === "QUEUED") return "Acquiring Redis compute worker slot...";
    if (status === "COMPLETED" || status === "COMPLETED_VALID") return "Integration complete. Compiling frequency spectrum.";
    if (status === "COMPLETED_WITH_WARNINGS") return "Integration complete with parameter warnings. Compiling frequency spectrum.";
    if (status === "FAILED") return "Integration halted due to physical/numerical exception.";
    if (status === "CANCELLED") return "Computation cancelled by user request.";
    if (progress < 30) return "Compiling coupled state-space equations (M, C, K matrices)";
    if (progress < 70) return "Integrating non-linear differential equations (SciPy RK45)";
    return "Evaluating FFT spectral transmissibility & RMS comfort metrics";
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-150 select-none">
      <div className="bg-[#111116] border border-white/10 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative text-white space-y-5">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-ansys-yellow/10 border border-ansys-yellow/30 flex items-center justify-center text-ansys-yellow">
              <Cpu size={18} />
            </div>
            <div>
              <h2 className="font-extrabold text-sm text-white tracking-tight">
                {simulationType}
              </h2>
              <div className="text-[10px] font-mono text-gray-400">
                Job ID: <span className="text-gray-300">{jobId || "pending-initialization"}</span>
              </div>
            </div>
          </div>

          {(status === "COMPLETED" ||
            status === "COMPLETED_WITH_WARNINGS" ||
            status === "COMPLETED_VALID" ||
            status === "FAILED" ||
            status === "CANCELLED") &&
            onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* Status Badge & Timer */}
        <div className="flex items-center justify-between">
          <div className={`px-3 py-1 rounded-full border text-xs font-mono font-bold flex items-center gap-2 ${badge.bg}`}>
            {badge.icon}
            {badge.label}
          </div>

          <div className="text-xs font-mono text-gray-400 flex items-center gap-1.5">
            <Clock size={13} className="text-gray-500" />
            <span>Elapsed: {elapsedSeconds}s</span>
          </div>
        </div>

        {/* Progress Bar & Stages */}
        <div className="space-y-2">
          <div className="flex justify-between text-xs font-mono">
            <span className="text-gray-400">{getPipelineStage()}</span>
            <span className="font-bold text-ansys-yellow">{Math.round(progress)}%</span>
          </div>

          <div className="h-2.5 w-full bg-white/[0.05] border border-white/[0.08] rounded-full overflow-hidden p-0.5">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                status === "FAILED"
                  ? "bg-rose-500"
                  : status === "CANCELLED"
                  ? "bg-gray-500"
                  : status === "COMPLETED" || status === "COMPLETED_VALID"
                  ? "bg-emerald-500"
                  : status === "COMPLETED_WITH_WARNINGS"
                  ? "bg-amber-500"
                  : "bg-gradient-to-r from-ansys-yellow to-amber-500"
              }`}
              style={{ width: `${Math.max(5, Math.min(100, progress))}%` }}
            />
          </div>
        </div>

        {/* Error Diagnostics (if failed) */}
        {status === "FAILED" && Boolean(error) ? (
          <EngineeringErrorDisplay error={error} onRetry={onRetry} />
        ) : null}

        {/* Action Controls */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-white/[0.08]">
          {(status === "QUEUED" || status === "RUNNING") && onCancel && (
            <button
              onClick={onCancel}
              className="px-4 py-2 rounded-xl bg-red-950/40 border border-red-500/30 text-red-400 hover:bg-red-950/60 font-bold text-xs flex items-center gap-1.5 transition-colors"
            >
              <Ban size={14} />
              Cancel Simulation
            </button>
          )}

          {(status === "FAILED" || status === "CANCELLED") && onRetry && (
            <button
              onClick={onRetry}
              className="px-4 py-2 bg-ansys-yellow text-black font-bold text-xs rounded-xl hover:brightness-110 flex items-center gap-1.5 transition-all shadow-lg"
            >
              <RotateCcw size={14} />
              Retry Job
            </button>
          )}

          {(status === "COMPLETED" ||
            status === "COMPLETED_WITH_WARNINGS" ||
            status === "COMPLETED_VALID") &&
            onClose && (
            <button
              onClick={onClose}
              className="px-5 py-2 bg-emerald-500 text-black font-bold text-xs rounded-xl hover:brightness-110 flex items-center gap-1.5 transition-all shadow-lg"
            >
              View Results
              <ArrowRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
