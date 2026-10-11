"use client";

import React from "react";

export type EngineeringStateType =
  | "MEASURED"
  | "SIMULATED"
  | "ESTIMATED"
  | "CORRELATED"
  | "PREDICTED"
  | "VALIDATED"
  | "UNVALIDATED"
  | "DEGRADED"
  | "FAILED"
  | "APPROVED"
  | "REJECTED";

interface EvidenceBadgeProps {
  state: EngineeringStateType | string;
  size?: "xs" | "sm" | "md";
  className?: string;
  showIcon?: boolean;
}

const STATE_CONFIG: Record<
  EngineeringStateType,
  {
    bg: string;
    border: string;
    text: string;
    dot: string;
    desc: string;
  }
> = {
  MEASURED: {
    bg: "bg-cyan-950/40",
    border: "border-cyan-500/40",
    text: "text-cyan-400",
    dot: "bg-cyan-400",
    desc: "Acquired directly from physical sensor telemetry",
  },
  SIMULATED: {
    bg: "bg-blue-950/40",
    border: "border-blue-500/40",
    text: "text-blue-400",
    dot: "bg-blue-400",
    desc: "Calculated via verified physics ODE solver",
  },
  ESTIMATED: {
    bg: "bg-indigo-950/40",
    border: "border-indigo-500/40",
    text: "text-indigo-400",
    dot: "bg-indigo-400",
    desc: "Derived through state observer / numerical estimation",
  },
  CORRELATED: {
    bg: "bg-teal-950/40",
    border: "border-teal-500/40",
    text: "text-teal-400",
    dot: "bg-teal-400",
    desc: "Quantified agreement between simulated & physical traces",
  },
  PREDICTED: {
    bg: "bg-purple-950/40",
    border: "border-purple-500/40",
    text: "text-purple-300",
    dot: "bg-purple-400",
    desc: "Forward-projected effect from candidate setup delta",
  },
  VALIDATED: {
    bg: "bg-emerald-950/50",
    border: "border-emerald-500/50",
    text: "text-emerald-400",
    dot: "bg-emerald-400",
    desc: "Verified within proven physical operating envelope",
  },
  UNVALIDATED: {
    bg: "bg-amber-950/40",
    border: "border-amber-500/40",
    text: "text-amber-400",
    dot: "bg-amber-400",
    desc: "Operating point outside verified domain bounds",
  },
  DEGRADED: {
    bg: "bg-orange-950/40",
    border: "border-orange-500/40",
    text: "text-orange-400",
    dot: "bg-orange-400",
    desc: "High residual divergence or sensor data dropout",
  },
  FAILED: {
    bg: "bg-rose-950/50",
    border: "border-rose-500/50",
    text: "text-rose-400",
    dot: "bg-rose-400",
    desc: "Solver divergence or hard kinematic constraint violation",
  },
  APPROVED: {
    bg: "bg-ansys-yellow/15",
    border: "border-ansys-yellow/50",
    text: "text-ansys-yellow",
    dot: "bg-ansys-yellow",
    desc: "Formally signed off by engineering authority with HMAC signature",
  },
  REJECTED: {
    bg: "bg-red-950/60",
    border: "border-red-500/50",
    text: "text-red-400",
    dot: "bg-red-400",
    desc: "Rejected in setup review cycle",
  },
};

export default function EvidenceBadge({
  state,
  size = "xs",
  className = "",
  showIcon = true,
}: EvidenceBadgeProps) {
  const normState = (state || "UNVALIDATED").toUpperCase() as EngineeringStateType;
  const cfg = STATE_CONFIG[normState] || STATE_CONFIG.UNVALIDATED;

  const sizeClasses = {
    xs: "px-1.5 py-0.5 text-[9px] gap-1",
    sm: "px-2 py-0.5 text-[10px] gap-1.5",
    md: "px-2.5 py-1 text-xs gap-2",
  }[size];

  return (
    <span
      className={`inline-flex items-center font-mono font-bold uppercase tracking-wider rounded-md border ${cfg.bg} ${cfg.border} ${cfg.text} ${sizeClasses} ${className}`}
      title={`${normState}: ${cfg.desc}`}
    >
      {showIcon && <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot} shrink-0`} />}
      <span>{normState}</span>
    </span>
  );
}
