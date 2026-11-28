"use client";

import React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  AlertCircle,
  Info,
  ArrowRight,
  Clock,
  Compass,
  FileCheck2,
} from "lucide-react";
import EvidenceBadge, { EngineeringStateType } from "./EvidenceBadge";

export type QuestionSeverity = "CRITICAL" | "WARNING" | "INFO";
export type QuestionStatus =
  | "UNVALIDATED"
  | "INVESTIGATING"
  | "HYPOTHESIS_FORMED"
  | "EXPERIMENTING"
  | "RESOLVED";

export interface EngineeringQuestionData {
  id: string;
  title: string;
  severity: QuestionSeverity;
  timestamp: string;
  affectedSubsystem: string; // e.g. "Rear Damper / Aero Platform", "Front Axle / Grip", "Chassis Roll Center"
  evidence: Array<{
    label: string;
    value: string;
    residual?: string;
  }>;
  currentStatus: QuestionStatus;
  recommendedNextAction: string;
  investigationRoute?: string;
}

interface EngineeringQuestionProps {
  question: EngineeringQuestionData;
  onInvestigate?: (question: EngineeringQuestionData) => void;
  className?: string;
}

const SEVERITY_CONFIG: Record<
  QuestionSeverity,
  {
    badgeClass: string;
    borderClass: string;
    bgClass: string;
    icon: any;
  }
> = {
  CRITICAL: {
    badgeClass: "bg-rose-950/60 border-rose-500/50 text-rose-400",
    borderClass: "border-rose-500/30 hover:border-rose-500/60",
    bgClass: "bg-gradient-to-r from-rose-950/20 to-transparent",
    icon: AlertCircle,
  },
  WARNING: {
    badgeClass: "bg-amber-950/60 border-amber-500/50 text-amber-400",
    borderClass: "border-amber-500/30 hover:border-amber-500/60",
    bgClass: "bg-gradient-to-r from-amber-950/20 to-transparent",
    icon: AlertTriangle,
  },
  INFO: {
    badgeClass: "bg-blue-950/60 border-blue-500/50 text-blue-400",
    borderClass: "border-blue-500/30 hover:border-blue-500/60",
    bgClass: "bg-gradient-to-r from-blue-950/20 to-transparent",
    icon: Info,
  },
};

export default function EngineeringQuestion({
  question,
  onInvestigate,
  className = "",
}: EngineeringQuestionProps) {
  const sev = SEVERITY_CONFIG[question.severity] || SEVERITY_CONFIG.WARNING;
  const SevIcon = sev.icon;

  return (
    <div
      className={`p-5 rounded-2xl bg-[#0f0f14] border ${sev.borderClass} ${sev.bgClass} transition-all duration-200 shadow-lg ${className}`}
    >
      {/* Top Header: Severity, Subsystem, Timestamp, Status */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-0.5 rounded-md border text-xs font-mono font-bold uppercase tracking-wider flex items-center gap-1 ${sev.badgeClass}`}
          >
            <SevIcon size={11} />
            {question.severity}
          </span>
          <span className="text-xs font-semibold text-gray-300 flex items-center gap-1">
            <Compass size={12} className="text-signal" />
            {question.affectedSubsystem}
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-gray-400">
          <span className="flex items-center gap-1">
            <Clock size={11} /> {question.timestamp}
          </span>
          <EvidenceBadge state={question.currentStatus} size="xs" />
        </div>
      </div>

      {/* Question Title */}
      <h3 className="text-base font-bold text-white tracking-tight mb-3">
        {question.title}
      </h3>

      {/* Evidence Residuals Chips */}
      {question.evidence && question.evidence.length > 0 && (
        <div className="mb-4">
          <div className="text-xs font-mono uppercase tracking-wider text-gray-400 mb-1.5">
            Measured Evidence & Residuals:
          </div>
          <div className="flex flex-wrap gap-2">
            {question.evidence.map((ev, i) => (
              <div
                key={i}
                className="px-2.5 py-1 rounded-lg bg-black/40 border border-white/10 font-mono text-xs text-gray-300 flex items-center gap-1.5"
              >
                <span className="text-gray-400">{ev.label}:</span>
                <span className="font-bold text-white">{ev.value}</span>
                {ev.residual && (
                  <span className="text-amber-400 font-semibold text-xs">
                    (Residual: {ev.residual})
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Next Action & Investigation Trigger */}
      <div className="pt-3 border-t border-white/[0.06] flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-gray-300 font-sans max-w-lg">
          <strong className="text-signal font-mono text-xs uppercase mr-1">
            Recommended Action:
          </strong>
          {question.recommendedNextAction}
        </div>

        {onInvestigate ? (
          <button
            onClick={() => onInvestigate(question)}
            className="px-4 py-2 rounded-xl bg-signal text-carbon font-bold text-xs hover:brightness-110 transition-all flex items-center gap-1.5 font-mono shadow-[0_0_15px_rgba(242,169,0,0.2)] shrink-0 cursor-pointer"
          >
            <span>Launch Investigation</span>
            <ArrowRight size={13} />
          </button>
        ) : (
          <Link
            href={question.investigationRoute || `/investigate?id=${encodeURIComponent(question.id)}`}
            className="px-4 py-2 rounded-xl bg-signal text-carbon font-bold text-xs hover:brightness-110 transition-all flex items-center gap-1.5 font-mono shadow-[0_0_15px_rgba(242,169,0,0.2)] shrink-0"
          >
            <span>Launch Investigation</span>
            <ArrowRight size={13} />
          </Link>
        )}
      </div>
    </div>
  );
}
