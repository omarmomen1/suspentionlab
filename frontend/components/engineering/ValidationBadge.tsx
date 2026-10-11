"use client";

import React from "react";
import { ShieldCheck, AlertTriangle, AlertCircle, HelpCircle } from "lucide-react";

export type ValidationTier =
  | "VALIDATED"
  | "CONDITIONAL"
  | "EXPERIMENTAL"
  | "OUT-OF-DOMAIN"
  | "UNVALIDATED"
  | "DATA_UNAVAILABLE";

interface ValidationBadgeProps {
  status: ValidationTier | string;
  score?: number | null;
  size?: "xs" | "sm" | "md";
  showScore?: boolean;
  className?: string;
}

const TIER_CONFIG: Record<
  ValidationTier,
  {
    bg: string;
    border: string;
    text: string;
    icon: any;
    label: string;
    meaning: string;
  }
> = {
  VALIDATED: {
    bg: "bg-emerald-950/60",
    border: "border-emerald-500/50",
    text: "text-emerald-400",
    icon: ShieldCheck,
    label: "VALIDATED",
    meaning: "Safe to base track suspension and aero decisions on.",
  },
  CONDITIONAL: {
    bg: "bg-amber-950/60",
    border: "border-amber-500/50",
    text: "text-amber-400",
    icon: AlertTriangle,
    label: "CONDITIONAL",
    meaning: "Directionally useful; validate setup changes on car before race.",
  },
  EXPERIMENTAL: {
    bg: "bg-purple-950/60",
    border: "border-purple-500/50",
    text: "text-purple-300",
    icon: AlertCircle,
    label: "EXPERIMENTAL",
    meaning: "Conceptual model only; physical limits unverified.",
  },
  "OUT-OF-DOMAIN": {
    bg: "bg-rose-950/60",
    border: "border-rose-500/50",
    text: "text-rose-400",
    icon: AlertCircle,
    label: "OUT-OF-DOMAIN",
    meaning: "Operating points exceed verified physical envelope bounds.",
  },
  UNVALIDATED: {
    bg: "bg-zinc-900",
    border: "border-zinc-700",
    text: "text-zinc-400",
    icon: HelpCircle,
    label: "UNVALIDATED",
    meaning: "No validation evidence recorded for this vehicle configuration.",
  },
  DATA_UNAVAILABLE: {
    bg: "bg-red-950/40",
    border: "border-red-500/40",
    text: "text-red-400",
    icon: HelpCircle,
    label: "DATA UNAVAILABLE",
    meaning: "Backend validation data could not be retrieved.",
  },
};

export default function ValidationBadge({
  status,
  score,
  size = "sm",
  showScore = true,
  className = "",
}: ValidationBadgeProps) {
  const normTier = (status || "UNVALIDATED").toUpperCase().replace(" ", "_") as ValidationTier;
  const cfg = TIER_CONFIG[normTier] || TIER_CONFIG.UNVALIDATED;
  const Icon = cfg.icon;

  const sizeClasses = {
    xs: "px-1.5 py-0.5 text-[9px] gap-1",
    sm: "px-2 py-0.5 text-[10px] gap-1.5",
    md: "px-2.5 py-1 text-xs gap-2",
  }[size];

  const iconSizes = { xs: 10, sm: 12, md: 14 }[size];

  return (
    <span
      className={`inline-flex items-center font-mono font-bold uppercase tracking-wider rounded-md border ${cfg.bg} ${cfg.border} ${cfg.text} ${sizeClasses} ${className}`}
      title={`${cfg.label}: ${cfg.meaning}`}
    >
      <Icon size={iconSizes} className="shrink-0" />
      <span>{cfg.label}</span>
      {showScore && typeof score === "number" && !isNaN(score) && (
        <span className="opacity-80 font-normal">({Math.round(score)}%)</span>
      )}
    </span>
  );
}
