"use client";

import React, { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Hash,
  ShieldCheck,
  FileText,
} from "lucide-react";
import ApprovalState from "./ApprovalState";

export interface DecisionPayload {
  runLabel: string;
  verdict: "GOOD" | "WARNING" | "CRITICAL";
  headline: string;
  primaryReason?: string | null;
  layers?: {
    why?: string[];
    evidence?: Array<{
      label: string;
      key: string;
      value: number | string;
      unit: string;
      status: "pass" | "warn" | "fail";
    }>;
    raw_data?: {
      params_hash?: string;
      result_hash?: string;
    };
  };
  proposalId?: string;
  approvalStatus?: string;
  approvedRole?: string;
  approvalSignature?: string;
}

interface DecisionCardProps {
  decision: DecisionPayload;
  className?: string;
}

export default function DecisionCard({ decision, className = "" }: DecisionCardProps) {
  const [expanded, setExpanded] = useState(false);

  const verdictConfig = {
    GOOD: {
      border: "border-emerald-500/40",
      bg: "bg-emerald-950/20",
      text: "text-emerald-400",
      badgeBg: "bg-emerald-950/60 border-emerald-500/50",
      icon: CheckCircle2,
    },
    WARNING: {
      border: "border-amber-500/40",
      bg: "bg-amber-950/20",
      text: "text-amber-400",
      badgeBg: "bg-amber-950/60 border-amber-500/50",
      icon: AlertTriangle,
    },
    CRITICAL: {
      border: "border-rose-500/40",
      bg: "bg-rose-950/20",
      text: "text-rose-400",
      badgeBg: "bg-rose-950/60 border-rose-500/50",
      icon: AlertCircle,
    },
  }[decision.verdict] || {
    border: "border-white/10",
    bg: "bg-white/[0.02]",
    text: "text-gray-300",
    badgeBg: "bg-white/5 border-white/10",
    icon: AlertCircle,
  };

  const VerdictIcon = verdictConfig.icon;

  return (
    <div
      className={`p-6 rounded-3xl bg-[#111116] border ${verdictConfig.border} shadow-2xl relative flex flex-col justify-between transition-all ${className}`}
    >
      <div>
        {/* Layer 1: Decision Verdict Banner */}
        <div className="flex items-center justify-between gap-3 mb-4 pb-3 border-b border-white/[0.08]">
          <div className="flex items-center gap-2">
            <span
              className={`px-2.5 py-1 rounded-lg border font-mono font-extrabold text-xs tracking-wider flex items-center gap-1.5 ${verdictConfig.badgeBg} ${verdictConfig.text}`}
            >
              <VerdictIcon size={14} />
              {decision.verdict}
            </span>
            <span className="font-mono text-xs text-gray-400">Run: {decision.runLabel}</span>
          </div>

          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-400 hover:text-white flex items-center gap-1 font-mono"
          >
            <span>{expanded ? "Hide Details" : "Layer 3-4 Evidence"}</span>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {/* Layer 2: Headline & Primary Reason */}
        <div className="mb-4">
          <h3 className="text-xl font-extrabold text-white tracking-tight">{decision.headline}</h3>
          {decision.primaryReason && (
            <p className="text-xs text-gray-300 mt-1.5 font-sans leading-relaxed">
              {decision.primaryReason}
            </p>
          )}
        </div>

        {/* Expanded Layer 3: Specific Evidence Metrics */}
        {expanded && decision.layers?.evidence && decision.layers.evidence.length > 0 && (
          <div className="my-4 p-4 rounded-2xl bg-black/40 border border-white/5 space-y-2 font-mono text-xs">
            <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
              Layer 3 — Evidence Metrics:
            </div>
            {decision.layers.evidence.map((ev, i) => (
              <div
                key={i}
                className="p-2 rounded-xl bg-white/[0.02] border border-white/[0.04] flex items-center justify-between"
              >
                <span className="text-gray-300">{ev.label}:</span>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white">
                    {ev.value} {ev.unit}
                  </span>
                  <span
                    className={`text-xs px-1.5 py-0.2 rounded font-bold uppercase ${
                      ev.status === "pass"
                        ? "bg-emerald-950/60 text-emerald-400 border border-emerald-500/30"
                        : ev.status === "warn"
                        ? "bg-amber-950/60 text-amber-400 border border-amber-500/30"
                        : "bg-rose-950/60 text-rose-400 border border-rose-500/30"
                    }`}
                  >
                    {ev.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Expanded Layer 4: Raw Artifact Hashes */}
        {expanded && decision.layers?.raw_data && (
          <div className="my-3 p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] flex flex-wrap gap-4 text-xs font-mono text-zinc-400">
            {decision.layers.raw_data.params_hash && (
              <div className="flex items-center gap-1">
                <Hash size={11} /> Params Hash:{" "}
                <span className="text-gray-400">{decision.layers.raw_data.params_hash.slice(0, 12)}</span>
              </div>
            )}
            {decision.layers.raw_data.result_hash && (
              <div className="flex items-center gap-1">
                <Hash size={11} /> Result Hash:{" "}
                <span className="text-gray-400">{decision.layers.raw_data.result_hash.slice(0, 12)}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Governance Sign-Off State */}
      {decision.proposalId && (
        <div className="mt-4 pt-4 border-t border-white/[0.08]">
          <ApprovalState
            proposalId={decision.proposalId}
            status={decision.approvalStatus || "PROPOSED"}
            approvedByRole={decision.approvedRole}
            approvalSignature={decision.approvalSignature}
          />
        </div>
      )}
    </div>
  );
}
