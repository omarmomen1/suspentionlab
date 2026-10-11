"use client";

import React from "react";
import { AlertOctagon, ArrowRight, ShieldAlert, CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";

export interface StructuredErrorCardProps {
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
  className?: string;
}

export default function StructuredErrorCard({
  title = "ENGINEERING WORKFLOW STATE VIOLATION",
  whatFailed,
  why,
  whatRemainsValid,
  whatCannotBeClaimed,
  nextAction,
  actionButton,
  className = "",
}: StructuredErrorCardProps) {
  return (
    <div
      data-testid="structured-error-card"
      className={`p-6 rounded-2xl border bg-rose-950/20 border-rose-500/40 font-mono text-xs shadow-2xl backdrop-blur-md ${className}`}
    >
      <div className="flex items-center justify-between gap-3 pb-3 border-b border-rose-500/20 mb-4">
        <div className="flex items-center gap-2 text-rose-400">
          <AlertOctagon size={18} className="shrink-0 animate-pulse" />
          <span className="font-bold text-sm tracking-wider uppercase font-sans text-white">
            {title}
          </span>
        </div>
        <span className="px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-rose-950/80 border border-rose-500/60 text-rose-300">
          ZERO SILENT FALLBACK ENFORCED
        </span>
      </div>

      <div className="space-y-3 font-sans">
        {/* 1. WHAT FAILED */}
        <div className="p-3 rounded-xl bg-black/40 border border-rose-500/20">
          <div className="flex items-center gap-1.5 text-rose-400 font-bold font-mono text-[11px] mb-1">
            <XCircle size={14} className="shrink-0" />
            <span>1. WHAT FAILED</span>
          </div>
          <p className="text-gray-200 text-sm leading-relaxed" data-testid="error-what-failed">
            {whatFailed}
          </p>
        </div>

        {/* 2. WHY */}
        <div className="p-3 rounded-xl bg-black/40 border border-white/5">
          <div className="text-amber-400 font-bold font-mono text-[11px] mb-1">
            2. WHY
          </div>
          <p className="text-gray-300 text-xs leading-relaxed font-mono" data-testid="error-why">
            {why}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* 3. WHAT REMAINS VALID */}
          <div className="p-3 rounded-xl bg-black/40 border border-emerald-500/20">
            <div className="flex items-center gap-1.5 text-emerald-400 font-bold font-mono text-[11px] mb-1">
              <CheckCircle2 size={13} className="shrink-0" />
              <span>3. WHAT REMAINS VALID</span>
            </div>
            <p className="text-gray-300 text-xs leading-relaxed" data-testid="error-what-remains-valid">
              {whatRemainsValid}
            </p>
          </div>

          {/* 4. WHAT CANNOT BE CLAIMED */}
          <div className="p-3 rounded-xl bg-black/40 border border-rose-500/20">
            <div className="flex items-center gap-1.5 text-rose-400 font-bold font-mono text-[11px] mb-1">
              <ShieldAlert size={13} className="shrink-0" />
              <span>4. WHAT CANNOT BE CLAIMED</span>
            </div>
            <p className="text-gray-300 text-xs leading-relaxed" data-testid="error-what-cannot-be-claimed">
              {whatCannotBeClaimed}
            </p>
          </div>
        </div>

        {/* 5. NEXT ACTION */}
        <div className="p-3 rounded-xl bg-blue-950/30 border border-blue-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="text-blue-400 font-bold font-mono text-[11px] mb-1">
              5. NEXT ACTION
            </div>
            <div className="text-gray-200 text-xs font-mono" data-testid="error-next-action">
              {nextAction}
            </div>
          </div>

          {actionButton && (
            <div className="shrink-0">
              {actionButton.href ? (
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
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
