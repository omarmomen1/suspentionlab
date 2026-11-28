"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, AlertCircle, HelpCircle, Loader2 } from "lucide-react";

export type SystemStatusType =
  | "CURRENT"
  | "STALE"
  | "FAILED"
  | "UNAVAILABLE"
  | "PENDING"
  | "HEALTHY"
  | "DEGRADED"
  | "UNVALIDATED"
  | "PROCESSING"
  | "DATA_UNAVAILABLE";

interface EngineeringStatusProps {
  status: SystemStatusType | string;
  label?: string;
  detail?: string;
  size?: "sm" | "md";
  className?: string;
}

const STATUS_CONFIG: Record<
  string,
  {
    bg: string;
    border: string;
    text: string;
    dot: string;
    icon: any;
    defaultLabel: string;
  }
> = {
  CURRENT: {
    bg: "bg-emerald-950/40",
    border: "border-emerald-500/40",
    text: "text-emerald-400",
    dot: "bg-emerald-400",
    icon: CheckCircle2,
    defaultLabel: "CURRENT",
  },
  HEALTHY: {
    bg: "bg-emerald-950/40",
    border: "border-emerald-500/40",
    text: "text-emerald-400",
    dot: "bg-emerald-400",
    icon: CheckCircle2,
    defaultLabel: "CURRENT",
  },
  STALE: {
    bg: "bg-amber-950/40",
    border: "border-amber-500/40",
    text: "text-amber-400",
    dot: "bg-amber-400",
    icon: AlertTriangle,
    defaultLabel: "STALE",
  },
  DEGRADED: {
    bg: "bg-orange-950/40",
    border: "border-orange-500/40",
    text: "text-orange-400",
    dot: "bg-orange-400",
    icon: AlertTriangle,
    defaultLabel: "DEGRADED",
  },
  FAILED: {
    bg: "bg-rose-950/50",
    border: "border-rose-500/50",
    text: "text-rose-400",
    dot: "bg-rose-400",
    icon: AlertCircle,
    defaultLabel: "FAILED",
  },
  UNAVAILABLE: {
    bg: "bg-zinc-900",
    border: "border-zinc-700",
    text: "text-zinc-400",
    dot: "bg-zinc-600",
    icon: HelpCircle,
    defaultLabel: "UNAVAILABLE",
  },
  DATA_UNAVAILABLE: {
    bg: "bg-zinc-900",
    border: "border-zinc-700",
    text: "text-zinc-400",
    dot: "bg-zinc-600",
    icon: HelpCircle,
    defaultLabel: "UNAVAILABLE",
  },
  PENDING: {
    bg: "bg-sky-950/40",
    border: "border-sky-500/40",
    text: "text-sky-300",
    dot: "bg-sky-400",
    icon: Loader2,
    defaultLabel: "PENDING",
  },
  PROCESSING: {
    bg: "bg-purple-950/40",
    border: "border-purple-500/40",
    text: "text-purple-300",
    dot: "bg-purple-400",
    icon: Loader2,
    defaultLabel: "PROCESSING",
  },
  UNVALIDATED: {
    bg: "bg-zinc-900",
    border: "border-zinc-700",
    text: "text-zinc-400",
    dot: "bg-zinc-500",
    icon: HelpCircle,
    defaultLabel: "UNVALIDATED",
  },
};

export default function EngineeringStatus({
  status,
  label,
  detail,
  size = "md",
  className = "",
}: EngineeringStatusProps) {
  const norm = (status || "UNVALIDATED").toUpperCase().replace(" ", "_") as SystemStatusType;
  const cfg = STATUS_CONFIG[norm] || STATUS_CONFIG.UNVALIDATED;
  const Icon = cfg.icon;

  const sizeClasses = {
    sm: "px-2 py-0.5 text-xs gap-1.5",
    md: "px-3 py-1 text-xs gap-2",
  }[size];

  return (
    <div
      className={`inline-flex items-center font-mono font-bold uppercase tracking-wider rounded-lg border ${cfg.bg} ${cfg.border} ${cfg.text} ${sizeClasses} ${className}`}
      title={detail || cfg.defaultLabel}
    >
      <Icon size={size === "sm" ? 11 : 13} className={norm === "PROCESSING" ? "animate-spin" : "shrink-0"} />
      <span>{label || cfg.defaultLabel}</span>
      {detail && <span className="opacity-70 font-normal font-sans normal-case">({detail})</span>}
    </div>
  );
}
