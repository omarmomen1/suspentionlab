"use client";

import React from "react";
import {
  AlertTriangle,
  AlertCircle,
  Loader2,
  Lock,
  RefreshCw,
  HelpCircle,
  CheckCircle2,
  Inbox,
} from "lucide-react";

export type EngineeringCardStatus =
  | "loading"
  | "empty"
  | "error"
  | "stale"
  | "permission_denied"
  | "unvalidated"
  | "degraded"
  | "processing"
  | "success"
  | "idle";

interface EngineeringCardProps {
  title: string;
  subtitle?: string;
  status?: EngineeringCardStatus;
  statusMessage?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  onRetry?: () => void;
}

export default function EngineeringCard({
  title,
  subtitle,
  status = "idle",
  statusMessage,
  badge,
  actions,
  children,
  className = "",
  onRetry,
}: EngineeringCardProps) {
  return (
    <div
      className={`p-6 rounded-3xl bg-[#111116] border border-white/[0.08] shadow-2xl relative flex flex-col justify-between transition-all ${className}`}
    >
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4 pb-3 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-white tracking-tight">{title}</h2>
            {badge}
          </div>
          {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>

      {/* State Renderers */}
      <div className="flex-1">
        {status === "loading" && (
          <div className="py-12 flex flex-col items-center justify-center gap-3 text-gray-400 font-mono text-xs">
            <Loader2 size={24} className="animate-spin text-ansys-yellow" />
            <span>Resolving physical state & telemetry...</span>
          </div>
        )}

        {status === "processing" && (
          <div className="py-12 flex flex-col items-center justify-center gap-3 text-purple-300 font-mono text-xs">
            <Loader2 size={24} className="animate-spin text-purple-400" />
            <span>{statusMessage || "Executing numerical simulation..."}</span>
          </div>
        )}

        {status === "error" && (
          <div className="py-8 px-4 rounded-2xl bg-rose-950/30 border border-rose-500/40 text-center space-y-2.5 font-mono text-xs">
            <AlertCircle size={24} className="text-rose-400 mx-auto" />
            <div className="font-bold text-rose-300">SOLVER EXECUTION ERROR</div>
            <p className="text-rose-200/80 max-w-md mx-auto">{statusMessage || "Physics solver encountered a numerical singularity."}</p>
            {onRetry && (
              <button
                onClick={onRetry}
                className="mt-2 px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 transition-colors inline-flex items-center gap-1.5"
              >
                <RefreshCw size={12} /> Retry Computation
              </button>
            )}
          </div>
        )}

        {status === "permission_denied" && (
          <div className="py-8 px-4 rounded-2xl bg-zinc-900 border border-zinc-700 text-center space-y-2.5 font-mono text-xs">
            <Lock size={24} className="text-amber-400 mx-auto" />
            <div className="font-bold text-amber-300">PERMISSION DENIED (RBAC)</div>
            <p className="text-zinc-400 max-w-md mx-auto">{statusMessage || "Requires Chief Engineer seat role to modify setup parameters."}</p>
          </div>
        )}

        {status === "empty" && (
          <div className="py-12 flex flex-col items-center justify-center gap-2 text-gray-500 font-mono text-xs text-center">
            <Inbox size={24} className="text-gray-600" />
            <span>{statusMessage || "No engineering observations recorded."}</span>
          </div>
        )}

        {status === "stale" && (
          <div className="mb-4 p-2.5 rounded-xl bg-amber-950/30 border border-amber-500/30 flex items-center justify-between text-xs font-mono text-amber-300">
            <span className="flex items-center gap-2">
              <AlertTriangle size={14} /> Telemetry data is stale (&gt; 30s since DAQ heartbeat)
            </span>
            {onRetry && (
              <button onClick={onRetry} className="text-[11px] underline hover:text-white">
                Reconnect
              </button>
            )}
          </div>
        )}

        {status === "unvalidated" && (
          <div className="mb-4 p-2.5 rounded-xl bg-zinc-900 border border-zinc-700 flex items-center gap-2 text-xs font-mono text-zinc-400">
            <HelpCircle size={14} /> Model state unvalidated against on-track data.
          </div>
        )}

        {status === "degraded" && (
          <div className="mb-4 p-2.5 rounded-xl bg-orange-950/30 border border-orange-500/30 flex items-center gap-2 text-xs font-mono text-orange-300">
            <AlertTriangle size={14} /> Degraded telemetry: sensor dropouts detected in Rear Ride Height channel.
          </div>
        )}

        {status !== "loading" && status !== "processing" && status !== "error" && status !== "permission_denied" && status !== "empty" && children}
      </div>
    </div>
  );
}
