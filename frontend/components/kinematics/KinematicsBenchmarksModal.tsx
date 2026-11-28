"use client";

import React from "react";
import {
  X,
  BookOpen,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ExternalLink,
  Award,
} from "lucide-react";
import { KinematicsBenchmarkItem } from "../../lib/api_client";

export interface KinematicsBenchmarksModalProps {
  isOpen: boolean;
  onClose: () => void;
  benchmarks: KinematicsBenchmarkItem[];
}

export default function KinematicsBenchmarksModal({
  isOpen,
  onClose,
  benchmarks,
}: KinematicsBenchmarksModalProps) {
  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const passedCount = benchmarks.filter((b) => b.status === "PASS").length;
  const warnedCount = benchmarks.filter((b) => b.status === "WARN").length;
  const failedCount = benchmarks.filter((b) => b.status === "FAIL").length;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#0e1017] border border-[#262a3d] rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 bg-[#12141e] border-b border-[#222638] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-950/70 border border-cyan-500/40 text-cyan-300">
              <Award className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-100">
                Vehicle Dynamics Benchmarks Verification
              </h3>
              <p className="text-xs text-gray-400">
                Audited against authoritative vehicle dynamics literature references (Milliken, Gillespie, Dixon, Carroll Smith)
              </p>
            </div>
          </div>
          <button
            data-testid="btn-close-benchmarks"
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Summary Metric Ribbon */}
        <div className="px-6 py-3 bg-[#0a0b0e] border-b border-[#1c1f2e] flex items-center justify-between text-xs font-mono">
          <div className="flex items-center gap-4">
            <span className="text-gray-400">Total Benchmarks: <strong>{benchmarks.length}</strong></span>
            <span className="text-emerald-400">Passed: <strong>{passedCount}</strong></span>
            {warnedCount > 0 && <span className="text-amber-400">Warnings: <strong>{warnedCount}</strong></span>}
            {failedCount > 0 && <span className="text-rose-400">Failed: <strong>{failedCount}</strong></span>}
          </div>
          <span className="text-xs text-cyan-400 uppercase font-semibold">
            {failedCount === 0 ? "Admissible CAE Envelope" : "Compliance Audit Alert"}
          </span>
        </div>

        {/* Content Table / Cards */}
        <div className="p-6 space-y-3 max-h-[70vh] overflow-y-auto">
          {benchmarks.length === 0 && (
            <div className="p-6 rounded-xl border border-dashed border-[#262a3d] text-center text-xs font-mono text-gray-400">
              No benchmark comparison entries yet. Click Recompute Sweep to run solver compliance checks against canonical vehicle dynamics benchmarks.
            </div>
          )}
          {benchmarks.map((item) => {
            const isPass = item.status === "PASS";
            const isWarn = item.status === "WARN";
            const isFail = item.status === "FAIL";

            return (
              <div
                key={item.id}
                className={`p-4 rounded-xl border transition-colors ${
                  isPass
                    ? "bg-[#11141e]/90 border-emerald-500/30"
                    : isWarn
                    ? "bg-[#161413]/90 border-amber-500/40"
                    : "bg-[#181114]/90 border-rose-500/40"
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-white/5">
                  <div className="flex items-center gap-2.5">
                    {isPass && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />}
                    {isWarn && <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />}
                    {isFail && <XCircle className="w-4 h-4 text-rose-400 shrink-0" />}
                    <span className="font-bold text-sm text-gray-100">{item.name}</span>
                    <span className="text-xs font-mono text-zinc-400 bg-white/5 px-1.5 py-0.5 rounded">
                      {item.id}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs font-mono font-bold px-2 py-0.5 rounded uppercase border ${
                        isPass
                          ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/50"
                          : isWarn
                          ? "bg-amber-950/80 text-amber-300 border-amber-500/50"
                          : "bg-rose-950/80 text-rose-300 border-rose-500/50"
                      }`}
                    >
                      {item.status} ({(item.error_pct ?? 0).toFixed(1)}% err)
                    </span>
                  </div>
                </div>

                {/* Values comparison grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mt-3 text-xs font-mono">
                  <div className="bg-black/30 p-2 rounded border border-white/5">
                    <span className="text-xs text-gray-400 block uppercase">Literature Reference</span>
                    <span className="text-gray-200 font-bold">{item.reference_value} {item.unit}</span>
                  </div>
                  <div className="bg-black/30 p-2 rounded border border-white/5">
                    <span className="text-xs text-gray-400 block uppercase">Current Production</span>
                    <span className="text-cyan-300 font-bold">{item.production_value} {item.unit}</span>
                  </div>
                  <div className="bg-black/30 p-2 rounded border border-white/5">
                    <span className="text-xs text-gray-400 block uppercase">Tolerance Allowed</span>
                    <span className="text-gray-300 font-bold">±{item.tolerance_pct}%</span>
                  </div>
                  <div className="bg-black/30 p-2 rounded border border-white/5">
                    <span className="text-xs text-gray-400 block uppercase">Relative Error</span>
                    <span className={`font-bold ${isPass ? "text-emerald-400" : isWarn ? "text-amber-400" : "text-rose-400"}`}>
                      {(item.error_pct ?? 0).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Source & Description Footer */}
                <div className="mt-3 pt-2 border-t border-white/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs text-gray-400">
                  <div className="flex items-center gap-1.5 text-cyan-400/90 font-medium">
                    <BookOpen className="w-3.5 h-3.5" />
                    <span>Source: {item.reference_source}</span>
                  </div>
                  <span className="text-gray-400 text-xs">{item.description}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-[#0a0b0e] border-t border-[#1c1f2e] flex items-center justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white font-medium text-xs transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
