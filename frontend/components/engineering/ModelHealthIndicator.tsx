"use client";

import React, { useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  HelpCircle,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";

export type SubsystemHealthStatus =
  | "HEALTHY"
  | "DEGRADED"
  | "DRIFTING"
  | "CRITICAL"
  | "UNVALIDATED";

export interface SubsystemHealthData {
  subsystem: string; // e.g. "Ride", "Handling", "Kinematics", "Aero", "Thermal"
  status: SubsystemHealthStatus;
  divergencePercent: number; // e.g. 2.4 (%)
  driftScore: number; // 0.0 - 1.0 (e.g. 0.12)
  lastCalibration: string; // e.g. "2026-09-06 14:32 UTC" or "Run #408"
  modelVersion?: string;
  solver?: string;
  rmsResidual?: number;
  sampleCount?: number;
  warningMessage?: string;
  trend?: "improving" | "stable" | "degrading";
}

interface ModelHealthIndicatorProps {
  data: SubsystemHealthData;
  showDetails?: boolean;
  className?: string;
}

const STATUS_CONFIG: Record<
  SubsystemHealthStatus,
  {
    bg: string;
    border: string;
    text: string;
    badge: string;
    icon: React.ComponentType<{ className?: string }>;
    label: string;
  }
> = {
  HEALTHY: {
    bg: "bg-emerald-950/20",
    border: "border-emerald-500/30",
    text: "text-emerald-400",
    badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    icon: CheckCircle2,
    label: "HEALTHY",
  },
  DEGRADED: {
    bg: "bg-amber-950/20",
    border: "border-amber-500/30",
    text: "text-amber-400",
    badge: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    icon: AlertTriangle,
    label: "DEGRADED",
  },
  DRIFTING: {
    bg: "bg-orange-950/20",
    border: "border-orange-500/30",
    text: "text-orange-400",
    badge: "bg-orange-500/10 text-orange-400 border-orange-500/30",
    icon: Activity,
    label: "DRIFTING",
  },
  CRITICAL: {
    bg: "bg-red-950/20",
    border: "border-red-500/30",
    text: "text-red-400",
    badge: "bg-red-500/10 text-red-400 border-red-500/30",
    icon: XCircle,
    label: "CRITICAL",
  },
  UNVALIDATED: {
    bg: "bg-zinc-900/40",
    border: "border-zinc-700/50",
    text: "text-zinc-400",
    badge: "bg-zinc-800 text-zinc-400 border-zinc-700",
    icon: HelpCircle,
    label: "UNVALIDATED",
  },
};

export default function ModelHealthIndicator({
  data,
  showDetails = false,
  className = "",
}: ModelHealthIndicatorProps) {
  const [expanded, setExpanded] = useState(showDetails);
  const cfg = STATUS_CONFIG[data.status] || STATUS_CONFIG.UNVALIDATED;
  const StatusIcon = cfg.icon;

  return (
    <div
      className={`rounded-lg border ${cfg.border} ${cfg.bg} p-3.5 transition-all text-sm ${className}`}
      data-testid={`model-health-${data.subsystem.toLowerCase()}`}
    >
      <div className="flex items-center justify-between gap-3">
        {/* Left: Subsystem & Status Badge */}
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded bg-zinc-900/80 border border-zinc-800">
            <StatusIcon className={`w-4 h-4 ${cfg.text}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-zinc-100">{data.subsystem}</span>
              <span
                className={`text-xs font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border ${cfg.badge}`}
              >
                {cfg.label}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs text-zinc-400 mt-0.5">
              <span className="flex items-center gap-1 font-mono">
                <Clock className="w-3 h-3 text-zinc-400" />
                {data.lastCalibration}
              </span>
              {data.modelVersion && (
                <span className="text-xs text-zinc-400 font-mono">
                  v{data.modelVersion}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Divergence & Drift Score & Accordion Toggle */}
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xs text-zinc-400 flex items-center justify-end gap-1 font-mono">
              <span>Div:</span>
              <span
                className={`font-semibold ${
                  data.divergencePercent > 5
                    ? "text-red-400"
                    : data.divergencePercent > 3
                    ? "text-amber-400"
                    : "text-emerald-400"
                }`}
              >
                {data.divergencePercent.toFixed(1)}%
              </span>
            </div>
            <div className="text-xs text-zinc-400 font-mono flex items-center justify-end gap-1">
              <span>Drift:</span>
              <span className="text-zinc-300 font-medium">
                {data.driftScore.toFixed(2)}
              </span>
              {data.trend === "improving" && (
                <TrendingDown className="w-3 h-3 text-emerald-400" />
              )}
              {data.trend === "degrading" && (
                <TrendingUp className="w-3 h-3 text-red-400" />
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="p-1 text-zinc-400 hover:text-zinc-200 rounded hover:bg-zinc-800/50 transition-colors"
            aria-label="Toggle model health details"
          >
            {expanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      {/* Warning message if any */}
      {data.warningMessage && (
        <div className="mt-2.5 px-2.5 py-1.5 rounded bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-amber-400" />
          <span>{data.warningMessage}</span>
        </div>
      )}

      {/* Expanded Technical Details */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-zinc-800 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
          <div className="bg-zinc-950/60 p-2 rounded border border-zinc-800/80">
            <span className="text-xs text-zinc-400 uppercase block">Solver</span>
            <span className="text-zinc-200">{data.solver || "RK45 (Native)"}</span>
          </div>
          <div className="bg-zinc-950/60 p-2 rounded border border-zinc-800/80">
            <span className="text-xs text-zinc-400 uppercase block">RMS Residual</span>
            <span className="text-zinc-200">
              {data.rmsResidual !== undefined ? data.rmsResidual.toFixed(4) : "—"}
            </span>
          </div>
          <div className="bg-zinc-950/60 p-2 rounded border border-zinc-800/80">
            <span className="text-xs text-zinc-400 uppercase block">Samples</span>
            <span className="text-zinc-200">
              {data.sampleCount !== undefined ? data.sampleCount.toLocaleString() : "—"}
            </span>
          </div>
          <div className="bg-zinc-950/60 p-2 rounded border border-zinc-800/80">
            <span className="text-xs text-zinc-400 uppercase block">Drift Threshold</span>
            <span className="text-zinc-200">&lt; 0.20 Max</span>
          </div>
        </div>
      )}
    </div>
  );
}
