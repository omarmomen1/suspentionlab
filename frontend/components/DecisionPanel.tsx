"use client";

/**
 * DecisionPanel — the layered decision UI (Issue 36).
 *
 *   Layer 1  DECISION   GOOD / WARNING / CRITICAL banner
 *   Layer 2  WHY        plain-language reasons
 *   Layer 3  EVIDENCE   the specific metrics behind each reason
 *   Layer 4  RAW DATA   expandable — full plots live in the parent page
 *
 * Engineers see one verdict first; detail is progressive disclosure,
 * never a wall of charts.
 *
 * Usage:
 *   <DecisionPanel decision={decision} />
 *
 * `decision` shape matches GET /api/v1/runs/{label}/decision:
 * { verdict: "GOOD"|"WARNING"|"CRITICAL", headline, primary_reason,
 *   layers: { why: string[], evidence: [{label,value,unit,status}],
 *             raw_data: {...} } }
 */

import React, { useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, ChevronDown, Layers } from "lucide-react";

export interface DecisionEvidence {
  label: string;
  key: string;
  value: number;
  unit: string;
  status: "pass" | "warn" | "fail";
}

export interface Decision {
  run?: string;
  verdict: "GOOD" | "WARNING" | "CRITICAL";
  headline: string;
  primary_reason?: string | null;
  layers: {
    why: string[];
    evidence: DecisionEvidence[];
    raw_data: Record<string, unknown>;
  };
}

const VERDICT_STYLE = {
  GOOD:     { color: "#22c55e", bg: "bg-emerald-950/30", border: "border-emerald-800/50", Icon: CheckCircle2 },
  WARNING:  { color: "#f59e0b", bg: "bg-amber-950/30",   border: "border-amber-800/50",  Icon: AlertTriangle },
  CRITICAL: { color: "#ef4444", bg: "bg-red-950/30",     border: "border-red-800/50",    Icon: XCircle },
} as const;

const STATUS_ICON = {
  pass: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />,
  warn: <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />,
  fail: <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />,
};

export default function DecisionPanel({ decision }: { decision: Decision | null }) {
  const [showWhy, setShowWhy] = useState(decision?.verdict !== "GOOD");
  const [showEvidence, setShowEvidence] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  if (!decision) return null;

  const { color, bg, border, Icon } = VERDICT_STYLE[decision.verdict];
  const hasWhy = (decision.layers?.why?.length ?? 0) > 0;

  return (
    <div
      data-testid="decision-panel"
      className={`rounded-xl border ${border} ${bg} p-4 space-y-3`}
      role="status"
      aria-label={`Simulation verdict: ${decision.verdict}`}
    >
      {/* ── LAYER 1: DECISION ─────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <Icon className="w-6 h-6 shrink-0" style={{ color }} />
        <div className="min-w-0">
          <div
            className="text-sm font-bold tracking-widest uppercase"
            style={{ color }}
          >
            {decision.verdict}
          </div>
          <div className="text-sm text-slate-200">{decision.headline}</div>
        </div>
        {decision.run && (
          <span className="ml-auto text-[10px] font-mono text-slate-500 uppercase tracking-widest">
            {decision.run}
          </span>
        )}
      </div>

      {/* ── LAYER 2: WHY ──────────────────────────────────────────────── */}
      {hasWhy && (
        <button
          onClick={() => setShowWhy((v) => !v)}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          aria-expanded={showWhy}
        >
          <Layers className="w-3.5 h-3.5" />
          Why? ({decision.layers.why.length} reason{decision.layers.why.length > 1 ? "s" : ""})
          <ChevronDown className={`w-3 h-3 transition-transform ${showWhy ? "rotate-180" : ""}`} />
        </button>
      )}
      {showWhy && hasWhy && (
        <ul className="space-y-1.5 pl-1">
          {decision.layers.why.map((reason, i) => (
            <li key={i} className="text-sm text-slate-300 leading-snug">
              {i === 0 && decision.primary_reason && (
                <span className="font-medium text-slate-100">Primary: </span>
              )}
              {reason}
            </li>
          ))}
        </ul>
      )}

      {/* ── LAYER 3: EVIDENCE ─────────────────────────────────────────── */}
      {(decision.layers?.evidence?.length ?? 0) > 0 && (
        <button
          onClick={() => setShowEvidence((v) => !v)}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          aria-expanded={showEvidence}
        >
          Evidence ({decision.layers.evidence.length} metric{decision.layers.evidence.length > 1 ? "s" : ""})
          <ChevronDown className={`w-3 h-3 transition-transform ${showEvidence ? "rotate-180" : ""}`} />
        </button>
      )}
      {showEvidence && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {decision.layers.evidence.map((ev) => (
            <div
              key={ev.key}
              className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2"
            >
              <div className="flex items-center gap-2 min-w-0">
                {STATUS_ICON[ev.status]}
                <span className="text-xs text-slate-300 truncate">{ev.label}</span>
              </div>
              <span className="text-xs font-mono text-white shrink-0 ml-2">
                {ev.value} {ev.unit}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ── LAYER 4: RAW DATA pointer ─────────────────────────────────── */}
      <button
        onClick={() => setShowRaw((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        aria-expanded={showRaw}
      >
        Raw data
        <ChevronDown className={`w-3 h-3 transition-transform ${showRaw ? "rotate-180" : ""}`} />
      </button>
      {showRaw && (
        <pre className="rounded-lg border border-slate-800 bg-black/40 p-3 text-[10px] font-mono text-slate-400 overflow-x-auto max-h-48 overflow-y-auto">
          {JSON.stringify(decision.layers.raw_data, null, 2)}
        </pre>
      )}
    </div>
  );
}
