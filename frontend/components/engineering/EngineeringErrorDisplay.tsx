"use client";

import React from "react";
import { AlertOctagon, ArrowRight, ShieldAlert, CheckCircle2, XCircle, RefreshCw } from "lucide-react";
import Link from "next/link";

export interface EngineeringErrorDisplayProps {
  title?: string;
  whatFailed: string;
  why: string;
  whatRemainsValid: string;
  whatCannotBeClaimed: string;
  nextAction: string | React.ReactNode;
  actionButton?: {
    label: string;
    onClick?: () => void;
    href?: string;
  };
  onRetry?: () => void;
  onDismiss?: () => void;
  className?: string;
}

/**
 * Standardized Engineering Failure UX Display.
 * Guarantees zero silent fallbacks and strictly presents the five mandatory
 * scientific-integrity sections required for engineering decision provenance.
 */
export default function EngineeringErrorDisplay({
  title = "ENGINEERING WORKFLOW OPERATION FAILED",
  whatFailed,
  why,
  whatRemainsValid,
  whatCannotBeClaimed,
  nextAction,
  actionButton,
  onRetry,
  onDismiss,
  className = "",
}: EngineeringErrorDisplayProps) {
  return (
    <div
      data-testid="engineering-error-display"
      className={`p-6 rounded-2xl border bg-rose-950/25 border-rose-500/40 font-mono text-xs shadow-2xl backdrop-blur-md ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3 pb-3 border-b border-rose-500/20 mb-4">
        <div className="flex items-center gap-2 text-rose-400">
          <AlertOctagon size={18} className="shrink-0 animate-pulse text-rose-500" />
          <span className="font-bold text-sm tracking-wider uppercase font-sans text-white">
            {title}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-rose-950/80 border border-rose-500/60 text-rose-300">
            SCIENTIFIC INTEGRITY GUARD
          </span>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="text-gray-400 hover:text-white text-xs px-1.5 py-0.5 rounded hover:bg-white/10"
              title="Dismiss error"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      <div className="space-y-3 font-sans">
        {/* 1. WHAT FAILED */}
        <div className="p-3 rounded-xl bg-black/50 border border-rose-500/30">
          <div className="flex items-center gap-1.5 text-rose-400 font-bold font-mono text-[11px] mb-1">
            <XCircle size={14} className="shrink-0 text-rose-400" />
            <span>1. WHAT FAILED</span>
          </div>
          <p className="text-gray-100 text-sm leading-relaxed" data-testid="error-what-failed">
            {whatFailed}
          </p>
        </div>

        {/* 2. WHY */}
        <div className="p-3 rounded-xl bg-black/50 border border-amber-500/30">
          <div className="text-amber-400 font-bold font-mono text-[11px] mb-1">
            2. WHY
          </div>
          <p className="text-gray-300 text-xs leading-relaxed font-mono" data-testid="error-why">
            {why}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* 3. WHAT REMAINS VALID */}
          <div className="p-3 rounded-xl bg-black/50 border border-emerald-500/30">
            <div className="flex items-center gap-1.5 text-emerald-400 font-bold font-mono text-[11px] mb-1">
              <CheckCircle2 size={13} className="shrink-0 text-emerald-400" />
              <span>3. WHAT REMAINS VALID</span>
            </div>
            <p className="text-gray-300 text-xs leading-relaxed" data-testid="error-what-remains-valid">
              {whatRemainsValid}
            </p>
          </div>

          {/* 4. WHAT CANNOT BE CLAIMED */}
          <div className="p-3 rounded-xl bg-black/50 border border-rose-500/30">
            <div className="flex items-center gap-1.5 text-rose-400 font-bold font-mono text-[11px] mb-1">
              <ShieldAlert size={13} className="shrink-0 text-rose-400" />
              <span>4. WHAT CANNOT BE CLAIMED</span>
            </div>
            <p className="text-gray-300 text-xs leading-relaxed" data-testid="error-what-cannot-be-claimed">
              {whatCannotBeClaimed}
            </p>
          </div>
        </div>

        {/* 5. WHAT THE ENGINEER CAN DO NEXT */}
        <div className="p-3 rounded-xl bg-blue-950/40 border border-blue-500/40 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="text-blue-400 font-bold font-mono text-[11px] mb-1">
              5. WHAT THE ENGINEER CAN DO NEXT
            </div>
            <div className="text-gray-200 text-xs font-mono" data-testid="error-next-action">
              {nextAction}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-gray-200 font-mono text-xs font-semibold shadow transition-colors border border-white/10"
              >
                <RefreshCw size={12} />
                Retry
              </button>
            )}
            {actionButton && (
              actionButton.href ? (
                <Link
                  href={actionButton.href}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-mono text-xs font-semibold shadow transition-colors"
                >
                  {actionButton.label}
                  <ArrowRight size={13} />
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={actionButton.onClick}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-mono text-xs font-semibold shadow transition-colors"
                >
                  {actionButton.label}
                  <ArrowRight size={13} />
                </button>
              )
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
