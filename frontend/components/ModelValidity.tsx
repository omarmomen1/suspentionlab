"use client";

/**
 * ModelValidity — renders the MODEL VALIDITY confidence panel (Issue 16).
 *
 * Shows a 0-100 score bar plus a pass/warn/fail checklist explaining exactly
 * why the result should or should not be trusted.
 *
 * Usage:
 *   <ModelValidity report={validityReport} />
 *
 * `report` shape matches POST /api/v1/models/validity:
 *   { score: number, band: "High"|"Medium"|"Low", summary: string,
 *     checks: [{ label, status: "pass"|"warn"|"fail", detail }] }
 */

import React, { useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, ChevronDown, ShieldCheck } from "lucide-react";

export interface ValidityCheck {
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface ValidityReport {
  score: number;
  band: "High" | "Medium" | "Low";
  summary?: string;
  checks: ValidityCheck[];
}

const BAND_COLORS: Record<string, string> = {
  High: "#22c55e",
  Medium: "#f59e0b",
  Low: "#ef4444",
};

const STATUS_ICONS: Record<string, JSX.Element> = {
  pass: <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />,
  warn: <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />,
  fail: <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />,
};

export default function ModelValidity({ report }: { report: ValidityReport | null }) {
  const [expanded, setExpanded] = useState(false);

  if (!report || !report.checks || report.checks.length === 0) return null;

  const color = BAND_COLORS[report.band] ?? "#f59e0b";
  const filled = Math.round(report.score / 10);

  return (
    <div
      className="rounded-xl border bg-slate-900/40 p-4"
      style={{ borderColor: `${color}44` }}
      data-testid="model-validity"
    >
      {/* Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-4 text-left"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-3 min-w-0">
          <ShieldCheck className="w-5 h-5 shrink-0" style={{ color }} />
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-widest text-slate-400 font-medium">
              Model Validity
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-semibold" style={{ color }}>
                {Math.round(report.score)}%
              </span>
              <span className="text-sm text-slate-300">{report.band} confidence</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Score bar */}
          <div
            className="hidden sm:flex gap-[3px] items-center"
            role="meter"
            aria-valuenow={Math.round(report.score)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Model validity ${Math.round(report.score)} percent`}
          >
            {Array.from({ length: 10 }).map((_, i) => (
              <span
                key={i}
                className="w-2 h-5 rounded-sm transition-colors"
                style={{ backgroundColor: i < filled ? color : "#33415580" }}
              />
            ))}
          </div>
          <ChevronDown
            className={`w-4 h-4 text-slate-400 transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </div>
      </button>

      {/* Checklist */}
      {expanded && (
        <ul className="mt-3 space-y-2 border-t border-slate-800 pt-3">
          {report.checks.map((check, idx) => (
            <li key={idx} className="flex items-start gap-2.5 text-sm">
              {STATUS_ICONS[check.status]}
              <div>
                <span className="text-slate-200 font-medium">{check.label}</span>
                <span className="text-slate-400"> — {check.detail}</span>
              </div>
            </li>
          ))}
          {report.summary && (
            <li className="pt-1 text-xs text-slate-500 italic">{report.summary}</li>
          )}
        </ul>
      )}
    </div>
  );
}
