"use client";

import React from "react";
import { X, Info, ShieldCheck, Cpu, ArrowDown, Database, Hash, AlertTriangle } from "lucide-react";
import EvidenceBadge from "./EvidenceBadge";

export interface ProvenanceChainStep {
  title: string;
  detail: string;
  type?: "source" | "model" | "setup" | "simulation" | "calculation" | "result";
}

export interface ProvenanceData {
  result: string | number;
  resultUnit?: string;
  source: string;
  inputs?: Record<string, string | number>;
  method: string;
  modelVersion: string;
  solver: string;
  backend: string;
  validation: string;
  confidence?: number | string | null;
  limitations?: string[];
  chain?: ProvenanceChainStep[];
  canonicalHash?: string;
}

interface ProvenancePopoverProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  data?: ProvenanceData | null;
}

export default function ProvenancePopover({
  isOpen,
  onClose,
  title,
  data,
}: ProvenancePopoverProps) {
  if (!isOpen) return null;

  const hasEvidence = Boolean(data && data.source && data.method);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="provenance-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-150"
    >
      <div className="bg-[#111116] border border-white/10 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative text-white max-h-[90vh] overflow-y-auto custom-scrollbar">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 pb-4 border-b border-white/10 mb-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-ansys-yellow mb-1 font-mono">
              <Info size={14} />
              Mathematical & Causal Provenance [WHY?]
            </div>
            <h3 id="provenance-title" className="text-xl font-extrabold text-white">
              {title}
            </h3>
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors shrink-0"
          >
            <X size={18} />
          </button>
        </div>

        {!hasEvidence ? (
          <div className="p-8 rounded-xl bg-amber-950/20 border border-amber-500/30 text-center space-y-3 font-mono">
            <div className="w-12 h-12 rounded-full bg-amber-500/10 text-amber-400 flex items-center justify-center mx-auto">
              <AlertTriangle size={24} />
            </div>
            <h4 className="text-sm font-bold text-amber-300 uppercase tracking-wider">
              EVIDENCE UNAVAILABLE
            </h4>
            <p className="text-xs text-gray-400 max-w-md mx-auto">
              No mathematical derivation, telemetry trace, or solver artifact was recorded for this value.
              In accordance with scientific integrity rules, unverified numbers cannot be verified.
            </p>
          </div>
        ) : (
          <div className="space-y-5 text-xs font-mono">
            {/* Causal Chain Timeline */}
            {Array.isArray(data?.chain) && data.chain.length > 0 && (
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.08]">
                <div className="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-3 font-sans">
                  Physical Causal Chain
                </div>
                <div className="space-y-2">
                  {data.chain.map((step, idx) => (
                    <React.Fragment key={idx}>
                      <div className="p-2.5 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between">
                        <div>
                          <div className="font-bold text-white text-[11px]">{step.title}</div>
                          <div className="text-[10px] text-gray-400">{step.detail}</div>
                        </div>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-ansys-yellow uppercase">
                          Step {idx + 1}
                        </span>
                      </div>
                      {idx < (data.chain?.length ?? 0) - 1 && (
                        <div className="flex justify-center py-0.5 text-gray-600">
                          <ArrowDown size={14} />
                        </div>
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            )}

            {/* Structured Table: Result, Source, Method, Solver, Backend, Validation */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Result */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <div className="text-gray-500 text-[10px] uppercase font-bold">RESULT</div>
                <div className="text-lg font-extrabold text-ansys-yellow mt-0.5">
                  {data!.result} {data!.resultUnit && <span className="text-xs text-gray-400 font-normal">{data!.resultUnit}</span>}
                </div>
              </div>

              {/* Source */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <div className="text-gray-500 text-[10px] uppercase font-bold flex items-center gap-1">
                  <Database size={12} /> SOURCE
                </div>
                <div className="text-white font-semibold mt-0.5 truncate" title={data!.source}>
                  {data!.source}
                </div>
              </div>

              {/* Method */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <div className="text-gray-500 text-[10px] uppercase font-bold">METHOD / FORMULATION</div>
                <div className="text-white font-semibold mt-0.5">{data!.method}</div>
              </div>

              {/* Model Version */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <div className="text-gray-500 text-[10px] uppercase font-bold">MODEL VERSION</div>
                <div className="text-emerald-400 font-semibold mt-0.5">{data!.modelVersion}</div>
              </div>

              {/* Solver & Backend */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <div className="text-gray-500 text-[10px] uppercase font-bold flex items-center gap-1">
                  <Cpu size={12} /> SOLVER & BACKEND
                </div>
                <div className="text-white font-semibold mt-0.5">{data!.solver}</div>
                <div className="text-[10px] text-gray-500">{data!.backend}</div>
              </div>

              {/* Validation & Confidence */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <div className="text-gray-500 text-[10px] uppercase font-bold flex items-center gap-1">
                  <ShieldCheck size={12} /> VALIDATION & CONFIDENCE
                </div>
                <div className="text-white font-semibold mt-0.5">{data!.validation}</div>
                {data!.confidence !== undefined && data!.confidence !== null && (
                  <div className="text-[10px] text-purple-400">Confidence: {data!.confidence}</div>
                )}
              </div>
            </div>

            {/* Inputs Snapshot */}
            {data!.inputs && Object.keys(data!.inputs).length > 0 && (
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <div className="text-gray-500 text-[10px] uppercase font-bold mb-2">INPUT PARAMETERS</div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                  {Object.entries(data!.inputs).map(([k, v]) => (
                    <div key={k} className="p-1.5 rounded bg-black/30 border border-white/5">
                      <span className="text-gray-500">{k}:</span> <span className="text-white font-bold">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Limitations */}
            {Array.isArray(data?.limitations) && data.limitations.length > 0 && (
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <div className="text-gray-500 text-[10px] uppercase font-bold mb-1.5 flex items-center gap-1">
                  <AlertTriangle size={12} className="text-amber-400" /> KNOWN LIMITATIONS
                </div>
                <ul className="list-disc list-inside space-y-1 text-[11px] text-gray-300">
                  {data.limitations.map((lim, i) => (
                    <li key={i}>{lim}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Cryptographic Hash */}
            {data!.canonicalHash && (
              <div className="flex items-center justify-between text-[10px] text-gray-500 pt-2 border-t border-white/5">
                <span className="flex items-center gap-1">
                  <Hash size={11} /> SHA-256 Provenance Hash:
                </span>
                <span className="font-mono text-gray-400">{data!.canonicalHash}</span>
              </div>
            )}
          </div>
        )}

        {/* Action Button */}
        <div className="mt-6 pt-4 border-t border-white/10 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-ansys-yellow text-black font-bold text-xs hover:brightness-110 transition-colors font-mono"
          >
            Acknowledge Evidence
          </button>
        </div>
      </div>
    </div>
  );
}
