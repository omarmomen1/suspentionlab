"use client";

/**
 * ModelValidity — renders the 4-Tier MODEL VALIDITY confidence engine.
 *
 * Tier Taxonomy:
 * - VALIDATED: Within calibrated test domain; verified telemetry correlation.
 * - CONDITIONAL: Directionally accurate; secondary approximations in effect.
 * - EXPERIMENTAL: Simplified kinematics or synthetic inputs; exploratory design.
 * - OUT-OF-DOMAIN: Operating outside physical/solver bounds or severe bottoming.
 */

import React, { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ShieldCheck,
  ShieldAlert,
  Info,
  Cpu,
} from "lucide-react";

export type ModelValidityTier = "VALIDATED" | "CONDITIONAL" | "EXPERIMENTAL" | "OUT-OF-DOMAIN";

export interface ValidityCheck {
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface ValidityReport {
  score: number;
  band?: "High" | "Medium" | "Low";
  status_tier?: ModelValidityTier;
  summary?: string;
  checks: ValidityCheck[];
  provenance?: {
    solver?: string;
    solver_version?: string;
    physics_backend?: string;
    parameter_version?: string;
  };
}

export function resolveValidityTier(report: ValidityReport): ModelValidityTier {
  if (report.status_tier) return report.status_tier;
  const score = report.score ?? 0;
  const hasFatalCheck = report.checks?.some((c) => c.status === "fail");

  if (hasFatalCheck) return "OUT-OF-DOMAIN";
  if (score >= 80) return "VALIDATED";
  if (score >= 60) return "CONDITIONAL";
  if (score >= 35) return "EXPERIMENTAL";
  return "OUT-OF-DOMAIN";
}

const TIER_CONFIG: Record<
  ModelValidityTier,
  { label: string; color: string; bg: string; border: string; desc: string; icon: typeof ShieldCheck }
> = {
  VALIDATED: {
    label: "VALIDATED",
    color: "#10b981",
    bg: "bg-emerald-950/60",
    border: "border-emerald-500/40",
    desc: "Within calibrated test domain. Safe to base track setup decisions on.",
    icon: ShieldCheck,
  },
  CONDITIONAL: {
    label: "CONDITIONAL",
    color: "#f59e0b",
    bg: "bg-amber-950/60",
    border: "border-amber-500/40",
    desc: "Approximation in effect. Directionally accurate; validate on car.",
    icon: AlertTriangle,
  },
  EXPERIMENTAL: {
    label: "EXPERIMENTAL",
    color: "#a855f7",
    bg: "bg-purple-950/60",
    border: "border-purple-500/40",
    desc: "Exploratory formulation. Simplified assumptions or uncalibrated tire.",
    icon: Info,
  },
  "OUT-OF-DOMAIN": {
    label: "OUT-OF-DOMAIN",
    color: "#f43f5e",
    bg: "bg-rose-950/60",
    border: "border-rose-500/40",
    desc: "Parameters outside physical/solver bounds. Do not use for race decisions.",
    icon: ShieldAlert,
  },
};

const STATUS_ICONS: Record<string, JSX.Element> = {
  pass: <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />,
  warn: <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />,
  fail: <XCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />,
};

export default function ModelValidity({ report }: { report: ValidityReport | null }) {
  const [expanded, setExpanded] = useState(false);

  if (!report || !report.checks || report.checks.length === 0) return null;

  const tier = resolveValidityTier(report);
  const cfg = TIER_CONFIG[tier];
  const filled = Math.round(report.score / 10);
  const IconComponent = cfg.icon;

  return (
    <div
      className={`rounded-2xl border p-4 transition-all shadow-xl ${cfg.bg} ${cfg.border}`}
      data-testid="model-validity"
    >
      {/* Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-4 text-left select-none"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border border-white/10 bg-black/40">
            <IconComponent className="w-5 h-5" style={{ color: cfg.color }} />
          </div>

          <div className="min-w-0">
            <div className="text-xs uppercase font-mono tracking-widest text-gray-400 font-bold flex items-center gap-2">
              <span>Model Validity Status</span>
              <span className={`px-2 py-0.2 rounded-full border text-xs font-extrabold ${cfg.bg} ${cfg.border}`} style={{ color: cfg.color }}>
                {cfg.label}
              </span>
            </div>

            <div className="flex items-baseline gap-2 mt-0.5">
              <span className="text-xl font-extrabold font-mono" style={{ color: cfg.color }}>
                {Math.round(report.score)}%
              </span>
              <span className="text-xs text-gray-300 font-medium truncate">
                — {cfg.desc}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {/* 10-bar Meter */}
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
                className="w-1.5 h-4 rounded-sm transition-colors"
                style={{ backgroundColor: i < filled ? cfg.color : "#ffffff15" }}
              />
            ))}
          </div>

          <ChevronDown
            className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </div>
      </button>

      {/* Expanded Checklist & Provenance Details */}
      {expanded && (
        <div className="mt-4 pt-3 border-t border-white/10 space-y-3 font-sans text-xs">
          <ul className="space-y-2">
            {report.checks.map((check, idx) => (
              <li key={idx} className="flex items-start gap-2.5 p-2 rounded-lg bg-black/30 border border-white/5">
                {STATUS_ICONS[check.status]}
                <div className="min-w-0">
                  <span className="text-white font-bold">{check.label}</span>
                  <p className="text-gray-400 text-xs mt-0.5">{check.detail}</p>
                </div>
              </li>
            ))}
          </ul>

          {report.summary && (
            <div className="text-xs text-gray-400 italic px-1">
              {report.summary}
            </div>
          )}

          {/* Provenance Metadata */}
          <div className="p-3 rounded-xl bg-black/50 border border-white/5 text-xs font-mono text-gray-400 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Cpu size={12} className="text-signal" />
              <span>Solver: {report.provenance?.solver || "—"}</span>
            </div>
            <div>
              <span>Backend: {report.provenance?.physics_backend || "—"}</span>
            </div>
            <div>
              <span>Build: {report.provenance?.parameter_version || "—"}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
